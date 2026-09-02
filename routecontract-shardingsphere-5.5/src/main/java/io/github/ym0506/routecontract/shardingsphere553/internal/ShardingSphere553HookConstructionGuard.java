package io.github.ym0506.routecontract.shardingsphere553.internal;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.CodeSource;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Non-recursive construction guard that runs before the 5.5.3 hook touches the core bridge.
 *
 * <p>This guard deliberately performs no Java or ShardingSphere service loading. It reads class
 * and service resources passively through the hook-defining loader so wrong-runtime, duplicate,
 * legacy all-in-one, classloader, and module-path failures surface before an incompatible hook
 * callback can be dispatched.</p>
 */
final class ShardingSphere553HookConstructionGuard {

    /**
     * A successful guard result is reusable only for the exact defining loader and runtime-anchor
     * tuple that was inspected. ShardingSphere creates one hook instance per physical callback,
     * so repeating the passive classpath scan for every instance would put filesystem work on the
     * JDBC hot path. Keeping the complete tuple here avoids an unkeyed process-global success bit:
     * a different loader, class identity, package version, or code-source origin is reverified.
     */
    private static volatile VerificationStamp verifiedStamp;

    private static final String SUPPORTED_VERSION = "5.5.3";
    private static final String HOOK_SERVICE =
            "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";
    private static final String RUNTIME_ADAPTER_SERVICE =
            "META-INF/services/io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter";
    private static final String HOOK_PROVIDER_553 =
            "io.github.ym0506.routecontract.shardingsphere553.internal.RouteContract553SqlExecutionHook";
    private static final String RUNTIME_PROVIDER_553 =
            "io.github.ym0506.routecontract.shardingsphere553.internal.ShardingSphere553RuntimeAdapter";
    private static final String ROUTECONTRACT_NAMESPACE = "io.github.ym0506.routecontract.";
    private static final String LEGACY_HOOK_PROVIDER =
            "io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook";
    private static final String LEGACY_HOOK_CLASS =
            "io/github/ym0506/routecontract/internal/RouteContractSqlExecutionHook.class";
    private static final String CORE_ENTRY_POINT_CLASS =
            "io.github.ym0506.routecontract.RouteContract";
    private static final String CORE_BRIDGE_CLASS =
            "io.github.ym0506.routecontract.spi.RouteContractHookBridge";
    private static final String CORE_COLLECTOR_CLASS =
            "io.github.ym0506.routecontract.internal.CaptureRegistry";
    private static final String CORE_RUNTIME_ADAPTER_CLASS =
            "io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter";
    private static final String CORE_RUNTIME_IDENTITY_CLASS =
            "io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity";
    private static final String EXECUTOR_ANCHOR_CLASS =
            "org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";
    private static final String SPI_ANCHOR_CLASS =
            "org.apache.shardingsphere.infra.spi.ShardingSphereSPI";
    private static final String DATABASE_ANCHOR_CLASS =
            "org.apache.shardingsphere.database.connector.core.jdbcurl.parser.ConnectionProperties";

    private ShardingSphere553HookConstructionGuard() {
    }

    static void verify() {
        VerificationStamp cachedStamp = verifiedStamp;
        if (cachedStamp != null) {
            VerificationContext cachedContext = verificationContext();
            if (cachedContext.stamp().equals(cachedStamp)) {
                return;
            }
        }
        synchronized (ShardingSphere553HookConstructionGuard.class) {
            cachedStamp = verifiedStamp;
            if (cachedStamp != null) {
                VerificationContext cachedContext = verificationContext();
                if (cachedContext.stamp().equals(cachedStamp)) {
                    return;
                }
            }
            Class<?> hookType = RouteContract553SqlExecutionHook.class;
            ClassLoader loader = hookType.getClassLoader();
            if (loader == null) {
                throw loaderMismatch("the exact adapter must have an application classloader", null);
            }
            DescriptorLayout descriptors = verifyDescriptorLayout(loader);
            VerificationContext context = verificationContext();
            verifyUncached(context, descriptors);
            verifiedStamp = context.stamp();
        }
    }

