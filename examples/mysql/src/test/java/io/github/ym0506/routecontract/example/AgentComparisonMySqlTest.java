package io.github.ym0506.routecontract.example;

import io.github.ym0506.routecontract.AttemptOutcome;
import io.github.ym0506.routecontract.CaptureStatus;
import io.github.ym0506.routecontract.CapturedResult;
import io.github.ym0506.routecontract.PhysicalExecutionAttempt;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteSnapshot;
import net.ttddyy.dsproxy.ExecutionInfo;
import net.ttddyy.dsproxy.QueryInfo;
import net.ttddyy.dsproxy.listener.QueryExecutionListener;
import net.ttddyy.dsproxy.support.ProxyDataSourceBuilder;
import org.apache.shardingsphere.driver.api.yaml.YamlShardingSphereDataSourceFactory;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import javax.sql.DataSource;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.logging.Logger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Opt-in acceptance fixture for comparing ShardingSphere Agent spans with two in-process oracles.
 *
 * <p>Each physical data source is wrapped before it is supplied to ShardingSphere. During each
 * fan-out statement, the count-only listener holds both backing calls at a two-party barrier. A
 * caller-attached Agent therefore has entered both {@code JDBCExecutorCallback.execute} advices
 * before either physical query proceeds. The listener never reads or retains SQL, parameters,
 * connection metadata, ports, or data-source names.</p>
 */
@Testcontainers
@Tag("agent-comparison")
class AgentComparisonMySqlTest {

    private static final int OPERATIONS = 20;
    private static final DockerImageName MYSQL_IMAGE = DockerImageName.parse(
            "mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb")
            .asCompatibleSubstituteFor("mysql");
    private static final PhysicalAttemptOracle PHYSICAL_ORACLE = new PhysicalAttemptOracle();

    @Container
    private static final MySQLContainer<?> DS_0 = mysql();

    @Container
    private static final MySQLContainer<?> DS_1 = mysql();

