package io.github.ym0506.routecontract.shardingsphere552.internal;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FreshJvmGuardFailureTest {

    @TempDir
    Path temporaryDirectory;

    @Test
    void staleBridgeDescriptorFailsWithAStableMarkerBeforeTheFirstBridgeInvocation() throws Exception {
        String output = runProbe(compileStaleCore(Fault.STALE_BRIDGE));

        assertTrue(output.contains("RouteContractHookBridge#noopAttempt"), output);
    }

    @Test
    void staleRuntimeAdapterInterfaceFailsBeforeServiceProviderInstantiation() throws Exception {
        String output = runProbe(compileStaleCore(Fault.STALE_RUNTIME_ADAPTER_INTERFACE));

        assertTrue(output.contains("RouteContractRuntimeAdapter#verifyRuntime"), output);
    }

    private String runProbe(final Path staleCore) throws Exception {
        List<String> command = new ArrayList<>();
        command.add(Path.of(System.getProperty("java.home"), "bin", "java").toString());
        command.add("-cp");
        command.add(staleCore + System.getProperty("path.separator") + classpathWithoutCurrentCore());
        command.add(FreshJvmGuardProbe.class.getName());
        command.add("RC_ADAPTER_CLASSLOADER_MISMATCH");

        Process process = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .start();
        boolean finished = process.waitFor(Duration.ofSeconds(20).toMillis(), TimeUnit.MILLISECONDS);
        if (!finished) {
            process.destroyForcibly();
        }
        String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);

        assertTrue(finished, "fresh JVM guard probe timed out: " + output);
        assertEquals(0, process.exitValue(), output);
        assertTrue(output.contains("ROUTECONTRACT_EXPECTED_GUARD_FAILURE"), output);
        assertFalse(output.startsWith("java.lang.NoSuchMethodError"), output);
        assertFalse(output.startsWith("java.lang.AbstractMethodError"), output);
        return output;
    }

    private Path compileStaleCore(final Fault fault) throws IOException {
        Path sources = Files.createDirectories(temporaryDirectory.resolve("sources"));
        Path classes = Files.createDirectories(temporaryDirectory.resolve("classes"));
        List<Path> sourceFiles = List.of(
                writeSource(sources, "io/github/ym0506/routecontract/RouteContract.java", """
                        package io.github.ym0506.routecontract;
                        public final class RouteContract { private RouteContract() { } }
                        """),
                writeSource(sources, "io/github/ym0506/routecontract/ShardingSphereRuntimeIdentity.java", """
                        package io.github.ym0506.routecontract;
                        public final class ShardingSphereRuntimeIdentity { }
                        """),
                writeSource(
                        sources,
                        "io/github/ym0506/routecontract/spi/RouteContractRuntimeAdapter.java",
                        runtimeAdapterSource(fault)),
                writeSource(
                        sources,
                        "io/github/ym0506/routecontract/spi/RouteContractHookBridge.java",
                        bridgeSource(fault)),
                writeSource(sources, "io/github/ym0506/routecontract/internal/CaptureRegistry.java", """
                        package io.github.ym0506.routecontract.internal;
                        import java.util.List;
                        public final class CaptureRegistry {
                            private CaptureRegistry() { }
                            public static Object noopAttemptFromAdapter() { return new Object(); }
                            public static Object startAttemptFromAdapter(String dataSourceName, String sql,
                                    List<Object> parameters, boolean trunkThread) { return new Object(); }
                            public static void finishCallbackReturnedFromAdapter(Object attempt) { }
                            public static void finishFailureFromAdapter(Object attempt, Exception cause) { }
                            public static void recordCurrentErrorFromAdapter(String errorCode) { }
                        }
                        """));
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        assertTrue(compiler != null, "fresh-JVM negative fixture requires a JDK compiler");
        List<String> compilerArguments = new ArrayList<>(List.of("-d", classes.toString()));
        sourceFiles.stream().map(Path::toString).forEach(compilerArguments::add);
        int result = compiler.run(null, null, null, compilerArguments.toArray(String[]::new));
        assertEquals(0, result, "stale core fixture compilation failed");

        Path jar = temporaryDirectory.resolve("stale-routecontract-core.jar");
        try (JarOutputStream output = new JarOutputStream(Files.newOutputStream(jar));
                var paths = Files.walk(classes)) {
            for (Path path : paths.filter(Files::isRegularFile).sorted().toList()) {
                String name = classes.relativize(path).toString().replace(path.getFileSystem().getSeparator(), "/");
                JarEntry entry = new JarEntry(name);
                entry.setTime(0L);
                output.putNextEntry(entry);
                Files.copy(path, output);
                output.closeEntry();
            }
        }
        return jar;
    }

    private static String runtimeAdapterSource(final Fault fault) {
        if (fault == Fault.STALE_RUNTIME_ADAPTER_INTERFACE) {
            return """
                    package io.github.ym0506.routecontract.spi;
                    public interface RouteContractRuntimeAdapter { Object verifyRuntime(); }
                    """;
        }
        return """
                package io.github.ym0506.routecontract.spi;
                import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
                public interface RouteContractRuntimeAdapter {
                    ShardingSphereRuntimeIdentity verifyRuntime();
                }
                """;
    }

    private static String bridgeSource(final Fault fault) {
        String noop = fault == Fault.STALE_BRIDGE
                ? "public static String noopAttempt() { return \"stale\"; }"
                : "public static Object noopAttempt() { return new Object(); }";
        return """
                package io.github.ym0506.routecontract.spi;
                import java.util.List;
                public final class RouteContractHookBridge {
                    private RouteContractHookBridge() { }
                    NOOP_METHOD
                    public static Object start(String dataSourceName, String sql,
                            List<Object> parameters, boolean trunkThread) { return new Object(); }
                    public static void finishCallbackReturned(Object attempt) { }
                    public static void finishFailure(Object attempt, Exception cause) { }
                    public static void recordDiagnostic(String errorCode) { }
                }
                """.replace("NOOP_METHOD", noop);
    }

    private static Path writeSource(final Path root, final String relativePath, final String source)
            throws IOException {
        Path target = root.resolve(relativePath);
        Files.createDirectories(target.getParent());
        Files.writeString(target, source, StandardCharsets.UTF_8);
        return target;
    }

    private static String classpathWithoutCurrentCore() {
        String separator = System.getProperty("path.separator");
        return List.of(System.getProperty("java.class.path").split(java.util.regex.Pattern.quote(separator)))
                .stream()
                .map(Path::of)
                .filter(path -> !path.toString().replace('\\', '/').contains("/routecontract-core/build/"))
                .map(Path::toString)
                .reduce((left, right) -> left + separator + right)
                .orElseThrow();
    }

    private enum Fault {
        STALE_BRIDGE,
        STALE_RUNTIME_ADAPTER_INTERFACE
    }
}
