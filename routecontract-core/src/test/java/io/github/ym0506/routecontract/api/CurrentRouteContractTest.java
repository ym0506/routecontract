package io.github.ym0506.routecontract.api;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.JarOutputStream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CurrentRouteContractTest {

    private static final String CORE_PACKAGE = "io.github.ym0506.routecontract.";
    private static final String LEGACY_RESOURCE =
            "io/github/ym0506/routecontract/internal/RouteContractSqlExecutionHook.class";
    private static final String HOOK_SERVICE =
            "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";

    @TempDir
    Path temporaryDirectory;

    @Test
    void captureRejectsMissingAdapterBeforeEnteringAction() {
        AtomicBoolean actionEntered = new AtomicBoolean();

        IllegalStateException failure = assertThrows(IllegalStateException.class,
                () -> RouteContract.capture("missing-adapter", () -> actionEntered.set(true)));

        assertMissingAdapter(failure);
        assertFalse(actionEntered.get());
    }

    @Test
    void captureResultRejectsMissingAdapterBeforeEnteringSupplier() {
        AtomicBoolean actionEntered = new AtomicBoolean();

        IllegalStateException failure = assertThrows(IllegalStateException.class,
                () -> RouteContract.captureResult("missing-adapter", () -> {
                    actionEntered.set(true);
                    return "must not be returned";
                }));

        assertMissingAdapter(failure);
        assertFalse(actionEntered.get());
    }

    @Test
    void startupVerificationRunsCompleteAdapterPreflight() {
        assertMissingAdapter(assertThrows(IllegalStateException.class, RouteContract::verifyRuntime));
    }

    @Test
    void oldCaptureFacadePreservesMissingAdapterBoundary() {
        AtomicBoolean actionEntered = new AtomicBoolean();

        IllegalStateException failure = assertThrows(IllegalStateException.class,
                () -> io.github.ym0506.routecontract.RouteContract.capture(
                        "missing-adapter", () -> actionEntered.set(true)));

        assertMissingAdapter(failure);
        assertFalse(actionEntered.get());
    }

    @Test
    void oldCaptureResultFacadePreservesMissingAdapterBoundary() {
        AtomicBoolean actionEntered = new AtomicBoolean();

        IllegalStateException failure = assertThrows(IllegalStateException.class,
                () -> io.github.ym0506.routecontract.RouteContract.captureResult("missing-adapter", () -> {
                    actionEntered.set(true);
                    return "must not be returned";
                }));

        assertMissingAdapter(failure);
        assertFalse(actionEntered.get());
    }

    @Test
    void newCaptureRejectsLegacyClassBeforeCollectorDependencyCanBeInitialized() throws Exception {
        assertPassiveCaptureCollision("capture", LEGACY_RESOURCE, "not bytecode");
    }

    @Test
    void newCaptureResultRejectsLegacyClassBeforeCollectorDependencyCanBeInitialized() throws Exception {
        assertPassiveCaptureCollision("captureResult", LEGACY_RESOURCE, "not bytecode");
    }

    @Test
    void newCaptureRejectsLegacyServiceBeforeServiceDiscoveryCanInstantiateIt() throws Exception {
        assertPassiveCaptureCollision("capture", HOOK_SERVICE,
                CORE_PACKAGE + "internal.RouteContractSqlExecutionHook\n");
    }

    @Test
    void newCaptureResultRejectsLegacyServiceBeforeServiceDiscoveryCanInstantiateIt() throws Exception {
        assertPassiveCaptureCollision("captureResult", HOOK_SERVICE,
                CORE_PACKAGE + "internal.RouteContractSqlExecutionHook\n");
    }

    @Test
    void duplicateCompatibilityEntryIsRejectedBeforeCollectorInitialization() throws Exception {
        assertPassiveCaptureFailure("capture", "io/github/ym0506/routecontract/RouteContract.class",
                "not bytecode", "RC_LEGACY_ADAPTER_COLLISION:");
    }

    @Test
    void duplicateCollectorIsRejectedBeforeCollectorInitialization() throws Exception {
        assertPassiveCaptureFailure("capture", "io/github/ym0506/routecontract/internal/CaptureRegistry.class",
                "not bytecode", "RC_LEGACY_ADAPTER_COLLISION:");
    }

    @Test
    void duplicateCurrentEntryIsClassifiedAsUnsupportedLoaderLayout() throws Exception {
        assertPassiveCaptureFailure("capture", "io/github/ym0506/routecontract/api/RouteContract.class",
                "not bytecode", "RC_ADAPTER_CLASSLOADER_MISMATCH:");
    }

    @Test
    void duplicateCurrentGuardIsClassifiedAsUnsupportedLoaderLayout() throws Exception {
        assertPassiveCaptureFailure("capture", "io/github/ym0506/routecontract/internal/CurrentRuntimeGuard.class",
                "not bytecode", "RC_ADAPTER_CLASSLOADER_MISMATCH:");
    }

    @Test
    void aSingleModelDefinitionFromAnotherOriginIsRejected() throws Exception {
        Path splitCore = temporaryDirectory.resolve("split-core.jar");
        String modelResource = "io/github/ym0506/routecontract/RouteSnapshot.class";
        Path movedModel = temporaryDirectory.resolve(modelResource);
        Files.createDirectories(movedModel.getParent());
        try (JarFile source = new JarFile(requiredCoreJar().toFile());
                JarOutputStream output = new JarOutputStream(Files.newOutputStream(splitCore))) {
            for (JarEntry entry : source.stream().toList()) {
                try (var bytes = source.getInputStream(entry)) {
                    if (entry.getName().equals(modelResource)) {
                        Files.copy(bytes, movedModel);
                    } else {
                        output.putNextEntry(new JarEntry(entry.getName()));
                        bytes.transferTo(output);
                        output.closeEntry();
                    }
                }
            }
        }
        assertTrue(Files.isRegularFile(movedModel));

        try (URLClassLoader loader = isolatedCoreLoader(splitCore)) {
            Class<?> guard = Class.forName(CORE_PACKAGE + "internal.CurrentRuntimeGuard", true, loader);
            Class<?> model = Class.forName(CORE_PACKAGE + "RouteSnapshot", false, loader);
            assertEquals(1, Collections.list(loader.getResources(modelResource)).size());
            assertNotEquals(guard.getProtectionDomain().getCodeSource().getLocation(),
                    model.getProtectionDomain().getCodeSource().getLocation());
            InvocationTargetException invocation = assertThrows(InvocationTargetException.class,
                    () -> guard.getMethod("verifyClasspath").invoke(null));

            IllegalStateException failure = assertInstanceOf(IllegalStateException.class, invocation.getCause());
            assertTrue(failure.getMessage().startsWith("RC_ADAPTER_CLASSLOADER_MISMATCH:"));
            assertTrue(failure.getMessage().contains("share one core origin"), failure.getMessage());
            assertFalse(failure.getMessage().contains(temporaryDirectory.toString()));
        }
    }

    @Test
    void aSuccessfulCompleteClasspathCheckDoesNotHideLaterLegacyService() throws Exception {
        try (URLClassLoader loader = isolatedCoreLoader(requiredCoreJar())) {
            Class<?> guard = Class.forName(CORE_PACKAGE + "internal.CurrentRuntimeGuard", true, loader);
            guard.getMethod("verifyClasspath").invoke(null);
            Path descriptor = temporaryDirectory.resolve(HOOK_SERVICE);
            Files.createDirectories(descriptor.getParent());
            Files.writeString(descriptor, CORE_PACKAGE + "internal.RouteContractSqlExecutionHook\n",
                    StandardCharsets.UTF_8);
            Class<?> api = Class.forName(CORE_PACKAGE + "api.RouteContract", true, loader);

            InvocationTargetException invocation = assertThrows(InvocationTargetException.class,
                    () -> api.getMethod("verifyRuntime").invoke(null));

            IllegalStateException failure = assertInstanceOf(IllegalStateException.class, invocation.getCause());
            assertTrue(failure.getMessage().startsWith("RC_LEGACY_ADAPTER_COLLISION:"));
        }
    }

    private void assertPassiveCaptureCollision(
            final String methodName, final String resource, final String resourceContent) throws Exception {
        assertPassiveCaptureFailure(methodName, resource, resourceContent, "RC_LEGACY_ADAPTER_COLLISION:");
    }

    private void assertPassiveCaptureFailure(
            final String methodName, final String resource, final String resourceContent,
            final String expectedMarker) throws Exception {
        Path marker = temporaryDirectory.resolve(resource);
        Files.createDirectories(marker.getParent());
        Files.writeString(marker, resourceContent, StandardCharsets.UTF_8);

        // Only the core and JDK are visible. Collector initialization needs TTL, which is absent;
        // service discovery cannot instantiate the intentionally absent/invalid legacy provider.
        // The stable collision exception therefore verifies the ordering of the public entry.
        try (URLClassLoader loader = isolatedCoreLoader(requiredCoreJar())) {
            AtomicBoolean actionEntered = new AtomicBoolean();
            Class<?> api = Class.forName(CORE_PACKAGE + "api.RouteContract", true, loader);
            String callbackName = methodName.equals("capture") ? "ThrowingRunnable" : "ThrowingSupplier";
            Class<?> callback = Class.forName(CORE_PACKAGE + callbackName, false, loader);
            Object action = Proxy.newProxyInstance(loader, new Class<?>[]{callback}, (proxy, method, arguments) -> {
                actionEntered.set(true);
                return methodName.equals("capture") ? null : "must not be returned";
            });
            Method capture = api.getMethod(methodName, String.class, callback);

            InvocationTargetException invocation = assertThrows(InvocationTargetException.class,
                    () -> capture.invoke(null, "legacy-collision", action));

            IllegalStateException failure = assertInstanceOf(IllegalStateException.class, invocation.getCause());
            assertTrue(failure.getMessage().startsWith(expectedMarker), failure.getMessage());
            assertFalse(failure.getMessage().contains(temporaryDirectory.toString()));
            assertFalse(actionEntered.get());
            assertEquals(loader, api.getClassLoader());
        }
    }

    private URLClassLoader isolatedCoreLoader(final Path coreJar) throws Exception {
        return new URLClassLoader(
                new URL[]{coreJar.toUri().toURL(), temporaryDirectory.toUri().toURL()},
                ClassLoader.getPlatformClassLoader());
    }

    private static Path requiredCoreJar() {
        String coreJar = System.getProperty("routecontract.coreJar");
        assertNotNull(coreJar, "the test task must provide the locally built core JAR");
        Path corePath = Path.of(coreJar);
        assertTrue(Files.isRegularFile(corePath));
        return corePath;
    }

    private static void assertMissingAdapter(final IllegalStateException failure) {
        assertTrue(failure.getMessage().startsWith("RC_ADAPTER_NOT_FOUND:"), failure.getMessage());
    }
}
