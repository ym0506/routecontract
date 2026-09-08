package io.github.ym0506.routecontract.boundary;

import io.github.ym0506.routecontract.api.RouteContract;

import java.io.File;
import java.io.InputStream;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.Set;
import java.util.TreeMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.regex.Pattern;

/** One fresh-process measurement of the current API's coherent opposite-runtime rejection. */
public final class OppositeRuntimeGuardProbe {
    private static final String ROUTE_GROUP = "io.github.ym0506.routecontract";
    private static final String SS_GROUP = "org.apache.shardingsphere";
    private static final String DIAGNOSTIC = "RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME";
    private static final Set<String> EXPECTATION_KEYS = Set.of(
            "adapterRuntime", "observedRuntime", "coreSha256", "coreByteCount",
            "adapterSha256", "adapterByteCount", "expectedUserHome", "expectedParentPid",
            "expectedShardingSphereCoordinates");

    private OppositeRuntimeGuardProbe() {
    }

    /** Requires a runner-written Java Properties file; no network or database is used. */
    public static void main(final String[] args) throws Exception {
        require(args.length == 2 && "--expectations".equals(args[0]),
                "Expected --expectations <runner-written Properties file>");
        Properties expected = new Properties();
        Path expectations = Path.of(args[1]);
        require(Files.isRegularFile(expectations, LinkOption.NOFOLLOW_LINKS),
                "Expectations must be a regular nonsymlink file");
        try (InputStream input = Files.newInputStream(expectations)) {
            expected.load(input);
        }
        require(expected.stringPropertyNames().equals(EXPECTATION_KEYS),
                "Expectations have missing or unknown keys");
        String adapterRuntime = property(expected, "adapterRuntime");
        String observedRuntime = property(expected, "observedRuntime");
        require(Set.of("5.5.2", "5.5.3").contains(adapterRuntime)
                        && opposite(adapterRuntime).equals(observedRuntime),
                "The two finite guard cases require coherent opposite exact runtimes");
        require(Runtime.version().feature() == 17, "The actual probe JVM must be Java 17");
        require("true".equals(System.getProperty("java.net.preferIPv4Stack")),
                "The actual probe JVM must use the trusted IPv4 setting");
        String expectedHome = property(expected, "expectedUserHome");
        Path home = Path.of(expectedHome);
        require(home.isAbsolute() && Files.isDirectory(home, LinkOption.NOFOLLOW_LINKS)
                        && home.toRealPath().toString().equals(expectedHome)
                        && expectedHome.equals(System.getProperty("user.home")),
                "The probe must use the exact canonical private user.home");
        long pid = ProcessHandle.current().pid();
        long parentPid = ProcessHandle.current().parent().orElseThrow().pid();
        require(parentPid == Long.parseLong(property(expected, "expectedParentPid")) && pid != parentPid,
                "The probe must be a fresh external child of the recorded runner process");

        ClassLoader loader = RouteContract.class.getClassLoader();
        require(loader != null && loader == OppositeRuntimeGuardProbe.class.getClassLoader(),
                "The current API and probe must use one application classloader");
        String adapterArtifact = adapterArtifact(adapterRuntime);
        Path coreJar = checkedJar(RouteContract.class, "routecontract-core",
                property(expected, "coreSha256"), property(expected, "coreByteCount"));
        Class<?> provider = loadUnique(providerClass(adapterRuntime), loader);
        Path adapterJar = checkedJar(provider, adapterArtifact,
                property(expected, "adapterSha256"), property(expected, "adapterByteCount"));
        require(!coreJar.equals(adapterJar), "Core and adapter must have separate JAR origins");
        for (String name : List.of(
                "io.github.ym0506.routecontract.api.RouteContract",
                "io.github.ym0506.routecontract.internal.CurrentRuntimeGuard",
                "io.github.ym0506.routecontract.internal.CaptureRegistry",
                "io.github.ym0506.routecontract.internal.RuntimeAdapterRegistry",
                "io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter",
                "io.github.ym0506.routecontract.spi.RouteContractHookBridge")) {
            require(codeSource(loadUnique(name, loader)).equals(coreJar),
                    "A current core class is outside the receipt-pinned core: " + name);
        }
        require(codeSource(loadUnique(hookClass(adapterRuntime), loader)).equals(adapterJar),
                "The exact adapter hook class is outside the receipt-pinned adapter");

        // Every precheck is outside the measured capture's exception handler. A missing class,
        // origin problem or linkage error here cannot be mistaken for runtime-guard success.
        List<Map<String, Object>> shardingSphereJars = inspectClasspath(coreJar, adapterJar);
        List<String> coordinates = shardingSphereJars.stream()
                .map(item -> (String) item.get("coordinate")).sorted().toList();
        String expectedCoordinates = property(expected, "expectedShardingSphereCoordinates");
        List<String> requestedCoordinates = List.of(expectedCoordinates.split(",", -1));
        require(requestedCoordinates.equals(requestedCoordinates.stream().distinct().sorted().toList()),
                "Expected ShardingSphere coordinates must be a unique sorted list");
        require(coordinates.equals(requestedCoordinates) && !coordinates.isEmpty(),
                "The actual full ShardingSphere JAR set differs from the retained resolved graph");
        for (String coordinate : coordinates) {
            require(coordinate.matches("org[.]apache[.]shardingsphere:[a-z0-9.-]+:"
                            + Pattern.quote(observedRuntime)),
                    "All actual ShardingSphere JARs must have the exact opposite runtime");
        }
        List<Map<String, Object>> anchors = inspectAnchors(observedRuntime, loader, shardingSphereJars);

        AtomicBoolean actionInvoked = new AtomicBoolean();
        IllegalStateException rejection = null;
        boolean returned = false;
        try {
            RouteContract.capture("coherent-opposite-runtime-boundary", () -> actionInvoked.set(true));
            returned = true;
        } catch (IllegalStateException failure) {
            rejection = failure;
        }
        String exactMessage = DIAGNOSTIC + ": exact adapter " + adapterRuntime + " observed " + observedRuntime;
        require(!returned && !actionInvoked.get(), "The current API returned or invoked the application action");
        require(rejection != null && rejection.getClass() == IllegalStateException.class
                        && exactMessage.equals(rejection.getMessage())
                        && rejection.getCause() == null && rejection.getSuppressed().length == 0,
                "Only a cause-free exact coherent-opposite runtime diagnostic is accepted; observed "
                        + (rejection == null ? "no rejection" : rejection));
        // Re-hash after the measured call: the files actually loaded must still match the receipt.
        checkedJar(RouteContract.class, "routecontract-core",
                property(expected, "coreSha256"), property(expected, "coreByteCount"));
        checkedJar(provider, adapterArtifact,
                property(expected, "adapterSha256"), property(expected, "adapterByteCount"));
        require(shardingSphereJars.equals(inspectClasspath(coreJar, adapterJar)),
                "The actual runtime classpath changed during capture");

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("schemaVersion", 1);
        result.put("adapterRuntime", adapterRuntime);
        result.put("observedRuntime", observedRuntime);
        result.put("currentApi", RouteContract.class.getName());
        result.put("javaFeature", Runtime.version().feature());
        result.put("javaVersion", Runtime.version().toString());
        result.put("userHome", System.getProperty("user.home"));
        result.put("preferIPv4Stack", Boolean.parseBoolean(System.getProperty("java.net.preferIPv4Stack")));
        result.put("pid", pid);
        result.put("parentPid", parentPid);
        result.put("core", jarEvidence(ROUTE_GROUP + ":routecontract-core:0.2.0", coreJar));
        result.put("adapter", jarEvidence(ROUTE_GROUP + ":" + adapterArtifact + ":0.2.0", adapterJar));
        result.put("anchors", anchors);
        result.put("shardingSphereCoordinates", coordinates);
        result.put("shardingSphereJars", shardingSphereJars);
        result.put("actionInvoked", actionInvoked.get());
        result.put("diagnosticCode", DIAGNOSTIC);
        result.put("diagnosticMessage", rejection.getMessage());
        result.put("exceptionType", rejection.getClass().getName());
        System.out.println("BOUNDARY_RUNTIME_RESULT " + json(result));
    }

