package io.github.ym0506.routecontract;

/**
 * Supplier that may throw a checked exception.
 *
 * @param <T> supplied value type
 */
@FunctionalInterface
public interface ThrowingSupplier<T> {
    /**
     * Produces the application result.
     *
     * @return supplied result
     * @throws Exception when the result cannot be produced
     */
    T get() throws Exception;
}
