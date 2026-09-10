package io.github.ym0506.routecontract;

import java.util.Arrays;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

/** Fluent assertions for observed physical-execution snapshots. */
public final class RouteAssertions {

    private final RouteSnapshot snapshot;

    private RouteAssertions(final RouteSnapshot snapshot) {
        this.snapshot = Objects.requireNonNull(snapshot, "snapshot");
    }

    /**
     * Starts a fluent assertion chain for a snapshot.
     *
     * @param snapshot completed operation snapshot to check
     * @return assertion chain bound to {@code snapshot}
     */
    public static RouteAssertions assertThat(final RouteSnapshot snapshot) {
        return new RouteAssertions(snapshot);
    }

    /**
     * Requires no more than the given number of observed physical JDBC execution attempts.
     *
     * @param maximum inclusive non-negative attempt budget
     * @return this assertion object
     * @throws RouteContractViolationException when the capture is not contract-eligible or exceeds the budget
     */
    public RouteAssertions hasAtMostObservedPhysicalAttempts(final int maximum) {
        requireCompleteCapture();
        requireNonNegative(maximum, "maximum");
        if (snapshot.observedPhysicalAttemptCount() > maximum) {
            fail("expected at most " + maximum + " observed physical attempts, but observed "
                    + snapshot.observedPhysicalAttemptCount());
        }
        return this;
    }

    /**
     * Requires exactly the given number of observed physical JDBC execution attempts.
     *
     * @param expected non-negative expected attempt count
     * @return this assertion object
     * @throws RouteContractViolationException when the capture is not contract-eligible or the count differs
     */
    public RouteAssertions hasExactlyObservedPhysicalAttempts(final int expected) {
        requireCompleteCapture();
        requireNonNegative(expected, "expected");
        if (snapshot.observedPhysicalAttemptCount() != expected) {
            fail("expected exactly " + expected + " observed physical attempts, but observed "
                    + snapshot.observedPhysicalAttemptCount());
        }
        return this;
    }

    /**
     * Requires no more than the given number of distinct callback-reported data-source names.
     *
     * @param maximum inclusive non-negative distinct-name budget
     * @return this assertion object
     * @throws RouteContractViolationException when the capture is not contract-eligible or exceeds the budget
     */
    public RouteAssertions hasAtMostDistinctObservedDataSourceNames(final int maximum) {
        requireCompleteCapture();
        requireNonNegative(maximum, "maximum");
        if (snapshot.observedDataSourceNames().size() > maximum) {
            fail("expected at most " + maximum + " observed data-source names, but observed "
                    + snapshot.observedDataSourceNames());
        }
        return this;
    }

    /**
     * Requires the set of observed data-source names to equal the supplied set.
     *
     * @param expected expected callback-reported names; order and duplicates are ignored
     * @return this assertion object
     * @throws RouteContractViolationException when the capture is not contract-eligible or the sets differ
     */
    public RouteAssertions observesExactlyDataSourceNames(final String... expected) {
        requireCompleteCapture();
        Set<String> expectedSet = new TreeSet<>(Arrays.asList(expected));
        Set<String> actualSet = new TreeSet<>(snapshot.observedDataSourceNames());
        if (!actualSet.equals(expectedSet)) {
            fail("expected observed data-source names " + expectedSet + ", but observed " + actualSet);
        }
        return this;
    }

    /**
     * Requires every observed data-source name to belong to the supplied allow-list.
     *
     * @param allowed allowed callback-reported names; observing none of them is permitted
     * @return this assertion object
     * @throws RouteContractViolationException when the capture is not contract-eligible or an unexpected name appears
     */
    public RouteAssertions observesOnlyDataSourceNames(final String... allowed) {
        requireCompleteCapture();
        Set<String> allowedSet = new TreeSet<>(Arrays.asList(allowed));
        Set<String> unexpected = new TreeSet<>(snapshot.observedDataSourceNames());
        unexpected.removeAll(allowedSet);
        if (!unexpected.isEmpty()) {
            fail("expected only data-source names " + allowedSet + ", but also observed " + unexpected);
        }
        return this;
    }

    /**
     * Requires a normally returned, non-interrupted capture with only callback-returned attempts.
     * Failure snapshots are diagnostic-only because ShardingSphere 5.5.3 can return from a failed
     * parallel execution before every submitted worker has joined.
     *
     * @return this assertion object
     * @throws RouteContractViolationException when the capture is not contract-eligible
     */
    public RouteAssertions hasCompleteCapture() {
        requireCompleteCapture();
        return this;
    }

    /**
     * Requires every observed attempt to have a {@code finishSuccess} report after the wrapped
     * physical {@code executeSQL} call returned.
     *
     * <p>This report does not establish completion of the enclosing JDBC operation or application
     * action, transaction commit, or business success.</p>
     *
     * @return this assertion object
     * @throws RouteContractViolationException when bookkeeping is incomplete or a callback reported failure
     */
    public RouteAssertions hasNoReportedExecutionFailures() {
        requireCollectorBookkeeping();
        if (snapshot.callbackFailureCount() != 0) {
            fail("expected no callback-reported execution failures, but observed "
                    + snapshot.callbackFailureCount());
        }
        return this;
    }

    private void requireCompleteCapture() {
        if (snapshot.status() != CaptureStatus.COMPLETE || snapshot.callbackFailureCount() != 0
                || snapshot.unknownOutcomeCount() != 0
                || !snapshot.collectorDiagnostics().isEmpty()) {
            fail("expected a contract-eligible COMPLETE capture, but status was " + snapshot.status()
                    + ", callbackFailures=" + snapshot.callbackFailureCount()
                    + ", unknownOutcomes=" + snapshot.unknownOutcomeCount()
                    + ", collectorDiagnostics=" + snapshot.collectorDiagnostics());
        }
    }

    private void requireCollectorBookkeeping() {
        if (snapshot.status() == CaptureStatus.INCOMPLETE || snapshot.unknownOutcomeCount() != 0
                || !snapshot.collectorDiagnostics().isEmpty()) {
            fail("expected complete observed callback bookkeeping, but status was " + snapshot.status()
                    + ", unknownOutcomes=" + snapshot.unknownOutcomeCount()
                    + ", collectorDiagnostics=" + snapshot.collectorDiagnostics());
        }
    }

    private static void requireNonNegative(final int value, final String label) {
        if (value < 0) {
            throw new IllegalArgumentException(label + " must be non-negative");
        }
    }

    private void fail(final String reason) {
        throw new RouteContractViolationException("Route contract violation for operation '"
                + snapshot.operationId() + "': " + reason);
    }
}
