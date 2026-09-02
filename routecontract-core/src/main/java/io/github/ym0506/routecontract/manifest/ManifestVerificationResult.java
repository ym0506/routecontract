package io.github.ym0506.routecontract.manifest;

import java.util.List;
import java.util.Objects;

/**
 * Final verification classification and deterministic findings at that precedence level.
 *
 * @param status mutually exclusive final status
 * @param diffs non-empty deterministic findings belonging to the final precedence level
 */
public record ManifestVerificationResult(VerificationStatus status, List<ManifestDiff> diffs) {

    /**
     * Creates an invariant-checked verification result.
     *
     * @param status mutually exclusive final status
     * @param diffs non-empty deterministic findings consistent with {@code status}
     */
    public ManifestVerificationResult {
        status = Objects.requireNonNull(status, "status");
        diffs = List.copyOf(Objects.requireNonNull(diffs, "diffs"));
        if (diffs.isEmpty()) {
            throw new IllegalArgumentException("Verification results must contain at least one diff code");
        }
        if (status == VerificationStatus.MATCH
                && (diffs.size() != 1 || diffs.get(0).code() != ManifestDiffCode.MATCH)) {
            throw new IllegalArgumentException("MATCH result must contain only the MATCH code");
        }
        if (status != VerificationStatus.MATCH
                && diffs.stream().anyMatch(diff -> diff.code() == ManifestDiffCode.MATCH)) {
            throw new IllegalArgumentException("Non-match result must not contain the MATCH code");
        }
        if (status == VerificationStatus.REVIEW_REQUIRED
                && diffs.stream().anyMatch(diff -> diff.severity() == ManifestDiffSeverity.BLOCKING)) {
            throw new IllegalArgumentException("REVIEW_REQUIRED result must not contain blocking findings");
        }
    }

    /**
     * Reports whether candidate and approved manifests match exactly.
     *
     * @return {@code true} only for {@link VerificationStatus#MATCH}
     */
    public boolean matched() {
        return status == VerificationStatus.MATCH;
    }

    /**
     * Reports whether CI-blocking checks pass, including a result that still needs human review.
     *
     * @return {@code true} for {@link VerificationStatus#MATCH} or
     *         {@link VerificationStatus#REVIEW_REQUIRED}
     */
    public boolean passesBlockingChecks() {
        return status == VerificationStatus.MATCH || status == VerificationStatus.REVIEW_REQUIRED;
    }
}
