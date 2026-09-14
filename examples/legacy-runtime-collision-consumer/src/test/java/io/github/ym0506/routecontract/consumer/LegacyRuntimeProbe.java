package io.github.ym0506.routecontract.consumer;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.ThrowingRunnable;
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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.logging.Logger;

/** A fresh process exercises the normal API; it never invokes a guard itself. */
public final class LegacyRuntimeProbe {
    private static boolean actionEntered;
    private static int physicalBusinessExecutions;
    private static List<String> rows = List.of();
    private static Map<String, Object> captureSnapshot;

    private LegacyRuntimeProbe() { }

    public static void main(final String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException("Expected mode, result file and MySQL port (0 for capture)");
        }
        String mode = args[0];
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("mode", mode);
        result.put("pid", ProcessHandle.current().pid());
        result.put("javaVersion", System.getProperty("java.version"));
        result.put("routeContractOrigin", origin(RouteContract.class));
        result.put("captureRegistryOrigin", origin(Class.forName(
                "io.github.ym0506.routecontract.internal.CaptureRegistry", false,
                LegacyRuntimeProbe.class.getClassLoader())));
        List<String> exceptionClasses = new ArrayList<>();
        List<String> exceptionMessages = new ArrayList<>();
        boolean returned = false;
        boolean linkageFailure = false;
        try {
            if ("capture".equals(mode)) {
                // This must remain the first RouteContract call, before datasource/SPI setup.
                var snapshot = RouteContract.capture("a28-capture-sentinel", (ThrowingRunnable) () -> actionEntered = true);
                captureSnapshot = Map.of("status", snapshot.status().name(),
                        "observedPhysicalAttemptCount", snapshot.observedPhysicalAttemptCount(),
                        "collectorDiagnostics", snapshot.collectorDiagnostics());
            } else if ("sql".equals(mode)) {
                sql(Integer.parseInt(args[2]));
            } else {
                throw new IllegalArgumentException("Unknown probe mode");
            }
            returned = true;
        } catch (Throwable failure) {
            failure.printStackTrace(System.out);
            for (Throwable cursor = failure; cursor != null; cursor = cursor.getCause()) {
                exceptionClasses.add(cursor.getClass().getName());
                linkageFailure |= cursor instanceof LinkageError;
                exceptionMessages.add(String.valueOf(cursor.getMessage()));
                if (cursor == cursor.getCause()) {
                    break;
                }
            }
        }
        result.put("returned", returned);
        result.put("linkageFailure", linkageFailure);
        result.put("actionEntered", actionEntered);
        result.put("physicalBusinessExecutions", physicalBusinessExecutions);
        result.put("businessRows", rows);
        result.put("captureSnapshot", captureSnapshot);
        result.put("exceptionClasses", exceptionClasses);
        result.put("exceptionMessages", exceptionMessages);
        new ObjectMapper().writerWithDefaultPrettyPrinter().writeValue(Path.of(args[1]).toFile(), result);
        // Exit after evidence, even if a failed datasource initialized executor threads.
        System.exit(0);
    }

    private static String origin(final Class<?> type) throws Exception {
        return Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toString();
    }

    private static void sql(final int port) throws Exception {
        String url = "jdbc:mysql://127.0.0.1:" + port + "/routecontract_a28?allowPublicKeyRetrieval=true&useSSL=false";
        // Setup is direct physical JDBC, outside the observed business execution.
        try (Connection physical = DriverManager.getConnection(url, "root", "");
             Statement setup = physical.createStatement()) {
            setup.executeUpdate("CREATE TABLE IF NOT EXISTS t_a28_order (order_id BIGINT PRIMARY KEY, user_id BIGINT, status VARCHAR(20))");
            setup.executeUpdate("DELETE FROM t_a28_order");
            setup.executeUpdate("INSERT INTO t_a28_order VALUES (201, 3, 'PAID')");
        }
        String yaml = """
                mode:
                  type: Standalone
                dataSources:
                  ds_0:
                    dataSourceClassName: com.zaxxer.hikari.HikariDataSource
                    driverClassName: io.github.ym0506.routecontract.consumer.LegacyRuntimeProbe$ObservedDriver
                    jdbcUrl: 'MYSQL_URL'
                    username: root
                    password: ''
                rules:
                  - !SHARDING
                    tables:
                      t_a28_order:
                        actualDataNodes: ds_0.t_a28_order
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
        DataSource datasource = YamlShardingSphereDataSourceFactory.createDataSource(yaml.getBytes(StandardCharsets.UTF_8));
        try {
            try (Connection connection = datasource.getConnection();
                 PreparedStatement query = connection.prepareStatement(
                         "SELECT order_id, user_id, status FROM t_a28_order WHERE user_id = ? AND status = ?")) {
                query.setLong(1, 3L);
                query.setString(2, "PAID");
                try (ResultSet result = query.executeQuery()) {
                    List<String> actual = new ArrayList<>();
                    while (result.next()) {
                        actual.add(result.getLong("order_id") + ":" + result.getLong("user_id") + ":" + result.getString("status"));
                    }
                    rows = List.copyOf(actual);
                }
            }
        } finally {
            if (datasource instanceof AutoCloseable closeable) {
                closeable.close();
            }
        }
    }

    /** Delegates to the actual MySQL driver, recording execution before delegation. */
    public static final class ObservedDriver implements Driver {
        private final Driver delegate;

        public ObservedDriver() throws ReflectiveOperationException {
            delegate = (Driver) Class.forName("com.mysql.cj.jdbc.Driver").getConstructor().newInstance();
        }

        @Override
        public Connection connect(final String url, final Properties properties) throws SQLException {
            Connection connection = delegate.connect(url, properties);
            return (Connection) Proxy.newProxyInstance(getClass().getClassLoader(), new Class<?>[]{Connection.class},
                    (proxy, method, args) -> {
                        Object value = invoke(connection, method, args);
                        if (value instanceof PreparedStatement statement && args != null && args[0] instanceof String sql) {
                            return Proxy.newProxyInstance(getClass().getClassLoader(), new Class<?>[]{PreparedStatement.class},
                                    (statementProxy, statementMethod, statementArgs) -> {
                                        if (statementMethod.getName().startsWith("execute") && isBusiness(sql)) {
                                            physicalBusinessExecutions++;
                                        }
                                        return invoke(statement, statementMethod, statementArgs);
                                    });
                        }
                        return value;
                    });
        }

        private static boolean isBusiness(final String sql) {
            String normalized = sql.toLowerCase(java.util.Locale.ROOT);
            return normalized.contains("order_id") && normalized.contains("t_a28_order") && normalized.contains("where");
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
        @Override public Logger getParentLogger() { return Logger.getLogger("routecontract.a28"); }
    }
}
