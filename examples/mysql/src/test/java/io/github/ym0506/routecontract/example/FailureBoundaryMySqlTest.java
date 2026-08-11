package io.github.ym0506.routecontract.example;

import io.github.ym0506.routecontract.CaptureStatus;
import io.github.ym0506.routecontract.RouteAssertions;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteContractViolationException;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.manifest.DataSourceAliases;
import io.github.ym0506.routecontract.manifest.ManifestDiffCode;
import io.github.ym0506.routecontract.manifest.ManifestPolicy;
import io.github.ym0506.routecontract.manifest.ManifestVerificationResult;
import io.github.ym0506.routecontract.manifest.ManifestVerifier;
import io.github.ym0506.routecontract.manifest.ObservedExecutionManifest;
import io.github.ym0506.routecontract.manifest.VerificationStatus;
import org.apache.shardingsphere.driver.api.yaml.YamlShardingSphereDataSourceFactory;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import javax.sql.DataSource;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class FailureBoundaryMySqlTest {

    private static final DockerImageName MYSQL_IMAGE = DockerImageName.parse(
            "mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb")
            .asCompatibleSubstituteFor("mysql");

    @Container
    private static final MySQLContainer<?> DS_0 = mysql();

    @Container
    private static final MySQLContainer<?> DS_1 = mysql();

    private static DataSource shardingDataSource;

    @BeforeAll
    static void createPhysicalSchemaAndDataSource() throws Exception {
        initialize(DS_0, 200L, 0);
        initialize(DS_1, 201L, 1);

        String yaml = """
                mode:
                  type: Standalone
                dataSources:
                  ds_0:
                    dataSourceClassName: com.zaxxer.hikari.HikariDataSource
                    driverClassName: com.mysql.cj.jdbc.Driver
                    jdbcUrl: 'DS0_URL'
                    username: 'DS0_USER'
                    password: 'DS0_PASSWORD'
                  ds_1:
                    dataSourceClassName: com.zaxxer.hikari.HikariDataSource
                    driverClassName: com.mysql.cj.jdbc.Driver
                    jdbcUrl: 'DS1_URL'
                    username: 'DS1_USER'
                    password: 'DS1_PASSWORD'
                rules:
                  - !SHARDING
                    tables:
                      t_failure:
                        actualDataNodes: ds_${0..1}.t_failure_${0..1}
                        databaseStrategy:
                          standard:
                            shardingColumn: user_id
                            shardingAlgorithmName: database_inline
                        tableStrategy:
                          standard:
                            shardingColumn: user_id
                            shardingAlgorithmName: table_inline
                    shardingAlgorithms:
                      database_inline:
                        type: INLINE
                        props:
                          algorithm-expression: ds_${user_id % 2}
                          allow-range-query-with-inline-sharding: true
                      table_inline:
                        type: INLINE
                        props:
                          algorithm-expression: t_failure_${user_id % 2}
                          allow-range-query-with-inline-sharding: true
                props:
                  sql-show: false
                  executor-size: 4
                """
                .replace("DS0_URL", DS_0.getJdbcUrl())
                .replace("DS0_USER", DS_0.getUsername())
                .replace("DS0_PASSWORD", DS_0.getPassword())
                .replace("DS1_URL", DS_1.getJdbcUrl())
                .replace("DS1_USER", DS_1.getUsername())
                .replace("DS1_PASSWORD", DS_1.getPassword());
        shardingDataSource = YamlShardingSphereDataSourceFactory.createDataSource(
                yaml.getBytes(StandardCharsets.UTF_8));
    }

    @AfterAll
    static void closeDataSource() throws Exception {
        if (shardingDataSource instanceof AutoCloseable closeable) {
            closeable.close();
        }
    }

    @Test
    void caughtFanOutJdbcFailureCannotBeCertifiedByBudgetsOrManifest() throws Exception {
        String operationId = "find-active-failures";
        RouteSnapshot approvedSnapshot = RouteContract.capture(
                operationId,
                () -> assertEquals(2, executeFanOut()));
        RouteAssertions.assertThat(approvedSnapshot)
                .hasCompleteCapture()
                .hasExactlyObservedPhysicalAttempts(2)
                .observesExactlyDataSourceNames("ds_0", "ds_1");
        ObservedExecutionManifest approved = ObservedExecutionManifest.from(
                approvedSnapshot,
                aliases(),
                ManifestPolicy.strict(2, 2));

        try (Connection connection = physicalConnection(DS_1);
             Statement statement = connection.createStatement()) {
            statement.execute("DROP TABLE t_failure_1");
        }

        AtomicReference<SQLException> caughtByApplication = new AtomicReference<>();
        RouteSnapshot failedSnapshot = RouteContract.capture(operationId, () -> {
            try {
                executeFanOut();
            } catch (SQLException failure) {
                caughtByApplication.set(failure);
            }
        });

        assertNotNull(caughtByApplication.get(), "the application must catch a real physical JDBC failure");
        // Do not require an exact total attempt count here. ShardingSphere 5.5.3 may leave a
        // submitted group unjoined when a parallel group fails; either timing must remain
        // diagnostic-only and must never satisfy a positive route contract.
        assertNotEquals(
                CaptureStatus.COMPLETE,
                failedSnapshot.status(),
                () -> "callback-reported failure was incorrectly contract-eligible: " + failedSnapshot);
        assertTrue(
                failedSnapshot.callbackFailureCount() >= 1,
                () -> "the missing physical table did not produce a failure callback: " + failedSnapshot);

        RouteContractViolationException budgetFailure = assertThrows(
                RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(failedSnapshot)
                        .hasAtMostObservedPhysicalAttempts(Integer.MAX_VALUE));
        assertTrue(budgetFailure.getMessage().contains("contract-eligible COMPLETE"));

        ManifestVerificationResult directVerification = new ManifestVerifier().verify(
                approved,
                failedSnapshot,
                aliases());
        assertEquals(VerificationStatus.NOT_ELIGIBLE, directVerification.status());
        assertEquals(1, directVerification.diffs().size());
        ManifestDiffCode expectedCode = failedSnapshot.status() == CaptureStatus.INCOMPLETE
                ? ManifestDiffCode.CAPTURE_INCOMPLETE
                : ManifestDiffCode.CALLBACK_FAILURE_NOT_ELIGIBLE;
        assertEquals(expectedCode, directVerification.diffs().get(0).code());

        ObservedExecutionManifest diagnosticCandidate = ObservedExecutionManifest.from(
                failedSnapshot,
                aliases(),
                approved.policy());
        ManifestVerificationResult diagnosticVerification = new ManifestVerifier().verify(
                approved,
                diagnosticCandidate);
        assertEquals(VerificationStatus.NOT_ELIGIBLE, diagnosticVerification.status());
        assertEquals(1, diagnosticVerification.diffs().size());
        assertEquals(
                expectedCode,
                diagnosticVerification.diffs().get(0).code(),
                "diagnostic manifest conversion must not turn a failure-bearing capture into a match");
    }

    private static int executeFanOut() throws SQLException {
        try (Connection connection = shardingDataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT order_id FROM t_failure WHERE status = ?")) {
            statement.setString(1, "ACTIVE");
            int rows = 0;
            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    rows++;
                }
            }
            return rows;
        }
    }

    private static DataSourceAliases aliases() {
        return DataSourceAliases.of(Map.of(
                "ds_0", "failures-even",
                "ds_1", "failures-odd"));
    }

    private static MySQLContainer<?> mysql() {
        return new MySQLContainer<>(MYSQL_IMAGE)
                .withDatabaseName("routecontract")
                .withUsername("routecontract")
                .withPassword("routecontract");
    }

    private static Connection physicalConnection(final MySQLContainer<?> container) throws SQLException {
        return DriverManager.getConnection(
                container.getJdbcUrl(),
                container.getUsername(),
                container.getPassword());
    }

    private static void initialize(
            final MySQLContainer<?> container,
            final long orderId,
            final int targetTableSuffix) throws SQLException {
        try (Connection connection = physicalConnection(container);
             Statement statement = connection.createStatement()) {
            statement.execute("CREATE TABLE t_failure_0"
                    + " (order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
            statement.execute("CREATE TABLE t_failure_1"
                    + " (order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
            statement.executeUpdate("INSERT INTO t_failure_" + targetTableSuffix
                    + "(order_id, user_id, status) VALUES (" + orderId + ", " + (orderId % 2) + ", 'ACTIVE')");
        }
    }
}
