package io.github.ym0506.routecontract.shardingsphere552.internal;

import org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook;
import org.apache.shardingsphere.infra.spi.ShardingSphereServiceLoader;

/** Child-process entry point that exercises ShardingSphere's real hook provider discovery path. */
public final class FreshJvmProviderDiscoveryProbe {

    private FreshJvmProviderDiscoveryProbe() {
    }

    /** Loads the hook provider set and accepts only the requested stable RouteContract marker. */
    public static void main(final String[] arguments) {
        if (arguments.length != 1) {
            throw new IllegalArgumentException("exactly one expected marker is required");
        }
        String expectedMarker = arguments[0];
        try {
            ShardingSphereServiceLoader.getServiceInstances(SQLExecutionHook.class);
        } catch (Throwable failure) {
            Throwable current = failure;
            while (current != null) {
                if (current.getMessage() != null
                        && current.getMessage().startsWith(expectedMarker + ":")) {
                    System.out.println("ROUTECONTRACT_EXPECTED_GUARD_FAILURE " + current.getMessage());
                    return;
                }
                current = current.getCause();
            }
            throw failure;
        }
        throw new AssertionError("provider discovery unexpectedly accepted the incompatible graph");
    }
}
