# Gradle legacy resolver acceptance, 2026-09-08

The local Gradle portion of ADR A-27 passed **37/37 actual resolver cases**.
This does not close A-27: its Maven consumer cases remain pending. A-28 manual
classpath/SQL/capture-sentinel execution and public 0.2 publication are separate
gates. No production source or published artifact was changed for this work.

The [specification](../legacy-resolver-acceptance.md) preceded implementation.
The [compact receipt](gradle-legacy-resolver-2026-09-08.json) records each case,
actual materialized first-party JAR pins, applied legacy capabilities, failure
counts, report/log hashes, source binding, and the exact tested fixture hashes.

## Inputs and environment

Execution used CPython 3.12.14, Homebrew OpenJDK 17.0.15+0, Gradle 8.14.4, and
Mac OS X 26.4.1 arm64. Four independent cases ran concurrently; every case had
its own Java process, copied Gradle build, absent dependency cache and separate
project cache. Strict dependency verification covered all resolved metadata and
materialized artifacts. Only the Gradle distribution was seeded.

The [shared legacy input registry](../../scripts/legacy-artifact-inputs.json)
pins the real distributed `0.1.0`, `0.1.2`, `0.1.3`, and `0.1.0-rc2` JAR/POM
bytes. It also includes the public Central 0.1.3 `.module`, immutable release/tag
provenance, and inspected all-in-one class/service entry hashes. All nine legacy
payloads were checked again before resolution. `0.1.1` and `0.1.0-rc1` remain
tag-only source/layout evidence and were not substituted for executable releases.

The current nine-payload staging receipt comes from
`008e125a0648ed615842a572d60fd453698bb5aa`. The test checkout was
`c027a192e554a8e230520bcc68b3064efb84087f` plus the new fixture/runner files.
The driver checked identical production/publication inputs, including source,
build configuration, locks, Gradle metadata configuration, and embedded
LICENSE/NOTICE. Every supplied current JAR/POM/module matched the reviewed
receipt before copying into the isolated repository; all copied inputs and
fixture hashes were checked again after the complete run.

- Legacy registry SHA-256: `f03dc0d63a23e68fd4cc6895efff1ba1175143e084b76f25f8e70fd19a04419f`.
- Staged receipt SHA-256: `ff4ad23aca357baa0a29f6ddac3a8b3708f1dbe62e0a73f200f84737449fdb41`.
- Full result summary SHA-256: `6e2e0fdb7045bd4a566682ffe2f9d0332021e3fcbc561c07a4390942f05e6f9a`.

These are the reviewed local staging bytes. They are not relabeled as the
later CI-generated metadata or as a coordinated public 0.2 release candidate.
Repeat the gate if the reviewed publication payload set changes.

## Observed results

| Case, repeated for each distributed legacy version | Total | Observed result |
| --- | ---: | --- |
| Legacy alone | 4 | Resolved the exact pinned legacy JAR. |
| Legacy + core, both declaration orders | 8 | Actual `routecontract-core-owner` capability conflict. |
| Legacy + 5.5.2 adapter, both orders | 8 | Actual legacy-GAV/core-owner capability conflict. |
| Same-GA legacy/current ordinary mediation, both orders | 8 | Selected exactly current adapter553 + transitive core; no legacy file. Each graph contained 26 ShardingSphere components, all 5.5.3, including the executor anchor. |
| Same-GA incompatible strict versions, both orders | 8 | Actual incompatible strict-version resolution failure. |
| Latest legacy + core, ownership rule disabled | 1 | Resolved both exact JARs, demonstrating the missing protection. The enabled cases above rejected that same combination. |

The [reusable consumer rule](../../examples/gradle-legacy-artifact-consumer/legacy-core-ownership.gradle)
assigns ownership to selected legacy component metadata. It does not reject
dependency requests, so ordinary same-GA version mediation remains usable.
Each negative case checked every unresolved failure chain for its required
conflict category; missing artifacts or unrelated failures did not count.

Evidence label `verified - unit`: **24/24 Python tests** passed, covering pinned
payload corruption, duplicate/altered JAR entries, POM and `.module` binding,
tag-only separation, the case matrix, staged-byte corruption, real Git source
drift for LICENSE/NOTICE, and an incorrect Gradle distribution checksum.
The 37-case result above is specifically Gradle/Java resolver evidence, not
ShardingSphere SQL or MySQL execution evidence. Third-party metadata was
resolved, but only first-party JARs were materialized by the resolver fixture.

## Reproduction and retained results

The final full run used this command shape from the test checkout. Set these
path variables to the reviewed inputs and a new absent evidence directory;
the exact local invocation is retained with the execution handoff.

```sh
python3 -I scripts/verify-gradle-legacy-artifact-consumer.py \
  --repository "$REVIEWED_STAGED_REPOSITORY" \
  --staged-receipt "$REVIEWED_STAGED_RECEIPT" \
  --staged-source-revision 008e125a0648ed615842a572d60fd453698bb5aa \
  --evidence-directory "$NEW_EVIDENCE_DIRECTORY" \
  --java-home "$JAVA17_HOME" \
  --legacy-payload-directory "$PINNED_LEGACY_INPUT_DIRECTORY" \
  --gradle-distribution-zip "$VERIFIED_GRADLE_DISTRIBUTION_ZIP" \
  --workers 4
```

Choose a new absent evidence directory when repeating. Omit the legacy cache
option to download the pinned public payloads. The optional distribution ZIP
came from `https://repo.huaweicloud.com/gradle/gradle-8.14.4-bin.zip` and matched
the checked-in wrapper SHA-256
`f1771298a70f6db5a29daf62378c4e18a17fc33c9ba6b14362e0cdf40610380d`;
the official redirect was too slow locally. No unchecked extracted distribution
or dependency cache was used as a replacement.

The retained final evidence directory contains
`summary.json`, `source-binding.json`, `fixture-inputs.json`, input inventory,
toolchain output, and `cases/<case-id>/{command.json,gradle.log,result.json}`.
The compact receipt binds all 37 retained result/log pairs to their hashes;
an independent review checked every case against its plan and expected bytes.
The separately retained unit output came from
`python3 -m unittest discover -s scripts/tests -p '*legacy_artifact*.py' -v`.

Earlier `diagnostic-b` and `full` attempts were retained as failures while the
fixture's Java variant setup and executor anchor were corrected. `diagnostic-c`
was a one-case partial run. None is substituted for the final 37-case receipt.
