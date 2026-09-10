package io.github.ym0506.routecontract.consumer;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.api.RouteContract;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HexFormat;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Observes one current capture in a fresh JVM; anchor reflection happens afterwards. */
public final class MixedAnchorProbe {
    private static int actionEntries;
    private MixedAnchorProbe() { }

    public static void main(final String[] args) throws Exception {
        if (args.length != 2 || !Set.of("5.5.2", "5.5.3").contains(args[0])) {
            throw new IllegalArgumentException("Expected adapter version and output file");
        }
        String adapter = args[0];
        boolean returned = false;
        boolean linkageFailure = false;
        Map<String, Object> snapshot = null;
        List<String> exceptionClasses = new ArrayList<>();
        List<String> exceptionMessages = new ArrayList<>();
        List<String> stackFrames = new ArrayList<>();
        try {
            RouteSnapshot captured = RouteContract.capture("mixed-anchor-sentinel", () -> actionEntries++);
            returned = true;
            snapshot = new LinkedHashMap<>();
            snapshot.put("schemaVersion", captured.schemaVersion());
            snapshot.put("status", captured.status().name());
            snapshot.put("observedPhysicalAttemptCount", captured.observedPhysicalAttemptCount());
            snapshot.put("collectorDiagnostics", captured.collectorDiagnostics());
            snapshot.put("runtimeIdentity", captured.runtimeIdentity());
        } catch (Throwable failure) {
            failure.printStackTrace(System.out);
            Set<Throwable> seen = Collections.newSetFromMap(new IdentityHashMap<>());
            for (Throwable cursor = failure; cursor != null && seen.add(cursor); cursor = cursor.getCause()) {
                exceptionClasses.add(cursor.getClass().getName());
                exceptionMessages.add(String.valueOf(cursor.getMessage()));
                linkageFailure |= cursor instanceof LinkageError;
                for (StackTraceElement frame : cursor.getStackTrace()) {
                    stackFrames.add(frame.getClassName() + "." + frame.getMethodName());
                }
            }
        }
        // Do not prime any ShardingSphere class or loader before the capture under test.
        String spi = adapter.equals("5.5.2") ? "ShardingSphereServiceLoader" : "ShardingSphereSPI";
        String database = adapter.equals("5.5.2")
                ? "org.apache.shardingsphere.infra.database.core.connector.ConnectionProperties"
                : "org.apache.shardingsphere.database.connector.core.jdbcurl.parser.ConnectionProperties";
        Map<String, Object> anchors = new LinkedHashMap<>();
        anchors.put("executor", anchor("org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook"));
        anchors.put("spi", anchor("org.apache.shardingsphere.infra.spi." + spi));
        anchors.put("database", anchor(database));
        Map<String, Object> observed = new LinkedHashMap<>();
        observed.put("pid", ProcessHandle.current().pid());
        observed.put("javaVersion", System.getProperty("java.version"));
        observed.put("adapter", adapter);
        observed.put("returned", returned);
        observed.put("actionEntries", actionEntries);
        observed.put("snapshot", snapshot);
        observed.put("exceptionClasses", exceptionClasses);
        observed.put("exceptionMessages", exceptionMessages);
        observed.put("stackFrames", stackFrames);
        observed.put("linkageFailure", linkageFailure);
        observed.put("newEntry", anchor("io.github.ym0506.routecontract.api.RouteContract"));
        observed.put("anchors", anchors);
        new ObjectMapper().writerWithDefaultPrettyPrinter().writeValue(Path.of(args[1]).toFile(), observed);
    }

    private static Map<String, Object> anchor(final String name) throws Exception {
        try {
        Class<?> type = Class.forName(name, false, MixedAnchorProbe.class.getClassLoader());
        Path origin = Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toRealPath();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("className", name);
        result.put("loaded", true);
        result.put("implementationVersion", type.getPackage().getImplementationVersion());
        result.put("origin", origin.toString());
        result.put("sha256", HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest(java.nio.file.Files.readAllBytes(origin))));
        return result;
        } catch (ClassNotFoundException | LinkageError failure) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("className", name);
            result.put("loaded", false);
            result.put("loadFailureClass", failure.getClass().getName());
            result.put("loadFailureMessage", String.valueOf(failure.getMessage()));
            return result;
        }
    }
}
