package io.github.ym0506.routecontract.manifest;

import java.util.Objects;

/**
 * One deterministic, machine-coded verification finding with explicit enforcement severity.
 *
 * @param code stable kind of finding
 * @param severity enforcement behavior associated with the finding
 * @param detail deterministic human-readable comparison detail
 */
public record ManifestDiff(ManifestDiffCode code, ManifestDiffSeverity severity, String detail) {

    /**
     * Creates a fully classified verification finding.
     *
     * @param code stable finding kind
     * @param severity explicit enforcement severity
     * @param detail deterministic human-readable comparison detail
     */
    public ManifestDiff {
        code = Objects.requireNonNull(code, "code");
        severity = Objects.requireNonNull(severity, "severity");
        detail = Objects.requireNonNull(detail, "detail");
    }
}
