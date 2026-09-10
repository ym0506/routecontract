package io.github.ym0506.routecontract;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ShardingSphereRuntimeIdentityTest {

    @Test
    void exactSupportedIdentitiesAreImmutableValues() {
        ShardingSphereRuntimeIdentity identity = new ShardingSphereRuntimeIdentity(
                ShardingSphereRuntimeIdentity.SQL_EXECUTION_HOOK_ADAPTER_ID,
                ShardingSphereRuntimeIdentity.CURRENT_ADAPTER_CONTRACT_VERSION,
                "5.5.2",
                "5.5.2");

        assertEquals(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_2, identity);
        assertTrue(identity.isSupported());
        assertTrue(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3.isSupported());
    }

    @Test
    void syntacticallyValidFutureOrMixedIdentitiesRemainRepresentableButUnsupported() {
        assertFalse(new ShardingSphereRuntimeIdentity(
                ShardingSphereRuntimeIdentity.SQL_EXECUTION_HOOK_ADAPTER_ID,
                ShardingSphereRuntimeIdentity.CURRENT_ADAPTER_CONTRACT_VERSION,
                "5.5.4",
                "5.5.4").isSupported());
        assertFalse(new ShardingSphereRuntimeIdentity(
                ShardingSphereRuntimeIdentity.SQL_EXECUTION_HOOK_ADAPTER_ID,
                ShardingSphereRuntimeIdentity.CURRENT_ADAPTER_CONTRACT_VERSION,
                "5.5.2",
                "5.5.3").isSupported());
    }

    @Test
    void malformedIdentityValuesAreRejected() {
        assertThrows(NullPointerException.class, () -> new ShardingSphereRuntimeIdentity(
                null, 1, "5.5.3", "5.5.3"));
        assertThrows(IllegalArgumentException.class, () -> new ShardingSphereRuntimeIdentity(
                " ", 1, "5.5.3", "5.5.3"));
        assertThrows(IllegalArgumentException.class, () -> new ShardingSphereRuntimeIdentity(
                "invalid adapter", 1, "5.5.3", "5.5.3"));
        assertThrows(IllegalArgumentException.class, () -> new ShardingSphereRuntimeIdentity(
                ShardingSphereRuntimeIdentity.SQL_EXECUTION_HOOK_ADAPTER_ID, 0, "5.5.3", "5.5.3"));
        assertThrows(IllegalArgumentException.class, () -> new ShardingSphereRuntimeIdentity(
                ShardingSphereRuntimeIdentity.SQL_EXECUTION_HOOK_ADAPTER_ID, 1, "", "5.5.3"));
        assertThrows(IllegalArgumentException.class, () -> new ShardingSphereRuntimeIdentity(
                ShardingSphereRuntimeIdentity.SQL_EXECUTION_HOOK_ADAPTER_ID, 1, "5.5.3", "bad version"));
    }
}
