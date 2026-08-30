package io.github.ym0506.routecontract.examples.buildshape;

import io.github.ym0506.routecontract.RouteContract;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RouteContractBuildShapePilotTest {
    @Test
    void loadsOnlyTheExactReleaseArtifactOnJdk17() throws Exception {
        assertEquals(17, Runtime.version().feature());
        assertEquals("gradle95-build-shape", BuildShapeApplication.lane());

        Path expectedJar = Path.of(
                System.getProperty("routecontract.expectedArtifactJar"))
                .toRealPath();
        URI classLocation = RouteContract.class.getProtectionDomain()
                .getCodeSource().getLocation().toURI();
        Path actualJar = Path.of(classLocation).toRealPath();
        assertEquals(expectedJar, actualJar);
        assertTrue(Files.isRegularFile(actualJar, LinkOption.NOFOLLOW_LINKS));
        assertFalse(Files.isSymbolicLink(actualJar));
        assertEquals(
                System.getProperty("routecontract.expectedJarSha256"),
                sha256(actualJar));

        Path repository = Path.of(
                System.getProperty("routecontract.expectedRepository"))
                .toRealPath();
        Path pom = repository.resolve(
                "io/github/ym0506/routecontract/routecontract-shardingsphere-5.5/0.1.2/"
                        + "routecontract-shardingsphere-5.5-0.1.2.pom");
        assertEquals(
                System.getProperty("routecontract.expectedPomSha256"),
                sha256(pom));

        System.out.println(
                "ROUTECONTRACT_BUILD_SHAPE_PILOT runtimeJdk=17 "
                        + "artifactOrigin=EXACT_LOCAL_RELEASE adoptionClaim=false "
                        + "externalTarget=false baselineApproved=false candidateChecked=false");
    }

    private static String sha256(Path path) throws Exception {
        return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                        .digest(Files.readAllBytes(path)));
    }
}
