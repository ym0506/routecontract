package io.github.ym0506.routecontract.manifest;

import io.github.ym0506.routecontract.CaptureStatus;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.TreeSet;

/** Applies compatibility, contract eligibility, policy, and structural checks in that order. */
public final class ManifestVerifier {

    /**
     * Builds a candidate using the approved policy and verifies it against the approved manifest.
     *
     * <p>Compatibility and contract eligibility are evaluated before aliases are resolved. A
     * callback-failure or incomplete snapshot therefore returns a structured diagnostic result
     * rather than becoming an approved or enforceable candidate manifest.</p>
     *
     * @param approved reviewed baseline manifest whose policy governs verification
     * @param snapshot newly observed operation evidence
     * @param aliases explicit reviewed mapping from observed names to stable aliases
     * @return final status and deterministic findings at the highest-precedence failing level
     */
    public ManifestVerificationResult verify(
            final ObservedExecutionManifest approved,
            final RouteSnapshot snapshot,
            final DataSourceAliases aliases) {
        Objects.requireNonNull(approved, "approved");
        Objects.requireNonNull(snapshot, "snapshot");
        Objects.requireNonNull(aliases, "aliases");
        List<ManifestDiff> incompatible = compatibilityFindings(approved, snapshot);
        if (!incompatible.isEmpty()) {
            return new ManifestVerificationResult(VerificationStatus.INCOMPATIBLE, incompatible);
        }
        ManifestVerificationResult notEligible = notEligibleResult(snapshot);
        if (notEligible != null) {
            return notEligible;
        }
        return verify(approved, ObservedExecutionManifest.from(snapshot, aliases, approved.policy()));
    }

    /**
     * Verifies two already validated manifests using the approved manifest's policy.
     *
     * <p>Checks are applied in this order: compatibility and approved eligibility, candidate
     * eligibility, explicit budgets, then structural drift. Callback-failure manifests remain
     * diagnostic evidence and cannot match an approved contract.</p>
     *
     * @param approved reviewed baseline manifest whose policy governs verification
     * @param candidate newly generated candidate manifest
     * @return final status and deterministic findings at the highest-precedence failing level
     */
    public ManifestVerificationResult verify(
            final ObservedExecutionManifest approved,
            final ObservedExecutionManifest candidate) {
        Objects.requireNonNull(approved, "approved");
        Objects.requireNonNull(candidate, "candidate");

        List<ManifestDiff> incompatible = compatibilityFindings(approved, candidate);
        if (!incompatible.isEmpty()) {
            return new ManifestVerificationResult(VerificationStatus.INCOMPATIBLE, incompatible);
        }

        ManifestVerificationResult notEligible = notEligibleResult(candidate);
        if (notEligible != null) {
            return notEligible;
        }

        List<ManifestDiff> policyViolations = policyFindings(approved.policy(), candidate.counts());
        if (!policyViolations.isEmpty()) {
            return new ManifestVerificationResult(VerificationStatus.POLICY_VIOLATION, policyViolations);
        }

        List<ManifestDiff> drift = driftFindings(approved, candidate);
        if (!drift.isEmpty()) {
            boolean blocking = drift.stream()
                    .anyMatch(diff -> diff.severity() == ManifestDiffSeverity.BLOCKING);
            return new ManifestVerificationResult(
                    blocking ? VerificationStatus.DRIFT : VerificationStatus.REVIEW_REQUIRED,
                    drift);
        }

        return new ManifestVerificationResult(
                VerificationStatus.MATCH,
                List.of(new ManifestDiff(
                        ManifestDiffCode.MATCH,
                        ManifestDiffSeverity.INFO,
                        "approved structural multiset matched")));
    }

