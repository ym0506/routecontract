package io.github.ym0506.routecontract.consumer;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.ym0506.routecontract.CapturedResult;
import io.github.ym0506.routecontract.PhysicalExecutionAttempt;
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
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
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
import java.util.HexFormat;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Properties;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Logger;

/** Observes the finite ordered/classpath/module boundary without invoking a test guard or replacing product classes. */
public final class RuntimeBoundaryProbe {
    private static final Set<String> MODES = Set.of("sequence", "capture", "sql", "core-only");
    private static final AtomicInteger DRIVER_COUNT = new AtomicInteger();
    private static final List<Map<String, Object>> DRIVER_EVENTS = new CopyOnWriteArrayList<>();
    private static final List<Map<String, Object>> STEPS = new ArrayList<>();
    private static final List<Map<String, Object>> SNAPSHOTS = new ArrayList<>();

    private static volatile String currentPhase = "not-started";
    private static int actionEntries;
    private static boolean datasourceConstructionEntered;
    private static List<String> businessRows = List.of();
    private static List<String> stepRows = List.of();

    private RuntimeBoundaryProbe() { }

    public static void main(final String[] args) throws Exception {
        if (args.length != 3 || !MODES.contains(args[0])) {
            throw new IllegalArgumentException("Expected supported mode, result file, and MySQL port (0 for capture)");
        }
        String mode = args[0];
        int port = Integer.parseInt(args[2]);
        if (("capture".equals(mode) && port != 0) || (!"capture".equals(mode) && (port < 1 || port > 65535))) {
            throw new IllegalArgumentException("Capture requires port 0; SQL modes require a valid MySQL port");
        }

        boolean returned = false;
        boolean linkageFailure = false;
        List<String> exceptionClasses = new ArrayList<>();
        List<String> exceptionMessages = new ArrayList<>();
        List<String> stackFrames = new ArrayList<>();
        try {
            switch (mode) {
                case "sequence" -> sequence(port, false);
                case "core-only" -> sequence(port, true);
                case "capture" -> step("capture-rejection", () -> {
                    // The tested capture is the first RouteContract call, before any datasource or bootstrap.
                    RouteSnapshot snapshot = RouteContract.capture("boundary-capture-rejection", () -> actionEntries++);
                    SNAPSHOTS.add(snapshot(snapshot));
                });
                case "sql" -> step("ordinary-rejection", () -> {
                    // No RouteContract invocation precedes the ordinary ShardingSphere path.
                    withDatasource(port, RuntimeBoundaryProbe::businessQuery);
                });
                default -> throw new IllegalArgumentException("Unsupported mode");
            }
            returned = true;
        } catch (Throwable failure) {
            failure.printStackTrace(System.out);
            linkageFailure = containsLinkage(failure);
            Set<Throwable> seen = Collections.newSetFromMap(new IdentityHashMap<>());
            for (Throwable cursor = failure; cursor != null && seen.add(cursor); cursor = cursor.getCause()) {
                exceptionClasses.add(cursor.getClass().getName());
                exceptionMessages.add(String.valueOf(cursor.getMessage()));
                for (StackTraceElement frame : cursor.getStackTrace()) {
                    stackFrames.add(frame.getClassName() + "." + frame.getMethodName());
                }
            }
        }

        // These observations occur only after the tested path, never as a preflight substitute.
        ClassLoader loader = RuntimeBoundaryProbe.class.getClassLoader();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("mode", mode);
        result.put("pid", ProcessHandle.current().pid());
        result.put("javaVersion", System.getProperty("java.version"));
        result.put("shardingSphereVersion", Class.forName(
                "org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook", false, loader)
                .getPackage().getImplementationVersion());
        result.put("returned", returned);
        result.put("actionEntries", actionEntries);
        result.put("actionEntered", actionEntries != 0);
        result.put("driverCount", DRIVER_COUNT.get());
        result.put("datasourceConstructionEntered", datasourceConstructionEntered);
        result.put("businessRows", businessRows);
        result.put("steps", STEPS);
        result.put("snapshots", SNAPSHOTS);
        result.put("driverEvents", List.copyOf(DRIVER_EVENTS));
        result.put("types", types(loader));
        result.put("exceptionClasses", exceptionClasses);
        result.put("exceptionMessages", exceptionMessages);
        result.put("stackFrames", stackFrames);
        result.put("linkageFailure", linkageFailure);
        result.put("boundary", "Driver counts and SHA-256 fingerprints cover only the fixed business PreparedStatement, "
                + "immediately before actual MySQL delegation. Schema setup and datasource metadata SQL are excluded. "
                + "Each sequence reuses one datasource and JVM. Hook callback return does not establish transaction "
                + "commit or business success. Type/module/loader observations occur after the tested invocation.");
        new ObjectMapper().writerWithDefaultPrettyPrinter().writeValue(Path.of(args[1]).toFile(), result);
        // Rejection during datasource construction may leave ShardingSphere executors alive.
        System.exit(0);
    }

