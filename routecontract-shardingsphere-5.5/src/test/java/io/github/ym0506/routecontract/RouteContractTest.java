package io.github.ym0506.routecontract;

import io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook;
import org.junit.jupiter.api.Test;

import java.util.AbstractList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RouteContractTest {

    @Test
    void capturesValueMinimizedCallbackReturnedAttempt() throws Exception {
        SensitiveParameter secret = new SensitiveParameter();

        RouteSnapshot snapshot = RouteContract.capture("privacy", () -> {
            RouteContractSqlExecutionHook hook = new RouteContractSqlExecutionHook();
            hook.start(
                    "ds_1",
                    "SELECT * FROM t_order_1 WHERE user_id = ? AND status = 'PRIVATE_LITERAL'",
                    List.of(secret),
                    null,
                    true);
            hook.finishSuccess();
        });

        assertEquals(CaptureStatus.COMPLETE, snapshot.status());
        assertEquals(1, snapshot.observedPhysicalAttemptCount());
        assertEquals(List.of("ds_1"), snapshot.observedDataSourceNames());
        PhysicalExecutionAttempt attempt = snapshot.attempts().get(0);
        assertTrue(attempt.sqlFingerprint().matches("[0-9a-f]{64}"));
        assertEquals(List.of(SensitiveParameter.class.getName()), attempt.parameterTypes());
        assertFalse(snapshot.toString().contains("PRIVATE_LITERAL"));
        assertFalse(snapshot.toString().contains("secret-value"));
        assertFalse(snapshot.toString().contains("SELECT"));
    }

    @Test
    void missingTerminalCallbackMakesCaptureIncomplete() throws Exception {
        RouteSnapshot snapshot = RouteContract.capture("incomplete", () -> {
            RouteContractSqlExecutionHook hook = new RouteContractSqlExecutionHook();
            hook.start("ds_0", "SELECT 1", List.of(), null, true);
        });

        assertEquals(CaptureStatus.INCOMPLETE, snapshot.status());
        assertEquals(1, snapshot.unknownOutcomeCount());
        assertThrows(RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(snapshot).hasCompleteCapture());
    }

    @Test
    void failureStoresOnlyExceptionType() throws Exception {
        RouteSnapshot snapshot = RouteContract.capture("failed", () -> {
            RouteContractSqlExecutionHook hook = new RouteContractSqlExecutionHook();
            hook.start("ds_0", "UPDATE t_order_0 SET status = ?", List.of("PAID"), null, false);
            hook.finishFailure(new IllegalStateException("do-not-store-this-message"));
        });

        assertEquals(CaptureStatus.REPORTED_EXECUTION_FAILURE, snapshot.status());
        assertEquals(1, snapshot.callbackFailureCount());
        assertEquals(IllegalStateException.class.getName(), snapshot.attempts().get(0).reportedFailureType());
        assertFalse(snapshot.toString().contains("do-not-store-this-message"));
        assertFalse(snapshot.toString().contains("PAID"));
        assertThrows(RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(snapshot).hasCompleteCapture());
        assertThrows(RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(snapshot).hasAtMostObservedPhysicalAttempts(1));
        RouteContractViolationException violation = assertThrows(
                RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(snapshot).hasNoReportedExecutionFailures());
        assertTrue(violation.getMessage().contains("observed 1"));
    }

    @Test
    void interruptedCallerAtCloseCannotProduceAContractEligibleCapture() throws Exception {
        RouteSnapshot snapshot;
        try {
            snapshot = RouteContract.capture("interrupted-close", () -> {
                callbackReturnedHook("ds_0", true);
                Thread.currentThread().interrupt();
            });
            assertTrue(Thread.currentThread().isInterrupted());
        } finally {
            Thread.interrupted();
        }

        assertEquals(CaptureStatus.INCOMPLETE, snapshot.status());
        assertEquals(List.of("RC_CALLER_INTERRUPTED_AT_CLOSE"), snapshot.collectorDiagnostics());
        assertThrows(RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(snapshot).hasExactlyObservedPhysicalAttempts(1));
    }

    @Test
    void attemptSafetyCeilingFailsClosedWithoutUnboundedRetention() throws Exception {
        RouteSnapshot snapshot = RouteContract.capture("attempt-ceiling", () -> {
            for (int index = 0; index < RouteContract.MAX_RETAINED_ATTEMPTS_PER_CAPTURE + 1; index++) {
                callbackReturnedHook("ds_0", true);
            }
        });

        assertEquals(CaptureStatus.INCOMPLETE, snapshot.status());
        assertEquals(RouteContract.MAX_RETAINED_ATTEMPTS_PER_CAPTURE,
                snapshot.observedPhysicalAttemptCount());
        assertEquals(List.of("RC_ATTEMPT_LIMIT_EXCEEDED"), snapshot.collectorDiagnostics());
        assertThrows(RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(snapshot).hasAtMostObservedPhysicalAttempts(
                        RouteContract.MAX_RETAINED_ATTEMPTS_PER_CAPTURE));
    }

    @Test
    void hookCollectorFailureIsContainedAndVisibleAsIncomplete() throws Exception {
        RouteSnapshot snapshot = RouteContract.capture("collector-failure", () -> {
            RouteContractSqlExecutionHook hook = new RouteContractSqlExecutionHook();
            hook.start("ds_0", "SELECT ?", new ExplodingList(), null, true);
            hook.finishSuccess();
        });

        assertEquals(CaptureStatus.INCOMPLETE, snapshot.status());
        assertEquals(0, snapshot.observedPhysicalAttemptCount());
        assertEquals(List.of("RC_COLLECTOR_START_FAILURE"), snapshot.collectorDiagnostics());
    }

    @Test
    void nullHookParametersCannotProduceACompleteCapture() throws Exception {
        RouteSnapshot snapshot = RouteContract.capture("null-parameters", () -> {
            RouteContractSqlExecutionHook hook = new RouteContractSqlExecutionHook();
            hook.start("ds_0", "SELECT 1", null, null, true);
            hook.finishSuccess();
        });

        assertEquals(CaptureStatus.INCOMPLETE, snapshot.status());
        assertEquals(1, snapshot.observedPhysicalAttemptCount());
        assertEquals(List.of("RC_NULL_PARAMETERS"), snapshot.collectorDiagnostics());
        assertThrows(RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(snapshot).hasExactlyObservedPhysicalAttempts(1));
    }

    @Test
    void everyPositiveAssertionFailsClosedForIncompleteCapture() throws Exception {
        RouteSnapshot incomplete = RouteContract.capture("incomplete-assertions", () -> { });

        assertThrows(RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(incomplete).hasAtMostObservedPhysicalAttempts(1));
        assertThrows(RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(incomplete).hasExactlyObservedPhysicalAttempts(0));
        assertThrows(RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(incomplete).hasAtMostDistinctObservedDataSourceNames(1));
        assertThrows(RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(incomplete).observesExactlyDataSourceNames());
        assertThrows(RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(incomplete).observesOnlyDataSourceNames("ds_0"));
        assertThrows(RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(incomplete).hasNoReportedExecutionFailures());
    }

    @Test
    void zeroProviderCallbacksCannotProduceCompleteZeroAttemptCapture() throws Exception {
        RouteSnapshot snapshot = RouteContract.capture("no-observed-callback", () -> { });

        assertEquals(CaptureStatus.INCOMPLETE, snapshot.status());
        assertEquals(0, snapshot.observedPhysicalAttemptCount());
        assertEquals(List.of("RC_NO_START_CALLBACK_OBSERVED"), snapshot.collectorDiagnostics());
    }

    @Test
    void orphanFinishIsContainedAndReported() throws Exception {
        RouteSnapshot snapshot = RouteContract.capture("orphan-finish", () ->
                new RouteContractSqlExecutionHook().finishSuccess());

        assertEquals(CaptureStatus.INCOMPLETE, snapshot.status());
        assertEquals(0, snapshot.observedPhysicalAttemptCount());
        assertEquals(
                List.of("RC_NO_START_CALLBACK_OBSERVED", "RC_ORPHAN_FINISH"),
                snapshot.collectorDiagnostics());
    }

    @Test
    void duplicateFinishIsContainedAndReportedWithoutCorruptingCounts() throws Exception {
        RouteSnapshot snapshot = RouteContract.capture("duplicate-finish", () -> {
            RouteContractSqlExecutionHook hook = new RouteContractSqlExecutionHook();
            hook.start("ds_0", "SELECT 1", List.of(), null, true);
            hook.finishSuccess();
            hook.finishFailure(new IllegalStateException("ignored"));
        });

        assertEquals(CaptureStatus.INCOMPLETE, snapshot.status());
        assertEquals(1, snapshot.observedPhysicalAttemptCount());
        assertEquals(1, snapshot.callbackReturnedCount());
        assertEquals(0, snapshot.callbackFailureCount());
        assertEquals(0, snapshot.unknownOutcomeCount());
        assertEquals(List.of("RC_DUPLICATE_FINISH"), snapshot.collectorDiagnostics());
    }

    @Test
    void snapshotRejectsDeclaredCountsThatDoNotMatchObservedAttempts() throws Exception {
        RouteSnapshot source = RouteContract.capture("integrity-counts", () ->
                callbackReturnedHook("ds_0", true));

        assertThrows(IllegalArgumentException.class, () -> new RouteSnapshot(
                source.schemaVersion(),
                source.operationId(),
                CaptureStatus.REPORTED_EXECUTION_FAILURE,
                source.observedPhysicalAttemptCount(),
                0,
                1,
                0,
                source.trunkThreadFlagCount(),
                source.workerThreadFlagCount(),
                source.observedDataSourceNames(),
                source.attempts(),
                source.collectorDiagnostics()));
    }

    @Test
    void snapshotRejectsStatusThatContradictsCollectorDiagnostics() throws Exception {
        RouteSnapshot source = RouteContract.capture("integrity-status", () -> { });

        assertThrows(IllegalArgumentException.class, () -> new RouteSnapshot(
                source.schemaVersion(),
                source.operationId(),
                CaptureStatus.COMPLETE,
                source.observedPhysicalAttemptCount(),
                source.callbackReturnedCount(),
                source.callbackFailureCount(),
                source.unknownOutcomeCount(),
                source.trunkThreadFlagCount(),
                source.workerThreadFlagCount(),
                source.observedDataSourceNames(),
                source.attempts(),
                        source.collectorDiagnostics()));
    }

    @Test
    void handAuthoredZeroAttemptSnapshotCannotForgeCompleteStatus() {
        assertThrows(IllegalArgumentException.class, () -> new RouteSnapshot(
                RouteSnapshot.CURRENT_SCHEMA_VERSION,
                "forged-zero",
                CaptureStatus.COMPLETE,
                0,
                0,
                0,
                0,
                0,
                0,
                List.of(),
                List.of(),
                List.of()));
    }

    @Test
    void handAuthoredSnapshotCannotExceedTheCaptureSafetyCeiling() {
        PhysicalExecutionAttempt attempt = new PhysicalExecutionAttempt(
                "ds_0",
                "a".repeat(64),
                0,
                List.of(),
                ThreadRole.TRUNK,
                AttemptOutcome.CALLBACK_RETURNED,
                null);
        int forgedCount = RouteContract.MAX_RETAINED_ATTEMPTS_PER_CAPTURE + 1;
        List<PhysicalExecutionAttempt> forgedAttempts = java.util.Collections.nCopies(forgedCount, attempt);

        assertThrows(IllegalArgumentException.class, () -> new RouteSnapshot(
                RouteSnapshot.CURRENT_SCHEMA_VERSION,
                "forged-over-limit",
                CaptureStatus.COMPLETE,
                forgedCount,
                forgedCount,
                0,
                0,
                forgedCount,
                0,
                List.of("ds_0"),
                forgedAttempts,
                List.of()));
    }

    @Test
    void nestedCaptureIsRejectedAndOuterCaptureRecovers() throws Exception {
        RouteSnapshot outer = RouteContract.capture("outer", () -> {
            IllegalStateException failure = assertThrows(
                    IllegalStateException.class,
                    () -> RouteContract.capture("inner", () -> { }));
            assertTrue(failure.getMessage().contains("Nested"));
            callbackReturnedHook("ds_0", true);
        });

        RouteAssertions.assertThat(outer)
                .hasExactlyObservedPhysicalAttempts(1)
                .observesExactlyDataSourceNames("ds_0")
                .hasCompleteCapture()
                .hasNoReportedExecutionFailures();
    }

    @Test
    void applicationExceptionIsNotMaskedAndContextIsCleaned() throws Exception {
        IllegalArgumentException original = new IllegalArgumentException("application-failure");
        IllegalArgumentException observed = assertThrows(IllegalArgumentException.class,
                () -> RouteContract.capture("throws", () -> {
                    callbackReturnedHook("ds_0", true);
                    throw original;
                }));
        assertSame(original, observed);

        RouteSnapshot next = RouteContract.capture("next", () -> callbackReturnedHook("ds_1", true));
        RouteAssertions.assertThat(next)
                .hasExactlyObservedPhysicalAttempts(1)
                .observesExactlyDataSourceNames("ds_1")
                .hasCompleteCapture()
                .hasNoReportedExecutionFailures();
    }

    @Test
    void assertionsExplainObservedDataSourceExpansion() throws Exception {
        RouteSnapshot snapshot = RouteContract.capture("fan-out", () -> {
            callbackReturnedHook("ds_1", true);
            callbackReturnedHook("ds_0", false);
        });

        RouteContractViolationException failure = assertThrows(
                RouteContractViolationException.class,
                () -> RouteAssertions.assertThat(snapshot).hasAtMostDistinctObservedDataSourceNames(1));
        assertTrue(failure.getMessage().contains("[ds_0, ds_1]"));
    }

    private static void callbackReturnedHook(final String dataSourceName, final boolean trunk) {
        RouteContractSqlExecutionHook hook = new RouteContractSqlExecutionHook();
        hook.start(dataSourceName, "SELECT * FROM t_order WHERE user_id = ?", List.of(3L), null, trunk);
        hook.finishSuccess();
    }

    private static final class SensitiveParameter {
        @Override
        public String toString() {
            return "secret-value";
        }
    }

    private static final class ExplodingList extends AbstractList<Object> {
        @Override
        public Object get(final int index) {
            throw new IllegalStateException("injected-get-failure");
        }

        @Override
        public int size() {
            throw new IllegalStateException("injected-size-failure");
        }
    }
}
