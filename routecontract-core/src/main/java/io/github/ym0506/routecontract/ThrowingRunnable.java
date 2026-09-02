package io.github.ym0506.routecontract;

/** Runnable that may throw a checked exception. */
@FunctionalInterface
public interface ThrowingRunnable {
    /**
     * Runs the application operation.
     *
     * @throws Exception when the operation cannot complete
     */
    void run() throws Exception;
}
