package io.github.ym0506.routecontract.examples.split;

import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteSnapshot;

/** Minimal classpath probe for one RouteContract 0.2 adapter and its exact runtime. */
public final class SplitArtifactConsumerProbe {

    private SplitArtifactConsumerProbe() {
    }

    /** Runs the version-specific runtime preflight through an empty capture. */
    public static void main(final String[] args) throws Exception {
        String expectedVersion = System.getProperty(
                "routecontract.expectedShardingSphereVersion");
        require(expectedVersion != null && !expectedVersion.isBlank(),
                "missing expected ShardingSphere version");

        RouteSnapshot snapshot = RouteContract.capture(
                "gradle-split-artifact-consumer-probe", () -> {
                });
        require(snapshot.operationId().equals("gradle-split-artifact-consumer-probe"),
                "capture did not run through RouteContract core");
        require(snapshot.observedPhysicalAttemptCount() == 0,
                "empty compatibility capture must contain no attempts");
        require(snapshot.runtimeIdentity().infraExecutorImplementationVersion()
                        .equals(expectedVersion),
                "unexpected executor implementation version");
        require(snapshot.runtimeIdentity().infraSpiImplementationVersion()
                        .equals(expectedVersion),
                "unexpected SPI implementation version");

        System.out.println(
                "ROUTECONTRACT_GRADLE_SPLIT_RUNTIME_VERIFIED version=" + expectedVersion);
    }

    private static void require(final boolean condition, final String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
