package io.github.ym0506.routecontract.consumer;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.ym0506.routecontract.api.RouteContract;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Fresh-process new-API probe: no datasource, SQL, service discovery, or explicit guard invocation. */
public final class CurrentEntryRegressionProbe {
    private static int actionEntries;

    private CurrentEntryRegressionProbe() { }

    public static void main(final String[] args) throws Exception {
        if (args.length != 2 || !("capture".equals(args[0]) || "captureResult".equals(args[0]))) {
            throw new IllegalArgumentException("Expected capture or captureResult, followed by an observation path");
        }
        String mode = args[0];
        boolean returned = false;
        boolean linkageFailure = false;
        List<String> exceptionClasses = new ArrayList<>();
        List<String> exceptionMessages = new ArrayList<>();
        List<String> stackFrames = new ArrayList<>();
        try {
            // This is deliberately the first RouteContract method invocation in this JVM.
            if ("capture".equals(mode)) {
                RouteContract.capture("current-entry-regression", () -> actionEntries++);
            } else {
                RouteContract.captureResult("current-entry-regression", () -> {
                    actionEntries++;
                    return "current-entry-sentinel";
                });
            }
            returned = true;
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

        // Inspect selected definitions only after the tested entry returned or failed.
        ClassLoader loader = CurrentEntryRegressionProbe.class.getClassLoader();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("mode", mode);
        result.put("pid", ProcessHandle.current().pid());
        result.put("javaVersion", System.getProperty("java.version"));
        result.put("newEntryOrigin", origin(RouteContract.class));
        result.put("guardOrigin", origin(Class.forName(
                "io.github.ym0506.routecontract.internal.CurrentRuntimeGuard", false, loader)));
        result.put("legacyEntryOrigin", origin(Class.forName(
                "io.github.ym0506.routecontract.RouteContract", false, loader)));
        result.put("captureRegistryOrigin", origin(Class.forName(
                "io.github.ym0506.routecontract.internal.CaptureRegistry", false, loader)));
        result.put("shardingSphereVersion", Class.forName(
                "org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook", false, loader)
                .getPackage().getImplementationVersion());
        result.put("returned", returned);
        result.put("actionEntered", actionEntries != 0);
        result.put("actionEntries", actionEntries);
        result.put("linkageFailure", linkageFailure);
        result.put("exceptionClasses", exceptionClasses);
        result.put("exceptionMessages", exceptionMessages);
        result.put("stackFrames", stackFrames);
        result.put("boundary", "No datasource or SQL is exercised; this is an API action-sentinel regression.");
        new ObjectMapper().writerWithDefaultPrettyPrinter().writeValue(Path.of(args[1]).toFile(), result);
    }

    private static String origin(final Class<?> type) throws Exception {
        return Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toString();
    }
}
