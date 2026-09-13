package io.github.ym0506.routecontract.experiments.shadow;

import io.github.ym0506.routecontract.RouteAssertions;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteContractViolationException;
import org.apache.shardingsphere.driver.api.yaml.YamlShardingSphereDataSourceFactory;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.lifecycle.Startables;
import org.testcontainers.utility.DockerImageName;

import javax.sql.DataSource;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.HexFormat;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Independent released-version reproduction of apache/shardingsphere#39750. */
class ShadowInsertSelectTest {
    private static final DockerImageName MYSQL = DockerImageName.parse(
            "mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb")
            .asCompatibleSubstituteFor("mysql");
    private static final MySQLContainer<?> PRIMARY = mysql();
    private static final MySQLContainer<?> SHADOW = mysql();
    private static DataSource dataSource;

    @BeforeAll
    static void start() throws Exception {
        Path jar = Path.of(RouteContract.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        assertTrue(Files.isRegularFile(jar), "Use the released JAR, not local compiled classes");
        assertEquals("9e883e618eb09d9ecf30814151bb4b0a43eba02c78d288cc582fa7e57e6edba2",
                HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(jar))));
        Startables.deepStart(PRIMARY, SHADOW).join();
        for (var db : new MySQLContainer<?>[]{PRIMARY, SHADOW}) {
            try (Connection connection = direct(db); var statement = connection.createStatement()) {
                statement.execute("CREATE TABLE t_order (user_id INT NOT NULL, status VARCHAR(32) NOT NULL)");
                statement.execute("CREATE TABLE t_order_backup (user_id INT NOT NULL, status VARCHAR(32) NOT NULL)");
                statement.executeUpdate("INSERT INTO t_order_backup VALUES (2, 'READY')");
            }
        }
        String yaml = """
                mode:
                  type: Standalone
                dataSources:
                  primary:
                    dataSourceClassName: com.zaxxer.hikari.HikariDataSource
                    driverClassName: com.mysql.cj.jdbc.Driver
                    jdbcUrl: '%s'
                    username: routecontract
                    password: routecontract
                    maximumPoolSize: 2
                  shadow:
                    dataSourceClassName: com.zaxxer.hikari.HikariDataSource
                    driverClassName: com.mysql.cj.jdbc.Driver
                    jdbcUrl: '%s'
                    username: routecontract
                    password: routecontract
                    maximumPoolSize: 2
                rules:
                  - !SINGLE
                    tables:
                      - shadow_group.*
                    defaultDataSource: shadow_group
                  - !SHADOW
                    dataSources:
                      shadow_group:
                        productionDataSourceName: primary
                        shadowDataSourceName: shadow
                    tables:
                      t_order:
                        dataSourceNames:
                          - shadow_group
                        shadowAlgorithmNames:
                          - insert_match
                    shadowAlgorithms:
                      insert_match:
                        type: VALUE_MATCH
                        props:
                          operation: insert
                          column: user_id
                          value: 1
                props:
                  sql-show: false
                  executor-size: 2
                """.formatted(PRIMARY.getJdbcUrl(), SHADOW.getJdbcUrl());
        dataSource = YamlShardingSphereDataSourceFactory.createDataSource(yaml.getBytes(StandardCharsets.UTF_8));
    }

    @BeforeEach
    void clearTargets() throws SQLException {
        for (var db : new MySQLContainer<?>[]{PRIMARY, SHADOW}) {
            try (Connection connection = direct(db); var statement = connection.createStatement()) {
                statement.executeUpdate("DELETE FROM t_order");
            }
        }
    }

    @Test
    void nonMatchingValuesUsePrimary() throws Exception {
        check("values-nonmatching", 2, "primary", false);
    }

    @Test
    void matchingValuesUseShadow() throws Exception {
        check("values-matching", 1, "shadow", false);
    }

    @Test
    void insertSelectReturnsOneButWritesToShadow() throws Exception {
        check("insert-select-nonmatching", 2, "shadow", true);
    }

    private static void check(String name, int userId, String observed, boolean insertSelect) throws Exception {
        var captured = RouteContract.captureResult(name, () -> {
            try (Connection connection = dataSource.getConnection(); var statement = connection.prepareStatement(
                    insertSelect ? "INSERT INTO t_order (user_id, status) SELECT user_id, status FROM t_order_backup"
                            : "INSERT INTO t_order (user_id, status) VALUES (?, ?)")) {
                if (!insertSelect) {
                    statement.setInt(1, userId);
                    statement.setString(2, "READY");
                }
                return statement.executeUpdate();
            }
        });
        assertEquals(1, captured.value());
        RouteAssertions.assertThat(captured.snapshot())
                .hasCompleteCapture().hasExactlyObservedPhysicalAttempts(1).observesExactlyDataSourceNames(observed);
        int primaryRows = rows(PRIMARY, userId);
        int shadowRows = rows(SHADOW, userId);
        assertEquals(observed.equals("primary") ? 1 : 0, primaryRows);
        assertEquals(observed.equals("shadow") ? 1 : 0, shadowRows);
        System.out.printf("RESULT case=%s affected=%d attempts=%d dataSources=%s primaryRows=%d shadowRows=%d%n",
                name, captured.value(), captured.snapshot().observedPhysicalAttemptCount(),
                captured.snapshot().observedDataSourceNames(), primaryRows, shadowRows);
        if (insertSelect) {
            Runnable primaryContract = () -> RouteAssertions.assertThat(captured.snapshot())
                    .hasExactlyObservedPhysicalAttempts(1).observesExactlyDataSourceNames("primary");
            if (Boolean.parseBoolean(System.getProperty("shadow.enforceProduction", "false"))) {
                primaryContract.run();
            } else {
                var violation = assertThrows(RouteContractViolationException.class, primaryContract::run);
                assertTrue(violation.getMessage().contains("expected observed data-source names [primary], but observed [shadow]"));
                System.out.println("EXPECTED_CONTRACT_FAILURE " + violation.getMessage());
            }
        }
    }

    private static int rows(MySQLContainer<?> db, int userId) throws SQLException {
        try (Connection connection = direct(db); var statement = connection.createStatement();
             var result = statement.executeQuery("SELECT user_id, status FROM t_order")) {
            int count = 0;
            while (result.next()) {
                assertEquals(userId, result.getInt(1));
                assertEquals("READY", result.getString(2));
                count++;
            }
            return count;
        }
    }

    private static Connection direct(MySQLContainer<?> db) throws SQLException {
        return DriverManager.getConnection(db.getJdbcUrl(), db.getUsername(), db.getPassword());
    }

    private static MySQLContainer<?> mysql() {
        return new MySQLContainer<>(MYSQL).withDatabaseName("routecontract")
                .withUsername("routecontract").withPassword("routecontract");
    }

    @AfterAll
    static void stop() throws Exception {
        try {
            if (dataSource instanceof AutoCloseable closeable) {
                closeable.close();
            }
        } finally {
            try {
                PRIMARY.stop();
            } finally {
                SHADOW.stop();
            }
        }
    }
}
