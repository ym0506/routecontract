package io.github.ym0506.routecontract;

/**
 * Compatibility entry point for operation-scoped observed physical JDBC execution captures.
 *
 * <p>New 0.2 applications use {@link io.github.ym0506.routecontract.api.RouteContract}.
 * Existing application bytecode may keep this entry on a clean split dependency graph. An
 * immutable pre-0.2 JAR placed first on an invalid mixed classpath can shadow this class, so
 * calls into that old bytecode cannot be guaranteed to expose current collision diagnostics.</p>
 *
 * <p>The action must execute synchronously inside the call. The exact installed 5.5.2 or 5.5.3
 * adapter observes hook-reported physical JDBC execution attempts; it does not expose a complete
 * route plan or infer transaction commit or business success.</p>
 */
public final class RouteContract {

    /** Maximum physical attempts retained for one capture before it fails closed as incomplete. */
    public static final int MAX_RETAINED_ATTEMPTS_PER_CAPTURE =
            io.github.ym0506.routecontract.api.RouteContract.MAX_RETAINED_ATTEMPTS_PER_CAPTURE;

    /** Maximum caller operation-ID length measured in Java UTF-16 code units. */
    public static final int MAX_OPERATION_ID_UTF16_CODE_UNITS =
            io.github.ym0506.routecontract.api.RouteContract.MAX_OPERATION_ID_UTF16_CODE_UNITS;

    private RouteContract() {
    }

    /**
     * Runs an operation and returns its observed physical-execution evidence.
     *
     * <p>Action exceptions and errors are rethrown unchanged after best-effort collector cleanup.</p>
     *
     * @param operationId non-blank opaque identifier, at most 200 Java UTF-16 code units
     * @param action synchronous application operation to observe
     * @return immutable snapshot recorded while the action ran
     * @throws Exception when the action throws a checked or runtime exception
     * @throws IllegalArgumentException when {@code operationId} is blank or too long
     * @throws IllegalStateException when preflight fails or a capture is nested
     */
    public static RouteSnapshot capture(final String operationId, final ThrowingRunnable action) throws Exception {
        return io.github.ym0506.routecontract.api.RouteContract.capture(operationId, action);
    }

    /**
     * Runs a value-producing operation and returns its value and observed execution evidence.
     *
     * <p>Action exceptions and errors are rethrown unchanged after best-effort collector cleanup.</p>
     *
     * @param operationId non-blank opaque identifier, at most 200 Java UTF-16 code units
     * @param action synchronous application operation to observe
     * @param <T> application result type
     * @return application value paired with the immutable capture snapshot
     * @throws Exception when the action throws a checked or runtime exception
     * @throws IllegalArgumentException when {@code operationId} is blank or too long
     * @throws IllegalStateException when preflight fails or a capture is nested
     */
    public static <T> CapturedResult<T> captureResult(
            final String operationId,
            final ThrowingSupplier<T> action) throws Exception {
        return io.github.ym0506.routecontract.api.RouteContract.captureResult(operationId, action);
    }
}