    private static VerificationContext verificationContext() {
        Class<?> hookType = RouteContract553SqlExecutionHook.class;
        ClassLoader loader = hookType.getClassLoader();
        if (loader == null) {
            throw loaderMismatch("the exact adapter must have an application classloader", null);
        }
        Class<?> executorAnchor = loadRuntimeAnchor(EXECUTOR_ANCHOR_CLASS, loader);
        Class<?> spiAnchor = loadRuntimeAnchor(SPI_ANCHOR_CLASS, loader);
        Class<?> databaseAnchor = loadRuntimeAnchor(DATABASE_ANCHOR_CLASS, loader);
        Class<?> coreEntryPoint = loadWithoutInitialization(CORE_ENTRY_POINT_CLASS, loader);
        Class<?> coreBridge = loadWithoutInitialization(CORE_BRIDGE_CLASS, loader);
        Class<?> coreCollector = loadWithoutInitialization(CORE_COLLECTOR_CLASS, loader);
        Class<?> coreRuntimeAdapter = loadWithoutInitialization(CORE_RUNTIME_ADAPTER_CLASS, loader);
        Class<?> coreRuntimeIdentity = loadWithoutInitialization(CORE_RUNTIME_IDENTITY_CLASS, loader);
        Class<?> runtimeProvider = loadWithoutInitialization(RUNTIME_PROVIDER_553, loader);
        verifyUnnamedModules(hookType, executorAnchor, spiAnchor, databaseAnchor);

        if (executorAnchor.getClassLoader() != loader
                || spiAnchor.getClassLoader() != loader
                || databaseAnchor.getClassLoader() != loader) {
            throw loaderMismatch("hook and exact ShardingSphere anchors must share one classloader", null);
        }
        return new VerificationContext(
                loader,
                hookType,
                executorAnchor,
                spiAnchor,
                databaseAnchor,
                new VerificationStamp(
                        loader,
                        hookType,
                        executorAnchor,
                        spiAnchor,
                        databaseAnchor,
                        coreEntryPoint,
                        coreBridge,
                        coreCollector,
                        coreRuntimeAdapter,
                        coreRuntimeIdentity,
                        runtimeProvider,
                        implementationVersion(executorAnchor),
                        implementationVersion(spiAnchor),
                        implementationVersion(databaseAnchor),
                        codeSourceLocation(hookType, "RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS"),
                        codeSourceLocation(executorAnchor, "RC_MIXED_SHARDINGSPHERE_RUNTIME"),
                        codeSourceLocation(spiAnchor, "RC_MIXED_SHARDINGSPHERE_RUNTIME"),
                        codeSourceLocation(databaseAnchor, "RC_MIXED_SHARDINGSPHERE_RUNTIME"),
                        codeSourceLocation(coreEntryPoint, "RC_ADAPTER_CLASSLOADER_MISMATCH"),
                        codeSourceLocation(coreBridge, "RC_ADAPTER_CLASSLOADER_MISMATCH"),
                        codeSourceLocation(coreCollector, "RC_ADAPTER_CLASSLOADER_MISMATCH"),
                        codeSourceLocation(coreRuntimeAdapter, "RC_ADAPTER_CLASSLOADER_MISMATCH"),
                        codeSourceLocation(coreRuntimeIdentity, "RC_ADAPTER_CLASSLOADER_MISMATCH"),
                        codeSourceLocation(runtimeProvider, "RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS")));
    }

    private static void verifyUncached(
            final VerificationContext context,
            final DescriptorLayout descriptors) {
        ClassLoader loader = context.loader();
        Class<?> hookType = context.hookType();
        Class<?> executorAnchor = context.executorAnchor();
        Class<?> spiAnchor = context.spiAnchor();
        Class<?> databaseAnchor = context.databaseAnchor();
        verifyAnchorVersions(
                implementationVersion(executorAnchor),
                implementationVersion(spiAnchor),
                implementationVersion(databaseAnchor));
        verifyUniqueDefinition(loader, hookType, "RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS");
        verifyUniqueDefinition(loader, executorAnchor, "RC_MIXED_SHARDINGSPHERE_RUNTIME");
        verifyUniqueDefinition(loader, spiAnchor, "RC_MIXED_SHARDINGSPHERE_RUNTIME");
        verifyUniqueDefinition(loader, databaseAnchor, "RC_MIXED_SHARDINGSPHERE_RUNTIME");
        verifyDistinctAnchorOrigins(executorAnchor, spiAnchor, databaseAnchor);
        verifyHookAbi(hookType, executorAnchor, databaseAnchor);

        verifyProviderNames(
                descriptors.hookProviders(),
                descriptors.runtimeProviders(),
                descriptors.legacyClassVisible());
        CoreLayout core = verifyCoreLayout(loader, hookType);
        verifyAdapterLayout(loader, hookType, core);
    }

