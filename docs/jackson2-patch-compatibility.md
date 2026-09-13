# Jackson 2 patch compatibility

This change qualifies Jackson **2.18.10** for the ShardingSphere-JDBC **5.5.3**
example and test graphs. The previous selection was 2.18.9. This is the patch
line identified by the [upstream 2.18.10 release notes](https://github.com/FasterXML/jackson/wiki/Jackson-Release-2.18.10),
including the [databind base-type advisory](https://github.com/FasterXML/jackson-databind/security/advisories/GHSA-gx83-3vf8-gh7j).
It does not establish that a vulnerable deserialization path is reachable in a
RouteContract operation or that every dependency is free of advisories.

## Acceptance criteria

- Current Gradle and Maven fixtures select Jackson 2 core, databind and Java 8
  datatype modules at 2.18.10. Existing Jackson 3/annotations resolution rules
  remain explicit rather than assuming every Jackson coordinate shares a version.
- Strict Gradle lock and checksum verification succeeds without update flags.
  New artifact checksums are corroborated against separate HTTPS Central reads.
- Core and real-MySQL tests pass on Java 17 and Java 21. Public Central consumers
  retain their business assertions and demonstrate the expected execution-change
  rejection and recovery with the unchanged RouteContract 0.1.3 JAR.
- The isolated Maven/Kotlin compatibility fixtures retain their origin,
  failure-before-operation and baseline-review checks with the updated graph.
- Generated publication metadata does not add Jackson 2 as a RouteContract
  runtime dependency. No previously published artifact or evidence is rewritten.

## Local qualification

`verified - MySQL` and `verified - ShardingSphere-JDBC 5.5.3`: on macOS with
Gradle 9.7.1, Homebrew OpenJDK 17.0.15 and 21.0.11, and the pinned MySQL 8.4.11
image, each JDK passes 48 core tests and 14 MySQL tests with no failures, errors
or skips. This is maintainer-run synthetic integration evidence.

With JDK 17 selected in `JAVA_HOME` and on `PATH`, the root command is:

```sh
./gradlew --no-daemon --no-build-cache --no-configuration-cache \
  --dependency-verification=strict clean check assemble \
  validateOfficialCycloneDxSbom
```

To repeat the core/MySQL tests using an installed JDK 21 while retaining the
JDK 17 compilation target:

```sh
./gradlew --no-daemon --no-build-cache --no-configuration-cache \
  --dependency-verification=strict --rerun-tasks \
  -ProutecontractTestJavaVersion=21 \
  -Porg.gradle.java.installations.paths=/absolute/jdk17,/absolute/jdk21 \
  :routecontract-shardingsphere-5.5:test :mysql-example:test
```

The public Central 0.1.3 standalone consumer and the same-checkout publication
consumer each pass their one real-MySQL JAR/SPI/capture test:

```sh
./gradlew --no-daemon --no-build-cache --no-configuration-cache \
  --dependency-verification=strict -p examples/standalone-consumer \
  -ProutecontractGroup=io.github.ym0506.routecontract \
  -ProutecontractVersion=0.1.3 \
  -ProutecontractRepository=https://repo.maven.apache.org/maven2 clean test
./scripts/verify-standalone-consumer.sh
```

All 18 unique added artifact checksums match separate HTTPS Maven Central
reads. Existing checksum entries and verification policies remain unchanged.
The first ordinary root run correctly rejected five missing POM checksum
entries needed by SBOM generation. The first refreshed standalone run rejected
two missing parent POM entries. Those exact files were corroborated before
adding their hashes; both commands then passed without verification-writing
flags. This is why metadata generation alone is not the acceptance check.

Generated publication metadata still has only TTL 2.14.2 and Jackson streaming
core 3.1.5 as runtime dependencies; it does not add Jackson 2. Historical release
records and published JAR/POM bytes are unchanged.

The CI first-project matrix also exercises public 0.1.3 with Maven and Gradle
on Java 17/21, checking business-success, expected execution-change rejection
and recovery. The Maven and Kotlin pilot jobs exercise the isolated graph and
origin/failure checks. Inspect the pull request's completed results before
merging; the local counts above do not substitute for those jobs.

These checks do not establish external adoption, performance improvements,
arbitrary deserialization safety or additional ShardingSphere versions. The
separate `tools.jackson.core:jackson-core` runtime patch is outside this
Jackson 2 change.
