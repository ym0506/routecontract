package io.github.ym0506.routecontract.internal;

import org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook;
import org.apache.shardingsphere.infra.spi.ShardingSphereServiceLoader;

import java.util.Collection;
import java.util.ServiceConfigurationError;

/** Fail-closed compatibility and SPI discovery check for the only supported runtime. */
final class ShardingSphere553Preflight {

    static final String SUPPORTED_VERSION = "5.5.3";

    private static volatile boolean verified;

    private ShardingSphere553Preflight() {
    }

    static void verify() {
        if (verified) {
            return;
        }
        synchronized (ShardingSphere553Preflight.class) {
            if (verified) {
                return;
            }
            verifyExactVersion("shardingsphere-infra-executor", implementationVersion(SQLExecutionHook.class));
            verifyExactVersion("shardingsphere-infra-spi", implementationVersion(ShardingSphereServiceLoader.class));
            verifyProviderDiscovery(discoverProviders());
            verified = true;
        }
    }

    static void verifyExactVersion(final String component, final String detectedVersion) {
        if (!SUPPORTED_VERSION.equals(detectedVersion)) {
            String renderedVersion = detectedVersion == null ? "<unavailable>" : detectedVersion;
            throw new IllegalStateException(
                    "RouteContract supports exactly Apache ShardingSphere " + SUPPORTED_VERSION
                            + "; " + component + " reported " + renderedVersion);
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

    private static String implementationVersion(final Class<?> runtimeType) {
        Package runtimePackage = runtimeType.getPackage();
        return runtimePackage == null ? null : runtimePackage.getImplementationVersion();
    }
}
