package io.github.ym0506.routecontract.examples.gradle.kotlin;

import org.apache.shardingsphere.driver.api.yaml.YamlShardingSphereDataSourceFactory;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.utility.DockerImageName;

import javax.sql.DataSource;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;

final class MySqlShardingFixture implements AutoCloseable {

    private static final DockerImageName MYSQL_IMAGE = DockerImageName.parse(
            "mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb")
            .asCompatibleSubstituteFor("mysql");

    private final MySQLContainer<?> mysql = new MySQLContainer<>(MYSQL_IMAGE);
    private DataSource shardingDataSource;

    DataSource start() throws Exception {
        mysql.start();
        try (Connection connection = DriverManager.getConnection(
                mysql.getJdbcUrl(), mysql.getUsername(), mysql.getPassword());
             Statement statement = connection.createStatement()) {
            statement.executeUpdate("CREATE TABLE t_order_0 ("
                    + "order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, "
                    + "status VARCHAR(32) NOT NULL)");
            statement.executeUpdate("CREATE TABLE t_order_1 ("
                    + "order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, "
                    + "status VARCHAR(32) NOT NULL)");
            statement.executeUpdate(
                    "INSERT INTO t_order_1(order_id, user_id, status) VALUES (201, 3, 'PAID')");
        }

        String yaml = """
                mode:
                  type: Standalone
                dataSources:
                  ds_0:
                    dataSourceClassName: com.zaxxer.hikari.HikariDataSource
                    driverClassName: com.mysql.cj.jdbc.Driver
                    jdbcUrl: 'MYSQL_URL'
                    username: 'MYSQL_USER'
                    password: 'MYSQL_PASSWORD'
                rules:
                  - !SHARDING
                    tables:
                      t_order:
                        actualDataNodes: ds_0.t_order_${0..1}
                        tableStrategy:
                          standard:
                            shardingColumn: user_id
                            shardingAlgorithmName: table_inline
                    shardingAlgorithms:
                      table_inline:
                        type: INLINE
                        props:
                          algorithm-expression: t_order_${user_id % 2}
                          allow-range-query-with-inline-sharding: true
                props:
                  sql-show: false
                  executor-size: 2
                """
                .replace("MYSQL_URL", mysql.getJdbcUrl())
                .replace("MYSQL_USER", mysql.getUsername())
                .replace("MYSQL_PASSWORD", mysql.getPassword());
        shardingDataSource = YamlShardingSphereDataSourceFactory.createDataSource(
                yaml.getBytes(StandardCharsets.UTF_8));
        return shardingDataSource;
    }

    @Override
    public void close() throws Exception {
        try {
            if (shardingDataSource instanceof AutoCloseable closeable) {
                closeable.close();
            }
        } finally {
            mysql.stop();
        }
    }
}