    private static List<ManifestDiff> compatibilityFindings(
            final ObservedExecutionManifest approved,
            final ObservedExecutionManifest candidate) {
        List<ManifestDiff> findings = new ArrayList<>();
        if (!isSupportedSchema(approved.schemaVersion()) || !isSupportedSchema(candidate.schemaVersion())) {
            findings.add(new ManifestDiff(
                    ManifestDiffCode.UNSUPPORTED_SCHEMA,
                    ManifestDiffSeverity.BLOCKING,
                    "supported=[1, " + ObservedExecutionManifest.CURRENT_SCHEMA_VERSION + "]"
                            + ", approved=" + approved.schemaVersion()
                            + ", candidate=" + candidate.schemaVersion()));
        }
        addRuntimeIdentityFindings(findings, approved.runtimeIdentity(), candidate.runtimeIdentity());
        if (!approved.operationId().equals(candidate.operationId())) {
            findings.add(new ManifestDiff(
                    ManifestDiffCode.OPERATION_ID_MISMATCH,
                    ManifestDiffSeverity.BLOCKING,
                    "approved=" + approved.operationId() + ", candidate=" + candidate.operationId()));
        }
        if (!isContractEligible(approved)) {
            findings.add(new ManifestDiff(
                    ManifestDiffCode.APPROVED_MANIFEST_NOT_ELIGIBLE,
                    ManifestDiffSeverity.BLOCKING,
                    "approved captureStatus=" + approved.captureStatus()
                            + ", callbackFailureCount=" + approved.counts().callbackFailureCount()
                            + ", unknownOutcomeCount=" + approved.counts().unknownOutcomeCount()));
        }
        return List.copyOf(findings);
    }

    private static List<ManifestDiff> compatibilityFindings(
            final ObservedExecutionManifest approved,
            final RouteSnapshot snapshot) {
        List<ManifestDiff> findings = new ArrayList<>();
        if (!isSupportedSchema(approved.schemaVersion()) || !isSupportedSnapshotSchema(snapshot.schemaVersion())) {
            findings.add(new ManifestDiff(
                    ManifestDiffCode.UNSUPPORTED_SCHEMA,
                    ManifestDiffSeverity.BLOCKING,
                    "supported=[1, " + ObservedExecutionManifest.CURRENT_SCHEMA_VERSION + "]"
                            + ", approved=" + approved.schemaVersion()
                            + ", candidateSnapshot=" + snapshot.schemaVersion()));
        }
        addRuntimeIdentityFindings(findings, approved.runtimeIdentity(), snapshot.runtimeIdentity());
        if (!approved.operationId().equals(snapshot.operationId())) {
            findings.add(new ManifestDiff(
                    ManifestDiffCode.OPERATION_ID_MISMATCH,
                    ManifestDiffSeverity.BLOCKING,
                    "approved=" + approved.operationId() + ", candidate=" + snapshot.operationId()));
        }
        if (!isContractEligible(approved)) {
            findings.add(new ManifestDiff(
                    ManifestDiffCode.APPROVED_MANIFEST_NOT_ELIGIBLE,
                    ManifestDiffSeverity.BLOCKING,
                    "approved captureStatus=" + approved.captureStatus()
                            + ", callbackFailureCount=" + approved.counts().callbackFailureCount()
                            + ", unknownOutcomeCount=" + approved.counts().unknownOutcomeCount()));
        }
        return List.copyOf(findings);
    }

    private static void addRuntimeIdentityFindings(
            final List<ManifestDiff> findings,
            final ShardingSphereRuntimeIdentity approved,
            final ShardingSphereRuntimeIdentity candidate) {
        boolean approvedSupported = approved.isSupported();
        boolean candidateSupported = candidate.isSupported();
        if (!approvedSupported || !candidateSupported) {
            findings.add(new ManifestDiff(
                    ManifestDiffCode.UNSUPPORTED_RUNTIME_IDENTITY,
                    ManifestDiffSeverity.BLOCKING,
                    "approved=" + approved + ", candidate=" + candidate));
        } else if (!approved.equals(candidate)) {
            findings.add(new ManifestDiff(
                    ManifestDiffCode.RUNTIME_IDENTITY_MISMATCH,
                    ManifestDiffSeverity.BLOCKING,
                    "approved=" + approved + ", candidate=" + candidate));
        }
    }

    private static boolean isSupportedSchema(final int schemaVersion) {
        return schemaVersion == 1 || schemaVersion == ObservedExecutionManifest.CURRENT_SCHEMA_VERSION;
    }

    private static boolean isSupportedSnapshotSchema(final int schemaVersion) {
        return schemaVersion == 1 || schemaVersion == RouteSnapshot.CURRENT_SCHEMA_VERSION;
    }

    private static boolean isContractEligible(final ObservedExecutionManifest manifest) {
        return manifest.captureStatus() == CaptureStatus.COMPLETE
                && manifest.counts().callbackFailureCount() == 0
                && manifest.counts().unknownOutcomeCount() == 0;
    }

