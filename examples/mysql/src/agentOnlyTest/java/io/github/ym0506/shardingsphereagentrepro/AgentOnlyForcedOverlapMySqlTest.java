package io.github.ym0506.shardingsphereagentrepro;

import net.ttddyy.dsproxy.ExecutionInfo;
import net.ttddyy.dsproxy.QueryInfo;
import net.ttddyy.dsproxy.listener.QueryExecutionListener;
import net.ttddyy.dsproxy.support.ProxyDataSourceBuilder;
import org.apache.shardingsphere.driver.api.yaml.YamlShardingSphereDataSourceFactory;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import javax.sql.DataSource;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.PrintWriter;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Enumeration;
import java.util.LinkedHashSet;
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
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.fail;

/**
 * Agent-only acceptance fixture for a forced two-way ShardingSphere fan-out.
 *
 * <p>The dedicated Gradle source set has no dependency on RouteContract. This test repeats that
 * isolation check inside the forked JVM, then uses a count-only datasource-proxy listener as the
 * backing-call oracle. During each fan-out statement, a two-party barrier holds both physical
 * calls after Agent advice entry and before either query proceeds.</p>
 */
@Testcontainers
class AgentOnlyForcedOverlapMySqlTest {

    private static final int ITERATIONS = 20;
    private static final int MAX_SERVICE_DESCRIPTOR_BYTES = 4 * 1024;
    private static final String ROUTECONTRACT_API =
            "io.github.ym0506.routecontract.RouteContract";
    private static final String ROUTECONTRACT_HOOK =
            "io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook";
    private static final String ROUTECONTRACT_ARTIFACT_PREFIX =
            "routecontract-shardingsphere-5.5-";
    private static final String SQL_EXECUTION_HOOK_SERVICE =
            "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";
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
        assertRouteContractRuntimeAbsent();
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
    void forcesTwentyTwoWayFanOutPairsWithoutRouteContractRuntime() throws Exception {
        Path evidencePath = requiredEvidencePath();
        int proxyAttemptBaseline = PHYSICAL_ORACLE.observedAttempts();
        int proxyFailureBaseline = PHYSICAL_ORACLE.reportedFailures();
        int totalControlRows = 0;
        int totalFanOutRows = 0;

        for (int iteration = 0; iteration < ITERATIONS; iteration++) {
            int iterationStart = PHYSICAL_ORACLE.observedAttempts();

            int controlRows = executeEquality(3L);
            int afterControl = PHYSICAL_ORACLE.observedAttempts();
            assertEquals(1, controlRows);
            assertEquals(1, afterControl - iterationStart,
                    "the single-target control must invoke one backing query callback");

            PHYSICAL_ORACLE.armFanOutPair();
            final int fanOutRows;
            try {
                fanOutRows = executeSameValueRange(3L);
            } finally {
                PHYSICAL_ORACLE.finishFanOutPair();
            }
            assertEquals(1, fanOutRows);
            assertEquals(2, PHYSICAL_ORACLE.observedAttempts() - afterControl,
                    "the range mutation must invoke two backing query callbacks");
            assertEquals(3, PHYSICAL_ORACLE.observedAttempts() - iterationStart);
            totalControlRows += controlRows;
            totalFanOutRows += fanOutRows;
        }

        assertEquals(60, PHYSICAL_ORACLE.observedAttempts() - proxyAttemptBaseline);
        assertEquals(0, PHYSICAL_ORACLE.reportedFailures() - proxyFailureBaseline);
        assertEquals(20, PHYSICAL_ORACLE.forcedFanOutPairs());
        assertEquals(20, totalControlRows);
        assertEquals(20, totalFanOutRows);
        assertRouteContractRuntimeAbsent();

        writePrivacySafeEvidence(evidencePath);
    }

    private static void assertRouteContractRuntimeAbsent() throws Exception {
        Set<ClassLoader> loaders = new LinkedHashSet<>();
        loaders.add(AgentOnlyForcedOverlapMySqlTest.class.getClassLoader());
        loaders.add(Thread.currentThread().getContextClassLoader());
        loaders.add(ClassLoader.getSystemClassLoader());
        loaders.remove(null);

        for (ClassLoader loader : loaders) {
            assertClassAbsent(ROUTECONTRACT_API, loader);
            assertClassAbsent(ROUTECONTRACT_HOOK, loader);
            assertNull(loader.getResource(ROUTECONTRACT_API.replace('.', '/') + ".class"),
                    "RouteContract API resource must be absent from the Agent-only JVM");
            assertNull(loader.getResource(ROUTECONTRACT_HOOK.replace('.', '/') + ".class"),
                    "RouteContract hook resource must be absent from the Agent-only JVM");
            assertNoRouteContractServiceProvider(loader);
        }

        String classpath = System.getProperty("java.class.path", "");
        int forbiddenArtifactEntries = 0;
        for (String entry : classpath.split(Pattern.quote(File.pathSeparator), -1)) {
            if (entry.isEmpty()) {
                continue;
            }
            try {
                Path filename = Path.of(entry).getFileName();
                if (filename != null
                        && filename.toString().startsWith(ROUTECONTRACT_ARTIFACT_PREFIX)) {
                    forbiddenArtifactEntries++;
                }
            } catch (RuntimeException ignored) {
                forbiddenArtifactEntries++;
            }
        }
        assertEquals(0, forbiddenArtifactEntries,
                "RouteContract artifact must be absent from java.class.path");
    }

