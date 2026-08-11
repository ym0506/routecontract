# RouteContract for ShardingSphere

[한국어](README.md) | [English](README.en.md)

> CI contracts for observed physical JDBC executions

RouteContract is a Java testing library for Apache ShardingSphere-JDBC applications. During one application operation, it turns the **physical JDBC execution attempts observed through `SQLExecutionHook`** into a deterministic manifest, then lets CI block observed execution expansion and structural changes caused by SQL or configuration changes.

Business-result assertions alone can stay green even when the hook-reported observed attempts increase from `1 → 2` or `1 → 8` while returning the same row. RouteContract adds a separate regression contract for per-operation execution budgets, hook-reported data-source names, and structural diffs of rewritten-SQL fingerprints.

The current version is a `v0.1.0-SNAPSHOT` development build. It has not been publicly released or independently validated by external users. The figures below are evidence from the local worktree as of 2026-08-11; they do not imply an award outcome, production support, or general performance.

## Quick Start

Prerequisites are Java 17, a running Docker daemon, and the executable Gradle
Wrapper. The first run may need network access to download Gradle and Maven
Central dependencies.

```bash
./scripts/quickstart-demo.sh
```

This command verifies the real-MySQL `1 → 2` observed-execution regression
while the business result stays unchanged, then feeds the same candidate to
the CI gate and checks the expected `RCM201`/`RCM202` rejection. A final
`[ROUTECONTRACT QUICKSTART VERIFIED]`, `realMysqlDemoExit 0`,
`intentionalCiGateExit 1`, and `quickstartExit 0` means the whole flow behaved
as expected. Exit `1` belongs to the intentionally rejecting inner CI gate;
exit `0` from the quickstart means that rejection was verified. A preflight or
verification failure exits `2`. The wrapper does not echo raw child-process
output that could contain SQL, parameters, or connection details.

## Verified core scenarios

| Scenario | Verified result |
|---|---|
| Same value, `=` → `BETWEEN` | Business row unchanged; observed attempts `1 → 2`; data sources `[ds_1] → [ds_0, ds_1]` |
| Reduced and modified fixture inspired by public issue #38456 | JOIN and subquery both return `COUNT=1`; observed attempts are `1` and `8`, respectively; this is not claimed as a faithful reproduction of the original issue |
| Configuration regression | Removing the table strategy keeps the attempt count and data sources unchanged but produces SQL-fingerprint drift |
| Determinism | Across 160 captures—8 corpus cases repeated 20 times—each case produced exactly one structural signature |
| Concurrently open caller-operation scopes | Across 20 single-attempt/multi-attempt scope pairs, no events were attributed across operations; temporal overlap of physical callbacks was neither forced nor measured |
| Generic JDBC-tool comparison | With datasource-proxy outside ShardingSphere, callbacks stay `1 → 1`; with wrappers around physical data sources, they become `1 → 2`; RouteContract also observes `1 → 2` |
| Isolated consumer build | In the same checkout, a standalone consumer using only a JAR published to a temporary Maven repository passed SPI auto-discovery and a MySQL execution test; this is not evidence of external adoption |

Run the full 50-test verification:

```bash
./gradlew --no-daemon --no-build-cache clean check assemble prepareVerifiedSbom
./scripts/verify-standalone-consumer.sh
```

The first command runs 50 core and MySQL-corpus tests on Java 17, ShardingSphere-JDBC 5.5.3, and a digest-pinned MySQL 8.4.11 Testcontainers image, then generates the JAR, Javadoc, and SBOM. The second command runs one separate consumer test. Docker is required.

## Consume public Release assets without a registry

This path becomes usable after a stable GitHub Release exists. Download every
public asset attached to that Release into one flat directory, then provide an
empty absolute repository path rather than relying on `~/.m2`.

```bash
python3 scripts/install-release-assets.py \
  --release-assets-dir /absolute/path/to/downloaded-release-assets \
  --repository /absolute/path/to/routecontract-maven
```

After the stable release version is chosen, use the coordinate printed by
the installer as the test dependency:

```groovy
testImplementation("io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:<release-version>")
```

The installer performs no network access. Before writing, it validates the
exact public-asset set, `SHA256SUMS`, stable POM coordinate, and JAR structure.
It copies only the main, sources, and Javadoc JARs plus the POM into the
explicit Maven layout, refuses to overwrite an existing coordinate, and does
not read or modify the default Maven repository. Checksums verify download
integrity, not publisher identity, so obtain the assets from the final public
Release.

To exercise a real MySQL consumer from the same source checkout with that file
repository as the exclusive RouteContract source, use a separate empty target:

```bash
./scripts/verify-release-assets-consumer.sh \
  /absolute/path/to/downloaded-release-assets \
  /absolute/path/to/empty-verification-maven
```

This is release-packaging evidence from the same checkout, not evidence of
external adoption.

For the shortest business-green/contract-red demonstration, run:

