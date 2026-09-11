package io.github.ym0506.routecontract.examples.firstproject;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.TearDown;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.TimeUnit;

/** Measures a real prepared query, with the same business assertion in every condition. */
@State(Scope.Benchmark)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
public class ObserverCostBenchmark {
    @Param({"equality", "range"})
    public String query;

    @Param({"absent", "idle", "checked"})
    public String condition;

    private static final List<OrderRepository.Order> EXPECTED =
            List.of(new OrderRepository.Order(201L, 3L, "PAID"));
    private OrderFixture fixture;
    private Operation operation;

    @Setup(Level.Trial)
    public void setUp() throws Exception {
        if (Runtime.version().feature() != 17) {
            throw new IllegalStateException("This experiment requires Java 17");
        }
        boolean expectedPresence = !condition.equals("absent");
        ClassLoader loader = getClass().getClassLoader();
        boolean classPresent = loader.getResource("io/github/ym0506/routecontract/RouteContract.class") != null;
        int providerCount = 0;
        var descriptors = loader.getResources(
                "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook");
        while (descriptors.hasMoreElements()) {
            try (var input = descriptors.nextElement().openStream()) {
                for (String line : new String(input.readAllBytes(), StandardCharsets.UTF_8).split("\\R")) {
                    String provider = line.split("#", 2)[0].strip();
                    if (provider.equals("io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook")) {
                        providerCount++;
                    }
                }
            }
        }
        if (classPresent != expectedPresence || providerCount != (expectedPresence ? 1 : 0)) {
            throw new IllegalStateException("Unexpected RouteContract class/SPI presence: "
                    + condition + "/" + classPresent + "/" + providerCount);
        }
        fixture = new OrderFixture();
        fixture.start();
        var repository = new OrderRepository(fixture.dataSource());
        operation = () -> {
            var rows = repository.findPaidOrders(query);
            if (!EXPECTED.equals(rows)) {
                throw new IllegalStateException("The synthetic business result changed");
            }
            return rows;
        };
        if (condition.equals("checked")) {
            // Keep this class unloaded in the absent classpath. Reflection happens only in setup.
            var wrapper = (CheckedOperationFactory) Class.forName(
                    "io.github.ym0506.routecontract.examples.firstproject.CheckedOperation")
                    .getConstructor().newInstance();
            operation = wrapper.wrap(operation, query.equals("equality") ? 1 : 2);
        }
        operation.run();
        System.out.println("OBSERVER_COST_PREFLIGHT condition=" + condition + " query=" + query
                + " classPresent=" + classPresent + " providerCount=" + providerCount + " business=PASS");
    }

    @Benchmark
    public Object queryAndAssert() throws Exception {
        return operation.run();
    }

    @TearDown(Level.Trial)
    public void tearDown() throws Exception {
        if (fixture != null) {
            fixture.close();
        }
    }

    public interface Operation {
        Object run() throws Exception;
    }

    public interface CheckedOperationFactory {
        Operation wrap(Operation operation, int expectedAttempts);
    }
}
