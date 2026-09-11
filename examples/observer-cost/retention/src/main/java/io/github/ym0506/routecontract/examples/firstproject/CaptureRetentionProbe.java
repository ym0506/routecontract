package io.github.ym0506.routecontract.examples.firstproject;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.github.ym0506.routecontract.CapturedResult;
import io.github.ym0506.routecontract.RouteAssertions;
import io.github.ym0506.routecontract.RouteContract;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/** Quiescent live-object checkpoints, with reusable callers and explicit retained-result controls. */
public final class CaptureRetentionProbe {
    private static final String PUBLIC_SHA256 =
            "9e883e618eb09d9ecf30814151bb4b0a43eba02c78d288cc582fa7e57e6edba2";
    private static final List<OrderRepository.Order> EXPECTED =
            List.of(new OrderRepository.Order(201L, 3L, "PAID"));
    private static final List<Object> RETAINED = new ArrayList<>();
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final BufferedReader INPUT =
            new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));

    private CaptureRetentionProbe() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !(args[0].equals("smoke") || args[0].equals("full"))) {
            throw new IllegalArgumentException("Expected smoke or full");
        }
        if (Runtime.version().feature() != 17) {
            throw new IllegalStateException("Select Java 17");
        }
        Path jar = Path.of(RouteContract.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        String jarHash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(jar)));
        if (!PUBLIC_SHA256.equals(jarHash)) {
            throw new IllegalStateException("Expected the immutable public 0.1.3 JAR");
        }
        // Preflight inside capture independently validates exact middleware and SPI activation.
        boolean smoke = args[0].equals("smoke");
        int blocks = smoke ? 2 : 10;
        int perCaller = smoke ? 40 : 2500;
        int warmupPerCaller = smoke ? 20 : 250;
        var callers = Executors.newFixedThreadPool(4);
        var fixture = new OrderFixture();
        try {
            fixture.start();
            var repository = new OrderRepository(fixture.dataSource());
            seedRetainedResults(repository);
            checkpoint("held", 0, 0, 0, 0, 0, jarHash);
            RETAINED.clear();
            checkpoint("released", 0, 0, 0, 0, 0, jarHash);
            runBlock(callers, repository, warmupPerCaller, -1);
            checkpoint("warmup", 0, 0, 0, 0, 0, jarHash);
            long completed = 0;
            long successful = 0;
            long exceptions = 0;
            long errors = 0;
            long nanos = 0;
            for (int block = 1; block <= blocks; block++) {
                long started = System.nanoTime();
                long[] counts = runBlock(callers, repository, perCaller, block);
                nanos += System.nanoTime() - started;
                successful += counts[0];
                exceptions += counts[1];
                errors += counts[2];
                completed += (long) perCaller * 4;
                checkpoint("block-" + block, completed, successful, exceptions, errors, nanos, jarHash);
            }
            emit(Map.of("event", "complete", "operations", completed, "mode", args[0]));
        } finally {
            RETAINED.clear();
            try {
                callers.shutdownNow();
                if (!callers.awaitTermination(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Caller threads did not stop");
                }
            } finally {
                fixture.close();
            }
        }
    }

    private static void seedRetainedResults(OrderRepository repository) throws Exception {
        for (int i = 0; i < 16; i++) {
            String query = i % 2 == 0 ? "equality" : "range";
            var result = RouteContract.captureResult("retained-control-" + i, () -> checkedRows(repository, query));
            assertCapture(result, query);
            RETAINED.add(result);
        }
    }

    private static long[] runBlock(java.util.concurrent.ExecutorService callers,
                                   OrderRepository repository, int perCaller, int block) throws Exception {
        var tasks = new ArrayList<Callable<long[]>>();
        for (int caller = 0; caller < 4; caller++) {
            int callerId = caller;
            tasks.add(() -> {
                long[] counts = new long[3];
                for (int index = 0; index < perCaller; index++) {
                    counts[runOne(repository, callerId, block, index)]++;
                }
                return counts;
            });
        }
        long[] total = new long[3];
        // Future results contain primitive counters only; no snapshot/exception survives the tasks.
        for (var task : callers.invokeAll(tasks, 180, TimeUnit.SECONDS)) {
            long[] counts = task.get();
            for (int i = 0; i < counts.length; i++) {
                total[i] += counts[i];
            }
        }
        return total;
    }

    private static int runOne(OrderRepository repository, int caller, int block, int index) throws Exception {
        String query = index % 2 == 0 ? "equality" : "range";
        int kind = index % 20 == 18 ? 1 : index % 20 == 19 ? 2 : 0;
        Throwable expected = kind == 1 ? new ExpectedException() : kind == 2 ? new ExpectedError() : null;
        String operation = "retention-" + caller + "-" + block + "-" + index;
        try {
            var result = RouteContract.captureResult(operation, () -> {
                var rows = checkedRows(repository, query);
                if (expected instanceof ExpectedException exception) {
                    throw exception;
                }
                if (expected instanceof ExpectedError error) {
                    throw error;
                }
                return rows;
            });
            if (expected != null || !operation.equals(result.snapshot().operationId())) {
                throw new AssertionError("Exception propagation or operation identity changed");
            }
            assertCapture(result, query);
        } catch (ExpectedException | ExpectedError actual) {
            if (actual != expected) {
                throw new AssertionError("The original thrown object was not preserved");
            }
        }
        return kind;
    }

    private static List<OrderRepository.Order> checkedRows(OrderRepository repository, String query) throws Exception {
        var rows = repository.findPaidOrders(query);
        if (!EXPECTED.equals(rows)) {
            throw new AssertionError("The exact synthetic business result changed");
        }
        return rows;
    }

    private static void assertCapture(CapturedResult<?> result, String query) {
        RouteAssertions.assertThat(result.snapshot()).hasCompleteCapture().hasNoReportedExecutionFailures()
                .hasExactlyObservedPhysicalAttempts(query.equals("equality") ? 1 : 2)
                .observesExactlyDataSourceNames(query.equals("equality") ? new String[]{"ds_1"}
                        : new String[]{"ds_0", "ds_1"});
    }

    private static void checkpoint(String phase, long operations, long successes, long exceptions,
                                   long errors, long nanos, String jarHash) throws Exception {
        emit(Map.of("event", "checkpoint", "phase", phase, "operations", operations,
                "successes", successes, "exceptions", exceptions, "errors", errors,
                "workloadNanos", nanos, "java", Runtime.version().toString(), "publicJarSha256", jarHash));
        if (!"continue".equals(INPUT.readLine())) {
            throw new IllegalStateException("Missing checkpoint acknowledgement");
        }
    }

    private static void emit(Map<String, ?> event) throws Exception {
        System.out.println("RETENTION_JSON " + JSON.writeValueAsString(event));
        System.out.flush();
    }

    private static final class ExpectedException extends Exception {
    }

    private static final class ExpectedError extends Error {
    }
}
