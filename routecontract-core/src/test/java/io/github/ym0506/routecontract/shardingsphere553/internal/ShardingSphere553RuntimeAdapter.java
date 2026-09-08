package io.github.ym0506.routecontract.shardingsphere553.internal;

import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter;

/** Test-only exact-name provider used to exercise the core trust boundary without the adapter. */
public final class ShardingSphere553RuntimeAdapter implements RouteContractRuntimeAdapter {

    private static ShardingSphereRuntimeIdentity identity =
            ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3;
    private static int verifications;
    private static RuntimeException diagnostic;
    private static LinkageError linkageFailure;

    /** Resets the deterministic test provider state. */
    public static void reset(final ShardingSphereRuntimeIdentity nextIdentity) {
        identity = nextIdentity;
        verifications = 0;
        diagnostic = null;
        linkageFailure = null;
    }

    /** Sets a deterministic guard diagnostic for the core boundary test. */
    public static void rejectWith(final RuntimeException failure) {
        diagnostic = failure;
    }

    /** Sets a deterministic linkage failure for the core boundary test. */
    public static void failLinkageWith(final LinkageError failure) {
        linkageFailure = failure;
    }

    /** Returns how many times the registry invoked the provider. */
    public static int verifications() {
        return verifications;
    }

    /** {@inheritDoc} */
    @Override
    public ShardingSphereRuntimeIdentity verifyRuntime() {
        verifications++;
        if (diagnostic != null) {
            throw diagnostic;
        }
        if (linkageFailure != null) {
            throw linkageFailure;
        }
        return identity;
    }
}