```bash
./scripts/run-demo.sh
```

This runs a real MySQL scenario in which changing equality to a same-value range preserves the business result but expands observed attempts from `1 → 2` and data sources from `1 → 2`. The strict manifest reports `RCM201` and `RCM202` as CI failures. The command succeeds because the test verifies that the expected violation occurs.

To reproduce an actual non-zero CI-gate exit using only two verified manifest files, run:

```bash
./scripts/demo-manifest-ci-failure.sh
```

This command does not require Docker. It prints `RCM201` and `RCM202`, then intentionally exits with code `1`. It is a dedicated fixture excluded from the regular `test` and `check` tasks.

To regenerate and compare the canonical files against real MySQL, then fail the build against the same approved baseline, run:

```bash
./scripts/demo-end-to-end-ci-failure.sh
```

Even when the preceding stages succeed, this command intentionally exits with code `1` at the final contract assertion.

## Smallest usage example

```java
RouteSnapshot snapshot = RouteContract.capture("orders.find-by-user-id", () -> {
    Order actual = orderRepository.findByUserId(3L);
    assertEquals(201L, actual.id()); // Keep the existing functional assertion.
});

RouteAssertions.assertThat(snapshot)
        .hasCompleteCapture()
        .hasNoReportedExecutionFailures()
        .hasExactlyObservedPhysicalAttempts(1)
        .observesExactlyDataSourceNames("ds_1");
```

The ShardingSphere SPI method name `finishSuccess()` does not mean that a transaction committed or that a business operation succeeded. RouteContract uses `CALLBACK_RETURNED` only to mean that ShardingSphere 5.5.3 reported `finishSuccess` to this hook provider after the physical `executeSQL` call returned. It does not prove completion of the surrounding JDBC operation, transaction, or application action.

## Approved manifests and CI diffs

```java
DataSourceAliases aliases = DataSourceAliases.of(Map.of(
        "ds_0", "orders-a",
        "ds_1", "orders-b"));
ManifestPolicy policy = ManifestPolicy.strict(1, 1);

ObservedExecutionManifest candidate = ObservedExecutionManifest.from(
        snapshot, aliases, policy);

Path approvedPath = Path.of("route-contracts/orders.find-by-user-id.json");
Path candidatePath = Path.of("build/routecontract/orders.find-by-user-id.candidate.json");
new ManifestStore().writeCandidate(approvedPath, candidatePath, candidate);

ObservedExecutionManifest approved = new ManifestStore().read(approvedPath);
ManifestVerificationResult result = new ManifestVerifier().verify(approved, snapshot, aliases);
ManifestAssertions.assertMatched(result); // A mismatch fails CI with stable RCM codes.
```

Writing a candidate never overwrites the approved file automatically. When a change is intentional, a person must review the diff and explicitly replace the approved baseline.

[examples/manifests](examples/manifests/README.md) contains canonical JSON from the real MySQL equality baseline and the same-result `BETWEEN` candidate, together with verifier output. The integration test regenerates these files on every run and checks byte-for-byte equality and stable diffs.

The data-source alias mapping is trusted configuration and part of the approval contract. The manifest stores caller-provided aliases, so aliases must be stable and non-sensitive. Reusing a real data-source name as its alias exposes that name. Quietly mapping a different real data source to an existing alias can hide drift. Review the mapping in version control alongside the manifest.

- `ManifestPolicy.strict(...)` blocks structural signature changes, including fingerprint changes.
- `ManifestPolicy.budgetOnly(...)` blocks changes in attempt count, data-source set, and callback outcomes, while returning signature-only changes as `REVIEW_REQUIRED`.
- Canonical JSON excludes timestamps, UUIDs, thread assignment, raw SQL, parameter values, and exception messages. It stores data sources only as caller-provided aliases, and callers remain responsible for keeping those aliases non-sensitive.

In a MySQL fixture that preserves the returned rows, one observed attempt, and
the same data source while changing an additional filter and predicate order,
only the fingerprint and parameter-type order drift. This is an observation
about that fixture, not a claim that the two SQL forms are generally
semantically equivalent.

| Policy | Result for this signature-only change | Tradeoff |
|---|---|---|
| `strict` | `DRIFT`; blocking `RCM301`/`RCM302`; assertion fails | Forces review and approval of small rewritten-SQL structural changes, but also blocks intentional changes until the baseline is updated |
| `budgetOnly` | `REVIEW_REQUIRED`; non-blocking `RCM301`/`RCM302`; `passesBlockingChecks=true` | Still blocks budget, data-source, and callback-outcome changes, but a missed manual review can allow a signature-only structural regression through CI |

## Precise comparison with existing tools

RouteContract does not claim that ShardingSphere observability facilities or generic JDBC tools are incapable of these tasks.

