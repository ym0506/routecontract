package io.github.ym0506.routecontract.shardingsphere552.internal;

/** Child-process entry point for fail-before-first-bridge-call compatibility probes. */
public final class FreshJvmGuardProbe {

    private FreshJvmGuardProbe() {
    }

    /** Runs one hook construction and accepts only the requested stable RouteContract marker. */
    public static void main(final String[] arguments) {
        if (arguments.length != 1) {
            throw new IllegalArgumentException("exactly one expected marker is required");
        }
        String expectedMarker = arguments[0];
        try {
            new RouteContract552SqlExecutionHook();
        } catch (Throwable failure) {
            Throwable current = failure;
            while (current != null) {
                if (current.getMessage() != null && current.getMessage().startsWith(expectedMarker + ":")) {
                    System.out.println("ROUTECONTRACT_EXPECTED_GUARD_FAILURE " + current.getMessage());
                    return;
                }
                current = current.getCause();
            }
            throw failure;
        }
        throw new AssertionError("hook construction unexpectedly accepted the incompatible core");
    }
}
