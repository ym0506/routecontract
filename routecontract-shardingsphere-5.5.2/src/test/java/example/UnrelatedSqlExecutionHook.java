package example;

import org.apache.shardingsphere.infra.database.core.connector.ConnectionProperties;
import org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook;

import java.util.List;

/** Test-only third-party hook proving RouteContract does not claim the shared SPI slot. */
public final class UnrelatedSqlExecutionHook implements SQLExecutionHook {

    /** {@inheritDoc} */
    @Override
    public void start(
            final String dataSourceName,
            final String sql,
            final List<Object> parameters,
            final ConnectionProperties connectionProperties,
            final boolean trunkThread) {
    }

    /** {@inheritDoc} */
    @Override
    public void finishSuccess() {
    }

    /** {@inheritDoc} */
    @Override
    public void finishFailure(final Exception cause) {
    }
}
