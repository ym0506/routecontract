package io.github.ym0506.routecontract.consumer;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.ym0506.routecontract.CapturedResult;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import io.github.ym0506.routecontract.api.RouteContract;
import org.apache.shardingsphere.driver.api.yaml.YamlShardingSphereDataSourceFactory;

import javax.sql.DataSource;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.Driver;
import java.sql.DriverManager;
import java.sql.DriverPropertyInfo;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Properties;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Logger;

/**
 * One cold-JVM successor-contract observation against actual supplied JARs.
 * Capture modes make their selected capture method the first RouteContract call.
 * Ordinary SQL does not call RouteContract before datasource construction or its query.
 */
public final class CurrentEntrySuccessorProbe {
    private static final String SENTINEL = "current-entry-sentinel";
    private static final Set<String> MODES = Set.of(
            "current-capture", "current-capture-result", "compatibility-capture",
            "compatibility-capture-result", "sql", "startup-sql", "startup");

    private static int actionEntries;
    private static final AtomicInteger PHYSICAL_BUSINESS_EXECUTIONS = new AtomicInteger();
    private static boolean datasourceConstructionEntered;
    private static List<String> businessRows = List.of();
    private static Map<String, Object> captureSnapshot;
    private static Object resultValue;
    private static Map<String, Object> verifiedRuntimeIdentity;

    private CurrentEntrySuccessorProbe() { }

    public static void main(final String[] args) throws Exception {
        if (args.length != 3 || !MODES.contains(args[0])) {
            throw new IllegalArgumentException("Expected supported mode, result file, and MySQL port (0 without SQL)");
        }
        String mode = args[0];
        int port = Integer.parseInt(args[2]);
        boolean sqlMode = "sql".equals(mode) || "startup-sql".equals(mode);
        if ((sqlMode && (port < 1 || port > 65535)) || (!sqlMode && port != 0)) {
            throw new IllegalArgumentException("SQL modes require a valid MySQL port; all other modes require 0");
        }

        boolean returned = false;
        boolean linkageFailure = false;
        List<String> exceptionClasses = new ArrayList<>();
        List<String> exceptionMessages = new ArrayList<>();
        List<String> stackFrames = new ArrayList<>();
        try {
            switch (mode) {
                case "current-capture" -> captureSnapshot = snapshot(RouteContract.capture(
                        "a29-current-capture", () -> actionEntries++));
                case "current-capture-result" -> {
                    CapturedResult<String> captured = RouteContract.captureResult("a29-current-capture-result", () -> {
                        actionEntries++;
                        return SENTINEL;
                    });
                    captureSnapshot = snapshot(captured.snapshot());
                    resultValue = captured.value();
                }
                case "compatibility-capture" -> captureSnapshot = snapshot(
                        io.github.ym0506.routecontract.RouteContract.capture(
                                "a29-compatibility-capture", () -> actionEntries++));
                case "compatibility-capture-result" -> {
                    CapturedResult<String> captured = io.github.ym0506.routecontract.RouteContract.captureResult(
                            "a29-compatibility-capture-result", () -> {
                                actionEntries++;
                                return SENTINEL;
                            });
                    captureSnapshot = snapshot(captured.snapshot());
                    resultValue = captured.value();
                }
                case "sql" -> sql(port, false);
                case "startup-sql" -> {
                    // Full startup verification precedes any fixture SQL or datasource construction.
                    verifiedRuntimeIdentity = identity(RouteContract.verifyRuntime());
                    sql(port, true);
                }
                case "startup" -> verifiedRuntimeIdentity = identity(RouteContract.verifyRuntime());
                default -> throw new IllegalArgumentException("Unsupported mode");
            }
            returned = true;
        } catch (Throwable failure) {
            failure.printStackTrace(System.out);
            Set<Throwable> seen = Collections.newSetFromMap(new IdentityHashMap<>());
            for (Throwable cursor = failure; cursor != null && seen.add(cursor); cursor = cursor.getCause()) {
                exceptionClasses.add(cursor.getClass().getName());
                exceptionMessages.add(String.valueOf(cursor.getMessage()));
                linkageFailure |= cursor instanceof LinkageError;
                for (StackTraceElement frame : cursor.getStackTrace()) {
                    stackFrames.add(frame.getClassName() + "." + frame.getMethodName());
                }
            }
        }

        // Class origins and package version are inspected only after the tested path has completed.
        ClassLoader loader = CurrentEntrySuccessorProbe.class.getClassLoader();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("mode", mode);
        result.put("pid", ProcessHandle.current().pid());
        result.put("javaVersion", System.getProperty("java.version"));
        result.put("shardingSphereVersion", Class.forName(
                "org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook", false, loader)
                .getPackage().getImplementationVersion());
        result.put("newEntryOrigin", origin(RouteContract.class));
        result.put("compatibilityEntryOrigin", origin(Class.forName(
                "io.github.ym0506.routecontract.RouteContract", false, loader)));
        result.put("guardOrigin", origin(Class.forName(
                "io.github.ym0506.routecontract.internal.CurrentRuntimeGuard", false, loader)));
        result.put("captureRegistryOrigin", origin(Class.forName(
                "io.github.ym0506.routecontract.internal.CaptureRegistry", false, loader)));
        result.put("returned", returned);
        result.put("actionEntries", actionEntries);
        result.put("actionEntered", actionEntries != 0);
        result.put("physicalBusinessExecutions", PHYSICAL_BUSINESS_EXECUTIONS.get());
        result.put("businessRows", businessRows);
        result.put("datasourceConstructionEntered", datasourceConstructionEntered);
        result.put("captureSnapshot", captureSnapshot);
        result.put("resultValue", resultValue);
        result.put("verifiedRuntimeIdentity", verifiedRuntimeIdentity);
        result.put("exceptionClasses", exceptionClasses);
        result.put("exceptionMessages", exceptionMessages);
        result.put("stackFrames", stackFrames);
        result.put("linkageFailure", linkageFailure);
        result.put("boundary", "The driver counter covers only the fixed synchronous business PreparedStatement, "
                + "immediately before actual MySQL delegation. Direct schema setup and datasource metadata SQL "
                + "are outside that counter. Hook evidence does not establish transaction commit or business success.");
        new ObjectMapper().writerWithDefaultPrettyPrinter().writeValue(Path.of(args[1]).toFile(), result);
        // A failed datasource can leave background executors alive; retain evidence before terminating this cell.
        System.exit(0);
    }

