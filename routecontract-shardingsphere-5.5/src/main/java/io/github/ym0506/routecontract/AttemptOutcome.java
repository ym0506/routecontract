package io.github.ym0506.routecontract;

/** Callback state reported for one observed physical JDBC execution attempt. */
public enum AttemptOutcome {
    /** A start callback was observed, but no matching finish callback was recorded. */
    START_REPORTED,

    /**
     * ShardingSphere reported {@code finishSuccess} to the hook provider after its wrapped
     * physical {@code executeSQL} call returned.
     *
     * <p>This does not establish completion of the enclosing JDBC operation or application action,
     * transaction commit, or application-level success.</p>
     */
    CALLBACK_RETURNED,

    /** The ShardingSphere execution callback reported an {@link Exception}. */
    CALLBACK_FAILURE
}
