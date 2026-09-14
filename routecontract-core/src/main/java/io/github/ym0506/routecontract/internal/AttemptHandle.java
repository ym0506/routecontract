package io.github.ym0506.routecontract.internal;

record AttemptHandle(MutableCapture capture, MutableAttempt attempt) {
    private static final AttemptHandle NOOP = new AttemptHandle(null, null);

    static AttemptHandle noop() {
        return NOOP;
    }

    boolean isActive() {
        return capture != null && attempt != null;
    }
}
