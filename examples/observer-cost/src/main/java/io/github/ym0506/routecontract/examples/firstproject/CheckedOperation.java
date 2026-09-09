package io.github.ym0506.routecontract.examples.firstproject;

import io.github.ym0506.routecontract.RouteAssertions;
import io.github.ym0506.routecontract.RouteContract;

/** The additional work measured by checked versus idle; no reporting or baseline approval. */
public final class CheckedOperation implements ObserverCostBenchmark.CheckedOperationFactory {
    @Override
    public ObserverCostBenchmark.Operation wrap(
            ObserverCostBenchmark.Operation operation, int expectedAttempts) {
        return () -> {
            var captured = RouteContract.captureResult("observer-cost.orders", operation::run);
            RouteAssertions.assertThat(captured.snapshot())
                    .hasCompleteCapture()
                    .hasNoReportedExecutionFailures()
                    .hasExactlyObservedPhysicalAttempts(expectedAttempts);
            return captured;
        };
    }
}
