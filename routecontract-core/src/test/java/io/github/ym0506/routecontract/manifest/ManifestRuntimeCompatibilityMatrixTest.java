package io.github.ym0506.routecontract.manifest;

import io.github.ym0506.routecontract.CaptureStatus;
import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import org.junit.jupiter.api.DynamicNode;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestFactory;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.DynamicContainer.dynamicContainer;
import static org.junit.jupiter.api.DynamicTest.dynamicTest;

/** A-22: decoded compatibility categories are distinct from documents that cannot be decoded. */
class ManifestRuntimeCompatibilityMatrixTest {
    private static final String ADAPTER = "apache-shardingsphere-jdbc/sql-execution-hook";
    private static final String IDENTITY_553 = identityJson(ADAPTER, 1, "5.5.3", "5.5.3");
    private static final ManifestCodec CODEC = new ManifestCodec();

    // Independent acceptance table, indexed by the declared fixture category, never isSupported().
    // Rows/columns: exact 553, exact 552, structurally valid unsupported identity.
    private static final String[][] RUNTIME_CODES = {
            {"RCM000", "RCM005", "RCM004"},
            {"RCM005", "RCM000", "RCM004"},
            {"RCM004", "RCM004", "RCM004"}
    };

    @TempDir
    Path temporary;

    @TestFactory
    Stream<DynamicNode> everyOrderedDecodedIdentityPair() {
        List<DecodedCase> cases = decodedCases();
        return cases.stream().map(approvedCase -> dynamicContainer(approvedCase.name(),
                cases.stream().map(candidateCase -> dynamicTest(candidateCase.name(), () -> {
                    var approved = decodeCanonical(approvedCase);
                    var candidate = decodeCanonical(candidateCase);
                    assertDecision(approved, candidate, expectedCodes(approvedCase, candidateCase));
                }))));
    }

    @Test
    void compatibilityFindingsPrecedeOperationEligibilityAndBudgetFindings() throws Exception {
        DecodedCase legacy = decodedCases().get(0);
        // Each incompatible category is checked on both sides, including schema + runtime errors.
        for (DecodedCase other : decodedCases()) {
            for (List<DecodedCase> pair : List.of(List.of(legacy, other), List.of(other, legacy))) {
                var approved = decodeCanonical(pair.get(0));
                var candidate = decodeCanonical(pair.get(1));
                approved = new ObservedExecutionManifest(approved.schemaVersion(), approved.runtimeIdentity(),
                        "approved-operation", CaptureStatus.INCOMPLETE, approved.policy(),
                        approved.counts(), approved.attempts());
                var attempts = List.of(candidate.attempts().get(0).withMultiplicity(2));
                candidate = new ObservedExecutionManifest(candidate.schemaVersion(), candidate.runtimeIdentity(),
                        "candidate-operation", CaptureStatus.INCOMPLETE, candidate.policy(),
                        ManifestCounts.from(attempts), attempts);
                List<String> expected = new ArrayList<>(expectedCodes(pair.get(0), pair.get(1)));
                expected.remove("RCM000");
                expected.add("RCM002");
                expected.add("RCM003");
                assertDecision(approved, candidate, expected);
            }
        }
    }

    @TestFactory
    Stream<DynamicNode> malformedDocumentsNeverBecomeCompatibilityResults() {
        return malformedCases().stream().map(input -> dynamicContainer(input.name(), Stream.of(
                dynamicTest("byte and stream decoders", () -> {
                    byte[] bytes = input.json().getBytes(StandardCharsets.UTF_8);
                    assertThrowsExactly(ManifestFormatException.class, () -> CODEC.decode(bytes));
                    assertThrowsExactly(ManifestFormatException.class,
                            () -> CODEC.decode(new ByteArrayInputStream(bytes)));
                }),
                dynamicTest("CLI rejects either input in both report formats", () -> {
                    Path directory = Files.createTempDirectory(temporary, "malformed-");
                    Path valid = Files.writeString(directory.resolve("valid.json"), document(2, IDENTITY_553));
                    Path invalid = Files.writeString(directory.resolve("invalid.json"), input.json());
                    for (String format : List.of("json", "markdown")) {
                        for (boolean invalidBaseline : List.of(false, true)) {
                            Path output = directory.resolve(format + "-" + invalidBaseline);
                            var errors = new ByteArrayOutputStream();
                            try (var stream = new PrintStream(errors, true, StandardCharsets.UTF_8)) {
                                int exit = ManifestReviewCli.run(new String[]{
                                        "--baseline", (invalidBaseline ? invalid : valid).toString(),
                                        "--candidate", (invalidBaseline ? valid : invalid).toString(),
                                        "--format", format, "--output", output.toString()}, stream);
                                assertEquals(2, exit);
                            }
                            assertFalse(Files.exists(output), "invalid input must not create a report");
                            String diagnostic = errors.toString(StandardCharsets.UTF_8);
                            assertTrue(diagnostic.contains("RC_REPORT_ERROR"));
                            assertFalse(diagnostic.contains("RCM"), "no comparison result for malformed input");
                        }
                    }
                    assertEquals(document(2, IDENTITY_553), Files.readString(valid));
                    assertEquals(input.json(), Files.readString(invalid));
                }))));
    }

