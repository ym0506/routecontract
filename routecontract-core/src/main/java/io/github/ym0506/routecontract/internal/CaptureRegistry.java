package io.github.ym0506.routecontract.internal;

import com.alibaba.ttl.TransmittableThreadLocal;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import io.github.ym0506.routecontract.ThreadRole;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

/**
 * Internal registry shared by the public capture API and the ShardingSphere SPI provider.
 *
 * <p>This type is public only so the library entry point can cross the package boundary. It is not
 * a supported application-facing API; use {@link io.github.ym0506.routecontract.RouteContract}
 * instead.</p>
 */
public final class CaptureRegistry {

    /*
     * ShardingSphere wraps submitted work with TtlExecutors. We need that
     * submission-time propagation, but not the one-time InheritableThreadLocal
     * copy when a pool thread is first created during a captured query. A null
     * child value prevents the first capture from becoming the worker's baseline.
     */
    private static final TransmittableThreadLocal<CaptureToken> CURRENT_CAPTURE = new SubmissionOnlyContext();
    private static final ConcurrentMap<CaptureToken, MutableCapture> CAPTURES = new ConcurrentHashMap<>();

    private CaptureRegistry() {
    }

    /**
     * Opens one internal capture scope after exact-runtime and SPI preflight checks.
     *
     * @param operationId non-blank opaque identifier, at most 200 Java UTF-16 code units
     * @return lifecycle scope that must be closed by the library entry point
     * @throws IllegalArgumentException when the identifier is blank or too long
     * @throws IllegalStateException when preflight fails or the current thread already owns a capture
     */
    public static CaptureScope open(final String operationId) {
        validateOperationId(operationId);
        ShardingSphereRuntimeIdentity runtimeIdentity = RuntimeAdapterRegistry.verify();
        if (CURRENT_CAPTURE.get() != null) {
            throw new IllegalStateException("Nested RouteContract captures are not supported");
        }
        CaptureToken token = CaptureToken.create();
        MutableCapture capture = new MutableCapture(operationId, runtimeIdentity);
        MutableCapture previous = CAPTURES.putIfAbsent(token, capture);
        if (previous != null) {
            throw new IllegalStateException("Capture identifier collision");
        }
        CURRENT_CAPTURE.set(token);
        return new CaptureScope(token);
    }

    static RouteSnapshot close(final CaptureToken token) {
        CaptureToken current = CURRENT_CAPTURE.get();
        MutableCapture capture = CAPTURES.get(token);
        if (capture == null) {
            throw new IllegalStateException("Capture is no longer active");
        }
        if (!token.equals(current)) {
            capture.recordError("RC_WRONG_CLOSE_CONTEXT");
        }
        CURRENT_CAPTURE.remove();
        try {
            return capture.closeAndFreeze();
        } finally {
            CAPTURES.remove(token, capture);
        }
    }

    /**
     * Starts one adapter-reported physical attempt for the public-at-the-JVM-boundary SPI bridge.
     *
     * @param dataSourceName physical data-source name reported by the adapter, or {@code null}
     * @param sql physical SQL reported by the adapter, or {@code null}
     * @param parameters parameter values used only to retain minimized runtime type names
     * @param trunkThread whether the adapter reported a trunk-thread callback
     * @return an opaque core-owned handle; callers must pass it back unchanged
     */
    public static Object startAttemptFromAdapter(
            final String dataSourceName,
            final String sql,
            final List<Object> parameters,
            final boolean trunkThread) {
        CaptureToken token = CURRENT_CAPTURE.get();
        if (token == null) {
            return AttemptHandle.noop();
        }
        MutableCapture capture = CAPTURES.get(token);
        if (capture == null) {
            return AttemptHandle.noop();
        }
        capture.recordStartCallbackObserved();
        try {
            String safeDataSourceName = dataSourceName == null ? "<unknown-data-source>" : dataSourceName;
            if (dataSourceName == null) {
                capture.recordError("RC_NULL_DATA_SOURCE_NAME");
            }
            if (sql == null) {
                capture.recordError("RC_NULL_SQL");
            }
            if (parameters == null) {
                capture.recordError("RC_NULL_PARAMETERS");
            }
            List<String> parameterTypes = parameterTypes(parameters);
            return capture.start(
                    safeDataSourceName,
                    SqlFingerprint.sha256(sql),
                    parameterTypes,
                    trunkThread ? ThreadRole.TRUNK : ThreadRole.WORKER);
        } catch (RuntimeException exception) {
            capture.recordError("RC_COLLECTOR_START_FAILURE");
            return AttemptHandle.noop();
        }
    }

