package io.github.ym0506.routecontract.spi;

import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;

/**
 * Internal JVM service boundary implemented by one exact-version runtime adapter.
 *
 * <p>This interface is public only for {@link java.util.ServiceLoader} linkage. It is not a
 * supported application extension point.</p>
 */
public interface RouteContractRuntimeAdapter {

    /**
     * Verifies the exact runtime and provider graph, then returns its immutable identity.
     *
     * @return verified exact runtime identity
     */
    ShardingSphereRuntimeIdentity verifyRuntime();
}
