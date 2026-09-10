# Java 21 runtime acceptance for public 0.1.3

Status: local checks **verified - unit**, **verified - MySQL**, **verified - ShardingSphere-JDBC 5.5.3**
on 2026-09-10. Acceptance criteria were written before implementation for [issue #84](https://github.com/ym0506/routecontract/issues/84).
The complete CI matrix below is required before merging the support change.

## User-visible requirement

A developer using Java 21 can run the current Maven or Gradle first-project example
against the unchanged Central 0.1.3 artifact and inspect the same meaningful
pass/fail/restore outcomes as Java 17. The example must identify the actual test JVM
and compiled consumer class version, rather than silently run Java 17 from a toolchain.

The current SCG source at `a6ecc490160707722b7f4478354901318f809ea3` declares a JDK 21
migration. Prior SCG/MySQL and Egon/PostgreSQL experiments already ran 0.1.3 on Java 21
under their documented isolated conditions. Those experiments do not establish this
maintained public-consumer workflow or independent adoption.

## Acceptance checks

1. Record the unchanged example's Java 21 rejection before modification. This proves
   an onboarding restriction, not a RouteContract runtime incompatibility.
2. Preserve the released library's production sources and artifact bytes. Compile the
   library for Java 17 and explicitly run existing core and real-MySQL tests on a
   selected Java 21 JVM. Record the launched JVM and actual test results, including
   failure/incomplete-capture boundaries and the existing concurrency fixtures.
3. Run the public Central consumer through Maven and Gradle on Java 17 and Java 21.
   Verify test-JVM feature 17/class major 61 or feature 21/class major 65. The example
   rejects other runtime selections before database startup.
4. In each public-consumer cell, verify the full existing lifecycle: missing baseline
   fails while preserving only a candidate; capture does not approve a baseline;
   equality matches; the range query returns the same exact order before failing with
   RCM201/RCM202 and observed counts 2/2 versus limits 1/1; restoration matches.
5. Verify direct assertions in each cell: pass, expected contract failure after the
   business assertion, restore. Previously existing baseline/candidate/report files
   remain byte-identical. Direct assertions do not create JSON review results.
6. Preserve all existing required Java 17 CI context names. New Java 21 results are
   additional evidence. An infrastructure/setup error must not be accepted as the
   intentional contract failure.
7. Update current 0.1.3 instructions only after these checks pass, with exact tested
   versions, commands, evidence and limits. Historical version-bound Java 17 runners,
   release assets and recorded first outcomes retain their original scope.

## Scope and decision rules

- Exact ShardingSphere-JDBC 5.5.3; synchronous, non-batch PreparedStatement operations.
- Observe SQLExecutionHook-reported physical JDBC execution attempts, not a complete
  route plan, physical-table count, transaction commit or measured latency change.
- The existing test scenarios qualify their own concurrency boundaries. They do not
  establish arbitrary async or virtual-thread propagation.
- A failure remains a failure until its cause is identified; do not lower assertions,
  approve expected manifests, replace released artifacts, or widen a claim to obtain a
  green runtime matrix.
- No 0.2 expectation approval, signing, upload or publication is part of this change.
- Author-run compatibility evidence is separate from independent integration/reuse.

## Recorded local results

Environment: macOS 26.4.1/aarch64, Homebrew OpenJDK 21.0.11 test runtime,
OpenJDK 17.0.15 library compiler, Maven 3.9.14, Gradle 8.14.4, ShardingSphere-JDBC
5.5.3 and MySQL 8.4.11. Each lifecycle was run once per build tool; each core/MySQL
suite was run once on Java 21. Repetitions inside those existing suites remain unchanged.

| Check | Observed result |
| --- | --- |
| Original example on Java 21 | Rejected before DB startup by the explicit Java 17 guard; one JUnit setup error, not a library incompatibility finding |
| Existing core tests on Java 21 | 48 tests, zero failures/errors/skips |
| Existing real-MySQL tests on Java 21 | 14 tests, zero failures/errors/skips |
| Maven public 0.1.3, Java 21 | Direct assertions: pass (1/1), expected contract failure (2/2), restore pass (1/1); exact order asserted in every run |
| Gradle public 0.1.3, Java 21 | Same three direct-assertion outcomes; both build tools preserved all existing manifest/report files |
| Actual runtime | Two native core/MySQL test-worker launches used Java 21; consumer class major 65, library class major 61 |
| Verifier negative controls | Java 17 executable and a synthetic log without worker launches were each rejected; neither produced a success summary |

The library's production sources are unchanged. Both public consumers verify this immutable
[Central 0.1.3 JAR checksum](https://repo.maven.apache.org/maven2/io/github/ym0506/routecontract/routecontract-shardingsphere-5.5/0.1.3/routecontract-shardingsphere-5.5-0.1.3.jar.sha256):

```text
9e883e618eb09d9ecf30814151bb4b0a43eba02c78d288cc582fa7e57e6edba2
```

Local raw logs, original JUnit and verifier-control records are retained privately under
`java21-public-runtime-2026-09-10/`. Native runtime summaries and minimized JUnit retain case
identities and outcomes while omitting framework stdout/stderr and connection details.

## Maintained CI and reproduction

[First project workflow](../.github/workflows/first-project.yml) runs these checks on each PR
and main push. [Run history](https://github.com/ym0506/routecontract/actions/workflows/first-project.yml)
records the tested commit and individual job results; PR checks are the merge evidence.

| Cell | Runtime configuration | Artifact |
| --- | --- | --- |
| Maven / Java 17 | Temurin `17.0.20+101`, Maven 3.9.14 | `first-project-Maven` |
| Gradle / Java 17 | Temurin `17.0.20+101`, Gradle 8.14.4 | `first-project-Gradle` |
| Maven / Java 21 | Temurin `21.0.12+8.0.LTS`, Maven 3.9.14 | `first-project-Maven-java21` |
| Gradle / Java 21 | Temurin `21.0.12+8.0.LTS`, Gradle 8.14.4 | `first-project-Gradle-java21` |
| Core and real MySQL / Java 21 | Java 17 library compiler, Java 21 test workers | `java21-core-mysql-runtime` |

Each public consumer verifies the missing-baseline/capture boundary, three JSON comparison
stages, and three direct-assertion stages. Its `build/lifecycle-evidence/direct-assertions/`
contains `summary.json`, per-stage logs and JUnit. The summary records the actual Java feature,
consumer/library class versions, public JAR hash, counts, expected failure and protected-file hashes.
The native artifact contains `java21-runtime-summary.json` and minimized `core.xml`/`mysql.xml`.
A configured version alone is not a passing runtime result.

For the public example, use the [Maven/Gradle walkthrough](first-project.md). With `JAVA_HOME`
pointing to Java 21, the existing direct lifecycle verifier can also be run from the repository root.
If Maven previously compiled this checkout on a different JDK, first preserve any needed generated
reports and run `mvn -B -f examples/first-project/pom.xml clean`; Maven incremental compilation
can otherwise reuse the previous class version:

```bash
ROUTECONTRACT_EXAMPLE_JAVA_VERSION=21 python3 submission/tools/verify_first_project_direct_assertions.py Maven
ROUTECONTRACT_EXAMPLE_JAVA_VERSION=21 python3 submission/tools/verify_first_project_direct_assertions.py Gradle
```

For native core/MySQL verification, install JDKs 17 and 21, set `JAVA_HOME` to Java 21 and
`ROUTECONTRACT_COMPILER_HOME` to Java 17, then run from the repository root with Docker available:

```bash
mkdir -p build
./gradlew --no-daemon --no-build-cache --no-configuration-cache --rerun-tasks --info \
  -ProutecontractTestJavaVersion=21 \
  "-Porg.gradle.java.installations.paths=${ROUTECONTRACT_COMPILER_HOME},${JAVA_HOME}" \
  -Porg.gradle.java.installations.auto-detect=false \
  -Porg.gradle.java.installations.auto-download=false \
  :routecontract-shardingsphere-5.5:test :mysql-example:test > build/java21-runtime.log 2>&1
python3 submission/tools/summarize_java_runtime.py \
  build/java21-runtime.log "$JAVA_HOME" build/java21-runtime-summary.json
```

Keep the Gradle command's exit status as part of the result; a summary does not override a failed
build. Review the raw log privately if the build fails. No new library release or reviewed
application baseline is created by these commands.
