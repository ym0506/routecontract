# Public classpath API migration consumer (A-26)

Status: unreleased 0.2 development fixture. Acceptance specification precedes implementation.
This is bounded migration evidence, not complete behavioral compatibility or release approval.

## Acceptance contract

1. Verify the checksums of the old `routecontract-shardingsphere-5.5:0.1.2` JAR and POM with pinned hashes
   from the immutable public release. Compare every old documented public type and member
   descriptor with a frozen inventory; exclude implementation classes and provider FQCNs.
2. Copy a consumer outside this checkout. In separate fresh dependency caches, resolve the old
   GAV and the same GAV at `0.2.0` from supplied local Maven-style repositories. Request only the
   adapter; core must be selected transitively by its POM. Exclude all first-party dependencies
   from Central. Verify selected JAR/POM bytes, graph exactness and runtime code sources.
3. Compile the consumer against the released 0.1.2 graph once. Run the same class-file bytes on
   the old graph as a control and on the current graph without recompilation. On real exact
   ShardingSphere-JDBC 5.5.3 and digest-pinned MySQL 8.4.11, both `capture` and `captureResult`
   must return the same exact business row and report one physical JDBC execution attempt.
   A range predicate must return the same business row but report two attempts and fail the
   unchanged approved schema-1 baseline with `RCM201` and `RCM202`. Retain raw JUnit and separate
   minimized route evidence; never approve or rewrite the baseline.
4. Independently exercise old constructor bytecode, unchanged-source recompilation, explicit
   schema-2 source migration, record reflection, equality/hashCode/toString, schema-1 JSON,
   code-source relocation, and enum switch migration. The source-constant rejection and old
   exhaustive-switch failure are expected, explicitly checked migration outcomes, not linkage
   success. Ordinary old methods and legacy constructor descriptors must remain linkable.
5. Execute a separate fresh-JVM module-path capture probe. Require
   `RC_UNSUPPORTED_MODULE_PATH` before the action runs; automatic-module metadata does not
   establish supported module-path execution.
6. Fail for missing, changed or unexpected artifacts, lost old-bytecode identity, empty/skipped
   or failed tests, missing evidence, changed pinned API inventory, or undocumented descriptor
   removal. Keep an exact receipt and each probe output. Do not disable checksum verification,
   dependency locks, version guards or artifact-origin checks to obtain a pass.

The consumer covers a representative synchronous non-batch operation and explicit model/API
migration cases. It does not exhaust every possible user program, asynchronous boundary,
reflection framework, serializer, old release, 5.5.2 operation, or ADR acceptance row. Locally
supplied staging bytes do not prove anonymous public consumption, Maven Central publication,
external approval, or adoption.

## Run

Use Java 17 (`JAVA_HOME` must identify that JDK), Docker, Python 3.10+, and network access for
fresh third-party caches. Supply the already checksum-verified public v0.1.2 repository and a
coordinated local 0.2 staging repository. These arguments are absolute directories:

```sh
python3 -I scripts/verify-public-api-migration.py \
  --legacy-repository /absolute/path/to/verified-v0.1.2-repository \
  --repository /absolute/path/to/staged-0.2-repository \
  --evidence-directory /absolute/path/to/new-migration-evidence
```

Choose a new evidence directory with an existing parent. The harness does not install, build,
publish, sign, modify or approve supplied artifacts. It does not contact GitHub or require account
credentials. Third-party resolution uses Maven Central; first-party resolution is restricted to
the supplied local repository. SHA-256 ties inputs to the frozen release hashes and local staging
receipt; it is not independent proof of a publisher's identity or signing-key ownership.

The fixture uses Gradle 8.14.4 with POM-only first-party resolution. Its sole direct RouteContract
dependency is the existing `routecontract-shardingsphere-5.5` GAV. The 0.2 core must arrive through
the adapter's published POM. Separate empty caches, strict verification metadata and per-version
locks protect the two resolved graphs. Source probes compile against the resolved compile
classpath; executions use the independently resolved runtime classpath. Current-source tests are never substituted for the old
compiled MySQL consumer. The harness checks all old class-file hashes after both executions.

Output includes artifact receipts, resolver graphs, raw JUnit (three tests per version), old
class-file hashes and bytes, and individual migration probe logs. `mysql-evidence` retains the
unchanged schema-1 baseline and minimized observed manifests. `business-rows.json` separately
retains the exact **synthetic fixture** rows returned by equality and range queries; it is business
assertion evidence, not captured SQL parameters or user data. Temporary caches are removed after
execution; logs and evidence remain even after an ordinary verification failure. `summary.json`
is written only after every required probe and receipt check passes.

## Intentional migrations exercised

- Both legacy record constructor descriptors remain, but accept only schema 1. Bytecode compiled
  with the old schema constants links; unchanged source recompiles with constant 2 and must be
  migrated to the explicit-identity constructor before it can execute successfully. Also, old
  bytecode comparing a new `snapshot.schemaVersion()` against its inlined old constant observes
  `2 != 1`. The MySQL fixture verifies that captures actually produce schema 2, while the old
  constant inventory is 1. Its deliberate version-specific expectation must not be mistaken for
  drop-in behavioral compatibility of arbitrary old tests.
- `runtimeIdentity` is inserted after `schemaVersion` in both record component lists (snapshot
  12 to 13, manifest 6 to 7). Reflection, canonical construction and record value shape change.
  Equal old-style values still have equal hashes within one runtime. Otherwise equal values with
  different runtime identities compare unequal. Schema-1 and schema-2 values also compare unequal,
  even when `ManifestVerifier` correctly returns `MATCH`; use the verifier for baseline matching.
- Existing public FQCNs and descriptors remain, but public API code sources move from the all-in-one
  adapter to `routecontract-core-0.2.0.jar`. Internal provider classes are excluded from the public
  compatibility promise; their code origins are checked only to validate the runtime graph.
- `ManifestDiffCode` gains `UNSUPPORTED_RUNTIME_IDENTITY` (`RCM004`) and
  `RUNTIME_IDENTITY_MISMATCH` (`RCM005`). An exhaustive old enum switch cannot process these values:
  its old bytecode throws `IncompatibleClassChangeError`, and recompilation requires new cases or
  a safe fallback. New identity findings must block. Do not persist enum ordinals as stable codes.
- Module-path capture is deliberately rejected before the action. This probe does not establish
  ordinary-SQL/module-path coverage for every possible ShardingSphere loader arrangement.

The Java 17 suite covers representative behavior plus the complete old non-internal public
member-descriptor inventory. It does not turn that descriptor inventory into an exhaustive
behavioral compatibility claim, or complete other A-26/public-release acceptance obligations.
