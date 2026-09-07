# Public API migration acceptance evidence, 2026-09-07

Status: local A-26 acceptance evidence with explicitly documented migration breaks. No public 0.2
release, anonymous public consumption, external adoption, or completion of other ADR rows follows
from this result. A-26 permits disclosed source/reflection/record/code-source changes; identical
behavior for every possible old program is not its acceptance criterion.

Evidence labels: `verified - unit`, `verified - MySQL`,
`verified - ShardingSphere-JDBC 5.5.3`.

## Inputs and environment

The [consumer specification](../../examples/public-api-migration-consumer/README.md) was written
before implementation. The fixture starts from source base `b84886f` and uses the supplied staged
production bytes built from `008e125`; this work changes no production source or released asset.

Environment: Darwin arm64, OpenJDK 17.0.15, Gradle 8.14.4, Docker Engine 29.2.1, Python 3.13.0,
Testcontainers 1.21.4 and exact Apache ShardingSphere-JDBC 5.5.3. MySQL is pinned to
`mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb`.

| Selected JAR | SHA-256 |
| --- | --- |
| Public `routecontract-shardingsphere-5.5-0.1.2.jar` | `d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc` |
| Staged `routecontract-shardingsphere-5.5-0.2.0.jar` | `6d139b136e714cb3dfd033aa47dfcbfedffd3e87f6f5aaa2c7762975a714f64e` |
| Staged `routecontract-core-0.2.0.jar` | `def89f37cf6b4eab02e593bddf77b493c8d52e7b7e66c8ef8f830dc0c67664e8` |

The old JAR and POM hashes are pinned in
[release-inputs.json](../../examples/public-api-migration-consumer/release-inputs.json). The old
bytes came from the immutable public v0.1.2 release; the new JAR/POM hashes come from the supplied
local staging receipt. Checksums establish byte identity against these inputs, not independent
publisher authentication, signing-key ownership, or public availability of 0.2.

The reviewed schema-1 baseline remains unchanged:
`a082ca797ebe40be5b8c9409893de7d9a861086d8d4b760cbc00e925b2436a60`.

## A-26 surface-to-evidence map

| Required A-26 surface | Observed result |
| --- | --- |
| Documented public API comparison, excluding internal/provider FQCNs | All 26 old non-internal public types and 167 public/protected member descriptors remain. The pinned inventory includes class declarations, constructors, fields, generic declarations and JVM descriptors. Two schema constants change from 1 to 2; two enum values are added. |
| Existing GAV through transitive core | Independent POM-only consumers request only `routecontract-shardingsphere-5.5`, first at 0.1.2 and then 0.2.0. The latter resolves core transitively from the adapter POM. Exact first-party selected sets, JAR hashes, code sources and whole-group ShardingSphere versions pass. No manual core classpath injection or project dependency is used. |
| Old-bytecode consumer | Three old Java class files compiled against 0.1.2 execute unchanged against both resolved graphs. Each graph passes all 3 real-MySQL tests with zero failures/errors/skips. `capture` and `captureResult` both return the exact row and produce one reported physical JDBC execution attempt. |
| Business-green/route-red regression | Both queries return the exact synthetic row `(201, 3, PAID)`. Equality matches the unchanged approved baseline with one attempt; range reports two attempts and is rejected with `POLICY_VIOLATION`, `RCM201`, and `RCM202`. Actual result rows and minimized route manifests are retained separately. |
| Source recompilation | The entire unchanged MySQL consumer recompiles against the normal 0.2 compile classpath. Separate old-source probes using the inlined schema constant recompile but reject the legacy constructors at execution; explicit-identity source compiles and runs successfully. Compile visibility of transitive core is checked separately from runtime visibility. |
| Record reflection | Snapshot components grow 12 to 13 and manifest components 6 to 7. Both insert `runtimeIdentity` immediately after `schemaVersion`. Exact component-name/type/order lists are compared with a frozen old list. |
| Equality/hashCode/toString | Equal old-style twins have equal hashes within each runtime. Runtime identity contributes to the new record value; different identities compare unequal. Schema-1 and schema-2 records also compare unequal even when `ManifestVerifier` returns `MATCH`. Both record strings gain identity. No cross-version hash-value stability is claimed. |
| Codec migration | The synthetic schema-1 model encodes identically on old and current runtimes and round-trips through the codec/store. The unchanged reviewed schema-1 baseline verifies against actual new schema-2 captures. Explicit schema-2 model round trips also pass. |
| Enum source and binary migration | Old enum mappings still work on the current runtime. Each new enum value is separately rejected by old exhaustive-switch bytecode with `IncompatibleClassChangeError`; unchanged exhaustive source fails recompilation. Migrated source explicitly blocks both identity findings. |
| Code-source location | Old public API classes originate in the all-in-one adapter JAR; current API classes originate in the exact selected core JAR. The sole hook service descriptor and provider originate in the matching selected adapter JAR. |
| Classpath/module migration | The real consumer executes on the supported ordinary classpath. A separate fresh JVM places the selected first-party JARs on the module path and verifies `RC_UNSUPPORTED_MODULE_PATH` before the capture action runs. Module-path compatibility is explicitly not claimed. |