    private static ManifestVerificationResult notEligibleResult(final RouteSnapshot snapshot) {
        if (snapshot.status() == CaptureStatus.INCOMPLETE || snapshot.unknownOutcomeCount() != 0
                || !snapshot.collectorDiagnostics().isEmpty()) {
            return new ManifestVerificationResult(
                    VerificationStatus.NOT_ELIGIBLE,
                    List.of(new ManifestDiff(
                            ManifestDiffCode.CAPTURE_INCOMPLETE,
                            ManifestDiffSeverity.BLOCKING,
                            "captureStatus=" + snapshot.status()
                                    + ", unknownOutcomeCount=" + snapshot.unknownOutcomeCount()
                                    + ", collectorDiagnostics=" + snapshot.collectorDiagnostics())));
        }
        if (snapshot.status() == CaptureStatus.REPORTED_EXECUTION_FAILURE
                || snapshot.callbackFailureCount() != 0) {
            return new ManifestVerificationResult(
                    VerificationStatus.NOT_ELIGIBLE,
                    List.of(new ManifestDiff(
                            ManifestDiffCode.CALLBACK_FAILURE_NOT_ELIGIBLE,
                            ManifestDiffSeverity.BLOCKING,
                            "captureStatus=" + snapshot.status()
                                    + ", callbackFailureCount=" + snapshot.callbackFailureCount())));
        }
        return null;
    }

    private static ManifestVerificationResult notEligibleResult(
            final ObservedExecutionManifest manifest) {
        if (manifest.captureStatus() == CaptureStatus.INCOMPLETE
                || manifest.counts().unknownOutcomeCount() != 0) {
            return new ManifestVerificationResult(
                    VerificationStatus.NOT_ELIGIBLE,
                    List.of(new ManifestDiff(
                            ManifestDiffCode.CAPTURE_INCOMPLETE,
                            ManifestDiffSeverity.BLOCKING,
                            "captureStatus=" + manifest.captureStatus()
                                    + ", unknownOutcomeCount=" + manifest.counts().unknownOutcomeCount())));
        }
        if (manifest.captureStatus() == CaptureStatus.REPORTED_EXECUTION_FAILURE
                || manifest.counts().callbackFailureCount() != 0) {
            return new ManifestVerificationResult(
                    VerificationStatus.NOT_ELIGIBLE,
                    List.of(new ManifestDiff(
                            ManifestDiffCode.CALLBACK_FAILURE_NOT_ELIGIBLE,
                            ManifestDiffSeverity.BLOCKING,
                            "captureStatus=" + manifest.captureStatus()
                                    + ", callbackFailureCount=" + manifest.counts().callbackFailureCount())));
        }
        return null;
    }

    private static List<ManifestDiff> policyFindings(
            final ManifestPolicy policy,
            final ManifestCounts counts) {
        List<ManifestDiff> findings = new ArrayList<>();
        if (counts.observedPhysicalAttemptCount() > policy.maxObservedPhysicalAttempts()) {
            findings.add(new ManifestDiff(
                    ManifestDiffCode.ATTEMPT_BUDGET_EXCEEDED,
                    ManifestDiffSeverity.BLOCKING,
                    "maximum=" + policy.maxObservedPhysicalAttempts()
                            + ", observed=" + counts.observedPhysicalAttemptCount()));
        }
        if (counts.distinctObservedDataSourceNameCount() > policy.maxDistinctObservedDataSourceNames()) {
            findings.add(new ManifestDiff(
                    ManifestDiffCode.DATA_SOURCE_BUDGET_EXCEEDED,
                    ManifestDiffSeverity.BLOCKING,
                    "maximum=" + policy.maxDistinctObservedDataSourceNames()
                            + ", observed=" + counts.distinctObservedDataSourceNameCount()));
        }
        return List.copyOf(findings);
    }

