package io.github.ym0506.routecontract.shardingsphere552.internal;

import io.github.ym0506.routecontract.api.RouteContract;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

/** Reproduces the observed missing-SPI mixed inputs before any caller action. */
public final class FreshJvmMixedAnchorProbe {
    private static int actionEntries;

    private FreshJvmMixedAnchorProbe() {
    }

    public static void main(final String[] arguments) throws Throwable {
        if (arguments.length != 1 || !Set.of("RC_MIXED_SHARDINGSPHERE_RUNTIME",
                "RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME").contains(arguments[0])) {
            throw new IllegalArgumentException("Expected one supported diagnostic marker");
        }
        String expectedMarker = arguments[0];
        try {
            RouteContract.capture("missing-spi-mixed-regression", () -> actionEntries++);
        } catch (Throwable failure) {
            failure.printStackTrace(System.out);
            boolean marker = failure.getMessage() != null
                    && failure.getMessage().startsWith(expectedMarker + ":");
            boolean linkageFailure = false;
            boolean guardFrame = false;
            Set<Throwable> seen = Collections.newSetFromMap(new IdentityHashMap<>());
            for (Throwable cursor = failure; cursor != null && seen.add(cursor); cursor = cursor.getCause()) {
                linkageFailure |= cursor instanceof LinkageError;
                for (StackTraceElement frame : cursor.getStackTrace()) {
                    guardFrame |= frame.getClassName().endsWith("HookConstructionGuard");
                }
            }
            if (marker && guardFrame && !linkageFailure && actionEntries == 0) {
                System.out.println("ROUTECONTRACT_DIAGNOSTIC_REJECTED_BEFORE_ACTION marker="
                        + expectedMarker + " actionEntries=0");
                return;
            }
            throw new AssertionError("Expected the actual guard diagnostic at the top level with zero action and no linkage cause; actions="
                    + actionEntries, failure);
        }
        throw new AssertionError("Mixed runtime capture unexpectedly returned; actions=" + actionEntries);
    }
}
