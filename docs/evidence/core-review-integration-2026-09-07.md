# Core review report integration verification — 2026-09-07

Status: local integration evidence for the unreleased 0.2 candidate. This is not a release,
Maven Central availability claim, external adoption result, or public-CI result for this revision.

## Source and change boundary

This checkout combines PR #62 head `08cfd1257b088047096a40eb2cb86fc46e69e579` with main
`de3ef507eaf0928670b72ce42d689a2816579d26`, plus the report integration corrections recorded
with this note. Main's report classes and tests belong to `routecontract-core`. The core Gradle
review task has no adapter dependency; the previous 5.5.3 task remains a compatibility alias.

The uncorrected combination failed compilation because the report switch omitted the new
`UNSUPPORTED_RUNTIME_IDENTITY` and `RUNTIME_IDENTITY_MISMATCH` enum values. After temporarily
completing that switch, the adapter report test also failed compilation: its Jackson imports
were no longer available through core's implementation dependency. Moving the tests to core
preserves the dependency boundary. The old test assumption that schema 2 was unsupported has
been replaced with a schema-3 case using the explicit-identity constructor.

Reports now explain `RCM004` and `RCM005`, preserve incompatibility precedence over budgets,
and continue to require a strict match. Tests cover same-runtime schema-2 matches, legacy
schema-1/5.5.3 compatibility, cross-runtime mismatch, unsupported identity, and CLI output.
The 5.5.2 MySQL fixture also emits policy and cross-runtime review reports.

## Environment and reproducible commands

- OS: macOS 26.4.1, arm64.
- Java: Homebrew OpenJDK 17.0.15+0.
- Gradle: repository wrapper 8.14.4, strict dependency verification unchanged.
- Docker server: 29.2.1.
- Database: digest-pinned MySQL 8.4.11 containers from each fixture; no H2 substitution.
- Exact ShardingSphere-JDBC lanes: 5.5.3 and 5.5.2, synchronous non-batch PreparedStatement.

```sh
./gradlew :routecontract-core:test :routecontract-shardingsphere-5.5:test :routecontract-shardingsphere-5.5.2:test --console=plain
./gradlew :mysql-example:test :mysql-5.5.2-example:test --console=plain
```

| Suite | Tests | Failures / errors / skipped | Evidence label |
| --- | ---: | --- | --- |
| core, including 13 review-report tests | 23 | 0 / 0 / 0 | verified - unit |
| exact 5.5.3 adapter | 60 | 0 / 0 / 0 | verified - unit |
| exact 5.5.2 adapter | 24 | 0 / 0 / 0 | verified - unit |
| exact 5.5.3 MySQL fixture | 14 | 0 / 0 / 0 | verified - MySQL; verified - ShardingSphere-JDBC 5.5.3 |
| exact 5.5.2 MySQL fixture | 6 | 0 / 0 / 0 | verified - MySQL; verified - ShardingSphere-JDBC 5.5.2 |

Each suite was run once for this correction. Existing within-test 20-capture determinism and
20-pair isolation repetitions ran as implemented; these do not prove arbitrary concurrency.
Raw JUnit files are under each listed project's `build/test-results/test/TEST-*.xml`.
The Gradle project `mysql-example` maps to `examples/mysql`, and `mysql-5.5.2-example` maps to
`examples/mysql-5.5.2`.

The 5.5.3 report files are in `examples/mysql/build/routecontract-demo/review.{md,json}`.
The 5.5.2 policy and mismatch reports are in
`examples/mysql-5.5.2/build/routecontract-552-evidence/{review,cross-runtime-review}.{md,json}`.
The PR CI upload list now includes core, 5.5.2 adapter, and 5.5.2 MySQL raw JUnit and reports;
a fresh public run is still needed to prove upload on the new revision.

The following core command and compatibility alias both returned zero for an unchanged
schema-2 5.5.2 baseline, and their JSON bytes were identical. Use new output paths on rerun.

```sh
./gradlew --quiet :routecontract-core:reviewManifest -PapprovedManifest=examples/manifests/find-paid-orders-by-user.shardingsphere-5.5.2.schema2.approved.json -PcandidateManifest=examples/manifests/find-paid-orders-by-user.shardingsphere-5.5.2.schema2.approved.json -PreviewReportFormat=json -PreviewReportOutput=build/core-review-match.json
./gradlew --quiet :routecontract-shardingsphere-5.5:reviewManifest -PapprovedManifest=examples/manifests/find-paid-orders-by-user.shardingsphere-5.5.2.schema2.approved.json -PcandidateManifest=examples/manifests/find-paid-orders-by-user.shardingsphere-5.5.2.schema2.approved.json -PreviewReportFormat=json -PreviewReportOutput=build/alias-review-match.json
cmp build/core-review-match.json build/alias-review-match.json
```

The existing Python script regression suite also completed successfully:

```sh
python3 -m unittest discover -s scripts/tests
```

Result: 557 tests run, 554 passed and 3 expected skips, no failures or errors
(`verified - unit`). The preserved log for this local run is
`/tmp/routecontract-pr62-python-verification.log`; raw local MySQL console output is
`/tmp/routecontract-pr62-mysql-verification.log`. These temporary logs are not immutable
publication evidence; the JUnit and reproducible commands above are the retained CI contract.

## Remaining boundaries

This correction does not implement the public split-artifact consumer, publication, or missing
0.2 release gates. The release-evidence workflow's fail-closed 0.2 guard remains intact. The
six-test 5.5.2 fixture is not the full separate route-risk corpus required by ADR acceptance
row A-23; the old-bytecode/public-API migration evidence in A-26 also needs its own audit.
No existing approved baseline or immutable release bytes were rewritten.

Observed evidence remains a ShardingSphere SQLExecutionHook-reported physical JDBC execution
attempt. A report does not establish a complete route plan, transaction commit, business success,
or performance improvement. The real-MySQL tests retain their separate business-result assertions.