    private static List<Map<String, Object>> inspectAnchors(
            final String observedRuntime, final ClassLoader loader,
            final List<Map<String, Object>> selectedJars) throws Exception {
        String databaseArtifact = "5.5.2".equals(observedRuntime)
                ? "shardingsphere-infra-database-core" : "shardingsphere-database-connector-core";
        String spiClass = "5.5.2".equals(observedRuntime)
                ? "org.apache.shardingsphere.infra.spi.ShardingSphereServiceLoader"
                : "org.apache.shardingsphere.infra.spi.ShardingSphereSPI";
        String databaseClass = "5.5.2".equals(observedRuntime)
                ? "org.apache.shardingsphere.infra.database.core.connector.ConnectionProperties"
                : "org.apache.shardingsphere.database.connector.core.jdbcurl.parser.ConnectionProperties";
        List<String[]> definitions = List.of(
                new String[]{"executor", "org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook",
                        "shardingsphere-infra-executor"},
                new String[]{"spi", spiClass, "shardingsphere-infra-spi"},
                new String[]{"database", databaseClass, databaseArtifact});
        List<Map<String, Object>> result = new ArrayList<>();
        Set<Path> distinctOrigins = new HashSet<>();
        for (String[] definition : definitions) {
            Class<?> type = loadUnique(definition[1], loader);
            Path origin = codeSource(type);
            String coordinate = SS_GROUP + ":" + definition[2] + ":" + observedRuntime;
            Map<String, Object> item = jarEvidence(coordinate, origin);
            require(selectedJars.contains(item), "Loaded anchor does not match its actual classpath JAR");
            require(origin.getFileName().toString().equals(definition[2] + "-" + observedRuntime + ".jar"),
                    "Loaded anchor has an unexpected CodeSource filename");
            require(type.getPackage() != null
                            && observedRuntime.equals(type.getPackage().getImplementationVersion()),
                    "Loaded anchor package does not identify the exact opposite runtime");
            try (JarFile jar = new JarFile(origin.toFile())) {
                require(jar.getManifest() != null && observedRuntime.equals(
                                jar.getManifest().getMainAttributes().getValue("Implementation-Version")),
                        "Loaded anchor JAR manifest does not identify the exact opposite runtime");
            }
            require(distinctOrigins.add(origin), "The three runtime anchors must have distinct JAR origins");
            item.put("role", definition[0]);
            item.put("className", type.getName());
            item.put("implementationVersion", type.getPackage().getImplementationVersion());
            result.add(item);
        }
        return result;
    }

