# Current API entry: focused legacy regression, 2026-09-08

The new guarded `io.github.ym0506.routecontract.api.RouteContract` entry passed
**8/8 focused regression cells**: the four real legacy-first inputs that failed
original A-28, each invoked through both `capture` and `captureResult` in a fresh
Java 17 JVM with the exact retained ShardingSphere-JDBC 5.5.2 graph.

**Original A-28 remains FAILED.** Its original direct-old-API observations,
harness and receipts were not changed. This implementation adopts the explicit
[new entry and migration contract](../current-entry-migration-acceptance.md);
it cannot change immutable old bytecode selected by an old-FQCN invocation.
The full successor matrix remains pending review of final candidate bytes.

| Actual legacy JAR first | New `capture` | New `captureResult` |
| --- | --- | --- |
| 0.1.0 | Collision rejected before action | Collision rejected before action |
| 0.1.2 | Collision rejected before action | Collision rejected before action |
| 0.1.3 | Collision rejected before action | Collision rejected before action |
| 0.1.0-rc2 | Collision rejected before action | Collision rejected before action |

Every cell produced `RC_LEGACY_ADAPTER_COLLISION` from the real
`CurrentRuntimeGuard` exception stack, with zero action entries, no returned
result and no linkage failure. Origin observations selected the new entry and
guard from the locally built core JAR while the compatibility entry and collector
still resolved from the actual first legacy JAR. The probe inspected those
origins only after the tested entry; it did not invoke a bootstrap or guard.
No datasource or SQL was executed by this focused regression.

See the [minimized receipt](current-entry-regression-2026-09-08.json). Evidence
labels: `verified - ShardingSphere-JDBC 5.5.2` applies to this exact classpath and
entry-diagnostic observation; `verified - unit` applies to the tests below. There
is no new MySQL, reviewed-staging, public 0.2 distribution or adoption claim.

## Candidate and input binding

- Local core JAR SHA-256:
  `1863b422179b0447035642bfa5a679ffa0f75201ac3bf6c261558f32849ba598`.
- Local sources JAR SHA-256:
  `9744a22c78e9c91376b6f720c7fd8934797fbcd84bff478669165f62b0eaf155`.
- Raw focused summary SHA-256:
  `98ba9bbf0ce9cb7adb788caee877feb5f30399d023ee554832008ce6f4dd0432`.
- Original A-28 summary remains byte-identical:
  `83ffad4b77bd025b8daf953a9d2275447e7e0d0068f82e8850e99a1e42a885c5`.

The separate runner verified all 203 retained graph artifacts, the four actual
legacy JARs and their registry-pinned layouts, and the original four diagnostic
failure observations. Every core JAR class matched its supplied local compiler
output; the sources JAR matched current core Java sources. Source, harness and
input fingerprints were rechecked after execution. These checks bind this local
build; they are not an independent reproducible-build or reviewed staging proof.

The actual Java runtime/compiler was Homebrew OpenJDK 17.0.15. Core compilation,
Javadoc and the external probe compilation succeeded with Java 17; compilation
used `--release 17`, `-Xlint:all` and `-Werror`.

## Focused product tests

- **47 core tests passed**, including 24 new guard/API tests. Isolated core-JAR
  tests deliberately omit TTL: a premature collector initialization would fail
  instead of producing the required collision diagnostic. Tests cover both new
  capture methods, missing adapters, complete startup preflight, legacy class and
  service signatures, resource failures, duplicates, different core origins and
  inspection after a previous successful check.
- **23 capture tests passed**: 19 existing lifecycle/exception/limit assertions
  and four new result/startup compatibility tests. The new tests preserve result
  object identity, checked-exception and error identity, cleanup, and subsequent
  capture after full startup verification. These tests invoke exact-adapter
  callbacks directly; they do not claim database execution.
- **7 harness tests passed**, including tampered core/source inputs and
  observations with action entry, wrong origins or absent guard evidence.
- A small consumer compiled against the actual public **0.1.3** JAR ran its
  unchanged bytecode against the local new core and retained exact **5.5.3**
  graph. Both old-FQCN capture methods entered their no-SQL actions and returned
  expected INCOMPLETE zero-attempt snapshots; result value was preserved.
  `javap -public -s -constants` output for the old entry matched exactly between
  that legacy JAR and the new compatibility facade. This is a focused linking
  check, not a rerun of the full A-26 compatibility gate.

## Reproduction and retained files

Build and test the candidate from its reviewed source checkout:

```sh
JAVA_HOME=/path/to/jdk-17 ./gradlew \
  :routecontract-core:jar :routecontract-core:sourcesJar \
  :routecontract-core:javadoc :routecontract-core:test

JAVA_HOME=/path/to/jdk-17 ./gradlew :routecontract-shardingsphere-5.5:test \
  --tests io.github.ym0506.routecontract.RouteContractTest \
  --tests io.github.ym0506.routecontract.CurrentRouteContractCompatibilityTest

python3 -m unittest discover -s scripts/tests \
  -p test_verify_current_entry_regression.py
```

Run the focused check with the newly built core's explicitly reviewed hashes and
the unchanged retained A-28 evidence. Choose an absent output directory outside
both the checkout and original evidence:

```sh
python3 scripts/verify-current-entry-regression.py \
  --core-jar /path/to/local/routecontract-core-0.2.0.jar \
  --expected-core-sha256 1863b422179b0447035642bfa5a679ffa0f75201ac3bf6c261558f32849ba598 \
  --core-classes-directory /path/to/checkout/routecontract-core/build/classes/java/main \
  --core-sources-jar /path/to/local/routecontract-core-0.2.0-sources.jar \
  --expected-core-sources-sha256 9744a22c78e9c91376b6f720c7fd8934797fbcd84bff478669165f62b0eaf155 \
  --retained-a28-evidence /path/to/original-a28-evidence \
  --evidence-directory /path/to/new-current-entry-evidence \
  --java-home /path/to/jdk-17
```

The actual focused run is retained at
`/private/tmp/routecontract-current-entry-regression-20260908-a`. It includes
commands, local build/source binding, original input verification, compiled
external probe hashes and all eight observations/logs. Exact unit JUnit files,
logs and the old-bytecode source/commands are retained under this checkout's
`build/current-entry-evidence`. Raw artifacts stay local; the JSON linked above
contains minimized evidence without private paths or raw exception messages.

The runner deliberately accepts a retained local dependency graph and has no
public-distribution mode. Its fixed eight-cell result cannot be reported as a
full successor-matrix result. The final 0.2 candidate still needs both runtime
lanes, both JAR orders, clean controls, ordinary-SQL protection, actual MySQL and
full API/migration gates before a release decision.
