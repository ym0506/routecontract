# Competitive analysis and claim boundary

Last checked: 2026-08-11

This document answers a narrow question: does an existing tool already provide RouteContract's proposed workflow for Apache ShardingSphere-JDBC 5.5.3? It is a source-based comparison, not a benchmark and not a claim that every related project on the Internet was exhaustively searched.

RouteContract's v0.1 comparison target is:

> Run one named, synchronous application operation; collect the physical JDBC execution attempts reported by ShardingSphere's `SQLExecutionHook`, including the hook-reported data-source names; reduce SQL and parameters to a value-minimized deterministic representation; and fail CI when an explicit budget or an approved observed-execution manifest changes.

Some of that target is implemented in the current worktree and some remains pending. [The evidence matrix](evidence-matrix.md) is the authority for implementation and verification status. This document must not be used by itself as proof that RouteContract works.

## What is and is not new

The following ingredients are **not novel by themselves**:

- intercepting or logging JDBC executions;
- counting SQL statements in a test;
- showing ShardingSphere's rewritten SQL and selected data-source name;
- tracing SQL execution through an observability agent;
- asserting over captured database interactions.

The candidate contribution is the combination of an application-operation boundary, ShardingSphere-JDBC worker correlation, hook-reported physical-attempt evidence, deterministic value-minimized manifests, semantic baseline diff and CI-oriented assertions. The reviewed official documentation did not identify that complete packaged workflow. This is evidence of differentiation among the compared tools, **not** proof of patent novelty or proof that no equivalent project exists.

## Apache ShardingSphere facilities

### `PREVIEW SQL`

