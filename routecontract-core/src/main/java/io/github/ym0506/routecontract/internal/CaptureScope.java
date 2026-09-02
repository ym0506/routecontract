package io.github.ym0506.routecontract.internal;

import io.github.ym0506.routecontract.RouteSnapshot;

/**
 * Internal lifecycle handle used by the public one-shot capture API.
 *
 * <p>This type is not an application extension point. It is public only for the library's package
 * boundary.</p>
 */
public final class CaptureScope {

    private final CaptureToken token;
    private RouteSnapshot snapshot;

    CaptureScope(final CaptureToken token) {
        this.token = token;
    }

    /**
     * Closes the scope once and returns its frozen snapshot; later calls return the same snapshot.
     *
     * @return immutable snapshot for the operation
     */
    public synchronized RouteSnapshot close() {
        if (snapshot == null) {
            snapshot = CaptureRegistry.close(token);
        }
        return snapshot;
    }

    /**
     * Performs best-effort cleanup without replacing an action's original failure.
     *
     * @param originalFailure action failure to which a cleanup failure is added as suppressed
     */
    public void closeAfterFailure(final Throwable originalFailure) {
        try {
            close();
        } catch (RuntimeException closeFailure) {
            originalFailure.addSuppressed(closeFailure);
        }
    }
}
