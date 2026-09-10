package io.github.ym0506.routecontract.consumer;

import io.github.ym0506.routecontract.AttemptOutcome;
import io.github.ym0506.routecontract.CaptureStatus;
import io.github.ym0506.routecontract.api.RouteContract;
import io.github.ym0506.routecontract.RouteContractViolationException;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import io.github.ym0506.routecontract.manifest.DataSourceAliases;
import io.github.ym0506.routecontract.manifest.ManifestAssertions;
import io.github.ym0506.routecontract.manifest.ManifestCodec;
import io.github.ym0506.routecontract.manifest.ManifestDiffCode;
import io.github.ym0506.routecontract.manifest.ManifestReviewCli;
import io.github.ym0506.routecontract.manifest.ManifestReviewReport;
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
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
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
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Exercises an independently resolved core/adapter pair, never source-project classes. */
@Testcontainers
class StagedArtifactMySqlTest {
    private static final String SERVICE_DESCRIPTOR =
            "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";
    private static final String OPERATION = "find-paid-orders-by-user";
    private static final List<OrderRow> EXPECTED_ROWS = List.of(new OrderRow(201L, 3L, "PAID"));
    private static final String EXPECTED_RUNTIME = requiredProperty("routecontract.expectedRuntime");
    private static final String VERSION = requiredProperty("routecontract.version");
    private static final String ADAPTER = switch (EXPECTED_RUNTIME) {
        case "5.5.2" -> "routecontract-shardingsphere-5.5.2";
        case "5.5.3" -> "routecontract-shardingsphere-5.5";
        default -> throw new IllegalArgumentException("Unsupported consumer runtime selection");
    };
    private static final String PROVIDER_CLASS = EXPECTED_RUNTIME.equals("5.5.2")
            ? "io.github.ym0506.routecontract.shardingsphere552.internal.RouteContract552SqlExecutionHook"
            : "io.github.ym0506.routecontract.shardingsphere553.internal.RouteContract553SqlExecutionHook";
    private static final ShardingSphereRuntimeIdentity RUNTIME_IDENTITY = EXPECTED_RUNTIME.equals("5.5.2")
            ? ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_2
            : ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3;
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
        // Fail before configuring ShardingSphere if the supposedly staged artifacts are source classes.
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
    void loadedCoreAndAutoDiscoveredHookAreTheExpectedStagedJarBytes() throws Exception {
        assertArtifactOriginsAndProviderDiscovery();
    }

    @Test
    void unchangedRealMySqlCaptureMatchesTheExistingReviewedSchemaTwoBaseline() throws Exception {
        byte[] reviewedBytes = reviewedBaselineBytes();
        ManifestCodec codec = new ManifestCodec();
        ObservedExecutionManifest approved = codec.decode(reviewedBytes);
        RouteSnapshot equality = RouteContract.capture(OPERATION, () -> assertEquals(EXPECTED_ROWS, executeEqual("PAID")));
        assertSnapshot(equality, 1, Set.of("ds_1"));
        ObservedExecutionManifest observed = ObservedExecutionManifest.from(equality, ALIASES, approved.policy());
        assertEquals(2, observed.schemaVersion());
        assertArrayEquals(reviewedBytes, codec.encode(observed),
                "new observations must match the copied reviewed baseline without rewriting it");
        var verification = new ManifestVerifier().verify(approved, observed);
        assertEquals(VerificationStatus.MATCH, verification.status());
        ManifestAssertions.assertMatched(verification);
        assertEquals(0, ManifestReviewReport.compare(approved, observed).strictExitCode());

        // Values remain local even when a real query binds a distinctive value absent from the rows.
        String privateBindValue = "staged-consumer-private-bind-39fa5e72";
        RouteSnapshot empty = RouteContract.capture(OPERATION, () -> assertEquals(List.of(), executeEqual(privateBindValue)));
        assertSnapshot(empty, 1, Set.of("ds_1"));
        byte[] valueMinimizedBytes = codec.encode(
                ObservedExecutionManifest.from(empty, ALIASES, approved.policy()));
        assertArrayEquals(reviewedBytes, valueMinimizedBytes,
                "parameter values and business result must not be encoded as execution evidence");
        assertFalse(empty.toString().contains(privateBindValue));
        assertFalse(new String(valueMinimizedBytes, StandardCharsets.UTF_8).contains(privateBindValue));
        assertArrayEquals(reviewedBytes, reviewedBaselineBytes());
    }

