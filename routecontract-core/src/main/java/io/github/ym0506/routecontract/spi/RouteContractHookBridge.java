package io.github.ym0506.routecontract.spi;

import io.github.ym0506.routecontract.internal.CaptureRegistry;

import java.util.List;

/**
 * Narrow internal bridge through which exact-version hook adapters report callback evidence.
 *
 * <p>This type is public only so separately packaged adapter JARs can call the version-neutral
 * collector. It is not a supported application-facing API.</p>
 */
public final class RouteContractHookBridge {

    private RouteContractHookBridge() {
    }

    /**
     * Returns an inactive opaque attempt for an adapter instance before its start callback.
     *
     * @return inactive opaque attempt
     */
    public static Object noopAttempt() {
        return CaptureRegistry.noopAttemptFromAdapter();
    }

    /**
     * Starts one physical-attempt callback lifecycle.
     *
     * @param dataSourceName physical data-source name reported by the adapter
     * @param sql physical SQL reported by the adapter
     * @param parameters physical parameter values, retained only as minimized type names
     * @param trunkThread whether the adapter reported a trunk-thread callback
     * @return opaque attempt to finish through this bridge
     */
    public static Object start(
            final String dataSourceName,
            final String sql,
            final List<Object> parameters,
            final boolean trunkThread) {
        return CaptureRegistry.startAttemptFromAdapter(dataSourceName, sql, parameters, trunkThread);
    }

    /**
     * Records successful return of the exact-version hook callback.
     *
     * @param attempt opaque attempt returned by {@link #start(String, String, List, boolean)}
     */
    public static void finishCallbackReturned(final Object attempt) {
        CaptureRegistry.finishCallbackReturnedFromAdapter(attempt);
    }

    /**
     * Records a failure reported by the exact-version hook callback.
     *
     * @param attempt opaque attempt returned by {@link #start(String, String, List, boolean)}
     * @param cause callback failure reported by the adapter
     */
    public static void finishFailure(final Object attempt, final Exception cause) {
        CaptureRegistry.finishFailureFromAdapter(attempt, cause);
    }

    /**
     * Records a stable adapter diagnostic without allowing diagnostics to escape into JDBC.
     *
     * @param errorCode stable minimized diagnostic code
     */
    public static void recordDiagnostic(final String errorCode) {
        CaptureRegistry.recordCurrentErrorFromAdapter(errorCode);
    }

}
