package io.github.ym0506.routecontract.examples.gradle.kotlin;

import io.github.ym0506.routecontract.CapturedResult;
import io.github.ym0506.routecontract.RouteAssertions;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.manifest.DataSourceAliases;
import io.github.ym0506.routecontract.manifest.ManifestAssertions;
import io.github.ym0506.routecontract.manifest.ManifestPolicy;
import io.github.ym0506.routecontract.manifest.ManifestStore;
import io.github.ym0506.routecontract.manifest.ManifestVerifier;
import io.github.ym0506.routecontract.manifest.ObservedExecutionManifest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;

import java.net.JarURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.fail;

class GradleKotlinRouteContractPilotTest {

    private static final String SERVICE_DESCRIPTOR =
            "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";
    private static final String PROVIDER_CLASS =
            "io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook";
    private static final String ARTIFACT_JAR_NAME =
            System.getProperty("routecontract.artifactJarName");
    private static final String ARTIFACT_JAR_PATH =
            System.getProperty("routecontract.artifactJarPath");

    private static MySqlShardingFixture fixture;
    private static OrderQueryService orderQueryService;

    @AfterAll
    static void stopFixture() throws Exception {
        if (fixture != null) {
            fixture.close();
        }
    }

    @Test
    void keepsTheApprovedExecutionStructure() throws Exception {
        Path expectedArtifactJar = expectedArtifactJar();
        Path routeContractClassOrigin = classOrigin(RouteContract.class);
        assertEquals(expectedArtifactJar, routeContractClassOrigin,
                "RouteContract must be loaded from the exact repository Release JAR");
        Class<?> providerClass = Class.forName(
                PROVIDER_CLASS, false, Thread.currentThread().getContextClassLoader());
        Path providerClassOrigin = classOrigin(providerClass);
        assertEquals(expectedArtifactJar, providerClassOrigin,
                "the SPI provider class must be loaded from the exact repository Release JAR");
        List<Path> serviceDescriptorJars = matchingServiceDescriptorJars();
        assertEquals(List.of(expectedArtifactJar), serviceDescriptorJars,
                "the Gradle Kotlin pilot must expose exactly one matching provider descriptor "
                        + "from the exact cached Release JAR");
        Path repositoryRoot = expectedRepositoryRoot();
        Path artifactPom = expectedArtifactPom(repositoryRoot, expectedArtifactJar);
        String jarSha256 = sha256(expectedArtifactJar);
        String pomSha256 = sha256(artifactPom);
        assertEquals(System.getProperty("routecontract.artifactJarSha256"), jarSha256);
        assertEquals(System.getProperty("routecontract.artifactPomSha256"), pomSha256);
        System.out.println("ROUTECONTRACT_GRADLE_RUNTIME_ORIGIN coordinate="
                + System.getProperty("routecontract.coordinate")
                + " jarSha256=" + jarSha256 + " pomSha256=" + pomSha256
                + " apiOrigin=EXACT providerOrigin=EXACT serviceDescriptorCount=1");

        // No container, ShardingSphere data source, or RouteContract operation starts before the
        // runtime origin and both immutable artifact hashes have passed in this test JVM.
        fixture = new MySqlShardingFixture();
        orderQueryService = new OrderQueryService(fixture.start());

        Path projectDir = Path.of(System.getProperty("routecontract.projectDir"))
                .toAbsolutePath().normalize();
        Path approvedPath = projectDir.resolve(
                "src/routeContractPilot/resources/route-contracts/"
                        + "orders.find-by-user-id.json");
        String candidateRoot = System.getProperty("routecontract.candidateRoot");
        if (candidateRoot == null || candidateRoot.isBlank()) {
            fail("routecontract.candidateRoot must be set by the isolated pilot lane");
        }
        Path candidateRootPath = Path.of(candidateRoot);
        if (candidateRootPath.isAbsolute()) {
            fail("routecontract.candidateRoot must be relative to the owning module");
        }
        Path candidateDirectory = projectDir.resolve(candidateRootPath).normalize();
        if (!candidateDirectory.startsWith(projectDir) || candidateDirectory.equals(projectDir)) {
            fail("routecontract.candidateRoot must stay below the owning module");
        }
        Path candidatePath = candidateDirectory.resolve(
                "orders.find-by-user-id.candidate.json");
        if (Files.exists(candidatePath) || Files.isSymbolicLink(candidatePath)) {
            fail("Stale candidate exists before capture: " + candidatePath);
        }

        int reviewedMaxAttempts = 1;
        int reviewedMaxDataSources = 1;
        ManifestPolicy policy = ManifestPolicy.strict(
                reviewedMaxAttempts, reviewedMaxDataSources);
        boolean baselineMissing = Files.notExists(approvedPath);

        assertEquals(jarSha256, sha256(expectedArtifactJar),
                "RouteContract JAR changed between runtime preflight and operation");
        assertEquals(pomSha256, sha256(artifactPom),
                "RouteContract POM changed between runtime preflight and operation");
        CapturedResult<Long> capture = RouteContract.captureResult(
                "gradle-kotlin-pilot-orders.find-by-user-id",
                () -> orderQueryService.countByUserId(3L));
        assertEquals(jarSha256, sha256(expectedArtifactJar),
                "RouteContract JAR changed while the representative operation ran");
        assertEquals(pomSha256, sha256(artifactPom),
                "RouteContract POM changed while the representative operation ran");
        assertEquals(1L, capture.value());
        RouteSnapshot snapshot = capture.snapshot();
        RouteAssertions.assertThat(snapshot)
                .hasExactlyObservedPhysicalAttempts(1)
                .observesExactlyDataSourceNames("ds_0")
                .hasCompleteCapture()
                .hasNoReportedExecutionFailures();
        assertEquals(1, snapshot.callbackReturnedCount());
        assertEquals(0, snapshot.callbackFailureCount());
        assertEquals(0, snapshot.unknownOutcomeCount());
        assertFalse(snapshot.attempts().get(0).sqlFingerprint().isBlank());

        DataSourceAliases aliases = DataSourceAliases.of(Map.of("ds_0", "orders-shard-a"));
        ObservedExecutionManifest candidate = ObservedExecutionManifest.from(
                snapshot, aliases, policy);
        ManifestStore store = new ManifestStore();

        if (baselineMissing) {
            RouteAssertions.assertThat(snapshot)
                    .hasAtMostObservedPhysicalAttempts(reviewedMaxAttempts)
                    .hasAtMostDistinctObservedDataSourceNames(reviewedMaxDataSources);
        }
        store.writeCandidate(approvedPath, candidatePath, candidate);
        writeProvenance(
                projectDir,
                expectedArtifactJar,
                artifactPom,
                repositoryRoot,
                jarSha256,
                pomSha256,
                routeContractClassOrigin,
                providerClassOrigin,
                serviceDescriptorJars);

        System.out.println("ROUTECONTRACT_GRADLE_KOTLIN_PILOT businessResult=PASS "
                + "capture=COMPLETE observedPhysicalAttempts=1 "
                + "observedDataSourceNames=[ds_0] candidate=" + candidatePath);
        if (baselineMissing) {
            fail("No approved baseline. Review " + candidatePath
                    + " and copy it to " + approvedPath + " only after human approval.");
        }

        ManifestAssertions.assertMatched(
                new ManifestVerifier().verify(store.read(approvedPath), candidate));
        System.out.println("ROUTECONTRACT_GRADLE_KOTLIN_PILOT candidateCheck=MATCHED");
    }

