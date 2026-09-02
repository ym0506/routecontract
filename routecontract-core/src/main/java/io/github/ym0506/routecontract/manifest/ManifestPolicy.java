package io.github.ym0506.routecontract.manifest;

/**
 * Explicit budgets evaluated before an approved structural baseline is compared.
 *
 * @param maxObservedPhysicalAttempts maximum permitted physical JDBC execution attempts
 * @param maxDistinctObservedDataSourceNames maximum permitted distinct stable data-source aliases
 * @param requireNoCallbackFailures whether callback failures are forbidden; v0.1 requires {@code true}
 * @param requireExactExecutionSignatures whether structural signature drift is blocking instead of review-only
 */
public record ManifestPolicy(
        int maxObservedPhysicalAttempts,
        int maxDistinctObservedDataSourceNames,
        boolean requireNoCallbackFailures,
        boolean requireExactExecutionSignatures) {

    /**
     * Creates a validated manifest policy.
     *
     * @param maxObservedPhysicalAttempts non-negative physical-attempt budget
     * @param maxDistinctObservedDataSourceNames non-negative distinct-alias budget
     * @param requireNoCallbackFailures must be {@code true} in the v0.1 manifest schema
     * @param requireExactExecutionSignatures whether signature drift must block verification
     */
    public ManifestPolicy {
        if (maxObservedPhysicalAttempts < 0) {
            throw new IllegalArgumentException("maxObservedPhysicalAttempts must be non-negative");
        }
        if (maxDistinctObservedDataSourceNames < 0) {
            throw new IllegalArgumentException("maxDistinctObservedDataSourceNames must be non-negative");
        }
        if (!requireNoCallbackFailures) {
            throw new IllegalArgumentException(
                    "v0.1 manifests must require no callback failures; failure snapshots are diagnostic-only");
        }
    }

    /**
     * Creates the strict v0.1 default, including exact execution-signature enforcement.
     *
     * @param maxObservedPhysicalAttempts non-negative physical-attempt budget
     * @param maxDistinctObservedDataSourceNames non-negative distinct-alias budget
     * @return policy that blocks callback failures and every structural signature difference
     */
    public static ManifestPolicy strict(
            final int maxObservedPhysicalAttempts,
            final int maxDistinctObservedDataSourceNames) {
        return new ManifestPolicy(
                maxObservedPhysicalAttempts,
                maxDistinctObservedDataSourceNames,
                true,
                true);
    }

    /**
     * Creates a budget-focused policy: fingerprint-only signature changes require review but do not
     * fail the explicit blocking-check predicate.
     *
     * @param maxObservedPhysicalAttempts non-negative physical-attempt budget
     * @param maxDistinctObservedDataSourceNames non-negative distinct-alias budget
     * @return policy that enforces budgets and callback success while making signature drift review-only
     */
    public static ManifestPolicy budgetOnly(
            final int maxObservedPhysicalAttempts,
            final int maxDistinctObservedDataSourceNames) {
        return new ManifestPolicy(
                maxObservedPhysicalAttempts,
                maxDistinctObservedDataSourceNames,
                true,
                false);
    }
}