    private static Map<String, Object> snapshot(final RouteSnapshot value) {
        return Map.of("schemaVersion", value.schemaVersion(), "status", value.status().name(),
                "observedPhysicalAttemptCount", value.observedPhysicalAttemptCount(),
                "collectorDiagnostics", value.collectorDiagnostics(), "runtimeIdentity", identity(value.runtimeIdentity()));
    }

    private static Map<String, Object> identity(final ShardingSphereRuntimeIdentity value) {
        return Map.of("adapterId", value.adapterId(), "adapterContractVersion", value.adapterContractVersion(),
                "infraExecutorImplementationVersion", value.infraExecutorImplementationVersion(),
                "infraSpiImplementationVersion", value.infraSpiImplementationVersion());
    }

    private static String origin(final Class<?> type) throws Exception {
        return Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toString();
    }

    private static void sql(final int port, final boolean captureQuery) throws Exception {
        String url = "jdbc:mysql://127.0.0.1:" + port + "/routecontract_a29?allowPublicKeyRetrieval=true&useSSL=false";
        // Direct fixture initialization is separate from ShardingSphere and the observed business query.
        try (Connection physical = DriverManager.getConnection(url, "root", "");
             Statement setup = physical.createStatement()) {
            setup.executeUpdate("CREATE TABLE IF NOT EXISTS t_a29_order (order_id BIGINT PRIMARY KEY, user_id BIGINT, status VARCHAR(20))");
            setup.executeUpdate("DELETE FROM t_a29_order");
            setup.executeUpdate("INSERT INTO t_a29_order VALUES (201, 3, 'PAID')");
        }
        String yaml = """
                mode:
                  type: Standalone
                dataSources:
                  ds_0:
                    dataSourceClassName: com.zaxxer.hikari.HikariDataSource
                    driverClassName: io.github.ym0506.routecontract.consumer.CurrentEntrySuccessorProbe$ObservedDriver
                    jdbcUrl: 'MYSQL_URL'
                    username: root
                    password: ''
                rules:
                  - !SHARDING
                    tables:
                      t_a29_order:
                        actualDataNodes: ds_0.t_a29_order
                        databaseStrategy:
                          standard:
                            shardingColumn: user_id
                            shardingAlgorithmName: one_database
                    shardingAlgorithms:
                      one_database:
                        type: INLINE
                        props:
                          algorithm-expression: ds_${user_id % 1}
                props:
                  sql-show: false
                  executor-size: 2
                """.replace("MYSQL_URL", url);
        datasourceConstructionEntered = true;
        DataSource datasource = YamlShardingSphereDataSourceFactory.createDataSource(yaml.getBytes(StandardCharsets.UTF_8));
        try {
            if (captureQuery) {
                // Datasource construction and schema setup intentionally precede the named capture.
                CapturedResult<List<String>> captured = RouteContract.captureResult("a29-business-query", () -> {
                    actionEntries++;
                    return businessQuery(datasource);
                });
                captureSnapshot = snapshot(captured.snapshot());
                resultValue = captured.value();
            } else {
                businessQuery(datasource);
            }
        } finally {
            if (datasource instanceof AutoCloseable closeable) {
                closeable.close();
            }
        }
    }