    /**
     * Returns the core-owned inactive handle used before an adapter start callback.
     *
     * @return opaque inactive handle
     */
    public static Object noopAttemptFromAdapter() {
        return AttemptHandle.noop();
    }

    /**
     * Finishes an opaque adapter attempt as callback-returned.
     *
     * @param opaqueHandle core-owned handle returned by the start bridge
     */
    public static void finishCallbackReturnedFromAdapter(final Object opaqueHandle) {
        AttemptHandle handle = requireAttemptHandle(opaqueHandle);
        if (!handle.isActive()) {
            return;
        }
        try {
            handle.capture().finishCallbackReturned(handle.attempt());
        } catch (RuntimeException exception) {
            handle.capture().recordError("RC_COLLECTOR_FINISH_FAILURE");
        }
    }

    /**
     * Finishes an opaque adapter attempt as callback-failure.
     *
     * @param opaqueHandle core-owned handle returned by the start bridge
     * @param cause failure reported by the adapter
     */
    public static void finishFailureFromAdapter(final Object opaqueHandle, final Exception cause) {
        AttemptHandle handle = requireAttemptHandle(opaqueHandle);
        if (!handle.isActive()) {
            return;
        }
        try {
            handle.capture().finishFailure(handle.attempt(), cause);
        } catch (RuntimeException exception) {
            handle.capture().recordError("RC_COLLECTOR_FINISH_FAILURE");
        }
    }

    /**
     * Records a stable adapter diagnostic on the current capture, when one exists.
     *
     * @param errorCode stable minimized diagnostic code
     */
    public static void recordCurrentErrorFromAdapter(final String errorCode) {
        CaptureToken token = CURRENT_CAPTURE.get();
        if (token == null) {
            return;
        }
        MutableCapture capture = CAPTURES.get(token);
        if (capture != null) {
            capture.recordError(errorCode);
        }
    }

    private static AttemptHandle requireAttemptHandle(final Object opaqueHandle) {
        if (opaqueHandle instanceof AttemptHandle handle) {
            return handle;
        }
        throw new IllegalArgumentException(
                "RC_ADAPTER_CLASSLOADER_MISMATCH: adapter attempt handle is not owned by this core copy");
    }

    private static List<String> parameterTypes(final List<Object> parameters) {
        if (parameters == null || parameters.isEmpty()) {
            return List.of();
        }
        List<String> result = new ArrayList<>(parameters.size());
        for (Object parameter : parameters) {
            result.add(parameter == null ? "null" : parameter.getClass().getName());
        }
        return List.copyOf(result);
    }

    private static void validateOperationId(final String operationId) {
        Objects.requireNonNull(operationId, "operationId");
        if (operationId.isBlank()) {
            throw new IllegalArgumentException("operationId must not be blank");
        }
        if (operationId.length() > RouteContract.MAX_OPERATION_ID_UTF16_CODE_UNITS) {
            throw new IllegalArgumentException("operationId must not exceed "
                    + RouteContract.MAX_OPERATION_ID_UTF16_CODE_UNITS + " Java UTF-16 code units");
        }
    }

    private static final class SubmissionOnlyContext extends TransmittableThreadLocal<CaptureToken> {
        @Override
        protected CaptureToken childValue(final CaptureToken parentValue) {
            return null;
        }
    }
}