- ShardingSphere-Proxy `PREVIEW SQL`, together with ShardingSphere `sql-show` and Agent, provides planning, logging, and operational telemetry.
- ShardingSphere Audit checks whether built-in algorithms recognize a sharding condition.
- Sniffy and datasource-proxy support SQL-count assertions or custom JDBC collection.
- RouteContract packages a **caller-defined application-operation boundary**, correlation into ShardingSphere workers, a value-minimized canonical manifest, an approval workflow, stable semantic diffs, CI assertions, and a real regression corpus.

datasource-proxy is a credible do-it-yourself alternative, not a strawman. By wrapping every physical data source and adding application-owned correlation, minimization, canonicalization, diff, and assertion code, it can implement a comparable narrow check. RouteContract's scoped contribution is packaging that workflow for ShardingSphere-JDBC 5.5.3 without requiring every physical data source to be wrapped.

See [competitive-analysis.md](docs/competitive-analysis.md) for the sourced comparison and limitations, and [empirical-comparison.md](docs/empirical-comparison.md) for the measured datasource-proxy fixture.

## Exact evidence boundary

RouteContract observes:

- the data-source name reported to the hook;
- the SHA-256 fingerprint of the exact rewritten SQL string reported to the hook;
- parameter count and Java type names;
- the trunk/worker flag;
- start, callback return, callback failure, and missing-terminal-callback states.

RouteContract does not observe or prove:

- the complete route plan or `RouteContext`;
- every planned execution unit or every target shard;
- the exact number of physical tables;
- automatic `FULL_ROUTE` or `BROADCAST` classification;
- transaction commit or business success.

## v0.1 support boundary

- Java 17
- Apache ShardingSphere-JDBC **exactly 5.5.3**
- Synchronous `PreparedStatement` operations that return normally and whose caller is not interrupted when capture closes
- Integration verification against MySQL 8.4.11
- Concurrent operations on different caller threads and multi-attempt worker callbacks in the test fixture

Out of scope:

- ShardingSphere-Proxy
- JDBC batch and reactive execution
- Application-owned `@Async` boundaries
- Every SQL Federation execution path
- Other ShardingSphere versions
- Legitimate zero-SQL operation verification
- Contract approval for operations with a callback failure or caller interruption

The preflight only checks that the classpath's `shardingsphere-infra-executor` and `shardingsphere-infra-spi` report implementation version `5.5.3`, and that the service loader finds exactly one RouteContract provider. It does not prove version consistency across the complete ShardingSphere runtime artifact set. A capture cannot pass when those checks fail or no start callback is observed inside the capture. RouteContract does not claim to identify or explicitly reject every out-of-scope execution path, including Proxy, batch, and reactive paths.

After a parallel execution failure, ShardingSphere 5.5.3 may not wait for every worker it already submitted. A `REPORTED_EXECUTION_FAILURE` snapshot is therefore diagnostic-only and cannot pass route budgets or manifest matching.

One capture retains at most 10,000 physical execution attempts. At the next attempt, it stops growing the retained set and becomes `INCOMPLETE` with the `RC_ATTEMPT_LIMIT_EXCEEDED` diagnostic.

## Data minimization and security

Snapshots and manifests do not store raw SQL, parameter values, connection properties, or exception messages. However, data-source names, operation IDs, Java type names, and unsalted SQL fingerprints can still be sensitive engineering metadata. A SHA-256 fingerprint is not anonymization. v0.1 therefore assumes deterministic `PreparedStatement` tests that do not inline confidential literals. See [SECURITY.md](SECURITY.md) for details.

## Documentation and reproduction paths

- [Technical specification](docs/specification.md)
- [Architecture and trust boundaries](docs/architecture.md)
- [Competitive analysis](docs/competitive-analysis.md)
- [Empirical datasource-proxy comparison](docs/empirical-comparison.md)
- [Contest evidence matrix](docs/evidence-matrix.md)
- [Development plan through August 27](docs/development-plan.md)
- [Independent published-JAR consumer](examples/standalone-consumer/README.md)
- [SBOM generation and review](docs/sbom.md)
- [Pre-submission work and ShardLens boundary](ORIGIN_AND_PRIOR_WORK.md)
- [AI-assistance disclosure](AI_ASSISTANCE.md)
- [Contribution guide](CONTRIBUTING.md)

## Project origin

The problem originated in the unimplemented `Route Guard` design of ShardLens, a personal portfolio project. RouteContract does not copy ShardLens application code; it reimplements the design problem as a separately installable general-purpose test tool, manifest and diff format, and MySQL corpus. [ORIGIN_AND_PRIOR_WORK.md](ORIGIN_AND_PRIOR_WORK.md) documents the boundary between prior design and new implementation.

## Trademark and license

RouteContract is an independent project and is not affiliated with or endorsed by the Apache Software Foundation. Apache ShardingSphere and Apache are trademarks of the Apache Software Foundation.

RouteContract is distributed under the [Apache License 2.0](LICENSE). See [THIRD_PARTY.md](THIRD_PARTY.md) for direct and test dependencies and whether they are included in distributed artifacts.
