package io.github.ym0506.routecontract.examples.firstproject;

import io.github.ym0506.routecontract.RouteAssertions;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.manifest.DataSourceAliases;
import io.github.ym0506.routecontract.manifest.ManifestAssertions;
import io.github.ym0506.routecontract.manifest.ManifestPolicy;
import io.github.ym0506.routecontract.manifest.ManifestReviewReport;
import io.github.ym0506.routecontract.manifest.ManifestStore;
import io.github.ym0506.routecontract.manifest.ObservedExecutionManifest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderContractTest {
    private static final String OPERATION = "find-paid-orders-by-user";
    private static final ManifestPolicy PROPOSED_POLICY = ManifestPolicy.strict(1, 1);
    private static final DataSourceAliases ALIASES = DataSourceAliases.of(Map.of(
            "ds_0", "orders-even", "ds_1", "orders-odd"));
    private static final Path OUTPUT = Path.of("build/routecontract").toAbsolutePath().normalize();
    private static final Path CANDIDATE = OUTPUT.resolve("candidate.json");
    private static final Path MARKDOWN = OUTPUT.resolve("review.md");
    private static final Path JSON = OUTPUT.resolve("review.json");
    private static OrderFixture fixture;
    private static String mode;
    private static String query;
    private static Path baseline;

    @BeforeAll
    static void setUp() throws Exception {
        baseline = Path.of(System.getProperty("routecontract.baseline",
                "baselines/find-paid-orders-by-user.approved.json")).toAbsolutePath().normalize();
        // Protect the selected baseline even if someone points it at a generated output file.
        if (baseline.startsWith(OUTPUT)) {
            throw new IllegalArgumentException("Keep routecontract.baseline outside build/routecontract");
        }
        for (Path output : List.of(CANDIDATE, MARKDOWN, JSON)) {
            if (Files.exists(baseline) && Files.exists(output) && Files.isSameFile(baseline, output)) {
                throw new IllegalArgumentException("The baseline must not alias a generated output");
            }
            Files.deleteIfExists(output);
        }
        if (Runtime.version().feature() != 17) {
            throw new IllegalArgumentException("Use a Java 17 JDK for this ShardingSphere-JDBC 5.5.3 example");
        }
        mode = option("routecontract.mode", "check", List.of("capture", "check"));
        query = option("routecontract.query", "equality", List.of("equality", "range"));
        fixture = new OrderFixture();
        fixture.start();
    }

    @AfterAll
    static void tearDown() throws Exception {
        if (fixture != null) {
            fixture.close();
        }
    }

    @Test
    void paidOrdersKeepTheirBusinessResultAndExecutionContract() throws Exception {
        OrderRepository orders = new OrderRepository(fixture.dataSource());
        var captured = RouteContract.captureResult(OPERATION, () -> orders.findPaidOrders(query));

        // Keep the application's business assertion independent of hook outcomes.
        assertEquals(List.of(new OrderRepository.Order(201L, 3L, "PAID")), captured.value());
        System.out.println("Business assertion passed: the exact expected order was returned.");

        ManifestStore store = new ManifestStore();
        var approved = mode.equals("check") && Files.exists(baseline) ? store.read(baseline) : null;
        var policy = approved == null ? PROPOSED_POLICY : approved.policy();
        var candidate = ObservedExecutionManifest.from(captured.snapshot(), ALIASES, policy);
        store.writeCandidate(baseline, CANDIDATE, candidate);
        System.out.println("Candidate: build/routecontract/candidate.json; physical JDBC execution attempts="
                + candidate.counts().observedPhysicalAttemptCount());

        if (mode.equals("capture")) {
            RouteAssertions.assertThat(captured.snapshot())
                    .hasAtMostObservedPhysicalAttempts(policy.maxObservedPhysicalAttempts())
                    .hasAtMostDistinctObservedDataSourceNames(policy.maxDistinctObservedDataSourceNames())
                    .hasNoReportedExecutionFailures();
            System.out.println("CAPTURED: inspect the candidate and proposed budgets. No baseline was approved.");
            return;
        }
        if (approved == null) {
            throw new IllegalStateException("No approved baseline. Candidate was preserved; review it, then have "
                    + "your project's authorized maintainer establish routecontract.baseline before checking.");
        }
        ManifestReviewReport report = ManifestReviewReport.compare(approved, candidate);
        Files.writeString(MARKDOWN, report.toMarkdown());
        Files.writeString(JSON, report.toJson());
        System.out.println(report.verification().status() + ": see build/routecontract/review.md and review.json");
        // Write both reports before failing the ordinary test/CI build.
        ManifestAssertions.assertMatched(report.verification());
    }

    private static String option(String name, String defaultValue, List<String> allowed) {
        String value = System.getProperty(name, defaultValue);
        if (!allowed.contains(value)) {
            throw new IllegalArgumentException(name + " must be one of " + allowed + "; received: " + value);
        }
        return value;
    }
}
