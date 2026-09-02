package io.github.ym0506.routecontract.shardingsphere552.internal;

import io.github.ym0506.routecontract.spi.RouteContractHookBridge;
import org.apache.shardingsphere.infra.database.core.connector.ConnectionProperties;
import org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook;

import java.util.List;

/**
 * ShardingSphere 5.5.2 SPI provider that contains RouteContract collector runtime failures.
 *
 * <p>The provider records callback evidence only while a RouteContract scope is active. In the
 * exact supported runtime, {@code finishSuccess} is reported after the wrapped physical
 * {@code executeSQL} call returns. It does not establish completion of the enclosing executor
 * callback or application action, transaction commit, or application-level success.</p>
 */
public final class RouteContract552SqlExecutionHook implements SQLExecutionHook {

    // ShardingSphere 5.5.2 creates a fresh non-singleton provider for each physical callback
    // lifecycle and invokes start/finish on that same instance. Exact-version preflight and
    // integration tests guard this instance-field pairing assumption.
    private Object inFlight;
    private Lifecycle lifecycle;

    /** Creates the per-physical-execution SPI provider instance expected by ShardingSphere 5.5.2. */
    public RouteContract552SqlExecutionHook() {
        ShardingSphere552HookConstructionGuard.verify();
        inFlight = initialNoopAttempt();
        lifecycle = Lifecycle.NEW;
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
            inFlight = RouteContractHookBridge.start(dataSourceName, sql, parameters, trunkThread);
        } catch (RuntimeException | LinkageError exception) {
            recordDiagnostic("RC_HOOK_START_FAILURE");
            inFlight = safeNoopAttempt();
        }
    }

    /** {@inheritDoc} */
    @Override
    public void finishSuccess() {
        if (!beginFinish()) {
            return;
        }
        try {
            RouteContractHookBridge.finishCallbackReturned(inFlight);
        } catch (RuntimeException | LinkageError exception) {
            recordDiagnostic("RC_HOOK_FINISH_FAILURE");
        } finally {
            inFlight = safeNoopAttempt();
        }
    }

    /** {@inheritDoc} */
    @Override
    public void finishFailure(final Exception cause) {
        if (!beginFinish()) {
            return;
        }
        try {
            RouteContractHookBridge.finishFailure(inFlight, cause);
        } catch (RuntimeException | LinkageError exception) {
            recordDiagnostic("RC_HOOK_FINISH_FAILURE");
        } finally {
            inFlight = safeNoopAttempt();
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
            RouteContractHookBridge.recordDiagnostic(errorCode);
        } catch (RuntimeException | LinkageError ignored) {
            // A diagnostics-path failure must not alter the JDBC callback result.
        }
    }

    private static Object initialNoopAttempt() {
        try {
            return RouteContractHookBridge.noopAttempt();
        } catch (RuntimeException | LinkageError exception) {
            throw new IllegalStateException(
                    "RC_ADAPTER_CLASSLOADER_MISMATCH: core bridge initialization failed",
                    exception);
        }
    }

    private static Object safeNoopAttempt() {
        try {
            return RouteContractHookBridge.noopAttempt();
        } catch (RuntimeException | LinkageError exception) {
            recordDiagnostic("RC_HOOK_NOOP_FAILURE");
            return null;
        }
    }

    private enum Lifecycle {
        NEW,
        STARTED,
        FINISHED
    }
}