    private static List<String> businessQuery(final DataSource datasource) throws SQLException {
        try (Connection connection = datasource.getConnection();
             PreparedStatement query = connection.prepareStatement(
                     "SELECT order_id, user_id, status FROM t_a29_order WHERE user_id = ? AND status = ?")) {
            query.setLong(1, 3L);
            query.setString(2, "PAID");
            try (ResultSet result = query.executeQuery()) {
                List<String> actual = new ArrayList<>();
                while (result.next()) {
                    actual.add(result.getLong("order_id") + ":" + result.getLong("user_id") + ":" + result.getString("status"));
                }
                businessRows = List.copyOf(actual);
                return businessRows;
            }
        }
    }

    /** Counts the fixed business execute call before delegating to the actual MySQL driver. */
    public static final class ObservedDriver implements Driver {
        private final Driver delegate;

        public ObservedDriver() throws ReflectiveOperationException {
            delegate = (Driver) Class.forName("com.mysql.cj.jdbc.Driver").getConstructor().newInstance();
        }

        @Override
        public Connection connect(final String url, final Properties properties) throws SQLException {
            Connection connection = delegate.connect(url, properties);
            if (connection == null) {
                return null;
            }
            return (Connection) Proxy.newProxyInstance(getClass().getClassLoader(), new Class<?>[]{Connection.class},
                    (proxy, method, args) -> {
                        Object value = invoke(connection, method, args);
                        if (value instanceof PreparedStatement statement && args != null && args.length > 0
                                && args[0] instanceof String sql) {
                            return Proxy.newProxyInstance(getClass().getClassLoader(), new Class<?>[]{PreparedStatement.class},
                                    (statementProxy, statementMethod, statementArgs) -> {
                                        if (statementMethod.getName().startsWith("execute") && isBusiness(sql)) {
                                            PHYSICAL_BUSINESS_EXECUTIONS.incrementAndGet();
                                        }
                                        return invoke(statement, statementMethod, statementArgs);
                                    });
                        }
                        return value;
                    });
        }

        private static boolean isBusiness(final String sql) {
            String normalized = sql.toLowerCase(Locale.ROOT);
            return normalized.contains("order_id") && normalized.contains("t_a29_order") && normalized.contains("where");
        }

        private static Object invoke(final Object target, final Method method, final Object[] args) throws Throwable {
            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException failure) {
                throw failure.getCause();
            }
        }

        @Override public boolean acceptsURL(final String url) throws SQLException { return delegate.acceptsURL(url); }
        @Override public DriverPropertyInfo[] getPropertyInfo(final String url, final Properties props) throws SQLException {
            return delegate.getPropertyInfo(url, props);
        }
        @Override public int getMajorVersion() { return delegate.getMajorVersion(); }
        @Override public int getMinorVersion() { return delegate.getMinorVersion(); }
        @Override public boolean jdbcCompliant() { return delegate.jdbcCompliant(); }
        @Override public Logger getParentLogger() { return Logger.getLogger("routecontract.a29"); }
    }
}
