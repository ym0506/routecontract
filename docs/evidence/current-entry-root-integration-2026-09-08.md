# Current entry: integrated-source verification, 2026-09-08

After integrating the reviewed current-entry implementation, **163 tests passed**
with no failures, errors or skips across the core, both exact adapters and both
real-MySQL examples. This is local integrated-source verification, separate from
the [eight focused legacy regressions](current-entry-regression-2026-09-08.md).

| Module | Tests |
| --- | ---: |
| Core | 47 |
| ShardingSphere-JDBC 5.5.3 adapter | 64 |
| ShardingSphere-JDBC 5.5.2 adapter | 24 |
| Real MySQL / 5.5.3 example | 14 |
| Real MySQL / 5.5.2 example | 14 |

The real-MySQL fixtures exercise the existing compatibility facade, which now
delegates to the new entry on clean split graphs. They retain the business-result
assertions and existing regression controls, including eight corpus cases each
repeated twenty times in each exact version lane. They do not inject legacy JARs
into the MySQL process or replace the required full successor collision matrix.

Environment: Homebrew OpenJDK 17.0.15, Gradle 8.14.4 and MySQL 8.4.11 at the
immutable image digest recorded in the [receipt](current-entry-root-integration-2026-09-08.json).
Labels: `verified - unit`, `verified - MySQL`,
`verified - ShardingSphere-JDBC 5.5.3`, `verified - ShardingSphere-JDBC 5.5.2`.

```sh
JAVA_HOME=/path/to/jdk-17 ./gradlew --no-daemon --console=plain --no-build-cache \
  :routecontract-core:test :routecontract-shardingsphere-5.5:test \
  :routecontract-shardingsphere-5.5.2:test \
  :mysql-example:test :mysql-5.5.2-example:test
```

The command exited 0. Its raw log is retained locally at
`/private/tmp/routecontract-current-entry-root-integration-20260908.log`;
the receipt records its SHA-256, the integrated source hashes and individual
JUnit XML hashes. Source files were unchanged from the independently reviewed
agent handoff when the integrated test ran. The repository-wide strict test summary was then updated to include the three
new suites; its unexpected-suite and historical-summary rules remain unchanged.

**Original A-28 remains FAILED.** The new API has a separately documented
[migration contract](../current-entry-migration-acceptance.md). This integrated
run does not prove final staged bytes, public 0.2 distribution or external use.

## Direct current-API MySQL follow-up

The current 0.2 MySQL fixtures subsequently changed their imports to
`io.github.ym0506.routecontract.api.RouteContract`. Both real-MySQL test tasks
reran on the same Java/Gradle/database environment: **28 tests passed**, with no
failures, errors or skips. Core and adapter bytecode did not change.

```sh
JAVA_HOME=/path/to/jdk-17 ./gradlew --no-daemon --console=plain --no-build-cache \
  :mysql-example:test :mysql-5.5.2-example:test
```

The strict summary accepted the retained 135 core/adapter tests together with the
28 rerun MySQL tests: 23 suites and 163 tests. This is a combined local result,
not a claim that all 163 tests reran in the follow-up. Eight summary unit tests
passed. JUnit inputs, the follow-up log and source hashes are retained at
`/private/tmp/routecontract-current-entry-direct-mysql-evidence-20260908` and
recorded in the receipt's `directCurrentApiFollowup` field.

Current 0.2 Gradle/Maven/staged/standalone consumer source imports were also
updated. Their final staged-artifact executions remain pending; the old staging
receipt predates the new API and cannot validate those updated consumer sources.
