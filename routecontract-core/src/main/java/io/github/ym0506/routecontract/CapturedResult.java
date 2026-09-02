package io.github.ym0506.routecontract;

import java.util.Objects;

/**
 * Application result paired with its observed physical-execution snapshot.
 *
 * @param value value returned by the captured action
 * @param snapshot immutable evidence captured while producing the value
 * @param <T> application result type
 */
public record CapturedResult<T>(T value, RouteSnapshot snapshot) {
    /**
     * Creates an application result paired with required capture evidence.
     *
     * @param value value returned by the captured action
     * @param snapshot immutable non-null capture evidence
     */
    public CapturedResult {
        snapshot = Objects.requireNonNull(snapshot, "snapshot");
    }
}
