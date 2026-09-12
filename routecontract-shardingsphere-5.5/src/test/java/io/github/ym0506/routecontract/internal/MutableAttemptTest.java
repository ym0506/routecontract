package io.github.ym0506.routecontract.internal;

import io.github.ym0506.routecontract.AttemptOutcome;
import io.github.ym0506.routecontract.PhysicalExecutionAttempt;
import io.github.ym0506.routecontract.ThreadRole;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MutableAttemptTest {

    private static final int RACE_ITERATIONS = 1_000_000;
    private static final String FINGERPRINT = "a".repeat(64);

    @Test
    void firstTerminalCallbackWinsWithoutChangingEarlierSnapshots() {
        MutableAttempt failed = attempt();
        PhysicalExecutionAttempt beforeFailure = failed.freeze();
        assertTrue(failed.finishFailure(new IllegalStateException("not retained")));
        PhysicalExecutionAttempt afterFailure = failed.freeze();
        assertFalse(failed.finishCallbackReturned());
        assertFalse(failed.finishFailure(new IllegalArgumentException()));
        assertEquals(AttemptOutcome.START_REPORTED, beforeFailure.outcome());
        assertNull(beforeFailure.reportedFailureType());
        assertEquals(AttemptOutcome.CALLBACK_FAILURE, afterFailure.outcome());
        assertEquals(IllegalStateException.class.getName(), afterFailure.reportedFailureType());
        assertEquals(afterFailure, failed.freeze());

        MutableAttempt returned = attempt();
        assertTrue(returned.finishCallbackReturned());
        PhysicalExecutionAttempt afterReturn = returned.freeze();
        assertFalse(returned.finishFailure(new IllegalStateException()));
        assertEquals(AttemptOutcome.CALLBACK_RETURNED, afterReturn.outcome());
        assertNull(afterReturn.reportedFailureType());
        assertEquals(afterReturn, returned.freeze());
    }

    @Test
    @Timeout(30)
    void concurrentFailureAndFreezeAlwaysProduceAConsistentDiagnostic() throws InterruptedException {
        RaceState race = new RaceState();
        AtomicReference<Throwable> writerFailure = new AtomicReference<>();
        Thread writer = new Thread(() -> {
            int seen = 0;
            IllegalStateException cause = new IllegalStateException("not retained");
            try {
                while (race.running) {
                    int requested = race.requested;
                    if (requested != seen) {
                        assertTrue(race.attempt.finishFailure(cause));
                        race.completed = requested;
                        seen = requested;
                    } else {
                        Thread.onSpinWait();
                    }
                }
            } catch (Throwable failure) {
                writerFailure.set(failure);
            }
        }, "routecontract-failure-freeze-test");
        writer.setDaemon(true);
        writer.start();
        try {
            for (int iteration = 1; iteration <= RACE_ITERATIONS; iteration++) {
                race.attempt = attempt();
                race.requested = iteration;
                assertConsistent(race.attempt.freeze());
                while (race.completed != iteration) {
                    assertNull(writerFailure.get(), "failure writer must complete each callback");
                    if (Thread.currentThread().isInterrupted()) {
                        throw new InterruptedException("failure/freeze race timed out");
                    }
                    Thread.onSpinWait();
                }
                PhysicalExecutionAttempt completed = race.attempt.freeze();
                assertEquals(AttemptOutcome.CALLBACK_FAILURE, completed.outcome());
                assertConsistent(completed);
            }
        } finally {
            race.running = false;
            writer.join(5_000);
        }
        assertFalse(writer.isAlive(), "failure writer must stop");
        assertNull(writerFailure.get(), "failure writer must not throw");
    }

    private static void assertConsistent(final PhysicalExecutionAttempt frozen) {
        if (frozen.outcome() == AttemptOutcome.START_REPORTED) {
            assertNull(frozen.reportedFailureType());
        } else {
            assertEquals(AttemptOutcome.CALLBACK_FAILURE, frozen.outcome());
            assertEquals(IllegalStateException.class.getName(), frozen.reportedFailureType());
        }
    }

    private static MutableAttempt attempt() {
        return new MutableAttempt("ds_0", FINGERPRINT, List.of(), ThreadRole.WORKER);
    }

    private static final class RaceState {
        private MutableAttempt attempt;
        private volatile int requested;
        private volatile int completed;
        private volatile boolean running = true;
    }
}
