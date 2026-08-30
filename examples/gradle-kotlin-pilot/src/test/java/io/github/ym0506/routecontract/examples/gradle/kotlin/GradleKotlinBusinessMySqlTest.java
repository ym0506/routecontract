package io.github.ym0506.routecontract.examples.gradle.kotlin;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Enumeration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GradleKotlinBusinessMySqlTest {

    private static final String SERVICE_DESCRIPTOR =
            "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";
    private static final String PROVIDER_CLASS =
            "io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook";

    private static MySqlShardingFixture fixture;
    private static OrderQueryService orderQueryService;

    @BeforeAll
    static void startFixture() throws Exception {
        fixture = new MySqlShardingFixture();
        orderQueryService = new OrderQueryService(fixture.start());
    }

    @AfterAll
    static void stopFixture() throws Exception {
        fixture.close();
    }

    @Test
    void existingBusinessAssertionPassesWithoutRouteContract() throws Exception {
        ClassLoader classLoader = Thread.currentThread().getContextClassLoader();
        assertThrows(ClassNotFoundException.class, () -> Class.forName(
                "io.github.ym0506.routecontract.RouteContract", false, classLoader));
        Enumeration<URL> descriptors = classLoader.getResources(SERVICE_DESCRIPTOR);
        while (descriptors.hasMoreElements()) {
            URL descriptor = descriptors.nextElement();
            String content;
            try (var stream = descriptor.openStream()) {
                content = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
            }
            assertFalse(content.lines().map(String::trim).anyMatch(PROVIDER_CLASS::equals),
                    () -> "RouteContract provider must be absent from the profile-off graph: "
                            + descriptor);
        }

        Path projectDir = Path.of(System.getProperty("routecontract.projectDir"))
                .toAbsolutePath().normalize();
        Path candidatePath = projectDir.resolve(
                "build/routecontract/orders.find-by-user-id.candidate.json");
        assertFalse(Files.exists(candidatePath) || Files.isSymbolicLink(candidatePath),
                "the profile-off build must not create a RouteContract candidate");

        assertEquals(1L, orderQueryService.countByUserId(3L));
        System.out.println("ROUTECONTRACT_GRADLE_KOTLIN_PROFILE_OFF businessResult=PASS "
                + "routecontractDependency=ABSENT mysql=8.4.11 shardingsphere=5.5.3");
    }
}
