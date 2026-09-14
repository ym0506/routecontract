package io.github.ym0506.routecontract.internal;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CurrentRuntimeGuardTest {

    private static final String LEGACY_HOOK =
            "io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook";
    private static final String LEGACY_RESOURCE = LEGACY_HOOK.replace('.', '/') + ".class";
    private static final String HOOK_SERVICE =
            "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";

    @TempDir
    Path temporaryDirectory;

    @Test
    void classResourceRejectsLegacyWithoutLoadingItsBytes() throws Exception {
        MutableResourceLoader loader = new MutableResourceLoader();
        // Deliberately invalid bytecode: a passive check must never load or initialize this class.
        loader.resources.put(LEGACY_RESOURCE, List.of(write("legacy.class", "not bytecode")));

        assertCollision(assertThrows(IllegalStateException.class,
                () -> CurrentRuntimeGuard.verifyLegacyResources(loader)));
    }

    @Test
    void legacyProviderWithWhitespaceAndInlineCommentIsRejected() throws Exception {
        MutableResourceLoader loader = new MutableResourceLoader();
        loader.resources.put(HOOK_SERVICE, List.of(write("hook-service.txt",
                "# registered hooks\r\n\t" + LEGACY_HOOK + "  # old all-in-one adapter\r\n")));

        assertCollision(assertThrows(IllegalStateException.class,
                () -> CurrentRuntimeGuard.verifyLegacyResources(loader)));
    }

    @Test
    void commentsAndDifferentProviderNamesDoNotBecomeFalseLegacyMatches() throws Exception {
        MutableResourceLoader loader = new MutableResourceLoader();
        loader.resources.put(HOOK_SERVICE, List.of(write("safe-hooks.txt",
                "# " + LEGACY_HOOK + "\n\n"
                        + "io.github.ym0506.routecontract.shardingsphere553.internal."
                        + "RouteContract553SqlExecutionHook\n"
                        + LEGACY_HOOK + "Suffix\n"
                        + "example.AnotherHook # " + LEGACY_HOOK + "\n")));

        assertDoesNotThrow(() -> CurrentRuntimeGuard.verifyLegacyResources(loader));
    }

    @Test
    void legacyProviderInLaterServiceResourceIsStillRejected() throws Exception {
        MutableResourceLoader loader = new MutableResourceLoader();
        loader.resources.put(HOOK_SERVICE, List.of(
                write("first-service.txt", "example.CurrentHook\n"),
                write("second-service.txt", LEGACY_HOOK + "\n")));

        assertCollision(assertThrows(IllegalStateException.class,
                () -> CurrentRuntimeGuard.verifyLegacyResources(loader)));
    }

    @Test
    void aSuccessfulPassiveCheckIsNotCachedWhenResourcesChange() throws Exception {
        MutableResourceLoader loader = new MutableResourceLoader();
        assertDoesNotThrow(() -> CurrentRuntimeGuard.verifyLegacyResources(loader));

        loader.resources.put(HOOK_SERVICE, List.of(write("added-service.txt", LEGACY_HOOK + "\n")));

        assertCollision(assertThrows(IllegalStateException.class,
                () -> CurrentRuntimeGuard.verifyLegacyResources(loader)));
    }

    @Test
    void legacyClassEnumerationFailureHasLoaderMismatchDiagnostic() {
        assertEnumerationFailure(LEGACY_RESOURCE);
    }

    @Test
    void serviceEnumerationFailureHasLoaderMismatchDiagnostic() {
        assertEnumerationFailure(HOOK_SERVICE);
    }

    @Test
    void deniedResourceEnumerationFailsClosedWithLoaderMismatchDiagnostic() {
        SecurityException cause = new SecurityException("private policy detail");
        ClassLoader loader = new ClassLoader(null) {
            @Override
            public Enumeration<URL> getResources(final String name) {
                throw cause;
            }
        };

        IllegalStateException failure = assertThrows(IllegalStateException.class,
                () -> CurrentRuntimeGuard.verifyLegacyResources(loader));

        assertTrue(failure.getMessage().startsWith("RC_ADAPTER_CLASSLOADER_MISMATCH:"));
        assertSame(cause, failure.getCause());
        assertFalse(failure.getMessage().contains(cause.getMessage()));
    }

    @Test
    void unreadableServiceResourceFailsClosedWithoutLeakingItsPath() throws Exception {
        MutableResourceLoader loader = new MutableResourceLoader();
        Path missingService = temporaryDirectory.resolve("private-service-that-does-not-exist");
        loader.resources.put(HOOK_SERVICE, List.of(missingService.toUri().toURL()));

        IllegalStateException failure = assertThrows(IllegalStateException.class,
                () -> CurrentRuntimeGuard.verifyLegacyResources(loader));

        assertTrue(failure.getMessage().startsWith("RC_ADAPTER_CLASSLOADER_MISMATCH:"));
        assertTrue(failure.getCause() instanceof IOException);
        assertFalse(failure.getMessage().contains(missingService.toString()));
    }

    private void assertEnumerationFailure(final String failingResource) {
        IOException cause = new IOException("private resource enumeration detail");
        ClassLoader loader = new ClassLoader(null) {
            @Override
            public Enumeration<URL> getResources(final String name) throws IOException {
                if (name.equals(failingResource)) {
                    throw cause;
                }
                return Collections.emptyEnumeration();
            }
        };

        IllegalStateException failure = assertThrows(IllegalStateException.class,
                () -> CurrentRuntimeGuard.verifyLegacyResources(loader));

        assertTrue(failure.getMessage().startsWith("RC_ADAPTER_CLASSLOADER_MISMATCH:"));
        assertSame(cause, failure.getCause());
        assertFalse(failure.getMessage().contains(cause.getMessage()));
    }

    private void assertCollision(final IllegalStateException failure) {
        assertTrue(failure.getMessage().startsWith("RC_LEGACY_ADAPTER_COLLISION:"));
        assertFalse(failure.getMessage().contains(temporaryDirectory.toString()));
    }

    private URL write(final String name, final String content) throws IOException {
        return Files.writeString(temporaryDirectory.resolve(name), content, StandardCharsets.UTF_8)
                .toUri().toURL();
    }

    private static final class MutableResourceLoader extends ClassLoader {
        private final Map<String, List<URL>> resources = new HashMap<>();

        private MutableResourceLoader() {
            super(null);
        }

        @Override
        public Enumeration<URL> getResources(final String name) {
            return Collections.enumeration(resources.getOrDefault(name, List.of()));
        }
    }
}