    private static List<ManifestDiff> driftFindings(
            final ObservedExecutionManifest approved,
            final ObservedExecutionManifest candidate) {
        List<ManifestDiff> findings = new ArrayList<>();
        if (!approved.policy().equals(candidate.policy())) {
            findings.add(new ManifestDiff(
                    ManifestDiffCode.POLICY_CHANGED,
                    ManifestDiffSeverity.BLOCKING,
                    "candidate policy differs from approved policy"));
        }

        if (approved.counts().observedPhysicalAttemptCount()
                != candidate.counts().observedPhysicalAttemptCount()) {
            findings.add(new ManifestDiff(
                    ManifestDiffCode.OBSERVED_ATTEMPT_COUNT_CHANGED,
                    ManifestDiffSeverity.BLOCKING,
                    "expected=" + approved.counts().observedPhysicalAttemptCount()
                            + ", observed=" + candidate.counts().observedPhysicalAttemptCount()));
        }
        TreeSet<String> approvedAliases = observedAliases(approved.attempts());
        TreeSet<String> candidateAliases = observedAliases(candidate.attempts());
        if (!approvedAliases.equals(candidateAliases)) {
            findings.add(new ManifestDiff(
                    ManifestDiffCode.OBSERVED_DATA_SOURCE_SET_CHANGED,
                    ManifestDiffSeverity.BLOCKING,
                    "expected=" + approvedAliases + ", observed=" + candidateAliases));
        }
        if (approved.counts().callbackReturnedCount() != candidate.counts().callbackReturnedCount()
                || approved.counts().callbackFailureCount() != candidate.counts().callbackFailureCount()
                || approved.counts().unknownOutcomeCount() != candidate.counts().unknownOutcomeCount()) {
            findings.add(new ManifestDiff(
                    ManifestDiffCode.OUTCOME_COUNTS_CHANGED,
                    ManifestDiffSeverity.BLOCKING,
                    "expected=[returned=" + approved.counts().callbackReturnedCount()
                            + ", failure=" + approved.counts().callbackFailureCount()
                            + ", unknown=" + approved.counts().unknownOutcomeCount()
                            + "], observed=[returned=" + candidate.counts().callbackReturnedCount()
                            + ", failure=" + candidate.counts().callbackFailureCount()
                            + ", unknown=" + candidate.counts().unknownOutcomeCount() + "]"));
        }

        Map<ManifestAttempt, Integer> approvedMultiset = toMultiset(approved.attempts());
        Map<ManifestAttempt, Integer> candidateMultiset = toMultiset(candidate.attempts());
        TreeSet<ManifestAttempt> signatures = new TreeSet<>(ManifestAttempt.CANONICAL_ORDER);
        signatures.addAll(approvedMultiset.keySet());
        signatures.addAll(candidateMultiset.keySet());
        for (ManifestAttempt signature : signatures) {
            int approvedMultiplicity = approvedMultiset.getOrDefault(signature, 0);
            int candidateMultiplicity = candidateMultiset.getOrDefault(signature, 0);
            ManifestDiffSeverity signatureSeverity = approved.policy().requireExactExecutionSignatures()
                    ? ManifestDiffSeverity.BLOCKING
                    : ManifestDiffSeverity.REVIEW;
            if (candidateMultiplicity < approvedMultiplicity) {
                findings.add(new ManifestDiff(
                        ManifestDiffCode.STRUCTURAL_ATTEMPT_REMOVED,
                        signatureSeverity,
                        signature.structuralDescription() + ", expectedMultiplicity="
                                + approvedMultiplicity + ", observedMultiplicity=" + candidateMultiplicity));
            } else if (candidateMultiplicity > approvedMultiplicity) {
                findings.add(new ManifestDiff(
                        ManifestDiffCode.STRUCTURAL_ATTEMPT_ADDED,
                        signatureSeverity,
                        signature.structuralDescription() + ", expectedMultiplicity="
                                + approvedMultiplicity + ", observedMultiplicity=" + candidateMultiplicity));
            }
        }
        return List.copyOf(findings);
    }

    private static TreeSet<String> observedAliases(final List<ManifestAttempt> attempts) {
        TreeSet<String> result = new TreeSet<>();
        for (ManifestAttempt attempt : attempts) {
            result.add(attempt.observedDataSourceAlias());
        }
        return result;
    }

    private static Map<ManifestAttempt, Integer> toMultiset(final List<ManifestAttempt> attempts) {
        Map<ManifestAttempt, Integer> result = new TreeMap<>(ManifestAttempt.CANONICAL_ORDER);
        for (ManifestAttempt attempt : attempts) {
            result.put(attempt, attempt.multiplicity());
        }
        return result;
    }
}
