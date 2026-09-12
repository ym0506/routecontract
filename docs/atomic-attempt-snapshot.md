# Preserve diagnostics when a failure overlaps capture closure

## Developer problem

A developer may catch a database exception and then inspect RouteContract's diagnostic
snapshot. If a worker reports a failure while that snapshot is being assembled, the collector
could instead throw `IllegalArgumentException` and lose the diagnostic result. This is an
internal snapshot construction failure, not an incorrectly passing execution contract.

The defect was reproduced against `MutableAttempt` from main
`6f6da9742cc7c479d949dffdd58a0996183e77ca` on 2026-09-12. The published `0.1.3`
implementation also has the two-field layout. The correction described here is **unreleased**;
it does not change the immutable published artifact.

## Cause and correction

Previously, the callback changed an atomic outcome and then wrote a separate volatile failure
class. `freeze()` read those fields separately. A legal interleaving was:

1. Closure reads `START_REPORTED`.
2. A worker records `CALLBACK_FAILURE` and its exception class.
3. Closure reads the non-null exception class.
4. `PhysicalExecutionAttempt` rejects that inconsistent pair.

The reverse partial observation was also possible: a failure outcome before its class was
published. Volatile visibility for individual fields does not make their pair atomic.

`MutableAttempt` now publishes an immutable `Completion` containing both values through one
`AtomicReference`, and `freeze()` reads it once. Compare-and-set from the shared initial state
keeps the first terminal callback. The failure state retains only the exception class name,
never the exception object or message. Null failure causes keep the existing diagnostic policy.

The public API, snapshot schema, capture eligibility rules and support boundary are unchanged.
The change does not wait for outstanding workers or make their execution part of a complete
route plan.

## Regression verification

Evidence labels: `verified - unit`, `verified - MySQL`,
`verified - ShardingSphere-JDBC 5.5.3`, with the separate limits below.

Local environment: macOS 26.4.1 arm64, Gradle 9.7.1, Homebrew OpenJDK 17.0.15,
Temurin 21.0.12.1+1-LTS, Docker Desktop engine 29.2.1, Testcontainers 1.21.4,
ShardingSphere-JDBC 5.5.3, MySQL Connector/J 26.7.0. MySQL uses the fixture's exact
`mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb`
image reference.

| Check | Observed result |
| --- | --- |
| New `MutableAttemptTest`, before changing production code | 2 tests ran; the concurrent test failed with `reportedFailureType is only valid for CALLBACK_FAILURE`; the first-terminal/snapshot test passed. |
| Java 17 `clean check` and official SBOM validation, after correction | 9 suites / 64 tests passed; six SBOM documents validated with pinned CycloneDX CLI 0.33.1. |
| Java 21 core and MySQL tests, library compiled for Java 17 | 9 suites / 64 tests passed. |
| Failure/freeze race inside each runtime run | 1,000,000 iterations per runtime; only coherent start/failure states observed, with the exact failure class required after callback completion. |
| Current summary acceptance tests, Python 3.13.0 | 8 passed; the independent fixture includes the new suite and retains historical contest counts. |

Reproduce the focused unit check with:

```bash
./gradlew --no-daemon --no-build-cache --rerun-tasks \
  :routecontract-shardingsphere-5.5:test \
  --tests io.github.ym0506.routecontract.internal.MutableAttemptTest
```

Run the complete checks from the same checkout with:

```bash
./gradlew --no-daemon --no-build-cache clean check validateOfficialCycloneDxSbom
./gradlew --no-daemon --no-build-cache --no-configuration-cache --rerun-tasks \
  -ProutecontractTestJavaVersion=21 \
  :routecontract-shardingsphere-5.5:test :mysql-example:test
python3 -m unittest discover -s submission/tools/tests -p test_summarize_test_results.py -v
```

Both JDKs must be visible to Gradle; see [contributor requirements](../CONTRIBUTING.md).
Raw JUnit results are written to `routecontract-shardingsphere-5.5/build/test-results/test/`
and `examples/mysql/build/test-results/test/`. Preserve each runtime's results before the
next invocation replaces them. The existing CI uploads the revision-bound XML and environment.
Local before/after logs and separate runtime XML copies are retained outside the repository
under `growth/evidence/atomic-attempt-snapshot-20260912/`; these are maintainer evidence, not
independent-user reports.

## What this establishes

The unit race directly reproduces the old field-level defect. It is schedule-dependent: an
old-code run need not fail every time, and passing a million iterations is not a proof of all
possible schedules. The consistency argument is the single atomic publication and single read
of an immutable pair, supported by the regression test.

The real MySQL suite checks existing failure handling, operation correlation, result-preserving
execution regressions and the independent data-source-proxy comparison. The existing
`FailureBoundaryMySqlTest` fails one physical group; it does **not** directly reproduce this
two-field race. Reachability when multiple physical groups fail and an unjoined callback overlaps
closure remains a `reasoned hypothesis` from the executor and collector paths. No production
incident, latency improvement or broader asynchronous-operation support is claimed.
