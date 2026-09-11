package io.github.ym0506.routecontract.examples.maven;

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
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.net.JarURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

class MavenRouteContractPilotTest {

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

    @BeforeAll
    static void startFixture() throws Exception {
        fixture = new MySqlShardingFixture();
        orderQueryService = new OrderQueryService(fixture.start());
    }

    @AfterAll
    static void stopFixture() throws Exception {
        fixture.close();
    }

    @Test
    void keepsTheApprovedExecutionStructure() throws Exception {
        Path expectedArtifactJar = expectedArtifactJar();
        assertEquals(expectedArtifactJar, classOrigin(RouteContract.class),
                "RouteContract must be loaded from the exact cached Release JAR");
        Class<?> providerClass = Class.forName(
                PROVIDER_CLASS, false, Thread.currentThread().getContextClassLoader());
        assertEquals(expectedArtifactJar, classOrigin(providerClass),
                "the SPI provider class must be loaded from the exact cached Release JAR");
        assertEquals(List.of(expectedArtifactJar), matchingServiceDescriptorJars(),
                "the Maven pilot must expose exactly one matching provider descriptor "
                        + "from the exact cached Release JAR");

        Path projectDir = Path.of(System.getProperty("routecontract.projectDir"))
                .toAbsolutePath()
                .normalize();
        Path approvedPath = projectDir.resolve(
                "src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json");
        String candidateRoot = System.getProperty("routecontract.candidateRoot");
        if (candidateRoot == null || candidateRoot.isBlank()) {
            fail("routecontract.candidateRoot must be set by the isolated pilot profile");
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
                reviewedMaxAttempts,
                reviewedMaxDataSources);
        boolean baselineMissing = Files.notExists(approvedPath);

        CapturedResult<Long> capture = RouteContract.captureResult(
                "maven-pilot-orders.find-by-user-id",
                () -> orderQueryService.countByUserId(3L));
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
                snapshot,
                aliases,
                policy);
        ManifestStore store = new ManifestStore();

        if (baselineMissing) {
            RouteAssertions.assertThat(snapshot)
                    .hasAtMostObservedPhysicalAttempts(reviewedMaxAttempts)
                    .hasAtMostDistinctObservedDataSourceNames(reviewedMaxDataSources);
        }
        store.writeCandidate(approvedPath, candidatePath, candidate);

        System.out.println("ROUTECONTRACT_MAVEN_PILOT businessResult=PASS capture=COMPLETE "
                + "observedPhysicalAttempts=1 observedDataSourceNames=[ds_0] candidate="
                + candidatePath);
        if (baselineMissing) {
            fail("No approved baseline. Review " + candidatePath
                    + " and copy it to " + approvedPath + " only after human approval.");
        }

        ManifestAssertions.assertMatched(
                new ManifestVerifier().verify(store.read(approvedPath), candidate));
        System.out.println("ROUTECONTRACT_MAVEN_PILOT candidateCheck=MATCHED");
    }

    private static Path expectedArtifactJar() throws Exception {
        assertEquals("routecontract-shardingsphere-5.5-0.1.2.jar", ARTIFACT_JAR_NAME);
        if (ARTIFACT_JAR_PATH == null || ARTIFACT_JAR_PATH.isBlank()) {
            fail("routecontract.artifactJarPath must identify the exact cached Release JAR");
        }
        Path configured = Path.of(ARTIFACT_JAR_PATH);
        if (!configured.isAbsolute() || Files.isSymbolicLink(configured)) {
            fail("routecontract.artifactJarPath must be an absolute non-symlink path");
        }
        Path actual = configured.toRealPath();
        assertEquals(ARTIFACT_JAR_NAME, actual.getFileName().toString());
        return actual;
    }

    private static Path classOrigin(Class<?> type) throws Exception {
        var codeSource = type.getProtectionDomain().getCodeSource();
        if (codeSource == null || !"file".equals(codeSource.getLocation().getProtocol())) {
            fail(type.getName() + " must expose a file-backed code source");
        }
        return Path.of(codeSource.getLocation().toURI()).toRealPath();
    }

    private static List<Path> matchingServiceDescriptorJars() throws Exception {
        Enumeration<URL> descriptors = Thread.currentThread()
                .getContextClassLoader()
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
