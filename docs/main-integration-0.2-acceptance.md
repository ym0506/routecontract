# Stable-line integration into the unreleased 0.2 branch

A contributor must be able to run the complete test set after the stable-line
maintenance is brought into the split core and two adapters. A successful job
that silently omits a module is insufficient evidence of Java 21 compatibility.

## Acceptance

- Retain the three coordinated 0.2 artifacts and exact 5.5.2 / 5.5.3 adapters.
- Use the stable line's Gradle 9.7.1, Jackson 2.18.10 and streaming Jackson 3.1.6
  with generated dependency locks and strict artifact verification.
- Run all five module test tasks on Java 17 and Java 21, including both real
  MySQL corpora. Library compilation must still produce Java 17 bytecode.
- The Java 21 evidence helper must reject a missing or differently launched
  module, incomplete JUnit inventory, failed/skipped/malformed results, and a
  missing or incompatible production class in any of the three libraries.
- Require the same exact suite inventory as the release test summary. Emit
  minimized evidence only after validation succeeds; omit captured output and
  host/connection properties.
- Preserve mandatory signatures and payload checksums across all three
  coordinates when Gradle omits optional signature-checksum sidecars. The
  Central upload remains exactly 90 entries.
- Validate both Python test roots, official SBOM schemas and staged consumers
  against the new integration inputs before making release-readiness claims.
- Require the current staged-consumer dependency graphs to select streaming
  Jackson 3.1.6 and Jackson BOM 2.18.10. An unchanged consumer smoke test can pass
  while an old strict lock still selects 3.1.5 / 2.18.9; that passing result does
  not qualify the updated combination. Keep historical experiment results tied
  to their original toolchains and input fingerprints.

## Evidence boundary

Local source verification on 2026-09-14:

| Check | Recorded result |
| --- | --- |
| Gradle 9.7.1 / Temurin 17.0.20.1+1 | 26 suites, 782 tests; zero failures/errors/skips |
| Gradle 9.7.1 / Homebrew OpenJDK 21.0.11 | Same 26 suites and 782 tests, five actual Java 21 workers |
| Real MySQL 8.4.11, exact 5.5.2 and 5.5.3 adapters | 14 tests per adapter on each Java runtime |
| Production bytecode after Java 21 testing | All 62 classes across the three libraries retain major version 61 (Java 17) |
| Official CycloneDX CLI 0.33.1 | Six JSON/XML pairs, 12 documents validated |
| SBOM/POM/lock inventory consistency | All six roles passed the supply-chain inventory gate; this alone is not an OSV scan |

These are **verified - unit**, **verified - MySQL** and exact-version
**verified - ShardingSphere-JDBC 5.5.2 / 5.5.3** observations. The native logs,
JUnit files and `java21-runtime-summary.json` are retained in the maintainer's
`02-main-integration-20260914` evidence directory. Packaged reruns, the final
security scan and CI qualification remain pending; earlier candidate evidence
does not qualify these new artifact bytes.

Reproduce the Java 17 run with a selected Java 17 `JAVA_HOME`:

```sh
./gradlew --no-daemon --no-build-cache --no-configuration-cache \
  --dependency-verification=strict clean check assemble validateOfficialCycloneDxSbom
```

For Java 21, set `COMPILER_HOME` to the Java 17 JDK and `JAVA_HOME` to the Java 21
JDK. The separate paths prevent a successful Gradle launcher from being mistaken
for proof of the test-worker runtime:

```sh
mkdir -p build
./gradlew --no-daemon --no-build-cache --no-configuration-cache \
  --dependency-verification=strict --rerun-tasks --info \
  -ProutecontractTestJavaVersion=21 \
  "-Porg.gradle.java.installations.paths=${COMPILER_HOME},${JAVA_HOME}" \
  -Porg.gradle.java.installations.auto-detect=false \
  -Porg.gradle.java.installations.auto-download=false \
  :routecontract-core:test \
  :routecontract-shardingsphere-5.5:test :routecontract-shardingsphere-5.5.2:test \
  :mysql-example:test :mysql-5.5.2-example:test > build/java21-runtime.log 2>&1
python3 submission/tools/summarize_java_runtime.py \
  build/java21-runtime.log "$JAVA_HOME" build/java21-runtime-summary.json
```

Helper fixtures are unit evidence; they do not prove a real Java 21 or MySQL run.
Successful synthetic MySQL tests do not establish external adoption, arbitrary
async/virtual-thread support, or business/transaction success. This integration
does not publish 0.2, approve a baseline, or reuse an older candidate's byte-level
release evidence for newly built artifacts.
