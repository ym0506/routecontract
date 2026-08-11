# Empirical comparison with ShardingSphere Agent 5.5.3

Last checked: 2026-08-12

This experiment asks one deliberately narrow question:

> When two backing JDBC executions from one ShardingSphere fan-out are forced to overlap, how many completed OpenTelemetry `/executeSQL/` spans does the official ShardingSphere Agent 5.5.3 export, compared with two in-process execution-attempt oracles?

It is not a general Agent benchmark, a performance test or evidence that RouteContract is universally more accurate than tracing. The public workflow is manual because it downloads a 46.7 MB archived distribution and starts two MySQL containers. Until a public commit-bound Actions run and digest-identified 90-day artifact exist at the submitted revision, the numbers below are **verified locally; public artifact pending**. That artifact can expire or be deleted and is not equivalent to an immutable GitHub Release.

## Why this comparison exists

The official Agent is a strong adjacent implementation, not a straw man. Its 5.5.3 OpenTelemetry advice creates a span for each `JDBCExecutorCallback` execution and records the execution unit's data-source name, rewritten SQL, bind-variable representation, host and port ([tagged advice source](https://github.com/apache/shardingsphere/blob/8d35894433416ef249ebb6ea21f8a8749648e9b6/agent/plugins/tracing/type/opentelemetry/src/main/java/org/apache/shardingsphere/agent/plugin/tracing/opentelemetry/advice/OpenTelemetryJDBCExecutorCallbackAdvice.java#L41-L74)). It is therefore incorrect to say that Agent cannot observe backing JDBC execution.

The same tagged code also supplies a concrete concurrency question:

