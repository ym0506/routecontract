package io.github.ym0506.routecontract.example;

import io.github.ym0506.routecontract.AttemptOutcome;
import io.github.ym0506.routecontract.CaptureStatus;
import io.github.ym0506.routecontract.CapturedResult;
import io.github.ym0506.routecontract.PhysicalExecutionAttempt;
import io.github.ym0506.routecontract.RouteAssertions;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteContractViolationException;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.manifest.DataSourceAliases;
import io.github.ym0506.routecontract.manifest.ManifestAssertions;
import io.github.ym0506.routecontract.manifest.ManifestCodec;
import io.github.ym0506.routecontract.manifest.ManifestDiffSeverity;
import io.github.ym0506.routecontract.manifest.ManifestPolicy;
import io.github.ym0506.routecontract.manifest.ManifestVerificationResult;
import io.github.ym0506.routecontract.manifest.ManifestVerifier;
import io.github.ym0506.routecontract.manifest.ObservedExecutionManifest;
import io.github.ym0506.routecontract.manifest.VerificationStatus;
import org.apache.shardingsphere.driver.api.yaml.YamlShardingSphereDataSourceFactory;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import javax.sql.DataSource;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Real MySQL regression corpus for observed ShardingSphere-JDBC execution changes.
 *
 * <p>These assertions deliberately describe only callback-observed physical JDBC attempts,
 * data-source names and SQL fingerprints. They do not infer a complete route plan, physical
 * table count, transaction commit or business success from the hook callbacks.</p>
 */
@Testcontainers
class ObservedExecutionRegressionCorpusMySqlTest {

    private static final Pattern SHA_256 = Pattern.compile("[0-9a-f]{64}");
    private static final DockerImageName MYSQL_IMAGE = DockerImageName.parse(
            "mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb")
            .asCompatibleSubstituteFor("mysql");

    @Container
    private static final MySQLContainer<?> DS_0 = mysql();

    @Container
    private static final MySQLContainer<?> DS_1 = mysql();

    private static DataSource fullStrategyDataSource;
    private static DataSource tableStrategyRemovedDataSource;
    private static DataSource databaseStrategyRemovedDataSource;
    private static DataSource issue38456DataSource;

    @BeforeAll
    static void createPhysicalSchemaAndShardingSphereDataSources() throws Exception {
        initialize(DS_0);
        initialize(DS_1);
        try (Connection ds0 = physicalConnection(DS_0);
             Connection ds1 = physicalConnection(DS_1)) {
            ds0.createStatement().executeUpdate(
                    "INSERT INTO t_order_0(order_id, user_id, status) VALUES (202, 2, 'PAID')");
            ds1.createStatement().executeUpdate(
                    "INSERT INTO t_order_1(order_id, user_id, status) VALUES (201, 3, 'PAID')");
            ds1.createStatement().executeUpdate(
                    "INSERT INTO t_parent(id, order_id) VALUES (3, 3)");
            ds1.createStatement().executeUpdate(
                    "INSERT INTO t_child_3(id, order_id) VALUES (301, 3)");
        }

        fullStrategyDataSource = dataSource(orderRuleYaml(true, true));
        tableStrategyRemovedDataSource = dataSource(orderRuleYaml(true, false));
        databaseStrategyRemovedDataSource = dataSource(orderRuleYaml(false, true));
        issue38456DataSource = dataSource(issue38456Yaml());
    }

    @AfterAll
    static void closeShardingSphereDataSources() throws Exception {
        close(issue38456DataSource);
        close(databaseStrategyRemovedDataSource);
        close(tableStrategyRemovedDataSource);
        close(fullStrategyDataSource);
    }

    @BeforeEach
    void restoreBusinessState() throws Exception {
        resetOrderStatus("PAID");
    }

