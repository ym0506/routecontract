package io.github.ym0506.routecontract.internal;

import org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook;
import org.apache.shardingsphere.infra.spi.ShardingSphereServiceLoader;

import java.util.Collection;
import java.util.List;
import java.util.ServiceConfigurationError;

/** Fail-closed compatibility and SPI discovery check for the exact runtimes this artifact supports. */
final class ShardingSphere541To552Preflight {

    // Each version is verified by the MySQL integration tasks in examples/mysql-5.4.1-5.5.2.
    static final List<String> SUPPORTED_VERSIONS = List.of("5.4.1", "5.5.0", "5.5.1", "5.5.2");

    private static volatile boolean verified;

    private ShardingSphere541To552Preflight() {
    }

    static void verify() {
        if (verified) {
            return;
        }
        synchronized (ShardingSphere541To552Preflight.class) {
            if (verified) {
                return;
            }
            String executorVersion = implementationVersion(SQLExecutionHook.class);
            verifySupportedVersion("shardingsphere-infra-executor", executorVersion);
            verifySameVersion("shardingsphere-infra-spi", implementationVersion(ShardingSphereServiceLoader.class),
                    executorVersion);
            verifyProviderDiscovery(discoverProviders());
            verified = true;
        }
    }

    static void verifySupportedVersion(final String component, final String detectedVersion) {
        // List.of(...).contains(null) throws, so an unavailable version is rejected explicitly.
        if (detectedVersion == null || !SUPPORTED_VERSIONS.contains(detectedVersion)) {
            throw new IllegalStateException(
                    "RouteContract routecontract-shardingsphere-5.4.1-5.5.2 supports exactly Apache ShardingSphere "
                            + String.join(", ", SUPPORTED_VERSIONS) + "; " + component + " reported "
                            + render(detectedVersion) + ". For 5.5.3 use "
                            + "io.github.ym0506.routecontract:routecontract-shardingsphere-5.5");
        }
    }

    static void verifySameVersion(final String component, final String detectedVersion, final String executorVersion) {
        if (!executorVersion.equals(detectedVersion)) {
            throw new IllegalStateException(
                    "RouteContract requires one Apache ShardingSphere version; shardingsphere-infra-executor reported "
                            + executorVersion + " but " + component + " reported " + render(detectedVersion));
        }
    }

    static void verifyProviderDiscovery(final Collection<SQLExecutionHook> providers) {
        long matchingProviders = providers.stream()
                .filter(provider -> provider.getClass() == RouteContractSqlExecutionHook.class)
                .count();
        if (matchingProviders != 1L) {
            throw new IllegalStateException(
                    "ShardingSphereServiceLoader must discover exactly one RouteContract SQLExecutionHook provider; found "
                            + matchingProviders);
        }
    }

    private static Collection<SQLExecutionHook> discoverProviders() {
        try {
            return ShardingSphereServiceLoader.getServiceInstances(SQLExecutionHook.class);
        } catch (RuntimeException | ServiceConfigurationError exception) {
            throw new IllegalStateException(
                    "ShardingSphereServiceLoader could not discover the RouteContract SQLExecutionHook provider",
                    exception);
        }
    }

    private static String render(final String version) {
        return version == null ? "<unavailable>" : version;
    }

    private static String implementationVersion(final Class<?> runtimeType) {
        Package runtimePackage = runtimeType.getPackage();
        return runtimePackage == null ? null : runtimePackage.getImplementationVersion();
    }
}
