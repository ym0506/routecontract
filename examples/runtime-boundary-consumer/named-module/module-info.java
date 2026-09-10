module io.github.ym0506.routecontract.consumer.runtimeboundary {
    requires transitive java.sql;
    requires transitive java.logging;
    requires io.github.ym0506.routecontract.core;

    // Hikari on the unnamed third-party graph constructs the public nested JDBC driver reflectively.
    exports io.github.ym0506.routecontract.consumer;
}
