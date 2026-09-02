package io.github.ym0506.routecontract.shardingsphere552.internal;

import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter;

/** Core runtime-adapter provider for exact Apache ShardingSphere-JDBC 5.5.2. */
public final class ShardingSphere552RuntimeAdapter implements RouteContractRuntimeAdapter {

    /** Creates the provider instance used by the core-defining service loader. */
    public ShardingSphere552RuntimeAdapter() {
    }

    /** {@inheritDoc} */
    @Override
    public ShardingSphereRuntimeIdentity verifyRuntime() {
        return ShardingSphere552Preflight.verify();
    }
}
