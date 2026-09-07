package io.github.ym0506.routecontract.manifest;

import io.github.ym0506.routecontract.AttemptOutcome;
import io.github.ym0506.routecontract.CaptureStatus;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.core.JsonParser;
import tools.jackson.core.ObjectReadContext;
import tools.jackson.core.json.JsonFactory;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ManifestReviewReportTest {
    @TempDir
    Path temporary;

    @Test
    void budgetRegressionHasCountsCodesAndInvestigationWithoutFalseSuccess() throws Exception {
        ManifestReviewReport report = ManifestReviewReport.compare(manifest(1), manifest(2));
        assertEquals(VerificationStatus.POLICY_VIOLATION, report.verification().status());
        assertEquals(1, report.strictExitCode());
        assertTrue(report.toMarkdown().contains("| Physical JDBC execution attempts | 1 | 2 | 1 |"));
        assertTrue(report.toMarkdown().contains("RCM201"));
        assertTrue(report.toMarkdown().contains("sharding predicates"));
        assertTrue(report.toJson().contains("\"status\":\"POLICY_VIOLATION\""));
        try (JsonParser parser = new JsonFactory().createParser(
                ObjectReadContext.empty(), report.toJson())) {
            while (parser.nextToken() != null) {
                // Parse the whole output, including every nested field.
            }
        }
        assertEquals(report.toJson(), ManifestReviewReport.compare(manifest(1), manifest(2)).toJson());
    }

    @Test
    void matchAndReviewRequiredHaveDistinctStrictExits() {
        assertEquals(0, ManifestReviewReport.compare(manifest(1), manifest(1)).strictExitCode());
        ManifestPolicy reviewPolicy = new ManifestPolicy(3, 1, true, false);
        var approved = copy(manifest(1), 1, "operation", CaptureStatus.COMPLETE, reviewPolicy);
        var candidate = copy(changedShape(), 1, "operation", CaptureStatus.COMPLETE, reviewPolicy);
        var report = ManifestReviewReport.compare(approved, candidate);
        assertEquals(VerificationStatus.REVIEW_REQUIRED, report.verification().status());
        assertTrue(report.verification().passesBlockingChecks());
        assertEquals(1, report.strictExitCode());
        assertTrue(report.toJson().contains("\"matched\":false"));
    }

    @Test
    void sameCountShapeChangeIsDriftAndCandidateCannotRaiseGoverningBudget() {
        var drift = ManifestReviewReport.compare(manifest(1), changedShape());
        assertEquals(VerificationStatus.DRIFT, drift.verification().status());
        assertTrue(drift.toMarkdown().contains("RCM301"));
        assertTrue(drift.toMarkdown().contains("RCM302"));
        var raised = copy(manifest(2), 1, "operation", CaptureStatus.COMPLETE, ManifestPolicy.strict(100, 100));
        var report = ManifestReviewReport.compare(manifest(1), raised);
        assertEquals(VerificationStatus.POLICY_VIOLATION, report.verification().status());
        assertTrue(report.toJson().contains("\"maxObservedPhysicalAttempts\":1"));
    }

    @Test
    void callbackFailureCannotMatchEvenWhenBothInputsHaveTheSameFailure() {
        var attempt = new ManifestAttempt("orders", "a".repeat(64), 0,
                List.of(), AttemptOutcome.CALLBACK_FAILURE, 1);
        var failed = new ObservedExecutionManifest(1, "operation", CaptureStatus.REPORTED_EXECUTION_FAILURE,
                ManifestPolicy.strict(1, 1), ManifestCounts.from(List.of(attempt)), List.of(attempt));
        assertEquals(VerificationStatus.NOT_ELIGIBLE,
                ManifestReviewReport.compare(manifest(1), failed).verification().status());
        var invalidBaseline = ManifestReviewReport.compare(failed, failed);
        assertEquals(VerificationStatus.INCOMPATIBLE, invalidBaseline.verification().status());
        assertEquals(1, invalidBaseline.strictExitCode());
    }

    @Test
    void incompatibilityAndIncompleteCaptureWinBeforeBudgets() {
        var incomplete = copy(manifest(2), 1, "operation", CaptureStatus.INCOMPLETE, ManifestPolicy.strict(1, 1));
        var report = ManifestReviewReport.compare(manifest(1), incomplete);
        assertEquals(VerificationStatus.NOT_ELIGIBLE, report.verification().status());
        assertTrue(report.toMarkdown().contains("RCM100"));
        assertFalse(report.toMarkdown().contains("RCM201"));
        var incompatible = copy(incomplete, 2, "operation", CaptureStatus.INCOMPLETE, incomplete.policy());
        assertEquals(VerificationStatus.INCOMPATIBLE,
                ManifestReviewReport.compare(manifest(1), incompatible).verification().status());
    }

    @Test
    void reportOmitsUntrustedIdentifiersAndDistinguishesCanonicalDigests() {
        String hostile = "<script>secret</script>\n::error::injected @someone";
        var renamed = copy(manifest(1), 1, hostile, CaptureStatus.COMPLETE, manifest(1).policy());
        var report = ManifestReviewReport.compare(manifest(1), renamed);
        for (String rendered : List.of(report.toMarkdown(), report.toJson())) {
            assertFalse(rendered.contains("secret"));
            assertFalse(rendered.contains("@someone"));
            assertFalse(rendered.contains("::error::"));
            assertFalse(rendered.contains("java.lang.Long"));
        }
        assertNotEquals(report.approvedCanonicalSha256(), report.candidateCanonicalSha256());
        var same = ManifestReviewReport.compare(renamed, renamed);
        assertEquals(same.approvedCanonicalSha256(), same.candidateCanonicalSha256());
    }

    @Test
    void cliWritesReportOnNonMatchAndDoesNotOverwriteAnyInputOrReport() throws Exception {
        Path baseline = write("baseline.json", manifest(1));
        Path candidate = write("candidate.json", manifest(2));
        Path output = temporary.resolve("review.md");
        byte[] originalBaseline = Files.readAllBytes(baseline);
        assertEquals(1, run(baseline, candidate, "markdown", output));
        assertTrue(Files.readString(output).contains("POLICY_VIOLATION"));
        assertEquals(2, run(baseline, candidate, "markdown", output));
        assertEquals(2, run(baseline, candidate, "json", baseline));
        Path link = temporary.resolve("link.json");
        Files.createSymbolicLink(link, baseline);
        assertEquals(2, run(baseline, candidate, "json", link));
        Path hardlink = temporary.resolve("hardlink.json");
        Files.createLink(hardlink, baseline);
        assertEquals(2, run(baseline, candidate, "json", hardlink));
        assertArrayEquals(originalBaseline, Files.readAllBytes(baseline));
    }

    @Test
    void cliRejectsMalformedOversizedAndMissingInputWithoutLeaksOrOutput() throws Exception {
        Path baseline = write("baseline.json", manifest(1));
        Path candidate = temporary.resolve("private-path-secret.json");
        Path output = temporary.resolve("output.json");
        for (String content : List.of("{\"private-secret\":", "x".repeat(1024 * 1024 + 1))) {
            Files.writeString(candidate, content);
            ByteArrayOutputStream errors = new ByteArrayOutputStream();
            assertEquals(2, ManifestReviewCli.run(arguments(baseline, candidate, "json", output),
                    new PrintStream(errors, true, StandardCharsets.UTF_8)));
            assertFalse(errors.toString(StandardCharsets.UTF_8).contains("secret"));
            assertFalse(Files.exists(output));
        }
        assertEquals(2, run(baseline, temporary.resolve("missing"), "json", output));
        assertEquals(2, ManifestReviewCli.run(new String[]{"--help", "oops"}, System.err));
        assertEquals(2, ManifestReviewCli.run(new String[]{"--baseline", "x", "--baseline", "y"}, System.err));
    }

    @Test
    void cliMatchWritesValidJsonAndRejectsUnknownFormat() throws Exception {
        Path baseline = write("baseline.json", manifest(1));
        Path output = temporary.resolve("output.json");
        assertEquals(0, run(baseline, baseline, "json", output));
        assertTrue(Files.readString(output).contains("\"matched\":true"));
        assertEquals(2, run(baseline, baseline, "html", temporary.resolve("bad")));
    }

    private Path write(String name, ObservedExecutionManifest manifest) throws Exception {
        return Files.write(temporary.resolve(name), new ManifestCodec().encode(manifest));
    }

    @Test
    void largeStructuralDiffIsBoundedWithoutHidingTruncationOrChangingTheDecision() {
        List<ManifestAttempt> before = java.util.stream.IntStream.range(1, 61)
                .mapToObj(i -> new ManifestAttempt("orders", String.format("%064x", i), 0,
                        List.of(), AttemptOutcome.CALLBACK_RETURNED, 1)).toList();
        List<ManifestAttempt> after = java.util.stream.IntStream.range(61, 121)
                .mapToObj(i -> new ManifestAttempt("orders", String.format("%064x", i), 0,
                        List.of(), AttemptOutcome.CALLBACK_RETURNED, 1)).toList();
        var baseline = new ObservedExecutionManifest(1, "operation", CaptureStatus.COMPLETE,
                ManifestPolicy.strict(60, 1), ManifestCounts.from(before), before);
        var candidate = new ObservedExecutionManifest(1, "operation", CaptureStatus.COMPLETE,
                ManifestPolicy.strict(60, 1), ManifestCounts.from(after), after);
        var report = ManifestReviewReport.compare(baseline, candidate);
        assertEquals(120, report.verification().diffs().size());
        assertEquals(1, report.strictExitCode());
        assertTrue(report.toJson().contains("\"omittedFindingCount\":20"));
        assertTrue(report.toMarkdown().contains("120 total; 20 omitted"));
        assertEquals(100, report.toMarkdown().lines().filter(line -> line.startsWith("- **RCM")).count());
    }

    private static int run(Path baseline, Path candidate, String format, Path output) {
        return ManifestReviewCli.run(arguments(baseline, candidate, format, output), System.err);
    }

    private static String[] arguments(Path baseline, Path candidate, String format, Path output) {
        return new String[]{"--baseline", baseline.toString(), "--candidate", candidate.toString(),
                "--format", format, "--output", output.toString()};
    }

    private static ObservedExecutionManifest manifest(int multiplicity) {
        var attempt = new ManifestAttempt("orders", "a".repeat(64), 1,
                List.of("java.lang.Long"), AttemptOutcome.CALLBACK_RETURNED, multiplicity);
        return new ObservedExecutionManifest(1, "operation", CaptureStatus.COMPLETE,
                ManifestPolicy.strict(1, 1), ManifestCounts.from(List.of(attempt)), List.of(attempt));
    }

    private static ObservedExecutionManifest changedShape() {
        var attempt = new ManifestAttempt("orders", "b".repeat(64), 1,
                List.of("java.lang.Long"), AttemptOutcome.CALLBACK_RETURNED, 1);
        return new ObservedExecutionManifest(1, "operation", CaptureStatus.COMPLETE,
                ManifestPolicy.strict(1, 1), ManifestCounts.from(List.of(attempt)), List.of(attempt));
    }

    private static ObservedExecutionManifest copy(ObservedExecutionManifest source, int schema,
            String operation, CaptureStatus status, ManifestPolicy policy) {
        return new ObservedExecutionManifest(schema, operation, status, policy, source.counts(), source.attempts());
    }
}