    private static DescriptorLayout verifyDescriptorLayout(final ClassLoader loader) {
        boolean legacyClassVisible = !resources(loader, LEGACY_HOOK_CLASS).isEmpty();
        List<String> hookProviders = providerNames(loader, HOOK_SERVICE);
        List<String> runtimeProviders = providerNames(loader, RUNTIME_ADAPTER_SERVICE);
        verifyProviderNames(hookProviders, runtimeProviders, legacyClassVisible);
        return new DescriptorLayout(hookProviders, runtimeProviders, legacyClassVisible);
    }

    static void verifyAnchorVersions(
            final String executorVersion,
            final String spiVersion,
            final String databaseVersion) {
        if (executorVersion == null || spiVersion == null || databaseVersion == null) {
            throw new IllegalStateException(
                    "RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME: implementation version unavailable; executor="
                            + renderedVersion(executorVersion)
                            + ", spi=" + renderedVersion(spiVersion)
                            + ", database=" + renderedVersion(databaseVersion));
        }
        Set<String> versions = new HashSet<>(List.of(
                renderedVersion(executorVersion),
                renderedVersion(spiVersion),
                renderedVersion(databaseVersion)));
        if (versions.size() != 1) {
            throw new IllegalStateException(
                    "RC_MIXED_SHARDINGSPHERE_RUNTIME: executor=" + renderedVersion(executorVersion)
                            + ", spi=" + renderedVersion(spiVersion)
                            + ", database=" + renderedVersion(databaseVersion));
        }
        if (!SUPPORTED_VERSION.equals(executorVersion)) {
            throw new IllegalStateException(
                    "RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME: exact adapter 5.5.3 observed "
                            + renderedVersion(executorVersion));
        }
    }

    static void verifyProviderNames(
            final List<String> hookProviders,
            final List<String> runtimeProviders,
            final boolean legacyClassVisible) {
        if (legacyClassVisible || hookProviders.contains(LEGACY_HOOK_PROVIDER)) {
            throw new IllegalStateException(
                    "RC_LEGACY_ADAPTER_COLLISION: a pre-0.2 all-in-one hook layout is visible");
        }
        List<String> routeContractHooks = hookProviders.stream()
                .filter(provider -> provider.startsWith(ROUTECONTRACT_NAMESPACE))
                .toList();
        long hook553Count = count(routeContractHooks, HOOK_PROVIDER_553);
        long runtime553Count = count(runtimeProviders, RUNTIME_PROVIDER_553);
        if (hook553Count > 1
                || runtime553Count > 1
                || routeContractHooks.size() != hook553Count
                || runtimeProviders.size() != runtime553Count) {
            throw new IllegalStateException(
                    "RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS: unexpected RouteContract provider descriptors are visible");
        }
        if (hook553Count == 0 || runtime553Count == 0) {
            throw new IllegalStateException(
                    "RC_ADAPTER_NOT_FOUND: exact 5.5.3 hook and runtime-adapter descriptors must both be visible");
        }
    }

