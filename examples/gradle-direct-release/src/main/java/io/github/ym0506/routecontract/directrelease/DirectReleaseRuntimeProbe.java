package io.github.ym0506.routecontract.directrelease;

import com.alibaba.ttl.TransmittableThreadLocal;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteSnapshot;
import org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook;
import org.apache.shardingsphere.infra.spi.ShardingSphereServiceLoader;
import tools.jackson.core.json.JsonFactory;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.JarURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.ProtectionDomain;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.HexFormat;
import java.util.List;
import java.util.ServiceLoader;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

/** Runtime identity and SPI probe for the immutable GitHub Release consumer lane. */
public final class DirectReleaseRuntimeProbe {
    private static final String PROVIDER_CLASS =
            "io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook";
    private static final String SERVICE_DESCRIPTOR =
            "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";

    private DirectReleaseRuntimeProbe() {
    }

    /** Runs the exact artifact, dependency, Java-provider, and runtime compatibility probes. */
    public static void main(final String[] args) throws Exception {
        require(Runtime.version().feature() == 17,
                "runtime must be exactly JDK 17, got " + Runtime.version());
        String expectedVersion = requiredProperty("routecontract.expectedVersion");
        String expectedSha256 = requiredProperty("routecontract.expectedSha256");
        long expectedSize = Long.parseLong(requiredProperty("routecontract.expectedSize"));
        String expectedTtlVersion = requiredProperty("routecontract.expectedTtlVersion");
        String expectedJacksonVersion = requiredProperty("routecontract.expectedJacksonVersion");
        String expectedShardingSphereVersion = requiredProperty(
                "routecontract.expectedShardingSphereVersion");

        Path routeContractJar = codeSource(RouteContract.class);
        require(routeContractJar.getFileName().toString().equals(
                        "routecontract-shardingsphere-5.5-" + expectedVersion + ".jar"),
                "unexpected RouteContract CodeSource filename: " + routeContractJar);
        require(Files.size(routeContractJar) == expectedSize,
                "unexpected RouteContract CodeSource size: " + Files.size(routeContractJar));
        require(sha256(routeContractJar).equals(expectedSha256),
                "unexpected RouteContract CodeSource SHA-256: " + sha256(routeContractJar));

        Path ttlJar = requireVersionedCodeSource(
                TransmittableThreadLocal.class,
                "transmittable-thread-local",
                expectedTtlVersion);
        Path jacksonJar = requireVersionedCodeSource(
                JsonFactory.class, "jackson-core", expectedJacksonVersion);
        Path executorJar = requireVersionedCodeSource(
                SQLExecutionHook.class,
                "shardingsphere-infra-executor",
                expectedShardingSphereVersion);
        Path spiJar = requireVersionedCodeSource(
                ShardingSphereServiceLoader.class,
                "shardingsphere-infra-spi",
                expectedShardingSphereVersion);
        require(expectedShardingSphereVersion.equals(
                        SQLExecutionHook.class.getPackage().getImplementationVersion()),
                "SQLExecutionHook package did not report exact ShardingSphere version");
        require(expectedShardingSphereVersion.equals(
                        ShardingSphereServiceLoader.class.getPackage().getImplementationVersion()),
                "ShardingSphereServiceLoader package did not report exact ShardingSphere version");

        verifyDescriptor(routeContractJar);
        ClassLoader routeContractLoader = RouteContract.class.getClassLoader();
        require(routeContractLoader != null, "RouteContract class loader must be explicit");

        List<ServiceLoader.Provider<SQLExecutionHook>> javaProviders = ServiceLoader
                .load(SQLExecutionHook.class, routeContractLoader)
                .stream()
                .filter(provider -> provider.type().getName().equals(PROVIDER_CLASS))
                .toList();
        require(javaProviders.size() == 1,
                "Java ServiceLoader expected exactly one RouteContract provider, got "
                        + javaProviders.size());

        ServiceLoader.Provider<SQLExecutionHook> javaProviderHandle = javaProviders.get(0);
        Class<? extends SQLExecutionHook> providerType = javaProviderHandle.type();
        require(providerType.getName().equals(PROVIDER_CLASS),
                "Java ServiceLoader returned an unexpected provider type");
        require(providerType.getClassLoader() == routeContractLoader,
                "Java ServiceLoader provider type used an unexpected class loader");
        Path providerTypeOrigin = codeSource(providerType);
        require(providerTypeOrigin.equals(routeContractJar),
                "Java ServiceLoader provider type did not come from verified RouteContract JAR");
        require(Files.size(providerTypeOrigin) == expectedSize
                        && sha256(providerTypeOrigin).equals(expectedSha256),
                "Java ServiceLoader provider type origin changed before instantiation");

        // Instantiate only after Provider.type() has passed the exact CodeSource check above.
        SQLExecutionHook javaProvider = javaProviderHandle.get();
        require(javaProvider.getClass() == providerType,
                "Java ServiceLoader instantiated an unexpected provider type");
        require(codeSource(javaProvider.getClass()).equals(routeContractJar),
                "Java ServiceLoader provider instance changed CodeSource");
        require(sha256(routeContractJar).equals(expectedSha256),
                "RouteContract CodeSource changed during Java provider instantiation");

        // This is a post-verification compatibility probe, not a pre-instantiation trust boundary.
        List<SQLExecutionHook> shardingSphereProviders = new ArrayList<>(
                ShardingSphereServiceLoader.getServiceInstances(SQLExecutionHook.class));
        List<SQLExecutionHook> matchingShardingSphereProviders = shardingSphereProviders.stream()
                .filter(provider -> provider.getClass().getName().equals(PROVIDER_CLASS))
                .toList();
        require(matchingShardingSphereProviders.size() == 1,
                "ShardingSphereServiceLoader expected exactly one RouteContract provider, got "
                        + matchingShardingSphereProviders.size());
        require(codeSource(matchingShardingSphereProviders.get(0).getClass())
                        .equals(routeContractJar),
                "ShardingSphere SPI provider did not come from verified RouteContract JAR");

        // This empty capture invokes RouteContract's fail-closed 5.5.3/SPI runtime preflight.
        RouteSnapshot snapshot = RouteContract.capture("direct-release-runtime-probe", () -> {
        });
        require(snapshot.operationId().equals("direct-release-runtime-probe"),
                "RouteContract capture did not run");
        require(sha256(routeContractJar).equals(expectedSha256),
                "RouteContract CodeSource changed during runtime probe");

        System.out.println("routecontractRuntimeJdk=" + Runtime.version().feature());
        System.out.println("routecontractRuntimeSha256=" + sha256(routeContractJar));
        System.out.println("routecontractRuntimeTtl=" + ttlJar.getFileName());
        System.out.println("routecontractRuntimeJackson=" + jacksonJar.getFileName());
        System.out.println("routecontractRuntimeShardingSphereExecutor="
                + executorJar.getFileName());
        System.out.println("routecontractRuntimeShardingSphereSpi=" + spiJar.getFileName());
        System.out.println("routecontractJavaProviderTypeOriginVerifiedBeforeInstantiation=true");
        System.out.println("routecontractShardingSphereLoaderRole=post-verification-compatibility");
        System.out.println("ROUTECONTRACT_DIRECT_RELEASE_RUNTIME_PROBE_VERIFIED");
    }

