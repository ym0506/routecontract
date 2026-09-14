package io.github.ym0506.routecontract.manifest;

import io.github.ym0506.routecontract.AttemptOutcome;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;

/**
 * One canonical structural entry in an observed-execution manifest.
 *
 * <p>Entries with an identical structural signature are represented once with a positive
 * multiplicity. Neither raw SQL nor parameter values are retained.</p>
 *
 * @param observedDataSourceAlias stable reviewed alias, not the environment-specific observed name
 * @param sqlFingerprint lowercase SHA-256 digest of the exact callback SQL encoded as UTF-8
 * @param parameterCount number of callback parameters
 * @param parameterTypes ordered Java runtime type names, using {@code "null"} for a null value
 * @param outcome last callback state observed for the represented attempts
 * @param multiplicity positive number of attempts with this structural signature
 */
public record ManifestAttempt(
        String observedDataSourceAlias,
        String sqlFingerprint,
        int parameterCount,
        List<String> parameterTypes,
        AttemptOutcome outcome,
        int multiplicity) {

    /** Stable ordering used by both JSON output and structural manifest/attempt diff output. */
    public static final Comparator<ManifestAttempt> CANONICAL_ORDER = Comparator
            .comparing(ManifestAttempt::observedDataSourceAlias)
            .thenComparing(ManifestAttempt::sqlFingerprint)
            .thenComparingInt(ManifestAttempt::parameterCount)
            .thenComparing(ManifestAttempt::parameterTypes, ManifestAttempt::compareParameterTypes)
            .thenComparing(attempt -> attempt.outcome().name());

    /**
     * Creates a validated canonical structural entry.
     *
     * @param observedDataSourceAlias non-blank stable reviewed alias
     * @param sqlFingerprint lowercase SHA-256 digest of the exact callback SQL encoded as UTF-8
     * @param parameterCount non-negative number of callback parameters
     * @param parameterTypes ordered, non-blank Java runtime type names
     * @param outcome last callback state represented by this entry
     * @param multiplicity positive number of structurally identical attempts
     */
    public ManifestAttempt {
        observedDataSourceAlias = requireNonBlank(observedDataSourceAlias, "observedDataSourceAlias");
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
            requireNonBlank(parameterType, "parameterType");
        }
        outcome = Objects.requireNonNull(outcome, "outcome");
        if (multiplicity <= 0) {
            throw new IllegalArgumentException("multiplicity must be positive");
        }
    }

    ManifestAttempt withMultiplicity(final int newMultiplicity) {
        return new ManifestAttempt(
                observedDataSourceAlias,
                sqlFingerprint,
                parameterCount,
                parameterTypes,
                outcome,
                newMultiplicity);
    }

    String structuralDescription() {
        return "alias=" + observedDataSourceAlias
                + ", fingerprint=" + sqlFingerprint
                + ", parameterCount=" + parameterCount
                + ", parameterTypes=" + parameterTypes
                + ", outcome=" + outcome;
    }

    private static String requireNonBlank(final String value, final String label) {
        Objects.requireNonNull(value, label);
        if (value.isBlank()) {
            throw new IllegalArgumentException(label + " must not be blank");
        }
        return value;
    }

    private static int compareParameterTypes(final List<String> left, final List<String> right) {
        int sharedSize = Math.min(left.size(), right.size());
        for (int index = 0; index < sharedSize; index++) {
            int comparison = left.get(index).compareTo(right.get(index));
            if (comparison != 0) {
                return comparison;
            }
        }
        return Integer.compare(left.size(), right.size());
    }
}
