package io.github.ym0506.routecontract.example;

import io.github.ym0506.routecontract.AttemptOutcome;
import io.github.ym0506.routecontract.CaptureStatus;
import io.github.ym0506.routecontract.PhysicalExecutionAttempt;
import io.github.ym0506.routecontract.RouteAssertions;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteContractViolationException;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.ThreadRole;
import io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook;
import io.github.ym0506.routecontract.manifest.DataSourceAliases;
import io.github.ym0506.routecontract.manifest.ManifestAssertions;
import io.github.ym0506.routecontract.manifest.ManifestCodec;
import io.github.ym0506.routecontract.manifest.ManifestDiffCode;
import io.github.ym0506.routecontract.manifest.ManifestPolicy;
import io.github.ym0506.routecontract.manifest.ManifestVerificationResult;
import io.github.ym0506.routecontract.manifest.ManifestVerifier;
import io.github.ym0506.routecontract.manifest.ObservedExecutionManifest;
import io.github.ym0506.routecontract.manifest.VerificationStatus;
import org.apache.shardingsphere.driver.api.yaml.YamlShardingSphereDataSourceFactory;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import javax.sql.DataSource;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class OperationCorrelationMySqlTest {

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
        initialize(DS_0);
        initialize(DS_1);
        try (Connection ds0 = physicalConnection(DS_0);
             Connection ds1 = physicalConnection(DS_1)) {
            ds0.createStatement().executeUpdate(
                    "INSERT INTO t_order_0(order_id, user_id, status) VALUES (202, 2, 'PAID')");
            ds1.createStatement().executeUpdate(
                    "INSERT INTO t_order_1(order_id, user_id, status) VALUES (201, 3, 'PAID')");
        }

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
                      t_order:
                        actualDataNodes: ds_${0..1}.t_order_${0..1}
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
                          algorithm-expression: t_order_${user_id % 2}
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
    @Order(1)
    void firstWorkerReceivesSubmissionContextButRawChildDoesNotInheritIt() throws Exception {
        RouteSnapshot first = RouteContract.capture("first-operation", () -> {
            Thread rawChild = new Thread(() -> {
                RouteContractSqlExecutionHook hook = new RouteContractSqlExecutionHook();
                hook.start("raw-child-must-not-be-captured", "SELECT 1", List.of(), null, false);
                hook.finishSuccess();
            }, "raw-child-without-ttl-wrapper");
            rawChild.start();
            rawChild.join();

            assertEquals(1, executeEqual(3L));
            assertEquals(1, executeFanOut(3L));
        });

        assertSnapshot(first, 3, Set.of("ds_0", "ds_1"));
        assertFalse(first.observedDataSourceNames().contains("raw-child-must-not-be-captured"));
        assertEquals(2, first.trunkThreadFlagCount());
        assertEquals(1, first.workerThreadFlagCount());

        assertEquals(1, executeFanOut(3L), "an unscoped query must still execute normally");

        RouteSnapshot second = RouteContract.capture("second-operation", () -> assertEquals(1, executeEqual(2L)));
        assertSnapshot(second, 1, Set.of("ds_0"));
    }

    @Test
    @Order(2)
    void fanOutSnapshotIsDeterministicAcrossTwentyCaptures() throws Exception {
        Set<String> signatures = new HashSet<>();
        for (int iteration = 0; iteration < 20; iteration++) {
            RouteSnapshot snapshot = RouteContract.capture(
                    "repeat-" + iteration,
                    () -> assertEquals(1, executeFanOut(3L)));
            assertSnapshot(snapshot, 2, Set.of("ds_0", "ds_1"));
            assertEquals(1, snapshot.trunkThreadFlagCount());
            assertEquals(1, snapshot.workerThreadFlagCount());
            signatures.add(canonicalSignature(snapshot));
        }
        assertEquals(1, signatures.size(), "all twenty semantic snapshots must be identical");
        System.out.println("ROUTECONTRACT_DETERMINISM repetitions=20 uniqueSignatures=" + signatures.size());
    }

    @Test
    @Order(3)
    void concurrentSingleAndFanOutOperationsRemainIsolatedAcrossTwentyPairs() throws Exception {
        ExecutorService callers = Executors.newFixedThreadPool(2);
        try {
            for (int iteration = 0; iteration < 20; iteration++) {
                CyclicBarrier bothCapturesOpen = new CyclicBarrier(2);
                Future<RouteSnapshot> single = callers.submit(capturedEqual("single-" + iteration, 3L, bothCapturesOpen));
                Future<RouteSnapshot> fanOut = callers.submit(capturedFanOut("fanout-" + iteration, 2L, bothCapturesOpen));

                RouteSnapshot singleSnapshot = single.get();
                RouteSnapshot fanOutSnapshot = fanOut.get();
                assertSnapshot(singleSnapshot, 1, Set.of("ds_1"));
                assertSnapshot(fanOutSnapshot, 2, Set.of("ds_0", "ds_1"));
                assertEquals(0, singleSnapshot.workerThreadFlagCount());
                assertEquals(1, fanOutSnapshot.workerThreadFlagCount());
            }
        } finally {
            callers.shutdownNow();
        }
        System.out.println("ROUTECONTRACT_CONCURRENCY simultaneousPairs=20 mixedCaptures=0");
    }

    @Test
    @Order(4)
    void functionallyEquivalentRangeQueryFailsCanonicalManifestContractWithActionableCiEvidence()
            throws Exception {
        RouteSnapshot equality = RouteContract.capture(
                "find-paid-orders-by-user",
                () -> assertEquals(1, executeEqual(3L)));
        RouteSnapshot range = RouteContract.capture(
                "find-paid-orders-by-user",
                () -> assertEquals(1, executeFanOut(3L)));

        RouteAssertions.assertThat(equality)
                .hasExactlyObservedPhysicalAttempts(1)
                .observesExactlyDataSourceNames("ds_1")
                .hasCompleteCapture()
                .hasNoReportedExecutionFailures();
        assertSnapshot(range, 2, Set.of("ds_0", "ds_1"));

        AssertionError violation = org.junit.jupiter.api.Assertions.assertThrows(
                AssertionError.class,
                () -> RouteAssertions.assertThat(range).hasAtMostObservedPhysicalAttempts(1));
        assertTrue(violation.getMessage().contains("observed 2"));

        DataSourceAliases aliases = DataSourceAliases.of(Map.of(
                "ds_0", "orders-even",
                "ds_1", "orders-odd"));
        ManifestPolicy strictPolicy = ManifestPolicy.strict(1, 1);
        ManifestCodec codec = new ManifestCodec();
        ObservedExecutionManifest approved = ObservedExecutionManifest.from(
                equality, aliases, strictPolicy);
        byte[] approvedBytes = codec.encode(approved);
        ObservedExecutionManifest approvedRoundTrip = codec.decode(approvedBytes);
        assertArrayEquals(approvedBytes, codec.encode(approvedRoundTrip),
                "approved manifest bytes must be canonical after a strict decode/encode round trip");

        ObservedExecutionManifest candidate = ObservedExecutionManifest.from(
                range, aliases, strictPolicy);
        byte[] candidateBytes = codec.encode(candidate);
        Path demoEvidenceDirectory = Path.of("build", "routecontract-demo");
        Files.createDirectories(demoEvidenceDirectory);
        Files.write(demoEvidenceDirectory.resolve("find-paid-orders-by-user.approved.json"), approvedBytes);
        Files.write(demoEvidenceDirectory.resolve("find-paid-orders-by-user.candidate.json"), candidateBytes);
        Path committedExampleDirectory = Path.of(
                System.getProperty("routecontract.repositoryRoot"), "examples", "manifests");
        assertArrayEquals(
                Files.readAllBytes(committedExampleDirectory.resolve(
                        "find-paid-orders-by-user.approved.json")),
                approvedBytes,
                "the checked-in approved example must be the exact canonical MySQL evidence");
        assertArrayEquals(
                Files.readAllBytes(committedExampleDirectory.resolve(
                        "find-paid-orders-by-user.candidate.json")),
                candidateBytes,
                "the checked-in candidate example must be the exact canonical MySQL evidence");
        ManifestVerificationResult verification = new ManifestVerifier().verify(
                approvedRoundTrip, candidate);

        assertEquals(VerificationStatus.POLICY_VIOLATION, verification.status());
        assertEquals(
                List.of(
                        ManifestDiffCode.ATTEMPT_BUDGET_EXCEEDED,
                        ManifestDiffCode.DATA_SOURCE_BUDGET_EXCEEDED),
                verification.diffs().stream().map(diff -> diff.code()).toList(),
                "policy findings must remain deterministic for CI consumers");
        assertEquals(
                verification,
                new ManifestVerifier().verify(approvedRoundTrip, range, aliases),
                "direct snapshot verification must produce the same deterministic result");
        List<String> actualDiff = verification.diffs().stream()
                .map(diff -> diff.code().stableCode() + " " + diff.severity() + " "
                        + diff.code() + ": " + diff.detail())
                .toList();
        assertEquals(
                Files.readAllLines(
                        committedExampleDirectory.resolve("find-paid-orders-by-user.expected-diff.txt"),
                        StandardCharsets.UTF_8),
                actualDiff,
                "the checked-in semantic diff must match the verifier output exactly");

        AssertionError manifestViolation = org.junit.jupiter.api.Assertions.assertThrows(
                AssertionError.class,
                () -> ManifestAssertions.assertMatched(verification));
        assertEquals(RouteContractViolationException.class, manifestViolation.getClass());
        assertTrue(manifestViolation.getMessage().contains("status=POLICY_VIOLATION"));
        assertTrue(manifestViolation.getMessage().contains(
                "RCM201 BLOCKING ATTEMPT_BUDGET_EXCEEDED: maximum=1, observed=2"));
        assertTrue(manifestViolation.getMessage().contains(
                "RCM202 BLOCKING DATA_SOURCE_BUDGET_EXCEEDED: maximum=1, observed=2"));

        String externallyVisibleEvidence = new String(approvedBytes, StandardCharsets.UTF_8)
                + new String(candidateBytes, StandardCharsets.UTF_8)
                + verification
                + manifestViolation.getMessage();
        for (String sensitiveText : List.of("SELECT", "t_order", "PAID")) {
            assertFalse(
                    externallyVisibleEvidence.contains(sensitiveText),
                    () -> "manifest CI evidence exposed SQL or a bound value: " + sensitiveText);
        }

        System.out.println("ROUTECONTRACT_MANIFEST_DEMO businessResult=UNCHANGED "
                + "observedPhysicalAttempts=1->2 verificationStatus=" + verification.status()
                + " blockingCodes=[RCM201,RCM202] privacy=MINIMIZED");
    }

    @Test
    @Order(5)
    void capturedEvidenceContainsNoRawParameterOrSqlText() throws Exception {
        String secret = "do-not-store-this-secret-value";
        RouteSnapshot snapshot = RouteContract.capture(
                "privacy",
                () -> assertEquals(0, executeByStatus(secret)));

        assertSnapshot(snapshot, 2, Set.of("ds_0", "ds_1"));
        assertFalse(snapshot.toString().contains(secret));
        assertFalse(snapshot.toString().contains("SELECT"));
        assertTrue(snapshot.attempts().stream().allMatch(attempt -> attempt.parameterCount() == 2));
        assertTrue(snapshot.attempts().stream().allMatch(attempt -> attempt.parameterTypes()
                .equals(List.of(String.class.getName(), String.class.getName()))));
    }

    private static Callable<RouteSnapshot> capturedEqual(
            final String operationId,
            final long userId,
            final CyclicBarrier barrier) {
        return () -> RouteContract.capture(operationId, () -> {
            barrier.await();
            assertEquals(1, executeEqual(userId));
        });
    }

    private static Callable<RouteSnapshot> capturedFanOut(
            final String operationId,
            final long userId,
            final CyclicBarrier barrier) {
        return () -> RouteContract.capture(operationId, () -> {
            barrier.await();
            assertEquals(1, executeFanOut(userId));
        });
    }

    private static int executeEqual(final long userId) throws Exception {
        return execute(
                "SELECT order_id, user_id, status FROM t_order WHERE user_id = ? AND status = ?",
                statement -> {
                    statement.setLong(1, userId);
                    statement.setString(2, "PAID");
                });
    }

    private static int executeFanOut(final long userId) throws Exception {
        return execute(
                "SELECT order_id, user_id, status FROM t_order WHERE user_id BETWEEN ? AND ? AND status = ?",
                statement -> {
                    statement.setLong(1, userId);
                    statement.setLong(2, userId);
                    statement.setString(3, "PAID");
                });
    }

    private static int executeByStatus(final String status) throws Exception {
        return execute(
                "SELECT order_id, user_id, status FROM t_order WHERE status = ?",
                statement -> statement.setString(1, status));
    }

    private static int execute(final String sql, final StatementBinder binder) throws Exception {
        try (Connection connection = shardingDataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            binder.bind(statement);
            int rows = 0;
            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    rows++;
                }
            }
            return rows;
        }
    }

    private static void assertSnapshot(
            final RouteSnapshot snapshot,
            final int expectedAttempts,
            final Set<String> expectedDataSourceNames) {
        assertEquals(CaptureStatus.COMPLETE, snapshot.status(), () -> "snapshot=" + snapshot);
        assertEquals(expectedAttempts, snapshot.observedPhysicalAttemptCount(), () -> "snapshot=" + snapshot);
        assertEquals(expectedDataSourceNames, Set.copyOf(snapshot.observedDataSourceNames()));
        assertTrue(snapshot.attempts().stream()
                .allMatch(attempt -> attempt.outcome() == AttemptOutcome.CALLBACK_RETURNED));
    }

    private static String canonicalSignature(final RouteSnapshot snapshot) {
        return snapshot.attempts().stream()
                .map(OperationCorrelationMySqlTest::canonicalAttempt)
                .sorted()
                .reduce((left, right) -> left + ";" + right)
                .orElse("");
    }

    private static String canonicalAttempt(final PhysicalExecutionAttempt attempt) {
        return attempt.observedDataSourceName()
                + "|" + attempt.sqlFingerprint()
                + "|" + attempt.parameterCount()
                + "|" + attempt.parameterTypes()
                + "|" + attempt.outcome();
    }

    private static MySQLContainer<?> mysql() {
        return new MySQLContainer<>(MYSQL_IMAGE)
                .withDatabaseName("routecontract")
                .withUsername("routecontract")
                .withPassword("routecontract");
    }

    private static Connection physicalConnection(final MySQLContainer<?> container) throws Exception {
        return DriverManager.getConnection(container.getJdbcUrl(), container.getUsername(), container.getPassword());
    }

    private static void initialize(final MySQLContainer<?> container) throws Exception {
        try (Connection connection = physicalConnection(container);
             Statement statement = connection.createStatement()) {
            statement.execute("CREATE TABLE t_order_0 (order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
            statement.execute("CREATE TABLE t_order_1 (order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
        }
    }

    @FunctionalInterface
    private interface StatementBinder {
        void bind(PreparedStatement statement) throws Exception;
    }
}
