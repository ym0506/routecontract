# Why RouteContract checks the execution behind a result

[한국어](design-decisions.ko.md) · [Run one example](first-project.md) · [Architecture](architecture.md) · [API reference](reference-guide.md)

An order lookup can return the right order after a query change starts visiting an extra database.
It can also visit a different database while returning the same row with the same execution count.
The application result and the execution expectation answer different questions. Keep both checks.

This guide explains **released 0.1.4**, for **Java 17 or 21 and exact ShardingSphere-JDBC 5.5.3**.
Each decision links to implementation and a way to inspect its limits. The separate
[0.2 core/adapter work](https://github.com/ym0506/routecontract/pull/62) is unreleased.

## Start with the requirement, then choose the check

| The operation must… | Check… | What this does not establish |
| --- | --- | --- |
| Return the expected order | Your existing result assertion | Which databases were visited |
| Stay within an agreed amount of execution | Attempt and distinct-data-source limits | Response time or server count |
| Use a particular configured destination | Expected data-source names or reviewed aliases | Transaction commit or tenant isolation by itself |
| Keep its reviewed execution structure | A canonical manifest comparison | That every structural change is a defect |

The [first-project test](../examples/first-project/src/test/java/io/github/ym0506/routecontract/examples/firstproject/OrderContractTest.java)
checks the exact returned row before checking execution. Its equality and same-value range queries
return the same order, but observe one and two physical JDBC execution attempts respectively.
The [unchanged-count destination experiment](application-evaluations.md#same-count-different-data-source)
shows why a counter alone may miss the property you care about. It uses synthetic data and does
not establish a defect in the application from which the routing classes came.

## Observe after ShardingSphere has chosen the physical work

A JDBC wrapper outside ShardingSphere can see the application's logical statement. ShardingSphere
may turn that statement into multiple physical executions. RouteContract listens to the exact
version's `SQLExecutionHook`, which reports the data-source name and rewritten SQL at the physical
JDBC executor callback.

This avoids requiring the application to wrap every backing data source for this supported path.
A wrapper around each physical data source is also a valid approach. The
[datasource-proxy comparison](empirical-comparison.md) exercises both placements and a custom
operation-aware wrapper; it does not claim that JDBC counting is new.

**Tradeoff:** the hook is a version-specific observation point. An attempt is not a physical-table
count or a complete route plan. One execution may include a rewritten `UNION ALL` over several
tables. Before opening a capture, preflight checks the `infra-executor` and `infra-spi`
version anchors and SPI provider discovery. It does not align or audit the whole dependency
graph; every ShardingSphere module must still be exactly 5.5.3.

Read [the hook adapter](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/internal/RouteContractSqlExecutionHook.java)
and [runtime preflight](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/internal/ShardingSphere553Preflight.java).
See [preflight tests](../routecontract-shardingsphere-5.5/src/test/java/io/github/ym0506/routecontract/internal/ShardingSphere553PreflightTest.java)
for rejected runtime configurations.

## Attribute worker events to one caller operation

A service method can issue several statements, and ShardingSphere can execute work on pooled
threads. A process-wide counter mixes operations; a caller-only thread-local can miss worker events.

RouteContract assigns a capture token to one operation. The supported ShardingSphere executor
propagates submission context to workers. Hook instances use that token to find the matching
capture, and each instance pairs its own start and finish. Cleanup removes the caller context
and registry entry even when the application action throws.

**Tradeoff:** this uses the exact middleware's context propagation. It does not promise propagation
through arbitrary application-created threads, reactive streams or `@Async` calls. The
[architecture's concurrency record](architecture.md#correlation) states what the repeated MySQL
test established; concurrently open caller scopes do not prove simultaneous physical callbacks.

Read [CaptureRegistry](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/internal/CaptureRegistry.java),
[CaptureScope](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/internal/CaptureScope.java)
and the [capture tests](../routecontract-shardingsphere-5.5/src/test/java/io/github/ym0506/routecontract/RouteContractTest.java).
The separate [retention diagnostic](capture-retention.md) records repeated operations and its limits.

## Refuse to pass when the observation is incomplete

"Observed zero attempts" could mean no SQL ran, or that collection did not provide usable evidence.
A failed parallel operation may return before every submitted worker has finished. Treating the
events collected so far as a complete count could make an unsafe test pass.

Positive assertions require a normally returned, non-interrupted capture with observed work,
completed hook outcomes and no collector diagnostics. Missing outcomes and callback failures
cannot satisfy a contract. Retention is bounded; exceeding the limit also makes the capture
ineligible. Waiting a fixed number of milliseconds would not prove all workers had finished.

**Tradeoff:** some snapshots are useful only for diagnosis. `finishSuccess` reports that the
wrapped physical `executeSQL` call returned; it does not prove the surrounding operation or
transaction succeeded. The positive claim covers synchronous, non-batch `PreparedStatement`
operations, not universal detection of callbacks arriving after a snapshot freezes.

Read [RouteAssertions](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/RouteAssertions.java)
and [MutableCapture](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/internal/MutableCapture.java).
The [MySQL regression corpus](../examples/mysql/src/test/java/io/github/ym0506/routecontract/example/ObservedExecutionRegressionCorpusMySqlTest.java)
keeps business-result checks independent of execution checks.

## Compare structure without depending on worker arrival order

Worker scheduling can change event arrival order even when the operation is unchanged. Saving
that order, a timestamp or a random capture identifier would create irrelevant baseline differences.
The canonical manifest instead sorts structural entries and retains their multiplicity. Reordering
equivalent attempts is stable; executing an attempt twice remains different from executing it once.

It stores SQL fingerprints and parameter counts/types, not raw SQL or bind values. Data-source
names become caller-reviewed aliases. **These choices reduce retained data; they do not anonymize
it.** Guessable SQL can have a guessable hash, type names can reveal internals, and an alias mapping
can conceal a destination change if reviewed carelessly. Fingerprints use the exact rewritten SQL;
they do not prove two queries have equivalent meaning.

Read [ObservedExecutionManifest](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/manifest/ObservedExecutionManifest.java)
and its [canonicalization and verification tests](../routecontract-shardingsphere-5.5/src/test/java/io/github/ym0506/routecontract/manifest/ObservedExecutionManifestTest.java).
See [data handling](../SECURITY.md) before sharing artifacts.

## Keep observation separate from approval

Automatically replacing the expected file with the latest execution would erase the change the
test is meant to detect. A candidate records what happened; a baseline records what a reviewer
accepted. The library writes candidates and compares them with a separate baseline. It has no
automatic approval operation, and candidate writes guard against paths that identify the baseline.

The verifier checks compatibility and eligibility before budgets and structural differences.
The report explains that decision; generating it alone does not fail the build. The strict
`assertMatched` check and CLI reject every non-match. The separate `assertPassesBlockingChecks`
API deliberately permits `REVIEW_REQUIRED`; choose that policy explicitly if it fits your process.
A difference may be intentional, so inspect the query and configuration before changing the expectation.

Read [ManifestStore](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/manifest/ManifestStore.java),
[ManifestVerifier](../routecontract-shardingsphere-5.5/src/main/java/io/github/ym0506/routecontract/manifest/ManifestVerifier.java)
and the [report guide](ci-review-report.md). Rehearse the review in the
[first-project walkthrough](first-project.md#capture-and-review-your-first-baseline).

## Evaluate the evidence before adopting

- [0.1.4 public consumers](evidence/release-0.1.4-central.md): exact public artifacts and recorded Java/MySQL/build-tool checks.
- [Application experiments](application-evaluations.md): what the maintainer ran against selected public application code, and what was not run.
- [Observer cost on 0.1.3](observer-cost.md): allocation and timing observations; timing direction varies, so there is no stable overhead percentage claim.
- [Use and feedback records](user-feedback.md): experiments, conversations, integrations and repeat use are recorded separately. Independent repeat use is not yet verified.

If your existing JDBC listeners already express the required checks, include that in the decision.
If execution changes are a recurring gap in your supported ShardingSphere tests,
[try one operation](first-project.md#adapt-one-existing-test) and judge the report against a change
whose expected behavior your team understands.
