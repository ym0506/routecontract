package io.github.ym0506.routecontract.structure;

import org.junit.jupiter.api.Test;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CorePublicationStructureTest {

    private static final String GROUP = "io.github.ym0506.routecontract";
    private static final String ARTIFACT = "routecontract-core";
    private static final String VERSION = "0.2.0";
    private static final String MODULE_NAME = "io.github.ym0506.routecontract.core";
    private static final String CORE_OWNER_CAPABILITY = "routecontract-core-owner";
    private static final String TTL_VERSION = "2.14.2";
    private static final String JACKSON_VERSION = "3.1.5";
    private static final String SHARDINGSPHERE_BINARY_PREFIX = "org/apache/shardingsphere/";
    private static final Pattern MODULE_DEPENDENCY = Pattern.compile(
            "\\\"group\\\":\\\"([^\\\"]+)\\\",\\\"module\\\":\\\"([^\\\"]+)\\\"");

    @Test
    void jarHasExactCoordinatedIdentityAndNoServiceOrShardingSphereContent() throws IOException {
        Path jarPath = requiredPath("routecontract.coreJar");
        assertEquals(ARTIFACT + "-" + VERSION + ".jar", jarPath.getFileName().toString());

        try (JarFile jar = new JarFile(jarPath.toFile())) {
            Attributes attributes = jar.getManifest().getMainAttributes();
            assertEquals(MODULE_NAME, attributes.getValue("Automatic-Module-Name"));
            assertEquals(GROUP + ":" + ARTIFACT, attributes.getValue("Implementation-Title"));
            assertEquals(VERSION, attributes.getValue("Implementation-Version"));
            assertFalse(jar.stream().anyMatch(entry -> entry.getName().equals("module-info.class")),
                    "0.2 deliberately supports the classpath, not the JPMS module path");

            assertFalse(jar.stream().anyMatch(entry -> entry.getName().startsWith("META-INF/services/")),
                    "the core artifact must not provide runtime services");

            List<String> offendingClasses = new ArrayList<>();
            for (JarEntry entry : jar.stream().filter(CorePublicationStructureTest::isClass).toList()) {
                if (contains(jar.getInputStream(entry).readAllBytes(), SHARDINGSPHERE_BINARY_PREFIX)) {
                    offendingClasses.add(entry.getName());
                }
            }
            assertEquals(List.of(), offendingClasses,
                    "the version-neutral core must not link to ShardingSphere binaries");
        }
    }

    @Test
    void pomHasOnlyTheTwoVersionNeutralRuntimeDependencies() throws Exception {
        Element project = parsePom(requiredPath("routecontract.corePom"));
        assertEquals(GROUP, directChildText(project, "groupId"));
        assertEquals(ARTIFACT, directChildText(project, "artifactId"));
        assertEquals(VERSION, directChildText(project, "version"));

        NodeList dependencyNodes = project.getElementsByTagName("dependency");
        assertEquals(2, dependencyNodes.getLength(), "core POM dependency set must remain minimal");

        Set<PomDependency> dependencies = Set.of(
                pomDependency((Element) dependencyNodes.item(0)),
                pomDependency((Element) dependencyNodes.item(1)));
        assertEquals(Set.of(
                new PomDependency("com.alibaba", "transmittable-thread-local", TTL_VERSION, "runtime"),
                new PomDependency("tools.jackson.core", "jackson-core", JACKSON_VERSION, "runtime")),
                dependencies);
        assertTrue(dependencies.stream().noneMatch(dependency ->
                dependency.group().startsWith("org.apache.shardingsphere")));
    }

    @Test
    void gradleMetadataHasExactIdentityDependenciesAndCoreOwnerCapability() throws IOException {
        String module = withoutWhitespace(Files.readString(
                requiredPath("routecontract.coreModuleMetadata"), StandardCharsets.UTF_8));
        assertTrue(module.contains("\"component\":{\"group\":\"" + GROUP
                + "\",\"module\":\"" + ARTIFACT + "\",\"version\":\"" + VERSION + "\""));
        assertFalse(module.contains("org.apache.shardingsphere"));

        String apiElements = namedVariant(module, "apiElements");
        String runtimeElements = namedVariant(module, "runtimeElements");
        assertCoreOwnerCapabilities(apiElements);
        assertCoreOwnerCapabilities(runtimeElements);
        assertFalse(apiElements.contains("\"dependencies\":"),
                "implementation dependencies must not leak into the API variant");

        String runtimeDependencies = arrayValue(runtimeElements, "dependencies");
        Matcher matcher = MODULE_DEPENDENCY.matcher(runtimeDependencies);
        List<String> coordinates = new ArrayList<>();
        while (matcher.find()) {
            coordinates.add(matcher.group(1) + ":" + matcher.group(2));
        }
        assertEquals(Set.of(
                "com.alibaba:transmittable-thread-local",
                "tools.jackson.core:jackson-core"), Set.copyOf(coordinates));
        assertEquals(2, coordinates.size(), "runtime variant must contain exactly two dependencies");
        assertRequiredVersion(runtimeDependencies,
                "com.alibaba", "transmittable-thread-local", TTL_VERSION);
        assertRequiredVersion(runtimeDependencies,
                "tools.jackson.core", "jackson-core", JACKSON_VERSION);
    }

    private static void assertCoreOwnerCapabilities(final String variant) {
        String capabilities = arrayValue(variant, "capabilities");
        assertTrue(capabilities.contains("{\"group\":\"" + GROUP + "\",\"name\":\""
                + ARTIFACT + "\",\"version\":\"" + VERSION + "\"}"));
        assertTrue(capabilities.contains("{\"group\":\"" + GROUP + "\",\"name\":\""
                + CORE_OWNER_CAPABILITY + "\",\"version\":\"1\"}"));
    }

    private static void assertRequiredVersion(
            final String dependencies,
            final String group,
            final String module,
            final String version) {
        String prefix = "{\"group\":\"" + group + "\",\"module\":\"" + module
                + "\",\"version\":{\"requires\":\"" + version + "\"}";
        assertTrue(dependencies.contains(prefix), "missing exact dependency version: " + prefix);
    }

    private static Element parsePom(final Path path) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
        factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        return factory.newDocumentBuilder().parse(path.toFile()).getDocumentElement();
    }

    private static PomDependency pomDependency(final Element dependency) {
        return new PomDependency(
                directChildText(dependency, "groupId"),
                directChildText(dependency, "artifactId"),
                directChildText(dependency, "version"),
                directChildText(dependency, "scope"));
    }

    private static String directChildText(final Element element, final String name) {
        for (Node child = element.getFirstChild(); child != null; child = child.getNextSibling()) {
            if (child instanceof Element childElement
                    && childElement.getLocalName() == null
                    && childElement.getTagName().equals(name)) {
                return childElement.getTextContent().trim();
            }
        }
        throw new AssertionError("missing direct XML child " + name + " under " + element.getTagName());
    }

    private static String namedVariant(final String module, final String name) {
        int nameIndex = module.indexOf("\"name\":\"" + name + "\"");
        assertTrue(nameIndex >= 0, "missing Gradle metadata variant " + name);
        int start = module.lastIndexOf('{', nameIndex);
        return objectValue(module, start);
    }

    private static String objectValue(final String value, final int start) {
        return delimitedValue(value, start, '{', '}');
    }

    private static String arrayValue(final String object, final String name) {
        int property = object.indexOf("\"" + name + "\":[");
        assertTrue(property >= 0, "missing JSON array " + name);
        int start = object.indexOf('[', property);
        return delimitedValue(object, start, '[', ']');
    }

    private static String delimitedValue(
            final String value,
            final int start,
            final char opening,
            final char closing) {
        assertTrue(start >= 0 && value.charAt(start) == opening, "missing JSON delimiter " + opening);
        int depth = 0;
        boolean quoted = false;
        boolean escaped = false;
        for (int index = start; index < value.length(); index++) {
            char current = value.charAt(index);
            if (quoted) {
                if (escaped) {
                    escaped = false;
                } else if (current == '\\') {
                    escaped = true;
                } else if (current == '"') {
                    quoted = false;
                }
            } else if (current == '"') {
                quoted = true;
            } else if (current == opening) {
                depth++;
            } else if (current == closing && --depth == 0) {
                return value.substring(start, index + 1);
            }
        }
        throw new AssertionError("unterminated JSON value beginning at " + start);
    }

    private static Path requiredPath(final String propertyName) {
        String value = System.getProperty(propertyName);
        assertNotNull(value, propertyName + " must identify generated publication content");
        assertFalse(value.isBlank(), propertyName + " must identify generated publication content");
        Path result = Path.of(value);
        assertTrue(Files.isRegularFile(result), propertyName + " must be a regular file: " + result);
        return result;
    }

    private static String withoutWhitespace(final String value) {
        return value.replaceAll("\\s+", "");
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

    private record PomDependency(String group, String artifact, String version, String scope) {
    }
}
