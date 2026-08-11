package io.github.ym0506.routecontract.manifest;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/** Intentional failure fixture used only by the manifestCiFailureDemo Gradle task. */
@Tag("manifest-ci-failure-demo")
class ManifestFileCiFailureDemoTest {

    @Test
    void committedCandidateFailsTheApprovedObservedExecutionContract() throws Exception {
        Path examples = Path.of(
                System.getProperty("routecontract.repositoryRoot"),
                "examples",
                "manifests");
        ManifestCodec codec = new ManifestCodec();
        ObservedExecutionManifest approved = codec.decode(Files.readAllBytes(
                examples.resolve("find-paid-orders-by-user.approved.json")));
        ObservedExecutionManifest candidate = codec.decode(Files.readAllBytes(
                examples.resolve("find-paid-orders-by-user.candidate.json")));

        ManifestVerificationResult result = new ManifestVerifier().verify(approved, candidate);
        List<String> actualCodes = result.diffs().stream()
                .map(diff -> diff.code().stableCode())
                .toList();
        List<String> expectedCodes = List.of("RCM201", "RCM202");
        if (result.status() != VerificationStatus.POLICY_VIOLATION
                || !actualCodes.equals(expectedCodes)) {
            throw new IllegalStateException(
                    "The committed CI failure fixture no longer produces RCM201/RCM202: " + result);
        }

        System.out.println("ROUTECONTRACT_FILE_CI_DEMO approvedAttempts="
                + approved.counts().observedPhysicalAttemptCount()
                + " candidateAttempts=" + candidate.counts().observedPhysicalAttemptCount()
                + " status=" + result.status()
                + " blockingCodes=[RCM201,RCM202]");

        ManifestAssertions.assertMatched(result);
    }
}