    @Test
    void equalityAndSafeSyntacticControlsStayOnOneObservedDataSource() throws Exception {
        Map<String, QueryCase> controls = new LinkedHashMap<>();
        controls.put("equality", new QueryCase(
                "SELECT order_id FROM t_order WHERE user_id = ?", List.of(3L)));
        controls.put("single-value-in", new QueryCase(
                "SELECT order_id FROM t_order WHERE user_id IN (?)", List.of(3L)));
        controls.put("additional-filter", new QueryCase(
                "SELECT order_id FROM t_order WHERE user_id = ? AND status = ?", List.of(3L, "PAID")));
        controls.put("predicate-reorder", new QueryCase(
                "SELECT order_id FROM t_order WHERE status = ? AND user_id = ?", List.of("PAID", 3L)));
        controls.put("alias", new QueryCase(
                "SELECT o.order_id FROM t_order o WHERE o.user_id = ?", List.of(3L)));
        controls.put("limit", new QueryCase(
                "SELECT order_id FROM t_order WHERE user_id = ? LIMIT 1", List.of(3L)));

        Map<String, CapturedResult<List<Long>>> observedControls = new LinkedHashMap<>();
        for (Map.Entry<String, QueryCase> entry : controls.entrySet()) {
            String operationId = entry.getKey().equals("additional-filter")
                    || entry.getKey().equals("predicate-reorder")
                    ? "safe-predicate-refactor"
                    : "control-" + entry.getKey();
            CapturedResult<List<Long>> result = captureRows(
                    fullStrategyDataSource, operationId, entry.getValue());
            assertEquals(List.of(201L), result.value(), entry.getKey());
            assertObserved(result.snapshot(), 1, Set.of("ds_1"));
            assertMinimizedEvidence(result.snapshot(), "SELECT", "t_order", "PAID");
            observedControls.put(entry.getKey(), result);
        }

        CapturedResult<List<Long>> additionalFilter = observedControls.get("additional-filter");
        CapturedResult<List<Long>> predicateReorder = observedControls.get("predicate-reorder");
        assertEquals(additionalFilter.value(), predicateReorder.value());
        assertNotEquals(
                fingerprints(additionalFilter.snapshot()),
                fingerprints(predicateReorder.snapshot()),
                "the real engine must produce structural drift before policy sensitivity is asserted");
        assertEquals(2, additionalFilter.snapshot().attempts().get(0).parameterCount());
        assertEquals(2, predicateReorder.snapshot().attempts().get(0).parameterCount());
        assertNotEquals(
                additionalFilter.snapshot().attempts().get(0).parameterTypes(),
                predicateReorder.snapshot().attempts().get(0).parameterTypes(),
                "predicate reordering must change the observed parameter-type order in this real fixture");

        DataSourceAliases aliases = DataSourceAliases.of(Map.of("ds_1", "orders-odd"));
        ManifestPolicy strictPolicy = ManifestPolicy.strict(1, 1);
        ManifestVerificationResult strictVerification = new ManifestVerifier().verify(
                ObservedExecutionManifest.from(additionalFilter.snapshot(), aliases, strictPolicy),
                ObservedExecutionManifest.from(predicateReorder.snapshot(), aliases, strictPolicy));
        assertEquals(VerificationStatus.DRIFT, strictVerification.status());
        assertFalse(strictVerification.passesBlockingChecks());
        assertEquals(
                List.of("RCM301", "RCM302"),
                strictVerification.diffs().stream()
                        .map(diff -> diff.code().stableCode())
                        .sorted()
                        .toList());
        assertTrue(strictVerification.diffs().stream()
                .allMatch(diff -> diff.severity() == ManifestDiffSeverity.BLOCKING));

        ManifestPolicy budgetPolicy = ManifestPolicy.budgetOnly(1, 1);
        ManifestVerificationResult budgetVerification = new ManifestVerifier().verify(
                ObservedExecutionManifest.from(additionalFilter.snapshot(), aliases, budgetPolicy),
                ObservedExecutionManifest.from(predicateReorder.snapshot(), aliases, budgetPolicy));
        assertEquals(VerificationStatus.REVIEW_REQUIRED, budgetVerification.status());
        assertTrue(budgetVerification.passesBlockingChecks());
        assertEquals(
                List.of("RCM301", "RCM302"),
                budgetVerification.diffs().stream()
                        .map(diff -> diff.code().stableCode())
                        .sorted()
                        .toList());
        assertTrue(budgetVerification.diffs().stream()
                .allMatch(diff -> diff.severity() == ManifestDiffSeverity.REVIEW));

        System.out.println("ROUTECONTRACT_POLICY_SENSITIVITY businessResult=UNCHANGED "
                + "observedPhysicalAttempts=1->1 observedDataSourceSet=UNCHANGED "
                + "strictStatus=DRIFT strictBlocking=true "
                + "budgetOnlyStatus=REVIEW_REQUIRED budgetOnlyBlocking=false");
    }