    private static Path expectedArtifactJar() throws Exception {
        assertEquals("routecontract-shardingsphere-5.5-0.1.2.jar", ARTIFACT_JAR_NAME);
        if (ARTIFACT_JAR_PATH == null || ARTIFACT_JAR_PATH.isBlank()) {
            fail("routecontract.artifactJarPath must identify the exact repository Release JAR");
        }
        Path configured = Path.of(ARTIFACT_JAR_PATH);
        if (!configured.isAbsolute() || Files.isSymbolicLink(configured)) {
            fail("routecontract.artifactJarPath must be an absolute non-symlink path");
        }
        Path actual = configured.toRealPath();
        assertEquals(ARTIFACT_JAR_NAME, actual.getFileName().toString());
        return actual;
    }

    private static void writeProvenance(
            Path projectDir,
            Path artifactJar,
            Path artifactPom,
            Path repositoryRoot,
            String jarSha256,
            String pomSha256,
            Path routeContractClassOrigin,
            Path providerClassOrigin,
            List<Path> serviceDescriptorJars) throws Exception {
        String coordinate = System.getProperty("routecontract.coordinate");
        assertEquals(
                "io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.2",
                coordinate);
        String provenanceProperty = System.getProperty("routecontract.provenancePath");
        if (provenanceProperty == null || provenanceProperty.isBlank()) {
            fail("routecontract.provenancePath must be set by the isolated pilot lane");
        }
        Path provenanceInput = Path.of(provenanceProperty);
        if (provenanceInput.isAbsolute()) {
            fail("routecontract.provenancePath must be relative to the owning module");
        }
        Path provenancePath = projectDir.resolve(provenanceInput).normalize();
        Path evidenceRoot = projectDir.resolve("build/routecontract").normalize();
        if (!provenancePath.startsWith(evidenceRoot) || provenancePath.equals(evidenceRoot)) {
            fail("routecontract.provenancePath must stay below build/routecontract");
        }
        if (Files.exists(provenancePath) || Files.isSymbolicLink(provenancePath)) {
            fail("Stale provenance exists before capture: " + provenancePath);
        }
        Files.createDirectories(provenancePath.getParent());
        if (!Files.isDirectory(provenancePath.getParent())
                || Files.isSymbolicLink(provenancePath.getParent())) {
            fail("provenance parent must be a real directory");
        }

        String json = "{\n"
                + "  \"schemaVersion\": 1,\n"
                + "  \"coordinate\": " + jsonString(coordinate) + ",\n"
                + "  \"resolvedComponent\": " + jsonString(coordinate) + ",\n"
                + "  \"pathsEphemeral\": true,\n"
                + "  \"repositoryRoot\": " + jsonString(repositoryRoot.toString()) + ",\n"
                + "  \"jar\": {\"path\": " + jsonString(artifactJar.toString())
                + ", \"sha256\": " + jsonString(jarSha256) + "},\n"
                + "  \"pom\": {\"path\": " + jsonString(artifactPom.toString())
                + ", \"sha256\": " + jsonString(pomSha256) + "},\n"
                + "  \"origins\": {\n"
                + "    \"routeContractClass\": "
                + jsonString(routeContractClassOrigin.toString()) + ",\n"
                + "    \"providerClass\": " + jsonString(providerClassOrigin.toString())
                + ",\n"
                + "    \"serviceDescriptorCount\": " + serviceDescriptorJars.size() + ",\n"
                + "    \"serviceDescriptorJars\": ["
                + jsonString(serviceDescriptorJars.get(0).toString()) + "]\n"
                + "  },\n"
                + "  \"claimBoundary\": {\"dependencyVerification\": "
                + "\"selected-invariant-graph-and-pre-operation-runtime-origin\", "
                + "\"externalUser\": false, "
                + "\"humanApprovedBaseline\": false, \"adoption\": false}\n"
                + "}\n";
        Files.writeString(
                provenancePath,
                json,
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE);
    }

