package io.github.ym0506.routecontract.lifecycle;

import java.lang.reflect.InvocationTargetException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/** JDK-only fresh-process launcher; application dependencies are owned by one controlled loader. */
public final class RuntimeLifecycleProbe {
    private static final String BRIDGE = "io.github.ym0506.routecontract.spi.RouteContractHookBridge";
    // This fresh JVM owns loader lifetime, including third-party shutdown hooks after main returns.
    // Closing either loader at action completion can prevent those hooks from loading cleanup classes.
    private static final List<ClassLoader> PROCESS_LOADERS = new ArrayList<>();

    private RuntimeLifecycleProbe() {
    }

    public static void main(final String[] arguments) throws Exception {
        if (arguments.length != 4) {
            throw new IllegalArgumentException("Expected CASE_ID RUNTIME OUTPUT_JSON FIRST_PARTY_EXPECTED_JSON");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("formatVersion", 1);
        result.put("caseId", arguments[0]);
        result.put("runtime", arguments[1]);
        result.put("outcome", "FAILED");
        result.put("diagnosticCode", null);
        result.put("actionCount", 0);
        result.put("driverExecutionCount", 0);
        result.put("returnedSnapshot", false);
        result.put("topLevelThrowableClass", null);
        result.put("exposedRawLinkageError", false);
        result.put("captureStatus", null);
        result.put("observedPhysicalAttemptCount", 0);
        result.put("exactBusinessRowsMatched", false);
        result.put("loaderPhases", new ArrayList<>());
        Map<String, Boolean> semanticChecks = new LinkedHashMap<>();
        result.put("semanticChecks", semanticChecks);
        ClassLoader originalTccl = Thread.currentThread().getContextClassLoader();
        try {
            String versionSuffix = switch (arguments[1]) {
                case "5.5.2" -> "552";
                case "5.5.3" -> "553";
                default -> throw new IllegalArgumentException("Unsupported exact runtime");
            };
            if (!Set.of("A11-" + versionSuffix, "A12-" + versionSuffix, "A13-" + versionSuffix)
                    .contains(arguments[0])) {
                throw new IllegalArgumentException("Case and exact runtime do not match");
            }
            Object pins = ProbeJson.parse(Files.readString(Path.of(arguments[3]), StandardCharsets.UTF_8));
            if (!(pins instanceof Map<?, ?> pinMap)) {
                throw new IllegalArgumentException("Pins must be an object");
            }
            Object corePin = pinMap.get("routecontract-core");
            if (!(corePin instanceof Map<?, ?> core) || !(core.get("path") instanceof String corePath)) {
                throw new IllegalArgumentException("Missing core path pin");
            }
            List<URL> urls = new ArrayList<>();
            for (String entry : requiredProperty("routecontract.resolvedClasspath")
                    .split(Pattern.quote(System.getProperty("path.separator")), -1)) {
                if (entry.isBlank()) {
                    throw new IllegalArgumentException("Empty resolved classpath entry");
                }
                urls.add(Path.of(entry).toRealPath().toUri().toURL());
            }
            URL fixtureClasses = Path.of(requiredProperty("routecontract.fixtureClasses"))
                    .toRealPath().toUri().toURL();
            if (!urls.contains(fixtureClasses)) {
                urls.add(0, fixtureClasses);
            }
            URLClassLoader bridgeLoader = new URLClassLoader("isolated-bridge",
                    new URL[]{Path.of(corePath).toRealPath().toUri().toURL()},
                    ClassLoader.getPlatformClassLoader());
            PROCESS_LOADERS.add(bridgeLoader);
            ApplicationLoader app = new ApplicationLoader(urls.toArray(URL[]::new),
                    arguments[0].startsWith("A13-") ? bridgeLoader : null);
            PROCESS_LOADERS.add(app);
            Thread.currentThread().setContextClassLoader(app);
            Class<?> worker = Class.forName(
                    "io.github.ym0506.routecontract.lifecycle.LifecycleCase", true, app);
            worker.getMethod("run", Map.class, Map.class, Map.class).invoke(null, result, pinMap, semanticChecks);
        } catch (Throwable failure) {
            Throwable exposed = unwrapInvocation(failure);
            result.put("outcome", "FAILED");
            result.put("topLevelThrowableClass", exposed.getClass().getName());
            result.put("diagnosticCode", diagnostic(exposed));
            result.put("exposedRawLinkageError", exposed instanceof LinkageError);
            result.put("failureChain", failureChain(exposed));
        } finally {
            Thread.currentThread().setContextClassLoader(originalTccl);
            result.put("tcclRestored", Thread.currentThread().getContextClassLoader() == originalTccl);
            semanticChecks.put("tcclRestored", Thread.currentThread().getContextClassLoader() == originalTccl);
            Files.writeString(Path.of(arguments[2]), ProbeJson.write(result) + "\n", StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
        }
        System.out.println("ROUTECONTRACT_LIFECYCLE " + arguments[0] + " " + result.get("outcome"));
        if ("FAILED".equals(result.get("outcome"))) {
            System.exit(1);
        }
    }

    private static String requiredProperty(final String key) {
        String value = System.getProperty(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing lifecycle launcher property: " + key);
        }
        return value;
    }

    static Throwable unwrapInvocation(final Throwable failure) {
        Throwable current = failure;
        while (current instanceof InvocationTargetException invocation && invocation.getCause() != null) {
            current = invocation.getCause();
        }
        return current;
    }

    static String diagnostic(final Throwable failure) {
        for (Throwable current : causes(failure)) {
            String message = current.getMessage();
            if (message != null && message.matches("(?s)^RC_[A-Z0-9_]+:.*")) {
                return message.substring(0, message.indexOf(':'));
            }
        }
        return null;
    }

    static List<Map<String, Object>> failureChain(final Throwable failure) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (Throwable current : causes(failure)) {
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("class", current.getClass().getName());
            entry.put("diagnosticCode", diagnostic(current));
            List<String> frames = new ArrayList<>();
            for (StackTraceElement frame : current.getStackTrace()) {
                // Class/method/line provenance is retained, never exception messages or connection data.
                frames.add(frame.getClassName() + "#" + frame.getMethodName() + ":" + frame.getLineNumber());
            }
            entry.put("frames", frames);
            result.add(entry);
        }
        return result;
    }

    private static List<Throwable> causes(final Throwable failure) {
        List<Throwable> result = new ArrayList<>();
        Set<Throwable> seen = java.util.Collections.newSetFromMap(new IdentityHashMap<>());
        for (Throwable current = failure; current != null && seen.add(current); current = current.getCause()) {
            result.add(current);
        }
        return result;
    }

    private static final class ApplicationLoader extends URLClassLoader {
        private final ClassLoader bridgeLoader;

        private ApplicationLoader(final URL[] urls, final ClassLoader bridgeLoader) {
            super("lifecycle-application", urls, ClassLoader.getPlatformClassLoader());
            this.bridgeLoader = bridgeLoader;
        }

        @Override
        protected Class<?> loadClass(final String name, final boolean resolve) throws ClassNotFoundException {
            if (bridgeLoader != null && BRIDGE.equals(name)) {
                return bridgeLoader.loadClass(name);
            }
            return super.loadClass(name, resolve);
        }
    }
}
