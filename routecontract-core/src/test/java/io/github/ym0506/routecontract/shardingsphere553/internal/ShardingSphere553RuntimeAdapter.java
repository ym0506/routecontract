package io.github.ym0506.routecontract.shardingsphere553.internal;

import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter;

/** Test-only exact-name provider used to exercise the core trust boundary without the adapter. */
public final class ShardingSphere553RuntimeAdapter implements RouteContractRuntimeAdapter {

    private static ShardingSphereRuntimeIdentity identity =
            ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3;
    private static int verifications;

    /** Resets the deterministic test provider state. */
    public static void reset(final ShardingSphereRuntimeIdentity nextIdentity) {
        identity = nextIdentity;
        verifications = 0;
    }

    /** Returns how many times the registry invoked the provider. */
    public static int verifications() {
        return verifications;
    }

    /** {@inheritDoc} */
    @Override
    public ShardingSphereRuntimeIdentity verifyRuntime() {
        verifications++;
        return identity;
    }
}