    private static void sequence(final int port, final boolean coreOnly) throws Exception {
        currentPhase = "datasource-construction";
        withDatasource(port, datasource -> {
            step("ordinary-before", () -> businessQuery(datasource));
            if (coreOnly) {
                step("capture-missing-adapter", () -> {
                    RouteSnapshot snapshot = RouteContract.capture("boundary-missing-adapter", () -> actionEntries++);
                    SNAPSHOTS.add(snapshot(snapshot));
                });
            } else {
                step("capture-first", () -> capturedQuery(datasource, "boundary-first"));
                step("ordinary-between", () -> businessQuery(datasource));
                step("capture-second", () -> capturedQuery(datasource, "boundary-second"));
            }
        });
    }

    private static void step(final String name, final StepAction action) throws Exception {
        currentPhase = name;
        int actionsBefore = actionEntries;
        int driverBefore = DRIVER_COUNT.get();
        int eventsBefore = DRIVER_EVENTS.size();
        int snapshotsBefore = SNAPSHOTS.size();
        stepRows = List.of();
        boolean returned = false;
        try {
            action.run();
            returned = true;
        } finally {
            Map<String, Object> observation = new LinkedHashMap<>();
            observation.put("name", name);
            observation.put("returned", returned);
            observation.put("actionDelta", actionEntries - actionsBefore);
            observation.put("driverDelta", DRIVER_COUNT.get() - driverBefore);
            observation.put("businessRows", stepRows);
            observation.put("driverSqlFingerprints", DRIVER_EVENTS.subList(eventsBefore, DRIVER_EVENTS.size()).stream()
                    .map(event -> event.get("sqlFingerprint")).toList());
            observation.put("snapshotIndex", SNAPSHOTS.size() == snapshotsBefore + 1 ? snapshotsBefore : null);
            // Record a failed step without catching or replacing its real thrown exception.
            STEPS.add(observation);
        }
    }

    private static void capturedQuery(final DataSource datasource, final String operationId) throws Exception {
        CapturedResult<List<String>> captured = RouteContract.captureResult(operationId, () -> {
            actionEntries++;
            return businessQuery(datasource);
        });
        SNAPSHOTS.add(snapshot(captured.snapshot()));
        if (!captured.value().equals(stepRows)) {
            throw new IllegalStateException("Captured application value differs from the actual business rows");
        }
    }

