package io.github.ym0506.routecontract.shardingsphere553.internal;

import example.UnrelatedSqlExecutionHook;
import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ShardingSphere553PreflightTest {

    @Test
    void actualTestRuntimeAndProviderDiscoveryPassPreflight() {
        assertEquals(
                ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3,
                assertDoesNotThrow(ShardingSphere553Preflight::verify));
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

        SQLExecutionHook first = new RouteContract553SqlExecutionHook();
        SQLExecutionHook second = new RouteContract553SqlExecutionHook();
        assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553Preflight.verifyProviderDiscovery(List.of(first, second)));
    }

    @Test
    void rejectsAnExtraRouteContractNamespaceProviderButAllowsUnrelatedHooks() {
        SQLExecutionHook exact = new RouteContract553SqlExecutionHook();
        SQLExecutionHook rogue = new RogueRouteContractHook();

        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553Preflight.verifyProviderDiscovery(List.of(exact, rogue)));

        assertTrue(failure.getMessage().startsWith("RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS:"));
        assertDoesNotThrow(() -> ShardingSphere553Preflight.verifyProviderDiscovery(
                List.of(exact, new UnrelatedSqlExecutionHook())));
    }

    @Test
    void hookKeepsItsAttemptOpaqueUntilConstructionGuardCompletes() throws NoSuchFieldException {
        assertEquals(Object.class, RouteContract553SqlExecutionHook.class
                .getDeclaredField("inFlight")
                .getType());
        assertDoesNotThrow(RouteContract553SqlExecutionHook::new);
    }

    @Test
    void constructionGuardCachesOnlyAClassloaderAndRuntimeTupleStamp() throws NoSuchFieldException {
        Field stamp = ShardingSphere553HookConstructionGuard.class.getDeclaredField("verifiedStamp");

        assertEquals("VerificationStamp", stamp.getType().getSimpleName());
        assertTrue(Modifier.isStatic(stamp.getModifiers()));
        assertTrue(Modifier.isVolatile(stamp.getModifiers()));
        assertTrue(Arrays.stream(ShardingSphere553HookConstructionGuard.class.getDeclaredFields())
                .noneMatch(field -> field.getType() == boolean.class));
        Set<String> stampComponents = Arrays.stream(stamp.getType().getRecordComponents())
                .map(component -> component.getName())
                .collect(Collectors.toSet());
        assertTrue(stampComponents.containsAll(Set.of(
                "loader",
                "hookType",
                "coreEntryPoint",
                "coreBridge",
                "coreCollector",
                "coreRuntimeAdapter",
                "coreRuntimeIdentity",
                "runtimeProvider",
                "executorAnchor",
                "spiAnchor",
                "databaseAnchor",
                "hookOrigin",
                "coreBridgeOrigin",
                "runtimeProviderOrigin",
                "executorOrigin",
                "spiOrigin",
                "databaseOrigin")));
    }

    @Test
    void anchorVersionClassificationUsesStableUnsupportedAndMixedMarkers() {
        IllegalStateException unsupported = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553HookConstructionGuard.verifyAnchorVersions(
                        "5.5.2", "5.5.2", "5.5.2"));
        IllegalStateException mixed = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553HookConstructionGuard.verifyAnchorVersions(
                        "5.5.3", "5.5.2", "5.5.3"));
        IllegalStateException missingExecutor = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553HookConstructionGuard.verifyAnchorVersions(
                        null, "5.5.3", "5.5.3"));
        IllegalStateException missingSpi = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553HookConstructionGuard.verifyAnchorVersions(
                        "5.5.3", null, "5.5.3"));
        IllegalStateException missingDatabase = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553HookConstructionGuard.verifyAnchorVersions(
                        "5.5.3", "5.5.3", null));

        assertTrue(unsupported.getMessage().startsWith("RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME:"));
        assertTrue(mixed.getMessage().startsWith("RC_MIXED_SHARDINGSPHERE_RUNTIME:"));
        assertTrue(missingExecutor.getMessage().startsWith("RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME:"));
        assertTrue(missingSpi.getMessage().startsWith("RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME:"));
        assertTrue(missingDatabase.getMessage().startsWith("RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME:"));
    }

    @Test
    void passiveDescriptorClassificationRejectsMissingDualAndLegacyLayouts() {
        String hook = "io.github.ym0506.routecontract.shardingsphere553.internal."
                + "RouteContract553SqlExecutionHook";
        String runtime = "io.github.ym0506.routecontract.shardingsphere553.internal."
                + "ShardingSphere553RuntimeAdapter";
        String hook552 = "io.github.ym0506.routecontract.shardingsphere552.internal."
                + "RouteContract552SqlExecutionHook";
        String legacy = "io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook";
        String rogueHook = "io.github.ym0506.routecontract.rogue.RogueSqlExecutionHook";
        String rogueRuntime = "example.RogueRuntimeAdapter";

        IllegalStateException missing = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553HookConstructionGuard.verifyProviderNames(
                        List.of(), List.of(), false));
        IllegalStateException multiple = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553HookConstructionGuard.verifyProviderNames(
                        List.of(hook, hook552), List.of(runtime), false));
        IllegalStateException collision = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553HookConstructionGuard.verifyProviderNames(
                        List.of(hook, legacy), List.of(runtime), true));
        IllegalStateException extraHook = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553HookConstructionGuard.verifyProviderNames(
                        List.of(hook, rogueHook), List.of(runtime), false));
        IllegalStateException extraRuntime = assertThrows(
                IllegalStateException.class,
                () -> ShardingSphere553HookConstructionGuard.verifyProviderNames(
                        List.of(hook), List.of(runtime, rogueRuntime), false));
        assertDoesNotThrow(() -> ShardingSphere553HookConstructionGuard.verifyProviderNames(
                List.of(hook, "example.UnrelatedSqlExecutionHook"), List.of(runtime), false));

        assertTrue(missing.getMessage().startsWith("RC_ADAPTER_NOT_FOUND:"));
        assertTrue(multiple.getMessage().startsWith("RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS:"));
        assertTrue(collision.getMessage().startsWith("RC_LEGACY_ADAPTER_COLLISION:"));
        assertTrue(extraHook.getMessage().startsWith("RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS:"));
        assertTrue(extraRuntime.getMessage().startsWith("RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS:"));
    }

    private static final class RogueRouteContractHook implements SQLExecutionHook {
        @Override
        public void start(
                final String dataSourceName,
                final String sql,
                final List<Object> parameters,
                final org.apache.shardingsphere.database.connector.core.jdbcurl.parser.ConnectionProperties
                        connectionProperties,
                final boolean trunkThread) {
        }

        @Override
        public void finishSuccess() {
        }

        @Override
        public void finishFailure(final Exception cause) {
        }
    }
}
