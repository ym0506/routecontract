package io.github.ym0506.routecontract.examples.firstproject;

import org.apache.shardingsphere.driver.api.yaml.YamlShardingSphereDataSourceFactory;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.lifecycle.Startables;
import org.testcontainers.utility.DockerImageName;

import javax.sql.DataSource;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;

/** Two disposable MySQL instances; never connects to an application's database. */
final class OrderFixture {
    private static final DockerImageName MYSQL = DockerImageName.parse(
            "mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb")
            .asCompatibleSubstituteFor("mysql");
    private final MySQLContainer<?> even = mysql();
    private final MySQLContainer<?> odd = mysql();
    private DataSource dataSource;

    void start() throws Exception {
        Startables.deepStart(even, odd).join();
        initialize(even, "INSERT INTO t_order_0 VALUES (202, 2, 'PAID')");
        initialize(odd, "INSERT INTO t_order_1 VALUES (201, 3, 'PAID')");
        String yaml;
        try (var input = OrderFixture.class.getResourceAsStream("/sharding.yaml")) {
            if (input == null) {
                throw new IllegalStateException("Missing fixture resource: sharding.yaml");
            }
            yaml = new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
        yaml = yaml.replace("EVEN_URL", even.getJdbcUrl()).replace("ODD_URL", odd.getJdbcUrl());
        dataSource = YamlShardingSphereDataSourceFactory.createDataSource(yaml.getBytes(StandardCharsets.UTF_8));
    }

    DataSource dataSource() {
        return dataSource;
    }

    void close() throws Exception {
        try {
            if (dataSource instanceof AutoCloseable closeable) {
                closeable.close();
            }
        } finally {
            try {
                even.stop();
            } finally {
                odd.stop();
            }
        }
    }

    private static MySQLContainer<?> mysql() {
        return new MySQLContainer<>(MYSQL).withDatabaseName("routecontract")
                .withUsername("routecontract").withPassword("routecontract");
    }

    private static void initialize(MySQLContainer<?> container, String insert) throws Exception {
        try (Connection connection = DriverManager.getConnection(
                container.getJdbcUrl(), container.getUsername(), container.getPassword());
             Statement statement = connection.createStatement()) {
            for (int table = 0; table < 2; table++) {
                statement.execute("CREATE TABLE t_order_" + table
                        + " (order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
            }
            statement.executeUpdate(insert);
        }
    }
}