    @Test
    void sameValueRangeAndFalseOtherShardBranchKeepBusinessRowsButExpandObservedExecutions() throws Exception {
        CapturedResult<List<Long>> equality = captureRows(
                fullStrategyDataSource,
                "read-equality-control",
                new QueryCase("SELECT order_id FROM t_order WHERE user_id = ?", List.of(3L)));
        CapturedResult<List<Long>> sameValueRange = captureRows(
                fullStrategyDataSource,
                "read-same-value-range",
                new QueryCase("SELECT order_id FROM t_order WHERE user_id BETWEEN ? AND ?", List.of(3L, 3L)));
        CapturedResult<List<Long>> falseOtherShardBranch = captureRows(
                fullStrategyDataSource,
                "read-false-other-shard-branch",
                new QueryCase(
                        "SELECT order_id FROM t_order WHERE user_id = ? OR (user_id = ? AND 1 = 0)",
                        List.of(3L, 4L)));

        assertEquals(equality.value(), sameValueRange.value());
        assertEquals(equality.value(), falseOtherShardBranch.value());
        assertEquals(List.of(201L), equality.value());
        assertObserved(equality.snapshot(), 1, Set.of("ds_1"));
        assertObserved(sameValueRange.snapshot(), 2, Set.of("ds_0", "ds_1"));
        assertObserved(falseOtherShardBranch.snapshot(), 2, Set.of("ds_0", "ds_1"));

        assertThrows(AssertionError.class, () -> RouteAssertions.assertThat(sameValueRange.snapshot())
                .hasAtMostObservedPhysicalAttempts(1));
        assertThrows(AssertionError.class, () -> RouteAssertions.assertThat(falseOtherShardBranch.snapshot())
                .observesOnlyDataSourceNames("ds_1"));
    }

    @Test
    void equalRangeUpdateChangesOneBusinessRowWhileFourJdbcAttemptsAreObserved() throws Exception {
        CapturedResult<Integer> equality = captureUpdate(
                fullStrategyDataSource,
                "update-equality-control",
                "UPDATE t_order SET status = ? WHERE user_id = ? AND order_id = ?",
                List.of("EQUALITY_UPDATED", 3L, 201L));
        assertEquals(1, equality.value());
        assertEquals("EQUALITY_UPDATED", readPhysicalOrderStatus());
        assertObserved(equality.snapshot(), 1, Set.of("ds_1"));

        resetOrderStatus("PAID");
        CapturedResult<Integer> sameValueRange = captureUpdate(
                fullStrategyDataSource,
                "update-same-value-range",
                "UPDATE t_order SET status = ? WHERE user_id BETWEEN ? AND ? AND order_id = ?",
                List.of("RANGE_UPDATED", 3L, 3L, 201L));
        assertEquals(1, sameValueRange.value());
        assertEquals("RANGE_UPDATED", readPhysicalOrderStatus());
        assertObserved(sameValueRange.snapshot(), 4, Set.of("ds_0", "ds_1"));
        assertMinimizedEvidence(sameValueRange.snapshot(), "UPDATE", "t_order", "RANGE_UPDATED");
    }