    private static void assertDecision(ObservedExecutionManifest approved,
            ObservedExecutionManifest candidate, List<String> expected) {
        var verifier = new ManifestVerifier();
        var result = verifier.verify(approved, candidate);
        boolean match = expected.equals(List.of("RCM000"));
        assertEquals(match ? VerificationStatus.MATCH : VerificationStatus.INCOMPATIBLE, result.status());
        assertEquals(expected, result.diffs().stream().map(diff -> diff.code().stableCode()).toList());
        assertTrue(result.diffs().stream().allMatch(diff -> diff.severity()
                == (match ? ManifestDiffSeverity.INFO : ManifestDiffSeverity.BLOCKING)));
        assertEquals(result, verifier.verify(approved, candidate), "finding order and details are deterministic");
        var report = ManifestReviewReport.compare(approved, candidate);
        assertEquals(result, report.verification());
        assertEquals(match ? 0 : 1, report.strictExitCode());
    }

    private static ObservedExecutionManifest decodeCanonical(DecodedCase fixture) throws Exception {
        byte[] bytes = document(fixture.schema(), fixture.identity().json()).getBytes(StandardCharsets.UTF_8);
        var decoded = CODEC.decode(bytes);
        assertEquals(fixture.schema(), decoded.schemaVersion());
        IdentityCase identity = fixture.identity();
        assertEquals(new ShardingSphereRuntimeIdentity(identity.adapter(), identity.revision(),
                identity.executor(), identity.spi()), decoded.runtimeIdentity());
        assertArrayEquals(bytes, CODEC.encode(decoded), "literal canonical fixture must remain byte-stable");
        assertEquals(decoded, CODEC.decode(new ByteArrayInputStream(bytes)));
        return decoded;
    }

    private static List<String> expectedCodes(DecodedCase approved, DecodedCase candidate) {
        List<String> result = new ArrayList<>();
        if (approved.schema() == 3 || candidate.schema() == 3) {
            result.add("RCM001");
        }
        String runtime = RUNTIME_CODES[approved.identity().category()][candidate.identity().category()];
        if (!runtime.equals("RCM000") || result.isEmpty()) {
            result.add(runtime);
        }
        return List.copyOf(result);
    }

    private static List<DecodedCase> decodedCases() {
        List<IdentityCase> identities = List.of(
                new IdentityCase("exact553", ADAPTER, 1, "5.5.3", "5.5.3", 0),
                new IdentityCase("exact552", ADAPTER, 1, "5.5.2", "5.5.2", 1),
                new IdentityCase("unknown-adapter", "example/other-hook", 1, "5.5.3", "5.5.3", 2),
                new IdentityCase("unknown-revision", ADAPTER, 2, "5.5.3", "5.5.3", 2),
                new IdentityCase("future-both", ADAPTER, 1, "5.5.4", "5.5.4", 2),
                new IdentityCase("mixed552-553", ADAPTER, 1, "5.5.2", "5.5.3", 2),
                new IdentityCase("mixed553-552", ADAPTER, 1, "5.5.3", "5.5.2", 2),
                new IdentityCase("future-executor", ADAPTER, 1, "5.5.4", "5.5.3", 2),
                new IdentityCase("future-spi", ADAPTER, 1, "5.5.3", "5.5.4", 2),
                new IdentityCase("snapshot-both", ADAPTER, 1, "5.5.3-SNAPSHOT", "5.5.3-SNAPSHOT", 2));
        List<DecodedCase> result = new ArrayList<>();
        result.add(new DecodedCase("schema1-implicit553", 1, identities.get(0)));
        for (int schema : List.of(2, 3)) {
            for (IdentityCase identity : identities) {
                result.add(new DecodedCase("schema" + schema + "-" + identity.name(), schema, identity));
            }
        }
        return List.copyOf(result);
    }

