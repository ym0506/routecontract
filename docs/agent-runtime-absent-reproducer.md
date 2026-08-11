# ShardingSphere Agent reproducer without the RouteContract runtime

Last checked: 2026-08-12

This opt-in follow-up isolates one question left by the main
[Agent comparison](empirical-agent-comparison.md): does the same completed-span gap appear when
the RouteContract product, API, hook provider and normal test output are absent from the forked
application runtime?

The name “runtime-absent reproducer” is deliberate. This is not an Agent-only process: it uses
datasource-proxy 1.11.0 as a count-only backing-query callback oracle. It is also authored and run
by the RouteContract maintainer, so it is not independent third-party validation or the smallest
possible upstream reproducer.

## Isolation and exact fixture

The dedicated `agentOnlyTest` Gradle source set does not extend the normal test configurations and
has no RouteContract project dependency. Before the fork starts, its opt-in task rejects a runtime
classpath containing the RouteContract build output, artifact or normal test output. Inside the
fork, the fixture verifies all of the following before and after the workload:

- the RouteContract public API class is absent;
- the RouteContract `SQLExecutionHook` class and class resource are absent;
- no RouteContract provider is present in the `SQLExecutionHook` service descriptors; and
- no RouteContract artifact entry is reported by the fork's system classpath check.

The fixed environment is Java 17, ShardingSphere-JDBC and official ShardingSphere Agent 5.5.3,
datasource-proxy 1.11.0, Connector/J 26.7.0, Testcontainers 1.21.4 and two digest-pinned MySQL
8.4.11 containers. Each of 20 sequential iterations performs one single-target equality control
and one two-target same-value range query. A two-party barrier inside the wrapped backing data
sources forces both range callbacks to overlap. Under the tagged 5.5.3 call path, that barrier is
reached from inside the Agent-advised `JDBCExecutorCallback`; this ordering is source-backed rather
than independently timestamped by the fixture.

## Bounded local result

In two consecutive local runs of this exact fixture:

| Observation | Each run |
|---|---:|
| Logical statements | 40 |
| datasource-proxy returned backing-query callbacks | 60 |
| datasource-proxy reported failures | 0 |
| Agent statement-root spans | 40 |
| Agent completed control `/executeSQL/` spans | 20 |
| Agent completed forced-overlap fan-out `/executeSQL/` spans | 20 |
| Agent completed `/executeSQL/` spans in total | 40 |
| Fan-out execute-span difference from the proxy oracle | 20 |

The two canonical summaries were byte-identical: 1,336 bytes with SHA-256
`30648c841726da7782fdfa2cfdfff3bf9d638bd7d331af618288179b4cd9ca88`. These are local results
until the dedicated manual workflow produces a public commit-bound run and a digest-identified
90-day artifact. An Actions artifact can expire or be deleted; it is not equivalent to an
immutable GitHub Release.

Safe conclusion:

> In this exact forced-overlap ShardingSphere-JDBC/Agent 5.5.3 fixture, with the RouteContract
> runtime, API, hook and SPI provider absent, datasource-proxy 1.11.0 reported 60 returned
> backing-query callbacks while the official Agent exported 40 completed `/executeSQL/` spans.
> The 20-span difference occurred in the 20 forced two-way fan-outs.

This narrows one alternative explanation for the main comparison: RouteContract's hook is not
required for the observed gap. It does not prove that the Agent always loses half of fan-out spans,
that the shared attachment is the cause, that datasource-proxy counts network round trips, or that
RouteContract is universally more accurate than tracing.

## Reproduction and publication boundary

Run only through the bounded wrapper when producing evidence:

```bash
python3 -m unittest scripts.tests.test_verify_agent_comparison -v
python3 scripts/verify-agent-comparison.py --agent-only
python3 scripts/verify-agent-comparison.py --agent-only --verify-summary-only
```

The wrapper downloads or stages only the exact official 5.5.3 archive, verifies its fixed byte
count and published SHA-512, extracts a ten-file allowlist, and attaches the Agent only to the
dedicated test JVM. It supplies the Gradle subprocess with a minimal environment allowlist and
private `HOME`, `GRADLE_USER_HOME` and temporary directory. Raw spans remain in memory.

The only file intended for publication is
`build/agent-only-reproducer/summary.json`. Its verifier opens repository-relative directories
without following links, requires that exact one-file set, enforces an exact typed schema and
canonical JSON encoding, and scans it for raw SQL, bind values, data-source names, trace/span IDs,
connection identifiers and paths. Ordinary ignored Gradle/JUnit output may still remain locally
and can contain environment metadata; it must not be uploaded.

The manual
[runtime-absent workflow](../.github/workflows/agent-only-reproducer.yml) has `contents: read`, uses
commit-pinned actions, enters the experiment only through the checksum-validating wrapper, verifies
the canonical summary again, and uploads that one file. It is intentionally not connected to
normal `test`, `check`, pull-request CI or the release gate.

## Limitations

- exact ShardingSphere-JDBC and Agent 5.5.3 only;
- synchronous `PreparedStatement` execution on the fixture's single-callback executor path;
- forced two-way overlap, not ordinary production timing;
- completed exported spans compared with returned datasource-proxy callbacks;
- no performance, transaction-commit, business-success or full-route-plan conclusion; and
- no upstream bug report or maintainer confirmation is claimed.
