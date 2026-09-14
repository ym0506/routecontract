package io.github.ym0506.routecontract;

import io.github.ym0506.routecontract.shardingsphere553.internal.RouteContract553SqlExecutionHook;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CurrentRouteContractCompatibilityTest {

    @Test
    void newAndCompatibilityResultEntriesKeepValueIdentityAndObservedAttempts() throws Exception {
        Object expectedValue = new Object();
        CapturedResult<Object> current = io.github.ym0506.routecontract.api.RouteContract.captureResult(
                "current-result", () -> {
                    reportAttempt();
                    return expectedValue;
                });
        CapturedResult<Object> compatibility = RouteContract.captureResult("compatibility-result", () -> {
            reportAttempt();
            return expectedValue;
        });

        assertSame(expectedValue, current.value());
        assertSame(expectedValue, compatibility.value());
        assertEquals(CaptureStatus.COMPLETE, current.snapshot().status());
        assertEquals(CaptureStatus.COMPLETE, compatibility.snapshot().status());
        assertEquals(1, current.snapshot().observedPhysicalAttemptCount());
        assertEquals(1, compatibility.snapshot().observedPhysicalAttemptCount());
        assertEquals(current.snapshot().runtimeIdentity(), compatibility.snapshot().runtimeIdentity());
    }

    @Test
    void checkedSupplierFailureKeepsIdentityAndCleansTheCaptureContext() throws Exception {
        Exception failure = new Exception("application-owned failure");
        assertSame(failure, assertThrows(Exception.class,
                () -> io.github.ym0506.routecontract.api.RouteContract.captureResult("failing-result", () -> {
                    reportAttempt();
                    throw failure;
                })));

        RouteSnapshot next = RouteContract.capture("after-failure", CurrentRouteContractCompatibilityTest::reportAttempt);
        assertEquals(CaptureStatus.COMPLETE, next.status());
        assertEquals(1, next.observedPhysicalAttemptCount());
    }

    @Test
    void supplierErrorKeepsIdentityAndCleansTheCaptureContext() throws Exception {
        AssertionError failure = new AssertionError("application-owned error");
        assertSame(failure, assertThrows(AssertionError.class,
                () -> io.github.ym0506.routecontract.api.RouteContract.captureResult("error-result", () -> {
                    reportAttempt();
                    throw failure;
                })));

        RouteSnapshot next = io.github.ym0506.routecontract.api.RouteContract.capture(
                "after-error", CurrentRouteContractCompatibilityTest::reportAttempt);
        assertEquals(CaptureStatus.COMPLETE, next.status());
        assertEquals(1, next.observedPhysicalAttemptCount());
    }

    @Test
    void fullStartupPreflightKeepsExactIdentityAndSubsequentCaptureUsable() throws Exception {
        assertEquals(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3,
                io.github.ym0506.routecontract.api.RouteContract.verifyRuntime());
        RouteSnapshot next = io.github.ym0506.routecontract.api.RouteContract.capture(
                "after-startup-preflight", CurrentRouteContractCompatibilityTest::reportAttempt);
        assertEquals(CaptureStatus.COMPLETE, next.status());
        assertEquals(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3, next.runtimeIdentity());
    }

    private static void reportAttempt() {
        RouteContract553SqlExecutionHook hook = new RouteContract553SqlExecutionHook();
        hook.start("ds_0", "SELECT 1", List.of(), null, true);
        hook.finishSuccess();
    }
}
