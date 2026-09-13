package io.github.ym0506.routecontract.internal;

import io.github.ym0506.routecontract.AttemptOutcome;
import io.github.ym0506.routecontract.PhysicalExecutionAttempt;
import io.github.ym0506.routecontract.ThreadRole;

import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

final class MutableAttempt {

    private static final Completion STARTED = new Completion(AttemptOutcome.START_REPORTED, null);
    private static final Completion RETURNED = new Completion(AttemptOutcome.CALLBACK_RETURNED, null);

    private final String observedDataSourceName;
    private final String sqlFingerprint;
    private final List<String> parameterTypes;
    private final ThreadRole threadRole;
    private final AtomicReference<Completion> completion = new AtomicReference<>(STARTED);

    MutableAttempt(
            final String observedDataSourceName,
            final String sqlFingerprint,
            final List<String> parameterTypes,
            final ThreadRole threadRole) {
        this.observedDataSourceName = observedDataSourceName;
        this.sqlFingerprint = sqlFingerprint;
        this.parameterTypes = List.copyOf(parameterTypes);
        this.threadRole = threadRole;
    }

    boolean finishCallbackReturned() {
        return completion.compareAndSet(STARTED, RETURNED);
    }

    boolean finishFailure(final Exception cause) {
        return completion.compareAndSet(STARTED, new Completion(
                AttemptOutcome.CALLBACK_FAILURE,
                cause == null ? null : cause.getClass().getName()));
    }

    PhysicalExecutionAttempt freeze() {
        Completion frozen = completion.get();
        return new PhysicalExecutionAttempt(
                observedDataSourceName,
                sqlFingerprint,
                parameterTypes.size(),
                parameterTypes,
                threadRole,
                frozen.outcome(),
                frozen.reportedFailureType());
    }

    private record Completion(AttemptOutcome outcome, String reportedFailureType) { }
}