    private static List<MalformedCase> malformedCases() {
        List<MalformedCase> result = new ArrayList<>();
        String valid = document(2, IDENTITY_553);
        String identityProperty = "\"runtimeIdentity\":" + IDENTITY_553;
        result.add(new MalformedCase("missing-identity", replaceOnce(valid, identityProperty + ",", "")));
        for (String invalid : List.of("null", "{}", "[]", "\"identity\"", "1", "1.0", "true")) {
            result.add(new MalformedCase("identity-value-" + invalid,
                    replaceOnce(valid, identityProperty, "\"runtimeIdentity\":" + invalid)));
        }
        List<String> fields = List.of("adapterId", "adapterContractVersion",
                "infraExecutorImplementationVersion", "infraSpiImplementationVersion");
        List<String> values = List.of("\"" + ADAPTER + "\"", "1", "\"5.5.3\"", "\"5.5.3\"");
        for (int index = 0; index < fields.size(); index++) {
            String field = fields.get(index);
            String property = "\"" + field + "\":" + values.get(index);
            boolean last = index == fields.size() - 1;
            result.add(new MalformedCase("missing-" + field,
                    replaceOnce(valid, last ? "," + property : property + ",", "")));
            List<String> invalidValues = new ArrayList<>(List.of("null", "true", "[]", "{}", "1.5"));
            if (index == 1) {
                invalidValues.addAll(List.of("\"1\"", "0", "-1", "2147483648"));
            } else {
                invalidValues.addAll(List.of("1", "\"\"", "\" \"", "\"5.5.3 \"",
                        "\"bad_value\"", "\"한글\"", "\"" + "1".repeat(index == 0 ? 129 : 101) + "\""));
            }
            for (String invalid : invalidValues) {
                result.add(new MalformedCase(field + "-value-" + invalid,
                        replaceOnce(valid, property, "\"" + field + "\":" + invalid)));
            }
            result.add(new MalformedCase("duplicate-" + field,
                    replaceOnce(valid, property, property + "," + property)));
        }
        result.add(new MalformedCase("duplicate-identity",
                replaceOnce(valid, identityProperty, identityProperty + "," + identityProperty)));
        result.add(new MalformedCase("unknown-identity-field",
                replaceOnce(valid, IDENTITY_553, IDENTITY_553.substring(0, IDENTITY_553.length() - 1)
                        + ",\"unknown\":1}")));
        result.add(new MalformedCase("unknown-root-field",
                replaceOnce(valid, "\"schemaVersion\":2", "\"schemaVersion\":2,\"unknown\":1")));
        result.add(new MalformedCase("duplicate-schema",
                replaceOnce(valid, "\"schemaVersion\":2", "\"schemaVersion\":2,\"schemaVersion\":2")));
        result.add(new MalformedCase("legacy-with-explicit-identity",
                replaceOnce(valid, "\"schemaVersion\":2", "\"schemaVersion\":1")));
        result.add(new MalformedCase("future-schema-with-missing-identity",
                replaceOnce(document(3, IDENTITY_553), identityProperty + ",", "")));
        for (String invalid : List.of("null", "true", "[]", "{}", "\"2\"", "2.0", "0", "-1", "2147483648")) {
            result.add(new MalformedCase("schema-value-" + invalid,
                    replaceOnce(valid, "\"schemaVersion\":2", "\"schemaVersion\":" + invalid)));
        }
        result.add(new MalformedCase("empty-document", ""));
        result.add(new MalformedCase("truncated-json", valid.substring(0, valid.length() - 2)));
        result.add(new MalformedCase("trailing-document", valid + "{}"));
        result.add(new MalformedCase("trailing-comma", valid.stripTrailing().replaceFirst("}$", ",}")));
        result.add(new MalformedCase("unquoted-property", replaceOnce(valid, "\"runtimeIdentity\"", "runtimeIdentity")));
        result.add(new MalformedCase("comment", "/* comment */" + valid));
        for (MalformedCase input : result) {
            assertNotEquals(valid, input.json(), "malformed fixture must change the valid document");
        }
        assertEquals(result.size(), result.stream().map(MalformedCase::name).distinct().count());
        return List.copyOf(result);
    }

    private static String replaceOnce(String source, String target, String replacement) {
        assertEquals(source.indexOf(target), source.lastIndexOf(target), "fixture target must be unique");
        assertTrue(source.contains(target), "fixture target must exist");
        return source.replace(target, replacement);
    }

    private static String identityJson(String adapter, int revision, String executor, String spi) {
        return "{\"adapterId\":\"" + adapter + "\",\"adapterContractVersion\":" + revision
                + ",\"infraExecutorImplementationVersion\":\"" + executor
                + "\",\"infraSpiImplementationVersion\":\"" + spi + "\"}";
    }

    private static String document(int schema, String identity) {
        return "{\"schemaVersion\":" + schema
                + (schema == 1 ? "" : ",\"runtimeIdentity\":" + identity)
                + ",\"operationId\":\"operation\",\"captureStatus\":\"COMPLETE\","
                + "\"policy\":{\"maxObservedPhysicalAttempts\":1,\"maxDistinctObservedDataSourceNames\":1,"
                + "\"requireNoCallbackFailures\":true,\"requireExactExecutionSignatures\":true},"
                + "\"counts\":{\"observedPhysicalAttemptCount\":1,\"callbackReturnedCount\":1,"
                + "\"callbackFailureCount\":0,\"unknownOutcomeCount\":0,\"distinctObservedDataSourceNameCount\":1},"
                + "\"attempts\":[{\"observedDataSourceAlias\":\"orders\",\"sqlFingerprint\":\"" + "a".repeat(64)
                + "\",\"parameterCount\":0,\"parameterTypes\":[],\"outcome\":\"CALLBACK_RETURNED\",\"multiplicity\":1}]}\n";
    }

    private record IdentityCase(String name, String adapter, int revision, String executor, String spi, int category) {
        String json() {
            return identityJson(adapter, revision, executor, spi);
        }
    }

    private record DecodedCase(String name, int schema, IdentityCase identity) { }

    private record MalformedCase(String name, String json) { }
}
