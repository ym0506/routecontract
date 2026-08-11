package io.github.ym0506.routecontract.internal;

import org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ShardingSphere553PreflightTest {

    @Test
    void actualTestRuntimeAndProviderDiscoveryPassPreflight() {
        assertDoesNotThrow(ShardingSphere553Preflight::verify);
    }

    @Test
    void rejectsUnknownOrDifferentRuntimeVersion() {
        IllegalStateException unavailable = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553Preflight.verifyExactVersion("test-component", null));
        IllegalStateException wrong = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553Preflight.verifyExactVersion("test-component", "5.5.2"));

        assertTrue(unavailable.getMessage().contains("<unavailable>"));
        assertTrue(wrong.getMessage().contains("5.5.2"));
    }

    @Test
    void rejectsMissingOrDuplicateRouteContractProviders() {
        assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553Preflight.verifyProviderDiscovery(List.of()));

        SQLExecutionHook first = new RouteContractSqlExecutionHook();
        SQLExecutionHook second = new RouteContractSqlExecutionHook();
        assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553Preflight.verifyProviderDiscovery(List.of(first, second)));
    }
}
