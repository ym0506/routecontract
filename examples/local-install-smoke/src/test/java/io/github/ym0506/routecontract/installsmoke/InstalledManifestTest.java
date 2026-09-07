package io.github.ym0506.routecontract.installsmoke;

import io.github.ym0506.routecontract.RouteContractViolationException;
import io.github.ym0506.routecontract.manifest.ManifestAssertions;
import io.github.ym0506.routecontract.manifest.ManifestCodec;
import io.github.ym0506.routecontract.manifest.ManifestVerifier;
import io.github.ym0506.routecontract.manifest.ObservedExecutionManifest;
import io.github.ym0506.routecontract.manifest.VerificationStatus;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Exercises the published manifest API; it does not execute a database query. */
class InstalledManifestTest {

    @Test
    void approvedManifestMatchesAnUnchangedCandidate() throws Exception {
        ObservedExecutionManifest approved = manifest("approved");
        var result = new ManifestVerifier().verify(approved, manifest("approved"));

        assertEquals(VerificationStatus.MATCH, result.status());
        assertEquals(result, ManifestAssertions.assertMatched(result));
    }

    @Test
    void committedExecutionIncreaseFailsTheContractAssertion() throws Exception {
        var result = new ManifestVerifier().verify(manifest("approved"), manifest("candidate"));

        assertEquals(VerificationStatus.POLICY_VIOLATION, result.status());
        assertEquals(List.of("RCM201", "RCM202"),
                result.diffs().stream().map(diff -> diff.code().stableCode()).toList());
        RouteContractViolationException failure = assertThrows(
                RouteContractViolationException.class, () -> ManifestAssertions.assertMatched(result));
        assertTrue(failure.getMessage().contains("RCM201"));
        assertTrue(failure.getMessage().contains("RCM202"));
    }

    @Test
    void usesThePublishedJarAndItsPomRuntimeDependencies() throws Exception {
        Path jar = Path.of(ManifestVerifier.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        assertEquals("routecontract-shardingsphere-5.5-0.1.2.jar", jar.getFileName().toString());
        assertTrue(Files.isRegularFile(jar));
        assertEquals("d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc",
                HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(jar))));
        assertRuntimeJar("com.alibaba.ttl.TransmittableThreadLocal", "transmittable-thread-local-2.14.2.jar");
        assertRuntimeJar("tools.jackson.core.json.JsonFactory", "jackson-core-3.1.5.jar");
    }

    private static ObservedExecutionManifest manifest(final String role) throws Exception {
        String resource = "/find-paid-orders-by-user." + role + ".json";
        try (InputStream input = InstalledManifestTest.class.getResourceAsStream(resource)) {
            assertNotNull(input, resource);
            return new ManifestCodec().decode(input.readAllBytes());
        }
    }

    private static void assertRuntimeJar(final String className, final String expectedJar) throws Exception {
        Class<?> dependency = Class.forName(className);
        Path jar = Path.of(dependency.getProtectionDomain().getCodeSource().getLocation().toURI());
        assertEquals(expectedJar, jar.getFileName().toString());
        assertTrue(Files.isRegularFile(jar));
    }
}
