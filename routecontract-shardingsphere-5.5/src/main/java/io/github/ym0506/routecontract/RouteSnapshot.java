package io.github.ym0506.routecontract;

import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

/**
 * Immutable result of one named operation capture.
 *
 * <p>This is observed callback evidence rather than a complete ShardingSphere route plan. Counts
 * and sets are redundantly validated against {@code attempts}; callback return does not prove
 * transaction commit or business success.</p>
 *
 * @param schemaVersion snapshot schema version
 * @param operationId opaque caller-supplied operation identifier
 * @param status completeness classification derived from outcomes and collector diagnostics
 * @param observedPhysicalAttemptCount total observed physical JDBC execution attempts
 * @param callbackReturnedCount attempts whose callbacks returned normally
 * @param callbackFailureCount attempts whose callbacks reported an {@link Exception}
 * @param unknownOutcomeCount attempts with a start callback but no matching finish callback
 * @param trunkThreadFlagCount attempts marked as trunk-thread callbacks by ShardingSphere
 * @param workerThreadFlagCount attempts marked as worker-thread callbacks by ShardingSphere
 * @param observedDataSourceNames unique sorted data-source names present in {@code attempts}
 * @param attempts immutable attempt evidence in deterministic canonical order
 * @param collectorDiagnostics stable diagnostics that make the capture incomplete
 */
public record RouteSnapshot(
        int schemaVersion,
        String operationId,
        CaptureStatus status,
        int observedPhysicalAttemptCount,
        int callbackReturnedCount,
        int callbackFailureCount,
        int unknownOutcomeCount,
        int trunkThreadFlagCount,
        int workerThreadFlagCount,
        List<String> observedDataSourceNames,
        List<PhysicalExecutionAttempt> attempts,
        List<String> collectorDiagnostics) {

    /** Schema version produced and accepted by this release. */
    public static final int CURRENT_SCHEMA_VERSION = 1;

    /**
     * Creates an immutable snapshot after validating all redundant counts, sets, and status.
     *
     * @param schemaVersion must equal {@link #CURRENT_SCHEMA_VERSION}
     * @param operationId non-null opaque operation identifier
     * @param status classification derived from outcomes and diagnostics
     * @param observedPhysicalAttemptCount count that must equal {@code attempts.size()}
     * @param callbackReturnedCount count of normal-return outcomes
     * @param callbackFailureCount count of callback-failure outcomes
     * @param unknownOutcomeCount count of start-only outcomes
     * @param trunkThreadFlagCount count of trunk-thread flags
     * @param workerThreadFlagCount count of worker-thread flags
     * @param observedDataSourceNames unique names that must exactly match the attempts
     * @param attempts physical-attempt evidence
     * @param collectorDiagnostics stable collector diagnostics
     */
    public RouteSnapshot {
        if (schemaVersion != CURRENT_SCHEMA_VERSION) {
            throw new IllegalArgumentException("Unsupported snapshot schema: " + schemaVersion);
        }
        operationId = Objects.requireNonNull(operationId, "operationId");
        status = Objects.requireNonNull(status, "status");
        observedDataSourceNames = List.copyOf(
                Objects.requireNonNull(observedDataSourceNames, "observedDataSourceNames"));
        attempts = List.copyOf(Objects.requireNonNull(attempts, "attempts"));
        collectorDiagnostics = List.copyOf(
                Objects.requireNonNull(collectorDiagnostics, "collectorDiagnostics"));
        if (callbackReturnedCount < 0 || callbackFailureCount < 0 || unknownOutcomeCount < 0
                || trunkThreadFlagCount < 0 || workerThreadFlagCount < 0) {
            throw new IllegalArgumentException("Snapshot counts must be non-negative");
        }
        if (observedPhysicalAttemptCount != attempts.size()) {
            throw new IllegalArgumentException("observedPhysicalAttemptCount must equal attempts size");
        }
        if (observedPhysicalAttemptCount > RouteContract.MAX_RETAINED_ATTEMPTS_PER_CAPTURE) {
            throw new IllegalArgumentException("observedPhysicalAttemptCount exceeds the capture safety ceiling");
        }
        if (callbackReturnedCount + callbackFailureCount + unknownOutcomeCount != observedPhysicalAttemptCount) {
            throw new IllegalArgumentException("callback outcome counts must sum to observedPhysicalAttemptCount");
        }
        if (trunkThreadFlagCount + workerThreadFlagCount != observedPhysicalAttemptCount) {
            throw new IllegalArgumentException("thread flag counts must sum to observedPhysicalAttemptCount");
        }
        if (callbackReturnedCount != count(attempts, AttemptOutcome.CALLBACK_RETURNED)
                || callbackFailureCount != count(attempts, AttemptOutcome.CALLBACK_FAILURE)
                || unknownOutcomeCount != count(attempts, AttemptOutcome.START_REPORTED)) {
            throw new IllegalArgumentException("callback outcome counts must match attempts");
        }
        if (trunkThreadFlagCount != count(attempts, ThreadRole.TRUNK)
                || workerThreadFlagCount != count(attempts, ThreadRole.WORKER)) {
            throw new IllegalArgumentException("thread flag counts must match attempts");
        }
        Set<String> declaredDataSourceNames = new TreeSet<>(observedDataSourceNames);
        Set<String> attemptedDataSourceNames = new TreeSet<>();
        for (PhysicalExecutionAttempt attempt : attempts) {
            attemptedDataSourceNames.add(attempt.observedDataSourceName());
        }
        if (declaredDataSourceNames.size() != observedDataSourceNames.size()
                || !declaredDataSourceNames.equals(attemptedDataSourceNames)) {
            throw new IllegalArgumentException("observedDataSourceNames must uniquely match attempts");
        }
        CaptureStatus derivedStatus = !collectorDiagnostics.isEmpty() || unknownOutcomeCount > 0
                ? CaptureStatus.INCOMPLETE
                : callbackFailureCount > 0 ? CaptureStatus.REPORTED_EXECUTION_FAILURE : CaptureStatus.COMPLETE;
        if (status != derivedStatus) {
            throw new IllegalArgumentException("status must match callback outcomes and collector diagnostics");
        }
        if (status == CaptureStatus.COMPLETE && observedPhysicalAttemptCount == 0) {
            throw new IllegalArgumentException("COMPLETE status requires at least one observed attempt");
        }
    }

    private static int count(
            final List<PhysicalExecutionAttempt> attempts,
            final AttemptOutcome expectedOutcome) {
        return (int) attempts.stream().filter(attempt -> attempt.outcome() == expectedOutcome).count();
    }

    private static int count(
            final List<PhysicalExecutionAttempt> attempts,
            final ThreadRole expectedRole) {
        return (int) attempts.stream().filter(attempt -> attempt.threadRole() == expectedRole).count();
    }
}
