package io.github.ym0506.routecontract.structure;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ArtifactIsolationTest {

    private static final String SHARDINGSPHERE_BINARY_PREFIX = "org/apache/shardingsphere/";
    private static final String ROUTECONTRACT_BINARY_PREFIX = "io/github/ym0506/routecontract/";
    private static final String ADAPTER_BINARY_PREFIX =
            "io/github/ym0506/routecontract/shardingsphere553/internal/";
    private static final String HOOK_SERVICE =
            "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";
    private static final String RUNTIME_ADAPTER_SERVICE =
            "META-INF/services/io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter";
    private static final String CONSTRUCTION_GUARD_CLASS = ADAPTER_BINARY_PREFIX
            + "ShardingSphere553HookConstructionGuard.class";
    private static final String ROUTECONTRACT_GROUP = "io.github.ym0506.routecontract";
    private static final String SHARDINGSPHERE_GROUP = "org.apache.shardingsphere";
    private static final String TARGET_VERSION = "0.2.0";
    private static final String SHARDINGSPHERE_VERSION = "5.5.3";
    private static final String HOOK_SLOT_CAPABILITY =
            "routecontract-shardingsphere-hook-adapter";

    @Test
    void coreContainsNoShardingSphereBinaryReferencesOrServiceDescriptors() throws IOException {
        try (JarFile core = openJar("routecontract.coreJar")) {
            assertFalse(core.stream().anyMatch(entry -> entry.getName().equals(HOOK_SERVICE)));
            assertFalse(core.stream().anyMatch(entry -> entry.getName().startsWith(
                    "META-INF/services/org.apache.shardingsphere.")));

            List<String> offendingClasses = new ArrayList<>();
            for (JarEntry entry : core.stream().filter(ArtifactIsolationTest::isClass).toList()) {
                byte[] bytes = core.getInputStream(entry).readAllBytes();
                if (contains(bytes, SHARDINGSPHERE_BINARY_PREFIX)) {
                    offendingClasses.add(entry.getName());
                }
            }
            assertEquals(List.of(), offendingClasses,
                    "core class files must not reference ShardingSphere binary names");
        }
    }

    @Test
    void adapterContainsOnlyVersionSpecificClassesAndNoCoreDuplicates() throws IOException {
        try (JarFile core = openJar("routecontract.coreJar");
                JarFile adapter = openJar("routecontract.adapterJar")) {
            Set<String> coreClasses = classEntries(core);
            Set<String> adapterClasses = classEntries(adapter);

            Set<String> duplicateClasses = new HashSet<>(coreClasses);
            duplicateClasses.retainAll(adapterClasses);
            assertEquals(Set.of(), duplicateClasses,
                    "core-owned class paths must not be copied into the adapter");
            assertTrue(adapterClasses.stream().allMatch(name -> name.startsWith(ADAPTER_BINARY_PREFIX)),
                    "adapter must own only its exact-version internal package: " + adapterClasses);
            assertTrue(adapterClasses.stream().noneMatch(name -> name.startsWith(ROUTECONTRACT_BINARY_PREFIX)
                    && !name.startsWith(ADAPTER_BINARY_PREFIX)));
        }
    }

    @Test
    void adapterOwnsBothExactSingleLineServiceDescriptors() throws IOException {
        try (JarFile adapter = openJar("routecontract.adapterJar")) {
            assertEquals(
                    List.of("io.github.ym0506.routecontract.shardingsphere553.internal."
                            + "RouteContract553SqlExecutionHook"),
                    serviceLines(adapter, HOOK_SERVICE));
            assertEquals(
                    List.of("io.github.ym0506.routecontract.shardingsphere553.internal."
                            + "ShardingSphere553RuntimeAdapter"),
                    serviceLines(adapter, RUNTIME_ADAPTER_SERVICE));
        }
    }

    @Test
    void hookConstructionGuardHasNoRecursiveServiceOrCoreBridgeLinkage() throws IOException {
        try (JarFile adapter = openJar("routecontract.adapterJar")) {
            JarEntry guard = adapter.getJarEntry(CONSTRUCTION_GUARD_CLASS);
            assertTrue(guard != null, CONSTRUCTION_GUARD_CLASS + " must exist");
            byte[] bytes = adapter.getInputStream(guard).readAllBytes();

            assertFalse(contains(bytes, "java/util/ServiceLoader"));
            assertFalse(contains(bytes, "org/apache/shardingsphere/infra/spi/ShardingSphereServiceLoader"));
            assertFalse(contains(bytes, "io/github/ym0506/routecontract/spi/RouteContractHookBridge"));
        }
    }

    @Test
    void adapterDoesNotLinkToACoreOwnedAttemptTokenDescriptor() throws IOException {
        try (JarFile adapter = openJar("routecontract.adapterJar")) {
            JarEntry hook = adapter.getJarEntry(ADAPTER_BINARY_PREFIX
                    + "RouteContract553SqlExecutionHook.class");
            assertTrue(hook != null, "exact hook class must exist");
            byte[] bytes = adapter.getInputStream(hook).readAllBytes();

            assertFalse(contains(bytes,
                    "io/github/ym0506/routecontract/spi/RouteContractHookBridge$Attempt"));
        }
    }

    @Test
    void publicationMetadataPinsTheCoordinatedVersionAndExact553Runtime() throws IOException {
        String pom = Files.readString(requiredPath("routecontract.adapterPom"));
        assertTrue(pom.contains("<version>" + TARGET_VERSION + "</version>"));
        assertFalse(pom.contains("<version>0.1.2</version>"));
        assertFalse(pom.contains("5.5.2"));
        assertPomDependency(pom, ROUTECONTRACT_GROUP, "routecontract-core", TARGET_VERSION, "compile");
        assertPomDependency(pom, SHARDINGSPHERE_GROUP,
                "shardingsphere-infra-executor", SHARDINGSPHERE_VERSION, "runtime");
        assertPomManagedDependency(pom, SHARDINGSPHERE_GROUP,
                "shardingsphere-infra-spi", SHARDINGSPHERE_VERSION);
        assertPomManagedDependency(pom, SHARDINGSPHERE_GROUP,
                "shardingsphere-database-connector-core", SHARDINGSPHERE_VERSION);

        String module = withoutWhitespace(Files.readString(
                requiredPath("routecontract.adapterModuleMetadata")));
        assertTrue(module.contains("\"version\":\"" + TARGET_VERSION + "\""));
        assertFalse(module.contains("\"version\":\"0.1.2\""));
        assertFalse(module.contains("5.5.2"));
        assertEquals(2, occurrences(module,
                "{\"group\":\"" + ROUTECONTRACT_GROUP + "\",\"name\":\""
                        + HOOK_SLOT_CAPABILITY + "\",\"version\":\"1\"}"));
        assertStrictModule(module, "shardingsphere-infra-executor", SHARDINGSPHERE_VERSION);
        assertStrictModule(module, "shardingsphere-infra-spi", SHARDINGSPHERE_VERSION);
        assertStrictModule(module, "shardingsphere-database-connector-core", SHARDINGSPHERE_VERSION);
    }

    private static JarFile openJar(final String propertyName) throws IOException {
        String value = System.getProperty(propertyName);
        assertTrue(value != null && !value.isBlank(), propertyName + " must identify a built JAR");
        return new JarFile(Path.of(value).toFile());
    }

    private static Path requiredPath(final String propertyName) {
        String value = System.getProperty(propertyName);
        assertTrue(value != null && !value.isBlank(), propertyName + " must identify generated metadata");
        Path result = Path.of(value);
        assertTrue(Files.isRegularFile(result), propertyName + " must be a regular file: " + result);
        return result;
    }

    private static void assertPomDependency(
            final String pom,
            final String group,
            final String artifact,
            final String version,
            final String scope) {
        String expected = "<dependency>\n      <groupId>" + group + "</groupId>\n"
                + "      <artifactId>" + artifact + "</artifactId>\n"
                + "      <version>" + version + "</version>\n"
                + "      <scope>" + scope + "</scope>\n    </dependency>";
        assertTrue(pom.contains(expected), "missing exact POM dependency: " + artifact);
    }

    private static void assertPomManagedDependency(
            final String pom,
            final String group,
            final String artifact,
            final String version) {
        int managementStart = pom.indexOf("<dependencyManagement>");
        int managementEnd = pom.indexOf("</dependencyManagement>");
        assertTrue(managementStart >= 0 && managementEnd > managementStart,
                "POM dependencyManagement must be present");
        String management = pom.substring(managementStart, managementEnd);
        String expected = "<groupId>" + group + "</groupId>\n"
                + "        <artifactId>" + artifact + "</artifactId>\n"
                + "        <version>" + version + "</version>";
        assertTrue(management.contains(expected), "missing exact managed dependency: " + artifact);
    }

    private static void assertStrictModule(
            final String moduleMetadata,
            final String module,
            final String version) {
        int moduleIndex = moduleMetadata.indexOf("\"module\":\"" + module + "\"");
        assertTrue(moduleIndex >= 0, "missing Gradle metadata module: " + module);
        int entryStart = moduleMetadata.lastIndexOf("{\"group\":", moduleIndex);
        int entryEnd = matchingObjectEnd(moduleMetadata, entryStart);
        String entry = moduleMetadata.substring(entryStart, entryEnd + 1);
        assertTrue(entry.contains("\"strictly\":\"" + version + "\""),
                "missing strict Gradle version for " + module + ": " + entry);
        assertTrue(entry.contains("\"requires\":\"" + version + "\""),
                "missing required Gradle version for " + module + ": " + entry);
    }

    private static int matchingObjectEnd(final String value, final int start) {
        assertTrue(start >= 0, "JSON object start must exist");
        int depth = 0;
        for (int index = start; index < value.length(); index++) {
            char current = value.charAt(index);
            if (current == '{') {
                depth++;
            } else if (current == '}' && --depth == 0) {
                return index;
            }
        }
        throw new AssertionError("unterminated JSON object");
    }

    private static String withoutWhitespace(final String value) {
        return value.replaceAll("\\s+", "");
    }

    private static int occurrences(final String value, final String expected) {
        int result = 0;
        int from = 0;
        while ((from = value.indexOf(expected, from)) >= 0) {
            result++;
            from += expected.length();
        }
        return result;
    }

    private static Set<String> classEntries(final JarFile jar) {
        Set<String> result = new HashSet<>();
        jar.stream().filter(ArtifactIsolationTest::isClass).map(JarEntry::getName).forEach(result::add);
        return Set.copyOf(result);
    }

    private static boolean isClass(final JarEntry entry) {
        return !entry.isDirectory() && entry.getName().endsWith(".class");
    }

    private static boolean contains(final byte[] haystack, final String needle) {
        byte[] expected = needle.getBytes(StandardCharsets.US_ASCII);
        for (int offset = 0; offset <= haystack.length - expected.length; offset++) {
            int index = 0;
            while (index < expected.length && haystack[offset + index] == expected[index]) {
                index++;
            }
            if (index == expected.length) {
                return true;
            }
        }
        return false;
    }

    private static List<String> serviceLines(final JarFile jar, final String path) throws IOException {
        JarEntry entry = jar.getJarEntry(path);
        assertTrue(entry != null, path + " must exist");
        return new String(jar.getInputStream(entry).readAllBytes(), StandardCharsets.UTF_8)
                .lines()
                .toList();
    }
}
