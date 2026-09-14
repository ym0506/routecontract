# Keep failure diagnostics in the next version

## Problem for the developer

After a database operation fails, a developer needs its diagnostic snapshot to investigate
what happened. In the unreleased 0.2 core, a worker could report a failure while capture was
closing. The collector could then throw its own `IllegalArgumentException` and discard that
snapshot. This is lost diagnostic evidence, not a contract incorrectly reporting success.

The 0.1.4 release already corrects this problem. The independent 0.2 branch still contained
the old implementation at `09743748824694cf28f761d07cf905e35c2420c0`. This change ports the
same correction and regression test into `routecontract-core`, shared by the exact 5.5.2
and 5.5.3 adapters. It does not publish 0.2 or change the immutable 0.1.4 artifacts.

## Why individual atomic fields were insufficient

The old implementation stored the outcome in an `AtomicReference` and the failure class in a
separate volatile field. Capture closure read them separately. A worker could change both
between those reads, producing an old `START_REPORTED` outcome with a new failure class.
The immutable snapshot correctly rejects that inconsistent pair. Reading the new failure
outcome before the failure-class write could also omit the diagnostic class.

The corrected implementation publishes an immutable `Completion` containing both values in
one compare-and-set operation. Closure reads that reference once. The first terminal callback
wins, and previously frozen snapshots remain unchanged. Only the exception class name is
retained; a null cause keeps the existing null-class policy.

The public API, schema and eligibility rules stay the same. Failure and incomplete captures
cannot become passing contracts. This correction neither waits for outstanding callbacks nor
adds general asynchronous-operation support.

## Reproduce and verify

The regression test was copied from the released-line correction before editing production
code. Against the old 0.2 core, its concurrent case failed with
`reportedFailureType is only valid for CALLBACK_FAILURE`; the first-terminal-callback case
passed. This directly reproduces the internal race.

```bash
./gradlew --no-daemon --no-build-cache --rerun-tasks \
  :routecontract-core:test \
  --tests io.github.ym0506.routecontract.internal.MutableAttemptTest
./gradlew --no-daemon --no-build-cache clean check assemble
python3 -m unittest discover -s submission/tools/tests -v
python3 -m unittest discover -s scripts/tests -v
```

Use the contributor environment for Python test dependencies. Raw Java results are under
`routecontract-core/build/test-results/test`, both adapter modules, and the
`examples/mysql` / `examples/mysql-5.5.2` test-result directories. The exact-result summarizer
and its independent acceptance fixture require the added two-test suite; historical release
test counts remain unchanged.

Local validation on 2026-09-14 used macOS arm64, Gradle 8.14.4 and Temurin
17.0.20.1+1 for compilation and all five test JVMs. `clean check assemble` passed
**782 tests in 26 suites**, including **28 real MySQL tests** across exact ShardingSphere-JDBC
5.5.2 and 5.5.3; there were no failures, errors or skipped Java tests. The fixtures use the
pinned MySQL 8.4.11 image. Both new regression cases passed, including one million race
iterations. The exact-result summarizer accepted all 26 suites.

Evidence labels: `verified - unit`, `verified - MySQL`,
`verified - ShardingSphere-JDBC 5.5.2`, `verified - ShardingSphere-JDBC 5.5.3`.
CI and Python validation results are recorded in the pull request. Before/after logs and
raw XML are retained separately so the passing run does not replace the failure evidence.

## Scope of the evidence

The race test uses one million iterations. It is schedule-dependent; a successful run alone
does not prove every possible interleaving. The consistency argument is the single atomic
publication and single read of an immutable pair.

The real MySQL tests check the existing adapter integration, failure handling, operation
correlation and same-result execution regressions. They do not directly reproduce the
failure/closure overlap in a real database. No production incident, performance gain or
independent-user adoption is claimed.

This change modifies the core JAR. Earlier unsigned 0.2 candidate hashes and consumer results
belong to their original source; they are not verification of these new bytes. The existing
human baseline review, final tagged release, license and public-consumption conditions remain
open. A passing source build does not satisfy those separate release conditions.
