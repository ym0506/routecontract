package io.github.ym0506.routecontract;

/** Completeness classification for an operation capture. */
public enum CaptureStatus {
    /** Every observed start callback has a matching normal-return callback and no collector diagnostic exists. */
    COMPLETE,

    /**
     * At least one observed callback reported an execution failure. This snapshot is diagnostic
     * only: ShardingSphere 5.5.3 may leave other submitted workers unjoined on a failure path.
     */
    REPORTED_EXECUTION_FAILURE,

    /** At least one callback outcome is unknown or the collector recorded a diagnostic. */
    INCOMPLETE
}
