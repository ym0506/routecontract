package io.github.ym0506.routecontract;

import java.io.Serial;

/** Assertion failure produced after a capture has completed. */
public final class RouteContractViolationException extends AssertionError {
    @Serial
    private static final long serialVersionUID = 1L;

    /**
     * Creates an assertion failure with deterministic contract diagnostics.
     *
     * @param message human-readable violation message
     */
    public RouteContractViolationException(final String message) {
        super(message);
    }
}