ShardingSphere documents `PREVIEW SQL` as a way to preview an SQL execution plan; its result contains `data_source_name` and `actual_sql` ([5.5.3 PREVIEW SQL documentation](https://shardingsphere.apache.org/document/5.5.3/en/user-manual/shardingsphere-proxy/distsql/syntax/rul/preview-sql/)). That is the closest built-in view of the rewritten target SQL.

Its boundary is important:

- DistSQL is documented as available only in ShardingSphere-Proxy, not ShardingSphere-JDBC ([5.5.3 DistSQL limitations](https://shardingsphere.apache.org/document/5.5.3/en/user-manual/shardingsphere-proxy/distsql/)). RouteContract v0.1 targets embedded ShardingSphere-JDBC.
- `PREVIEW` describes a plan preview. It does not execute the caller's repository/service operation and therefore is not evidence that a physical JDBC callback returned.
- The official `PREVIEW` page does not define a JUnit operation boundary, approved-baseline file, value-minimized canonical form or CI diff policy.

Conclusion: `PREVIEW` is a complementary diagnostic and a useful planned-route control. It is not a substitute for an observed-execution contract inside a ShardingSphere-JDBC application.

### `sql-show`

The `sql-show` property logs logical SQL, authentic/actual SQL and parsing results at INFO level; it is disabled by default ([5.5.3 properties documentation](https://shardingsphere.apache.org/document/5.5.3/en/user-manual/common-config/props/)). The ShardingSphere FAQ also says the debug output includes the rewritten SQL and routed data source ([official FAQ](https://shardingsphere.apache.org/document/current/en/faq/)). In the tagged implementation, logging happens after route/rewrite builds an `ExecutionContext` and before that context is returned to the executor ([5.5.3 `KernelProcessor`](https://github.com/apache/shardingsphere/blob/8d35894433416ef249ebb6ea21f8a8749648e9b6/infra/context/src/main/java/org/apache/shardingsphere/infra/connection/kernel/KernelProcessor.java#L49-L55)). Normal, non-simple logging can include the parameter collection along with each execution unit ([5.5.3 `SQLLogger`](https://github.com/apache/shardingsphere/blob/8d35894433416ef249ebb6ea21f8a8749648e9b6/infra/executor/src/main/java/org/apache/shardingsphere/infra/executor/sql/log/SQLLogger.java#L45-L68)).

This makes `sql-show` valuable for interactive diagnosis. The cited documentation does not define:

- ownership of records by a named application operation;
- isolation between two concurrent test operations;
- a stable, order-independent baseline schema;
- budget assertions or structural added/removed diff;
- a default persisted artifact that excludes parameter values and raw SQL.

A team could select simple logging or build a log parser and add those policies; `sql-show` is not being characterized as inherently unsafe. The additional callback correlation, canonicalization and verification layer is the product work RouteContract proposes. A direct `sql-show` parser comparison remains pending. The separate generic-JDBC-wrapper comparison described below is `verified-local`; it must not be presented as evidence about a log parser.

### Sharding Audit

ShardingSphere exposes the `ShardingAuditAlgorithm` extension point. The built-in `DML_SHARDING_CONDITIONS` algorithm is described as prohibiting DML without sharding conditions ([5.5.3 sharding developer documentation](https://shardingsphere.apache.org/document/5.5.3/en/dev-manual/sharding/)). Its 5.5.3 implementation checks whether the sharding-condition engine returns a non-empty result for a DML statement that touches a sharding table ([tagged source](https://github.com/apache/shardingsphere/blob/5.5.3/features/sharding/core/src/main/java/org/apache/shardingsphere/sharding/algorithm/audit/DMLShardingConditionsShardingAuditAlgorithm.java#L37-L52)).

That policy is not equivalent to an observed execution budget. A statement may contain a sharding condition yet still produce more physical attempts or a different rewritten SQL shape than an application's approved baseline. This is both a source-level distinction and a locally measured one. The real-MySQL E06 fixture first proves that the built-in Audit is active by rejecting a statement without a sharding condition. It then shows Audit allowing a same-value range read, a false other-shard branch and a same-value range update while RouteContract observes respectively 2, 2 and 4 physical attempts across two hook-reported data-source names ([fixture source](../examples/mysql/src/test/java/io/github/ym0506/routecontract/example/ObservedExecutionRegressionCorpusMySqlTest.java)). The two read mutations separately fail a one-attempt or one-data-source RouteContract assertion. This result is `verified-local`; no immutable public revision or CI artifact exists yet, so it is not yet a final-report result.

Conclusion: Audit is an execution policy and extension point. RouteContract is intended to be a regression oracle over what the physical-execution hook reports. They can be used together.

### ShardingSphere-Agent

ShardingSphere-Agent is the project's Java-agent-based observability framework. Its documented plugins provide metrics, tracing and logging, including integration with systems such as Prometheus and OpenTelemetry ([5.5.3 Agent documentation](https://shardingsphere.apache.org/document/5.5.3/en/user-manual/shardingsphere-agent/)). The metrics catalog includes routed-SQL and route-result counters as well as JDBC statement counts, failures and latency ([5.5.3 metrics documentation](https://shardingsphere.apache.org/document/5.5.3/en/user-manual/shardingsphere-agent/metrics/)). The official tracing article describes parse and execute spans and shows how tracing helps analyze the time spent at storage nodes ([official SQL trace article](https://shardingsphere.apache.org/blog/en/material/2023_06_07_how_to_run_sql_trace_with_shardingsphere/)).

Agent is broader and stronger for operational telemetry than RouteContract. Its tagged OpenTelemetry advice observes each JDBC executor callback and attaches the data-source name, rewritten SQL and bind-variable representation to a span ([5.5.3 callback advice](https://github.com/apache/shardingsphere/blob/8d35894433416ef249ebb6ea21f8a8749648e9b6/agent/plugins/tracing/type/opentelemetry/src/main/java/org/apache/shardingsphere/agent/plugin/tracing/opentelemetry/advice/OpenTelemetryJDBCExecutorCallbackAdvice.java#L41-L74)). RouteContract therefore must not claim that Agent cannot observe physical execution. The difference is that the cited Agent material does not present a test assertion library with an application-defined multi-statement operation, approved value-minimized manifest, deterministic semantic diff, or fail-the-build budget. RouteContract should not claim to replace Agent, distributed tracing, latency analysis or production monitoring.

Conclusion: Agent answers "what happened and how long did it take in an observed system?" RouteContract's proposed narrow question is "did this named test operation stay within its approved observed-execution contract?"

### `SQLExecutionHook`: the foundation, not a competitor

RouteContract does not invent the underlying callback. In ShardingSphere 5.5.3, `SQLExecutionHook.start` receives a data-source name, rewritten SQL, parameters, connection properties and a trunk-thread flag; terminal callbacks are `finishSuccess` and `finishFailure` ([tagged interface source](https://github.com/apache/shardingsphere/blob/5.5.3/infra/executor/src/main/java/org/apache/shardingsphere/infra/executor/sql/hook/SQLExecutionHook.java#L28-L51)). `SPISQLExecutionHook` discovers implementations with ShardingSphere's service loader and forwards those callbacks ([tagged dispatcher source](https://github.com/apache/shardingsphere/blob/5.5.3/infra/executor/src/main/java/org/apache/shardingsphere/infra/executor/sql/hook/SPISQLExecutionHook.java#L29-L51)).

The 5.5.3 JDBC executor calls `start` immediately before `executeSQL`, calls `finishSuccess` after that method returns, and calls `finishFailure` when the shown `SQLException` path is taken ([tagged executor source](https://github.com/apache/shardingsphere/blob/5.5.3/infra/executor/src/main/java/org/apache/shardingsphere/infra/executor/sql/execute/engine/driver/jdbc/JDBCExecutorCallback.java#L78-L105)). Therefore RouteContract uses these precise terms:

- **observed physical JDBC execution attempt**, not complete route plan;
- **hook-reported data-source name**, not automatically discovered topology;
- **callback returned**, not transaction committed or business operation succeeded;
- **reported failure**, not proof that every possible failure path was observed.

RouteContract's work is the lifecycle, correlation, minimization, deterministic model, assertions, manifest storage/diff, tests and documentation around this version-specific SPI. Supporting one tagged version is deliberate because SPI compatibility across versions has not been established.

## Generic JDBC testing tools

### Sniffy

Sniffy wraps a JDBC driver or `DataSource`, records statements in a `Spy`, and provides query-count expectations. Its documentation includes `atMostOneQuery`, current-thread/other-thread filtering and lambda/resource-scoped expectations ([Sniffy unit and component test documentation](https://sniffy.io/docs/latest/#_unit_and_component_tests)). Stable release 3.1.14 was published on 2022-11-05 ([release record](https://github.com/sniffy/sniffy/releases/tag/v3.1.14)); the repository has later development activity, so the release date must not be misrepresented as project abandonment. Sniffy also covers profiling, network observation and fault injection, all outside RouteContract's scope.

Overlap is substantial: both can observe JDBC work during a bounded test and fail an assertion on query count. RouteContract must not market basic query counting as its innovation.

The released thread matcher distinguishes `CURRENT`, `OTHERS` and `ANY` by thread identity ([3.1.14 `Threads` source](https://github.com/sniffy/sniffy/blob/v3.1.14/sniffy-core/src/main/java/io/sniffy/Threads.java#L11-L42)). The released statement metadata stores SQL, SQL type, stack trace and owner thread, while its source still contains a data-source-field TODO ([3.1.14 `StatementMetaData`](https://github.com/sniffy/sniffy/blob/v3.1.14/sniffy-core/src/main/java/io/sniffy/sql/StatementMetaData.java#L13-L30)). This does not prove that Sniffy cannot observe physical SQL; placement at the backing JDBC layer matters. It does show that the released model is not ShardingSphere `ExecutionUnit`/`dataSourceName` aware and has no documented operation token that separates two concurrent operations whose work both appears on other threads. The cited guide also does not document record/verify of a canonical multi-data-source observed-execution manifest. A direct head-to-head test is required before claiming any practical advantage.

### datasource-proxy

datasource-proxy 1.11.0 wraps a `DataSource` and supports before/after query listeners, logging, slow-query callbacks, query metrics and custom listeners ([current 1.11.0 user guide](https://jdbc-observations.github.io/datasource-proxy/docs/current/user-guide/), [release record](https://github.com/jdbc-observations/datasource-proxy/releases/tag/datasource-proxy-1.11.0)). Its `DataSourceQueryCountListener` can use thread-local storage or a single cross-thread holder, and its listener API is expressive enough to build custom capture behavior.

This is the strongest "build it yourself" alternative. An application can wrap each physical data source, name the wrappers, implement its own operation context, redact values, sort events, serialize a baseline and write assertions. RouteContract's proposed value is not that this is impossible; it is avoiding that bespoke wiring for the supported ShardingSphere-JDBC version and providing tested event semantics and regression fixtures.

The default datasource-proxy logging examples include raw query and parameter representations. That does **not** mean datasource-proxy forces unsafe persistence: custom listeners and formatters can minimize data. RouteContract's differentiator must be a tested default artifact that omits raw SQL, raw parameter values, connection properties and exception messages, not a claim that the competing library is inherently unsafe.

The fair real-MySQL comparison is now `verified-local` ([method and limitations](empirical-comparison.md), [fixture source](../examples/mysql/src/test/java/io/github/ym0506/routecontract/example/DataSourceProxyComparisonMySqlTest.java)). On the same unchanged-business-result mutation, one datasource-proxy wrapper outside ShardingSphere reports `1 -> 1` logical callbacks, wrappers around every physical data source report `1 -> 2` backing callbacks, and RouteContract reports `1 -> 2` hook attempts. The fixture also implements the missing operation token, worker propagation, minimization, canonicalization, diff and assertion code to prove that a comparable narrow workflow is buildable. This supports a packaging-and-defaults claim, not categorical technical superiority. Public immutable output is still pending.

### datasource-assert

datasource-assert wraps a data source in `ProxyTestDataSource` and provides JUnit/TestNG, AssertJ and Hamcrest assertions over execution count, query type, SQL and parameters ([official 1.0 user guide](https://ttddyy.github.io/datasource-assert/docs/current/user-guide/index.html)). The guide identifies version 1.0 and a 2017-10-27 documentation date; its GitHub repository is explicitly archived and read-only ([repository](https://github.com/ttddyy/datasource-assert)). That is a repository-state fact, not a reason to dismiss its design or assertions.

It is direct precedent for a fluent JDBC assertion API and therefore weakens any novelty claim based only on `assertThat(dataSource)`. The reviewed guide does not describe ShardingSphere hook-reported data-source names, worker correlation or a canonical record/verify manifest workflow. RouteContract needs to demonstrate those differences in code and MySQL evidence, not only in prose.

## Adjacent database-regression precedent

### pg-plan-guard

The [pg-plan-guard repository and README](https://github.com/YusufDrymz/pg-plan-guard) describe a PostgreSQL tool that captures plain `EXPLAIN` plans, normalizes them to plan shapes, writes a deterministic committed lock file, compares later plans and can fail CI according to finding severity. That is primary-source evidence that the broader snapshot/lock/diff/CI workflow for database execution structure is prior art. RouteContract must not claim to have invented that workflow.

pg-plan-guard is not a direct substitute for the scoped RouteContract product. It guards a planned PostgreSQL optimizer shape for queries listed in its own configuration and deliberately does not execute those queries. RouteContract observes ShardingSphere-JDBC 5.5.3 hook-reported backing JDBC attempts while the caller's named application operation runs. The pg-plan-guard README does not describe a ShardingSphere operation token, worker-callback correlation, ShardingSphere data-source-name evidence or callback outcomes. Conversely, RouteContract does not analyze PostgreSQL scan/join nodes, index loss, cost drift or planner stability. The projects are adjacent precedents with different observation points and regression semantics.

## Capability matrix

`Documented` means the linked upstream documentation explicitly supports the capability. `Not identified` means it was not found in the cited material; it does not mean the capability is impossible or absent from every extension.

| Tool/facility | Primary observation point | Documented test assertion | Hook-reported ShardingSphere data-source name | Canonical approved manifest + semantic diff | Appropriate conclusion |
|---|---|---|---|---|---|
| ShardingSphere `PREVIEW` | Proxy plan preview | Not identified | Returns planned `data_source_name` | Not identified | Complementary planned-route diagnostic; Proxy-only DistSQL |
| ShardingSphere `sql-show` | Diagnostic logs | Not identified | Routed data source appears in logs | Not identified | Useful debugging source; extra product code is needed for contracts |
| Sharding Audit | Pre-execution SQL policy | Rejects configured policy violations | Not its documented output | Not identified | Policy control, not an observed-attempt baseline |
| ShardingSphere-Agent | Runtime tracing/metrics/logging | Not identified | Execution tracing can show where SQL is sent | Not identified | Operational observability; do not position RouteContract as a replacement |
| Sniffy | JDBC driver/`DataSource` wrapper | Query/row/thread expectations | Not identified | Not identified | Close query-count competitor; head-to-head evidence required |
| datasource-proxy | Proxied `DataSource` listeners | Metrics; custom assertions are buildable | Wrapper-defined data-source identity, not the hook field | Buildable with custom code; not identified as built-in workflow | Most credible DIY alternative |
| datasource-assert | `ProxyTestDataSource` | Fluent execution/query assertions | Not identified | Not identified | Direct assertion-API precedent |
| pg-plan-guard | PostgreSQL planned `EXPLAIN` shape | CI check with configurable failure severity | No | Deterministic plan lock and structural diff | Adjacent database-regression precedent, not a ShardingSphere execution-attempt tool |
| RouteContract v0.1 target | ShardingSphere 5.5.3 `SQLExecutionHook` within a named synchronous operation | Budgets, completeness, failures and approved manifest | Yes, exactly the hook argument | Target capability; see evidence matrix for current status | Narrow ShardingSphere-JDBC regression-testing package |

## Positioning that survives scrutiny

Use this sentence in final public claims only after E03-E08 are artifact-ready at the submitted revision:

> RouteContract turns the physical JDBC execution attempts reported by ShardingSphere-JDBC 5.5.3 during one named synchronous application operation into a deterministic, value-minimized contract that can be budgeted, versioned and structurally diffed in CI.

Do not use any of these claims:

- "detects every full route" or "proves single-shard routing";
- "captures the complete route plan";
- "counts physical tables";
- "proves commit/business success";
- "works with all ShardingSphere versions, async styles or batch execution";
- "is the first" or "has no competitors";
- "is privacy-safe" without stating exactly which values are and are not retained.

The precise privacy statement for v0.1 is: the default contract model is designed not to persist raw parameter values, connection properties, exception messages or raw SQL; it does retain operation labels, hook-reported data-source names, SQL fingerprints, parameter counts/type names, thread-role flags and callback outcomes. E03-E08 and dedicated privacy tests must verify that statement.

## Falsification gates

The project should be stopped or repositioned if any of the following occurs:

1. An actively usable project is found that already provides the same ShardingSphere-JDBC operation correlation, value-minimized canonical manifest and CI diff with less integration work.
2. A real MySQL test cannot reliably associate the observed ShardingSphere worker callbacks with the correct caller operations while two capture scopes are concurrently open. Passing that test alone does not prove that physical hook callbacks overlapped in time.
3. The same operation and configuration do not produce a deterministic canonical manifest after sorting away event order.
4. Hook activation cannot be distinguished from a zero-execution operation, allowing an unloaded adapter to pass silently.
5. A physical-`DataSource` wrapper implementation proves equally precise and materially simpler for the promised scope.

## Current external evidence

Apache ShardingSphere issue [#38456](https://github.com/apache/shardingsphere/issues/38456) is a public example in which a subquery was reported to expand to many actual SQLs while an equivalent JOIN produced one. The issue is open at the time of this review. RouteContract's local corpus contains an **issue-inspired reduced and modified fixture**; it is not an exact reproduction of the upstream report and must not be described as one. The related kernel-fix [PR #39112](https://github.com/apache/shardingsphere/pull/39112) was opened by GitHub user `Develop-KIM` and closed without merge after review identified a cross-layer routing-contract problem. Until the participant's ownership of that account is confirmed, this repository does not claim the PR as participant prior work. In all cases, that public history supports the reality and subtlety of route regressions; it does **not** establish acceptance, endorsement or usage of RouteContract.

As of 2026-08-11 there is no public RouteContract release, no external RouteContract user, no independent installation result and no upstream acceptance. Those items remain evidence gates, not report claims.