    private static CoreLayout verifyCoreLayout(final ClassLoader loader, final Class<?> hookType) {
        List<URL> routeResources = resources(loader, binaryClassPath(CORE_ENTRY_POINT_CLASS));
        if (routeResources.size() > 1) {
            throw new IllegalStateException(
                    "RC_LEGACY_ADAPTER_COLLISION: multiple core public-class origins are visible");
        }
        List<String> coreClasses = List.of(
                CORE_ENTRY_POINT_CLASS,
                CORE_BRIDGE_CLASS,
                CORE_COLLECTOR_CLASS,
                CORE_RUNTIME_ADAPTER_CLASS,
                CORE_RUNTIME_IDENTITY_CLASS);
        for (String coreClass : coreClasses) {
            int definitions = resources(loader, binaryClassPath(coreClass)).size();
            if (definitions != 1) {
                throw loaderMismatch("expected one visible definition of " + coreClass
                        + "; found " + definitions, null);
            }
        }

        Class<?> routeType = loadWithoutInitialization(CORE_ENTRY_POINT_CLASS, loader);
        Class<?> bridgeType = loadWithoutInitialization(CORE_BRIDGE_CLASS, loader);
        Class<?> collectorType = loadWithoutInitialization(CORE_COLLECTOR_CLASS, loader);
        Class<?> runtimeAdapterType = loadWithoutInitialization(CORE_RUNTIME_ADAPTER_CLASS, loader);
        Class<?> identityType = loadWithoutInitialization(CORE_RUNTIME_IDENTITY_CLASS, loader);
        verifyUnnamedModules(routeType, bridgeType, collectorType, runtimeAdapterType, identityType);
        if (routeType.getClassLoader() != loader
                || bridgeType.getClassLoader() != loader
                || collectorType.getClassLoader() != loader
                || runtimeAdapterType.getClassLoader() != loader
                || identityType.getClassLoader() != loader) {
            throw loaderMismatch("core entry point, bridge, collector, SPI, and identity classloaders differ", null);
        }
        String routeOrigin = codeSourceLocation(routeType, "RC_ADAPTER_CLASSLOADER_MISMATCH");
        if (!routeOrigin.equals(codeSourceLocation(bridgeType, "RC_ADAPTER_CLASSLOADER_MISMATCH"))
                || !routeOrigin.equals(codeSourceLocation(collectorType, "RC_ADAPTER_CLASSLOADER_MISMATCH"))
                || !routeOrigin.equals(codeSourceLocation(
                        runtimeAdapterType, "RC_ADAPTER_CLASSLOADER_MISMATCH"))
                || !routeOrigin.equals(codeSourceLocation(identityType, "RC_ADAPTER_CLASSLOADER_MISMATCH"))) {
            throw loaderMismatch("core entry point, bridge, collector, SPI, and identity have different origins", null);
        }
        if (routeOrigin.equals(codeSourceLocation(hookType, "RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS"))) {
            throw new IllegalStateException(
                    "RC_LEGACY_ADAPTER_COLLISION: core and hook share an all-in-one code-source origin");
        }
        verifyBridgeAbi(bridgeType);
        verifyCollectorAbi(collectorType);
        verifyMethod(runtimeAdapterType, "verifyRuntime", identityType, false);
        return new CoreLayout(runtimeAdapterType, identityType, routeOrigin);
    }

    private static void verifyAdapterLayout(
            final ClassLoader loader,
            final Class<?> hookType,
            final CoreLayout core) {
        Class<?> runtimeProviderType = loadWithoutInitialization(RUNTIME_PROVIDER_553, loader);
        verifyUnnamedModules(runtimeProviderType);
        if (runtimeProviderType.getClassLoader() != loader) {
            throw loaderMismatch("hook and runtime-adapter provider classloaders differ", null);
        }
        verifyUniqueDefinition(loader, runtimeProviderType, "RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS");
        String hookOrigin = codeSourceLocation(hookType, "RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS");
        String runtimeOrigin = codeSourceLocation(
                runtimeProviderType, "RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS");
        if (!hookOrigin.equals(runtimeOrigin)) {
            throw loaderMismatch("hook and runtime-adapter provider have different origins", null);
        }
        if (hookOrigin.equals(core.origin())) {
            throw new IllegalStateException(
                    "RC_LEGACY_ADAPTER_COLLISION: core and adapter share an all-in-one code-source origin");
        }
        if (!core.runtimeAdapterType().isAssignableFrom(runtimeProviderType)) {
            throw loaderMismatch("runtime provider does not implement the core-owned adapter SPI", null);
        }
        try {
            int constructorModifiers = runtimeProviderType.getDeclaredConstructor().getModifiers();
            if (!Modifier.isPublic(constructorModifiers)) {
                throw new NoSuchMethodException("runtime adapter no-arg constructor is not public");
            }
        } catch (ReflectiveOperationException | LinkageError exception) {
            throw loaderMismatch("runtime adapter no-arg constructor ABI differs", exception);
        }
        verifyMethod(runtimeProviderType, "verifyRuntime", core.identityType(), false);
    }

