package io.github.ym0506.routecontract.manifest;

import io.github.ym0506.routecontract.PhysicalExecutionAttempt;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteSnapshot;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/**
 * Canonical, value-minimized observed-execution contract for one named application operation.
 *
 * <p>It contains neither timestamps nor capture UUIDs, and it deliberately excludes thread-role
 * flags, raw SQL, parameter values, exception messages, and environment-specific data-source
 * names. The operation identifier is opaque contract data; no manifest API derives a file path
 * from it.</p>
 *
 * <p>A manifest may preserve diagnostic evidence for a callback failure or incomplete capture,
 * but only {@link io.github.ym0506.routecontract.CaptureStatus#COMPLETE COMPLETE} evidence with
 * no callback failures or unknown outcomes is eligible for contract matching.</p>
 *
 * @param schemaVersion manifest schema version
 * @param operationId non-blank caller identifier, at most 200 Java UTF-16 code units
 * @param captureStatus completeness classification copied from the source snapshot
 * @param policy explicit budgets and structural enforcement policy
 * @param counts redundant counts validated against canonical attempts
 * @param attempts immutable canonical structural multiset entries
 */
public record ObservedExecutionManifest(
        int schemaVersion,
        String operationId,
        io.github.ym0506.routecontract.CaptureStatus captureStatus,
        ManifestPolicy policy,
        ManifestCounts counts,
        List<ManifestAttempt> attempts) {

    /** Manifest schema version produced and supported by this release. */
    public static final int CURRENT_SCHEMA_VERSION = 1;

    /**
     * Creates and validates a canonical observed-execution manifest.
     *
     * @param schemaVersion positive manifest schema version
     * @param operationId non-blank opaque identifier, at most 200 Java UTF-16 code units
     * @param captureStatus source capture completeness classification
     * @param policy explicit verification policy
     * @param counts counts that must equal the recomputed canonical-attempt counts
     * @param attempts structural entries; they are sorted and must not duplicate signatures
     */
    public ObservedExecutionManifest {
        if (schemaVersion <= 0) {
            throw new IllegalArgumentException("schemaVersion must be positive");
        }
        operationId = requireOperationId(operationId);
        captureStatus = Objects.requireNonNull(captureStatus, "captureStatus");
        policy = Objects.requireNonNull(policy, "policy");
        counts = Objects.requireNonNull(counts, "counts");
        attempts = new ArrayList<>(Objects.requireNonNull(attempts, "attempts"));
        attempts.sort(ManifestAttempt.CANONICAL_ORDER);
        for (int index = 1; index < attempts.size(); index++) {
            if (ManifestAttempt.CANONICAL_ORDER.compare(attempts.get(index - 1), attempts.get(index)) == 0) {
                throw new IllegalArgumentException("Duplicate structural manifest attempt; use multiplicity");
            }
        }
        attempts = List.copyOf(attempts);
        ManifestCounts recomputed = ManifestCounts.from(attempts);
        if (!counts.equals(recomputed)) {
            throw new IllegalArgumentException("Manifest counts do not match canonical attempts: declared="
                    + counts + ", recomputed=" + recomputed);
        }
        if (counts.observedPhysicalAttemptCount() > RouteContract.MAX_RETAINED_ATTEMPTS_PER_CAPTURE) {
            throw new IllegalArgumentException("Manifest attempt count exceeds the capture safety ceiling");
        }
        validateCaptureStatus(captureStatus, counts);
    }

    /**
     * Builds a canonical manifest candidate from a completed or diagnosable capture.
     *
     * <p>Every observed data-source name must have an explicit, collision-free alias. Counts are
     * independently recomputed from attempt entries and checked against the source snapshot.</p>
     *
     * @param snapshot immutable observed callback evidence
     * @param aliases explicit reviewed mapping from observed names to stable aliases
     * @param policy policy to embed in the candidate
     * @return canonical manifest preserving the snapshot's diagnostic or contract-eligible status
     */
    public static ObservedExecutionManifest from(
            final RouteSnapshot snapshot,
            final DataSourceAliases aliases,
            final ManifestPolicy policy) {
        Objects.requireNonNull(snapshot, "snapshot");
        Objects.requireNonNull(aliases, "aliases");
        Objects.requireNonNull(policy, "policy");

        Map<ManifestAttempt, Integer> multiplicities = new TreeMap<>(ManifestAttempt.CANONICAL_ORDER);
        Set<String> recomputedObservedNames = new TreeSet<>();
        for (PhysicalExecutionAttempt attempt : snapshot.attempts()) {
            recomputedObservedNames.add(attempt.observedDataSourceName());
            ManifestAttempt structural = new ManifestAttempt(
                    aliases.resolve(attempt.observedDataSourceName()),
                    attempt.sqlFingerprint(),
                    attempt.parameterCount(),
                    attempt.parameterTypes(),
                    attempt.outcome(),
                    1);
            multiplicities.merge(structural, 1, Math::addExact);
        }

        List<ManifestAttempt> canonicalAttempts = multiplicities.entrySet().stream()
                .map(entry -> entry.getKey().withMultiplicity(entry.getValue()))
                .toList();
        ManifestCounts recomputedCounts = ManifestCounts.from(canonicalAttempts);
        validateSnapshotCounts(snapshot, recomputedObservedNames, recomputedCounts);
        return new ObservedExecutionManifest(
                CURRENT_SCHEMA_VERSION,
                snapshot.operationId(),
                snapshot.status(),
                policy,
                recomputedCounts,
                canonicalAttempts);
    }

    private static void validateSnapshotCounts(
            final RouteSnapshot snapshot,
            final Set<String> recomputedObservedNames,
            final ManifestCounts recomputedCounts) {
        Set<String> declaredObservedNames = new TreeSet<>(snapshot.observedDataSourceNames());
        boolean namesAreUnique = declaredObservedNames.size() == snapshot.observedDataSourceNames().size();
        if (!namesAreUnique || !declaredObservedNames.equals(recomputedObservedNames)) {
            throw new IllegalArgumentException("Snapshot observed data-source names do not match its attempts");
        }
        if (snapshot.observedPhysicalAttemptCount() != recomputedCounts.observedPhysicalAttemptCount()
                || snapshot.callbackReturnedCount() != recomputedCounts.callbackReturnedCount()
                || snapshot.callbackFailureCount() != recomputedCounts.callbackFailureCount()
                || snapshot.unknownOutcomeCount() != recomputedCounts.unknownOutcomeCount()) {
            throw new IllegalArgumentException("Snapshot callback counts do not match its attempts");
        }
    }

    private static void validateCaptureStatus(
            final io.github.ym0506.routecontract.CaptureStatus status,
            final ManifestCounts counts) {
        if (status == io.github.ym0506.routecontract.CaptureStatus.COMPLETE
                && (counts.callbackFailureCount() != 0 || counts.unknownOutcomeCount() != 0)) {
            throw new IllegalArgumentException("COMPLETE captureStatus requires only callback returns");
        }
        if (status == io.github.ym0506.routecontract.CaptureStatus.COMPLETE
                && counts.observedPhysicalAttemptCount() == 0) {
            throw new IllegalArgumentException(
                    "COMPLETE captureStatus requires at least one observed attempt");
        }
        if (status == io.github.ym0506.routecontract.CaptureStatus.REPORTED_EXECUTION_FAILURE
                && (counts.callbackFailureCount() == 0 || counts.unknownOutcomeCount() != 0)) {
            throw new IllegalArgumentException(
                    "REPORTED_EXECUTION_FAILURE requires a callback failure and no unknown outcome");
        }
        if (status != io.github.ym0506.routecontract.CaptureStatus.INCOMPLETE
                && counts.unknownOutcomeCount() != 0) {
            throw new IllegalArgumentException("Unknown outcomes require INCOMPLETE captureStatus");
        }
    }

    private static String requireNonBlank(final String value, final String label) {
        Objects.requireNonNull(value, label);
        if (value.isBlank()) {
            throw new IllegalArgumentException(label + " must not be blank");
        }
        return value;
    }

    private static String requireOperationId(final String value) {
        String result = requireNonBlank(value, "operationId");
        if (result.length() > RouteContract.MAX_OPERATION_ID_UTF16_CODE_UNITS) {
            throw new IllegalArgumentException("operationId must not exceed "
                    + RouteContract.MAX_OPERATION_ID_UTF16_CODE_UNITS
                    + " Java UTF-16 code units");
        }
        return result;
    }
}
