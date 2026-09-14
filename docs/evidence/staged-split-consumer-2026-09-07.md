# Independent staged-artifact consumer verification — 2026-09-07

Status: `verified - MySQL` on local and CI-staged bytes; unreleased 0.2 development evidence.
No Maven Central availability, anonymous public consumption, external user, full route-risk matrix,
or release-readiness claim is made. The 0.2 release-evidence fail-closed guard is unchanged.

## What this adds

The existing split probes checked an empty capture, and the existing Gradle split fixture substituted
source projects. This fixture instead copies an independent consumer and wrapper outside the source
checkout, resolves only the packaged core plus selected adapter from a supplied staging directory,
and runs a real MySQL candidate assertion. The harness does not build or publish RouteContract.

First-party implementation bytes came from `008e125a0648ed615842a572d60fd453698bb5aa`, prepared by
`publishRouteContractCentralStaging` with signing disabled. The staged repository was unchanged
throughout the final harness run. Its nine core/adapter JAR/POM/module hashes were inserted into a
copy of the existing strict verification metadata. Each exact runtime had its own initially absent
Gradle user home and its own reviewed dependency lockfile. No verification bypass, Maven Local,
project dependency, composite build or first-party public-repository fallback was used.

## Verified behavior

| Runtime | Selected ShardingSphere components | Real MySQL tests | Graph rejection cases | Failures/errors/skips |
| --- | ---: | ---: | ---: | --- |
| exact 5.5.2 | 122, all 5.5.2 | 3 | 5 | 0 / 0 / 0 |
| exact 5.5.3 | 75, all 5.5.3 | 3 | 5 | 0 / 0 / 0 |

Each lane verified:

- executing core and hook provider JAR filenames and SHA-256, plus unique matching hook discovery;
- an unchanged operation returning the exact immutable row `(order_id=201, user_id=3, status=PAID)`
  and one reported physical JDBC execution
  attempt, byte-identical to the existing reviewed schema-2 baseline and classified MATCH;
- a range predicate returning the same row while reported attempts increase from one to two;
  the candidate assertion throws and both CLI report formats return strict exit 1 with
  POLICY_VIOLATION, RCM201 and RCM202;
- a distinct bound-string privacy control changes the business result without entering canonical
  execution evidence; expected SQL literals, parameters and raw data-source names stay out of the
  minimized public fixture reports;
- wrong runtime/non-anchor requests rejected through the whole-group exact-version policy;
  both ordinary adapter dependency orders rejected through the published default shared capability
  without custom capability requests; a pre-0.2 all-in-one
  request rejected by consumer policy before artifact resolution.

Those last five are graph-policy cases. They do not prove manually assembled legacy-classpath
behavior or replace the separately required ABI, loader, module-path and migration tests.

The final fresh-cache run executed each lane once. Prior development runs established the same
scenario and generated reviewed lockfiles. This is not an arbitrary concurrency or performance
claim. The supplied reviewed baseline resources were copied unchanged; no candidate became an
approved baseline automatically.

## Reproduction and raw evidence

Use the exact recipe in the [consumer README](../../examples/staged-split-artifact-consumer/README.md).
For this local run:

```sh
python3 scripts/verify-staged-split-artifact-consumer.py --repository /private/tmp/routecontract-staged-consumer-008e125/repository --evidence-directory /private/tmp/routecontract-staged-consumer-008e125/evidence-final
python3 -m unittest discover -s scripts/tests -p test_verify_staged_split_artifact_consumer.py
```

The second command passed all eight integrity/evidence tests (`verified - unit`). They cover
missing coordinates, symlinked payloads, changed bytes despite unchanged filenames, preservation
of third-party trust hashes, empty/skipped/partial/failed JUnit, failure artifact retention and
persisted output on timeout. Available JUnit, generated reports, locks and metadata are retained
even when the Gradle command fails.

Final run artifacts under `/private/tmp/routecontract-staged-consumer-008e125/evidence-final/`:

- `summary.json`: 2 lanes, 6 MySQL tests, 10 graph cases, public consumption explicitly false;
- `staged-receipt.json`: all nine supplied JAR/POM/module SHA-256 values;
- `<runtime>/gradle.log`, `junit/TEST-io.github.ym0506.routecontract.consumer.StagedArtifactMySqlTest.xml`;
- `<runtime>/reports/resolved-graph.txt`, `negative-graphs.txt`, and `reports/<runtime>/` baseline/candidate/review outputs;
- `<runtime>/gradle.lockfile`, `verification-metadata.xml`, consumer build/settings inputs.

Environment: macOS 26.4.1 arm64, Homebrew OpenJDK 17.0.15+0, Gradle wrapper 8.14.4,
Docker 29.2.1, Testcontainers 1.21.4, and two containers per lane of
`mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb`.
These local paths are temporary; commands and source tests provide reproduction, not an immutable
public run. Ordinary CI invokes this harness after preparing its own coordinated staging files;
the CI receipt identifies the checked-out revision independently of this local run.

## Public CI follow-up

[CI 34106764778](https://github.com/ym0506/routecontract/actions/runs/34106764778) passed all five
jobs for PR head `0f0a0caab3d6c3176d0e8c5eb8731e16f96054a0`. Its tested merge
`b7d64ac2ad7315a11490bb317ad877c4c105cd73` has the same tree
`42852caaf2d406c6f2c082698555a811f49eb34c` as that head.

The [staged-consumer artifact](https://github.com/ym0506/routecontract/actions/runs/34106764778/artifacts/10013680934)
contains two raw JUnit suites with six tests and zero failures/errors/skips; its summary records all
ten graph rejection cases. The candidate, reviewed baseline and Markdown/JSON report files for both
exact runtimes are byte-identical to the eight corresponding files from the local run above.
This comparison is limited to those fixtures and the two recorded environments.

The [main test artifact](https://github.com/ym0506/routecontract/actions/runs/34106764778/artifacts/10013679868)
separately contains the 20-suite/135-test core, adapter and versioned-MySQL result summary, plus one
same-checkout publication-consumer test; all 136 raw test results passed without skips. The
[v0.1.2 installed-consumer artifact](https://github.com/ym0506/routecontract/actions/runs/34106764778/artifacts/10013680361)
contains nine passing tests across Gradle Groovy, Kotlin DSL and Maven. These groups cover different
consumer paths and must not be relabeled as independent users or a Central release. The later Maven
staged-consumer and A-26 additions are not part of this run.

Observed evidence is a ShardingSphere SQLExecutionHook-reported physical JDBC execution attempt.
It is not a complete route plan, transaction result, business success, or measured performance.