    private static Path expectedRepositoryRoot() throws Exception {
        Path repositoryRoot = Path.of(System.getProperty("routecontract.repositoryRoot"));
        if (!repositoryRoot.isAbsolute() || Files.isSymbolicLink(repositoryRoot)) {
            fail("routecontract.repositoryRoot must identify an absolute real directory");
        }
        return repositoryRoot.toRealPath();
    }

    private static Path expectedArtifactPom(
            Path repositoryRoot, Path artifactJar) throws Exception {
        Path expectedCoordinateDirectory = repositoryRoot.resolve(
                "io/github/ym0506/routecontract/routecontract-shardingsphere-5.5/0.1.2");
        assertEquals(
                expectedCoordinateDirectory.resolve(
                        "routecontract-shardingsphere-5.5-0.1.2.jar"),
                artifactJar);
        Path artifactPom = Path.of(System.getProperty("routecontract.artifactPomPath"));
        if (!artifactPom.isAbsolute() || Files.isSymbolicLink(artifactPom)) {
            fail("routecontract.artifactPomPath must identify an absolute non-symlink path");
        }
        artifactPom = artifactPom.toRealPath();
        assertEquals(
                expectedCoordinateDirectory.resolve(
                        "routecontract-shardingsphere-5.5-0.1.2.pom"),
                artifactPom);
        return artifactPom;
    }

    private static String sha256(Path path) throws Exception {
        return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
    }

    private static String jsonString(String value) {
        return "\"" + value
                .replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t") + "\"";
    }

    private static Path classOrigin(Class<?> type) throws Exception {
        var codeSource = type.getProtectionDomain().getCodeSource();
        if (codeSource == null || !"file".equals(codeSource.getLocation().getProtocol())) {
            fail(type.getName() + " must expose a file-backed code source");
        }
        return Path.of(codeSource.getLocation().toURI()).toRealPath();
    }

    private static List<Path> matchingServiceDescriptorJars() throws Exception {
        Enumeration<URL> descriptors = Thread.currentThread().getContextClassLoader()
                .getResources(SERVICE_DESCRIPTOR);
        List<Path> result = new ArrayList<>();
        while (descriptors.hasMoreElements()) {
            URL descriptor = descriptors.nextElement();
            var connection = descriptor.openConnection();
            String content;
            try (var stream = connection.getInputStream()) {
                content = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
            }
            if (content.lines().map(String::trim).anyMatch(PROVIDER_CLASS::equals)) {
                if (!(connection instanceof JarURLConnection)) {
                    fail("matching RouteContract provider descriptor must come from a JAR");
                }
                JarURLConnection jarConnection = (JarURLConnection) connection;
                result.add(Path.of(jarConnection.getJarFileURL().toURI()).toRealPath());
            }
        }
        return result;
    }
}
