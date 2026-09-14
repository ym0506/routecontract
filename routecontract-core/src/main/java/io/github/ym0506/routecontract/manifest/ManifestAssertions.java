package io.github.ym0506.routecontract.manifest;

import io.github.ym0506.routecontract.RouteContractViolationException;

import java.util.Objects;

/** Deterministic CI assertions for manifest verification results. */
public final class ManifestAssertions {

    private ManifestAssertions() {
    }

    /**
     * Requires an exact approved-manifest match, including review-level differences.
     *
     * @param result verification result to enforce
     * @return the same result when it is an exact match
     * @throws RouteContractViolationException when the result is not an exact match
     */
    public static ManifestVerificationResult assertMatched(final ManifestVerificationResult result) {
        Objects.requireNonNull(result, "result");
        if (!result.matched()) {
            throw failure(result, "exact manifest match required");
        }
        return result;
    }

    /**
     * Requires every blocking check to pass while permitting explicit review-level differences.
     *
     * @param result verification result to enforce
     * @return the same result when it is a match or only needs human review
     * @throws RouteContractViolationException when the result contains a blocking failure
     */
    public static ManifestVerificationResult assertPassesBlockingChecks(
            final ManifestVerificationResult result) {
        Objects.requireNonNull(result, "result");
        if (!result.passesBlockingChecks()) {
            throw failure(result, "blocking manifest checks must pass");
        }
        return result;
    }

    private static RouteContractViolationException failure(
            final ManifestVerificationResult result,
            final String expectation) {
        StringBuilder message = new StringBuilder("Observed-execution contract violation: ")
                .append(expectation)
                .append(", status=")
                .append(result.status());
        for (ManifestDiff diff : result.diffs()) {
            message.append(System.lineSeparator())
                    .append("- ")
                    .append(diff.code().stableCode())
                    .append(' ')
                    .append(diff.severity())
                    .append(' ')
                    .append(diff.code())
                    .append(": ")
                    .append(diff.detail());
        }
        return new RouteContractViolationException(message.toString());
    }
}