    private static void verifyHookAbi(
            final Class<?> hookType,
            final Class<?> executorAnchor,
            final Class<?> databaseAnchor) {
        if (!executorAnchor.isAssignableFrom(hookType)) {
            throw loaderMismatch("exact hook does not implement the runtime SQLExecutionHook identity", null);
        }
        verifyMethod(
                hookType,
                "start",
                void.class,
                false,
                String.class,
                String.class,
                List.class,
                databaseAnchor,
                boolean.class);
        verifyMethod(hookType, "finishSuccess", void.class, false);
        verifyMethod(hookType, "finishFailure", void.class, false, Exception.class);
    }

    private static void verifyBridgeAbi(final Class<?> bridgeType) {
        verifyMethod(bridgeType, "noopAttempt", Object.class, true);
        verifyMethod(
                bridgeType,
                "start",
                Object.class,
                true,
                String.class,
                String.class,
                List.class,
                boolean.class);
        verifyMethod(bridgeType, "finishCallbackReturned", void.class, true, Object.class);
        verifyMethod(bridgeType, "finishFailure", void.class, true, Object.class, Exception.class);
        verifyMethod(bridgeType, "recordDiagnostic", void.class, true, String.class);
    }

    private static void verifyCollectorAbi(final Class<?> collectorType) {
        verifyMethod(collectorType, "noopAttemptFromAdapter", Object.class, true);
        verifyMethod(
                collectorType,
                "startAttemptFromAdapter",
                Object.class,
                true,
                String.class,
                String.class,
                List.class,
                boolean.class);
        verifyMethod(collectorType, "finishCallbackReturnedFromAdapter", void.class, true, Object.class);
        verifyMethod(
                collectorType,
                "finishFailureFromAdapter",
                void.class,
                true,
                Object.class,
                Exception.class);
        verifyMethod(collectorType, "recordCurrentErrorFromAdapter", void.class, true, String.class);
    }

    private static Method verifyMethod(
            final Class<?> owner,
            final String name,
            final Class<?> returnType,
            final boolean staticMethod,
            final Class<?>... parameterTypes) {
        try {
            Method method = owner.getDeclaredMethod(name, parameterTypes);
            int modifiers = method.getModifiers();
            if (!Modifier.isPublic(modifiers)
                    || Modifier.isStatic(modifiers) != staticMethod
                    || method.getReturnType() != returnType) {
                throw new NoSuchMethodException("method modifiers or return type differ");
            }
            return method;
        } catch (ReflectiveOperationException | LinkageError exception) {
            throw loaderMismatch("required ABI differs: " + owner.getName() + "#" + name, exception);
        }
    }

    private static void verifyUnnamedModules(final Class<?>... runtimeTypes) {
        for (Class<?> runtimeType : runtimeTypes) {
            if (runtimeType.getModule().isNamed()) {
                throw new IllegalStateException(
                        "RC_UNSUPPORTED_MODULE_PATH: RouteContract 0.2 adapters require the classpath");
            }
        }
    }

    private static void verifyUniqueDefinition(
            final ClassLoader loader,
            final Class<?> runtimeType,
            final String marker) {
        List<URL> visibleDefinitions = resources(loader, binaryClassPath(runtimeType.getName()));
        if (visibleDefinitions.size() != 1) {
            throw new IllegalStateException(marker + ": expected one visible definition of "
                    + runtimeType.getName() + "; found " + visibleDefinitions.size());
        }
        codeSourceLocation(runtimeType, marker);
    }

    private static void verifyDistinctAnchorOrigins(final Class<?>... anchors) {
        Set<String> origins = new HashSet<>();
        for (Class<?> anchor : anchors) {
            origins.add(codeSourceLocation(anchor, "RC_MIXED_SHARDINGSPHERE_RUNTIME"));
        }
        if (origins.size() != anchors.length) {
            throw new IllegalStateException(
                    "RC_MIXED_SHARDINGSPHERE_RUNTIME: exact runtime anchors have overlapping code-source origins");
        }
    }

