package io.github.ym0506.routecontract;

/** Role reported by ShardingSphere for a physical execution callback. */
public enum ThreadRole {
    /** ShardingSphere marked the callback as executing on its trunk thread. */
    TRUNK,

    /** ShardingSphere marked the callback as executing on a worker thread. */
    WORKER
}
