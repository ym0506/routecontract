package io.github.ym0506.routecontract.internal;

import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.CodeSource;
import java.util.Collections;
import java.util.List;

/**
 * Passive entry protection owned only by the current split core.
 *
 * <p>Public only to cross the core's package boundary; not an application extension point.
 * Class names remain strings until legacy detection completes. In particular, this class must
 * not initialize a shadowable collector or discover runtime services before that detection.</p>
 */
public final class CurrentRuntimeGuard {

    private static final String LEGACY_HOOK_CLASS =
            "io/github/ym0506/routecontract/internal/RouteContractSqlExecutionHook.class";
    private static final String LEGACY_HOOK_PROVIDER =
            "io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook";
    private static final String HOOK_SERVICE =
            "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";
    private static final String COMPATIBILITY_ENTRY = "io.github.ym0506.routecontract.RouteContract";
    private static final String COLLECTOR = "io.github.ym0506.routecontract.internal.CaptureRegistry";
    private static final List<String> CORE_CLASSES = List.of(
            "io.github.ym0506.routecontract.api.RouteContract",
            "io.github.ym0506.routecontract.internal.CurrentRuntimeGuard",
            COMPATIBILITY_ENTRY,
            COLLECTOR,
            "io.github.ym0506.routecontract.internal.RuntimeAdapterRegistry",
            "io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter",
            "io.github.ym0506.routecontract.spi.RouteContractHookBridge",
            "io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity",
            "io.github.ym0506.routecontract.RouteSnapshot",
            "io.github.ym0506.routecontract.CapturedResult",
            "io.github.ym0506.routecontract.ThrowingRunnable",
            "io.github.ym0506.routecontract.ThrowingSupplier");

    private CurrentRuntimeGuard() {
    }

    /**
     * Rejects a visible legacy layout before any collector or runtime service is initialized.
     *
     * @throws IllegalStateException when the classpath does not have one current core origin
     */
    public static void verifyClasspath() {
        Class<?> anchor = CurrentRuntimeGuard.class;
        ClassLoader loader = anchor.getClassLoader();
        if (loader == null) {
            throw loaderMismatch("the current core requires an application classloader", null);
        }
        // Intentionally first: even loading old classes to inspect them can let old linkage or
        // initialization errors mask the actionable collision diagnostic.
        verifyLegacyResources(loader);
        verifyUnnamedModule(anchor);
        String expectedOrigin = codeSourceLocation(anchor);
        for (String className : CORE_CLASSES) {
            List<URL> definitions = resources(loader, className.replace('.', '/') + ".class");
            if (definitions.size() > 1
                    && (COMPATIBILITY_ENTRY.equals(className) || COLLECTOR.equals(className))) {
                throw legacyCollision();
            }
            if (definitions.size() != 1) {
                throw loaderMismatch("one visible definition of each current core class is required", null);
            }
            Class<?> actual;
            try {
                actual = Class.forName(className, false, loader);
            } catch (ClassNotFoundException | LinkageError | SecurityException failure) {
                throw loaderMismatch("a required current core class could not be resolved", failure);
            }
            verifyUnnamedModule(actual);
            if (actual.getClassLoader() != loader || !expectedOrigin.equals(codeSourceLocation(actual))) {
                throw loaderMismatch("the current entry, collector, models and SPI must share one core origin", null);
            }
        }
    }

    /**
     * Performs entry protection followed by complete runtime and cached-provider verification.
     *
     * @return verified exact runtime identity
     * @throws IllegalStateException when either the passive guard or runtime preflight fails
     */
    public static ShardingSphereRuntimeIdentity verifyRuntime() {
        verifyClasspath();
        return RuntimeAdapterRegistry.verify();
    }

    static void verifyLegacyResources(final ClassLoader loader) {
        if (!resources(loader, LEGACY_HOOK_CLASS).isEmpty()) {
            throw legacyCollision();
        }
        for (URL descriptor : resources(loader, HOOK_SERVICE)) {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                    descriptor.openStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    int comment = line.indexOf('#');
                    String provider = (comment < 0 ? line : line.substring(0, comment)).trim();
                    if (LEGACY_HOOK_PROVIDER.equals(provider)) {
                        throw legacyCollision();
                    }
                }
            } catch (IOException | SecurityException failure) {
                throw loaderMismatch("hook service resources could not be inspected", failure);
            }
        }
    }

    private static List<URL> resources(final ClassLoader loader, final String resource) {
        try {
            return List.copyOf(Collections.list(loader.getResources(resource)));
        } catch (IOException | SecurityException failure) {
            throw loaderMismatch("current core resources could not be enumerated", failure);
        }
    }

    private static void verifyUnnamedModule(final Class<?> type) {
        if (type.getModule().isNamed()) {
            throw new IllegalStateException("RC_UNSUPPORTED_MODULE_PATH: RouteContract 0.2 requires the classpath");
        }
    }

    private static String codeSourceLocation(final Class<?> type) {
        try {
            CodeSource source = type.getProtectionDomain().getCodeSource();
            if (source == null || source.getLocation() == null) {
                throw loaderMismatch("current core code-source origin is unavailable", null);
            }
            return source.getLocation().toExternalForm();
        } catch (SecurityException failure) {
            throw loaderMismatch("current core code-source origin could not be inspected", failure);
        }
    }

    private static IllegalStateException legacyCollision() {
        return new IllegalStateException(
                "RC_LEGACY_ADAPTER_COLLISION: remove all pre-0.2 routecontract-shardingsphere-5.5 JARs; "
                        + "select one 0.2 adapter matching the exact ShardingSphere version, re-resolve "
                        + "Gradle/Maven dependencies, and restart the JVM");
    }

    private static IllegalStateException loaderMismatch(final String reason, final Throwable cause) {
        return new IllegalStateException("RC_ADAPTER_CLASSLOADER_MISMATCH: " + reason, cause);
    }
}
