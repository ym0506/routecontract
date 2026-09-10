package io.github.ym0506.routecontract.lifecycle;

import io.github.ym0506.routecontract.CaptureStatus;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity;
import io.github.ym0506.routecontract.api.RouteContract;
import org.apache.shardingsphere.driver.api.yaml.YamlShardingSphereDataSourceFactory;
import org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook;
import org.apache.shardingsphere.infra.spi.ShardingSphereServiceLoader;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.utility.DockerImageName;

import javax.sql.DataSource;
import java.io.IOException;
import java.net.JarURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Enumeration;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

/** Runs inside the controlled application loader; the launcher itself has only JDK dependencies. */
public final class LifecycleCase {
    private static final String NAMESPACE = "io.github.ym0506.routecontract.";
    private static final String CORE_ENTRY = NAMESPACE + "api.RouteContract";
    private static final String CORE_BRIDGE = NAMESPACE + "spi.RouteContractHookBridge";
    private static final String HOOK_SERVICE =
            "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";
    private static final String RUNTIME_SERVICE = "META-INF/services/" + NAMESPACE + "spi.RouteContractRuntimeAdapter";
    private static final String MYSQL_IMAGE =
            "mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb";
    private static final List<OrderRow> EXPECTED_ROWS = List.of(new OrderRow(201L, 3L, "PAID"));

    private final Map<String, Object> result;
    private final Map<String, Boolean> semanticChecks;
    private final String caseId;
    private final String runtime;
    private final String adapterModule;
    private final String hookName;
    private final String runtimeAdapterName;
    private final ClassLoader app = LifecycleCase.class.getClassLoader();
    private final Map<String, Pin> pins = new LinkedHashMap<>();
    private final List<Map<String, Object>> phases = new ArrayList<>();
    private final AtomicInteger actions = new AtomicInteger();