    @Test
    void strategyRemovalProducesTwoDifferentObservableRegressionShapes() throws Exception {
        QueryCase equalityQuery = new QueryCase(
                "SELECT order_id FROM t_order WHERE user_id = ?", List.of(3L));
        String operationId = "find-order-by-user-after-strategy-change";
        CapturedResult<List<Long>> baseline = captureRows(
                fullStrategyDataSource, operationId, equalityQuery);
        CapturedResult<List<Long>> withoutTableStrategy = captureRows(
                tableStrategyRemovedDataSource, operationId, equalityQuery);
        CapturedResult<List<Long>> withoutDatabaseStrategy = captureRows(
                databaseStrategyRemovedDataSource, "database-strategy-removed", equalityQuery);

        assertEquals(List.of(201L), baseline.value());
        assertEquals(baseline.value(), withoutTableStrategy.value());
        assertEquals(baseline.value(), withoutDatabaseStrategy.value());

        assertObserved(baseline.snapshot(), 1, Set.of("ds_1"));
        assertObserved(withoutTableStrategy.snapshot(), 1, Set.of("ds_1"));
        assertNotEquals(
                fingerprints(baseline.snapshot()),
                fingerprints(withoutTableStrategy.snapshot()),
                "a one-attempt budget alone must not hide a changed rewritten-SQL fingerprint");
        assertObserved(withoutDatabaseStrategy.snapshot(), 2, Set.of("ds_0", "ds_1"));

        DataSourceAliases aliases = DataSourceAliases.of(Map.of("ds_1", "orders-odd"));
        ManifestPolicy strictPolicy = ManifestPolicy.strict(1, 1);
        ObservedExecutionManifest approved = ObservedExecutionManifest.from(
                baseline.snapshot(), aliases, strictPolicy);
        ObservedExecutionManifest candidate = ObservedExecutionManifest.from(
                withoutTableStrategy.snapshot(), aliases, strictPolicy);
        ManifestCodec codec = new ManifestCodec();
        byte[] approvedBytes = codec.encode(approved);
        byte[] candidateBytes = codec.encode(candidate);
        Path committedExampleDirectory = Path.of(
                System.getProperty("routecontract.repositoryRoot"), "examples", "manifests");
        assertArrayEquals(
                Files.readAllBytes(committedExampleDirectory.resolve(
                        "find-order-by-user-after-strategy-change.approved.json")),
                approvedBytes,
                () -> "checked-in same-budget approved bytes differ from canonical MySQL evidence; actual="
                        + new String(approvedBytes, StandardCharsets.UTF_8));
        assertArrayEquals(
                Files.readAllBytes(committedExampleDirectory.resolve(
                        "find-order-by-user-after-strategy-change.candidate.json")),
                candidateBytes,
                () -> "checked-in same-budget candidate bytes differ from canonical MySQL evidence; actual="
                        + new String(candidateBytes, StandardCharsets.UTF_8));
        ManifestVerificationResult verification = new ManifestVerifier().verify(approved, candidate);

        assertEquals(VerificationStatus.DRIFT, verification.status());
        assertFalse(verification.passesBlockingChecks());
        assertEquals(
                List.of("RCM301", "RCM302"),
                verification.diffs().stream()
                        .map(diff -> diff.code().stableCode())
                        .sorted()
                        .toList(),
                "same-budget fingerprint drift must produce only the stable structural diff codes");
        assertTrue(verification.diffs().stream()
                .allMatch(diff -> diff.severity() == ManifestDiffSeverity.BLOCKING));
        List<String> actualDiff = verification.diffs().stream()
                .map(diff -> diff.code().stableCode() + " " + diff.severity() + " "
                        + diff.code() + ": " + diff.detail())
                .toList();
        assertEquals(
                Files.readAllLines(
                        committedExampleDirectory.resolve(
                                "find-order-by-user-after-strategy-change.expected-diff.txt"),
                        StandardCharsets.UTF_8),
                actualDiff,
                () -> "checked-in same-budget diff differs from verifier output; actual=" + actualDiff);
        assertEquals(
                verification,
                new ManifestVerifier().verify(approved, withoutTableStrategy.snapshot(), aliases),
                "direct snapshot verification must preserve the deterministic manifest result");

        RouteContractViolationException blockingFailure = assertThrows(
                RouteContractViolationException.class,
                () -> ManifestAssertions.assertPassesBlockingChecks(verification));
        assertTrue(blockingFailure.getMessage().contains(
                "RCM301 BLOCKING STRUCTURAL_ATTEMPT_REMOVED"));
        assertTrue(blockingFailure.getMessage().contains(
                "RCM302 BLOCKING STRUCTURAL_ATTEMPT_ADDED"));

        String externallyVisibleEvidence = new String(approvedBytes, StandardCharsets.UTF_8)
                + new String(candidateBytes, StandardCharsets.UTF_8)
                + verification
                + String.join("\n", actualDiff)
                + blockingFailure.getMessage();
        for (String sensitiveText : List.of("SELECT", "t_order", "PAID", "ds_1")) {
            assertFalse(
                    externallyVisibleEvidence.contains(sensitiveText),
                    () -> "manifest CI evidence exposed raw execution data: " + sensitiveText);
        }

        System.out.println("ROUTECONTRACT_FINGERPRINT_DRIFT_DEMO businessResult=UNCHANGED "
                + "observedPhysicalAttempts=1->1 observedDataSourceAliases="
                + "[orders-odd]->[orders-odd] fingerprintMultiset=CHANGED "
                + "parameterTypeShape=[Long]->[Long,Long] "
                + "verificationStatus=DRIFT blockingCodes=[RCM301,RCM302] privacy=MINIMIZED");
    }

    @Test
    void reducedPublicIssue38456PairReturnsSameCountButEightVersusOneAttemptsAreObserved() throws Exception {
        CapturedResult<Long> subquery = captureScalar(
                issue38456DataSource,
                "issue-38456-subquery",
                "SELECT COUNT(t.id) AS num FROM t_parent t "
                        + "WHERE t.id IN (SELECT o.order_id FROM t_child o WHERE o.order_id = ?) "
                        + "AND t.order_id = ?",
                List.of(3L, 3L));
        CapturedResult<Long> join = captureScalar(
                issue38456DataSource,
                "issue-38456-join-control",
                "SELECT COUNT(t.id) AS num FROM t_parent t "
                        + "JOIN t_child o ON t.id = o.order_id "
                        + "WHERE o.order_id = ? AND t.order_id = ?",
                List.of(3L, 3L));

        assertEquals(1L, subquery.value());
        assertEquals(subquery.value(), join.value());
        assertObserved(subquery.snapshot(), 8, Set.of("ds_0", "ds_1"));
        assertObserved(join.snapshot(), 1, Set.of("ds_1"));
        assertThrows(AssertionError.class, () -> RouteAssertions.assertThat(subquery.snapshot())
                .hasAtMostObservedPhysicalAttempts(1));
        assertMinimizedEvidence(subquery.snapshot(), "SELECT", "t_parent", "t_child");
    }

