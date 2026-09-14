package io.github.ym0506.routecontract.internal;

import java.util.UUID;

record CaptureToken(UUID value) {
    static CaptureToken create() {
        return new CaptureToken(UUID.randomUUID());
    }
}