    @Test
    void sameBusinessRowWithExpandedExecutionFailsAssertionsAndBothCliReportFormats() throws Exception {
        byte[] reviewedBytes = reviewedBaselineBytes();
        ManifestCodec codec = new ManifestCodec();
        ObservedExecutionManifest approved = codec.decode(reviewedBytes);
        RouteSnapshot equality = RouteContract.capture(OPERATION, () -> assertEquals(EXPECTED_ROWS, executeEqual("PAID")));
        RouteSnapshot range = RouteContract.capture(OPERATION, () -> assertEquals(EXPECTED_ROWS, executeRange()));
        assertSnapshot(equality, 1, Set.of("ds_1"));
        assertSnapshot(range, 2, Set.of("ds_0", "ds_1"));
        assertArrayEquals(reviewedBytes, codec.encode(
                ObservedExecutionManifest.from(equality, ALIASES, approved.policy())));
        ObservedExecutionManifest candidate = ObservedExecutionManifest.from(range, ALIASES, approved.policy());
        assertEquals(2, candidate.schemaVersion());
        var verification = new ManifestVerifier().verify(approved, candidate);
        assertEquals(VerificationStatus.POLICY_VIOLATION, verification.status());
        assertEquals(List.of(ManifestDiffCode.ATTEMPT_BUDGET_EXCEEDED,
                        ManifestDiffCode.DATA_SOURCE_BUDGET_EXCEEDED),
                verification.diffs().stream().map(diff -> diff.code()).toList());
        var violation = assertThrows(RouteContractViolationException.class,
                () -> ManifestAssertions.assertMatched(verification));
        assertTrue(violation.getMessage().contains("RCM201"));
        assertTrue(violation.getMessage().contains("RCM202"));

        Path evidence = Path.of("build", "routecontract-consumer-evidence", EXPECTED_RUNTIME);
        Files.createDirectories(evidence);
        // This is an unchanged copy of a reviewed resource, never an approval of today's capture.
        Path baselinePath = evidence.resolve("reviewed-baseline.json");
        Path candidatePath = evidence.resolve("candidate.json");
        Files.write(baselinePath, reviewedBytes, StandardOpenOption.CREATE_NEW);
        Files.write(candidatePath, codec.encode(candidate), StandardOpenOption.CREATE_NEW);
        ManifestReviewReport report = ManifestReviewReport.compare(approved, candidate);
        assertEquals(verification, report.verification());
        for (String format : List.of("markdown", "json")) {
            Path output = evidence.resolve(format.equals("json") ? "review.json" : "review.md");
            ByteArrayOutputStream errors = new ByteArrayOutputStream();
            try (PrintStream diagnostics = new PrintStream(errors, true, StandardCharsets.UTF_8)) {
                assertEquals(1, ManifestReviewCli.run(new String[]{
                        "--baseline", baselinePath.toString(), "--candidate", candidatePath.toString(),
                        "--format", format, "--output", output.toString()}, diagnostics));
            }
            assertEquals("", errors.toString(StandardCharsets.UTF_8));
            String rendered = Files.readString(output, StandardCharsets.UTF_8);
            assertEquals(format.equals("json") ? report.toJson() : report.toMarkdown(), rendered);
            assertTrue(rendered.contains("POLICY_VIOLATION"));
            assertTrue(rendered.contains("RCM201"));
            assertTrue(rendered.contains("RCM202"));
        }
        assertTrue(report.toMarkdown().contains("| Physical JDBC execution attempts | 1 | 2 | 1 |"));
        assertTrue(report.toJson().contains("\"strictExitCode\":1"));
        String publicEvidence = new String(reviewedBytes, StandardCharsets.UTF_8)
                + new String(codec.encode(candidate), StandardCharsets.UTF_8)
                + report.toMarkdown() + report.toJson() + violation.getMessage();
        for (String sensitive : List.of("SELECT", "t_order", "PAID", "user_id", "ds_0", "ds_1")) {
            assertFalse(publicEvidence.contains(sensitive),
                    "report or minimized manifest disclosed a raw SQL element, bound value, or data-source name");
        }
        assertArrayEquals(reviewedBytes, Files.readAllBytes(baselinePath));
        assertArrayEquals(reviewedBytes, reviewedBaselineBytes());
        System.out.println("ROUTECONTRACT_STAGED_SPLIT_MYSQL_VERIFIED version=" + EXPECTED_RUNTIME
                + " baseline=MATCH regression=POLICY_VIOLATION attempts=1-to-2");
    }

    private static void assertArtifactOriginsAndProviderDiscovery() throws Exception {
        assertJarOrigin(RouteContract.class, "routecontract-core-" + VERSION + ".jar",
                requiredProperty("routecontract.coreSha256"));
        ClassLoader loader = Thread.currentThread().getContextClassLoader();
        Class<?> provider = Class.forName(PROVIDER_CLASS, false, loader);
        Path adapterJar = assertJarOrigin(provider, ADAPTER + "-" + VERSION + ".jar",
                requiredProperty("routecontract.adapterSha256"));
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
        String resource = "/manifests/find-paid-orders-by-user.shardingsphere-"
                + EXPECTED_RUNTIME + ".schema2.approved.json";
        try (var input = StagedArtifactMySqlTest.class.getResourceAsStream(resource)) {
            assertNotNull(input, "reviewed per-version baseline resource must be present");
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
        assertEquals(RUNTIME_IDENTITY, snapshot.runtimeIdentity());
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
