# Final packaged runtime binding for the existing MySQL corpus

Retained result: packaged runtime binding for producer `86a0be5` was verified on
2026-09-08. All 28 existing MySQL tests in six suites passed against its reviewed
local 0.2.0 JARs. The separate
authentic human review remains pending: `humanReview: null`, `fullA23Complete:
false`, and `publicConsumption: false`. See the [execution evidence](evidence/packaged-corpus-final-86a0be5-2026-09-08.md).
No workloads or goldens were added or regenerated.

The dependency correction changes the 5.5.2 source build and lock inputs at
`5fdfc3dcd3f4190e4c2b9e381b0b096169b387bb`. The corresponding input fingerprints
were independently reviewed; all test methods, resources and expected values remain unchanged.
Its passing source-project tests do not replace a new packaged execution on the
corrected inputs. That execution is pending, and the recorded result below keeps
its original producer, receipt and dependency graph.

## Fixed scope

Use Java 17 and the checksum-pinned Gradle 8.14.4 distribution. Run two standalone
consumers sequentially: exact ShardingSphere 5.5.3 with the four existing suites
under `examples/mysql` (14 tests), and exact 5.5.2 with the two suites under
`examples/mysql-5.5.2` (14 tests). The exact class/method allowlist and original
source/resource hashes are frozen in `examples/packaged-corpus-consumer/expected-corpus.json`.

The existing corpus assertions retain safe controls, route-risk mutations,
expected business results, failure/ineligibility boundaries, secret minimization,
the 5.5.3 datasource-proxy comparison, and version-specific golden observations.
Each runtime retains its eight-shape × 20-repetition structural-signature check
and 20 concurrently open caller-capture pairs. Physical callback overlap is not
forced or measured; arbitrary async or application concurrency is outside scope.

## Independent packaged consumption

Before execution, require an independently supplied receipt path, expected
SHA-256, and full staged source revision. Validate all nine unique coordinate-bound
JAR/POM/module payloads, their actual repository bytes, and the unchanged
production/publication source binding. Do not derive approval from a freshly
computed receipt hash. The executed reviewed source is `86a0be5d2e444f3b73925122fa448d9d1a324edd`;
the independently supplied receipt digest is
`1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e`.
The earlier `4e06694` candidate was used for preparation only; no full corpus
execution occurred on that candidate.

Each consumer and dependency cache must begin absent. Copy the original tests,
resources, and manifest inputs byte-for-byte into a disposable consumer, retain
the copy mapping, and recheck original and copied inputs after execution.
Preserve each original Gradle dependency declaration except for replacing its
single adapter project dependency with the reviewed Maven coordinate. Preserve
the original complete third-party lock entries and add only the reviewed core
and selected adapter coordinates. Strict locks must match the full selected
compile/runtime graphs; project components, production class directories,
unreviewed first-party artifacts, or mixed ShardingSphere versions must fail.
First-party resolution is exclusive to reviewed staging; other modules use
ordinary HTTPS Maven Central with existing strict verification metadata.

A separate supplemental JUnit extension adds no test cases. It runs before and
after each existing suite in that suite's test JVM, verifies the current
`io.github.ym0506.routecontract.api.RouteContract` entry, core, selected hook and
SPI descriptor originate in the exact expected JARs, and records JAR SHA-256,
code-source paths, class-loader/JVM identity and suite identity. It must not
instantiate additional hooks or replace corpus assertions. The actual test
runtime classpath and selected artifact inventory are retained separately.

Force `routecontract.generate552Evidence=false` and reject the opt-in project
property. Ordinary existing tests may write their observations/reports to build
output, but their golden comparisons must execute and golden inputs must remain
unchanged. `humanReview` remains `null` even when every test passes.

## Required evidence and failure handling

Require the exact 28 JUnit class/method identities with no additional cases,
duplicates, failures, errors or skips. Verify the existing output markers and
version-specific report/golden comparisons; bind repetition/isolation claims to
their exact unmodified test source and successful JUnit case, including cases
whose source prints no marker. Retain actual commands, exits, Gradle version,
full selected graphs and artifact hashes, same-JVM provenance, JUnit XML,
standard output, all generated observations/reports, original/copy inventories,
strict locks/metadata and wrapper identity.

At completion recheck receipt bytes, all staged payloads and repository inventory,
source binding, every executed fixture/helper file, and all original/copy inputs.
After the second lane, revalidate both retained lanes, including their commands,
logs and exits, JUnit, provenance, consumer inputs, selected JAR bytes and outputs.
Only the final packaged runtime binding can become complete. The result must
leave full A-23/human approval/public consumption false or pending as appropriate.
No source-project MySQL result may substitute for this packaged execution.

Before the full runtime run: implement focused meaningful regressions for exact
JUnit/provenance/hash/graph/copy/generation checks, perform independent read-only
review, freeze all inputs and record a run-ready handoff. Preserve a failed
attempt honestly. An observation timeout does not authorize restarting a live
run; any retry needs a diagnosed terminal cause and new evidence directory.

No offline, additional JDK, production build, signing, release, publication or
user-adoption claim belongs to this check. Raw SQL/bind/connection details remain
private; public evidence must contain minimized outcomes and hash bindings only.

## Retained result for producer 86a0be5

The two sequential Java 17 consumers completed once, with exit 0 and full output
retained. ShardingSphere 5.5.3 passed the four existing suites / 14 tests, and
5.5.2 passed the two existing suites / 14 tests. There were zero failed, skipped,
missing or additional cases. The provenance extension contributed zero tests.

Independent read-only audit verified all 39 original inputs, 16 executed
fixture/helper files, 54 applicable original-copy occurrences, 74 consumer-input
hashes, 633 compile/runtime graph artifact occurrences and 349 runtime-classpath
JAR occurrences. All 12 class-level before/after provenance records matched the
reviewed core/adapter JARs and current API in the actual suite JVMs. All 14
5.5.2 corpus golden comparisons and 11 generated report/demo files were retained
and checked; no golden input changed. Both lanes and global inputs passed final
closure checks after all execution.

Each original corpus's eight shapes × 20 repetitions and each runtime's 20
concurrently open caller-capture pairs are bound to their successful original
JUnit method and unchanged test source. The report checks use the report API;
this run does not establish a standalone CLI result. Technical golden comparison
and packaged-runtime verification do not complete the separate human baseline
review. No public-consumption, extra-JDK, offline, or physical callback-overlap
claim follows from this result.
