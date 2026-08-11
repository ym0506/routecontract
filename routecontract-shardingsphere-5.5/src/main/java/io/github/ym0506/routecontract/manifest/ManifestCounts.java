package io.github.ym0506.routecontract.manifest;

import io.github.ym0506.routecontract.AttemptOutcome;

import java.util.List;

/**
 * Redundant manifest counts validated against canonical structural entries on every read.
 *
 * @param observedPhysicalAttemptCount total attempts after expanding multiplicities
 * @param callbackReturnedCount attempts whose callbacks returned normally
 * @param callbackFailureCount attempts whose callbacks reported an execution failure
 * @param unknownOutcomeCount attempts with a start callback but no matching finish callback
 * @param distinctObservedDataSourceNameCount number of distinct stable data-source aliases
 */
public record ManifestCounts(
        int observedPhysicalAttemptCount,
        int callbackReturnedCount,
        int callbackFailureCount,
        int unknownOutcomeCount,
        int distinctObservedDataSourceNameCount) {

    /**
     * Creates validated redundant manifest counts.
     *
     * @param observedPhysicalAttemptCount non-negative total attempt count
     * @param callbackReturnedCount non-negative normal-return count
     * @param callbackFailureCount non-negative callback-failure count
     * @param unknownOutcomeCount non-negative start-only count
     * @param distinctObservedDataSourceNameCount non-negative distinct-alias count
     */
    public ManifestCounts {
        if (observedPhysicalAttemptCount < 0
                || callbackReturnedCount < 0
                || callbackFailureCount < 0
                || unknownOutcomeCount < 0
                || distinctObservedDataSourceNameCount < 0) {
            throw new IllegalArgumentException("Manifest counts must be non-negative");
        }
        if (callbackReturnedCount + callbackFailureCount + unknownOutcomeCount
                != observedPhysicalAttemptCount) {
            throw new IllegalArgumentException("Callback outcome counts must sum to observedPhysicalAttemptCount");
        }
    }

    static ManifestCounts from(final List<ManifestAttempt> attempts) {
        int total = 0;
        int returned = 0;
        int failed = 0;
        int unknown = 0;
        java.util.Set<String> aliases = new java.util.TreeSet<>();
        for (ManifestAttempt attempt : attempts) {
            total = Math.addExact(total, attempt.multiplicity());
            aliases.add(attempt.observedDataSourceAlias());
            if (attempt.outcome() == AttemptOutcome.CALLBACK_RETURNED) {
                returned = Math.addExact(returned, attempt.multiplicity());
            } else if (attempt.outcome() == AttemptOutcome.CALLBACK_FAILURE) {
                failed = Math.addExact(failed, attempt.multiplicity());
            } else {
                unknown = Math.addExact(unknown, attempt.multiplicity());
            }
        }
        return new ManifestCounts(total, returned, failed, unknown, aliases.size());
    }
}