    private static List<Map<String, Object>> inspectClasspath(
            final Path coreJar, final Path adapterJar) throws Exception {
        Map<String, Map<String, Object>> selected = new TreeMap<>();
        Set<String> seenModules = new HashSet<>();
        Set<Path> paths = new HashSet<>();
        Set<Path> firstParty = new HashSet<>();
        Path probeClasses = Path.of(OppositeRuntimeGuardProbe.class.getProtectionDomain()
                .getCodeSource().getLocation().toURI()).toRealPath();
        require(Files.isDirectory(probeClasses), "The external probe must use the compiled classes directory");
        for (String element : System.getProperty("java.class.path").split(Pattern.quote(File.pathSeparator), -1)) {
            require(!element.isBlank(), "The actual Java classpath has an empty entry");
            Path declared = Path.of(element);
            require(declared.isAbsolute() && !Files.isSymbolicLink(declared),
                    "The recorded runtime classpath must use absolute nonsymlink entries");
            Path path = declared.toRealPath();
            require(paths.add(path), "The actual Java classpath contains a duplicate path");
            if (path.equals(probeClasses)) {
                continue;
            }
            require(Files.isRegularFile(path) && path.getFileName().toString().endsWith(".jar"),
                    "Only the probe classes directory and regular JARs may be on the classpath");
            if (path.getFileName().toString().startsWith("routecontract-")) {
                require(path.equals(coreJar) || path.equals(adapterJar),
                        "An extra RouteContract JAR is on the actual classpath");
                firstParty.add(path);
            }
            try (JarFile jar = new JarFile(path.toFile())) {
                String manifestClasspath = jar.getManifest() == null ? null
                        : jar.getManifest().getMainAttributes().getValue("Class-Path");
                require(manifestClasspath == null || manifestClasspath.isBlank(),
                        "Manifest Class-Path entries may not expand the recorded runtime classpath");
                List<JarEntry> metadata = jar.stream().filter(entry -> !entry.isDirectory()
                                && entry.getName().startsWith("META-INF/maven/" + SS_GROUP + "/")
                                && entry.getName().endsWith("/pom.properties"))
                        .toList();
                boolean hasShardingSphereClasses = jar.stream().anyMatch(entry ->
                        entry.getName().startsWith("org/apache/shardingsphere/")
                                && entry.getName().endsWith(".class"));
                if (metadata.isEmpty()) {
                    require(!hasShardingSphereClasses && !path.getFileName().toString().startsWith("shardingsphere-"),
                            "A ShardingSphere JAR lacks independently inspectable Maven coordinates");
                    continue;
                }
                require(metadata.size() == 1, "A ShardingSphere JAR must expose one unambiguous Maven identity");
                Properties identity = new Properties();
                try (InputStream input = jar.getInputStream(metadata.get(0))) {
                    identity.load(input);
                }
                String group = property(identity, "groupId");
                String artifact = property(identity, "artifactId");
                String version = property(identity, "version");
                require(SS_GROUP.equals(group) && artifact.matches("shardingsphere-[a-z0-9.-]+")
                                && metadata.get(0).getName().equals(
                                "META-INF/maven/" + group + "/" + artifact + "/pom.properties")
                                && path.getFileName().toString().equals(artifact + "-" + version + ".jar"),
                        "A ShardingSphere JAR has inconsistent path and Maven identities");
                String coordinate = group + ":" + artifact + ":" + version;
                require(seenModules.add(group + ":" + artifact),
                        "The actual classpath contains duplicate ShardingSphere module identities");
                selected.put(coordinate, jarEvidence(coordinate, path));
            }
        }
        require(paths.contains(probeClasses) && firstParty.equals(Set.of(coreJar, adapterJar)),
                "The actual classpath must include one probe, one receipt-pinned core and one adapter");
        return List.copyOf(selected.values());
    }

