# Public v0.1.3 first-project acceptance

Status: implemented; local lifecycle verified below. This specification preceded the example.

## User outcome

A developer can run one standalone project with the released Central dependency, preserve an exact
business-result assertion, inspect a candidate, compare against a separately reviewed synthetic
baseline, and understand a failing CI check when a query change increases observed execution.

## Required behavior

1. `examples/first-project` builds independently of the RouteContract source build using Maven or
   the repository Gradle wrapper with its own settings. Both use the same Java 17 test source and
   checked-in synthetic baseline. Dependency repositories are public Maven Central; RouteContract
   is `io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.3`, test scope.
2. Exact ShardingSphere-JDBC 5.5.3 and MySQL 8.4.11 Testcontainers execute synchronous non-batch
   PreparedStatement calls. An existing assertion checks the exact returned synthetic order.
3. Capture mode writes only an unapproved candidate. It never writes or replaces the baseline.
   The synthetic baseline has a separate provenance/review explanation. Adapting the test to an
   external project requires that project's authorized maintainer to review its own baseline.
4. Check mode defaults to the equality query and fails unless the approved baseline matches.
   It writes candidate, Markdown review and JSON review before the route assertion.
5. The intentional range query returns the same exact business row but observes two physical
   JDBC execution attempts instead of one. The ordinary build fails with POLICY_VIOLATION,
   RCM201 and RCM202. The example must not swallow this exception to produce a green build.
6. Repeated capture/check/range invocations do not reuse stale Gradle test outputs or approve
   a candidate. Maven and Gradle produce equivalent candidate/report content.
7. A normal CI job runs check mode and retains Markdown/JSON when the test fails. Missing
   baseline and invalid mode/query must produce actionable errors, never silently capture.
8. Example Java classes use the repository's `io.github.ym0506.routecontract.*` namespace so the
   existing source-archive installer contract accepts a normal archive of the repository. Package
   alignment must preserve operation IDs, SQL, baseline bytes and native Maven/Gradle results.
9. A visitor can fork the repository and manually run **First project** with a browser and a
   GitHub account that can run Actions. Hosted execution needs no locally installed Java, Docker
   or build tool. Manual runs default to Maven and allow Gradle or Both; push and pull-request
   runs retain both build tools. A manual run must not cancel automatic CI on the same ref.
10. The run summary distinguishes normal MATCH, the expected same-result POLICY_VIOLATION,
    and restored MATCH. It uses reports retained only after each step's assertions succeed,
    together with the actual step outcomes. Missing, malformed or unverified reports cannot
    produce a completed demonstration. Infrastructure/compiler failures remain failures.
    All three stage reports are retained as artifacts; baseline bytes remain unchanged.
11. English and Korean entry points explain how to run in the visitor's own fork, interpret
    the green demonstration, retrieve reports and then adapt one real test. This synthetic
    rehearsal does not approve a user's baseline or establish independent adoption.

## Verification record

Record the actual commands, build exits, Docker/MySQL and Java/build-tool versions, baseline hash
before/after, observed counts/status, and raw log locations after implementation. A separate test of
this synthetic fixture may review and use the already approved fixture baseline; it does not prove
human approval or adoption in any external project. Evidence labels: `verified - MySQL` and
`verified - ShardingSphere-JDBC 5.5.3` only after actual database execution.

This example observes hook-reported physical JDBC execution attempts. It does not prove a complete
route plan, physical table count, transaction commit, business success from callbacks, performance,
or independent external adoption. Business success is asserted separately in the test.

## Initial local verification — 2026-09-08 (before namespace alignment)

**verified - MySQL; verified - ShardingSphere-JDBC 5.5.3.** Maintainer-owned synthetic
fixture execution on macOS 26.4.1/aarch64, Homebrew Java 17.0.15, Docker Desktop engine 29.2.1,
MySQL 8.4.11 pinned to
`sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb`.

Both build tools resolved the public dependency into initially empty resolver caches. The sole
RouteContract JAR in each cache was `routecontract-shardingsphere-5.5-0.1.3.jar`, SHA-256
`9e883e618eb09d9ecf30814151bb4b0a43eba02c78d288cc582fa7e57e6edba2`.
The Maven resolver origin record says `central`; no RouteContract project build or local publish
was used. The observed Maven test classpath had 75 ShardingSphere artifacts, all version 5.5.3.
The actual Gradle `testRuntimeClasspath` resolution selected 148 external modules, including
75 ShardingSphere modules, all 5.5.3, and only the RouteContract 0.1.3 module above. An offline
resolution task read the same primed Gradle cache and unchanged build files after the database
runs; it did not rerun tests. The sorted module-identity file has SHA-256
`5ae791c9d144eceb2b124b8dee17caec2cba7ebda834c804fe2d1e3849c6edbf`.

| Command case | Maven 3.9.14 | Gradle 8.14.4 | Observed result |
| --- | --- | --- | --- |
| Default check | exit 0 | exit 0 | Exact business row passed; 1 attempt; MATCH |
| Missing baseline check | exit 1 | Not separately run | Candidate preserved; no baseline or review files created |
| Capture | exit 0 | exit 0 | Candidate only; proposed budgets checked; no baseline approval |
| Separate synthetic reviewed copy | exit 0 | Uses shipped reviewed fixture | MATCH; copy equals the previously reviewed fixture content |
| Intentional range query | exit 1 | exit 1 | Same exact business row; 2 attempts; POLICY_VIOLATION; RCM201 and RCM202 |
| Invalid mode `chek` | exit 1 | Not separately run | Clear error before Docker setup; candidate/reports absent |
| Return to equality | exit 0 | exit 0 | Both tools executed again and returned to MATCH |

