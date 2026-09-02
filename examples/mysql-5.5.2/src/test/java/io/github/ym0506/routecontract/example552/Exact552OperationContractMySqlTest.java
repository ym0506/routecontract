package io.github.ym0506.routecontract.example552;

import io.github.ym0506.routecontract.AttemptOutcome;
import io.github.ym0506.routecontract.CaptureStatus;
import io.github.ym0506.routecontract.PhysicalExecutionAttempt;
import io.github.ym0506.routecontract.RouteAssertions;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteContractViolationException;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import io.github.ym0506.routecontract.manifest.DataSourceAliases;
import io.github.ym0506.routecontract.manifest.ManifestCodec;
import io.github.ym0506.routecontract.manifest.ManifestDiffCode;
import io.github.ym0506.routecontract.manifest.ManifestPolicy;
import io.github.ym0506.routecontract.manifest.ManifestVerificationResult;
import io.github.ym0506.routecontract.manifest.ManifestVerifier;
import io.github.ym0506.routecontract.manifest.ObservedExecutionManifest;
import io.github.ym0506.routecontract.manifest.VerificationStatus;
import io.github.ym0506.routecontract.shardingsphere552.internal.RouteContract552SqlExecutionHook;
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
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class Exact552OperationContractMySqlTest {

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
            ds0.createStatement().executeUpdate(
                    "INSERT INTO t_failure_0(order_id, user_id, status) VALUES (302, 2, 'ACTIVE')");
            ds1.createStatement().executeUpdate(
                    "INSERT INTO t_failure_1(order_id, user_id, status) VALUES (301, 3, 'ACTIVE')");
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
                      t_failure:
                        actualDataNodes: ds_${0..1}.t_failure_${0..1}
                        databaseStrategy:
                          standard:
                            shardingColumn: user_id
                            shardingAlgorithmName: database_inline
                        tableStrategy:
                          standard:
                            shardingColumn: user_id
                            shardingAlgorithmName: failure_table_inline
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
                      failure_table_inline:
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
    @Order(1)
    void ordinarySqlAndSuccessiveCapturesRemainIsolatedOnExact552() throws Exception {
        assertEquals(1, executeEqual(3L), "ordinary SQL before capture must remain unaffected");

        RouteSnapshot equality = RouteContract.capture(
                "552-first-equality", () -> assertEquals(1, executeEqual(3L)));
        assertSnapshot(equality, 1, Set.of("ds_1"));

        assertEquals(1, executeFanOut(3L), "ordinary SQL between captures must remain unaffected");

        RouteSnapshot range = RouteContract.capture(
                "552-second-range", () -> assertEquals(1, executeFanOut(3L)));
        assertSnapshot(range, 2, Set.of("ds_0", "ds_1"));

        RouteSnapshot finalEquality = RouteContract.capture(
                "552-third-equality", () -> assertEquals(1, executeEqual(2L)));
        assertSnapshot(finalEquality, 1, Set.of("ds_0"));
        assertEquals(1, executeEqual(2L), "ordinary SQL after capture must remain unaffected");
    }

    @Test
    @Order(2)
    void sameBusinessResultProducesCanonicalExact552PolicyEvidence() throws Exception {
        RouteSnapshot equality = RouteContract.capture(
                "find-paid-orders-by-user", () -> assertEquals(1, executeEqual(3L)));
        RouteSnapshot range = RouteContract.capture(
                "find-paid-orders-by-user", () -> assertEquals(1, executeFanOut(3L)));
        assertSnapshot(equality, 1, Set.of("ds_1"));
        assertSnapshot(range, 2, Set.of("ds_0", "ds_1"));

        DataSourceAliases aliases = DataSourceAliases.of(Map.of(
                "ds_0", "orders-even",
                "ds_1", "orders-odd"));
        ManifestPolicy policy = ManifestPolicy.strict(1, 1);
        ObservedExecutionManifest approved = ObservedExecutionManifest.from(equality, aliases, policy);
        ObservedExecutionManifest candidate = ObservedExecutionManifest.from(range, aliases, policy);
        ManifestCodec codec = new ManifestCodec();
        byte[] approvedBytes = codec.encode(approved);
        byte[] candidateBytes = codec.encode(candidate);
        assertArrayEquals(approvedBytes, codec.encode(codec.decode(approvedBytes)));
        assertArrayEquals(candidateBytes, codec.encode(codec.decode(candidateBytes)));

        ManifestVerificationResult verification = new ManifestVerifier().verify(approved, candidate);
        assertEquals(VerificationStatus.POLICY_VIOLATION, verification.status());
        assertEquals(
                List.of(
                        ManifestDiffCode.ATTEMPT_BUDGET_EXCEEDED,
                        ManifestDiffCode.DATA_SOURCE_BUDGET_EXCEEDED),
                verification.diffs().stream().map(diff -> diff.code()).toList());
        List<String> diffLines = verification.diffs().stream()
                .map(diff -> diff.code().stableCode() + " " + diff.severity() + " "
                        + diff.code() + ": " + diff.detail())
                .toList();
        byte[] diffBytes = (String.join("\n", diffLines) + "\n").getBytes(StandardCharsets.UTF_8);

        Path committedManifestRoot = Path.of(
                System.getProperty("routecontract.repositoryRoot"), "examples", "manifests");
        ObservedExecutionManifest approved553 = codec.decode(Files.readAllBytes(
                committedManifestRoot.resolve(
                        "find-paid-orders-by-user.shardingsphere-5.5.3.schema2.approved.json")));
        ManifestVerificationResult crossVersion = new ManifestVerifier().verify(approved553, approved);
        assertEquals(VerificationStatus.INCOMPATIBLE, crossVersion.status());
        assertEquals(
                List.of(ManifestDiffCode.RUNTIME_IDENTITY_MISMATCH),
                crossVersion.diffs().stream().map(diff -> diff.code()).toList());
        assertEquals("RCM005", ManifestDiffCode.RUNTIME_IDENTITY_MISMATCH.stableCode());

        Path generated = Path.of("build", "routecontract-552-evidence");
        Files.createDirectories(generated);
        Files.write(generated.resolve("find-paid-orders-by-user.shardingsphere-5.5.2.schema2.approved.json"),
                approvedBytes);
        Files.write(generated.resolve("find-paid-orders-by-user.shardingsphere-5.5.2.schema2.candidate.json"),
                candidateBytes);
        Files.write(generated.resolve("find-paid-orders-by-user.shardingsphere-5.5.2.expected-diff.txt"),
                diffBytes);

        String publicEvidence = new String(approvedBytes, StandardCharsets.UTF_8)
                + new String(candidateBytes, StandardCharsets.UTF_8)
                + new String(diffBytes, StandardCharsets.UTF_8);
        for (String sensitive : List.of("SELECT", "t_order", "PAID", "ds_0", "ds_1")) {
            assertFalse(publicEvidence.contains(sensitive),
                    () -> "5.5.2 evidence exposed raw execution data: " + sensitive);
        }

        Set<String> repeatedSignatures = new HashSet<>();
        for (int iteration = 0; iteration < 20; iteration++) {
            RouteSnapshot repeated = RouteContract.capture(
                    "552-repeat-" + iteration, () -> assertEquals(1, executeFanOut(3L)));
            assertSnapshot(repeated, 2, Set.of("ds_0", "ds_1"));
            assertEquals(1, repeated.trunkThreadFlagCount());
            assertEquals(1, repeated.workerThreadFlagCount());
            repeatedSignatures.add(canonicalSignature(repeated));
        }
        assertEquals(1, repeatedSignatures.size(),
                "twenty exact-5.5.2 captures must have one structural signature");

        if (!Boolean.getBoolean("routecontract.generate552Evidence")) {
            assertArrayEquals(Files.readAllBytes(committedManifestRoot.resolve(
                            "find-paid-orders-by-user.shardingsphere-5.5.2.schema2.approved.json")),
                    approvedBytes);
            assertArrayEquals(Files.readAllBytes(committedManifestRoot.resolve(
                            "find-paid-orders-by-user.shardingsphere-5.5.2.schema2.candidate.json")),
                    candidateBytes);
            assertArrayEquals(Files.readAllBytes(committedManifestRoot.resolve(
                            "find-paid-orders-by-user.shardingsphere-5.5.2.expected-diff.txt")),
                    diffBytes);
        } else {
            System.out.println("ROUTECONTRACT_552_EVIDENCE_CANDIDATE approvedBytes="
                    + approvedBytes.length + " approvedSha256=" + sha256(approvedBytes)
                    + " candidateBytes=" + candidateBytes.length
                    + " candidateSha256=" + sha256(candidateBytes)
                    + " diffBytes=" + diffBytes.length + " diffSha256=" + sha256(diffBytes));
        }
    }

    @Test
    @Order(3)
    void workerReceivesSubmissionContextButRawChildDoesNotInheritItOnExact552() throws Exception {
        RouteSnapshot snapshot = RouteContract.capture("552-worker-propagation", () -> {
            Thread rawChild = new Thread(() -> {
                RouteContract552SqlExecutionHook hook = new RouteContract552SqlExecutionHook();
                hook.start("raw-child-must-not-be-captured", "SELECT 1", List.of(), null, false);
                hook.finishSuccess();
            }, "552-raw-child-without-ttl-wrapper");
            rawChild.start();
            rawChild.join();

            assertEquals(1, executeEqual(3L));
            assertEquals(1, executeFanOut(3L));
        });

        assertSnapshot(snapshot, 3, Set.of("ds_0", "ds_1"));
        assertFalse(snapshot.observedDataSourceNames().contains("raw-child-must-not-be-captured"));
        assertEquals(2, snapshot.trunkThreadFlagCount());
        assertEquals(1, snapshot.workerThreadFlagCount());
    }

    @Test
    @Order(4)
    void concurrentSingleAndFanOutCapturesRemainIsolatedAcrossTwentyPairs() throws Exception {
        RouteSnapshot singleReference = RouteContract.capture(
                "552-single-reference", () -> assertEquals(1, executeEqual(3L)));
        RouteSnapshot fanOutReference = RouteContract.capture(
                "552-fanout-reference", () -> assertEquals(1, executeFanOut(2L)));
        String singleSignature = canonicalSignature(singleReference);
        String fanOutSignature = canonicalSignature(fanOutReference);
        assertFalse(singleSignature.equals(fanOutSignature));

        ExecutorService callers = Executors.newFixedThreadPool(2);
        try {
            for (int iteration = 0; iteration < 20; iteration++) {
                CyclicBarrier bothCapturesOpen = new CyclicBarrier(2);
                Future<RouteSnapshot> single = callers.submit(capturedEqual(
                        "552-single-" + iteration, 3L, bothCapturesOpen));
                Future<RouteSnapshot> fanOut = callers.submit(capturedFanOut(
                        "552-fanout-" + iteration, 2L, bothCapturesOpen));

                RouteSnapshot singleSnapshot = single.get();
                RouteSnapshot fanOutSnapshot = fanOut.get();
                assertSnapshot(singleSnapshot, 1, Set.of("ds_1"));
                assertSnapshot(fanOutSnapshot, 2, Set.of("ds_0", "ds_1"));
                assertEquals(0, singleSnapshot.workerThreadFlagCount());
                assertEquals(1, fanOutSnapshot.workerThreadFlagCount());
                assertEquals(singleSignature, canonicalSignature(singleSnapshot));
                assertEquals(fanOutSignature, canonicalSignature(fanOutSnapshot));
            }
        } finally {
            callers.shutdownNow();
        }
    }

    @Test
    @Order(5)
    void caughtPhysicalCallbackFailureRemainsDiagnosticOnlyOnExact552() throws Exception {
        String operationId = "552-failure-boundary";
        RouteSnapshot successfulShape = RouteContract.capture(
                operationId,
                () -> assertEquals(2, executeFailureFanOut()));
        assertSnapshot(successfulShape, 2, Set.of("ds_0", "ds_1"));

        // This in-memory manifest is a test comparator only. It is never persisted, published,
        // or represented as an externally human-approved operation baseline.
        ObservedExecutionManifest testComparator = ObservedExecutionManifest.from(
                successfulShape,
                failureAliases(),
                ManifestPolicy.strict(2, 2));

        try (Connection connection = physicalConnection(DS_1);
             Statement statement = connection.createStatement()) {
            statement.execute("DROP TABLE t_failure_1");
        }

        AtomicReference<SQLException> caughtByApplication = new AtomicReference<>();
        RouteSnapshot failed = RouteContract.capture(operationId, () -> {
            try {
                executeFailureFanOut();
            } catch (SQLException failure) {
                caughtByApplication.set(failure);
            }
        });

        assertNotNull(caughtByApplication.get(), "the application must catch a physical JDBC failure");
        assertEquals(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_2, failed.runtimeIdentity());
        assertNotEquals(CaptureStatus.COMPLETE, failed.status(), () -> "failed snapshot=" + failed);
        assertTrue(failed.callbackFailureCount() >= 1, () -> "failed snapshot=" + failed);
        assertThrows(
                RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(failed)
                        .hasAtMostObservedPhysicalAttempts(Integer.MAX_VALUE));

        ManifestVerificationResult direct = new ManifestVerifier().verify(
                testComparator,
                failed,
                failureAliases());
        ManifestDiffCode expectedCode = failed.status() == CaptureStatus.INCOMPLETE
                ? ManifestDiffCode.CAPTURE_INCOMPLETE
                : ManifestDiffCode.CALLBACK_FAILURE_NOT_ELIGIBLE;
        assertEquals(VerificationStatus.NOT_ELIGIBLE, direct.status());
        assertEquals(List.of(expectedCode), direct.diffs().stream().map(diff -> diff.code()).toList());

        ObservedExecutionManifest diagnostic = ObservedExecutionManifest.from(
                failed,
                failureAliases(),
                testComparator.policy());
        ManifestVerificationResult diagnosticVerification = new ManifestVerifier().verify(
                testComparator,
                diagnostic);
        assertEquals(VerificationStatus.NOT_ELIGIBLE, diagnosticVerification.status());
        assertEquals(
                List.of(expectedCode),
                diagnosticVerification.diffs().stream().map(diff -> diff.code()).toList());

        String minimizedEvidence = failed + "\n" + direct + "\n" + diagnosticVerification;
        for (String sensitive : List.of("SELECT", "t_failure", "ACTIVE")) {
            assertFalse(minimizedEvidence.contains(sensitive),
                    () -> "failure evidence exposed raw execution data: " + sensitive);
        }
    }

    @Test
    @Order(6)
    void interruptedCallerCannotCloseAsContractEligibleOnExact552() throws Exception {
        RouteSnapshot interrupted;
        try {
            interrupted = RouteContract.capture("552-interrupted-close", () -> {
                assertEquals(1, executeEqual(3L));
                Thread.currentThread().interrupt();
            });
            assertTrue(Thread.currentThread().isInterrupted());
        } finally {
            Thread.interrupted();
        }

        assertEquals(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_2, interrupted.runtimeIdentity());
        assertEquals(CaptureStatus.INCOMPLETE, interrupted.status());
        assertEquals(1, interrupted.observedPhysicalAttemptCount());
        assertEquals(1, interrupted.callbackReturnedCount());
        assertEquals(0, interrupted.callbackFailureCount());
        assertEquals(List.of("RC_CALLER_INTERRUPTED_AT_CLOSE"), interrupted.collectorDiagnostics());
        assertThrows(
                RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(interrupted)
                        .hasExactlyObservedPhysicalAttempts(1));
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

    private static int executeFailureFanOut() throws SQLException {
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

    private static DataSourceAliases failureAliases() {
        return DataSourceAliases.of(Map.of(
                "ds_0", "failures-even",
                "ds_1", "failures-odd"));
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
        assertEquals(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_2, snapshot.runtimeIdentity());
        assertEquals(CaptureStatus.COMPLETE, snapshot.status(), () -> "snapshot=" + snapshot);
        assertEquals(expectedAttempts, snapshot.observedPhysicalAttemptCount(), () -> "snapshot=" + snapshot);
        assertEquals(expectedDataSourceNames, Set.copyOf(snapshot.observedDataSourceNames()));
        assertTrue(snapshot.attempts().stream()
                .allMatch(attempt -> attempt.outcome() == AttemptOutcome.CALLBACK_RETURNED));
    }

    private static String canonicalSignature(final RouteSnapshot snapshot) {
        return snapshot.attempts().stream()
                .map(Exact552OperationContractMySqlTest::canonicalAttempt)
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

    private static String sha256(final byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
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
            statement.execute("CREATE TABLE t_order_0 (order_id BIGINT PRIMARY KEY, "
                    + "user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
            statement.execute("CREATE TABLE t_order_1 (order_id BIGINT PRIMARY KEY, "
                    + "user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
            statement.execute("CREATE TABLE t_failure_0 (order_id BIGINT PRIMARY KEY, "
                    + "user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
            statement.execute("CREATE TABLE t_failure_1 (order_id BIGINT PRIMARY KEY, "
                    + "user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
        }
    }

    @FunctionalInterface
    private interface StatementBinder {
        void bind(PreparedStatement statement) throws Exception;
    }
}
