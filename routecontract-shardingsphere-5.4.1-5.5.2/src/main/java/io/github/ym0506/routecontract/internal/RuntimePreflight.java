package io.github.ym0506.routecontract.internal;

/**
 * Artifact-specific entry point for the fail-closed runtime check.
 *
 * <p>Shared capture code calls this class. Each RouteContract artifact supplies its own copy
 * that delegates to the preflight for the exact ShardingSphere versions it supports.</p>
 */
final class RuntimePreflight {

    private RuntimePreflight() {
    }

    static void verify() {
        ShardingSphere541To552Preflight.verify();
    }
}