    private static void assertClassAbsent(final String className, final ClassLoader loader) {
        try {
            Class.forName(className, false, loader);
            fail("RouteContract class must be absent from the Agent-only JVM");
        } catch (ClassNotFoundException expected) {
            // Expected isolation proof.
        }
    }

    private static void assertNoRouteContractServiceProvider(final ClassLoader loader)
            throws IOException {
        Enumeration<URL> resources = loader.getResources(SQL_EXECUTION_HOOK_SERVICE);
        while (resources.hasMoreElements()) {
            URL resource = resources.nextElement();
            byte[] content;
            try (InputStream stream = resource.openStream()) {
                content = stream.readNBytes(MAX_SERVICE_DESCRIPTOR_BYTES + 1);
            }
            assertFalse(content.length > MAX_SERVICE_DESCRIPTOR_BYTES,
                    "SQLExecutionHook service descriptor exceeds the bounded inspection size");
            String descriptor = new String(content, StandardCharsets.UTF_8);
            for (String line : descriptor.split("\\R", -1)) {
                String provider = line.split("#", 2)[0].trim();
                assertFalse(provider.equals(ROUTECONTRACT_HOOK),
                        "RouteContract SQLExecutionHook provider must be absent");
            }
        }
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

    private static Path requiredEvidencePath() {
        String configured = System.getProperty("agentOnlyEvidence");
        if (configured == null || configured.isBlank()) {
            throw new IllegalStateException(
                    "agentOnlyEvidence must name the new privacy-safe JSON output path");
        }
        Path path = Path.of(configured).toAbsolutePath().normalize();
        Path parent = path.getParent();
        if (parent == null
                || !Files.isDirectory(parent, LinkOption.NOFOLLOW_LINKS)
                || Files.exists(path, LinkOption.NOFOLLOW_LINKS)) {
            throw new IllegalStateException(
                    "agentOnlyEvidence must name a new file in an existing directory");
        }
        return path;
    }

    private static void writePrivacySafeEvidence(final Path evidencePath) throws Exception {
        String evidence = "{\"schemaVersion\":1,\"iterations\":20,\"logicalStatements\":40,"
                + "\"controlExpectedBackingCallbacks\":20,"
                + "\"fanOutExpectedBackingCallbacks\":40,"
                + "\"expectedBackingCallbacks\":60,"
                + "\"proxyObservedBackingCallbacks\":60,\"proxyReportedFailures\":0,"
                + "\"forcedFanOutPairs\":20,\"controlReturnedRows\":20,"
                + "\"fanOutReturnedRows\":20,"
                + "\"routeContractArtifactClasspathEntries\":0,"
                + "\"routeContractApiClassPresent\":false,"
                + "\"routeContractHookClassPresent\":false,"
                + "\"routeContractSpiProviderPresent\":false}\n";
        Files.writeString(
                evidencePath,
                evidence,
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW,
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
                .withDatabaseName("agent_only_reproducer")
                .withUsername("agent_only_reproducer")
                .withPassword("agent_only_reproducer");
    }

    private static Connection physicalConnection(final MySQLContainer<?> container)
            throws SQLException {
        return DriverManager.getConnection(
                container.getJdbcUrl(),
                container.getUsername(),
                container.getPassword());
    }

    private static void initialize(final MySQLContainer<?> container) throws Exception {
        try (Connection connection = physicalConnection(container);
             Statement statement = connection.createStatement()) {
            statement.execute("CREATE TABLE t_order_0 ("
                    + "order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, "
                    + "status VARCHAR(64) NOT NULL)");
            statement.execute("CREATE TABLE t_order_1 ("
                    + "order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, "
                    + "status VARCHAR(64) NOT NULL)");
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
                throw new IllegalStateException(
                        "the two backing fan-out calls did not overlap cleanly");
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
        public void beforeQuery(
                final ExecutionInfo executionInfo,
                final List<QueryInfo> queryInfoList) {
            CyclicBarrier barrier = activeFanOutBarrier.get();
            if (barrier == null) {
                return;
            }
            try {
                barrier.await(BARRIER_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "interrupted while forcing backing fan-out overlap", exception);
            } catch (BrokenBarrierException | TimeoutException exception) {
                throw new IllegalStateException(
                        "backing fan-out calls failed to reach the barrier", exception);
            }
        }

        @Override
        public void afterQuery(
                final ExecutionInfo executionInfo,
                final List<QueryInfo> queryInfoList) {
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
        public Connection getConnection(final String user, final String secret)
                throws SQLException {
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
        public Connection getConnection(final String user, final String secret)
                throws SQLException {
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
    private interface StatementBinder {
        void bind(PreparedStatement statement) throws Exception;
    }
}
