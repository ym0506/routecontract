package io.github.ym0506.routecontract.internal;

import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import io.github.ym0506.routecontract.spi.RouteContractHookBridge;
import io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter;

import java.io.IOException;
import java.net.URL;
import java.security.CodeSource;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

/** Discovers exactly one version-specific runtime adapter through the core-defining loader. */
final class RuntimeAdapterRegistry {

    private static final Map<String, ShardingSphereRuntimeIdentity> EXPECTED_ADAPTER_IDENTITIES = Map.of(
            "io.github.ym0506.routecontract.shardingsphere552.internal.ShardingSphere552RuntimeAdapter",
            ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_2,
            "io.github.ym0506.routecontract.shardingsphere553.internal.ShardingSphere553RuntimeAdapter",
            ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3);
    private static final Map<String, String> EXPECTED_HOOK_CLASSES = Map.of(
            "io.github.ym0506.routecontract.shardingsphere552.internal.ShardingSphere552RuntimeAdapter",
            "io.github.ym0506.routecontract.shardingsphere552.internal.RouteContract552SqlExecutionHook",
            "io.github.ym0506.routecontract.shardingsphere553.internal.ShardingSphere553RuntimeAdapter",
            "io.github.ym0506.routecontract.shardingsphere553.internal.RouteContract553SqlExecutionHook");

    private RuntimeAdapterRegistry() {
    }

    static ShardingSphereRuntimeIdentity verify() {
        verifyUnnamedModules(
                RouteContract.class,
                RouteContractRuntimeAdapter.class,
                RouteContractHookBridge.class,
                CaptureRegistry.class);
        ServiceLoader<RouteContractRuntimeAdapter> loader = ServiceLoader.load(
                RouteContractRuntimeAdapter.class,
                RouteContract.class.getClassLoader());
        return verifyDiscovered(loader);
    }

    static void verifyUnnamedModules(final Class<?>... coreTypes) {
        for (Class<?> coreType : coreTypes) {
            if (coreType.getModule().isNamed()) {
                throw new IllegalStateException(
                        "RC_UNSUPPORTED_MODULE_PATH: RouteContract 0.2 requires the classpath");
            }
        }
    }

    static ShardingSphereRuntimeIdentity verifyDiscovered(
            final Iterable<RouteContractRuntimeAdapter> discoveredAdapters) {
        List<RouteContractRuntimeAdapter> adapters = collectAdapters(discoveredAdapters);
        if (adapters.isEmpty()) {
            throw new IllegalStateException(
                    "RC_ADAPTER_NOT_FOUND: no RouteContract runtime adapter is visible to the core classloader");
        }
        if (adapters.size() > 1) {
            throw new IllegalStateException(
                    "RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS: expected one runtime adapter; found "
                            + adapters.size());
        }
        RouteContractRuntimeAdapter adapter = adapters.get(0);
        verifyCompatibleClassLoader(adapter);
        ShardingSphereRuntimeIdentity expected = EXPECTED_ADAPTER_IDENTITIES.get(
                adapter.getClass().getName());
        if (expected == null) {
            throw new IllegalStateException(
                    "RC_UNSUPPORTED_ROUTE_CONTRACT_ADAPTER: exact 5.5.2 or 5.5.3 adapter required; observed "
                            + adapter.getClass().getName());
        }
        verifyAdapterLayout(adapter);
        ShardingSphereRuntimeIdentity result;
        try {
            result = adapter.verifyRuntime();
        } catch (LinkageError error) {
            throw new IllegalStateException(
                    "RC_ADAPTER_CLASSLOADER_MISMATCH: runtime adapter verification could not be linked",
                    error);
        }
        if (!expected.equals(result)) {
            throw new IllegalStateException(
                    "RC_ADAPTER_IDENTITY_MISMATCH: " + adapter.getClass().getName()
                            + " must verify " + expected + "; observed " + result);
        }
        return result;
    }

    private static List<RouteContractRuntimeAdapter> collectAdapters(
            final Iterable<RouteContractRuntimeAdapter> discoveredAdapters) {
        try {
            List<RouteContractRuntimeAdapter> result = new ArrayList<>();
            discoveredAdapters.forEach(result::add);
            return List.copyOf(result);
        } catch (ServiceConfigurationError | LinkageError exception) {
            throw new IllegalStateException(
                    "RC_ADAPTER_CLASSLOADER_MISMATCH: runtime-adapter service configuration could not be linked",
                    exception);
        }
    }

    private static void verifyCompatibleClassLoader(final RouteContractRuntimeAdapter adapter) {
        ClassLoader coreLoader = RouteContract.class.getClassLoader();
        if (RouteContractRuntimeAdapter.class.getClassLoader() != coreLoader
                || RouteContractHookBridge.class.getClassLoader() != coreLoader
                || CaptureRegistry.class.getClassLoader() != coreLoader
                || adapter.getClass().getClassLoader() != coreLoader) {
            throw new IllegalStateException(
                    "RC_ADAPTER_CLASSLOADER_MISMATCH: core, bridge, collector, and adapter must share one classloader");
        }
    }

    private static void verifyAdapterLayout(final RouteContractRuntimeAdapter adapter) {
        Class<?> adapterType = adapter.getClass();
        ClassLoader loader = adapterType.getClassLoader();
        if (adapterType.getModule().isNamed()) {
            throw new IllegalStateException(
                    "RC_UNSUPPORTED_MODULE_PATH: RouteContract 0.2 requires the classpath");
        }
        verifyUniqueDefinition(loader, adapterType);
        String hookClassName = EXPECTED_HOOK_CLASSES.get(adapterType.getName());
        Class<?> hookType;
        try {
            hookType = Class.forName(hookClassName, false, loader);
        } catch (ClassNotFoundException | LinkageError exception) {
            throw new IllegalStateException(
                    "RC_ADAPTER_CLASSLOADER_MISMATCH: exact hook could not be linked",
                    exception);
        }
        if (hookType.getClassLoader() != loader || hookType.getModule().isNamed()) {
            throw new IllegalStateException(
                    "RC_ADAPTER_CLASSLOADER_MISMATCH: runtime adapter and exact hook must share one unnamed loader");
        }
        verifyUniqueDefinition(loader, hookType);
        if (!codeSourceLocation(adapterType).equals(codeSourceLocation(hookType))) {
            throw new IllegalStateException(
                    "RC_ADAPTER_CLASSLOADER_MISMATCH: runtime adapter and exact hook have different origins");
        }
    }

    private static void verifyUniqueDefinition(final ClassLoader loader, final Class<?> runtimeType) {
        try {
            List<URL> definitions = List.copyOf(Collections.list(loader.getResources(
                    runtimeType.getName().replace('.', '/') + ".class")));
            if (definitions.size() != 1) {
                throw new IllegalStateException(
                        "RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS: expected one visible definition of "
                                + runtimeType.getName() + "; found " + definitions.size());
            }
        } catch (IOException exception) {
            throw new IllegalStateException(
                    "RC_ADAPTER_CLASSLOADER_MISMATCH: adapter class resources could not be enumerated",
                    exception);
        }
        codeSourceLocation(runtimeType);
    }

    private static String codeSourceLocation(final Class<?> runtimeType) {
        CodeSource codeSource = runtimeType.getProtectionDomain().getCodeSource();
        if (codeSource == null || codeSource.getLocation() == null) {
            throw new IllegalStateException(
                    "RC_ADAPTER_CLASSLOADER_MISMATCH: code-source origin unavailable for "
                            + runtimeType.getName());
        }
        return codeSource.getLocation().toExternalForm();
    }
}