    private static Map<String, Object> snapshot(final RouteSnapshot value) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("schemaVersion", value.schemaVersion());
        result.put("runtimeIdentity", identity(value.runtimeIdentity()));
        result.put("operationId", value.operationId());
        result.put("status", value.status().name());
        result.put("observedPhysicalAttemptCount", value.observedPhysicalAttemptCount());
        result.put("callbackReturnedCount", value.callbackReturnedCount());
        result.put("callbackFailureCount", value.callbackFailureCount());
        result.put("unknownOutcomeCount", value.unknownOutcomeCount());
        result.put("trunkThreadFlagCount", value.trunkThreadFlagCount());
        result.put("workerThreadFlagCount", value.workerThreadFlagCount());
        result.put("observedDataSourceNames", value.observedDataSourceNames());
        result.put("attempts", value.attempts().stream().map(RuntimeBoundaryProbe::attempt).toList());
        result.put("collectorDiagnostics", value.collectorDiagnostics());
        return result;
    }

    private static Map<String, Object> attempt(final PhysicalExecutionAttempt value) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("observedDataSourceName", value.observedDataSourceName());
        result.put("sqlFingerprint", value.sqlFingerprint());
        result.put("parameterCount", value.parameterCount());
        result.put("parameterTypes", value.parameterTypes());
        result.put("threadRole", value.threadRole().name());
        result.put("outcome", value.outcome().name());
        result.put("reportedFailureType", value.reportedFailureType());
        return result;
    }

    private static Map<String, Object> identity(final ShardingSphereRuntimeIdentity value) {
        return Map.of("adapterId", value.adapterId(), "adapterContractVersion", value.adapterContractVersion(),
                "infraExecutorImplementationVersion", value.infraExecutorImplementationVersion(),
                "infraSpiImplementationVersion", value.infraSpiImplementationVersion());
    }

    private static Map<String, Object> types(final ClassLoader loader) {
        Map<String, String> names = new LinkedHashMap<>();
        names.put("consumer", RuntimeBoundaryProbe.class.getName());
        names.put("newEntry", "io.github.ym0506.routecontract.api.RouteContract");
        names.put("coreBridge", "io.github.ym0506.routecontract.spi.RouteContractHookBridge");
        names.put("currentGuard", "io.github.ym0506.routecontract.internal.CurrentRuntimeGuard");
        names.put("captureRegistry", "io.github.ym0506.routecontract.internal.CaptureRegistry");
        names.put("adapter552", "io.github.ym0506.routecontract.shardingsphere552.internal.ShardingSphere552RuntimeAdapter");
        names.put("adapter553", "io.github.ym0506.routecontract.shardingsphere553.internal.ShardingSphere553RuntimeAdapter");
        names.put("hook552", "io.github.ym0506.routecontract.shardingsphere552.internal.RouteContract552SqlExecutionHook");
        names.put("hook553", "io.github.ym0506.routecontract.shardingsphere553.internal.RouteContract553SqlExecutionHook");
        Map<String, Object> observations = new LinkedHashMap<>();
        names.forEach((name, binaryName) -> observations.put(name, type(binaryName, loader)));
        return observations;
    }

    private static Map<String, Object> type(final String name, final ClassLoader loader) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("className", name);
        try {
            Class<?> value = Class.forName(name, false, loader);
            ClassLoader definingLoader = value.getClassLoader();
            result.put("present", true);
            result.put("origin", value.getProtectionDomain().getCodeSource() == null ? null
                    : Path.of(value.getProtectionDomain().getCodeSource().getLocation().toURI()).toString());
            result.put("moduleName", value.getModule().getName());
            result.put("namedModule", value.getModule().isNamed());
            result.put("loaderClass", definingLoader == null ? null : definingLoader.getClass().getName());
            result.put("loaderName", definingLoader == null ? null : definingLoader.getName());
            result.put("loaderIdentity", definingLoader == null ? "bootstrap"
                    : Integer.toHexString(System.identityHashCode(definingLoader)));
        } catch (ClassNotFoundException absent) {
            result.put("present", false);
        } catch (Exception | LinkageError failure) {
            result.put("present", false);
            result.put("inspectionErrorClass", failure.getClass().getName());
            result.put("inspectionErrorMessage", String.valueOf(failure.getMessage()));
        }
        return result;
    }

    private static DataSource createDatasource(final int port) throws Exception {
        String url = "jdbc:mysql://127.0.0.1:" + port
                + "/routecontract_runtime_boundaries?allowPublicKeyRetrieval=true&useSSL=false";
        // Direct physical setup is outside the wrapping driver and the business-operation evidence.
        try (Connection physical = DriverManager.getConnection(url, "root", "");
             Statement setup = physical.createStatement()) {
            setup.executeUpdate("CREATE TABLE IF NOT EXISTS t_boundary_order (order_id BIGINT PRIMARY KEY, user_id BIGINT, status VARCHAR(20))");
            setup.executeUpdate("DELETE FROM t_boundary_order");
            setup.executeUpdate("INSERT INTO t_boundary_order VALUES (201, 3, 'PAID')");
        }
        String yaml = """
                mode:
                  type: Standalone
                dataSources:
                  ds_0:
                    dataSourceClassName: com.zaxxer.hikari.HikariDataSource
                    driverClassName: io.github.ym0506.routecontract.consumer.RuntimeBoundaryProbe$ObservedDriver
                    jdbcUrl: 'MYSQL_URL'
                    username: root
                    password: ''
                rules:
                  - !SHARDING
                    tables:
                      t_boundary_order:
                        actualDataNodes: ds_0.t_boundary_order
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
        return YamlShardingSphereDataSourceFactory.createDataSource(yaml.getBytes(StandardCharsets.UTF_8));
    }

    private static void withDatasource(final int port, final DatasourceAction action) throws Exception {
        DataSource datasource = createDatasource(port);
        Throwable primaryFailure = null;
        try {
            action.run(datasource);
        } catch (Exception | Error failure) {
            primaryFailure = failure;
            throw failure;
        } finally {
            currentPhase = "datasource-close";
            if (datasource instanceof AutoCloseable closeable) {
                try {
                    closeable.close();
                } catch (Exception | Error closingFailure) {
                    if (primaryFailure == null) {
                        throw closingFailure;
                    }
                    // Preserve the tested rejection if cleanup independently fails.
                    primaryFailure.addSuppressed(closingFailure);
                }
            }
        }
    }

    private static boolean containsLinkage(final Throwable failure) {
        Set<Throwable> seen = Collections.newSetFromMap(new IdentityHashMap<>());
        List<Throwable> pending = new ArrayList<>(List.of(failure));
        for (int index = 0; index < pending.size(); index++) {
            Throwable current = pending.get(index);
            if (!seen.add(current)) {
                continue;
            }
            if (current instanceof LinkageError) {
                return true;
            }
            if (current.getCause() != null) {
                pending.add(current.getCause());
            }
            Collections.addAll(pending, current.getSuppressed());
        }
        return false;
    }

    private static List<String> businessQuery(final DataSource datasource) throws SQLException {
        try (Connection connection = datasource.getConnection();
             PreparedStatement query = connection.prepareStatement(
                     "SELECT order_id, user_id, status FROM t_boundary_order WHERE user_id = ? AND status = ?")) {
            query.setLong(1, 3L);
            query.setString(2, "PAID");
            try (ResultSet rows = query.executeQuery()) {
                List<String> actual = new ArrayList<>();
                while (rows.next()) {
                    actual.add(rows.getLong("order_id") + ":" + rows.getLong("user_id") + ":" + rows.getString("status"));
                }
                businessRows = List.copyOf(actual);
                stepRows = businessRows;
                return businessRows;
            }
        }
    }

    @FunctionalInterface
    private interface StepAction {
        void run() throws Exception;
    }

    @FunctionalInterface
    private interface DatasourceAction {
        void run(DataSource datasource) throws Exception;
    }

    /** Counts and fingerprints the fixed business statement immediately before actual MySQL delegation. */
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
                                            DRIVER_COUNT.incrementAndGet();
                                            DRIVER_EVENTS.add(Map.of("phase", currentPhase, "sqlFingerprint", sha256(sql)));
                                        }
                                        return invoke(statement, statementMethod, statementArgs);
                                    });
                        }
                        return value;
                    });
        }

        private static String sha256(final String sql) throws NoSuchAlgorithmException {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(sql.getBytes(StandardCharsets.UTF_8)));
        }

        private static boolean isBusiness(final String sql) {
            String normalized = sql.toLowerCase(Locale.ROOT);
            return normalized.contains("order_id") && normalized.contains("t_boundary_order") && normalized.contains("where");
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
        @Override public Logger getParentLogger() { return Logger.getLogger("routecontract.runtime-boundaries"); }
    }
}
