# Public API migration: final-candidate follow-up, 2026-09-08

**A-26 passed in one finite run** against the reviewed 0.2.0 staging produced from source
`4e066942f6e244345fe908970b81446f9e08f64e`. This is new candidate evidence; the
[2026-09-07 record](public-api-migration-2026-09-07.md) remains unchanged historical evidence.
It does not establish a public 0.2 release or universal drop-in compatibility.

Evidence labels: `verified - unit`, `verified - MySQL`,
`verified - ShardingSphere-JDBC 5.5.3`.

## Frozen inputs and execution

The reviewed nine-payload receipt has SHA-256
`38b2269eca162f121fd3996c56df8b894ae2f43cedeb08fcc627032cf70eaa43`.
Source, 21 harness inputs, all nine staged payloads, the receipt, and both legacy input files were
unchanged before/after. The unchanged runner is
[verify-public-api-migration.py](../../scripts/verify-public-api-migration.py), SHA-256
`b1893cd2171a458bfd5253a27a0ca6935499f2d2adddd13a94a6b13f4be7835d`.

| Input | SHA-256 |
| --- | --- |
| Public 0.1.2 adapter JAR | `d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc` |
| Public 0.1.2 adapter POM | `70b5d4161d1532e9f9cb699071790a7806d87658511d931477544fa06037b85d` |
| Staged 0.2.0 core JAR | `1863b422179b0447035642bfa5a679ffa0f75201ac3bf6c261558f32849ba598` |
| Staged 0.2.0 exact-5.5.3 adapter JAR | `6d139b136e714cb3dfd033aa47dfcbfedffd3e87f6f5aaa2c7762975a714f64e` |

The old files match the [immutable release pins](../../examples/public-api-migration-consumer/release-inputs.json)
and were copied alone into a fresh Maven layout. Each online consumer used its own initially empty
Gradle cache, strict locks/checksums and the existing adapter GAV; 0.2 resolved core transitively.
There was no first-party rebuild, runner modification or public download of first-party bytes.

Environment: macOS 26.4.1 arm64, Homebrew OpenJDK 17.0.15+0, Python 3.12.14, Gradle 8.14.4,
Docker Engine 29.2.1, Testcontainers 1.21.4 and exact ShardingSphere-JDBC 5.5.3. The digest-pinned
MySQL image is recorded in the [JSON](public-api-migration-final-candidate-2026-09-08.json).
Execution ran from 07:18:28 to 07:20:46 UTC, took 138.25 seconds and exited 0.

## Observed outcome

- Both old and current resolved graphs passed **3/3 real-MySQL tests**, with zero failures, errors
  or skips. The three old MySQL class files were reused unchanged on 0.2.
- The same exact synthetic order was returned in both query forms. Equality produced one observed
  attempt and `MATCH`; range produced two attempts and `POLICY_VIOLATION`, `RCM201` and `RCM202`.
  The migration suite asserts that rejection; the successful A26 harness does not make the range
  query a matching contract.
- All **26 old public types and 167 member descriptors** were retained. Full unchanged MySQL source
  also recompiled against the new compile graph. Schema-1 codec bytes matched; the reviewed
  schema-1 baseline matched actual schema-2 captures.
- Source constants, record identity/equality/string form, two new enum values and API code-source
  ownership have the disclosed migration behavior. Both old exhaustive-switch failures and the
  source recompilation rejection were observed. Explicitly migrated source passed.
- Module-path capture was rejected before the action with `RC_UNSUPPORTED_MODULE_PATH`.

`completeBehavioralCompatibility=false` and `publicRepositoryConsumption=false` are intentional.
An old assertion expecting the inlined schema constant to equal a new capture's schema can fail.
This clean 0.1.2-to-0.2.0 test covers exact 5.5.3 only; it does not complete A-29 collision checks,
5.5.2 behavior, other release gates or independent adoption.

## Reproduce and inspect

Set `SOURCE_ROOT` to the clean source commit above, `JAVA17_HOME` to a Java 17 JDK,
`LEGACY_REPOSITORY` to a fresh layout of the pinned old JAR/POM, `STAGED_REPOSITORY` to the reviewed
staging, and `NEW_EVIDENCE_DIRECTORY` to an absent directory under an existing parent. The following
command replaces only machine-specific path prefixes; the exact original argv remains in the local
wrapper record. Python 3.12.14 and the pinned Gradle wrapper were used for this execution.

```bash
cd "$SOURCE_ROOT"
JAVA_HOME="$JAVA17_HOME" PATH="$JAVA17_HOME/bin:$PATH" \
  python3 -I scripts/verify-public-api-migration.py \
  --legacy-repository "$LEGACY_REPOSITORY" \
  --repository "$STAGED_REPOSITORY" \
  --evidence-directory "$NEW_EVIDENCE_DIRECTORY"
```

The [minimized JSON](public-api-migration-final-candidate-2026-09-08.json) includes every staged
payload hash, environment/command details, summary results and retained raw/review hashes.
Wrapper record SHA-256: `2e84ad29663ad4a3c9a8121094a99c11ae0988281c4300bf274ef8443dde5f00`.
Independent result review SHA-256: `a7cd87ac5a69438c41e8818882987a846cb39e0b47999f7ebdeb0412e5b92fae`.
All 75 retained evidence files were checked against the wrapper's recorded sizes and hashes.
Raw logs, graphs and JUnit stay local; this note includes no raw SQL, connection details or local
account paths. Hashes establish byte identity, not publisher authentication or release approval.