The range JUnit reports from **both tools** contain one test, one failure, zero errors and zero
skips; the failure is `io.github.ym0506.routecontract.RouteContractViolationException` from
`paidOrdersKeepTheirBusinessResultAndExecutionContract` (Gradle appends `()`). This binds the
intentional nonzero build result to the route assertion, rather than a dependency or Docker error.
Maven and Gradle equality/range candidates and both report formats were byte-for-byte equal.
The shipped baseline retained SHA-256
`a082ca797ebe40be5b8c9409893de7d9a861086d8d4b760cbc00e925b2436a60` throughout.

Reproducible commands, from `examples/first-project`, after selecting a Java 17 JDK:

```bash
mvn -B test
mvn -B test -Droutecontract.mode=capture
mvn -B test -Droutecontract.query=range
../../gradlew -p . test --rerun-tasks
../../gradlew -p . test --rerun-tasks -ProutecontractMode=capture
../../gradlew -p . test --rerun-tasks -ProutecontractQuery=range
```

The range commands intentionally exit nonzero; run them individually. The guide supplies the
separate review step and missing-baseline path. The local verification used `-B -ntp` and
`-Dmaven.repo.local=/private/tmp/routecontract-first-project-evidence-20260908/m2` with the Maven
binary `/opt/homebrew/Cellar/maven/3.9.14/libexec/bin/mvn`; Gradle used `--no-daemon --console=plain`
and `GRADLE_USER_HOME=/private/tmp/routecontract-first-project-evidence-20260908/gradle-home`.
For both tools, `JAVA_HOME` was
`/opt/homebrew/Cellar/openjdk@17/17.0.15/libexec/openjdk.jdk/Contents/Home`.

Raw local evidence is retained at `/private/tmp/routecontract-first-project-evidence-20260908/`:
`run-records.json` records the exact nine lifecycle commands, exits, durations and parsed reports;
`public-artifacts.json` records the resolved release JAR identities;
`gradle-resolved-runtime.txt`, its `.log` and `gradle-resolved-runtime-summary.json` retain the
actual selected runtime graph, exact resolution command, counts and digest; each named run has a raw `.log`
and copied candidate/reports. The supplemental `maven-range-junit/` and `gradle-range/` directories
retain actual range JUnit XML for the workflow assertions. `maven-check.log` records the initial
fresh-cache run; `maven-restored-check.log` records the final ordinary Maven check. These local
paths are maintainer audit records, not public downloads or external-user evidence.

Limitations: this is one deterministic synthetic MySQL fixture, not general compatibility,
performance or external adoption evidence. Reports are cleared when JUnit setup runs; dependency
or compiler failures occur before that cleanup. CI starts from a clean checkout, and local users
must not treat earlier report files as evidence for a build that failed before tests started.


## Namespace alignment verification — 2026-09-08

**verified - MySQL; verified - ShardingSphere-JDBC 5.5.3.** PR #69's legacy source-archive
installer test rejected the example's initial `example` package. The example now follows the
repository namespace convention: `io.github.ym0506.routecontract.examples.firstproject`.
The installer check remains unchanged. A byte comparison against the previous commit confirmed
that all three Java sources changed only their package declaration and path; SQL, operation IDs,
policies and the baseline remained unchanged.

The initial evidence above remains historical evidence for the previous namespace. The final
namespace was compiled from clean test output and executed again against the same public dependency
caches, Java 17.0.15, MySQL 8.4.11 and ShardingSphere-JDBC 5.5.3:

| Final namespace command | Maven 3.9.14 | Gradle 8.14.4 | Result |
| --- | --- | --- | --- |
| `clean test` | exit 0 | exit 0 | One test; exact business row; 1 attempt; MATCH |
| `test` with the range query option | exit 1 | exit 1 | One route assertion failure; same exact business row; 2 attempts; RCM201/RCM202 |
| `test` without the range option | exit 0 | exit 0 | One test executed again; MATCH restored |

Exact final JUnit class:
`io.github.ym0506.routecontract.examples.firstproject.OrderContractTest`.
Both range JUnit files report one test, one failure, zero errors and zero skips, with failure type
`io.github.ym0506.routecontract.RouteContractViolationException`. Every equality/range candidate,
Markdown report and JSON report was byte-for-byte identical to the corresponding earlier namespace
result. The shipped baseline retained SHA-256
`a082ca797ebe40be5b8c9409893de7d9a861086d8d4b760cbc00e925b2436a60`.

The six final-namespace runs are retained separately at
`/private/tmp/routecontract-first-project-evidence-20260908/namespace-aligned/`.
Its `run-records.json` records exact commands, cache locations, Java home, build exits, durations
and observed statuses/counts. Each run directory retains `run.log`, the final-class JUnit XML,
`candidate.json`, `review.md` and `review.json`; `summary.json` records the namespace and byte-parity
checks, and `source-files.json` identifies the reviewed final source files. Maven reused the
recorded public Maven cache. Gradle reused the recorded public Gradle cache with
`--no-daemon --console=plain --rerun-tasks`; each tool began with `clean test` to remove old compiled
classes. Historical raw evidence was preserved. The source-archive installer regression is a
separate repository check; these database runs do not substitute for it.
