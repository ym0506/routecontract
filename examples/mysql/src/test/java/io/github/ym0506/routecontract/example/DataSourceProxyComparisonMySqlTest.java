package io.github.ym0506.routecontract.example;

import com.alibaba.ttl.TransmittableThreadLocal;
import io.github.ym0506.routecontract.AttemptOutcome;
import io.github.ym0506.routecontract.CaptureStatus;
import io.github.ym0506.routecontract.CapturedResult;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.manifest.DataSourceAliases;
import io.github.ym0506.routecontract.manifest.ManifestAssertions;
import io.github.ym0506.routecontract.manifest.ManifestDiffCode;
import io.github.ym0506.routecontract.manifest.ManifestPolicy;
import io.github.ym0506.routecontract.manifest.ManifestVerificationResult;
import io.github.ym0506.routecontract.manifest.ManifestVerifier;
import io.github.ym0506.routecontract.manifest.ObservedExecutionManifest;
import io.github.ym0506.routecontract.manifest.VerificationStatus;
import net.ttddyy.dsproxy.ExecutionInfo;
import net.ttddyy.dsproxy.QueryInfo;
import net.ttddyy.dsproxy.listener.QueryExecutionListener;
import net.ttddyy.dsproxy.proxy.ParameterSetOperation;
import net.ttddyy.dsproxy.support.ProxyDataSourceBuilder;
import org.apache.shardingsphere.driver.api.yaml.YamlShardingSphereDataSourceFactory;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import javax.sql.DataSource;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Empirical comparison against datasource-proxy on the same ShardingSphere-JDBC/MySQL operation.
 *
 * <p>The test deliberately gives datasource-proxy its strongest fair placement: every physical
 * data source is wrapped before it is supplied to ShardingSphere. The nested DIY contract is
 * evidence that a comparable workflow is buildable, not production code or a claim that
 * datasource-proxy is incapable.</p>
 */
@Testcontainers
public class DataSourceProxyComparisonMySqlTest {

    private static final DockerImageName MYSQL_IMAGE = DockerImageName.parse(
            "mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb")
            .asCompatibleSubstituteFor("mysql");

    @Container
    private static final MySQLContainer<?> DS_0 = mysql();

    @Container
    private static final MySQLContainer<?> DS_1 = mysql();

    private static final DiyOperationCollector INNER_PROXY_COLLECTOR = new DiyOperationCollector();
    private static final FlatQueryRecorder OUTER_PROXY_RECORDER = new FlatQueryRecorder();

    private static DataSource shardingDataSource;
    private static DataSource logicalOuterProxy;

    @BeforeAll
    static void createPhysicalSchemaAndObservedDataSources() throws Exception {
        initialize(DS_0);
        initialize(DS_1);
        try (Connection connection = physicalConnection(DS_1);
             Statement statement = connection.createStatement()) {
            statement.executeUpdate(
                    "INSERT INTO t_order_1(order_id, user_id, status) VALUES (201, 3, 'PAID')");
        }

        Map<String, DataSource> physicalDataSources = Map.of(
                "ds_0", innerProxy("ds_0", DS_0),
                "ds_1", innerProxy("ds_1", DS_1));
        shardingDataSource = YamlShardingSphereDataSourceFactory.createDataSource(
                physicalDataSources,
                shardingRules().getBytes(StandardCharsets.UTF_8));
        logicalOuterProxy = ProxyDataSourceBuilder.create(shardingDataSource)
                .name("logical-shardingsphere")
                .listener(OUTER_PROXY_RECORDER)
                .build();
    }

    @AfterAll
    static void closeDataSource() throws Exception {
        if (shardingDataSource instanceof AutoCloseable closeable) {
            closeable.close();
        }
    }

    @AfterEach
    void clearRawOuterObservations() {
        OUTER_PROXY_RECORDER.clear();
    }