    @Test
    void builtInShardingConditionsAuditIsActiveButDoesNotRejectTheRecordedRiskCases() throws Exception {
        SQLException rejected = assertThrows(SQLException.class, () -> executeRows(
                fullStrategyDataSource,
                "SELECT order_id FROM t_order WHERE order_id = ?",
                List.of(201L)));
        assertTrue(rejected.getMessage().contains("without sharding conditions"));

        CapturedResult<List<Long>> sameValueRange = captureRows(
                fullStrategyDataSource,
                "audit-allows-same-value-range",
                new QueryCase("SELECT order_id FROM t_order WHERE user_id BETWEEN ? AND ?", List.of(3L, 3L)));
        CapturedResult<List<Long>> falseOtherShardBranch = captureRows(
                fullStrategyDataSource,
                "audit-allows-false-other-shard-branch",
                new QueryCase(
                        "SELECT order_id FROM t_order WHERE user_id = ? OR (user_id = ? AND 1 = 0)",
                        List.of(3L, 4L)));
        CapturedResult<Integer> sameValueRangeUpdate = captureUpdate(
                fullStrategyDataSource,
                "audit-allows-same-value-range-update",
                "UPDATE t_order SET status = ? WHERE user_id BETWEEN ? AND ? AND order_id = ?",
                List.of("AUDIT_ALLOWED", 3L, 3L, 201L));

        assertEquals(List.of(201L), sameValueRange.value());
        assertEquals(List.of(201L), falseOtherShardBranch.value());
        assertEquals(1, sameValueRangeUpdate.value());
        assertObserved(sameValueRange.snapshot(), 2, Set.of("ds_0", "ds_1"));
        assertObserved(falseOtherShardBranch.snapshot(), 2, Set.of("ds_0", "ds_1"));
        assertObserved(sameValueRangeUpdate.snapshot(), 4, Set.of("ds_0", "ds_1"));
    }

