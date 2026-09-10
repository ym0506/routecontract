package io.github.ym0506.routecontract.consumer;

import io.github.ym0506.routecontract.AttemptOutcome;
import io.github.ym0506.routecontract.CaptureStatus;
import io.github.ym0506.routecontract.CapturedResult;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteContractViolationException;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.manifest.DataSourceAliases;
import io.github.ym0506.routecontract.manifest.ManifestAssertions;
import io.github.ym0506.routecontract.manifest.ManifestCodec;
import io.github.ym0506.routecontract.manifest.ManifestDiffCode;
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
import java.net.JarURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.Set;
import java.util.jar.JarFile;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Compiled once against public v0.1.2; the identical class bytes run on both resolved graphs.
 * Observes exact ShardingSphere-JDBC 5.5.3 synchronous non-batch physical JDBC execution attempts.
 * Business rows are asserted separately; hook completion does not prove business success or commit.
 */
@Testcontainers
class OldBytecodeMySqlTest {
    private static final String SERVICE_DESCRIPTOR =
            "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";
    private static final String OPERATION = "find-paid-orders-by-user";
    private static final List<OrderRow> EXPECTED_ROWS = List.of(new OrderRow(201L, 3L, "PAID"));
    private static final String EXPECTED_RUNTIME = "5.5.3";
    private static final String VERSION = requiredProperty("routecontract.version");
    private static final boolean LEGACY = switch (VERSION) {
        case "0.1.2" -> true;
        case "0.2.0" -> false;
        default -> throw new IllegalArgumentException("Unsupported migration consumer version: " + VERSION);
    };
    private static final String LEGACY_PROVIDER =
            "io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook";
    private static final String CURRENT_PROVIDER =
            "io.github.ym0506.routecontract.shardingsphere553.internal.RouteContract553SqlExecutionHook";
    private static final String PROVIDER_CLASS = LEGACY ? LEGACY_PROVIDER : CURRENT_PROVIDER;
    private static final DataSourceAliases ALIASES = DataSourceAliases.of(Map.of(
            "ds_0", "orders-even", "ds_1", "orders-odd"));
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
        // Fail before configuring ShardingSphere if selected dependency classes are not the expected JAR bytes.
        assertArtifactOriginsAndProviderDiscovery();
        initialize(DS_0);
        initialize(DS_1);
        try (Connection connection = physicalConnection(DS_0);
             Statement statement = connection.createStatement()) {
            statement.executeUpdate(
                    "INSERT INTO t_order_0(order_id, user_id, status) VALUES (202, 2, 'PAID')");
        }
        try (Connection connection = physicalConnection(DS_1);
             Statement statement = connection.createStatement()) {
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
    void selectedRuntimeApiOriginsAndAutoDiscoveredHookAreTheExpectedJarBytes() throws Exception {
        assertArtifactOriginsAndProviderDiscovery();
    }

    @Test
    void unchangedOldCaptureAndCaptureResultBytecodeMatchTheReviewedSchemaOneBaseline() throws Exception {
        byte[] reviewedBytes = reviewedBaselineBytes();
        ManifestCodec codec = new ManifestCodec();
        ObservedExecutionManifest approved = codec.decode(reviewedBytes);
        assertEquals(1, approved.schemaVersion());
        RouteSnapshot captured = RouteContract.capture(OPERATION,
                () -> assertEquals(EXPECTED_ROWS, executeEqual("PAID")));
        CapturedResult<List<OrderRow>> returned = RouteContract.captureResult(OPERATION,
                () -> executeEqual("PAID"));
        assertEquals(EXPECTED_ROWS, returned.value(), "captureResult must return the exact business row");
        for (RouteSnapshot snapshot : List.of(captured, returned.snapshot())) {
            assertSnapshot(snapshot, 1, Set.of("ds_1"));
            ObservedExecutionManifest observed = ObservedExecutionManifest.from(snapshot, ALIASES, approved.policy());
            assertEquals(LEGACY ? 1 : 2, observed.schemaVersion());
            var verification = new ManifestVerifier().verify(approved, observed);
            assertEquals(VerificationStatus.MATCH, verification.status());
            ManifestAssertions.assertMatched(verification);
            ManifestAssertions.assertMatched(new ManifestVerifier().verify(approved, snapshot, ALIASES));
            // Schema 2 adds identity metadata; old bytecode must still verify the unchanged schema-1 baseline.
            if (LEGACY) {
                assertArrayEquals(reviewedBytes, codec.encode(observed));
            }
        }
        Path evidence = evidenceDirectory();
        byte[] captureBytes = codec.encode(ObservedExecutionManifest.from(captured, ALIASES, approved.policy()));
        byte[] resultBytes = codec.encode(ObservedExecutionManifest.from(returned.snapshot(), ALIASES, approved.policy()));
        assertArrayEquals(captureBytes, resultBytes,
                "the two public entry points must yield the same minimized execution evidence");
        Files.write(evidence.resolve("equality-capture.json"), captureBytes, StandardOpenOption.CREATE_NEW);
        Files.write(evidence.resolve("equality-capture-result.json"), resultBytes, StandardOpenOption.CREATE_NEW);
        assertMinimized(new String(captureBytes, StandardCharsets.UTF_8));
        assertArrayEquals(reviewedBytes, reviewedBaselineBytes());
    }

    @Test
    void oldBytecodeStillRejectsTwoAttemptsWhenTheBusinessRowIsUnchanged() throws Exception {
        byte[] reviewedBytes = reviewedBaselineBytes();
        ManifestCodec codec = new ManifestCodec();
        ObservedExecutionManifest approved = codec.decode(reviewedBytes);
        CapturedResult<List<OrderRow>> equality = RouteContract.captureResult(OPERATION,
                () -> executeEqual("PAID"));
        CapturedResult<List<OrderRow>> range = RouteContract.captureResult(OPERATION,
                OldBytecodeMySqlTest::executeRange);
        assertEquals(EXPECTED_ROWS, equality.value());
        assertEquals(EXPECTED_ROWS, range.value());
        assertEquals(equality.value(), range.value(), "business equality must be independently established");
        assertSnapshot(equality.snapshot(), 1, Set.of("ds_1"));
        assertSnapshot(range.snapshot(), 2, Set.of("ds_0", "ds_1"));
        ManifestAssertions.assertMatched(new ManifestVerifier().verify(approved, equality.snapshot(), ALIASES));
        ObservedExecutionManifest candidate = ObservedExecutionManifest.from(range.snapshot(), ALIASES, approved.policy());
        assertEquals(LEGACY ? 1 : 2, candidate.schemaVersion());
        var verification = new ManifestVerifier().verify(approved, candidate);
        assertEquals(VerificationStatus.POLICY_VIOLATION, verification.status());
        assertEquals(List.of(ManifestDiffCode.ATTEMPT_BUDGET_EXCEEDED,
                        ManifestDiffCode.DATA_SOURCE_BUDGET_EXCEEDED),
                verification.diffs().stream().map(diff -> diff.code()).toList());
        assertEquals(verification, new ManifestVerifier().verify(approved, range.snapshot(), ALIASES));
        var violation = assertThrows(RouteContractViolationException.class,
                () -> ManifestAssertions.assertMatched(verification));
        assertTrue(violation.getMessage().contains("RCM201"));
        assertTrue(violation.getMessage().contains("RCM202"));

        Path evidence = evidenceDirectory();
        // This is an unchanged copy of a reviewed resource, never approval of today's capture.
        Path baselinePath = evidence.resolve("approved.json");
        Files.write(baselinePath, reviewedBytes, StandardOpenOption.CREATE_NEW);
        byte[] candidateBytes = codec.encode(candidate);
        Files.write(evidence.resolve("candidate.json"), candidateBytes, StandardOpenOption.CREATE_NEW);
        String summary = """
                {
                  "routeContractVersion": "%s",
                  "shardingSphereJdbcVersion": "5.5.3",
                  "boundary": "synchronous non-batch PreparedStatement",
                  "business": {"exactExpectedRowMatched": true, "equalityRowCount": 1, "rangeRowCount": 1, "sameRows": true},
                  "equality": {"physicalJdbcExecutionAttempts": 1, "verification": "MATCH"},
                  "range": {"physicalJdbcExecutionAttempts": 2, "verification": "POLICY_VIOLATION", "codes": ["RCM201", "RCM202"]},
                  "approvedSchemaVersion": 1,
                  "observedSchemaVersion": %d
                }
                """.formatted(VERSION, candidate.schemaVersion());
        Files.writeString(evidence.resolve("business-summary.json"), summary,
                StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        // Separate synthetic business assertion evidence, derived from the actual captured rows.
        // The exact fixture rows were asserted above; raw SQL and connection details are omitted.
        // These business values are deliberately excluded from the minimized route-evidence check.
        OrderRow equalityRow = equality.value().get(0);
        OrderRow rangeRow = range.value().get(0);
        String businessRows = """
                {
                  "syntheticFixtureData": true,
                  "equality": [{"orderId": %d, "userId": %d, "status": "%s"}],
                  "range": [{"orderId": %d, "userId": %d, "status": "%s"}]
                }
                """.formatted(equalityRow.orderId(), equalityRow.userId(), equalityRow.status(),
                        rangeRow.orderId(), rangeRow.userId(), rangeRow.status());
        Files.writeString(evidence.resolve("business-rows.json"), businessRows,
                StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        assertMinimized(new String(reviewedBytes, StandardCharsets.UTF_8)
                + new String(candidateBytes, StandardCharsets.UTF_8) + summary + violation.getMessage());
        assertArrayEquals(reviewedBytes, Files.readAllBytes(baselinePath));
        assertArrayEquals(reviewedBytes, reviewedBaselineBytes());
        System.out.println("ROUTECONTRACT_OLD_BYTECODE_MYSQL_VERIFIED routecontract=" + VERSION
                + " shardingsphere=" + EXPECTED_RUNTIME
                + " baseline=MATCH regression=POLICY_VIOLATION attempts=1-to-2");
    }

    private static void assertArtifactOriginsAndProviderDiscovery() throws Exception {
        String apiJarName = LEGACY ? "routecontract-shardingsphere-5.5-0.1.2.jar"
                : "routecontract-core-0.2.0.jar";
        String apiSha256 = requiredProperty(LEGACY ? "routecontract.legacySha256" : "routecontract.coreSha256");
        for (Class<?> api : List.of(RouteContract.class, CapturedResult.class, RouteSnapshot.class,
                ObservedExecutionManifest.class, ManifestVerifier.class, ManifestCodec.class)) {
            assertJarOrigin(api, apiJarName, apiSha256);
        }
        ClassLoader loader = Thread.currentThread().getContextClassLoader();
        Class<?> provider = Class.forName(PROVIDER_CLASS, false, loader);
        Path adapterJar = assertJarOrigin(provider, "routecontract-shardingsphere-5.5-" + VERSION + ".jar",
                requiredProperty(LEGACY ? "routecontract.legacySha256" : "routecontract.adapterSha256"));
        assertThrows(ClassNotFoundException.class,
                () -> Class.forName(LEGACY ? CURRENT_PROVIDER : LEGACY_PROVIDER, false, loader),
                "the other version's hook implementation must not leak onto the resolved runtime");
        List<String> ownProviders = new ArrayList<>();
        Enumeration<URL> descriptors = loader.getResources(SERVICE_DESCRIPTOR);
        while (descriptors.hasMoreElements()) {
            URL descriptor = descriptors.nextElement();
            String content;
            try (var input = descriptor.openStream()) {
                content = new String(input.readAllBytes(), StandardCharsets.UTF_8);
            }
            List<String> declarations = content.lines()
                    .map(line -> line.split("#", 2)[0].trim())
                    .filter(line -> line.startsWith("io.github.ym0506.routecontract."))
                    .toList();
            if (!declarations.isEmpty()) {
                assertEquals("jar", descriptor.getProtocol(), "provider declaration must be from a JAR");
                JarURLConnection connection = (JarURLConnection) descriptor.openConnection();
                assertEquals(adapterJar, Path.of(connection.getJarFileURL().toURI()).toRealPath());
                ownProviders.addAll(declarations);
            }
        }
        assertEquals(List.of(PROVIDER_CLASS), ownProviders,
                "exactly one RouteContract hook provider must be visible from the selected adapter JAR");
        assertExactShardingSphereRuntime();
    }

    private static void assertExactShardingSphereRuntime() throws Exception {
        URL origin = YamlShardingSphereDataSourceFactory.class.getProtectionDomain().getCodeSource().getLocation();
        assertEquals("file", origin.getProtocol());
        Path jar = Path.of(origin.toURI());
        assertTrue(Files.isRegularFile(jar, LinkOption.NOFOLLOW_LINKS));
        assertEquals("shardingsphere-jdbc-5.5.3.jar", jar.getFileName().toString());
        try (JarFile archive = new JarFile(jar.toFile())) {
            var entry = archive.getJarEntry("META-INF/maven/org.apache.shardingsphere/shardingsphere-jdbc/pom.properties");
            assertNotNull(entry, "selected ShardingSphere JDBC JAR must retain Maven version metadata");
            Properties properties = new Properties();
            try (var input = archive.getInputStream(entry)) {
                properties.load(input);
            }
            assertEquals("org.apache.shardingsphere", properties.getProperty("groupId"));
            assertEquals("shardingsphere-jdbc", properties.getProperty("artifactId"));
            assertEquals(EXPECTED_RUNTIME, properties.getProperty("version"));
        }
    }

    private static Path evidenceDirectory() throws Exception {
        Path evidence = Path.of("build", "migration-mysql-evidence", VERSION);
        Files.createDirectories(evidence);
        return evidence;
    }

    private static void assertMinimized(String evidence) {
        for (String sensitive : List.of("SELECT", "t_order", "PAID", "user_id", "ds_0", "ds_1", "jdbc:mysql")) {
            assertFalse(evidence.contains(sensitive),
                    "minimized evidence disclosed a raw SQL element, bound value, data-source name, or JDBC URL");
        }
    }

    private static Path assertJarOrigin(Class<?> type, String expectedName, String expectedSha256)
            throws Exception {
        assertTrue(expectedSha256.matches("[0-9a-f]{64}"), "expected artifact checksum must be exact SHA-256");
        assertNotNull(type.getProtectionDomain().getCodeSource());
        URL origin = type.getProtectionDomain().getCodeSource().getLocation();
        assertEquals("file", origin.getProtocol(), "classes must originate in a resolved local JAR file");
        Path jar = Path.of(origin.toURI());
        assertTrue(Files.isRegularFile(jar, LinkOption.NOFOLLOW_LINKS), "source class directories are not JARs");
        assertEquals(expectedName, jar.getFileName().toString());
        assertEquals(expectedSha256, HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(jar))));
        return jar.toRealPath();
    }

    private static byte[] reviewedBaselineBytes() throws Exception {
        String resource = "/manifests/find-paid-orders-by-user.approved.json";
        try (var input = OldBytecodeMySqlTest.class.getResourceAsStream(resource)) {
            assertNotNull(input, "unchanged reviewed schema-1 baseline resource must be present");
            return input.readAllBytes();
        }
    }

    private static String requiredProperty(String name) {
        String value = System.getProperty(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing required consumer property: " + name);
        }
        return value;
    }

    private static void assertSnapshot(RouteSnapshot snapshot, int attempts, Set<String> dataSources) {
        assertEquals(LEGACY ? 1 : 2, snapshot.schemaVersion());
        assertEquals(OPERATION, snapshot.operationId());
        assertEquals(CaptureStatus.COMPLETE, snapshot.status());
        assertEquals(attempts, snapshot.observedPhysicalAttemptCount());
        assertEquals(dataSources, Set.copyOf(snapshot.observedDataSourceNames()));
        assertTrue(snapshot.attempts().stream().allMatch(attempt -> attempt.outcome() == AttemptOutcome.CALLBACK_RETURNED));
        assertEquals(0, snapshot.callbackFailureCount());
        assertEquals(0, snapshot.unknownOutcomeCount());
    }

    private static List<OrderRow> executeEqual(String status) throws Exception {
        return execute("SELECT order_id, user_id, status FROM t_order WHERE user_id = ? AND status = ?", statement -> {
            statement.setLong(1, 3L);
            statement.setString(2, status);
        });
    }

    private static List<OrderRow> executeRange() throws Exception {
        return execute("SELECT order_id, user_id, status FROM t_order WHERE user_id BETWEEN ? AND ? AND status = ?", statement -> {
            statement.setLong(1, 3L);
            statement.setLong(2, 3L);
            statement.setString(3, "PAID");
        });
    }

    private static List<OrderRow> execute(String sql, StatementBinder binder) throws Exception {
        try (Connection connection = shardingDataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            binder.bind(statement);
            List<OrderRow> rows = new ArrayList<>();
            try (ResultSet results = statement.executeQuery()) {
                while (results.next()) {
                    rows.add(new OrderRow(results.getLong("order_id"),
                            results.getLong("user_id"), results.getString("status")));
                }
            }
            return List.copyOf(rows);
        }
    }

    private record OrderRow(long orderId, long userId, String status) {
    }

    private static MySQLContainer<?> mysql() {
        return new MySQLContainer<>(MYSQL_IMAGE)
                .withDatabaseName("routecontract")
                .withUsername("routecontract")
                .withPassword("routecontract");
    }

    private static Connection physicalConnection(MySQLContainer<?> container) throws Exception {
        return DriverManager.getConnection(container.getJdbcUrl(), container.getUsername(), container.getPassword());
    }

    private static void initialize(MySQLContainer<?> container) throws Exception {
        try (Connection connection = physicalConnection(container);
             Statement statement = connection.createStatement()) {
            statement.execute("CREATE TABLE t_order_0 (order_id BIGINT PRIMARY KEY, "
                    + "user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
            statement.execute("CREATE TABLE t_order_1 (order_id BIGINT PRIMARY KEY, "
                    + "user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
        }
    }

    @FunctionalInterface
    private interface StatementBinder {
        void bind(PreparedStatement statement) throws Exception;
    }
}
