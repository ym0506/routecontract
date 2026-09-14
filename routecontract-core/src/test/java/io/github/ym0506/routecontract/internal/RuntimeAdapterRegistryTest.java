package io.github.ym0506.routecontract.internal;

import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import io.github.ym0506.routecontract.shardingsphere553.internal.ShardingSphere553RuntimeAdapter;
import io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter;
import org.junit.jupiter.api.Test;

import java.util.Iterator;
import java.util.List;
import java.util.ServiceConfigurationError;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RuntimeAdapterRegistryTest {

    @Test
    void zeroVisibleAdaptersHasStableNotFoundMarker() {
        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> RuntimeAdapterRegistry.verifyDiscovered(List.of()));

        assertTrue(failure.getMessage().startsWith("RC_ADAPTER_NOT_FOUND:"));
    }

    @Test
    void multipleVisibleAdaptersHaveStableMultipleMarker() {
        RouteContractRuntimeAdapter first = new StubRuntimeAdapter();
        RouteContractRuntimeAdapter second = new StubRuntimeAdapter();

        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> RuntimeAdapterRegistry.verifyDiscovered(List.of(first, second)));

        assertTrue(failure.getMessage().startsWith("RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS:"));
    }

    @Test
    void serviceConfigurationErrorIsClassifiedAsLoaderMismatch() {
        Iterable<RouteContractRuntimeAdapter> malformedProviders = () -> new Iterator<>() {
            @Override
            public boolean hasNext() {
                throw new ServiceConfigurationError("foreign provider copy");
            }

            @Override
            public RouteContractRuntimeAdapter next() {
                throw new AssertionError("next must not be called");
            }
        };

        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> RuntimeAdapterRegistry.verifyDiscovered(malformedProviders));

        assertTrue(failure.getMessage().startsWith("RC_ADAPTER_CLASSLOADER_MISMATCH:"));
        assertTrue(failure.getCause() instanceof ServiceConfigurationError);
    }

    @Test
    void foreignSameLoaderAdapterCannotClaimASupportedIdentity() {
        CountingRuntimeAdapter adapter = new CountingRuntimeAdapter();

        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> RuntimeAdapterRegistry.verifyDiscovered(List.of(adapter)));

        assertTrue(failure.getMessage().startsWith("RC_UNSUPPORTED_ROUTE_CONTRACT_ADAPTER:"));
        assertEquals(0, adapter.verifications);
    }

    @Test
    void exactProviderIsReverifiedAndCannotReturnAnotherAdaptersIdentity() {
        ShardingSphere553RuntimeAdapter.reset(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3);
        ShardingSphere553RuntimeAdapter adapter = new ShardingSphere553RuntimeAdapter();

        assertEquals(
                ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3,
                RuntimeAdapterRegistry.verifyDiscovered(List.of(adapter)));
        assertEquals(
                ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3,
                RuntimeAdapterRegistry.verifyDiscovered(List.of(adapter)));
        assertEquals(2, ShardingSphere553RuntimeAdapter.verifications());

        ShardingSphere553RuntimeAdapter.reset(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_2);
        IllegalStateException mismatch = assertThrows(
                IllegalStateException.class,
                () -> RuntimeAdapterRegistry.verifyDiscovered(
                        List.of(new ShardingSphere553RuntimeAdapter())));

        assertTrue(mismatch.getMessage().startsWith("RC_ADAPTER_IDENTITY_MISMATCH:"));
        assertEquals(1, ShardingSphere553RuntimeAdapter.verifications());
        ShardingSphere553RuntimeAdapter.reset(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3);
    }

    @Test
    void exactProviderGuardDiagnosticsRetainTheirPublicMessageAndCause() {
        try {
            for (String marker : List.of("RC_MIXED_SHARDINGSPHERE_RUNTIME", "RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME")) {
                ShardingSphere553RuntimeAdapter.reset(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3);
                IllegalStateException diagnostic = new IllegalStateException(marker + ": actual guard rejected input",
                        new IllegalArgumentException("retained diagnostic detail"));
                ShardingSphere553RuntimeAdapter.rejectWith(diagnostic);
                IllegalStateException observed = assertThrows(IllegalStateException.class,
                        () -> RuntimeAdapterRegistry.verifyDiscovered(List.of(new ShardingSphere553RuntimeAdapter())));
                assertSame(diagnostic, observed);
                assertSame(diagnostic.getCause(), observed.getCause());
                assertEquals(1, ShardingSphere553RuntimeAdapter.verifications());
            }
        } finally {
            ShardingSphere553RuntimeAdapter.reset(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3);
        }
    }

    @Test
    void exactProviderLinkageFailuresStillHaveTheClassloaderDiagnostic() {
        try {
            ShardingSphere553RuntimeAdapter.reset(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3);
            LinkageError linkage = new NoClassDefFoundError("missing runtime dependency");
            ShardingSphere553RuntimeAdapter.failLinkageWith(linkage);
            IllegalStateException observed = assertThrows(IllegalStateException.class,
                    () -> RuntimeAdapterRegistry.verifyDiscovered(List.of(new ShardingSphere553RuntimeAdapter())));
            assertTrue(observed.getMessage().startsWith("RC_ADAPTER_CLASSLOADER_MISMATCH:"));
            assertSame(linkage, observed.getCause());
        } finally {
            ShardingSphere553RuntimeAdapter.reset(ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3);
        }
    }

    @Test
    void foreignCopyBridgeHandleHasStableLoaderMismatchMarker() {
        IllegalArgumentException failure = assertThrows(
                IllegalArgumentException.class,
                () -> CaptureRegistry.finishCallbackReturnedFromAdapter(new Object()));

        assertTrue(failure.getMessage().startsWith("RC_ADAPTER_CLASSLOADER_MISMATCH:"));
    }

    @Test
    void namedModuleHasStableUnsupportedModulePathMarker() {
        IllegalStateException failure = assertThrows(
                IllegalStateException.class,
                () -> RuntimeAdapterRegistry.verifyUnnamedModules(String.class));

        assertTrue(failure.getMessage().startsWith("RC_UNSUPPORTED_MODULE_PATH:"));
    }

    private static class StubRuntimeAdapter implements RouteContractRuntimeAdapter {
        @Override
        public ShardingSphereRuntimeIdentity verifyRuntime() {
            return ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3;
        }
    }

    private static final class CountingRuntimeAdapter extends StubRuntimeAdapter {
        private int verifications;

        @Override
        public ShardingSphereRuntimeIdentity verifyRuntime() {
            verifications++;
            return super.verifyRuntime();
        }
    }
}