    private LifecycleCase(final Map<String, Object> result, final Map<?, ?> expectedPins,
            final Map<String, Boolean> semanticChecks) throws Exception {
        this.result = result;
        this.semanticChecks = semanticChecks;
        caseId = (String) result.get("caseId");
        runtime = (String) result.get("runtime");
        String suffix = runtime.equals("5.5.2") ? "552" : "553";
        adapterModule = runtime.equals("5.5.2") ? "routecontract-shardingsphere-5.5.2" : "routecontract-shardingsphere-5.5";
        hookName = NAMESPACE + "shardingsphere" + suffix + ".internal.RouteContract" + suffix + "SqlExecutionHook";
        runtimeAdapterName = NAMESPACE + "shardingsphere" + suffix + ".internal.ShardingSphere" + suffix + "RuntimeAdapter";
        require(expectedPins.keySet().equals(Set.of("routecontract-core", adapterModule)), "Unexpected pin modules");
        for (String module : List.of("routecontract-core", adapterModule)) {
            Object raw = expectedPins.get(module);
            require(raw instanceof Map<?, ?>, "Expected module pin object");
            Map<?, ?> pin = (Map<?, ?>) raw;
            require(pin.keySet().equals(Set.of("path", "sha256")), "Unexpected module pin fields");
            require(pin.get("path") instanceof String && pin.get("sha256") instanceof String, "Invalid module pin values");
            Path path = Path.of((String) pin.get("path"));
            require(path.isAbsolute() && Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS), "Pin requires regular absolute JAR");
            String sha = (String) pin.get("sha256");
            require(sha.matches("[0-9a-f]{64}") && sha.equals(digest(path)), "Pinned JAR checksum differs");
            require(path.getFileName().toString().equals(module + "-0.2.0.jar"), "Unexpected first-party JAR name");
            pins.put(module, new Pin(path.toRealPath(), sha));
        }
        result.put("loaderPhases", phases);
        result.put("physicalDriverCounterKind", "real JDBC execute delegations after warm-up");
        result.put("mysqlImage", caseId.startsWith("A12-") ? MYSQL_IMAGE : null);
        result.put("mysqlContainerCount", caseId.startsWith("A12-") ? 2 : 0);
    }

    public static void run(final Map<String, Object> result, final Map<?, ?> expectedPins,
            final Map<String, Boolean> semanticChecks) throws Exception {
        LifecycleCase fixture = new LifecycleCase(result, expectedPins, semanticChecks);
        ClassLoader original = Thread.currentThread().getContextClassLoader();
        try {
            if (fixture.caseId.startsWith("A11-")) {
                fixture.lateAttachment();
            } else if (fixture.caseId.startsWith("A12-")) {
                fixture.cachedProviderWithHiddenTccl();
            } else {
                fixture.splitBridge();
            }
        } finally {
            CountingMySqlDriver.endMeasurement();
            result.put("actionCount", fixture.actions.get());
            result.put("driverExecutionCount", CountingMySqlDriver.executionCount());
            Thread.currentThread().setContextClassLoader(original);
            result.put("applicationTcclRestored", Thread.currentThread().getContextClassLoader() == original);
        }
    }

    private void lateAttachment() throws Exception {
        ClassLoader hidden = new AdapterHidingLoader(app, pins.get(adapterModule).path(), hookName, runtimeAdapterName);
        Thread.currentThread().setContextClassLoader(hidden);
        phase("first-discovery-hidden-before", null);
        require(!canLoad(hidden, hookName) && !canLoad(hidden, runtimeAdapterName), "Hiding TCCL loads adapter classes");
        require(adapterResources(hidden, HOOK_SERVICE).isEmpty()
                && adapterResources(hidden, RUNTIME_SERVICE).isEmpty(), "Hiding TCCL exposes adapter descriptor");
        semanticChecks.put("firstTcclHidesAdapter", true);
        Collection<SQLExecutionHook> first = ShardingSphereServiceLoader.getServiceInstances(SQLExecutionHook.class);
        semanticChecks.put("actualShardingSphereDiscoveryUsed", true);
        require(routeContractProviders(first).isEmpty(), "First hidden discovery unexpectedly found RouteContract");
        semanticChecks.put("firstDiscoveryHasNoRouteContractProvider", true);
        phase("first-discovery-hidden-after", first);
        Thread.currentThread().setContextClassLoader(app);
        require(canLoad(app, hookName) && adapterResources(app, HOOK_SERVICE).size() == 1,
                "Exposing loader does not expose the real adapter");
        semanticChecks.put("exposedTcclSeesAdapter", true);
        Collection<SQLExecutionHook> later = ShardingSphereServiceLoader.getServiceInstances(SQLExecutionHook.class);
        require(routeContractProviders(later).isEmpty(), "ShardingSphere cache attached a late provider");
        semanticChecks.put("laterDiscoveryHasNoRouteContractProvider", true);
        phase("later-discovery-exposed", later);
        rejectCapture("RC_SHARDINGSPHERE_PROVIDER_NOT_ACTIVE");
    }

    private void cachedProviderWithHiddenTccl() throws Exception {
        Thread.currentThread().setContextClassLoader(app);
        phase("first-discovery-visible-before", null);
        require(canLoad(app, hookName) && canLoad(app, runtimeAdapterName)
                && adapterResources(app, HOOK_SERVICE).size() == 1
                && adapterResources(app, RUNTIME_SERVICE).size() == 1,
                "Initial application/core TCCL visibility differs");
        semanticChecks.put("firstBothLoadersSeeAdapter", true);
        Collection<SQLExecutionHook> first = ShardingSphereServiceLoader.getServiceInstances(SQLExecutionHook.class);
        semanticChecks.put("actualShardingSphereDiscoveryUsed", true);
        Class<?> cachedClass = exactProvider(first).getClass();
        phase("first-discovery-visible-after", first);
        Map<String, Object> beforeIdentity = classInfo(cachedClass);
        try (MySQLContainer<?> ds0 = mysql(); MySQLContainer<?> ds1 = mysql()) {
            ds0.start();
            ds1.start();
            result.put("physicalDriverClass", classInfo(Class.forName("com.mysql.cj.jdbc.Driver", false, app)));
            result.put("physicalDriverWrapperClass", CountingMySqlDriver.class.getName());
            result.put("mysqlServerMetadata", List.of(mysqlMetadata(ds0), mysqlMetadata(ds1)));
            initialize(ds0, false);
            initialize(ds1, true);
            DataSource dataSource = dataSource(ds0, ds1);
            try {
                require(EXPECTED_ROWS.equals(query(dataSource)), "Warm-up business rows differ");
                ClassLoader hidden = new AdapterHidingLoader(app, pins.get(adapterModule).path(), hookName, runtimeAdapterName);
                Thread.currentThread().setContextClassLoader(hidden);
                require(!canLoad(hidden, hookName) && !canLoad(hidden, runtimeAdapterName), "Hidden TCCL still loads adapter");
                require(adapterResources(hidden, HOOK_SERVICE).isEmpty()
                        && adapterResources(hidden, RUNTIME_SERVICE).isEmpty(), "Hidden TCCL exposes adapter services");
                semanticChecks.put("laterTcclHidesAdapter", true);
                require(canLoad(app, hookName) && canLoad(app, runtimeAdapterName), "Core loader lost adapter visibility");
                semanticChecks.put("laterCoreLoaderSeesAdapter", true);
                Collection<SQLExecutionHook> later = ShardingSphereServiceLoader.getServiceInstances(SQLExecutionHook.class);
                Class<?> laterClass = exactProvider(later).getClass();
                phase("cached-discovery-under-hidden-tccl", later);
                require(cachedClass == laterClass, "Cached provider class identity changed");
                require(beforeIdentity.equals(classInfo(laterClass)), "Cached provider loader or origin changed");
                result.put("cachedProviderClassUnchanged", true);
                semanticChecks.put("cachedProviderClassUnchanged", true);
                result.put("cachedProviderLoaderUnchanged", cachedClass.getClassLoader() == laterClass.getClassLoader());
                result.put("cachedProviderOriginUnchanged", true);
                CountingMySqlDriver.beginMeasurement();
                RouteSnapshot snapshot;
                try {
                    snapshot = RouteContract.capture("lifecycle-find-paid-orders-by-user", () -> {
                        actions.incrementAndGet();
                        List<OrderRow> rows = query(dataSource);
                        result.put("syntheticBusinessRows", rows.stream().map(row -> Map.of(
                                "orderId", row.orderId(), "userId", row.userId(), "status", row.status())).toList());
                        boolean matches = EXPECTED_ROWS.equals(rows);
                        result.put("exactBusinessRowsMatched", matches);
                        require(matches, "Captured business rows differ");
                    });
                } finally {
                    CountingMySqlDriver.endMeasurement();
                }
                recordSnapshot(snapshot);
                require(actions.get() == 1 && CountingMySqlDriver.executionCount() == 1,
                        "Expected exactly one action and physical driver execute delegation");
                semanticChecks.put("physicalDriverDelegatedToMysql", true);
                require(snapshot.status() == CaptureStatus.COMPLETE, "Capture was not complete");
                require(snapshot.observedPhysicalAttemptCount() == 1 && snapshot.callbackReturnedCount() == 1
                        && snapshot.callbackFailureCount() == 0 && snapshot.unknownOutcomeCount() == 0
                        && snapshot.collectorDiagnostics().isEmpty(), "Unexpected callback evidence");
                semanticChecks.put("noCallbackFailure", true);
                require(snapshot.observedDataSourceNames().equals(List.of("ds_1")), "Unexpected physical data source");
                require(snapshot.runtimeIdentity().equals(runtime.equals("5.5.2")
                        ? ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_2
                        : ShardingSphereRuntimeIdentity.SHARDINGSPHERE_5_5_3), "Capture runtime identity differs");
                Collection<SQLExecutionHook> after = ShardingSphereServiceLoader.getServiceInstances(SQLExecutionHook.class);
                require(exactProvider(after).getClass() == cachedClass, "Provider class changed after actual execution");
                phase("capture-completed-under-hidden-tccl", after);
                result.put("outcome", "CAPTURED");
            } finally {
                CountingMySqlDriver.endMeasurement();
                Thread.currentThread().setContextClassLoader(app);
                if (dataSource instanceof AutoCloseable closeable) {
                    closeable.close();
                }
            }
        }
    }

    private void splitBridge() throws Exception {
        Thread.currentThread().setContextClassLoader(app);
        Class<?> core = Class.forName(CORE_ENTRY, false, app);
        Class<?> bridge = Class.forName(CORE_BRIDGE, false, app);
        require(core.getClassLoader() == app && bridge.getClassLoader() != app, "Fixture did not separate bridge loader");
        semanticChecks.put("bridgeLoaderDistinct", true);
        Class<?> separateCore = Class.forName(CORE_ENTRY, false, bridge.getClassLoader());
        require(core != separateCore, "Fixture core copies have identical class objects");
        require(classInfo(core).get("sha256").equals(classInfo(bridge).get("sha256")), "Core and bridge bytes are not the same pinned JAR");
        semanticChecks.put("bridgeOriginMatchesCore", true);
        require(Collections.list(app.getResources(CORE_ENTRY.replace('.', '/') + ".class")).size() == 1
                && Collections.list(app.getResources(CORE_BRIDGE.replace('.', '/') + ".class")).size() == 1,
                "Fixture should expose one resource per core class");
        result.put("splitBridgeClassLoader", true);
        result.put("separatelyLoadedCoreClass", classInfo(separateCore));
        result.put("sameCoreJarAcrossLoaders", true);
        phase("split-bridge-before-discovery", null);
        String databaseAnchor = runtime.equals("5.5.2")
                ? "org.apache.shardingsphere.infra.database.core.connector.ConnectionProperties"
                : "org.apache.shardingsphere.database.connector.core.jdbcurl.parser.ConnectionProperties";
        for (String name : List.of(CORE_ENTRY, NAMESPACE + "internal.CaptureRegistry",
                NAMESPACE + "internal.CurrentRuntimeGuard", hookName,
                runtimeAdapterName, SQLExecutionHook.class.getName(), ShardingSphereServiceLoader.class.getName(), databaseAnchor)) {
            require(Class.forName(name, false, app).getClassLoader() == app, "Non-bridge anchor crossed application loader");
        }
        semanticChecks.put("otherAnchorsShareApplicationLoader", true);
        if (runtime.equals("5.5.3")) {
            require(Class.forName("org.apache.shardingsphere.infra.spi.ShardingSphereSPI", false, app).getClassLoader() == app,
                    "ShardingSphereSPI anchor crossed application loader");
        }
        Throwable discoveryFailure = null;
        try {
            ShardingSphereServiceLoader.getServiceInstances(SQLExecutionHook.class);
        } catch (Throwable failure) {
            discoveryFailure = failure;
        }
        require(discoveryFailure != null, "Split bridge unexpectedly passed real provider discovery");
        semanticChecks.put("actualShardingSphereDiscoveryUsed", true);
        require("RC_ADAPTER_CLASSLOADER_MISMATCH".equals(RuntimeLifecycleProbe.diagnostic(discoveryFailure)),
                "Real provider discovery did not expose the required loader diagnostic");
        semanticChecks.put("discoveryRejectedWithStableDiagnostic", true);
        require(!(RuntimeLifecycleProbe.unwrapInvocation(discoveryFailure) instanceof LinkageError),
                "Real provider discovery exposed a raw linkage error");
        List<Map<String, Object>> trace = RuntimeLifecycleProbe.failureChain(discoveryFailure);
        String traceText = ProbeJson.write(trace);
        require(traceText.contains(hookName + "#<init>")
                && traceText.contains("org.apache.shardingsphere.infra.spi.ShardingSphereServiceLoader#"),
                "Failure trace does not prove actual ShardingSphere hook construction");
        semanticChecks.put("discoveryTraceShowsRealHookConstructor", true);
        result.put("providerDiscoveryFailure", trace);
        result.put("providerDiscoveryDiagnosticCode", RuntimeLifecycleProbe.diagnostic(discoveryFailure));
        phase("split-bridge-after-discovery-rejection", null);
        rejectCapture("RC_ADAPTER_CLASSLOADER_MISMATCH");
        semanticChecks.put("captureRejectedWithStableDiagnostic", true);
    }

    private void rejectCapture(final String expectedMarker) throws Exception {
        Throwable exposed = null;
        try {
            RouteSnapshot snapshot = RouteContract.capture("lifecycle-rejected-operation", actions::incrementAndGet);
            recordSnapshot(snapshot);
        } catch (Throwable failure) {
            exposed = failure;
        }
        require(exposed != null, "Capture unexpectedly returned a snapshot");
        String diagnostic = RuntimeLifecycleProbe.diagnostic(exposed);
        result.put("topLevelThrowableClass", exposed.getClass().getName());
        result.put("diagnosticCode", diagnostic);
        result.put("failureChain", RuntimeLifecycleProbe.failureChain(exposed));
        result.put("exposedRawLinkageError", exposed instanceof LinkageError);
        require(expectedMarker.equals(diagnostic), "Capture produced an unexpected diagnostic");
        require(!(exposed instanceof LinkageError), "Capture exposed raw linkage error");
        require(actions.get() == 0 && CountingMySqlDriver.executionCount() == 0, "Rejected capture entered its action");
        require(Boolean.FALSE.equals(result.get("returnedSnapshot")), "Rejected capture returned snapshot");
        result.put("outcome", "EXPECTED_REJECTION");
    }

    private void recordSnapshot(final RouteSnapshot snapshot) {
        result.put("returnedSnapshot", true);
        result.put("captureStatus", snapshot.status().name());
        result.put("observedPhysicalAttemptCount", snapshot.observedPhysicalAttemptCount());
        result.put("callbackReturnedCount", snapshot.callbackReturnedCount());
        result.put("callbackFailureCount", snapshot.callbackFailureCount());
        result.put("unknownOutcomeCount", snapshot.unknownOutcomeCount());
        result.put("collectorDiagnostics", snapshot.collectorDiagnostics());
        result.put("observedDataSourceNames", snapshot.observedDataSourceNames());
    }

    private void phase(final String label, final Collection<SQLExecutionHook> providers) throws Exception {
        ClassLoader tccl = Thread.currentThread().getContextClassLoader();
        Map<String, Object> phase = new LinkedHashMap<>();
        phase.put("phase", label);
        phase.put("tccl", loaderInfo(tccl));
        phase.put("coreDefiningLoader", loaderInfo(Class.forName(CORE_ENTRY, false, app).getClassLoader()));
        phase.put("tcclCanLoadHook", canLoad(tccl, hookName));
        phase.put("tcclCanLoadRuntimeAdapter", canLoad(tccl, runtimeAdapterName));
        phase.put("coreLoaderCanLoadHook", canLoad(app, hookName));
        phase.put("coreLoaderCanLoadRuntimeAdapter", canLoad(app, runtimeAdapterName));
        phase.put("tcclHookDescriptorResources", resourceInfo(tccl, HOOK_SERVICE));
        phase.put("tcclRuntimeDescriptorResources", resourceInfo(tccl, RUNTIME_SERVICE));
        phase.put("coreHookDescriptorResources", resourceInfo(app, HOOK_SERVICE));
        phase.put("coreRuntimeDescriptorResources", resourceInfo(app, RUNTIME_SERVICE));
        phase.put("tcclHookClassResources", resourceInfo(tccl, hookName.replace('.', '/') + ".class"));
        phase.put("coreHookClassResources", resourceInfo(app, hookName.replace('.', '/') + ".class"));
        Map<String, Object> classes = new LinkedHashMap<>();
        String databaseAnchor = runtime.equals("5.5.2")
                ? "org.apache.shardingsphere.infra.database.core.connector.ConnectionProperties"
                : "org.apache.shardingsphere.database.connector.core.jdbcurl.parser.ConnectionProperties";
        List<String> observedClassNames = new ArrayList<>(List.of(CORE_ENTRY, NAMESPACE + "RouteContract", CORE_BRIDGE,
                NAMESPACE + "internal.CaptureRegistry", NAMESPACE + "spi.RouteContractRuntimeAdapter",
                NAMESPACE + "internal.CurrentRuntimeGuard",
                hookName, runtimeAdapterName, SQLExecutionHook.class.getName(),
                ShardingSphereServiceLoader.class.getName(), databaseAnchor));
        if (runtime.equals("5.5.3")) {
            observedClassNames.add("org.apache.shardingsphere.infra.spi.ShardingSphereSPI");
        }
        for (String name : observedClassNames) {
            Class<?> type = Class.forName(name, false, app);
            classes.put(name, classInfo(type));
        }
        phase.put("classes", classes);
        phase.put("providers", providers == null ? null : providerInfo(providers));
        phase.put("routeContractProviderCount", providers == null ? null : routeContractProviders(providers).size());
        phases.add(phase);
        semanticChecks.put("firstPartyOriginsPinned", true);
    }

    private List<Map<String, Object>> providerInfo(final Collection<SQLExecutionHook> providers) throws Exception {
        List<Map<String, Object>> result = new ArrayList<>();
        for (SQLExecutionHook provider : providers) {
            result.add(classInfo(provider.getClass()));
        }
        return result;
    }

    private SQLExecutionHook exactProvider(final Collection<SQLExecutionHook> providers) throws Exception {
        List<SQLExecutionHook> matching = routeContractProviders(providers);
        require(matching.size() == 1, "Expected exactly one RouteContract provider");
        SQLExecutionHook provider = matching.get(0);
        require(provider.getClass().getName().equals(hookName)
                && provider.getClass() == Class.forName(hookName, false, app), "Provider class identity differs");
        classInfo(provider.getClass());
        return provider;
    }

    private static List<SQLExecutionHook> routeContractProviders(final Collection<SQLExecutionHook> providers) {
        return providers.stream().filter(provider -> provider.getClass().getName().startsWith(NAMESPACE)).toList();
    }

    private Map<String, Object> classInfo(final Class<?> type) throws Exception {
        require(type.getProtectionDomain().getCodeSource() != null, "Missing class code source");
        Path source = Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toRealPath();
        require(Files.isRegularFile(source), "Product class must be loaded from a JAR");
        String sha = digest(source);
        if (type.getName().startsWith(NAMESPACE) && !type.getName().startsWith(NAMESPACE + "lifecycle.")) {
            Pin pin = pins.get(type.getName().startsWith(NAMESPACE + "shardingsphere") ? adapterModule : "routecontract-core");
            require(pin.path().equals(source) && pin.sha256().equals(sha), "Class origin differs from pinned first-party artifact");
        }
        Map<String, Object> identity = new LinkedHashMap<>();
        identity.put("name", type.getName());
        identity.put("classId", type.getName() + "@" + Integer.toHexString(System.identityHashCode(type)));
        identity.put("loader", loaderInfo(type.getClassLoader()));
        identity.put("jar", source.getFileName().toString());
        identity.put("sha256", sha);
        identity.put("implementationVersion", type.getPackage().getImplementationVersion());
        identity.put("namedModule", type.getModule().isNamed());
        return identity;
    }

    private static Map<String, Object> loaderInfo(final ClassLoader loader) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", loaderId(loader));
        result.put("name", loader == null ? null : loader.getName());
        result.put("class", loader == null ? null : loader.getClass().getName());
        result.put("parentId", loader == null ? null : loaderId(loader.getParent()));
        return result;
    }

    private static String loaderId(final ClassLoader loader) {
        return loader == null ? "bootstrap" : loader.getClass().getName() + "@"
                + Integer.toHexString(System.identityHashCode(loader));
    }

    private List<Map<String, Object>> resourceInfo(final ClassLoader loader, final String name) throws Exception {
        List<Map<String, Object>> resources = new ArrayList<>();
        for (URL url : Collections.list(loader.getResources(name))) {
            require(url.openConnection() instanceof JarURLConnection, "Product resource must come from an actual JAR");
            JarURLConnection connection = (JarURLConnection) url.openConnection();
            connection.setUseCaches(false);
            Path jar = Path.of(connection.getJarFileURL().toURI()).toRealPath();
            Map<String, Object> observed = new LinkedHashMap<>();
            observed.put("resource", name);
            observed.put("jar", jar.getFileName().toString());
            observed.put("normalizedUrl", "jar:" + jar.getFileName() + "!/" + connection.getEntryName());
            observed.put("sha256", digest(jar));
            observed.put("adapterResource", jar.equals(pins.get(adapterModule).path()));
            if (name.startsWith("META-INF/services/")) {
                try (var input = connection.getInputStream()) {
                    observed.put("descriptorLines", new String(input.readAllBytes(), StandardCharsets.UTF_8).lines().toList());
                }
            }
            resources.add(observed);
        }
        return resources;
    }

    private List<URL> adapterResources(final ClassLoader loader, final String name) throws Exception {
        List<URL> result = new ArrayList<>();
        for (URL url : Collections.list(loader.getResources(name))) {
            if (url.openConnection() instanceof JarURLConnection connection) {
                if (Path.of(connection.getJarFileURL().toURI()).toRealPath().equals(pins.get(adapterModule).path())) {
                    result.add(url);
                }
            }
        }
        return result;
    }

    private static boolean canLoad(final ClassLoader loader, final String name) {
        try {
            Class.forName(name, false, loader);
            return true;
        } catch (ClassNotFoundException absent) {
            return false;
        }
    }

    private static String digest(final Path path) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (var input = Files.newInputStream(path)) {
            byte[] buffer = new byte[65536];
            int read;
            while ((read = input.read(buffer)) >= 0) {
                digest.update(buffer, 0, read);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    private static void require(final boolean condition, final String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static MySQLContainer<?> mysql() {
        return new MySQLContainer<>(DockerImageName.parse(MYSQL_IMAGE).asCompatibleSubstituteFor("mysql"))
                .withDatabaseName("routecontract").withUsername("routecontract").withPassword("routecontract");
    }

    private static void initialize(final MySQLContainer<?> mysql, final boolean includeExpectedRow) throws Exception {
        try (Connection connection = DriverManager.getConnection(mysql.getJdbcUrl(), mysql.getUsername(), mysql.getPassword());
             Statement statement = connection.createStatement()) {
            statement.execute("CREATE TABLE t_order_0 (order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
            statement.execute("CREATE TABLE t_order_1 (order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
            if (includeExpectedRow) {
                statement.executeUpdate("INSERT INTO t_order_1(order_id, user_id, status) VALUES (201, 3, 'PAID')");
            } else {
                statement.executeUpdate("INSERT INTO t_order_0(order_id, user_id, status) VALUES (202, 2, 'PAID')");
            }
        }
    }

    private static Map<String, Object> mysqlMetadata(final MySQLContainer<?> mysql) throws Exception {
        try (Connection connection = DriverManager.getConnection(mysql.getJdbcUrl(), mysql.getUsername(), mysql.getPassword())) {
            String product = connection.getMetaData().getDatabaseProductName();
            String version = connection.getMetaData().getDatabaseProductVersion();
            require("MySQL".equals(product) && version.startsWith("8.4.11"), "Unexpected actual database product/version");
            return Map.of("databaseProductName", product, "databaseProductVersion", version);
        }
    }

    private static DataSource dataSource(final MySQLContainer<?> ds0, final MySQLContainer<?> ds1) throws Exception {
        String yaml = """
                mode:
                  type: Standalone
                dataSources:
                  ds_0:
                    dataSourceClassName: com.zaxxer.hikari.HikariDataSource
                    driverClassName: io.github.ym0506.routecontract.lifecycle.CountingMySqlDriver
                    jdbcUrl: 'DS0_URL'
                    username: 'DS0_USER'
                    password: 'DS0_PASSWORD'
                    minimumIdle: 1
                    maximumPoolSize: 1
                  ds_1:
                    dataSourceClassName: com.zaxxer.hikari.HikariDataSource
                    driverClassName: io.github.ym0506.routecontract.lifecycle.CountingMySqlDriver
                    jdbcUrl: 'DS1_URL'
                    username: 'DS1_USER'
                    password: 'DS1_PASSWORD'
                    minimumIdle: 1
                    maximumPoolSize: 1
                rules:
                  - !SHARDING
                    tables:
                      t_order:
                        actualDataNodes: ds_${0..1}.t_order_${0..1}
                        databaseStrategy:
                          standard:
                            shardingColumn: user_id
                            shardingAlgorithmName: database_inline
                        tableStrategy:
                          standard:
                            shardingColumn: user_id
                            shardingAlgorithmName: table_inline
                    shardingAlgorithms:
                      database_inline:
                        type: INLINE
                        props:
                          algorithm-expression: ds_${user_id % 2}
                      table_inline:
                        type: INLINE
                        props:
                          algorithm-expression: t_order_${user_id % 2}
                props:
                  sql-show: false
                  executor-size: 1
                """
                .replace("DS0_URL", ds0.getJdbcUrl()).replace("DS0_USER", ds0.getUsername()).replace("DS0_PASSWORD", ds0.getPassword())
                .replace("DS1_URL", ds1.getJdbcUrl()).replace("DS1_USER", ds1.getUsername()).replace("DS1_PASSWORD", ds1.getPassword());
        return YamlShardingSphereDataSourceFactory.createDataSource(yaml.getBytes(StandardCharsets.UTF_8));
    }

    private static List<OrderRow> query(final DataSource source) throws Exception {
        try (Connection connection = source.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT order_id, user_id, status FROM t_order WHERE user_id = ? AND status = ?")) {
            statement.setLong(1, 3L);
            statement.setString(2, "PAID");
            try (ResultSet results = statement.executeQuery()) {
                List<OrderRow> rows = new ArrayList<>();
                while (results.next()) {
                    rows.add(new OrderRow(results.getLong("order_id"), results.getLong("user_id"), results.getString("status")));
                }
                return List.copyOf(rows);
            }
        }
    }

    private record Pin(Path path, String sha256) {
    }

    private record OrderRow(long orderId, long userId, String status) {
    }

    /** Defines no application classes and filters only the actual selected adapter artifact. */
    private static final class AdapterHidingLoader extends ClassLoader {
        private final Path hiddenJar;
        private final String adapterPackage;

        private AdapterHidingLoader(final ClassLoader parent, final Path hiddenJar,
                final String hookName, final String runtimeAdapterName) {
            super("adapter-hiding-tccl", parent);
            this.hiddenJar = hiddenJar;
            adapterPackage = hookName.substring(0, hookName.lastIndexOf('.') + 1);
            require(runtimeAdapterName.startsWith(adapterPackage), "Mismatched adapter package");
        }

        @Override
        protected Class<?> loadClass(final String name, final boolean resolve) throws ClassNotFoundException {
            if (name.startsWith(adapterPackage)) {
                throw new ClassNotFoundException("Adapter intentionally hidden by lifecycle fixture");
            }
            return super.loadClass(name, resolve);
        }

        @Override
        public Enumeration<URL> getResources(final String name) throws IOException {
            List<URL> visible = new ArrayList<>();
            for (URL url : Collections.list(getParent().getResources(name))) {
                if (!hidden(url)) {
                    visible.add(url);
                }
            }
            return Collections.enumeration(visible);
        }

        @Override
        public URL getResource(final String name) {
            try {
                Enumeration<URL> visible = getResources(name);
                return visible.hasMoreElements() ? visible.nextElement() : null;
            } catch (IOException failure) {
                throw new IllegalStateException("Lifecycle resource lookup failed", failure);
            }
        }

        private boolean hidden(final URL url) throws IOException {
            if (!(url.openConnection() instanceof JarURLConnection connection)) {
                return false;
            }
            try {
                return Path.of(connection.getJarFileURL().toURI()).toRealPath().equals(hiddenJar);
            } catch (java.net.URISyntaxException failure) {
                throw new IOException("Malformed classpath resource origin", failure);
            }
        }
    }
}