All requested categories in the A-26 row have local evidence with their permitted changes disclosed.
There is no additional A-26 requirement here that every old behavior remain identical. The
pre-publication requirement to repeat acceptance on the exact final coordinated staged release
set remains; these receipts identify the current local 0.2 candidate bytes. Other ADR rows and
public/release gates remain independent.

The old `CURRENT_SCHEMA_VERSION` field is inlined as 1 in old bytecode; actual current captures
produce 2. An old user's assertion comparing the captured schema to that inlined constant can
therefore fail even though constructor/method linkage works. The version-specific expected schema
inside this deliberate migration fixture does not establish drop-in compatibility for arbitrary
old test assertions.

## Execution receipts

The runtime and source refinements were verified in separate phases to avoid repeating unchanged
MySQL controls:

1. `/private/tmp/routecontract-a26-evidence-b`: completed independent old/current graph resolution,
   old bytecode execution and MySQL evidence. Each graph began with its own empty Gradle cache.
   Raw JUnit is `<version>/junit/TEST-io.github.ym0506.routecontract.consumer.OldBytecodeMySqlTest.xml`;
   business/route artifacts are `<version>/mysql-evidence/<version>/`. Source probe results in this
   phase are superseded by the compile-classpath refinement below.
2. `/private/tmp/routecontract-a26-compile-probes-c`: completed fresh old/current compile/runtime
   graph resolution and the corrected Java probes, including separate failures for both new enum
   values. It records `source-receipt.json`, `artifact-receipts.json`, each resolved graph and each
   probe output. No MySQL run was repeated in this phase.
3. `/private/tmp/routecontract-a26-java-source-bytecode-check`: recompiling the final MySQL fixture
   against checksum-verified dependencies from the resolved old compile graph reproduced all
   three class hashes from phase 1 exactly. Its source SHA-256 is
   `53703db063b0f12ed40647fa0b73ed6f320544ef46a41062bbd123222053a5f1`.
4. `/private/tmp/routecontract-a26-java-source-recompile-current`: the same complete consumer
   source compiles under Java 17 against the resolved current compile graph with all warnings
   treated as errors. These recompiled classes were never substituted into the old-bytecode run.

The retained top-level old MySQL consumer class has SHA-256
`f60641f6619cb0623d56cc57b8afa559dc387784bf193455db38e736486c9934`; the receipt also covers its two
nested classes. The final harness includes the refined checks in its single reproducible command.
The phase receipts, rather than an unexecuted claim of a second full monolithic run, identify the
local validation actually performed.

An initial `/private/tmp/routecontract-a26-evidence-a` execution exposed a harness expected-test-name
mismatch after three successful legacy MySQL tests. The harness names were corrected; no test
assertion or expected application result was weakened. Phase 1 above is the corrected full runtime
run. Independent review then identified runtime-classpath compilation as insufficient source
migration evidence and a first-new-enum-only probe; phase 2 fixes and verifies both.

Raw logs and raw JUnit remain local evidence: framework output includes synthetic SQL and JDBC
URLs. Share only the minimized manifests, explicitly synthetic business rows, summaries, or a
separately sanitized JUnit derivative. No connection properties or raw framework logs are included
in this committed note.

## Reproduce

Run the command in the [consumer README](../../examples/public-api-migration-consumer/README.md)
with the verified legacy repository, the coordinated staged repository and a new evidence directory.
The harness never builds or publishes first-party code and never approves a baseline.

Focused failure-path checks:

```sh
python3 -m unittest discover -s scripts/tests -p test_verify_public_api_migration.py
```

Ten tests pass, including changed legacy bytes, absent core POM, symlinked payloads, removed API
descriptors, altered frozen inventory, substituted/skipped JUnit cases, trust bypasses, direct core
injection, runtime-only core, and missing exact business rows.

This evidence is bounded to Java 17, exact 5.5.3, one synchronous non-batch operation and the stated
migration probes. It is not another runtime's semantic corpus, a full serializer/framework audit,
public repository availability, publisher endorsement, or external adoption.
