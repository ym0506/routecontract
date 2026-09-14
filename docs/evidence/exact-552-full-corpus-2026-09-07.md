# Exact 5.5.2 full route-risk corpus

Evidence labels: `verified - MySQL`, `verified - ShardingSphere-JDBC 5.5.2`,
`verified - ShardingSphere-JDBC 5.5.3`. This note records local source-candidate execution.
It is neither public release evidence nor an independent-user adoption report.

## Change and acceptance boundary

At commit `008e125a0648ed615842a572d60fd453698bb5aa`, the 5.5.2 lane had six tests:
its repeated fan-out, caller isolation and failure checks did not execute the complete
route-risk/safe-control corpus required by [ADR A-23](../versioned-shardingsphere-adapters.md).
The added `Exact552ObservedExecutionRegressionCorpusMySqlTest` now executes that corpus on
its own exact-5.5.2 graph and physical MySQL containers. It derives fixture structure from the
existing 5.5.3 corpus but does not substitute source similarity for execution evidence.
The original 5.5.2 operation fixture now checks full business rows and adds the secret-value
privacy case. No adapter, core, publication, build or existing 5.5.3/schema-1 baseline changed.

The new 14 fixed schema-2 observation files are test expectations with exact 5.5.2 identity;
they are not newly approved application manifests. They were captured from this exact lane,
inspected, and checked again by a normal run with generation disabled. The human-review
requirement in A-23 is retained: automated implementation and review do not constitute a
human's approval of these new test expectations. A-23 should not be marked fully accepted
until that review is recorded.

## Observed corpus and independent business oracle

Every complete capture below requires exact 5.5.2 runtime identity, no diagnostic, failure or
unknown outcome, and the expected callback-returned count. Aliases are explicitly fixed as
`ds_0 → orders-even`, `ds_1 → orders-odd`; they do not expose real infrastructure names.

| Case | Independently asserted business result | Observed attempts | Sources by alias |
|---|---|---:|---|
| Equality, single-value IN, additional filter, reordered predicates, alias, LIMIT | Each returns order ID `[201]` | 1 each | orders-odd |
| Same-value range | `[201]` | 2 | orders-even, orders-odd |
| False other-shard OR branch | `[201]` | 2 | orders-even, orders-odd |
| Equality UPDATE control | Update count 1; odd row status changed; even row unchanged | 1 | orders-odd |
| Same-value range UPDATE | Update count 1; odd row status changed; even row unchanged | 4 | orders-even, orders-odd |
| Table strategy removed | `[201]` | 1 | orders-odd |
| Database strategy removed | `[201]` | 2 | orders-even, orders-odd |
| Reduced issue #38456 subquery | Scalar 1 | 8 | orders-even, orders-odd |
| Reduced issue #38456 join | Scalar 1 | 1 | orders-odd |

The built-in `DML_SHARDING_CONDITIONS` auditor rejects a query without a sharding condition;
it accepts the measured range, false-OR and range-UPDATE risks. This fixture does not claim
all auditors or configurations behave the same way.

Table-strategy removal retains the one-attempt budget while changing fingerprint
`b8b1f33ad62b87278f4f7623eb3d53e87b6f1fff88abf1415f14f2d4ceddd78b` to
`0788cb631ab1c688853da32e0fe4f6652e69b091debde648c0dcf14c778b9979` and parameter shape
`[Long] → [Long, Long]`. Strict verification blocks with `RCM301/RCM302`. These happen to
match the existing 5.5.3 example's fingerprints; identity and separate evidence are still
required. The reordered-predicate safe control also produces `RCM301/RCM302`: strict policy
blocks, while budget-only policy requests nonblocking review.

The fixed files contain the full fingerprint/type/outcome/multiplicity records for six safe
controls and eight repeated shapes. Each repeated shape runs **20 times** with exact business,
count and source assertions, fixed-file comparisons, and exactly one canonical signature.
The separate operation fixture executes **20 pairs** of a single-source and a fan-out capture;
it asserts operation IDs, exact business rows, independent signatures and worker flags.

## Reproduction and raw evidence

The local validation used Java 17.0.15, Gradle 8.14.4 and Docker with:

```text
mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb
```

From the repository root, with `JAVA_HOME` set to a working Java 17 installation:

```bash
./gradlew --no-daemon --no-build-cache \
  :mysql-5.5.2-example:cleanTest :mysql-5.5.2-example:test \
  :mysql-example:cleanTest :mysql-example:test
```

Normal validation, with generation mode disabled:

| Raw JUnit directory / suite | Tests | Failures / errors / skipped |
|---|---:|---|
| `examples/mysql-5.5.2/build/test-results/test/TEST-io.github.ym0506.routecontract.example552.Exact552ObservedExecutionRegressionCorpusMySqlTest.xml` | 7 | 0 / 0 / 0 |
| `examples/mysql-5.5.2/build/test-results/test/TEST-io.github.ym0506.routecontract.example552.Exact552OperationContractMySqlTest.xml` | 7 | 0 / 0 / 0 |
| `examples/mysql/build/test-results/test/TEST-*.xml` (four existing 5.5.3 suites) | 14 | 0 / 0 / 0 |

Generated minimized evidence is under `examples/mysql-5.5.2/build/routecontract-552-corpus/`
and `examples/mysql-5.5.2/build/routecontract-552-evidence/`. Raw build/JUnit files are local,
regenerable evidence, not immutable public CI receipts. Do not substitute this note for a
fresh exact-head public CI run before release.

## Limits

- The barrier proves concurrently open application capture scopes, not forced overlap of
  every physical callback, arbitrary async propagation or production stress resilience.
- The dropped-table test allows callback scheduling to vary. It requires a real caught
  SQLException, at least one reported failure, a non-COMPLETE snapshot and `NOT_ELIGIBLE`
  manifest verification; it does not invent an exact failure-attempt total.
- `finishSuccess` is only the hook report after a wrapped physical `executeSQL` returned.
  Business results are independently read; callbacks do not establish transaction commit.
- Attempt counts are not physical-table counts or complete route plans. Rewritten UNION ALL
  can combine tables in one attempt. No performance claim follows from these measurements.
- The 5.5.3 datasource-proxy packaging comparison remains in the 5.5.3 lane only. This change
  covers the A-23 corpus; it does not claim parity for every optional integration package.
- A-23 human review, A-26 migration evidence, staged/public split-artifact consumers and the
  release gates remain separately auditable requirements.