    @Test
    void fairPhysicalWrapperComparisonShowsWhatThePrimitiveProvidesAndWhatTheContractAdds()
            throws Exception {
        PairedCapture<Integer> equality = captureBoth(
                "find-paid-orders-by-user",
                () -> executeEquality(3L));
        PairedCapture<Integer> sameValueRange = captureBoth(
                "find-paid-orders-by-user",
                () -> executeSameValueRange(3L));

        assertEquals(1, equality.value());
        assertEquals(equality.value(), sameValueRange.value(),
                "the application-visible row count remains unchanged");

        // Wrapping only the logical ShardingSphere DataSource observes one application JDBC call.
        assertEquals(1, equality.outerLogicalCalls().size());
        assertEquals(1, sameValueRange.outerLogicalCalls().size());
        assertEquals(
                Set.of("logical-shardingsphere"),
                dataSourceNames(equality.outerLogicalCalls()));
        assertEquals(
                Set.of("logical-shardingsphere"),
                dataSourceNames(sameValueRange.outerLogicalCalls()));
        assertTrue(equality.outerLogicalCalls().get(0).rawSql().contains("FROM t_order WHERE"));
        assertFalse(equality.outerLogicalCalls().get(0).rawSql().contains("t_order_1"));

        // Wrapping every physical DataSource exposes the 1 -> 2 expansion.
        assertEquals(1, equality.diyCapture().rawAttempts().size());
        assertEquals(2, sameValueRange.diyCapture().rawAttempts().size());
        assertEquals("find-paid-orders-by-user", equality.diyCapture().operationId());
        assertEquals("find-paid-orders-by-user", sameValueRange.diyCapture().operationId());
        assertEquals(Set.of("ds_1"), dataSourceNames(equality.diyCapture().rawAttempts()));
        assertEquals(
                Set.of("ds_0", "ds_1"),
                dataSourceNames(sameValueRange.diyCapture().rawAttempts()));
        assertTrue(equality.diyCapture().rawAttempts().stream().allMatch(RawProxyAttempt::success));
        assertTrue(sameValueRange.diyCapture().rawAttempts().stream().allMatch(RawProxyAttempt::success));

        // The generic listener surface intentionally exposes raw rewritten SQL and bound values.
        assertTrue(equality.diyCapture().rawAttempts().stream()
                .anyMatch(attempt -> attempt.rawSql().contains("t_order_1")));
        assertTrue(equality.diyCapture().rawAttempts().stream()
                .flatMap(attempt -> attempt.rawParameterValues().stream())
                .anyMatch("PAID"::equals));

        // RouteContract observes the same normal-return attempts through ShardingSphere's SPI.
        assertReturnedSnapshot(equality.routeSnapshot(), 1, Set.of("ds_1"));
        assertReturnedSnapshot(
                sameValueRange.routeSnapshot(), 2, Set.of("ds_0", "ds_1"));

        Map<String, String> aliases = Map.of(
                "ds_0", "orders-even",
                "ds_1", "orders-odd");

        // datasource-proxy can support the workflow after application-owned correlation,
        // minimization, canonicalization, policy/diff and assertion code is supplied.
        DiyManifest diyApproved = DiyManifest.from(equality.diyCapture(), aliases, 1, 1);
        DiyManifest diyApprovedAgain = DiyManifest.from(equality.diyCapture(), aliases, 1, 1);
        DiyManifest diyCandidate = DiyManifest.from(sameValueRange.diyCapture(), aliases, 1, 1);
        assertArrayEquals(diyApproved.canonicalBytes(), diyApprovedAgain.canonicalBytes());
        assertMinimized(diyApproved.canonicalText());
        assertMinimized(diyCandidate.canonicalText());

        DiyVerification diyVerification = DiyManifestVerifier.verify(diyApproved, diyCandidate);
        assertEquals(
                List.of(
                        "DIY_ATTEMPT_BUDGET_EXCEEDED",
                        "DIY_DATA_SOURCE_BUDGET_EXCEEDED",
                        "DIY_STRUCTURAL_DRIFT"),
                diyVerification.codes());
        AssertionError diyFailure = assertThrows(
                AssertionError.class,
                () -> assertDiyMatched(diyVerification));
        assertTrue(diyFailure.getMessage().contains("DIY_ATTEMPT_BUDGET_EXCEEDED"));

        // RouteContract packages those contract semantics and stable failure codes.
        DataSourceAliases routeAliases = DataSourceAliases.of(aliases);
        ManifestPolicy strictPolicy = ManifestPolicy.strict(1, 1);
        ObservedExecutionManifest routeApproved = ObservedExecutionManifest.from(
                equality.routeSnapshot(), routeAliases, strictPolicy);
        ManifestVerificationResult routeVerification = new ManifestVerifier().verify(
                routeApproved,
                sameValueRange.routeSnapshot(),
                routeAliases);
        assertEquals(VerificationStatus.POLICY_VIOLATION, routeVerification.status());
        assertEquals(
                List.of(
                        ManifestDiffCode.ATTEMPT_BUDGET_EXCEEDED,
                        ManifestDiffCode.DATA_SOURCE_BUDGET_EXCEEDED),
                routeVerification.diffs().stream().map(diff -> diff.code()).toList());
        AssertionError routeFailure = assertThrows(
                AssertionError.class,
                () -> ManifestAssertions.assertMatched(routeVerification));
        assertTrue(routeFailure.getMessage().contains("RCM201"));
        assertTrue(routeFailure.getMessage().contains("RCM202"));

        System.out.println("ROUTECONTRACT_DATASOURCE_PROXY_COMPARISON "
                + "businessRows=1->1 outerLogicalCallbacks=1->1 "
                + "innerPhysicalCallbacks=1->2 routeContractAttempts=1->2 "
                + "diyWiring=[physical-wrappers,ttl-correlation,minimization,canonicalization,diff,assertion]");
    }

