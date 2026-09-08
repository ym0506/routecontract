package io.github.ym0506.routecontract.shardingsphere552.internal;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FreshJvmCompatibilityFailureTest {

    private static final String PATH_SEPARATOR = System.getProperty("path.separator");

    @TempDir
    Path temporaryDirectory;

    @Test
    void namedDualAdaptersRejectModulePathBeforeDescriptorMultiplicityOnBothExactRuntimes() throws Exception {
        String adapter552 = requiredProperty("routecontract.adapterJar");
        String adapter553 = requiredProperty("routecontract.adapter553Jar");
        Path launcher = temporaryDirectory.resolve("NamedProviderDiscoveryLauncher.java");
        // The existing probe shares an adapter package. Load only that classpath test entry point
        // through a child loader so the named module's package mapping cannot hide the main class.
        // ShardingSphere and the real named providers still use the system application loader.
        Files.writeString(launcher, """
                import java.net.URL;
                import java.net.URLClassLoader;
                import java.nio.file.Path;
                import java.util.Arrays;
                import java.util.regex.Pattern;

                class NamedProviderDiscoveryLauncher {
                    public static void main(String[] args) throws Exception {
                        URL[] roots = Arrays.stream(args[0].split(Pattern.quote(System.getProperty("path.separator"))))
                                .filter(path -> !path.isBlank())
                                .map(path -> {
                                    try {
                                        return Path.of(path).toUri().toURL();
                                    } catch (java.net.MalformedURLException failure) {
                                        throw new IllegalArgumentException(failure);
                                    }
                                }).toArray(URL[]::new);
                        try (URLClassLoader probeLoader = new URLClassLoader(roots, ClassLoader.getSystemClassLoader())) {
                            Class<?> probe = Class.forName(args[1], true, probeLoader);
                            probe.getMethod("main", String[].class).invoke(null, (Object) new String[] {args[2]});
                        }
                    }
                }
                """, StandardCharsets.UTF_8);

        assertAll(
                () -> runNamedProbe(launcher, List.of(adapter552, adapter553), "routecontract.exact552RuntimeClasspath"),
                () -> runNamedProbe(launcher, List.of(adapter553, adapter552), "routecontract.exact552RuntimeClasspath"),
                () -> runNamedProbe(launcher, List.of(adapter552, adapter553), "routecontract.wrong553RuntimeClasspath"),
                () -> runNamedProbe(launcher, List.of(adapter553, adapter552), "routecontract.wrong553RuntimeClasspath"));
    }

    private static void runNamedProbe(
            final Path launcher,
            final List<String> adapterOrder,
            final String runtimeClasspathProperty) throws Exception {
        List<String> modules = new ArrayList<>();
        modules.add(requiredProperty("routecontract.coreJar"));
        modules.addAll(adapterOrder);
        List<String> classpath = new ArrayList<>();
        addPathList(classpath, requiredProperty("routecontract.testClasses"));
        addPathList(classpath, requiredProperty(runtimeClasspathProperty));
        String expectedMarker = "RC_UNSUPPORTED_MODULE_PATH";
        List<String> command = List.of(
                Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "--module-path", String.join(PATH_SEPARATOR, modules),
                "--add-modules", "java.se,ALL-MODULE-PATH",
                "-cp", String.join(PATH_SEPARATOR, classpath),
                launcher.toString(),
                requiredProperty("routecontract.testClasses"),
                FreshJvmProviderDiscoveryProbe.class.getName(),
                expectedMarker);
        System.out.println("NAMED_PROVIDER_COMMAND " + command);
        Process process = new ProcessBuilder(command).redirectErrorStream(true).start();
        boolean finished = process.waitFor(Duration.ofSeconds(30).toMillis(), TimeUnit.MILLISECONDS);
        if (!finished) {
            process.destroyForcibly();
        }
        String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        System.out.println("NAMED_PROVIDER_RESULT runtime=" + runtimeClasspathProperty
                + " adapters=" + adapterOrder + " pid=" + process.pid() + " output=" + output);
        assertTrue(finished, "fresh JVM named provider probe timed out: " + output);
        assertEquals(0, process.exitValue(), output);
        assertTrue(output.contains("ROUTECONTRACT_EXPECTED_GUARD_FAILURE " + expectedMarker + ":"), output);
        assertFalse(output.contains("RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS:"), output);
        assertFalse(output.contains("AbstractMethodError"), output);
        assertFalse(output.contains("NoSuchMethodError"), output);
    }

    @Test
    void adapter552OnRuntime553FailsBeforeAnIncompatibleCallbackCanRun() throws Exception {
        String output = runProbe(
                singleAdapterClasspath(
                        requiredProperty("routecontract.adapterJar"),
                        "routecontract.wrong553RuntimeClasspath"),
                "RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME");

        assertFalse(output.contains("AbstractMethodError"), output);
        assertFalse(output.contains("NoSuchMethodError"), output);
    }

    @Test
    void adapter553OnRuntime552FailsBeforeAnIncompatibleCallbackCanRun() throws Exception {
        String output = runProbe(
                singleAdapterClasspath(
                        requiredProperty("routecontract.adapter553Jar"),
                        "routecontract.exact552RuntimeClasspath"),
                "RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME");

        assertFalse(output.contains("AbstractMethodError"), output);
        assertFalse(output.contains("NoSuchMethodError"), output);
    }

    @Test
    void dualAdaptersFailIdenticallyInBothClasspathOrdersOnBothExactRuntimes() throws Exception {
        String adapter552 = requiredProperty("routecontract.adapterJar");
        String adapter553 = requiredProperty("routecontract.adapter553Jar");

        String runtime552FirstOrder = runProbe(
                dualAdapterClasspath(
                        List.of(adapter552, adapter553),
                        "routecontract.exact552RuntimeClasspath"),
                "RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS");
        String runtime552SecondOrder = runProbe(
                dualAdapterClasspath(
                        List.of(adapter553, adapter552),
                        "routecontract.exact552RuntimeClasspath"),
                "RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS");
        String runtime553FirstOrder = runProbe(
                dualAdapterClasspath(
                        List.of(adapter552, adapter553),
                        "routecontract.wrong553RuntimeClasspath"),
                "RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS");
        String runtime553SecondOrder = runProbe(
                dualAdapterClasspath(
                        List.of(adapter553, adapter552),
                        "routecontract.wrong553RuntimeClasspath"),
                "RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS");

        for (String output : List.of(
                runtime552FirstOrder,
                runtime552SecondOrder,
                runtime553FirstOrder,
                runtime553SecondOrder)) {
            assertTrue(output.contains("unexpected RouteContract provider descriptors"), output);
            assertFalse(output.contains("AbstractMethodError"), output);
            assertFalse(output.contains("NoSuchMethodError"), output);
        }
    }

    private static List<String> dualAdapterClasspath(
            final List<String> adapterOrder,
            final String runtimeClasspathProperty) {
        List<String> result = new ArrayList<>();
        addPathList(result, requiredProperty("routecontract.testClasses"));
        result.addAll(adapterOrder);
        result.add(requiredProperty("routecontract.coreJar"));
        addPathList(result, requiredProperty(runtimeClasspathProperty));
        return List.copyOf(result);
    }

    private static List<String> singleAdapterClasspath(
            final String adapter,
            final String runtimeClasspathProperty) {
        List<String> result = new ArrayList<>();
        addPathList(result, requiredProperty("routecontract.testClasses"));
        result.add(adapter);
        result.add(requiredProperty("routecontract.coreJar"));
        addPathList(result, requiredProperty(runtimeClasspathProperty));
        return List.copyOf(result);
    }

    private static String runProbe(
            final List<String> classpath,
            final String expectedMarker) throws Exception {
        List<String> command = List.of(
                Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-cp",
                String.join(PATH_SEPARATOR, classpath),
                FreshJvmProviderDiscoveryProbe.class.getName(),
                expectedMarker);
        Process process = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .start();
        boolean finished = process.waitFor(Duration.ofSeconds(30).toMillis(), TimeUnit.MILLISECONDS);
        if (!finished) {
            process.destroyForcibly();
        }
        String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);

        assertTrue(finished, "fresh JVM compatibility probe timed out: " + output);
        assertEquals(0, process.exitValue(), output);
        assertTrue(output.contains("ROUTECONTRACT_EXPECTED_GUARD_FAILURE"), output);
        assertTrue(output.contains(expectedMarker + ":"), output);
        return output;
    }

    private static void addPathList(final List<String> target, final String value) {
        Arrays.stream(value.split(java.util.regex.Pattern.quote(PATH_SEPARATOR)))
                .filter(path -> !path.isBlank())
                .forEach(target::add);
    }

    private static String requiredProperty(final String name) {
        String value = System.getProperty(name);
        assertTrue(value != null && !value.isBlank(), name + " must be configured by the build");
        return value;
    }
}
