# Exact 5.5.2 MySQL acceptance fixture

This source-candidate fixture executes the complete route-risk corpus separately on
**ShardingSphere-JDBC 5.5.2**, Java 17, and the digest-pinned MySQL 8.4.11 image.
It is not a released 5.5.2 support claim.

```bash
./gradlew --no-daemon --no-build-cache :mysql-5.5.2-example:cleanTest :mysql-5.5.2-example:test
```

Docker and a working Java 17 installation are required. The build rejects any mixed
ShardingSphere dependency version, and every complete snapshot assertion checks exact 5.5.2
runtime identity. Raw JUnit appears under `build/test-results/test/`.

`Exact552ObservedExecutionRegressionCorpusMySqlTest` contains seven tests: six safe SQL
controls, strict versus budget-only policy sensitivity, same-value range and false-OR read
risks, a range UPDATE, database/table strategy removal, a reduced issue #38456 subquery/join
pair, an active built-in sharding audit control, and twenty repetitions of all eight corpus
shapes. Tests assert explicit business results separately from observed callback evidence.
UPDATE checks also read the intended odd-shard row and the unchanged even-shard row directly.

`Exact552OperationContractMySqlTest` contains seven tests for successive captures and ordinary
SQL, the existing approved exact-5.5.2 manifest example, propagation boundaries, twenty pairs
of concurrently open captures, actual physical JDBC failure, interruption, and secret-value
privacy. Equality/range assertions check full `(order_id, user_id, status)` rows. A dropped
physical table produces an application-caught SQLException and contract-ineligible evidence.

The 14 JSON files in `src/test/resources/corpus/shardingsphere-5.5.2/` are version-specific
**test observations**, not approved baselines for a user's application. They pin runtime
identity, aliases, counts, fingerprints, parameter types, outcomes and multiplicities.
The six safe controls and all eight repeated shapes compare against these fixed files; a
stable change across runs cannot pass merely because each run is internally deterministic.
The common `8 attempts / 2 sources` policy is only an envelope for these fixture records;
separate assertions enforce each case's tighter count/source expectation and reject the
business-green regressions against their intended contract.

Normal tests never overwrite expected files. To inspect new candidate observations:

```bash
./gradlew --no-daemon --no-build-cache :mysql-5.5.2-example:cleanTest :mysql-5.5.2-example:test \
  -ProutecontractGenerate552Evidence
```

Candidates are written only to `build/routecontract-552-corpus/` and the existing
`build/routecontract-552-evidence/`. Generation mode omits fixed-file equality checks, so it
cannot serve as acceptance evidence. Review changes to counts, SQL rewrite fingerprints,
parameter shapes and aliases before deliberately editing an expectation. A customer's
operation baseline still requires its own explicit approval.

For exact results and limitations, see the [A-23 evidence note](../../docs/evidence/exact-552-full-corpus-2026-09-07.md).
