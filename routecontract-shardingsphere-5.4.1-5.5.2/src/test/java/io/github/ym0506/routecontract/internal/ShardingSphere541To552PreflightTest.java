package io.github.ym0506.routecontract.internal;

import org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ShardingSphere541To552PreflightTest {

    @Test
    void actualTestRuntimeAndProviderDiscoveryPassPreflight() {
        assertDoesNotThrow(ShardingSphere541To552Preflight::verify);
    }

    @Test
    void acceptsEachSupportedVersion() {
        for (String each : List.of("5.4.1", "5.5.0", "5.5.1", "5.5.2")) {
            assertDoesNotThrow(() -> ShardingSphere541To552Preflight.verifySupportedVersion("test-component", each));
        }
    }

    @Test
    void rejectsUnknownOrDifferentRuntimeVersion() {
        IllegalStateException unavailable = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere541To552Preflight.verifySupportedVersion("test-component", null));
        IllegalStateException newer = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere541To552Preflight.verifySupportedVersion("test-component", "5.5.3"));
        IllegalStateException older = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere541To552Preflight.verifySupportedVersion("test-component", "5.4.0"));

        assertTrue(unavailable.getMessage().contains("<unavailable>"));
        assertTrue(newer.getMessage().contains("5.5.3"));
        assertTrue(newer.getMessage().contains("routecontract-shardingsphere-5.5"));
        assertTrue(older.getMessage().contains("5.4.0"));
    }

    @Test
    void rejectsMixedRuntimeVersions() {
        IllegalStateException mixed = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere541To552Preflight.verifySameVersion("test-component", "5.5.1", "5.5.2"));

        assertTrue(mixed.getMessage().contains("5.5.1"));
        assertTrue(mixed.getMessage().contains("5.5.2"));
    }

    @Test
    void rejectsMissingOrDuplicateRouteContractProviders() {
        assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere541To552Preflight.verifyProviderDiscovery(List.of()));

        SQLExecutionHook first = new RouteContractSqlExecutionHook();
        SQLExecutionHook second = new RouteContractSqlExecutionHook();
        assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere541To552Preflight.verifyProviderDiscovery(List.of(first, second)));
    }
}