    private static String codeSourceLocation(final Class<?> runtimeType, final String marker) {
        CodeSource codeSource = runtimeType.getProtectionDomain().getCodeSource();
        if (codeSource == null || codeSource.getLocation() == null) {
            throw new IllegalStateException(
                    marker + ": code-source origin unavailable for "
                            + runtimeType.getName());
        }
        return codeSource.getLocation().toExternalForm();
    }

    private static Class<?> loadWithoutInitialization(final String className, final ClassLoader loader) {
        try {
            return Class.forName(className, false, loader);
        } catch (ClassNotFoundException | LinkageError exception) {
            throw loaderMismatch("core class could not be linked: " + className, exception);
        }
    }

    private static Class<?> loadRuntimeAnchor(final String className, final ClassLoader loader) {
        try {
            return Class.forName(className, false, loader);
        } catch (ClassNotFoundException | LinkageError exception) {
            throw new IllegalStateException(
                    "RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME: required 5.5.3 anchor could not be linked: "
                            + className,
                    exception);
        }
    }

    private static List<String> providerNames(final ClassLoader loader, final String servicePath) {
        List<String> result = new ArrayList<>();
        for (URL resource : resources(loader, servicePath)) {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                    resource.openStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    int comment = line.indexOf('#');
                    String provider = (comment < 0 ? line : line.substring(0, comment)).strip();
                    if (!provider.isEmpty()) {
                        result.add(provider);
                    }
                }
            } catch (IOException exception) {
                throw loaderMismatch("service descriptor could not be read: " + servicePath, exception);
            }
        }
        return List.copyOf(result);
    }

    private static List<URL> resources(final ClassLoader loader, final String path) {
        try {
            return List.copyOf(Collections.list(loader.getResources(path)));
        } catch (IOException exception) {
            throw loaderMismatch("classloader resources could not be enumerated: " + path, exception);
        }
    }

    private static long count(final List<String> providers, final String expectedProvider) {
        return providers.stream().filter(expectedProvider::equals).count();
    }

    private static String implementationVersion(final Class<?> runtimeType) {
        Package runtimePackage = runtimeType.getPackage();
        return runtimePackage == null ? null : runtimePackage.getImplementationVersion();
    }

    private static String renderedVersion(final String version) {
        return version == null ? "<unavailable>" : version;
    }

    private static String binaryClassPath(final String className) {
        return className.replace('.', '/') + ".class";
    }

    private static IllegalStateException loaderMismatch(final String detail, final Throwable cause) {
        return new IllegalStateException("RC_ADAPTER_CLASSLOADER_MISMATCH: " + detail, cause);
    }

    private record CoreLayout(
            Class<?> runtimeAdapterType,
            Class<?> identityType,
            String origin) {
    }

    private record VerificationContext(
            ClassLoader loader,
            Class<?> hookType,
            Class<?> executorAnchor,
            Class<?> spiAnchor,
            Class<?> databaseAnchor,
            VerificationStamp stamp) {
    }

    private record VerificationStamp(
            ClassLoader loader,
            Class<?> hookType,
            Class<?> executorAnchor,
            Class<?> spiAnchor,
            Class<?> databaseAnchor,
            Class<?> coreEntryPoint,
            Class<?> coreBridge,
            Class<?> coreCollector,
            Class<?> coreRuntimeAdapter,
            Class<?> coreRuntimeIdentity,
            Class<?> runtimeProvider,
            String executorVersion,
            String spiVersion,
            String databaseVersion,
            String hookOrigin,
            String executorOrigin,
            String spiOrigin,
            String databaseOrigin,
            String coreEntryPointOrigin,
            String coreBridgeOrigin,
            String coreCollectorOrigin,
            String coreRuntimeAdapterOrigin,
            String coreRuntimeIdentityOrigin,
            String runtimeProviderOrigin) {
    }

    private record DescriptorLayout(
            List<String> hookProviders,
            List<String> runtimeProviders,
            boolean legacyClassVisible) {
    }
}
