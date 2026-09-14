package io.github.ym0506.routecontract.packaged;

import org.junit.jupiter.api.extension.AfterAllCallback;
import org.junit.jupiter.api.extension.BeforeAllCallback;
import org.junit.jupiter.api.extension.ExtensionContext;

import java.net.JarURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Supplemental origin observation; it adds no corpus test and never instantiates a hook. */
public final class PackagedCorpusProvenance implements BeforeAllCallback, AfterAllCallback {
    private static final String CURRENT_ENTRY = "io.github.ym0506.routecontract.api.RouteContract";
    private static final String HOOK_SPI = "org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";

    @Override
    public void beforeAll(final ExtensionContext context) throws Exception {
        observe(context, "before");
    }

    @Override
    public void afterAll(final ExtensionContext context) throws Exception {
        observe(context, "after");
    }

    private static void observe(final ExtensionContext context, final String phase) throws Exception {
        Class<?> suite = context.getRequiredTestClass();
        List<String> expected = Arrays.asList(required("packaged.expectedSuites").split(","));
        if (!expected.contains(suite.getName())) throw new IllegalStateException("Unexpected corpus suite");
        if (!"false".equals(System.getProperty("routecontract.generate552Evidence"))) {
            throw new IllegalStateException("Golden comparison must be enabled, generation disabled");
        }
        if (Runtime.version().feature() != 17) throw new IllegalStateException("Java 17 corpus required");
        String runtime = required("packaged.runtime");
        if (!List.of("5.5.2", "5.5.3").contains(runtime)) throw new IllegalStateException("Exact runtime required");
        String suffix = runtime.replace(".", "");
        String adapter = runtime.equals("5.5.2") ? "routecontract-shardingsphere-5.5.2" : "routecontract-shardingsphere-5.5";
        String hook = "io.github.ym0506.routecontract.shardingsphere" + suffix + ".internal.RouteContract" + suffix + "SqlExecutionHook";
        String runtimeAdapter = "io.github.ym0506.routecontract.shardingsphere" + suffix + ".internal.ShardingSphere" + suffix + "RuntimeAdapter";
        ClassLoader loader = suite.getClassLoader();
        Map<String, String> data = new LinkedHashMap<>();
        data.put("suite", suite.getName());
        data.put("phase", phase);
        data.put("runtime", runtime);
        data.put("pid", Long.toString(ProcessHandle.current().pid()));
        data.put("javaVersion", Runtime.version().toString());
        data.put("loader", loader.getClass().getName() + "@" + Integer.toHexString(System.identityHashCode(loader)));
        data.put("suiteCodeSource", suite.getProtectionDomain().getCodeSource().getLocation().toString());
        data.put("generationEnabled", System.getProperty("routecontract.generate552Evidence"));
        data.put("currentEntry", CURRENT_ENTRY);
        Path core = jar(CURRENT_ENTRY, loader, "routecontract-core", required("packaged.coreSha256"));
        for (String name : List.of("io.github.ym0506.routecontract.RouteSnapshot",
                "io.github.ym0506.routecontract.manifest.ManifestVerifier",
                "io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter")) {
            if (!core.equals(jar(name, loader, "routecontract-core", required("packaged.coreSha256")))) {
                throw new IllegalStateException("Core class origins differ");
            }
        }
        Path adapterJar = jar(hook, loader, adapter, required("packaged.adapterSha256"));
        if (!adapterJar.equals(jar(runtimeAdapter, loader, adapter, required("packaged.adapterSha256")))) {
            throw new IllegalStateException("Adapter class origins differ");
        }
        verifyProvider(loader, HOOK_SPI, hook, adapterJar);
        verifyProvider(loader, "io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter", runtimeAdapter, adapterJar);
        data.put("coreJar", core.toString());
        data.put("coreSha256", digest(core));
        data.put("adapterJar", adapterJar.toString());
        data.put("adapterSha256", digest(adapterJar));
        data.put("hookClass", hook);
        data.put("runtimeAdapterClass", runtimeAdapter);
        data.put("providerDescriptors", "EXACT_PACKAGED");
        Path destination = Path.of(required("packaged.provenanceDirectory"));
        Files.createDirectories(destination);
        List<String> fields = new ArrayList<>();
        data.forEach((key, value) -> fields.add(quote(key) + ":" + quote(value)));
        Files.writeString(destination.resolve(suite.getName() + "-" + phase + ".json"),
                "{" + String.join(",", fields) + "}\n", StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        System.out.println("ROUTECONTRACT_PACKAGED_CORPUS_ORIGIN suite=" + suite.getName()
                + " phase=" + phase + " runtime=" + runtime + " pid=" + data.get("pid")
                + " core=" + data.get("coreSha256") + " adapter=" + data.get("adapterSha256"));
    }

    private static Path jar(final String name, final ClassLoader loader, final String module,
                            final String expected) throws Exception {
        Class<?> type = Class.forName(name, false, loader);
        URL origin = type.getProtectionDomain().getCodeSource().getLocation();
        if (!"file".equals(origin.getProtocol())) throw new IllegalStateException("A local resolved JAR is required");
        Path path = Path.of(origin.toURI());
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
                || !path.getFileName().toString().equals(module + "-0.2.0.jar")
                || !digest(path).equals(expected)) throw new IllegalStateException("Unreviewed class origin: " + name);
        List<URL> resources = Collections.list(loader.getResources(name.replace('.', '/') + ".class"));
        if (resources.size() != 1 || !"jar".equals(resources.get(0).getProtocol())) {
            throw new IllegalStateException("Duplicated or directory-backed first-party class: " + name);
        }
        JarURLConnection connection = (JarURLConnection) resources.get(0).openConnection();
        if (!path.toRealPath().equals(Path.of(connection.getJarFileURL().toURI()).toRealPath())) {
            throw new IllegalStateException("Class resource and code source differ");
        }
        return path.toRealPath();
    }

    private static void verifyProvider(final ClassLoader loader, final String spi, final String expected,
                                       final Path adapter) throws Exception {
        List<String> own = new ArrayList<>();
        for (URL url : Collections.list(loader.getResources("META-INF/services/" + spi))) {
            String content;
            try (var input = url.openStream()) {
                content = new String(input.readAllBytes(), StandardCharsets.UTF_8);
            }
            for (String line : content.split("\\R")) {
                String declaration = line.split("#", 2)[0].strip();
                if (!declaration.startsWith("io.github.ym0506.routecontract.")) continue;
                if (!"jar".equals(url.getProtocol())) throw new IllegalStateException("Directory-backed provider descriptor");
                JarURLConnection connection = (JarURLConnection) url.openConnection();
                if (!adapter.equals(Path.of(connection.getJarFileURL().toURI()).toRealPath())) {
                    throw new IllegalStateException("Provider descriptor is not in reviewed adapter");
                }
                own.add(declaration);
            }
        }
        if (!own.equals(List.of(expected))) throw new IllegalStateException("Unexpected packaged provider declarations");
    }

    private static String required(final String key) {
        String value = System.getProperty(key);
        if (value == null || value.isBlank()) throw new IllegalStateException("Missing " + key);
        return value;
    }

    private static String digest(final Path file) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file)));
    }

    private static String quote(final String value) {
        return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r") + "\"";
    }
}
