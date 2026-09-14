package io.github.ym0506.routecontract.shardingsphere552.internal;

import io.github.ym0506.routecontract.CaptureStatus;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import org.junit.jupiter.api.Test;

import java.util.AbstractList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RouteContract552HookContainmentTest {

    @Test
    void capturesAValueMinimizedAttemptWithTheExact552RuntimeIdentity() throws Exception {
        SensitiveParameter secret = new SensitiveParameter();

        RouteSnapshot snapshot = RouteContract.capture("privacy-552", () -> {
            RouteContract552SqlExecutionHook hook = new RouteContract552SqlExecutionHook();
            hook.start(
                    "ds_1",
                    "SELECT * FROM t_order_1 WHERE user_id = ? AND status = 'PRIVATE_LITERAL'",
                    List.of(secret),
                    null,
                    true);
            hook.finishSuccess();
        });

        assertEquals(CaptureStatus.COMPLETE, snapshot.status());
        assertEquals(2, snapshot.schemaVersion());
        assertEquals(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_2, snapshot.runtimeIdentity());
        assertEquals(1, snapshot.observedPhysicalAttemptCount());
        assertEquals(List.of(SensitiveParameter.class.getName()), snapshot.attempts().get(0).parameterTypes());
        assertTrue(snapshot.attempts().get(0).sqlFingerprint().matches("[0-9a-f]{64}"));
        assertFalse(snapshot.toString().contains("PRIVATE_LITERAL"));
        assertFalse(snapshot.toString().contains("secret-value"));
        assertFalse(snapshot.toString().contains("SELECT"));
    }

    @Test
    void collectorFailureIsContainedAndMakesTheCaptureIncomplete() throws Exception {
        RouteSnapshot snapshot = RouteContract.capture("collector-failure-552", () -> {
            RouteContract552SqlExecutionHook hook = new RouteContract552SqlExecutionHook();
            hook.start("ds_0", "SELECT ?", new ExplodingList(), null, true);
            hook.finishSuccess();
        });

        assertEquals(CaptureStatus.INCOMPLETE, snapshot.status());
        assertEquals(0, snapshot.observedPhysicalAttemptCount());
        assertEquals(List.of("RC_COLLECTOR_START_FAILURE"), snapshot.collectorDiagnostics());
    }

    @Test
    void duplicateFinishIsContainedWithoutCorruptingAttemptCounts() throws Exception {
        RouteSnapshot snapshot = RouteContract.capture("duplicate-finish-552", () -> {
            RouteContract552SqlExecutionHook hook = new RouteContract552SqlExecutionHook();
            hook.start("ds_0", "SELECT 1", List.of(), null, true);
            hook.finishSuccess();
            hook.finishFailure(new IllegalStateException("ignored"));
        });

        assertEquals(CaptureStatus.INCOMPLETE, snapshot.status());
        assertEquals(1, snapshot.observedPhysicalAttemptCount());
        assertEquals(1, snapshot.callbackReturnedCount());
        assertEquals(0, snapshot.callbackFailureCount());
        assertEquals(List.of("RC_DUPLICATE_FINISH"), snapshot.collectorDiagnostics());
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
