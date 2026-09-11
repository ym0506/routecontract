package io.github.ym0506.routecontract.examples.buildshape;

import org.junit.jupiter.api.Test;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DefaultTargetGraphIsolationTest {
    @Test
    void leavesRouteContractOutOfTheTargetRuntime() {
        assertEquals(21, Runtime.version().feature());
        assertEquals("gradle95-build-shape", BuildShapeApplication.lane());
        assertThrows(
                ClassNotFoundException.class,
                () -> Class.forName("io.github.ym0506.routecontract.RouteContract"));
        String expectedBootBom = System.getProperty("routecontract.expectedBootBom");
        assertTrue(
                Set.of("3.5.16", "4.1.0").contains(expectedBootBom),
                "the target graph must use one exact reviewed Spring Boot BOM cell");
    }
}
