package io.github.ym0506.routecontract;

import java.util.List;
import java.util.Objects;

/**
 * Value-minimized evidence for one observed physical JDBC execution attempt.
 *
 * <p>The SQL text and parameter values are deliberately absent. The fingerprint is an unsalted
 * SHA-256 digest of the exact SQL string supplied to the hook, so it is pseudonymous evidence and
 * may be guessable for low-entropy SQL.</p>
 *
 * @param observedDataSourceName data-source name reported by the ShardingSphere callback
 * @param sqlFingerprint lowercase SHA-256 digest of the exact callback SQL string encoded as UTF-8
 * @param parameterCount number of callback parameters
 * @param parameterTypes ordered Java runtime type names, using {@code "null"} for a null value
 * @param threadRole trunk/worker flag reported by ShardingSphere
 * @param outcome last callback state observed for this attempt
 * @param reportedFailureType exception class name for {@link AttemptOutcome#CALLBACK_FAILURE}, otherwise {@code null}
 */
public record PhysicalExecutionAttempt(
        String observedDataSourceName,
        String sqlFingerprint,
        int parameterCount,
        List<String> parameterTypes,
        ThreadRole threadRole,
        AttemptOutcome outcome,
        String reportedFailureType) {

    /**
     * Creates validated value-minimized evidence for one observed physical attempt.
     *
     * @param observedDataSourceName non-blank callback-reported data-source name
     * @param sqlFingerprint lowercase SHA-256 digest of the exact callback SQL encoded as UTF-8
     * @param parameterCount non-negative number of callback parameters
     * @param parameterTypes ordered, non-blank Java runtime type names
     * @param threadRole thread flag reported by ShardingSphere
     * @param outcome last observed callback state
     * @param reportedFailureType nullable exception class name, permitted only for a failure outcome
     */
    public PhysicalExecutionAttempt {
        observedDataSourceName = Objects.requireNonNull(observedDataSourceName, "observedDataSourceName");
        if (observedDataSourceName.isBlank()) {
            throw new IllegalArgumentException("observedDataSourceName must not be blank");
        }
        sqlFingerprint = Objects.requireNonNull(sqlFingerprint, "sqlFingerprint");
        if (!sqlFingerprint.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("sqlFingerprint must be a lowercase SHA-256 hex digest");
        }
        if (parameterCount < 0) {
            throw new IllegalArgumentException("parameterCount must be non-negative");
        }
        parameterTypes = List.copyOf(Objects.requireNonNull(parameterTypes, "parameterTypes"));
        if (parameterTypes.size() != parameterCount) {
            throw new IllegalArgumentException("parameterTypes size must equal parameterCount");
        }
        for (String parameterType : parameterTypes) {
            if (parameterType.isBlank()) {
                throw new IllegalArgumentException("parameterTypes must not contain blank values");
            }
        }
        threadRole = Objects.requireNonNull(threadRole, "threadRole");
        outcome = Objects.requireNonNull(outcome, "outcome");
        if (outcome != AttemptOutcome.CALLBACK_FAILURE && reportedFailureType != null) {
            throw new IllegalArgumentException("reportedFailureType is only valid for CALLBACK_FAILURE");
        }
    }
}