    @Test
    void allCorpusStructuralSignaturesRemainDeterministicAcrossTwentyRepetitions() throws Exception {
        Map<String, Set<String>> signaturesByCase = new LinkedHashMap<>();
        for (String caseName : List.of(
                "equality", "same-value-range", "false-other-shard", "range-update",
                "table-strategy-removed", "database-strategy-removed", "issue-subquery", "issue-join")) {
            signaturesByCase.put(caseName, new HashSet<>());
        }

        for (int repetition = 0; repetition < 20; repetition++) {
            CapturedResult<List<Long>> equality = captureRows(
                    fullStrategyDataSource,
                    "repeat-equality-" + repetition,
                    new QueryCase("SELECT order_id FROM t_order WHERE user_id = ?", List.of(3L)));
            CapturedResult<List<Long>> sameValueRange = captureRows(
                    fullStrategyDataSource,
                    "repeat-range-" + repetition,
                    new QueryCase("SELECT order_id FROM t_order WHERE user_id BETWEEN ? AND ?", List.of(3L, 3L)));
            CapturedResult<List<Long>> falseOtherShard = captureRows(
                    fullStrategyDataSource,
                    "repeat-false-other-shard-" + repetition,
                    new QueryCase(
                            "SELECT order_id FROM t_order WHERE user_id = ? OR (user_id = ? AND 1 = 0)",
                            List.of(3L, 4L)));

            resetOrderStatus("PAID");
            CapturedResult<Integer> rangeUpdate = captureUpdate(
                    fullStrategyDataSource,
                    "repeat-range-update-" + repetition,
                    "UPDATE t_order SET status = ? WHERE user_id BETWEEN ? AND ? AND order_id = ?",
                    List.of("REPEAT_UPDATED", 3L, 3L, 201L));

            QueryCase equalityQuery = new QueryCase(
                    "SELECT order_id FROM t_order WHERE user_id = ?", List.of(3L));
            CapturedResult<List<Long>> tableStrategyRemoved = captureRows(
                    tableStrategyRemovedDataSource,
                    "repeat-table-strategy-removed-" + repetition,
                    equalityQuery);
            CapturedResult<List<Long>> databaseStrategyRemoved = captureRows(
                    databaseStrategyRemovedDataSource,
                    "repeat-database-strategy-removed-" + repetition,
                    equalityQuery);
            CapturedResult<Long> issueSubquery = captureScalar(
                    issue38456DataSource,
                    "repeat-issue-subquery-" + repetition,
                    "SELECT COUNT(t.id) AS num FROM t_parent t "
                            + "WHERE t.id IN (SELECT o.order_id FROM t_child o WHERE o.order_id = ?) "
                            + "AND t.order_id = ?",
                    List.of(3L, 3L));
            CapturedResult<Long> issueJoin = captureScalar(
                    issue38456DataSource,
                    "repeat-issue-join-" + repetition,
                    "SELECT COUNT(t.id) AS num FROM t_parent t "
                            + "JOIN t_child o ON t.id = o.order_id "
                            + "WHERE o.order_id = ? AND t.order_id = ?",
                    List.of(3L, 3L));

            assertEquals(List.of(201L), equality.value());
            assertEquals(equality.value(), sameValueRange.value());
            assertEquals(equality.value(), falseOtherShard.value());
            assertEquals(1, rangeUpdate.value());
            assertEquals(equality.value(), tableStrategyRemoved.value());
            assertEquals(equality.value(), databaseStrategyRemoved.value());
            assertEquals(1L, issueSubquery.value());
            assertEquals(issueSubquery.value(), issueJoin.value());

            assertObserved(equality.snapshot(), 1, Set.of("ds_1"));
            assertObserved(sameValueRange.snapshot(), 2, Set.of("ds_0", "ds_1"));
            assertObserved(falseOtherShard.snapshot(), 2, Set.of("ds_0", "ds_1"));
            assertObserved(rangeUpdate.snapshot(), 4, Set.of("ds_0", "ds_1"));
            assertObserved(tableStrategyRemoved.snapshot(), 1, Set.of("ds_1"));
            assertObserved(databaseStrategyRemoved.snapshot(), 2, Set.of("ds_0", "ds_1"));
            assertObserved(issueSubquery.snapshot(), 8, Set.of("ds_0", "ds_1"));
            assertObserved(issueJoin.snapshot(), 1, Set.of("ds_1"));

            recordSignature(signaturesByCase, "equality", equality.snapshot());
            recordSignature(signaturesByCase, "same-value-range", sameValueRange.snapshot());
            recordSignature(signaturesByCase, "false-other-shard", falseOtherShard.snapshot());
            recordSignature(signaturesByCase, "range-update", rangeUpdate.snapshot());
            recordSignature(signaturesByCase, "table-strategy-removed", tableStrategyRemoved.snapshot());
            recordSignature(signaturesByCase, "database-strategy-removed", databaseStrategyRemoved.snapshot());
            recordSignature(signaturesByCase, "issue-subquery", issueSubquery.snapshot());
            recordSignature(signaturesByCase, "issue-join", issueJoin.snapshot());
        }

        signaturesByCase.forEach((caseName, signatures) -> assertEquals(
                1,
                signatures.size(),
                () -> caseName + " produced non-deterministic structural signatures: " + signatures));
        System.out.println("ROUTECONTRACT_CORPUS repetitions=20 cases=8 uniqueSignaturesPerCase=1");
    }

    private static void recordSignature(
            final Map<String, Set<String>> signaturesByCase,
            final String caseName,
            final RouteSnapshot snapshot) {
        signaturesByCase.get(caseName).add(structuralSignature(snapshot));
    }

    private static String structuralSignature(final RouteSnapshot snapshot) {
        String attempts = snapshot.attempts().stream()
                .map(ObservedExecutionRegressionCorpusMySqlTest::structuralAttempt)
                .sorted()
                .collect(Collectors.joining(";"));
        return snapshot.status()
                + "|attempts=" + snapshot.observedPhysicalAttemptCount()
                + "|sources=" + new TreeSet<>(snapshot.observedDataSourceNames())
                + "|evidence=" + attempts;
    }

    private static String structuralAttempt(final PhysicalExecutionAttempt attempt) {
        return attempt.observedDataSourceName()
                + "|" + attempt.sqlFingerprint()
                + "|" + attempt.parameterCount()
                + "|" + attempt.parameterTypes()
                + "|" + attempt.outcome()
                + "|" + attempt.reportedFailureType();
    }

    private static Set<String> fingerprints(final RouteSnapshot snapshot) {
        return snapshot.attempts().stream()
                .map(PhysicalExecutionAttempt::sqlFingerprint)
                .collect(Collectors.toSet());
    }

    private static void assertObserved(
            final RouteSnapshot snapshot,
            final int expectedAttempts,
            final Set<String> expectedDataSourceNames) {
        assertEquals(CaptureStatus.COMPLETE, snapshot.status(), () -> "snapshot=" + snapshot);
        assertEquals(expectedAttempts, snapshot.observedPhysicalAttemptCount(), () -> "snapshot=" + snapshot);
        assertEquals(expectedDataSourceNames, Set.copyOf(snapshot.observedDataSourceNames()));
        assertEquals(expectedAttempts, snapshot.callbackReturnedCount());
        assertEquals(0, snapshot.callbackFailureCount());
        assertEquals(0, snapshot.unknownOutcomeCount());
        assertTrue(snapshot.collectorDiagnostics().isEmpty());
        assertTrue(snapshot.attempts().stream()
                .allMatch(attempt -> attempt.outcome() == AttemptOutcome.CALLBACK_RETURNED));
        RouteAssertions.assertThat(snapshot)
                .hasExactlyObservedPhysicalAttempts(expectedAttempts)
                .observesExactlyDataSourceNames(expectedDataSourceNames.toArray(String[]::new))
                .hasCompleteCapture()
                .hasNoReportedExecutionFailures();
    }

