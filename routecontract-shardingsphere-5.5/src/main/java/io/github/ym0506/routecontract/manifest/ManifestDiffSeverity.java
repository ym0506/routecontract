package io.github.ym0506.routecontract.manifest;

/** Whether a finding blocks verification, needs human review, or is informational. */
public enum ManifestDiffSeverity {
    /** The finding fails both exact-match and blocking-check assertions. */
    BLOCKING,

    /** The finding permits blocking checks to pass but requires explicit human review. */
    REVIEW,

    /** The finding is informational and does not represent a mismatch. */
    INFO
}