- Agent adds one private volatile attachment field to each instrumented target object ([builder source](https://github.com/apache/shardingsphere/blob/8d35894433416ef249ebb6ea21f8a8749648e9b6/agent/core/src/main/java/org/apache/shardingsphere/agent/core/builder/interceptor/impl/TargetAdviceObjectBuilderInterceptor.java#L29-L36), [attachment interface](https://github.com/apache/shardingsphere/blob/8d35894433416ef249ebb6ea21f8a8749648e9b6/agent/api/src/main/java/org/apache/shardingsphere/agent/api/advice/TargetAdviceObject.java#L23-L37)).
- the OpenTelemetry advice stores the newly started span in that attachment, then reads it back to end the span ([tagged advice source](https://github.com/apache/shardingsphere/blob/8d35894433416ef249ebb6ea21f8a8749648e9b6/agent/plugins/tracing/type/opentelemetry/src/main/java/org/apache/shardingsphere/agent/plugin/tracing/opentelemetry/advice/OpenTelemetryJDBCExecutorCallbackAdvice.java#L41-L74));
- on the single-callback `JDBCExecutor.execute(context, callback)` path used by this fixture, `JDBCExecutor` supplies `null` as `firstCallback` ([tagged JDBC executor source](https://github.com/apache/shardingsphere/blob/8d35894433416ef249ebb6ea21f8a8749648e9b6/infra/executor/src/main/java/org/apache/shardingsphere/infra/executor/sql/execute/engine/driver/jdbc/JDBCExecutor.java#L49-L66)); `ExecutorEngine` then uses the remaining callback for both the caller-thread group and submitted worker groups ([tagged executor-engine source](https://github.com/apache/shardingsphere/blob/8d35894433416ef249ebb6ea21f8a8749648e9b6/infra/executor/src/main/java/org/apache/shardingsphere/infra/executor/kernel/ExecutorEngine.java#L91-L112)).

Those sources make attachment overwrite a plausible explanation when the same target is entered concurrently. The experiment measures the externally visible completed spans; it does not mutate Agent code to prove causality.

## Fixture and independent oracles

The fixture runs on Java 17 with ShardingSphere-JDBC and Agent 5.5.3, Connector/J 26.7.0, Testcontainers 1.21.4 and two digest-pinned MySQL 8.4.11 containers.

Each of 20 sequential, caller-named operations executes:

1. one equality control that reaches one backing data source; and
2. one same-value range mutation that returns the same business row but reaches two backing data sources.

The physical `DataSource` wrappers contain a count-only listener. For the range mutation, a two-party barrier holds both backing calls after Agent advice has been entered and before either physical query proceeds. The listener does not read or retain SQL, parameters, connection metadata, ports or data-source names.

Two in-process oracles must agree before Agent output is considered:

- datasource-proxy reports one control attempt plus two fan-out attempts per operation; and
- RouteContract reports a `COMPLETE` three-attempt snapshot, two hook-reported data-source names, two trunk flags, one worker flag and no failures or diagnostics.

The Java fixture is [AgentComparisonMySqlTest](../examples/mysql/src/test/java/io/github/ym0506/routecontract/example/AgentComparisonMySqlTest.java). The bounded runner is [verify-agent-comparison.py](../scripts/verify-agent-comparison.py).

## Locally verified result

| Observation | Count |
|---|---:|
| Named operations | 20 |
| Logical statements | 40 |
| datasource-proxy backing callbacks | 60 |
| RouteContract hook-reported attempts | 60 |
| Agent statement-root spans | 40 |
| Agent completed control `/executeSQL/` spans | 20 |
| Agent completed forced-overlap fan-out `/executeSQL/` spans | 20 |
| Agent completed `/executeSQL/` spans in total | 40 |
| Difference from the two agreeing oracles | 20 |

All 20 controls produced one completed execute span. Across 20 forced two-way fan-outs, the two oracles reported 40 backing attempts while Agent exported 20 completed fan-out execute spans. The surviving fan-out spans covered both data-source identities across the run. The JUnit fixture passed once with zero failures, errors or skips, and all 20 RouteContract operation signatures were identical.

The canonical local summary was 1,068 bytes with SHA-256 `40061ab53689a011c341cf983256e417498380370684b6b5316a10527f767b06`. That checksum identifies a local run only; it is not a public evidence claim. A public commit-bound Actions run and digest-identified 90-day artifact must replace it before the result appears in the contest report.

## What the result means

Safe conclusion:

> In this exact forced-overlap ShardingSphere-JDBC/Agent 5.5.3 fixture, datasource-proxy and RouteContract each reported 60 backing attempts while Agent exported 40 completed execute spans. The 20-span difference occurred in the 20 forced two-way fan-outs and is consistent with the tagged shared-attachment implementation.

This supports a version-specific integration and defaults argument. It does **not** establish that:

- Agent always loses half of fan-out spans;
- non-overlapping fan-out behaves the same way;
- every ShardingSphere version, Agent plugin or exporter has this behavior;
- RouteContract observes a complete route plan, transaction commit or business success;
- RouteContract is safe for arbitrary asynchronous or failure-return paths; or
- tracing cannot be assembled into a contract-testing workflow.

A follow-up [RouteContract-runtime-absent reproducer](agent-runtime-absent-reproducer.md) now runs the same forced-overlap shape from a dedicated source set without the RouteContract product, API, hook provider or normal test output on the forked runtime. It uses datasource-proxy 1.11.0 as its sole count oracle and reproduced the same `60` returned callbacks versus `40` completed Agent execute spans in two local runs. This narrows one alternative explanation but is maintainer-authored evidence, not independent third-party validation or the smallest upstream reproducer. Its public commit-bound workflow run and digest-identified 90-day artifact are still pending.

## Privacy and supply-chain controls

The runner:

- accepts only the exact [official 5.5.3 Agent archive](https://archive.apache.org/dist/shardingsphere/5.5.3/apache-shardingsphere-5.5.3-shardingsphere-agent-bin.tar.gz), 46,741,869-byte size and [published SHA-512](https://archive.apache.org/dist/shardingsphere/5.5.3/apache-shardingsphere-5.5.3-shardingsphere-agent-bin.tar.gz.sha512) `6538bf650cbdb1813814e1922b6c2072246c4595cb07322f793d5592c86be875949529ab6a00553c15f72a0b17e2d23628f6e8b5da9fb189a72ce8c4cfb37839`;
- copies a caller-supplied archive through one no-follow descriptor before validation and extraction;
- extracts an exact ten-file allowlist into a private temporary directory;
- receives Zipkin JSON or bounded gzip only on a loopback ephemeral port;
- caps requests, workers, wire bytes, decoded bytes, spans, fields, Gradle output and wall time;
- validates the exact statement shapes, bind arities, parent/root relationships, `OK` statuses and required Agent attributes in memory;
- keeps raw Agent spans in memory and makes the fixed-schema canonical aggregate summary the only comparison artifact intended for publication and the only file uploaded by the workflow; standard local Gradle build/test output may remain; and
- excludes raw-telemetry fields from the summary schema, then scans the serialized summary for SQL tokens, the fixture string bind, fixture data-source aliases, loopback/JDBC identifiers, trace/span key names and path separators.

The official Agent distribution is downloaded only for this opt-in test, is Apache-2.0 licensed, is not redistributed and is not part of the Gradle dependency graph or generated library SBOM. See [THIRD_PARTY.md](../THIRD_PARTY.md).

## Reproduction

Prerequisites are Java 17, Docker and network access to the Apache archive:

```bash
python3 -m unittest scripts.tests.test_verify_agent_comparison -v
python3 scripts/verify-agent-comparison.py
```

To reuse a separately downloaded archive without a second network fetch:

```bash
python3 scripts/verify-agent-comparison.py --archive /path/to/apache-shardingsphere-5.5.3-shardingsphere-agent-bin.tar.gz
```

On success, `build/agent-comparison/summary.json` is the only comparison artifact intended for publication. Standard local Gradle build/test files may also remain. The command prints one fixed success marker and does not print raw Agent telemetry or captured Gradle output. The manual [Agent comparison workflow](../.github/workflows/agent-comparison.yml) uploads only the verified summary.

## Generic tracing remains a credible alternative

The standard [OpenTelemetry Java Agent](https://github.com/open-telemetry/opentelemetry-java-instrumentation) provides automatic JDBC and executor instrumentation, while [Tracetest](https://docs.tracetest.io/) turns trace data into selectors and assertions that can run in CI. With application operation spans, exporter configuration, attribute minimization, normalization and baseline policy, a team can assemble a workflow that overlaps substantially with RouteContract.

That composition has not yet been run against this exact ShardingSphere fixture, so its behavior here is an experiment backlog item rather than a result. RouteContract's defensible distinction is the tested ShardingSphere-JDBC 5.5.3 package and contract lifecycle, not a claim that tracing-based alternatives are impossible.
