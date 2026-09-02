package io.github.ym0506.routecontract.manifest;

/** Mutually exclusive verification result, evaluated in declaration order. */
public enum VerificationStatus {
    /** Schema, runtime identity, operation identity, or approved-baseline eligibility prevents comparison. */
    INCOMPATIBLE,

    /** Candidate evidence is diagnostic-only and not eligible for contract comparison. */
    NOT_ELIGIBLE,

    /** Candidate evidence exceeds an explicit policy budget. */
    POLICY_VIOLATION,

    /** A blocking structural difference exists after compatibility and policy checks pass. */
    DRIFT,

    /** Only non-blocking structural differences exist and require human review. */
    REVIEW_REQUIRED,

    /** Candidate and approved structural multisets match. */
    MATCH
}
