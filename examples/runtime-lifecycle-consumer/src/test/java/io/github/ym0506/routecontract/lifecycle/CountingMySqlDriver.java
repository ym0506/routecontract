package io.github.ym0506.routecontract.lifecycle;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.Driver;
import java.sql.DriverPropertyInfo;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.Statement;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Logger;

/** Counts real physical execute delegations; never emits or fabricates hook events. */
public final class CountingMySqlDriver implements Driver {
    private static final AtomicInteger EXECUTIONS = new AtomicInteger();
    private static volatile boolean measuring;
    private final Driver delegate;

    public CountingMySqlDriver() throws ReflectiveOperationException {
        delegate = (Driver) Class.forName("com.mysql.cj.jdbc.Driver")
                .getDeclaredConstructor().newInstance();
    }

    static void beginMeasurement() {
        EXECUTIONS.set(0);
        measuring = true;
    }

    static void endMeasurement() {
        measuring = false;
    }

    static int executionCount() {
        return EXECUTIONS.get();
    }

    @Override
    public Connection connect(final String url, final Properties info) throws SQLException {
        Connection actual = delegate.connect(url, info);
        if (actual == null) {
            return null;
        }
        return (Connection) Proxy.newProxyInstance(CountingMySqlDriver.class.getClassLoader(),
                new Class<?>[]{Connection.class}, (proxy, method, arguments) -> {
                    Object result = invoke(method, actual, arguments);
                    if (result instanceof CallableStatement statement) {
                        return wrapStatement(statement, CallableStatement.class);
                    }
                    if (result instanceof PreparedStatement statement) {
                        return wrapStatement(statement, PreparedStatement.class);
                    }
                    if (result instanceof Statement statement) {
                        return wrapStatement(statement, Statement.class);
                    }
                    return result;
                });
    }

    private static Object wrapStatement(final Statement statement, final Class<?> type) {
        return Proxy.newProxyInstance(CountingMySqlDriver.class.getClassLoader(), new Class<?>[]{type},
                (proxy, method, arguments) -> {
                    if (measuring && switch (method.getName()) {
                        case "execute", "executeQuery", "executeUpdate", "executeLargeUpdate",
                                "executeBatch", "executeLargeBatch" -> true;
                        default -> false;
                    }) {
                        EXECUTIONS.incrementAndGet();
                    }
                    return invoke(method, statement, arguments);
                });
    }

    private static Object invoke(final Method method, final Object target, final Object[] arguments)
            throws Throwable {
        try {
            return method.invoke(target, arguments);
        } catch (InvocationTargetException failure) {
            throw failure.getCause();
        }
    }

    @Override
    public boolean acceptsURL(final String url) throws SQLException {
        return delegate.acceptsURL(url);
    }

    @Override
    public DriverPropertyInfo[] getPropertyInfo(final String url, final Properties info) throws SQLException {
        return delegate.getPropertyInfo(url, info);
    }

    @Override
    public int getMajorVersion() {
        return delegate.getMajorVersion();
    }

    @Override
    public int getMinorVersion() {
        return delegate.getMinorVersion();
    }

    @Override
    public boolean jdbcCompliant() {
        return delegate.jdbcCompliant();
    }

    @Override
    public Logger getParentLogger() throws SQLFeatureNotSupportedException {
        return delegate.getParentLogger();
    }
}