    private static PairedCapture<Integer> captureBoth(
            final String operationId,
            final ThrowingSupplier<Integer> operation) throws Exception {
        int outerStart = OUTER_PROXY_RECORDER.size();
        CapturedResult<DiyCapture<Integer>> routeResult = RouteContract.captureResult(
                operationId,
                () -> INNER_PROXY_COLLECTOR.capture(operationId, operation));
        DiyCapture<Integer> diyCapture = routeResult.value();
        return new PairedCapture<>(
                diyCapture.value(),
                routeResult.snapshot(),
                diyCapture,
                OUTER_PROXY_RECORDER.since(outerStart));
    }

    private static int executeEquality(final long userId) throws Exception {
        return execute(
                "SELECT order_id, user_id, status FROM t_order WHERE user_id = ? AND status = ?",
                List.of(userId, "PAID"));
    }

    private static int executeSameValueRange(final long userId) throws Exception {
        return execute(
                "SELECT order_id, user_id, status FROM t_order "
                        + "WHERE user_id BETWEEN ? AND ? AND status = ?",
                List.of(userId, userId, "PAID"));
    }

    private static int execute(final String sql, final List<Object> parameters) throws Exception {
        try (Connection connection = logicalOuterProxy.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            for (int index = 0; index < parameters.size(); index++) {
                statement.setObject(index + 1, parameters.get(index));
            }
            int rows = 0;
            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    rows++;
                }
            }
            return rows;
        }
    }

    private static void assertReturnedSnapshot(
            final RouteSnapshot snapshot,
            final int expectedAttempts,
            final Set<String> expectedNames) {
        assertEquals(CaptureStatus.COMPLETE, snapshot.status());
        assertEquals(expectedAttempts, snapshot.observedPhysicalAttemptCount());
        assertEquals(expectedNames, Set.copyOf(snapshot.observedDataSourceNames()));
        assertTrue(snapshot.attempts().stream()
                .allMatch(attempt -> attempt.outcome() == AttemptOutcome.CALLBACK_RETURNED));
    }

    private static void assertMinimized(final String manifestText) {
        for (String forbidden : List.of("SELECT", "t_order", "PAID", "ds_0", "ds_1")) {
            assertFalse(
                    manifestText.contains(forbidden),
                    () -> "DIY minimized evidence retained forbidden text: " + forbidden);
        }
    }

    private static void assertDiyMatched(final DiyVerification verification) {
        if (!verification.codes().isEmpty()) {
            throw new AssertionError("datasource-proxy DIY contract mismatch: " + verification.codes());
        }
    }

    private static Set<String> dataSourceNames(final List<RawProxyAttempt> attempts) {
        Set<String> result = new LinkedHashSet<>();
        attempts.forEach(attempt -> result.add(attempt.configuredProxyName()));
        return Set.copyOf(result);
    }

    private static DataSource innerProxy(
            final String dataSourceName,
            final MySQLContainer<?> container) {
        DataSource raw = new DriverManagerDataSource(
                container.getJdbcUrl(),
                container.getUsername(),
                container.getPassword());
        DataSource observed = ProxyDataSourceBuilder.create(raw)
                .name(dataSourceName)
                .listener(INNER_PROXY_COLLECTOR)
                .build();
        return new ShardingSphereInspectableDataSource(
                observed,
                container.getJdbcUrl(),
                container.getUsername(),
                container.getPassword());
    }

    private static MySQLContainer<?> mysql() {
        return new MySQLContainer<>(MYSQL_IMAGE)
                .withDatabaseName("routecontract")
                .withUsername("routecontract")
                .withPassword("routecontract");
    }

    private static Connection physicalConnection(final MySQLContainer<?> container) throws Exception {
        return DriverManager.getConnection(
                container.getJdbcUrl(),
                container.getUsername(),
                container.getPassword());
    }

    private static void initialize(final MySQLContainer<?> container) throws Exception {
        try (Connection connection = physicalConnection(container);
             Statement statement = connection.createStatement()) {
            statement.execute("CREATE TABLE t_order_0 ("
                    + "order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
            statement.execute("CREATE TABLE t_order_1 ("
                    + "order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
        }
    }

    private static String shardingRules() {
        return """
                mode:
                  type: Standalone
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
                """;
    }

    private static List<Object> parameterValues(final QueryInfo queryInfo) {
        List<Object> result = new ArrayList<>();
        for (List<ParameterSetOperation> parameterSet : queryInfo.getParametersList()) {
            for (ParameterSetOperation operation : parameterSet) {
                Object[] arguments = operation.getArgs();
                if (arguments != null && arguments.length > 1) {
                    result.add(arguments[1]);
                }
            }
        }
        return List.copyOf(result);
    }

    private static List<String> parameterTypes(final List<Object> values) {
        return values.stream()
                .map(value -> value == null ? "null" : value.getClass().getName())
                .toList();
    }

    private static String sha256(final String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is required by the Java platform", impossible);
        }
    }

    private static final class FlatQueryRecorder implements QueryExecutionListener {

        private final CopyOnWriteArrayList<RawProxyAttempt> observations = new CopyOnWriteArrayList<>();

        @Override
        public void beforeQuery(final ExecutionInfo executionInfo, final List<QueryInfo> queryInfoList) {
            // The comparison records completed normal-return callbacks only.
        }

        @Override
        public void afterQuery(final ExecutionInfo executionInfo, final List<QueryInfo> queryInfoList) {
            queryInfoList.forEach(queryInfo -> observations.add(RawProxyAttempt.from(
                    executionInfo, queryInfo)));
        }

        int size() {
            return observations.size();
        }

        List<RawProxyAttempt> since(final int startIndex) {
            return List.copyOf(observations.subList(startIndex, observations.size()));
        }

        void clear() {
            observations.clear();
        }
    }

    /**
     * Test-only operation correlator needed on top of datasource-proxy for this comparison.
     * It intentionally supports only the synchronous, normal-return PreparedStatement boundary.
     */
    private static final class DiyOperationCollector implements QueryExecutionListener {

        private final TransmittableThreadLocal<OperationToken> current = new SubmissionOnlyContext();
        private final ConcurrentMap<OperationToken, CopyOnWriteArrayList<RawProxyAttempt>> active =
                new ConcurrentHashMap<>();

        <T> DiyCapture<T> capture(
                final String operationId,
                final ThrowingSupplier<T> operation) throws Exception {
            if (current.get() != null) {
                throw new IllegalStateException("nested DIY captures are not supported");
            }
            OperationToken token = new OperationToken(UUID.randomUUID(), operationId);
            CopyOnWriteArrayList<RawProxyAttempt> observations = new CopyOnWriteArrayList<>();
            if (active.putIfAbsent(token, observations) != null) {
                throw new IllegalStateException("DIY capture token collision");
            }
            current.set(token);
            try {
                T value = operation.get();
                return new DiyCapture<>(operationId, value, List.copyOf(observations));
            } finally {
                current.remove();
                active.remove(token, observations);
            }
        }

        @Override
        public void beforeQuery(final ExecutionInfo executionInfo, final List<QueryInfo> queryInfoList) {
            // The comparison records completed normal-return callbacks only.
        }

        @Override
        public void afterQuery(final ExecutionInfo executionInfo, final List<QueryInfo> queryInfoList) {
            OperationToken token = current.get();
            if (token == null) {
                return;
            }
            List<RawProxyAttempt> observations = active.get(token);
            if (observations != null) {
                queryInfoList.forEach(queryInfo -> observations.add(RawProxyAttempt.from(
                        executionInfo, queryInfo)));
            }
        }
    }

    private static final class SubmissionOnlyContext extends TransmittableThreadLocal<OperationToken> {
        @Override
        protected OperationToken childValue(final OperationToken parentValue) {
            return null;
        }
    }

    private record OperationToken(UUID id, String operationId) {
        private OperationToken {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(operationId, "operationId");
        }
    }

    private record RawProxyAttempt(
            String configuredProxyName,
            String rawSql,
            List<Object> rawParameterValues,
            boolean success) {

        private RawProxyAttempt {
            configuredProxyName = Objects.requireNonNull(configuredProxyName, "configuredProxyName");
            rawSql = Objects.requireNonNull(rawSql, "rawSql");
            rawParameterValues = List.copyOf(rawParameterValues);
        }

        static RawProxyAttempt from(
                final ExecutionInfo executionInfo,
                final QueryInfo queryInfo) {
            return new RawProxyAttempt(
                    executionInfo.getDataSourceName(),
                    queryInfo.getQuery(),
                    parameterValues(queryInfo),
                    executionInfo.isSuccess());
        }
    }

    private record DiyCapture<T>(String operationId, T value, List<RawProxyAttempt> rawAttempts) {
        private DiyCapture {
            operationId = Objects.requireNonNull(operationId, "operationId");
            rawAttempts = List.copyOf(rawAttempts);
        }
    }

    private record PairedCapture<T>(
            T value,
            RouteSnapshot routeSnapshot,
            DiyCapture<T> diyCapture,
            List<RawProxyAttempt> outerLogicalCalls) {
        private PairedCapture {
            outerLogicalCalls = List.copyOf(outerLogicalCalls);
        }
    }

    /** Test-only minimized representation; it is not a reusable datasource-proxy extension. */
    private record DiyAttempt(
            String dataSourceAlias,
            String sqlFingerprint,
            List<String> parameterTypes,
            String outcome) {
        private DiyAttempt {
            parameterTypes = List.copyOf(parameterTypes);
        }

        static DiyAttempt from(
                final RawProxyAttempt raw,
                final Map<String, String> aliases) {
            String alias = aliases.get(raw.configuredProxyName());
            if (alias == null) {
                throw new IllegalArgumentException(
                        "missing DIY alias for proxy name " + raw.configuredProxyName());
            }
            return new DiyAttempt(
                    alias,
                    sha256(raw.rawSql()),
                    DataSourceProxyComparisonMySqlTest.parameterTypes(raw.rawParameterValues()),
                    raw.success() ? "CALLBACK_RETURNED" : "CALLBACK_FAILURE");
        }

        String canonicalLine() {
            return dataSourceAlias + "|" + sqlFingerprint + "|"
                    + String.join(",", parameterTypes) + "|" + outcome;
        }
    }

    /** Test-only baseline format showing the extra product code a generic listener needs. */
    private record DiyManifest(
            String operationId,
            int maxAttempts,
            int maxDistinctDataSources,
            int observedAttempts,
            int distinctDataSources,
            List<DiyAttempt> attempts) {

        private static final Comparator<DiyAttempt> ATTEMPT_ORDER = Comparator
                .comparing(DiyAttempt::dataSourceAlias)
                .thenComparing(DiyAttempt::sqlFingerprint)
                .thenComparing(attempt -> String.join(",", attempt.parameterTypes()))
                .thenComparing(DiyAttempt::outcome);

        private DiyManifest {
            attempts = attempts.stream().sorted(ATTEMPT_ORDER).toList();
        }

        static DiyManifest from(
                final DiyCapture<?> capture,
                final Map<String, String> aliases,
                final int maxAttempts,
                final int maxDistinctDataSources) {
            List<DiyAttempt> attempts = capture.rawAttempts().stream()
                    .map(raw -> DiyAttempt.from(raw, aliases))
                    .toList();
            int distinctSources = (int) attempts.stream()
                    .map(DiyAttempt::dataSourceAlias)
                    .distinct()
                    .count();
            return new DiyManifest(
                    capture.operationId(),
                    maxAttempts,
                    maxDistinctDataSources,
                    attempts.size(),
                    distinctSources,
                    attempts);
        }

        String canonicalText() {
            StringBuilder result = new StringBuilder();
            result.append("diy-format=1\n");
            result.append("operationId=").append(operationId).append('\n');
            result.append("maxAttempts=").append(maxAttempts).append('\n');
            result.append("maxDistinctDataSources=").append(maxDistinctDataSources).append('\n');
            result.append("observedAttempts=").append(observedAttempts).append('\n');
            result.append("distinctDataSources=").append(distinctDataSources).append('\n');
            attempts.forEach(attempt -> result.append("attempt=")
                    .append(attempt.canonicalLine())
                    .append('\n'));
            return result.toString();
        }

        byte[] canonicalBytes() {
            return canonicalText().getBytes(StandardCharsets.UTF_8);
        }
    }

    private record DiyVerification(List<String> codes) {
        private DiyVerification {
            codes = List.copyOf(codes);
        }
    }

    private static final class DiyManifestVerifier {
        static DiyVerification verify(final DiyManifest approved, final DiyManifest candidate) {
            List<String> findings = new ArrayList<>();
            if (candidate.observedAttempts() > approved.maxAttempts()) {
                findings.add("DIY_ATTEMPT_BUDGET_EXCEEDED");
            }
            if (candidate.distinctDataSources() > approved.maxDistinctDataSources()) {
                findings.add("DIY_DATA_SOURCE_BUDGET_EXCEEDED");
            }
            if (!approved.attempts().equals(candidate.attempts())) {
                findings.add("DIY_STRUCTURAL_DRIFT");
            }
            return new DiyVerification(findings);
        }

        private DiyManifestVerifier() {
        }
    }

    /** Minimal unpooled physical DataSource so the test can wrap each storage unit explicitly. */
    private static final class DriverManagerDataSource implements DataSource {

        private final String jdbcUrl;
        private final String username;
        private final String password;
        private volatile PrintWriter logWriter;
        private volatile int loginTimeout;

        private DriverManagerDataSource(
                final String jdbcUrl,
                final String username,
                final String password) {
            this.jdbcUrl = jdbcUrl;
            this.username = username;
            this.password = password;
        }

        @Override
        public Connection getConnection() throws SQLException {
            return DriverManager.getConnection(jdbcUrl, username, password);
        }

        @Override
        public Connection getConnection(final String user, final String secret) throws SQLException {
            return DriverManager.getConnection(jdbcUrl, user, secret);
        }

        @Override
        public PrintWriter getLogWriter() {
            return logWriter;
        }

        @Override
        public void setLogWriter(final PrintWriter writer) {
            logWriter = writer;
        }

        @Override
        public void setLoginTimeout(final int seconds) {
            loginTimeout = seconds;
        }

        @Override
        public int getLoginTimeout() {
            return loginTimeout;
        }

        @Override
        public Logger getParentLogger() {
            return Logger.getLogger(Logger.GLOBAL_LOGGER_NAME);
        }

        @Override
        public <T> T unwrap(final Class<T> type) throws SQLException {
            if (type.isInstance(this)) {
                return type.cast(this);
            }
            throw new SQLException("Not a wrapper for " + type.getName());
        }

        @Override
        public boolean isWrapperFor(final Class<?> type) {
            return type.isInstance(this);
        }
    }

    /**
     * Keeps datasource-proxy on the physical JDBC path while exposing the connection metadata
     * that ShardingSphere 5.5.3 reflects from a caller-supplied DataSource.
     */
    public static final class ShardingSphereInspectableDataSource implements DataSource {

        private final DataSource delegate;
        private final String url;
        private final String username;
        private final String password;

        private ShardingSphereInspectableDataSource(
                final DataSource delegate,
                final String url,
                final String username,
                final String password) {
            this.delegate = delegate;
            this.url = url;
            this.username = username;
            this.password = password;
        }

        public String getUrl() {
            return url;
        }

        public String getUsername() {
            return username;
        }

        public String getPassword() {
            return password;
        }

        @Override
        public Connection getConnection() throws SQLException {
            return delegate.getConnection();
        }

        @Override
        public Connection getConnection(final String user, final String secret) throws SQLException {
            return delegate.getConnection(user, secret);
        }

        @Override
        public PrintWriter getLogWriter() throws SQLException {
            return delegate.getLogWriter();
        }

        @Override
        public void setLogWriter(final PrintWriter writer) throws SQLException {
            delegate.setLogWriter(writer);
        }

        @Override
        public void setLoginTimeout(final int seconds) throws SQLException {
            delegate.setLoginTimeout(seconds);
        }

        @Override
        public int getLoginTimeout() throws SQLException {
            return delegate.getLoginTimeout();
        }

        @Override
        public Logger getParentLogger() throws java.sql.SQLFeatureNotSupportedException {
            return delegate.getParentLogger();
        }

        @Override
        public <T> T unwrap(final Class<T> type) throws SQLException {
            if (type.isInstance(this)) {
                return type.cast(this);
            }
            return delegate.unwrap(type);
        }

        @Override
        public boolean isWrapperFor(final Class<?> type) throws SQLException {
            return type.isInstance(this) || delegate.isWrapperFor(type);
        }
    }

    @FunctionalInterface
    private interface ThrowingSupplier<T> {
        T get() throws Exception;
    }
}
