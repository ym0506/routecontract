package io.github.ym0506.routecontract.internal;

import org.apache.shardingsphere.database.connector.core.jdbcurl.parser.ConnectionProperties;
import org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook;

import java.util.List;

/**
 * ShardingSphere 5.5.3 SPI provider that contains RouteContract collector runtime failures.
 *
 * <p>The provider records callback evidence only while a RouteContract scope is active. In the
 * exact supported runtime, {@code finishSuccess} is reported after the wrapped physical
 * {@code executeSQL} call returns. It does not establish completion of the enclosing executor
 * callback or application action, transaction commit, or application-level success.</p>
 */
public final class RouteContractSqlExecutionHook implements SQLExecutionHook {

    // ShardingSphere 5.5.3 creates a fresh non-singleton provider for each physical callback
    // lifecycle and invokes start/finish on that same instance. Exact-version preflight and
    // integration tests guard this instance-field pairing assumption.
    private AttemptHandle inFlight = AttemptHandle.noop();
    private Lifecycle lifecycle = Lifecycle.NEW;

    /** Creates the per-physical-execution SPI provider instance expected by ShardingSphere 5.5.3. */
    public RouteContractSqlExecutionHook() {
    }

    /** {@inheritDoc} */
    @Override
    public void start(
            final String dataSourceName,
            final String sql,
            final List<Object> parameters,
            final ConnectionProperties connectionProperties,
            final boolean trunkThread) {
        if (lifecycle != Lifecycle.NEW) {
            recordDiagnostic(lifecycle == Lifecycle.STARTED
                    ? "RC_START_WHILE_ATTEMPT_ACTIVE"
                    : "RC_START_AFTER_FINISH");
            return;
        }
        lifecycle = Lifecycle.STARTED;
        try {
            inFlight = CaptureRegistry.startAttempt(dataSourceName, sql, parameters, trunkThread);
        } catch (RuntimeException exception) {
            recordDiagnostic("RC_HOOK_START_FAILURE");
            inFlight = AttemptHandle.noop();
        }
    }

    /** {@inheritDoc} */
    @Override
    public void finishSuccess() {
        if (!beginFinish()) {
            return;
        }
        try {
            CaptureRegistry.finishCallbackReturned(inFlight);
        } catch (RuntimeException exception) {
            recordDiagnostic("RC_HOOK_FINISH_FAILURE");
        } finally {
            inFlight = AttemptHandle.noop();
        }
    }

    /** {@inheritDoc} */
    @Override
    public void finishFailure(final Exception cause) {
        if (!beginFinish()) {
            return;
        }
        try {
            CaptureRegistry.finishFailure(inFlight, cause);
        } catch (RuntimeException exception) {
            recordDiagnostic("RC_HOOK_FINISH_FAILURE");
        } finally {
            inFlight = AttemptHandle.noop();
        }
    }

    private boolean beginFinish() {
        if (lifecycle == Lifecycle.NEW) {
            lifecycle = Lifecycle.FINISHED;
            recordDiagnostic("RC_ORPHAN_FINISH");
            return false;
        }
        if (lifecycle == Lifecycle.FINISHED) {
            recordDiagnostic("RC_DUPLICATE_FINISH");
            return false;
        }
        lifecycle = Lifecycle.FINISHED;
        return true;
    }

    private static void recordDiagnostic(final String errorCode) {
        try {
            CaptureRegistry.recordCurrentError(errorCode);
        } catch (RuntimeException ignored) {
            // A diagnostics-path failure must not alter the JDBC callback result.
        }
    }

    private enum Lifecycle {
        NEW,
        STARTED,
        FINISHED
    }
}
