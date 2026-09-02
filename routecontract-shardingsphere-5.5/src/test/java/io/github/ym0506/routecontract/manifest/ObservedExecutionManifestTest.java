package io.github.ym0506.routecontract.manifest;

import io.github.ym0506.routecontract.AttemptOutcome;
import io.github.ym0506.routecontract.CaptureStatus;
import io.github.ym0506.routecontract.PhysicalExecutionAttempt;
import io.github.ym0506.routecontract.RouteContractViolationException;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import io.github.ym0506.routecontract.ThreadRole;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ObservedExecutionManifestTest {

    private static final String FINGERPRINT_A = "a".repeat(64);
    private static final String FINGERPRINT_B = "b".repeat(64);

    @TempDir
    Path temporaryDirectory;

    @Test
    void canonicalCodecAggregatesSortsAndOmitsVolatileCaptureFields() throws Exception {
        RouteSnapshot snapshot = snapshot(
                "checkout",
                CaptureStatus.COMPLETE,
                List.of(
                        attempt("prod_2", FINGERPRINT_B, List.of(Long.class.getName()),
                                ThreadRole.WORKER, AttemptOutcome.CALLBACK_RETURNED, null),
                        attempt("prod_1", FINGERPRINT_A, List.of(),
                                ThreadRole.TRUNK, AttemptOutcome.CALLBACK_RETURNED, null),
                        attempt("prod_2", FINGERPRINT_B, List.of(Long.class.getName()),
                                ThreadRole.TRUNK, AttemptOutcome.CALLBACK_RETURNED, null)));
        ObservedExecutionManifest manifest = ObservedExecutionManifest.from(
                snapshot,
                DataSourceAliases.of(Map.of("prod_1", "orders-a", "prod_2", "orders-b")),
                ManifestPolicy.strict(4, 2));

        ManifestCodec codec = new ManifestCodec();
        byte[] encoded = codec.encode(manifest);
        String json = new String(encoded, StandardCharsets.UTF_8);
        String expected = "{\"schemaVersion\":2,\"runtimeIdentity\":{"
                + "\"adapterId\":\"apache-shardingsphere-jdbc/sql-execution-hook\","
                + "\"adapterContractVersion\":1,"
                + "\"infraExecutorImplementationVersion\":\"5.5.3\","
                + "\"infraSpiImplementationVersion\":\"5.5.3\"},"
                + "\"operationId\":\"checkout\","
                + "\"captureStatus\":\"COMPLETE\",\"policy\":{"
                + "\"maxObservedPhysicalAttempts\":4,"
                + "\"maxDistinctObservedDataSourceNames\":2,"
                + "\"requireNoCallbackFailures\":true,"
                + "\"requireExactExecutionSignatures\":true},\"counts\":{"
                + "\"observedPhysicalAttemptCount\":3,\"callbackReturnedCount\":3,"
                + "\"callbackFailureCount\":0,\"unknownOutcomeCount\":0,"
                + "\"distinctObservedDataSourceNameCount\":2},\"attempts\":[{"
                + "\"observedDataSourceAlias\":\"orders-a\",\"sqlFingerprint\":\""
                + FINGERPRINT_A
                + "\",\"parameterCount\":0,\"parameterTypes\":[],"
                + "\"outcome\":\"CALLBACK_RETURNED\",\"multiplicity\":1},{"
                + "\"observedDataSourceAlias\":\"orders-b\",\"sqlFingerprint\":\""
                + FINGERPRINT_B
                + "\",\"parameterCount\":1,\"parameterTypes\":[\"java.lang.Long\"],"
                + "\"outcome\":\"CALLBACK_RETURNED\",\"multiplicity\":2}]}\n";

        assertEquals(expected, json);
        assertFalse(json.contains("prod_"));
        assertFalse(json.contains("threadRole"));
        assertFalse(json.contains("reportedFailureType"));
        assertFalse(json.contains("timestamp"));
        assertFalse(json.contains("uuid"));
        ObservedExecutionManifest decoded = codec.decode(encoded);
        assertEquals(manifest, decoded);
        assertArrayEquals(encoded, codec.encode(decoded));
    }

    @Test
    void legacySchemaOneDecodeEncodeIsByteStableAndCarriesImplicit553Identity() throws Exception {
        assertEquals(6, ObservedExecutionManifest.class.getConstructor(
                int.class,
                String.class,
                CaptureStatus.class,
                ManifestPolicy.class,
                ManifestCounts.class,
                List.class).getParameterCount());
        ManifestCodec codec = new ManifestCodec();
        byte[] schemaTwo = codec.encode(manifest(
                "legacy-operation", FINGERPRINT_A, ManifestPolicy.strict(1, 1)));
        String explicitIdentity = "\"schemaVersion\":2,\"runtimeIdentity\":{"
                + "\"adapterId\":\"apache-shardingsphere-jdbc/sql-execution-hook\","
                + "\"adapterContractVersion\":1,"
                + "\"infraExecutorImplementationVersion\":\"5.5.3\","
                + "\"infraSpiImplementationVersion\":\"5.5.3\"},";
        byte[] schemaOne = new String(schemaTwo, StandardCharsets.UTF_8)
                .replace(explicitIdentity, "\"schemaVersion\":1,")
                .getBytes(StandardCharsets.UTF_8);

        ObservedExecutionManifest decoded = codec.decode(schemaOne);

        assertEquals(1, decoded.schemaVersion());
        assertEquals(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3, decoded.runtimeIdentity());
        assertArrayEquals(schemaOne, codec.encode(decoded));
        ObservedExecutionManifest current = manifest(
                "current-operation", FINGERPRINT_A, ManifestPolicy.strict(1, 1));
        assertThrows(IllegalArgumentException.class, () -> new ObservedExecutionManifest(
                ObservedExecutionManifest.CURRENT_SCHEMA_VERSION,
                current.operationId(),
                current.captureStatus(),
                current.policy(),
                current.counts(),
                current.attempts()));
    }

    @Test
    void strictDecoderRejectsMalformedOrSchemaInconsistentRuntimeIdentity() throws Exception {
        ManifestCodec codec = new ManifestCodec();
        String canonical = new String(codec.encode(manifest(
                "runtime-identity", FINGERPRINT_A, ManifestPolicy.strict(1, 1))),
                StandardCharsets.UTF_8);
        String identity = "\"runtimeIdentity\":{"
                + "\"adapterId\":\"apache-shardingsphere-jdbc/sql-execution-hook\","
                + "\"adapterContractVersion\":1,"
                + "\"infraExecutorImplementationVersion\":\"5.5.3\","
                + "\"infraSpiImplementationVersion\":\"5.5.3\"},";

        List<String> malformed = List.of(
                canonical.replace(identity, ""),
                canonical.replace("\"adapterId\":\"apache-shardingsphere-jdbc/sql-execution-hook\",", ""),
                canonical.replace(
                        "\"adapterId\":\"apache-shardingsphere-jdbc/sql-execution-hook\"",
                        "\"adapterId\":\" \""),
                canonical.replace("\"adapterContractVersion\":1", "\"adapterContractVersion\":0"),
                canonical.replace(
                        "\"infraExecutorImplementationVersion\":\"5.5.3\"",
                        "\"infraExecutorImplementationVersion\":null"),
                canonical.replace(
                        "\"infraSpiImplementationVersion\":\"5.5.3\"",
                        "\"infraSpiImplementationVersion\":\"5.5.3\",\"unknown\":true"));
        for (String invalid : malformed) {
            assertThrows(ManifestFormatException.class,
                    () -> codec.decode(invalid.getBytes(StandardCharsets.UTF_8)));
        }

        String schemaOneWithExplicitIdentity = canonical.replace("\"schemaVersion\":2", "\"schemaVersion\":1");
        assertThrows(ManifestFormatException.class,
                () -> codec.decode(schemaOneWithExplicitIdentity.getBytes(StandardCharsets.UTF_8)));
    }

    @Test
    void strictDecoderRejectsTamperedCountsDuplicateFieldsAndUnknownProperties() throws Exception {
        ManifestCodec codec = new ManifestCodec();
        ObservedExecutionManifest manifest = manifest(
                "operation", FINGERPRINT_A, ManifestPolicy.strict(1, 1));
        String canonical = new String(codec.encode(manifest), StandardCharsets.UTF_8);

        String tamperedCount = canonical.replace(
                "\"observedPhysicalAttemptCount\":1",
                "\"observedPhysicalAttemptCount\":2");
        assertThrows(ManifestFormatException.class,
                () -> codec.decode(tamperedCount.getBytes(StandardCharsets.UTF_8)));
        String duplicate = canonical.replace(
                "{\"schemaVersion\":2",
                "{\"schemaVersion\":2,\"schemaVersion\":2");
        assertThrows(ManifestFormatException.class,
                () -> codec.decode(duplicate.getBytes(StandardCharsets.UTF_8)));
        String unknown = canonical.replace(
                "{\"schemaVersion\":2",
                "{\"unknown\":true,\"schemaVersion\":2");
        assertThrows(ManifestFormatException.class,
                () -> codec.decode(unknown.getBytes(StandardCharsets.UTF_8)));
    }

    @Test
    void codecNeverWritesAManifestThatItsOwnSizeLimitRejects() {
        ManifestAttempt oversizedAttempt = new ManifestAttempt(
                "x".repeat(ManifestCodec.MAX_MANIFEST_BYTES),
                FINGERPRINT_A,
                0,
                List.of(),
                AttemptOutcome.CALLBACK_RETURNED,
                1);
        ObservedExecutionManifest oversized = new ObservedExecutionManifest(
                ObservedExecutionManifest.CURRENT_SCHEMA_VERSION,
                ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3,
                "oversized",
                CaptureStatus.COMPLETE,
                ManifestPolicy.strict(1, 1),
                ManifestCounts.from(List.of(oversizedAttempt)),
                List.of(oversizedAttempt));

        IllegalArgumentException failure = assertThrows(
                IllegalArgumentException.class,
                () -> new ManifestCodec().encode(oversized));
        assertTrue(failure.getMessage().contains("exceeds"));
    }

    @Test
    void aliasesMustBeExplicitAndCollisionFree() {
        assertThrows(IllegalArgumentException.class,
                () -> DataSourceAliases.of(Map.of("prod_1", "orders", "prod_2", "orders")));
        RouteSnapshot snapshot = snapshot(
                "checkout",
                CaptureStatus.COMPLETE,
                List.of(attempt("prod_1", FINGERPRINT_A, List.of(),
                        ThreadRole.TRUNK, AttemptOutcome.CALLBACK_RETURNED, null)));
        assertThrows(IllegalArgumentException.class,
                () -> ObservedExecutionManifest.from(
                        snapshot,
                        DataSourceAliases.of(Map.of("another", "orders")),
                        ManifestPolicy.strict(1, 1)));
    }

    @Test
    void constructorRecomputesCountsAndCaptureStatus() {
        ManifestAttempt failure = new ManifestAttempt(
                "orders", FINGERPRINT_A, 0, List.of(), AttemptOutcome.CALLBACK_FAILURE, 1);
        assertThrows(IllegalArgumentException.class,
                () -> new ObservedExecutionManifest(
                        1,
                        "inconsistent-count",
                        CaptureStatus.REPORTED_EXECUTION_FAILURE,
                        ManifestPolicy.strict(1, 1),
                        new ManifestCounts(1, 1, 0, 0, 1),
                        List.of(failure)));
        assertThrows(IllegalArgumentException.class,
                () -> new ObservedExecutionManifest(
                        1,
                        "inconsistent-status",
                        CaptureStatus.COMPLETE,
                        ManifestPolicy.strict(1, 1),
                        ManifestCounts.from(List.of(failure)),
                        List.of(failure)));
        assertThrows(IllegalArgumentException.class,
                () -> new ManifestPolicy(1, 1, false, true));
        assertThrows(IllegalArgumentException.class,
                () -> new ObservedExecutionManifest(
                        1,
                        "forged-zero",
                        CaptureStatus.COMPLETE,
                        ManifestPolicy.strict(0, 0),
                        new ManifestCounts(0, 0, 0, 0, 0),
                        List.of()));
        String exactUtf16Boundary = "😀".repeat(100);
        ObservedExecutionManifest boundary = new ObservedExecutionManifest(
                1,
                exactUtf16Boundary,
                CaptureStatus.REPORTED_EXECUTION_FAILURE,
                ManifestPolicy.strict(1, 1),
                ManifestCounts.from(List.of(failure)),
                List.of(failure));
        assertEquals(exactUtf16Boundary, boundary.operationId());
        for (String invalidOperationId : List.of(" ", "x".repeat(201), "😀".repeat(101))) {
            assertThrows(IllegalArgumentException.class,
                    () -> new ObservedExecutionManifest(
                            1,
                            invalidOperationId,
                            CaptureStatus.REPORTED_EXECUTION_FAILURE,
                            ManifestPolicy.strict(1, 1),
                            ManifestCounts.from(List.of(failure)),
                            List.of(failure)));
        }
    }

    @Test
    void decoderRejectsHandAuthoredCompleteZeroAttemptManifest() {
        String forged = "{\"schemaVersion\":1,\"operationId\":\"forged-zero\","
                + "\"captureStatus\":\"COMPLETE\",\"policy\":{"
                + "\"maxObservedPhysicalAttempts\":0,"
                + "\"maxDistinctObservedDataSourceNames\":0,"
                + "\"requireNoCallbackFailures\":true,"
                + "\"requireExactExecutionSignatures\":true},\"counts\":{"
                + "\"observedPhysicalAttemptCount\":0,\"callbackReturnedCount\":0,"
                + "\"callbackFailureCount\":0,\"unknownOutcomeCount\":0,"
                + "\"distinctObservedDataSourceNameCount\":0},\"attempts\":[]}\n";

        assertThrows(ManifestFormatException.class,
                () -> new ManifestCodec().decode(forged.getBytes(StandardCharsets.UTF_8)));
    }

    @Test
    void decoderRejectsCompactMultiplicityAboveTheCaptureSafetyCeiling() {
        ManifestCodec codec = new ManifestCodec();
        String canonical = new String(codec.encode(manifest(
                "forged-over-limit", FINGERPRINT_A, ManifestPolicy.strict(1, 1))),
                StandardCharsets.UTF_8);
        int forgedCount = io.github.ym0506.routecontract.RouteContract
                .MAX_RETAINED_ATTEMPTS_PER_CAPTURE + 1;
        String forged = canonical
                .replace("\"maxObservedPhysicalAttempts\":1",
                        "\"maxObservedPhysicalAttempts\":" + forgedCount)
                .replace("\"observedPhysicalAttemptCount\":1",
                        "\"observedPhysicalAttemptCount\":" + forgedCount)
                .replace("\"callbackReturnedCount\":1",
                        "\"callbackReturnedCount\":" + forgedCount)
                .replace("\"multiplicity\":1", "\"multiplicity\":" + forgedCount);

        assertThrows(ManifestFormatException.class,
                () -> codec.decode(forged.getBytes(StandardCharsets.UTF_8)));
    }

    @Test
    void strictPolicyBlocksFingerprintOnlyStructuralDrift() {
        ManifestPolicy strict = ManifestPolicy.strict(1, 1);
        ObservedExecutionManifest approved = manifest("checkout", FINGERPRINT_A, strict);
        ObservedExecutionManifest candidate = manifest("checkout", FINGERPRINT_B, strict);

        ManifestVerificationResult result = new ManifestVerifier().verify(approved, candidate);

        assertEquals(VerificationStatus.DRIFT, result.status());
        assertFalse(result.passesBlockingChecks());
        assertEquals(
                List.of(
                        ManifestDiffCode.STRUCTURAL_ATTEMPT_REMOVED,
                        ManifestDiffCode.STRUCTURAL_ATTEMPT_ADDED),
                result.diffs().stream().map(ManifestDiff::code).toList());
        assertTrue(result.diffs().stream()
                .allMatch(diff -> diff.severity() == ManifestDiffSeverity.BLOCKING));
        RouteContractViolationException failure = assertThrows(
                RouteContractViolationException.class,
                () -> ManifestAssertions.assertMatched(result));
        assertTrue(failure.getMessage().contains("RCM301 BLOCKING STRUCTURAL_ATTEMPT_REMOVED"));
        assertTrue(failure.getMessage().contains("RCM302 BLOCKING STRUCTURAL_ATTEMPT_ADDED"));
    }

    @Test
    void budgetOnlyPolicySurfacesFingerprintDriftAsExplicitReview() {
        ManifestPolicy budgetOnly = ManifestPolicy.budgetOnly(1, 1);
        ObservedExecutionManifest approved = manifest("checkout", FINGERPRINT_A, budgetOnly);
        ObservedExecutionManifest candidate = manifest("checkout", FINGERPRINT_B, budgetOnly);

        ManifestVerificationResult result = new ManifestVerifier().verify(approved, candidate);

        assertEquals(VerificationStatus.REVIEW_REQUIRED, result.status());
        assertFalse(result.matched());
        assertTrue(result.passesBlockingChecks());
        assertTrue(result.diffs().stream()
                .allMatch(diff -> diff.severity() == ManifestDiffSeverity.REVIEW));
        ManifestAssertions.assertPassesBlockingChecks(result);
        assertThrows(RouteContractViolationException.class, () -> ManifestAssertions.assertMatched(result));
    }

    @Test
    void verificationHonorsIncompatibleIncompleteAndPolicyPrecedence() {
        ManifestPolicy policy = ManifestPolicy.budgetOnly(3, 2);
        ObservedExecutionManifest approved = manifest("checkout", FINGERPRINT_A, policy);
        ObservedExecutionManifest incompatibleIncomplete = new ObservedExecutionManifest(
                3,
                ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3,
                "checkout",
                CaptureStatus.INCOMPLETE,
                policy,
                new ManifestCounts(0, 0, 0, 0, 0),
                List.of());
        ManifestVerificationResult incompatible = new ManifestVerifier()
                .verify(approved, incompatibleIncomplete);
        assertEquals(VerificationStatus.INCOMPATIBLE, incompatible.status());
        assertEquals(ManifestDiffCode.UNSUPPORTED_SCHEMA, incompatible.diffs().get(0).code());

        ObservedExecutionManifest incomplete = new ObservedExecutionManifest(
                1,
                "checkout",
                CaptureStatus.INCOMPLETE,
                policy,
                new ManifestCounts(0, 0, 0, 0, 0),
                List.of());
        ManifestVerificationResult incompleteResult = new ManifestVerifier().verify(approved, incomplete);
        assertEquals(VerificationStatus.NOT_ELIGIBLE, incompleteResult.status());
        assertEquals(ManifestDiffCode.CAPTURE_INCOMPLETE, incompleteResult.diffs().get(0).code());

        RouteSnapshot incompleteWithUnaliasedAttempt = snapshot(
                "checkout",
                CaptureStatus.INCOMPLETE,
                List.of(attempt(
                        "unaliased",
                        FINGERPRINT_A,
                        List.of(),
                        ThreadRole.TRUNK,
                        AttemptOutcome.START_REPORTED,
                        null)));
        ManifestVerificationResult snapshotIncomplete = new ManifestVerifier().verify(
                approved,
                incompleteWithUnaliasedAttempt,
                DataSourceAliases.of(Map.of()));
        assertEquals(VerificationStatus.NOT_ELIGIBLE, snapshotIncomplete.status());
        assertEquals(ManifestDiffCode.CAPTURE_INCOMPLETE, snapshotIncomplete.diffs().get(0).code());

        ManifestPolicy limited = new ManifestPolicy(1, 1, true, false);
        ObservedExecutionManifest limitedApproved = manifest("checkout", FINGERPRINT_A, limited);
        RouteSnapshot overBudget = snapshot(
                "checkout",
                CaptureStatus.COMPLETE,
                List.of(
                        attempt("prod_1", FINGERPRINT_A, List.of(),
                                ThreadRole.TRUNK, AttemptOutcome.CALLBACK_RETURNED, null),
                        attempt("prod_2", FINGERPRINT_B, List.of(),
                                ThreadRole.WORKER, AttemptOutcome.CALLBACK_RETURNED, null),
                        attempt("prod_2", "c".repeat(64), List.of(),
                                ThreadRole.WORKER, AttemptOutcome.CALLBACK_RETURNED, null)));
        ObservedExecutionManifest candidate = ObservedExecutionManifest.from(
                overBudget,
                DataSourceAliases.of(Map.of("prod_1", "orders-a", "prod_2", "orders-b")),
                limited);
        ManifestVerificationResult policyResult = new ManifestVerifier().verify(limitedApproved, candidate);
        assertEquals(VerificationStatus.POLICY_VIOLATION, policyResult.status());
        assertEquals(
                List.of(
                        ManifestDiffCode.ATTEMPT_BUDGET_EXCEEDED,
                        ManifestDiffCode.DATA_SOURCE_BUDGET_EXCEEDED),
                policyResult.diffs().stream().map(ManifestDiff::code).toList());
    }

    @Test
    void legacy553AndExplicit553MatchBut552NeverSilentlySharesTheBaseline() {
        ManifestPolicy policy = ManifestPolicy.strict(1, 1);
        ObservedExecutionManifest current553 = manifest("checkout", FINGERPRINT_A, policy);
        ObservedExecutionManifest legacy553 = new ObservedExecutionManifest(
                1,
                current553.operationId(),
                current553.captureStatus(),
                current553.policy(),
                current553.counts(),
                current553.attempts());
        ObservedExecutionManifest current552 = new ObservedExecutionManifest(
                2,
                ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_2,
                current553.operationId(),
                current553.captureStatus(),
                current553.policy(),
                current553.counts(),
                current553.attempts());

        ManifestVerificationResult legacyTo553 = new ManifestVerifier().verify(legacy553, current553);
        ManifestVerificationResult legacyTo552 = new ManifestVerifier().verify(legacy553, current552);

        assertEquals(VerificationStatus.MATCH, legacyTo553.status());
        assertEquals(VerificationStatus.INCOMPATIBLE, legacyTo552.status());
        assertEquals(List.of(ManifestDiffCode.RUNTIME_IDENTITY_MISMATCH),
                legacyTo552.diffs().stream().map(ManifestDiff::code).toList());
        assertEquals("RCM005", ManifestDiffCode.RUNTIME_IDENTITY_MISMATCH.stableCode());
    }

    @Test
    void snapshotRuntimeMismatchIsRejectedBeforeAliasResolutionOrEligibilityChecks() {
        ManifestPolicy policy = ManifestPolicy.strict(1, 1);
        ObservedExecutionManifest approved553 = manifest("checkout", FINGERPRINT_A, policy);
        RouteSnapshot captured553 = snapshot(
                "checkout",
                CaptureStatus.COMPLETE,
                List.of(attempt(
                        "unaliased",
                        FINGERPRINT_A,
                        List.of(Long.class.getName()),
                        ThreadRole.TRUNK,
                        AttemptOutcome.CALLBACK_RETURNED,
                        null)));
        RouteSnapshot captured552 = new RouteSnapshot(
                captured553.schemaVersion(),
                ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_2,
                captured553.operationId(),
                captured553.status(),
                captured553.observedPhysicalAttemptCount(),
                captured553.callbackReturnedCount(),
                captured553.callbackFailureCount(),
                captured553.unknownOutcomeCount(),
                captured553.trunkThreadFlagCount(),
                captured553.workerThreadFlagCount(),
                captured553.observedDataSourceNames(),
                captured553.attempts(),
                captured553.collectorDiagnostics());

        ManifestVerificationResult result = new ManifestVerifier().verify(
                approved553,
                captured552,
                DataSourceAliases.of(Map.of()));

        assertEquals(VerificationStatus.INCOMPATIBLE, result.status());
        assertEquals(List.of(ManifestDiffCode.RUNTIME_IDENTITY_MISMATCH),
                result.diffs().stream().map(ManifestDiff::code).toList());
    }

    @Test
    void compatibilityFindingsUseSchemaRuntimeMismatchOperationEligibilityPrecedence() {
        ManifestPolicy policy = ManifestPolicy.strict(1, 1);
        ObservedExecutionManifest candidate553 = manifest("candidate-operation", FINGERPRINT_A, policy);
        ShardingSphereRuntimeIdentity unsupported = new ShardingSphereRuntimeIdentity(
                ShardingSphereRuntimeIdentity.SQL_EXECUTION_HOOK_ADAPTER_ID,
                ShardingSphereRuntimeIdentity.CURRENT_ADAPTER_CONTRACT_VERSION,
                "5.5.4",
                "5.5.4");
        ObservedExecutionManifest unsupportedApproved = new ObservedExecutionManifest(
                3,
                unsupported,
                "approved-operation",
                CaptureStatus.INCOMPLETE,
                policy,
                new ManifestCounts(0, 0, 0, 0, 0),
                List.of());

        ManifestVerificationResult unsupportedResult = new ManifestVerifier()
                .verify(unsupportedApproved, candidate553);

        assertEquals(VerificationStatus.INCOMPATIBLE, unsupportedResult.status());
        assertEquals(List.of(
                        ManifestDiffCode.UNSUPPORTED_SCHEMA,
                        ManifestDiffCode.UNSUPPORTED_RUNTIME_IDENTITY,
                        ManifestDiffCode.OPERATION_ID_MISMATCH,
                        ManifestDiffCode.APPROVED_MANIFEST_NOT_ELIGIBLE),
                unsupportedResult.diffs().stream().map(ManifestDiff::code).toList());
        assertEquals("RCM004", ManifestDiffCode.UNSUPPORTED_RUNTIME_IDENTITY.stableCode());

        ObservedExecutionManifest approved552 = new ObservedExecutionManifest(
                2,
                ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_2,
                "approved-operation",
                candidate553.captureStatus(),
                candidate553.policy(),
                candidate553.counts(),
                candidate553.attempts());
        ManifestVerificationResult mismatchResult = new ManifestVerifier().verify(approved552, candidate553);
        assertEquals(List.of(
                        ManifestDiffCode.RUNTIME_IDENTITY_MISMATCH,
                        ManifestDiffCode.OPERATION_ID_MISMATCH),
                mismatchResult.diffs().stream().map(ManifestDiff::code).toList());
    }

    @Test
    void exactStructuralMatchIgnoresAttemptOrderAndThreadRole() {
        ManifestPolicy policy = ManifestPolicy.strict(2, 1);
        RouteSnapshot approvedSnapshot = snapshot(
                "checkout",
                CaptureStatus.COMPLETE,
                List.of(
                        attempt("prod_1", FINGERPRINT_A, List.of(),
                                ThreadRole.TRUNK, AttemptOutcome.CALLBACK_RETURNED, null),
                        attempt("prod_1", FINGERPRINT_B, List.of(Integer.class.getName()),
                                ThreadRole.WORKER, AttemptOutcome.CALLBACK_RETURNED, null)));
        RouteSnapshot candidateSnapshot = snapshot(
                "checkout",
                CaptureStatus.COMPLETE,
                List.of(
                        attempt("prod_1", FINGERPRINT_B, List.of(Integer.class.getName()),
                                ThreadRole.TRUNK, AttemptOutcome.CALLBACK_RETURNED, null),
                        attempt("prod_1", FINGERPRINT_A, List.of(),
                                ThreadRole.WORKER, AttemptOutcome.CALLBACK_RETURNED, null)));
        DataSourceAliases aliases = DataSourceAliases.of(Map.of("prod_1", "orders"));

        ManifestVerificationResult result = new ManifestVerifier().verify(
                ObservedExecutionManifest.from(approvedSnapshot, aliases, policy),
                ObservedExecutionManifest.from(candidateSnapshot, aliases, policy));

        assertEquals(VerificationStatus.MATCH, result.status());
        assertTrue(result.matched());
    }

    @Test
    void failureBearingCandidateManifestCanNeverMatchAnApprovedContract() {
        ManifestPolicy policy = ManifestPolicy.strict(1, 1);
        ObservedExecutionManifest approved = manifest("checkout", FINGERPRINT_A, policy);
        RouteSnapshot failureSnapshot = snapshot(
                "checkout",
                CaptureStatus.REPORTED_EXECUTION_FAILURE,
                List.of(attempt(
                        "prod_1",
                        FINGERPRINT_A,
                        List.of(Long.class.getName()),
                        ThreadRole.WORKER,
                        AttemptOutcome.CALLBACK_FAILURE,
                        IllegalStateException.class.getName())));
        ObservedExecutionManifest failureCandidate = ObservedExecutionManifest.from(
                failureSnapshot,
                DataSourceAliases.of(Map.of("prod_1", "orders")),
                policy);

        ManifestVerificationResult result = new ManifestVerifier().verify(approved, failureCandidate);

        assertEquals(VerificationStatus.NOT_ELIGIBLE, result.status());
        assertFalse(result.passesBlockingChecks());
        assertEquals(ManifestDiffCode.CALLBACK_FAILURE_NOT_ELIGIBLE, result.diffs().get(0).code());
    }

    @Test
    void candidateWriteIsAtomicExplicitPathOnlyAndNeverOverwritesApprovedFile() throws Exception {
        ManifestStore store = new ManifestStore();
        Path approved = temporaryDirectory.resolve("approved.json");
        Path candidate = temporaryDirectory.resolve("nested/candidate.json");
        Files.writeString(approved, "APPROVED\n", StandardCharsets.UTF_8);
        ObservedExecutionManifest traversalNamed = manifest(
                "../../must-not-be-a-path", FINGERPRINT_A, ManifestPolicy.strict(1, 1));

        assertThrows(IllegalArgumentException.class,
                () -> store.writeCandidate(approved, approved, traversalNamed));
        assertEquals("APPROVED\n", Files.readString(approved, StandardCharsets.UTF_8));

        Path written = store.writeCandidate(approved, candidate, traversalNamed);
        assertEquals(candidate.toAbsolutePath().normalize(), written);
        assertEquals(traversalNamed, store.read(candidate));
        assertEquals("APPROVED\n", Files.readString(approved, StandardCharsets.UTF_8));
        try (var files = Files.list(candidate.getParent())) {
            assertEquals(List.of(candidate.getFileName()), files.map(Path::getFileName).toList());
        }
    }

    @Test
    void candidatePathCannotAliasANonexistentApprovedFileThroughASymlinkedParent() throws Exception {
        Path realDirectory = Files.createDirectory(temporaryDirectory.resolve("real"));
        Path linkedDirectory = temporaryDirectory.resolve("linked");
        Files.createSymbolicLink(linkedDirectory, realDirectory);
        Path approved = realDirectory.resolve("contract.json");
        Path candidateAlias = linkedDirectory.resolve("contract.json");

        IllegalArgumentException failure = assertThrows(
                IllegalArgumentException.class,
                () -> new ManifestStore().writeCandidate(
                        approved,
                        candidateAlias,
                        manifest("checkout", FINGERPRINT_A, ManifestPolicy.strict(1, 1))));
        assertTrue(failure.getMessage().contains("differ"));
        assertFalse(Files.exists(approved));
    }

    @Test
    void candidateWriteRejectsFileSystemEquivalentFutureApprovedLeaf() throws Exception {
        assertFutureLeafAliasHandling("case-probe", "BASELINE.json", "baseline.json");
    }

    @Test
    void candidateWriteRejectsUnicodeNormalizedFutureApprovedLeaf() throws Exception {
        assertFutureLeafAliasHandling("unicode-probe", "caf\u00e9.json", "cafe\u0301.json");
    }

    private void assertFutureLeafAliasHandling(
            final String directoryName,
            final String approvedName,
            final String candidateName) throws Exception {
        Path probeDirectory = Files.createDirectory(temporaryDirectory.resolve(directoryName));
        Path approved = probeDirectory.resolve(approvedName);
        Path candidate = probeDirectory.resolve(candidateName);

        Files.createFile(candidate);
        boolean fileSystemAliasesNames = Files.exists(approved, LinkOption.NOFOLLOW_LINKS)
                && Files.isSameFile(approved, candidate);
        Files.delete(candidate);

        ObservedExecutionManifest candidateManifest =
                manifest("checkout", FINGERPRINT_A, ManifestPolicy.strict(1, 1));
        if (fileSystemAliasesNames) {
            IllegalArgumentException failure = assertThrows(
                    IllegalArgumentException.class,
                    () -> new ManifestStore().writeCandidate(
                            approved, candidate, candidateManifest));
            assertTrue(failure.getMessage().contains("differ")
                    || failure.getMessage().contains("absent approvedFile"));
            assertFalse(Files.exists(approved, LinkOption.NOFOLLOW_LINKS));
            assertFalse(Files.exists(candidate, LinkOption.NOFOLLOW_LINKS));
        } else {
            Path written = new ManifestStore().writeCandidate(
                    approved, candidate, candidateManifest);
            assertEquals(candidate.toAbsolutePath().normalize(), written);
            assertFalse(Files.exists(approved, LinkOption.NOFOLLOW_LINKS));
            assertEquals(candidateManifest, new ManifestStore().read(candidate));
        }
    }

    @Test
    void danglingApprovedLeafSymlinkCannotBecomeAnAliasOfTheCandidate() throws Exception {
        Path candidate = temporaryDirectory.resolve("candidate.json");
        Path approved = temporaryDirectory.resolve("approved.json");
        Files.createSymbolicLink(approved, candidate.getFileName());

        IllegalArgumentException failure = assertThrows(
                IllegalArgumentException.class,
                () -> new ManifestStore().writeCandidate(
                        approved,
                        candidate,
                        manifest("checkout", FINGERPRINT_A, ManifestPolicy.strict(1, 1))));
        assertTrue(failure.getMessage().contains("symbolic links"));
        assertTrue(Files.isSymbolicLink(approved));
        assertFalse(Files.exists(candidate));
    }

    private static ObservedExecutionManifest manifest(
            final String operation,
            final String fingerprint,
            final ManifestPolicy policy) {
        RouteSnapshot snapshot = snapshot(
                operation,
                CaptureStatus.COMPLETE,
                List.of(attempt(
                        "prod_1",
                        fingerprint,
                        List.of(Long.class.getName()),
                        ThreadRole.TRUNK,
                        AttemptOutcome.CALLBACK_RETURNED,
                        null)));
        return ObservedExecutionManifest.from(
                snapshot,
                DataSourceAliases.of(Map.of("prod_1", "orders")),
                policy);
    }

    private static PhysicalExecutionAttempt attempt(
            final String observedDataSourceName,
            final String fingerprint,
            final List<String> parameterTypes,
            final ThreadRole threadRole,
            final AttemptOutcome outcome,
            final String reportedFailureType) {
        return new PhysicalExecutionAttempt(
                observedDataSourceName,
                fingerprint,
                parameterTypes.size(),
                parameterTypes,
                threadRole,
                outcome,
                reportedFailureType);
    }

    private static RouteSnapshot snapshot(
            final String operation,
            final CaptureStatus status,
            final List<PhysicalExecutionAttempt> attempts) {
        int returned = 0;
        int failures = 0;
        int unknown = 0;
        int trunk = 0;
        TreeSet<String> observedNames = new TreeSet<>();
        for (PhysicalExecutionAttempt attempt : attempts) {
            observedNames.add(attempt.observedDataSourceName());
            if (attempt.outcome() == AttemptOutcome.CALLBACK_RETURNED) {
                returned++;
            } else if (attempt.outcome() == AttemptOutcome.CALLBACK_FAILURE) {
                failures++;
            } else {
                unknown++;
            }
            if (attempt.threadRole() == ThreadRole.TRUNK) {
                trunk++;
            }
        }
        return new RouteSnapshot(
                RouteSnapshot.CURRENT_SCHEMA_VERSION,
                ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3,
                operation,
                status,
                attempts.size(),
                returned,
                failures,
                unknown,
                trunk,
                attempts.size() - trunk,
                List.copyOf(observedNames),
                attempts,
                List.of());
    }
}