    private static void assertMinimizedEvidence(final RouteSnapshot snapshot, final String... forbiddenText) {
        String rendered = snapshot.toString();
        for (String forbidden : forbiddenText) {
            assertFalse(rendered.contains(forbidden), () -> "snapshot persisted forbidden text: " + forbidden);
        }
        assertTrue(snapshot.attempts().stream()
                .allMatch(attempt -> SHA_256.matcher(attempt.sqlFingerprint()).matches()));
    }

    private static CapturedResult<List<Long>> captureRows(
            final DataSource dataSource,
            final String operationId,
            final QueryCase query) throws Exception {
        return RouteContract.captureResult(
                operationId,
                () -> executeRows(dataSource, query.sql(), query.parameters()));
    }

    private static CapturedResult<Long> captureScalar(
            final DataSource dataSource,
            final String operationId,
            final String sql,
            final List<Object> parameters) throws Exception {
        return RouteContract.captureResult(operationId, () -> {
            try (Connection connection = dataSource.getConnection();
                 PreparedStatement statement = connection.prepareStatement(sql)) {
                bind(statement, parameters);
                try (ResultSet resultSet = statement.executeQuery()) {
                    assertTrue(resultSet.next());
                    long result = resultSet.getLong(1);
                    assertFalse(resultSet.next());
                    return result;
                }
            }
        });
    }

    private static CapturedResult<Integer> captureUpdate(
            final DataSource dataSource,
            final String operationId,
            final String sql,
            final List<Object> parameters) throws Exception {
        return RouteContract.captureResult(operationId, () -> {
            try (Connection connection = dataSource.getConnection();
                 PreparedStatement statement = connection.prepareStatement(sql)) {
                bind(statement, parameters);
                return statement.executeUpdate();
            }
        });
    }

