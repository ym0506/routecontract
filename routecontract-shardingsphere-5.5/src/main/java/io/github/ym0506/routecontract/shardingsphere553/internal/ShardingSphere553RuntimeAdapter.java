package io.github.ym0506.routecontract.shardingsphere553.internal;

import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter;

/** Core runtime-adapter provider for exact Apache ShardingSphere-JDBC 5.5.3. */
public final class ShardingSphere553RuntimeAdapter implements RouteContractRuntimeAdapter {

    /** Creates the provider instance used by the core-defining service loader. */
    public ShardingSphere553RuntimeAdapter() {
    }

    /** {@inheritDoc} */
    @Override
    public ShardingSphereRuntimeIdentity verifyRuntime() {
        return ShardingSphere553Preflight.verify();
    }
}
