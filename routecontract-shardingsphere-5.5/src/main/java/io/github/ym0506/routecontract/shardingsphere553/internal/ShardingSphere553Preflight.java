package io.github.ym0506.routecontract.shardingsphere553.internal;

import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook;
import org.apache.shardingsphere.infra.spi.ShardingSphereServiceLoader;

import java.util.Collection;
import java.util.ServiceConfigurationError;

/** Fail-closed compatibility and SPI discovery check for the only supported runtime. */
final class ShardingSphere553Preflight {

    static final String SUPPORTED_VERSION = "5.5.3";
    private static final String ROUTECONTRACT_NAMESPACE = "io.github.ym0506.routecontract.";
    private static final String EXACT_HOOK = RouteContract553SqlExecutionHook.class.getName();
    private static final String LEGACY_HOOK =
            "io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook";

    private ShardingSphere553Preflight() {
    }

    static ShardingSphereRuntimeIdentity verify() {
        ShardingSphere553HookConstructionGuard.verify();
        verifyExactVersion("shardingsphere-infra-executor", implementationVersion(SQLExecutionHook.class));
        verifyExactVersion("shardingsphere-infra-spi", implementationVersion(ShardingSphereServiceLoader.class));
        verifyProviderDiscovery(discoverProviders());
        return ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3;
    }

    static void verifyExactVersion(final String component, final String detectedVersion) {
        if (!SUPPORTED_VERSION.equals(detectedVersion)) {
            String renderedVersion = detectedVersion == null ? "<unavailable>" : detectedVersion;
            throw new IllegalStateException(
                    "RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME: RouteContract supports exactly Apache ShardingSphere "
                            + SUPPORTED_VERSION
                            + "; " + component + " reported " + renderedVersion);
        }
    }

    static void verifyProviderDiscovery(final Collection<SQLExecutionHook> providers) {
        long legacyProviders = providers.stream()
                .filter(provider -> provider.getClass().getName().equals(LEGACY_HOOK))
                .count();
        if (legacyProviders != 0) {
            throw new IllegalStateException(
                    "RC_LEGACY_ADAPTER_COLLISION: ShardingSphere cached a pre-0.2 RouteContract hook");
        }
        Collection<SQLExecutionHook> routeContractProviders = providers.stream()
                .filter(provider -> provider.getClass().getName().startsWith(ROUTECONTRACT_NAMESPACE))
                .toList();
        boolean foreignExactCopy = routeContractProviders.stream()
                .anyMatch(provider -> provider.getClass().getName().equals(EXACT_HOOK)
                        && provider.getClass() != RouteContract553SqlExecutionHook.class);
        if (foreignExactCopy) {
            throw new IllegalStateException(
                    "RC_ADAPTER_CLASSLOADER_MISMATCH: cached exact-name hook has a foreign class identity");
        }
        if (routeContractProviders.isEmpty()) {
            throw new IllegalStateException(
                    "RC_SHARDINGSPHERE_PROVIDER_NOT_ACTIVE: matching RouteContract hook is not active");
        }
        if (routeContractProviders.size() != 1
                || routeContractProviders.iterator().next().getClass()
                        != RouteContract553SqlExecutionHook.class) {
            throw new IllegalStateException(
                    "RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS: ShardingSphere cached an unexpected RouteContract hook set");
        }
    }

    private static Collection<SQLExecutionHook> discoverProviders() {
        try {
            return ShardingSphereServiceLoader.getServiceInstances(SQLExecutionHook.class);
        } catch (RuntimeException | ServiceConfigurationError | LinkageError exception) {
            throw new IllegalStateException(
                    "RC_ADAPTER_CLASSLOADER_MISMATCH: ShardingSphere hook providers could not be linked",
                    exception);
        }
    }

    private static String implementationVersion(final Class<?> runtimeType) {
        Package runtimePackage = runtimeType.getPackage();
        return runtimePackage == null ? null : runtimePackage.getImplementationVersion();
    }
}
