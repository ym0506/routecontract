package io.github.ym0506.routecontract;

import java.util.Objects;
import java.util.regex.Pattern;

/**
 * Immutable identity of the ShardingSphere callback contract observed by a capture.
 *
 * <p>The component versions are the implementation versions reported by the exact executor and
 * SPI packages checked by RouteContract. They do not claim that every artifact in an application
 * dependency graph has the same version.</p>
 *
 * @param adapterId stable identifier for the callback adapter semantics
 * @param adapterContractVersion positive revision of those semantics
 * @param infraExecutorImplementationVersion observed executor package implementation version
 * @param infraSpiImplementationVersion observed SPI package implementation version
 */
public record ShardingSphereRuntimeIdentity(
        String adapterId,
        int adapterContractVersion,
        String infraExecutorImplementationVersion,
        String infraSpiImplementationVersion) {

    private static final Pattern ADAPTER_ID_PATTERN = Pattern.compile("[a-z0-9][a-z0-9./-]{0,127}");
    private static final Pattern IMPLEMENTATION_VERSION_PATTERN =
            Pattern.compile("[0-9][0-9A-Za-z.+-]{0,99}");

    /** Stable adapter identifier used by the SQL execution-hook integration. */
    public static final String SQL_EXECUTION_HOOK_ADAPTER_ID =
            "apache-shardingsphere-jdbc/sql-execution-hook";

    /** Current semantic contract revision for captured SQL execution-hook evidence. */
    public static final int CURRENT_ADAPTER_CONTRACT_VERSION = 1;

    /** Exact identity of the supported ShardingSphere 5.5.2 adapter contract. */
    public static final ShardingSphereRuntimeIdentity SHARDINGSPHERE_5_5_2 = forVersion("5.5.2");

    /** Exact identity of the supported ShardingSphere 5.5.3 adapter contract. */
    public static final ShardingSphereRuntimeIdentity SHARDINGSPHERE_5_5_3 = forVersion("5.5.3");

    /**
     * Validates and freezes an identity without silently normalizing any field.
     *
     * @param adapterId stable identifier for the callback adapter semantics
     * @param adapterContractVersion positive revision of those semantics
     * @param infraExecutorImplementationVersion observed executor implementation version
     * @param infraSpiImplementationVersion observed SPI implementation version
     */
    public ShardingSphereRuntimeIdentity {
        adapterId = requireAdapterId(adapterId);
        if (adapterContractVersion <= 0) {
            throw new IllegalArgumentException("adapterContractVersion must be positive");
        }
        infraExecutorImplementationVersion = requireImplementationVersion(
                infraExecutorImplementationVersion, "infraExecutorImplementationVersion");
        infraSpiImplementationVersion = requireImplementationVersion(
                infraSpiImplementationVersion, "infraSpiImplementationVersion");
    }

    /**
     * Returns whether this is one of the exact runtime identities this code understands.
     *
     * @return {@code true} only for exact 5.5.2 or 5.5.3 executor/SPI pairs and contract revision
     */
    public boolean isSupported() {
        return equals(SHARDINGSPHERE_5_5_2) || equals(SHARDINGSPHERE_5_5_3);
    }

    private static ShardingSphereRuntimeIdentity forVersion(final String version) {
        return new ShardingSphereRuntimeIdentity(
                SQL_EXECUTION_HOOK_ADAPTER_ID,
                CURRENT_ADAPTER_CONTRACT_VERSION,
                version,
                version);
    }

    private static String requireAdapterId(final String value) {
        Objects.requireNonNull(value, "adapterId");
        if (!ADAPTER_ID_PATTERN.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "adapterId must be 1-128 lowercase ASCII identifier characters");
        }
        return value;
    }

    private static String requireImplementationVersion(final String value, final String label) {
        Objects.requireNonNull(value, label);
        if (!IMPLEMENTATION_VERSION_PATTERN.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    label + " must be a 1-100 character ASCII implementation version");
        }
        return value;
    }
}
