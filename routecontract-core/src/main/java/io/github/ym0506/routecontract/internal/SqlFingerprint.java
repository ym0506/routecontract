package io.github.ym0506.routecontract.internal;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

final class SqlFingerprint {

    private SqlFingerprint() {
    }

    static String sha256(final String sql) {
        String exactSql = sql == null ? "<null-sql>" : sql;
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(exactSql.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }
}
