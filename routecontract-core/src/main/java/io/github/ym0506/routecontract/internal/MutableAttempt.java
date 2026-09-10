package io.github.ym0506.routecontract.internal;

import io.github.ym0506.routecontract.AttemptOutcome;
import io.github.ym0506.routecontract.PhysicalExecutionAttempt;
import io.github.ym0506.routecontract.ThreadRole;

import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

final class MutableAttempt {

    private final String observedDataSourceName;
    private final String sqlFingerprint;
    private final List<String> parameterTypes;
    private final ThreadRole threadRole;
    private final AtomicReference<AttemptOutcome> outcome = new AtomicReference<>(AttemptOutcome.START_REPORTED);
    private volatile String reportedFailureType;

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
        return outcome.compareAndSet(AttemptOutcome.START_REPORTED, AttemptOutcome.CALLBACK_RETURNED);
    }

    boolean finishFailure(final Exception cause) {
        if (!outcome.compareAndSet(AttemptOutcome.START_REPORTED, AttemptOutcome.CALLBACK_FAILURE)) {
            return false;
        }
        reportedFailureType = cause == null ? null : cause.getClass().getName();
        return true;
    }

    PhysicalExecutionAttempt freeze() {
        return new PhysicalExecutionAttempt(
                observedDataSourceName,
                sqlFingerprint,
                parameterTypes.size(),
                parameterTypes,
                threadRole,
                outcome.get(),
                reportedFailureType);
    }
}
