package io.github.ym0506.routecontract.manifest;

/** Stable machine-readable codes for manifest verification output. */
public enum ManifestDiffCode {
    /** Approved and candidate manifests match. */
    MATCH("RCM000"),

    /** At least one manifest uses an unsupported schema version. */
    UNSUPPORTED_SCHEMA("RCM001"),

    /** The approved and candidate operation identifiers differ. */
    OPERATION_ID_MISMATCH("RCM002"),

    /** The approved manifest is not eligible to serve as an enforceable contract. */
    APPROVED_MANIFEST_NOT_ELIGIBLE("RCM003"),

    /** At least one runtime identity is outside the exact supported adapter/runtime set. */
    UNSUPPORTED_RUNTIME_IDENTITY("RCM004"),

    /** Approved and candidate runtime identities are supported but differ. */
    RUNTIME_IDENTITY_MISMATCH("RCM005"),

    /** Collector diagnostics or an unknown callback outcome make the capture incomplete. */
    CAPTURE_INCOMPLETE("RCM100"),

    /** A callback-reported execution failure makes the capture diagnostic-only. */
    CALLBACK_FAILURE_NOT_ELIGIBLE("RCM101"),

    /** The candidate exceeds the maximum observed physical-attempt budget. */
    ATTEMPT_BUDGET_EXCEEDED("RCM201"),

    /** The candidate exceeds the maximum distinct data-source-alias budget. */
    DATA_SOURCE_BUDGET_EXCEEDED("RCM202"),

    /** Candidate policy differs from the approved policy. */
    POLICY_CHANGED("RCM300"),

    /** A structural attempt present in the approved multiset is absent or less frequent. */
    STRUCTURAL_ATTEMPT_REMOVED("RCM301"),

    /** A structural attempt is new or more frequent in the candidate multiset. */
    STRUCTURAL_ATTEMPT_ADDED("RCM302"),

    /** Total observed physical-attempt count changed. */
    OBSERVED_ATTEMPT_COUNT_CHANGED("RCM303"),

    /** Set of observed stable data-source aliases changed. */
    OBSERVED_DATA_SOURCE_SET_CHANGED("RCM304"),

    /** Callback outcome counts changed. */
    OUTCOME_COUNTS_CHANGED("RCM305");

    private final String stableCode;

    ManifestDiffCode(final String stableCode) {
        this.stableCode = stableCode;
    }

    /**
     * Returns the stable external identifier for this finding kind.
     *
     * @return an {@code RCMnnn} code suitable for CI output and automation
     */
    public String stableCode() {
        return stableCode;
    }
}