    private static DataSource shardingDataSource;

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
                "ds_0", observedDataSource(DS_0),
                "ds_1", observedDataSource(DS_1));
        shardingDataSource = YamlShardingSphereDataSourceFactory.createDataSource(
                physicalDataSources,
                shardingRules().getBytes(StandardCharsets.UTF_8));
    }

    @AfterAll
    static void closeDataSource() throws Exception {
        if (shardingDataSource instanceof AutoCloseable closeable) {
            closeable.close();
        }
    }

    @Test
    void sequentialOperationsExposeExpectedPhysicalAttemptCounts() throws Exception {
        Path evidencePath = requiredEvidencePath();
        Set<String> routeSignatures = new HashSet<>();
        int routeContractObservedAttempts = 0;
        int proxyObservedAttempts = 0;
        int proxyAttemptBaseline = PHYSICAL_ORACLE.observedAttempts();
        int proxyFailureBaseline = PHYSICAL_ORACLE.reportedFailures();

        for (int iteration = 0; iteration < OPERATIONS; iteration++) {
            int operationStart = PHYSICAL_ORACLE.observedAttempts();
            CapturedResult<BusinessRows> captured = RouteContract.captureResult(
                    "agent-comparison-operation-" + iteration,
                    () -> executeObservedOperation(operationStart));

            assertEquals(1, captured.value().controlRows());
            assertEquals(1, captured.value().fanOutRows());
            assertEquals(1, captured.value().controlProxyAttempts());
            assertEquals(2, captured.value().fanOutProxyAttempts());
            assertEquals(3, PHYSICAL_ORACLE.observedAttempts() - operationStart);

            RouteSnapshot snapshot = captured.snapshot();
            assertCompleteOperationSnapshot(snapshot);
            routeContractObservedAttempts += snapshot.observedPhysicalAttemptCount();
            proxyObservedAttempts += captured.value().controlProxyAttempts()
                    + captured.value().fanOutProxyAttempts();
            routeSignatures.add(canonicalSignature(snapshot));
        }

        assertEquals(60, proxyObservedAttempts);
        assertEquals(
                proxyObservedAttempts,
                PHYSICAL_ORACLE.observedAttempts() - proxyAttemptBaseline,
                "only the twenty operation deltas count toward comparison evidence");
        assertEquals(
                0,
                PHYSICAL_ORACLE.reportedFailures() - proxyFailureBaseline,
                "no comparison operation may produce a failed physical proxy callback");
        assertEquals(60, routeContractObservedAttempts);
        assertEquals(20, PHYSICAL_ORACLE.forcedFanOutPairs());
        assertEquals(1, routeSignatures.size(),
                "all twenty operation-scoped route signatures must be identical");

        writePrivacySafeEvidence(evidencePath);
    }

    private static BusinessRows executeObservedOperation(final int operationStart) throws Exception {
        int controlRows = executeEquality(3L);
        int afterControl = PHYSICAL_ORACLE.observedAttempts();
        int controlAttempts = afterControl - operationStart;
        assertEquals(1, controlAttempts,
                "the single-target control must invoke one physical backing query");

        PHYSICAL_ORACLE.armFanOutPair();
        final int fanOutRows;
        try {
            fanOutRows = executeSameValueRange(3L);
        } finally {
            PHYSICAL_ORACLE.finishFanOutPair();
        }
        int fanOutAttempts = PHYSICAL_ORACLE.observedAttempts() - afterControl;
        assertEquals(2, fanOutAttempts,
                "the range mutation must invoke two physical backing queries");
        return new BusinessRows(controlRows, fanOutRows, controlAttempts, fanOutAttempts);
    }

    private static int executeEquality(final long userId) throws Exception {
        return execute(
                "SELECT order_id, user_id, status FROM t_order WHERE user_id = ? AND status = ?",
                statement -> {
                    statement.setLong(1, userId);
                    statement.setString(2, "PAID");
                });
    }

    private static int executeSameValueRange(final long userId) throws Exception {
        return execute(
                "SELECT order_id, user_id, status FROM t_order "
                        + "WHERE user_id BETWEEN ? AND ? AND status = ?",
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

    private static void assertCompleteOperationSnapshot(final RouteSnapshot snapshot) {
        assertEquals(CaptureStatus.COMPLETE, snapshot.status(),
                "the operation capture must be complete");
        assertEquals(3, snapshot.observedPhysicalAttemptCount(),
                "the operation must report three physical JDBC execution attempts");
        assertEquals(3, snapshot.callbackReturnedCount(),
                "all three physical callbacks must report normal return");
        assertEquals(0, snapshot.callbackFailureCount(),
                "no physical callback may report an execution failure");
        assertEquals(0, snapshot.unknownOutcomeCount(),
                "no physical callback outcome may remain unknown");
        assertEquals(2, snapshot.observedDataSourceNames().size(),
                "the operation must report two distinct data-source names");
        assertEquals(2, snapshot.trunkThreadFlagCount(),
                "the operation must report two trunk-thread flags");
        assertEquals(1, snapshot.workerThreadFlagCount(),
                "the operation must report one worker-thread flag");
        assertTrue(snapshot.collectorDiagnostics().isEmpty(),
                "the operation capture must have no collector diagnostics");
        assertTrue(snapshot.attempts().stream()
                .allMatch(attempt -> attempt.outcome() == AttemptOutcome.CALLBACK_RETURNED));
    }

    private static String canonicalSignature(final RouteSnapshot snapshot) {
        return snapshot.attempts().stream()
                .map(AgentComparisonMySqlTest::canonicalAttempt)
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

    private static Path requiredEvidencePath() {
        String configured = System.getProperty("routecontractAgentEvidence");
        if (configured == null || configured.isBlank()) {
            throw new IllegalStateException(
                    "routecontractAgentEvidence must name the privacy-safe JSON output path");
        }
        return Path.of(configured).toAbsolutePath().normalize();
    }

    private static void writePrivacySafeEvidence(final Path evidencePath) throws Exception {
        String evidence = "{\"schemaVersion\":1,\"operations\":20,\"logicalStatements\":40,"
                + "\"controlExpectedAttempts\":20,\"fanOutExpectedAttempts\":40,"
                + "\"expectedPhysicalAttempts\":60,\"proxyObservedAttempts\":60,"
                + "\"routeContractObservedAttempts\":60,\"forcedFanOutPairs\":20,"
                + "\"uniqueRouteSignatures\":1}\n";
        Path parent = evidencePath.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }
        Files.writeString(
                evidencePath,
                evidence,
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING,
                StandardOpenOption.WRITE);
    }

    private static DataSource observedDataSource(final MySQLContainer<?> container) {
        DataSource physical = new DriverManagerDataSource(
                container.getJdbcUrl(),
                container.getUsername(),
                container.getPassword());
        DataSource observed = ProxyDataSourceBuilder.create(physical)
                .listener(PHYSICAL_ORACLE)
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

    private static Connection physicalConnection(final MySQLContainer<?> container) throws SQLException {
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

    /** Count-only oracle that also forces each two-way fan-out pair to overlap. */
    private static final class PhysicalAttemptOracle implements QueryExecutionListener {

        private static final long BARRIER_TIMEOUT_SECONDS = 20L;
        private final AtomicInteger observedAttempts = new AtomicInteger();
        private final AtomicInteger reportedFailures = new AtomicInteger();
        private final AtomicInteger forcedFanOutPairs = new AtomicInteger();
        private final AtomicReference<CyclicBarrier> activeFanOutBarrier = new AtomicReference<>();

        void armFanOutPair() {
            CyclicBarrier barrier = new CyclicBarrier(2, forcedFanOutPairs::incrementAndGet);
            if (!activeFanOutBarrier.compareAndSet(null, barrier)) {
                throw new IllegalStateException("a fan-out barrier is already active");
            }
        }

        void finishFanOutPair() {
            CyclicBarrier barrier = activeFanOutBarrier.getAndSet(null);
            if (barrier == null) {
                throw new IllegalStateException("no fan-out barrier is active");
            }
            if (barrier.isBroken() || barrier.getNumberWaiting() != 0) {
                throw new IllegalStateException("the two physical fan-out calls did not overlap cleanly");
            }
        }

        int observedAttempts() {
            return observedAttempts.get();
        }

        int reportedFailures() {
            return reportedFailures.get();
        }

        int forcedFanOutPairs() {
            return forcedFanOutPairs.get();
        }

        @Override
        public void beforeQuery(final ExecutionInfo executionInfo, final List<QueryInfo> queryInfoList) {
            CyclicBarrier barrier = activeFanOutBarrier.get();
            if (barrier == null) {
                return;
            }
            try {
                barrier.await(BARRIER_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("interrupted while forcing physical fan-out overlap", exception);
            } catch (BrokenBarrierException | TimeoutException exception) {
                throw new IllegalStateException("physical fan-out calls failed to reach the barrier", exception);
            }
        }

        @Override
        public void afterQuery(final ExecutionInfo executionInfo, final List<QueryInfo> queryInfoList) {
            observedAttempts.addAndGet(queryInfoList.size());
            if (!executionInfo.isSuccess()) {
                reportedFailures.addAndGet(queryInfoList.size());
            }
        }
    }

    /** Minimal unpooled physical data source used only inside this acceptance fixture. */
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

    /** Exposes the connection properties reflected by ShardingSphere for supplied data sources. */
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

    private record BusinessRows(
            int controlRows,
            int fanOutRows,
            int controlProxyAttempts,
            int fanOutProxyAttempts) {
    }

    @FunctionalInterface
    private interface StatementBinder {
        void bind(PreparedStatement statement) throws Exception;
    }
}