    private static Path requireVersionedCodeSource(
            final Class<?> type,
            final String artifactPrefix,
            final String exactVersion) throws Exception {
        Path result = codeSource(type);
        String expectedFileName = artifactPrefix + "-" + exactVersion + ".jar";
        require(result.getFileName().toString().equals(expectedFileName),
                type.getName() + " expected CodeSource " + expectedFileName + ", got " + result);
        return result;
    }

    private static void verifyDescriptor(final Path routeContractJar) throws Exception {
        try (JarFile jar = new JarFile(routeContractJar.toFile())) {
            JarEntry entry = jar.getJarEntry(SERVICE_DESCRIPTOR);
            require(entry != null, "RouteContract JAR is missing " + SERVICE_DESCRIPTOR);
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                    jar.getInputStream(entry), StandardCharsets.UTF_8))) {
                List<String> providers = reader.lines()
                        .map(String::trim)
                        .filter(line -> !line.isEmpty() && !line.startsWith("#"))
                        .toList();
                require(providers.equals(List.of(PROVIDER_CLASS)),
                        "unexpected RouteContract service descriptor: " + providers);
            }
        }

        Enumeration<URL> resources = RouteContract.class.getClassLoader()
                .getResources(SERVICE_DESCRIPTOR);
        List<Path> matchingOrigins = new ArrayList<>();
        while (resources.hasMoreElements()) {
            URL resource = resources.nextElement();
            var connection = resource.openConnection();
            connection.setUseCaches(false);
            List<String> providers;
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                    connection.getInputStream(), StandardCharsets.UTF_8))) {
                providers = reader.lines()
                        .map(String::trim)
                        .filter(line -> !line.isEmpty() && !line.startsWith("#"))
                        .toList();
            }
            if (!providers.contains(PROVIDER_CLASS)) {
                continue;
            }
            require(providers.equals(List.of(PROVIDER_CLASS)),
                    "matching descriptor contains unexpected providers: " + providers);
            require(connection instanceof JarURLConnection,
                    "matching provider descriptor is not JAR-backed: " + resource);
            JarURLConnection jarConnection = (JarURLConnection) connection;
            jarConnection.setUseCaches(false);
            require(SERVICE_DESCRIPTOR.equals(jarConnection.getEntryName()),
                    "matching provider descriptor has an unexpected JAR entry name");
            URL jarUrl = jarConnection.getJarFileURL();
            require("file".equals(jarUrl.getProtocol()),
                    "matching provider descriptor does not use a file-backed JAR");
            Path origin = Path.of(jarUrl.toURI()).toRealPath();
            require(Files.isRegularFile(origin) && !Files.isSymbolicLink(origin),
                    "matching provider descriptor origin is not a regular non-symlink file");
            matchingOrigins.add(origin);
        }
        require(matchingOrigins.equals(List.of(routeContractJar)),
                "expected one exact descriptor from the verified RouteContract JAR, got "
                        + matchingOrigins);
    }

    private static Path codeSource(final Class<?> type) throws Exception {
        ProtectionDomain domain = type.getProtectionDomain();
        require(domain != null && domain.getCodeSource() != null
                        && domain.getCodeSource().getLocation() != null,
                "missing CodeSource for " + type.getName());
        Path result = Path.of(domain.getCodeSource().getLocation().toURI()).toRealPath();
        require(Files.isRegularFile(result) && !Files.isSymbolicLink(result),
                "CodeSource is not a regular non-symlink file for " + type.getName());
        return result;
    }

    private static String sha256(final Path path) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (var input = Files.newInputStream(path)) {
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) >= 0) {
                digest.update(buffer, 0, count);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    private static String requiredProperty(final String name) {
        String result = System.getProperty(name);
        require(result != null && !result.isBlank(),
                "missing required system property " + name);
        return result;
    }

    private static void require(final boolean condition, final String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