    private static List<Long> executeRows(
            final DataSource dataSource,
            final String sql,
            final List<Object> parameters) throws Exception {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            bind(statement, parameters);
            List<Long> result = new ArrayList<>();
            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    result.add(resultSet.getLong(1));
                }
            }
            return result;
        }
    }

    private static void bind(final PreparedStatement statement, final List<Object> parameters) throws SQLException {
        for (int index = 0; index < parameters.size(); index++) {
            statement.setObject(index + 1, parameters.get(index));
        }
    }

    private static void resetOrderStatus(final String status) throws Exception {
        try (Connection connection = physicalConnection(DS_1);
             PreparedStatement statement = connection.prepareStatement(
                     "UPDATE t_order_1 SET status = ? WHERE order_id = 201")) {
            statement.setString(1, status);
            assertEquals(1, statement.executeUpdate());
        }
    }

    private static String readPhysicalOrderStatus() throws Exception {
        try (Connection connection = physicalConnection(DS_1);
             ResultSet resultSet = connection.createStatement().executeQuery(
                     "SELECT status FROM t_order_1 WHERE order_id = 201")) {
            assertTrue(resultSet.next());
            String result = resultSet.getString(1);
            assertFalse(resultSet.next());
            return result;
        }
    }

    private static DataSource dataSource(final String yaml) throws IOException, SQLException {
        return YamlShardingSphereDataSourceFactory.createDataSource(yaml.getBytes(StandardCharsets.UTF_8));
    }

    private static String orderRuleYaml(final boolean databaseStrategy, final boolean tableStrategy) {
        String databaseBlock = databaseStrategy ? """
                        databaseStrategy:
                          standard:
                            shardingColumn: user_id
                            shardingAlgorithmName: database_inline
                """ : "";
        String tableBlock = tableStrategy ? """
                        tableStrategy:
                          standard:
                            shardingColumn: user_id
                            shardingAlgorithmName: table_inline
                """ : "";
        return dataSourceYaml() + """
                rules:
                  - !SHARDING
                    tables:
                      t_order:
                        actualDataNodes: ds_${0..1}.t_order_${0..1}
                        auditStrategy:
                          auditorNames:
                            - sharding_key_required_auditor
                          allowHintDisable: false
                """ + databaseBlock + tableBlock + """
                    shardingAlgorithms:
                      database_inline:
                        type: INLINE
                        props:
                          algorithm-expression: ds_${user_id % 2}
                          allow-range-query-with-inline-sharding: true
                      table_inline:
                        type: INLINE
                        props:
                          algorithm-expression: t_order_${user_id % 2}
                          allow-range-query-with-inline-sharding: true
                    auditors:
                      sharding_key_required_auditor:
                        type: DML_SHARDING_CONDITIONS
                props:
                  sql-show: false
                  executor-size: 8
                """;
    }

    private static String issue38456Yaml() {
        return dataSourceYaml() + """
                rules:
                  - !SHARDING
                    tables:
                      t_parent:
                        actualDataNodes: ds_${0..1}.t_parent
                        databaseStrategy:
                          standard:
                            shardingColumn: order_id
                            shardingAlgorithmName: database_inline_order
                        auditStrategy:
                          auditorNames:
                            - sharding_key_required_auditor
                          allowHintDisable: false
                      t_child:
                        actualDataNodes: ds_${0..1}.t_child_${0..3}
                        databaseStrategy:
                          standard:
                            shardingColumn: order_id
                            shardingAlgorithmName: database_inline_order
                        tableStrategy:
                          standard:
                            shardingColumn: order_id
                            shardingAlgorithmName: table_inline_order
                        auditStrategy:
                          auditorNames:
                            - sharding_key_required_auditor
                          allowHintDisable: false
                    shardingAlgorithms:
                      database_inline_order:
                        type: INLINE
                        props:
                          algorithm-expression: ds_${order_id % 2}
                      table_inline_order:
                        type: INLINE
                        props:
                          algorithm-expression: t_child_${order_id % 4}
                    auditors:
                      sharding_key_required_auditor:
                        type: DML_SHARDING_CONDITIONS
                props:
                  sql-show: false
                  executor-size: 8
                """;
    }

    private static String dataSourceYaml() {
        return """
                mode:
                  type: Standalone
                dataSources:
                  ds_0:
                    dataSourceClassName: com.zaxxer.hikari.HikariDataSource
                    driverClassName: com.mysql.cj.jdbc.Driver
                    jdbcUrl: 'DS0_URL'
                    username: 'DS0_USER'
                    password: 'DS0_PASSWORD'
                  ds_1:
                    dataSourceClassName: com.zaxxer.hikari.HikariDataSource
                    driverClassName: com.mysql.cj.jdbc.Driver
                    jdbcUrl: 'DS1_URL'
                    username: 'DS1_USER'
                    password: 'DS1_PASSWORD'
                """
                .replace("DS0_URL", DS_0.getJdbcUrl())
                .replace("DS0_USER", DS_0.getUsername())
                .replace("DS0_PASSWORD", DS_0.getPassword())
                .replace("DS1_URL", DS_1.getJdbcUrl())
                .replace("DS1_USER", DS_1.getUsername())
                .replace("DS1_PASSWORD", DS_1.getPassword());
    }

    private static void close(final DataSource dataSource) throws Exception {
        if (dataSource instanceof AutoCloseable closeable) {
            closeable.close();
        }
    }

    private static MySQLContainer<?> mysql() {
        return new MySQLContainer<>(MYSQL_IMAGE)
                .withDatabaseName("routecontract")
                .withUsername("routecontract")
                .withPassword("routecontract");
    }

    private static Connection physicalConnection(final MySQLContainer<?> container) throws SQLException {
        return DriverManager.getConnection(container.getJdbcUrl(), container.getUsername(), container.getPassword());
    }

    private static void initialize(final MySQLContainer<?> container) throws Exception {
        try (Connection connection = physicalConnection(container);
             Statement statement = connection.createStatement()) {
            statement.execute("CREATE TABLE t_order_0 ("
                    + "order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
            statement.execute("CREATE TABLE t_order_1 ("
                    + "order_id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL, status VARCHAR(64) NOT NULL)");
            statement.execute("CREATE TABLE t_parent (id BIGINT PRIMARY KEY, order_id BIGINT NOT NULL)");
            statement.execute("CREATE TABLE t_child_0 (id BIGINT PRIMARY KEY, order_id BIGINT NOT NULL)");
            statement.execute("CREATE TABLE t_child_1 (id BIGINT PRIMARY KEY, order_id BIGINT NOT NULL)");
            statement.execute("CREATE TABLE t_child_2 (id BIGINT PRIMARY KEY, order_id BIGINT NOT NULL)");
            statement.execute("CREATE TABLE t_child_3 (id BIGINT PRIMARY KEY, order_id BIGINT NOT NULL)");
        }
    }

    private record QueryCase(String sql, List<Object> parameters) {
        private QueryCase {
            parameters = List.copyOf(parameters);
        }
    }
}
