package io.github.ym0506.routecontract.shardingsphere552.internal;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.function.Executable;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.jar.JarFile;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FreshJvmMixedAnchorTest {
    private static final String SEPARATOR = System.getProperty("path.separator");
    private static final Set<String> ANCHOR_MODULES = Set.of("shardingsphere-infra-executor",
            "shardingsphere-infra-spi", "shardingsphere-infra-database-core",
            "shardingsphere-database-connector-core");

    @Test
    void actualMissingSpiMixedInputsHaveTheMixedDiagnosticInBothOrders() throws Exception {
        List<Executable> assertions = new ArrayList<>();
        for (List<String> tuple : List.of(List.of("5.5.2", "5.5.2", "5.5.3"),
                List.of("5.5.3", "5.5.2", "5.5.2"), List.of("5.5.3", "5.5.2", "5.5.3"))) {
            for (boolean reverse : List.of(false, true)) {
                List<String> classpath = classpath(tuple, reverse);
                assertions.add(() -> verifyCapture(classpath, tuple + " reverse=" + reverse, "RC_MIXED_SHARDINGSPHERE_RUNTIME"));
            }
        }
        assertAll(assertions);
    }

    @Test
    void exactWholeRuntimeWrongPairsRetainTheTopLevelUnsupportedDiagnostic() throws Exception {
        List<Executable> assertions = new ArrayList<>();
        for (String runtimeVersion : List.of("5.5.2", "5.5.3")) {
            String adapter = runtimeVersion.equals("5.5.2") ? "routecontract.adapter553Jar" : "routecontract.adapterJar";
            List<String> paths = new ArrayList<>(paths(required("routecontract.testClasses")));
            paths.add(required("routecontract.coreJar"));
            paths.add(required(adapter));
            paths.addAll(runtime(runtimeVersion));
            assertions.add(() -> verifyCapture(paths, "wrong adapter on whole runtime " + runtimeVersion,
                    "RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME"));
        }
        assertAll(assertions);
    }

    private static void verifyCapture(final List<String> classpath, final String label, final String marker)
            throws Exception {
        List<String> command = List.of(Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-cp", String.join(SEPARATOR, classpath), FreshJvmMixedAnchorProbe.class.getName(), marker);
        System.out.println("CAPTURE_DIAGNOSTIC_COMMAND " + command);
        Process process = new ProcessBuilder(command).redirectErrorStream(true).start();
        boolean finished = process.waitFor(Duration.ofSeconds(30).toMillis(), TimeUnit.MILLISECONDS);
        if (!finished) {
            process.destroyForcibly();
        }
        String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        System.out.println("CAPTURE_DIAGNOSTIC_RESULT label=" + label + " pid=" + process.pid() + " output=" + output);
        assertTrue(finished, label + " timed out: " + output);
        assertEquals(0, process.exitValue(), label + ": " + output);
        assertTrue(output.contains("ROUTECONTRACT_DIAGNOSTIC_REJECTED_BEFORE_ACTION marker=" + marker + " actionEntries=0"), label + ": " + output);
    }

    private static List<String> classpath(final List<String> tuple, final boolean reverse) throws Exception {
        String databaseVersion = tuple.get(2);
        String databaseModule = databaseVersion.equals("5.5.2")
                ? "shardingsphere-infra-database-core" : "shardingsphere-database-connector-core";
        List<String> anchors = new ArrayList<>(List.of(anchor(tuple.get(0), "shardingsphere-infra-executor"),
                anchor(tuple.get(1), "shardingsphere-infra-spi"), anchor(databaseVersion, databaseModule)));
        if (reverse) {
            Collections.reverse(anchors);
        }
        List<String> result = new ArrayList<>(paths(required("routecontract.testClasses")));
        result.add(required("routecontract.coreJar"));
        result.add(required(databaseVersion.equals("5.5.2") ? "routecontract.adapterJar" : "routecontract.adapter553Jar"));
        result.addAll(anchors);
        for (String path : runtime(databaseVersion)) {
            String name = Path.of(path).getFileName().toString();
            if (ANCHOR_MODULES.stream().noneMatch(module -> name.equals(module + "-" + databaseVersion + ".jar"))) {
                result.add(path);
            }
        }
        assertEquals(result.size(), Set.copyOf(result).size(), "duplicate physical classpath entry");
        return List.copyOf(result);
    }

    private static String anchor(final String version, final String module) throws Exception {
        List<String> selected = runtime(version).stream().filter(path -> Path.of(path).getFileName().toString()
                .equals(module + "-" + version + ".jar")).toList();
        assertEquals(1, selected.size(), "one exact official module must be resolved");
        try (JarFile jar = new JarFile(selected.get(0))) {
            assertEquals(version, jar.getManifest().getMainAttributes().getValue("Implementation-Version"));
        }
        return selected.get(0);
    }

    private static List<String> runtime(final String version) {
        return paths(required(version.equals("5.5.2")
                ? "routecontract.exact552RuntimeClasspath" : "routecontract.wrong553RuntimeClasspath"));
    }

    private static List<String> paths(final String value) {
        return Arrays.stream(value.split(java.util.regex.Pattern.quote(SEPARATOR)))
                .filter(path -> !path.isBlank()).toList();
    }

    private static String required(final String name) {
        String value = System.getProperty(name);
        assertTrue(value != null && !value.isBlank(), name + " is required");
        return value;
    }
}
