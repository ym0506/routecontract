package io.github.ym0506.routecontract.manifest;

import java.io.IOException;
import java.io.Serial;

/** Indicates malformed, ambiguous, or internally inconsistent manifest JSON. */
public final class ManifestFormatException extends IOException {
    @Serial
    private static final long serialVersionUID = 1L;

    /**
     * Creates a format exception with a validation message.
     *
     * @param message validation failure description
     */
    public ManifestFormatException(final String message) {
        super(message);
    }

    /**
     * Creates a format exception with its underlying parser or invariant failure.
     *
     * @param message validation failure description
     * @param cause underlying failure
     */
    public ManifestFormatException(final String message, final Throwable cause) {
        super(message, cause);
    }
}
