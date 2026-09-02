package io.github.ym0506.routecontract;

import io.github.ym0506.routecontract.internal.CaptureRegistry;
import io.github.ym0506.routecontract.internal.CaptureScope;

import java.util.Objects;

/**
 * Entry point for operation-scoped observed physical JDBC execution captures.
 *
 * <p>The action must execute synchronously inside the call. RouteContract observes
 * ShardingSphere-JDBC 5.5.3 {@code SQLExecutionHook} callbacks; it does not expose a complete route
 * plan and does not infer transaction commit or business success from callback return.</p>
 */
public final class RouteContract {

    /** Maximum physical attempts retained for one capture before it fails closed as incomplete. */
    public static final int MAX_RETAINED_ATTEMPTS_PER_CAPTURE = 10_000;

    /** Maximum caller operation-ID length measured in Java UTF-16 code units. */
    public static final int MAX_OPERATION_ID_UTF16_CODE_UNITS = 200;

    private RouteContract() {
    }

    /**
     * Runs an operation and returns its observed physical-execution evidence.
     *
     * <p>If the action throws, its original exception or error is rethrown after best-effort
     * collector cleanup, so no snapshot is returned.</p>
     *
     * @param operationId non-blank opaque identifier, at most 200 Java UTF-16 code units
     * @param action synchronous application operation to observe
     * @return immutable snapshot recorded while the action ran
     * @throws Exception when the action throws a checked or runtime exception
     * @throws IllegalArgumentException when {@code operationId} is blank or too long
     * @throws IllegalStateException when the supported runtime/SPI preflight fails or a capture is nested
     */
    public static RouteSnapshot capture(final String operationId, final ThrowingRunnable action) throws Exception {
        Objects.requireNonNull(action, "action");
        CaptureScope scope = CaptureRegistry.open(operationId);
        try {
            action.run();
        } catch (Exception exception) {
            scope.closeAfterFailure(exception);
            throw exception;
        } catch (Error error) {
            scope.closeAfterFailure(error);
            throw error;
        }
        return scope.close();
    }

    /**
     * Runs a value-producing operation and returns both its value and observed execution evidence.
     *
     * <p>If the action throws, its original exception or error is rethrown after best-effort
     * collector cleanup, so no partial result is returned.</p>
     *
     * @param operationId non-blank opaque identifier, at most 200 Java UTF-16 code units
     * @param action synchronous application operation to observe
     * @param <T> application result type
     * @return application value paired with the immutable capture snapshot
     * @throws Exception when the action throws a checked or runtime exception
     * @throws IllegalArgumentException when {@code operationId} is blank or too long
     * @throws IllegalStateException when the supported runtime/SPI preflight fails or a capture is nested
     */
    public static <T> CapturedResult<T> captureResult(
            final String operationId,
            final ThrowingSupplier<T> action) throws Exception {
        Objects.requireNonNull(action, "action");
        CaptureScope scope = CaptureRegistry.open(operationId);
        final T value;
        try {
            value = action.get();
        } catch (Exception exception) {
            scope.closeAfterFailure(exception);
            throw exception;
        } catch (Error error) {
            scope.closeAfterFailure(error);
            throw error;
        }
        return new CapturedResult<>(value, scope.close());
    }
}