    private static Class<?> loadUnique(final String name, final ClassLoader loader) throws Exception {
        require(Collections.list(loader.getResources(name.replace('.', '/') + ".class")).size() == 1,
                "Exactly one visible class definition is required: " + name);
        Class<?> type = Class.forName(name, false, loader);
        require(type.getClassLoader() == loader && !type.getModule().isNamed(),
                "Class must use the current unnamed application loader: " + name);
        return type;
    }

    private static Path checkedJar(
            final Class<?> type, final String artifact, final String expectedHash,
            final String expectedByteCount) throws Exception {
        require(expectedHash.matches("[0-9a-f]{64}") && expectedByteCount.matches("[1-9][0-9]*"),
                "Receipt SHA-256 and byte count must be explicit canonical values");
        Path path = codeSource(type);
        require(path.getFileName().toString().equals(artifact + "-0.2.0.jar")
                        && Files.size(path) == Long.parseLong(expectedByteCount)
                        && expectedHash.equals(sha256(path)),
                "Loaded first-party CodeSource differs from the independently reviewed receipt");
        return path;
    }

    private static Path codeSource(final Class<?> type) throws Exception {
        require(type.getProtectionDomain() != null && type.getProtectionDomain().getCodeSource() != null,
                "Loaded class has no CodeSource: " + type.getName());
        URL location = type.getProtectionDomain().getCodeSource().getLocation();
        require(location != null && "file".equals(location.getProtocol()),
                "Loaded class must have a local file-backed CodeSource: " + type.getName());
        Path declared = Path.of(location.toURI());
        require(Files.isRegularFile(declared, LinkOption.NOFOLLOW_LINKS),
                "Loaded class CodeSource must be a regular nonsymlink JAR: " + type.getName());
        return declared.toRealPath();
    }

    private static Map<String, Object> jarEvidence(final String coordinate, final Path path) throws Exception {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("coordinate", coordinate);
        result.put("path", path.toString());
        result.put("sha256", sha256(path));
        result.put("byteCount", Files.size(path));
        return result;
    }

    private static String sha256(final Path path) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = Files.newInputStream(path)) {
            byte[] buffer = new byte[65536];
            int count;
            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    private static String property(final Properties values, final String name) {
        String result = values.getProperty(name);
        require(result != null && !result.isBlank() && result.equals(result.strip()),
                "Missing or noncanonical property " + name);
        return result;
    }

    private static String opposite(final String version) {
        return "5.5.2".equals(version) ? "5.5.3" : "5.5.2";
    }

    private static String adapterArtifact(final String runtime) {
        return "5.5.2".equals(runtime) ? "routecontract-shardingsphere-5.5.2" : "routecontract-shardingsphere-5.5";
    }

    private static String providerClass(final String runtime) {
        String suffix = runtime.replace(".", "");
        return "io.github.ym0506.routecontract.shardingsphere" + suffix
                + ".internal.ShardingSphere" + suffix + "RuntimeAdapter";
    }

    private static String hookClass(final String runtime) {
        String suffix = runtime.replace(".", "");
        return "io.github.ym0506.routecontract.shardingsphere" + suffix
                + ".internal.RouteContract" + suffix + "SqlExecutionHook";
    }

    private static String json(final Object value) {
        if (value instanceof String text) {
            StringBuilder result = new StringBuilder("\"");
            for (int index = 0; index < text.length(); index++) {
                char character = text.charAt(index);
                if (character == '"' || character == '\\') {
                    result.append('\\').append(character);
                } else if (character < 0x20) {
                    result.append(String.format("\\u%04x", (int) character));
                } else {
                    result.append(character);
                }
            }
            return result.append('"').toString();
        }
        if (value instanceof Map<?, ?> map) {
            List<String> items = new ArrayList<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                require(entry.getKey() instanceof String, "JSON object key must be a string");
                items.add(json(entry.getKey()) + ":" + json(entry.getValue()));
            }
            return "{" + String.join(",", items) + "}";
        }
        if (value instanceof List<?> list) {
            return "[" + String.join(",", list.stream().map(OppositeRuntimeGuardProbe::json).toList()) + "]";
        }
        require(value instanceof Number || value instanceof Boolean, "Unsupported evidence JSON value");
        return value.toString();
    }

    private static void require(final boolean condition, final String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
