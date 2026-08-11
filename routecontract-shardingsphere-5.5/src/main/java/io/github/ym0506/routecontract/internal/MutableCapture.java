package io.github.ym0506.routecontract.internal;

import io.github.ym0506.routecontract.AttemptOutcome;
import io.github.ym0506.routecontract.CaptureStatus;
import io.github.ym0506.routecontract.PhysicalExecutionAttempt;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.ThreadRole;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

final class MutableCapture {

    private static final Comparator<PhysicalExecutionAttempt> ATTEMPT_ORDER = Comparator
            .comparing(PhysicalExecutionAttempt::observedDataSourceName)
            .thenComparing(PhysicalExecutionAttempt::sqlFingerprint)
            .thenComparingInt(PhysicalExecutionAttempt::parameterCount)
            .thenComparing(attempt -> String.join("\u0000", attempt.parameterTypes()))
            .thenComparing(PhysicalExecutionAttempt::threadRole)
            .thenComparing(PhysicalExecutionAttempt::outcome)
            .thenComparing(PhysicalExecutionAttempt::reportedFailureType, Comparator.nullsFirst(String::compareTo));

    private final String operationId;
    private final ConcurrentLinkedQueue<MutableAttempt> attempts = new ConcurrentLinkedQueue<>();
    private final ConcurrentLinkedQueue<String> collectorDiagnostics = new ConcurrentLinkedQueue<>();
    private final AtomicBoolean startCallbackObserved = new AtomicBoolean();
    private final AtomicBoolean attemptLimitDiagnosticRecorded = new AtomicBoolean();
    private final AtomicBoolean closed = new AtomicBoolean();
    private final AtomicInteger retainedAttemptCount = new AtomicInteger();

    MutableCapture(final String operationId) {
        this.operationId = operationId;
    }

    void recordStartCallbackObserved() {
        startCallbackObserved.set(true);
    }

    AttemptHandle start(
            final String observedDataSourceName,
            final String sqlFingerprint,
            final List<String> parameterTypes,
            final ThreadRole threadRole) {
        if (closed.get()) {
            recordError("RC_LATE_START");
            return AttemptHandle.noop();
        }
        int attemptNumber = retainedAttemptCount.incrementAndGet();
        if (attemptNumber > RouteContract.MAX_RETAINED_ATTEMPTS_PER_CAPTURE) {
            if (attemptLimitDiagnosticRecorded.compareAndSet(false, true)) {
                recordError("RC_ATTEMPT_LIMIT_EXCEEDED");
            }
            return AttemptHandle.noop();
        }
        MutableAttempt attempt = new MutableAttempt(
                observedDataSourceName, sqlFingerprint, parameterTypes, threadRole);
        attempts.add(attempt);
        return new AttemptHandle(this, attempt);
    }

    void finishCallbackReturned(final MutableAttempt attempt) {
        if (!attempt.finishCallbackReturned()) {
            recordError("RC_DUPLICATE_FINISH");
        }
    }

    void finishFailure(final MutableAttempt attempt, final Exception cause) {
        if (cause == null) {
            recordError("RC_NULL_FAILURE_CAUSE");
        }
        if (!attempt.finishFailure(cause)) {
            recordError("RC_DUPLICATE_FINISH");
        }
    }

    void recordError(final String errorCode) {
        collectorDiagnostics.add(errorCode);
    }

    RouteSnapshot closeAndFreeze() {
        if (!closed.compareAndSet(false, true)) {
            recordError("RC_DUPLICATE_CLOSE");
        }
        if (!startCallbackObserved.get()) {
            recordError("RC_NO_START_CALLBACK_OBSERVED");
        }
        if (Thread.currentThread().isInterrupted()) {
            recordError("RC_CALLER_INTERRUPTED_AT_CLOSE");
        }

        List<PhysicalExecutionAttempt> frozenAttempts = new ArrayList<>();
        for (MutableAttempt attempt : attempts) {
            frozenAttempts.add(attempt.freeze());
        }
        frozenAttempts.sort(ATTEMPT_ORDER);

        int callbackReturned = count(frozenAttempts, AttemptOutcome.CALLBACK_RETURNED);
        int callbackFailure = count(frozenAttempts, AttemptOutcome.CALLBACK_FAILURE);
        int unknownOutcome = count(frozenAttempts, AttemptOutcome.START_REPORTED);
        int trunk = count(frozenAttempts, ThreadRole.TRUNK);
        int worker = count(frozenAttempts, ThreadRole.WORKER);

        Set<String> observedDataSourceNames = new TreeSet<>();
        for (PhysicalExecutionAttempt attempt : frozenAttempts) {
            observedDataSourceNames.add(attempt.observedDataSourceName());
        }

        List<String> diagnostics = new ArrayList<>(collectorDiagnostics);
        diagnostics.sort(String::compareTo);
        CaptureStatus status = !diagnostics.isEmpty() || unknownOutcome > 0
                ? CaptureStatus.INCOMPLETE
                : callbackFailure > 0 ? CaptureStatus.REPORTED_EXECUTION_FAILURE : CaptureStatus.COMPLETE;

        return new RouteSnapshot(
                RouteSnapshot.CURRENT_SCHEMA_VERSION,
                operationId,
                status,
                frozenAttempts.size(),
                callbackReturned,
                callbackFailure,
                unknownOutcome,
                trunk,
                worker,
                List.copyOf(observedDataSourceNames),
                frozenAttempts,
                diagnostics);
    }

    private static int count(
            final List<PhysicalExecutionAttempt> attempts,
            final AttemptOutcome expectedOutcome) {
        return (int) attempts.stream().filter(attempt -> attempt.outcome() == expectedOutcome).count();
    }

    private static int count(
            final List<PhysicalExecutionAttempt> attempts,
            final ThreadRole expectedRole) {
        return (int) attempts.stream().filter(attempt -> attempt.threadRole() == expectedRole).count();
    }
}
