package io.github.ym0506.routecontract.consumer;

import io.github.ym0506.routecontract.CapturedResult;
import io.github.ym0506.routecontract.RouteAssertions;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteSnapshot;
import org.apache.shardingsphere.driver.api.yaml.YamlShardingSphereDataSourceFactory;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import javax.sql.DataSource;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class PublishedArtifactMySqlTest {

    private static final String SERVICE_DESCRIPTOR =
            "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";
    private static final String PROVIDER_CLASS =
            "io.github.ym0506.routecontract.shardingsphere553.internal."
                    + "RouteContract553SqlExecutionHook";
    private static final String CORE_JAR_NAME =
            System.getProperty("routecontract.coreJarName");
    private static final String ADAPTER_JAR_NAME =
            System.getProperty("routecontract.adapterJarName");
    private static final DockerImageName MYSQL_IMAGE = DockerImageName.parse(
            "mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb")
            .asCompatibleSubstituteFor("mysql");

    @Container
    private static final MySQLContainer<?> MYSQL = new MySQLContainer<>(MYSQL_IMAGE);

    private static DataSource shardingDataSource;

    @BeforeAll
    static void createMySqlFixtureAndShardingSphereDataSource() throws Exception {
        try (Connection connection = physicalConnection();
             Statement statement = connection.createStatement()) {
            statement.executeUpdate("CREATE TABLE t_order_0 ("
                    + "order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, status VARCHAR(32) NOT NULL)");
            statement.executeUpdate("CREATE TABLE t_order_1 ("
                    + "order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, status VARCHAR(32) NOT NULL)");
            statement.executeUpdate(
                    "INSERT INTO t_order_1(order_id, user_id, status) VALUES (201, 3, 'PAID')");
        }

        String yaml = """
                mode:
                  type: Standalone
                dataSources:
                  ds_0:
                    dataSourceClassName: com.zaxxer.hikari.HikariDataSource
                    driverClassName: com.mysql.cj.jdbc.Driver
                    jdbcUrl: 'MYSQL_URL'
                    username: 'MYSQL_USER'
                    password: 'MYSQL_PASSWORD'
                rules:
                  - !SHARDING
                    tables:
                      t_order:
                        actualDataNodes: ds_0.t_order_${0..1}
                        tableStrategy:
                          standard:
                            shardingColumn: user_id
                            shardingAlgorithmName: table_inline
                    shardingAlgorithms:
                      table_inline:
                        type: INLINE
                        props:
                          algorithm-expression: t_order_${user_id % 2}
                          allow-range-query-with-inline-sharding: true
                props:
                  sql-show: false
                  executor-size: 2
                """
                .replace("MYSQL_URL", MYSQL.getJdbcUrl())
                .replace("MYSQL_USER", MYSQL.getUsername())
                .replace("MYSQL_PASSWORD", MYSQL.getPassword());
        shardingDataSource = YamlShardingSphereDataSourceFactory.createDataSource(
                yaml.getBytes(StandardCharsets.UTF_8));
    }

    @AfterAll
    static void closeShardingSphereDataSource() throws Exception {
        if (shardingDataSource instanceof AutoCloseable closeable) {
            closeable.close();
        }
    }

    @Test
    void publishedJarAutoDiscoversSpiAndCapturesOneRealMySqlExecution() throws Exception {
        URL routeContractOrigin = RouteContract.class.getProtectionDomain().getCodeSource().getLocation();
        assertTrue(routeContractOrigin.toExternalForm().endsWith("/" + CORE_JAR_NAME),
                () -> "RouteContract must be loaded from the published core JAR, but was "
                        + routeContractOrigin);

        Class<?> providerClass = Class.forName(
                PROVIDER_CLASS, false, Thread.currentThread().getContextClassLoader());
        URL providerOrigin = providerClass.getProtectionDomain().getCodeSource().getLocation();
        assertTrue(providerOrigin.toExternalForm().endsWith("/" + ADAPTER_JAR_NAME),
                () -> "the hook provider must be loaded from the published adapter JAR, but was "
                        + providerOrigin);

        List<URL> matchingDescriptors = matchingServiceDescriptors();
        assertEquals(1, matchingDescriptors.size(),
                "the published JAR must contribute exactly one RouteContract SPI descriptor");
        assertTrue(matchingDescriptors.get(0).toExternalForm().startsWith("jar:"),
                "the SPI descriptor must come from a JAR resource");
        assertTrue(matchingDescriptors.get(0).toExternalForm().contains(ADAPTER_JAR_NAME),
                "the SPI descriptor must come from the published RouteContract adapter JAR");

        CapturedResult<Long> capture = RouteContract.captureResult(
                "standalone-consumer-find-order",
                PublishedArtifactMySqlTest::countOrderForUserThree);

        assertEquals(1L, capture.value());
        RouteSnapshot snapshot = capture.snapshot();
        RouteAssertions.assertThat(snapshot)
                .hasExactlyObservedPhysicalAttempts(1)
                .observesExactlyDataSourceNames("ds_0")
                .hasCompleteCapture()
                .hasNoReportedExecutionFailures();
        assertEquals(1, snapshot.callbackReturnedCount());
        assertEquals(0, snapshot.callbackFailureCount());
        assertEquals(0, snapshot.unknownOutcomeCount());
        assertFalse(snapshot.attempts().get(0).sqlFingerprint().isBlank());
        assertFalse(snapshot.toString().contains("SELECT"), "raw SQL must not be retained in the snapshot");

        System.out.println("ROUTECONTRACT_STANDALONE artifact=published-jar spi=auto-discovered "
                + "mysql=8.4.11 shardingsphere=5.5.3 observedPhysicalAttempts="
                + snapshot.observedPhysicalAttemptCount() + " observedDataSourceNames="
                + snapshot.observedDataSourceNames());
    }

    private static List<URL> matchingServiceDescriptors() throws Exception {
        Enumeration<URL> descriptors = Thread.currentThread().getContextClassLoader().getResources(SERVICE_DESCRIPTOR);
        List<URL> result = new ArrayList<>();
        while (descriptors.hasMoreElements()) {
            URL descriptor = descriptors.nextElement();
            String content;
            try (var stream = descriptor.openStream()) {
                content = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
            }
            if (content.lines().map(String::trim).anyMatch(PROVIDER_CLASS::equals)) {
                result.add(descriptor);
            }
        }
        return result;
    }

    private static long countOrderForUserThree() throws Exception {
        try (Connection connection = shardingDataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT COUNT(*) FROM t_order WHERE user_id = ?")) {
            statement.setLong(1, 3L);
            try (ResultSet resultSet = statement.executeQuery()) {
                assertTrue(resultSet.next());
                return resultSet.getLong(1);
            }
        }
    }

    private static Connection physicalConnection() throws Exception {
        return DriverManager.getConnection(MYSQL.getJdbcUrl(), MYSQL.getUsername(), MYSQL.getPassword());
    }
}
