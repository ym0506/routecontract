package io.github.ym0506.routecontract.examples.maven;

import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter;

import java.net.URISyntaxException;
import java.nio.file.Path;
import java.util.List;
import java.util.ServiceLoader;

/** Minimal runtime and artifact-identity probe for the Maven split-artifact fixture. */
public final class MavenSplitArtifactConsumerProbe {

    private MavenSplitArtifactConsumerProbe() {
    }

    /** Runs the selected exact adapter's preflight and checks the split artifact origins. */
    public static void main(final String[] args) throws Exception {
        String expectedShardingSphereVersion = requireProperty(
                "routecontract.expectedShardingSphereVersion");
        String expectedAdapterArtifactId = requireProperty(
                "routecontract.expectedAdapterArtifactId");
        String expectedRouteContractVersion = requireProperty(
                "routecontract.expectedVersion");

        List<RouteContractRuntimeAdapter> adapters = ServiceLoader
                .load(RouteContractRuntimeAdapter.class)
                .stream()
                .map(ServiceLoader.Provider::get)
                .toList();
        require(adapters.size() == 1,
                "Maven consumer must expose exactly one RouteContract runtime adapter");
        RouteContractRuntimeAdapter adapter = adapters.get(0);

        require(originFileName(RouteContract.class).equals(
                        "routecontract-core-" + expectedRouteContractVersion + ".jar"),
                "RouteContract public API must come from the split core JAR");
        require(originFileName(adapter.getClass()).equals(
                        expectedAdapterArtifactId + "-" + expectedRouteContractVersion + ".jar"),
                "runtime adapter must come from the selected exact adapter JAR");

        RouteSnapshot snapshot = RouteContract.capture(
                "maven-split-artifact-consumer-probe", () -> {
                });
        require(snapshot.observedPhysicalAttemptCount() == 0,
                "empty compatibility capture must contain no attempts");
        require(snapshot.runtimeIdentity().infraExecutorImplementationVersion()
                        .equals(expectedShardingSphereVersion),
                "unexpected ShardingSphere executor implementation version");
        require(snapshot.runtimeIdentity().infraSpiImplementationVersion()
                        .equals(expectedShardingSphereVersion),
                "unexpected ShardingSphere SPI implementation version");

        System.out.println("ROUTECONTRACT_MAVEN_SPLIT_RUNTIME_VERIFIED version="
                + expectedShardingSphereVersion + " adapter=" + expectedAdapterArtifactId);
    }

    private static String requireProperty(final String name) {
        String value = System.getProperty(name);
        require(value != null && !value.isBlank(), "missing system property: " + name);
        return value;
    }

    private static String originFileName(final Class<?> type) throws URISyntaxException {
        var codeSource = type.getProtectionDomain().getCodeSource();
        require(codeSource != null && "file".equals(codeSource.getLocation().getProtocol()),
                type.getName() + " must expose a file-backed code source");
        return Path.of(codeSource.getLocation().toURI()).getFileName().toString();
    }

    private static void require(final boolean condition, final String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
