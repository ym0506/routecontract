# Existing runtime lifecycle acceptance: A-11, A-12 and A-13

Status: candidate `86a0be5` is accepted within the existing six A-11/A-12/A-13 cells after
independent review of full terminated JVM logs and final input bindings. See the
[new candidate evidence](evidence/runtime-lifecycle-final-86a0be5-2026-09-08.md). The
[corrected 4e execution](evidence/runtime-lifecycle-final-candidate-2026-09-08.md) remains
separately accepted for its original bytes; its first-run predecessor remains NOT_ACCEPTED.
No acceptance scope was added.

## Frozen execution inputs

- Production source: `86a0be5d2e444f3b73925122fa448d9d1a324edd`.
- Local coordinated 0.2.0 staging: one neutral core and exact 5.5.2/5.5.3 adapters.
- Externally pinned reviewed receipt SHA-256:
  `1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e`.
- Java 17; Gradle 8.14.4 distribution and wrapper hashes are verified before use.
- MySQL 8.4.11, digest
  `b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb`, only for the positive A-12 cases.

The harness accepts a supplied staged repository and an externally pinned receipt. It does not
build or publish first-party artifacts, rewrite staged bytes, or create a baseline. It resolves and
compiles one independently locked/strict consumer graph per exact runtime with a fresh dependency
cache. Each lifecycle case then runs in a separate fresh JVM against that lane's frozen resolved
classpath; shared artifact bytes never mean shared ShardingSphere static state.

## Finite plan — exactly six cases

| Case | Exact runtime | Real loader/discovery sequence | Required result |
| --- | --- | --- | --- |
| A11-552 | 5.5.2 | First ShardingSphere SQLExecutionHook discovery through a TCCL that cannot see the matching adapter; switch TCCL to the application loader exposing that adapter; call the public capture entry. | `RC_SHARDINGSPHERE_PROVIDER_NOT_ACTIVE`; action count 0, driver-execution count 0, no returned snapshot. |
| A11-553 | 5.5.3 | Same sequence with the exact 5.5.3 hook ABI and artifact. | Same failure and counters. |
| A12-552 | 5.5.2 | First discovery sees the matching adapter through both required loaders. Retain that automatically discovered provider Class; switch TCCL to one hiding the adapter while the defining core loader still sees the original adapter; capture one real MySQL operation. | Complete capture, expected exact synthetic business row, 1 action, 1 counted physical driver execution, 1 hook-reported attempt, no callback failure; cached provider Class, defining loader and code origin unchanged. |
| A12-553 | 5.5.3 | Same sequence with the exact 5.5.3 hook ABI and artifact. | Same success within that exact runtime. |
| A13-552 | 5.5.2 | A child application loader automatically discovers the actual adapter while it delegates only the bridge class to a sibling child loader containing the same core JAR. Call the public capture entry separately. | Both entry paths expose `RC_ADAPTER_CLASSLOADER_MISMATCH`; action count 0, driver-execution count 0, no returned snapshot, no exposed raw linkage error. |
| A13-553 | 5.5.3 | Same split-loader arrangement with exact 5.5.3 artifacts. | Same failure and counters. |

## Required observations

Record the actual TCCL before/after, defining loader identities for core entry/bridge/hook/runtime
adapter/ShardingSphere anchors, parent relationships, visible descriptor and class resources, and
class code-source JAR names plus independently checked hashes. A-11 must retain evidence that first
discovery contained no RouteContract provider and the later loader exposes its real descriptor.
A-12 must retain the cached provider Class, defining loader and code origin before/after and prove the hiding TCCL
does not supply the adapter while the core loader still does. A-13 must prove distinct class objects
or defining loaders for the relevant duplicate core/bridge and the child-owned adapter.

ShardingSphere's non-singleton SQLExecutionHook discovery caches provider classes and may construct
new instances on each lookup. Instance IDs are observations, not an equality requirement. The
A-13 controlled topology uses sibling child loaders of the JDK platform loader: the application
owns the exact graph and delegates only `RouteContractHookBridge` to the other core-JAR loader.
Within each A-13 cell, actual automatic ShardingSphere discovery and the public capture call are
observed separately; the current API guard can reject before it reaches the service cache.

Use real ShardingSphere provider discovery in fresh JVMs. Do not construct hooks directly, inject
mock provider collections, clear ShardingSphere caches reflectively, or report synthetic callback
events as database observations. Resource filtering belongs to the actual controlled ClassLoader;
its visibility must be measured, not assumed from a label. Restore TCCL during fixture cleanup.

Counters distinguish the application action from physical JDBC execute calls. A-12 initializes and
warms its disposable database before resetting measured counters. The counter wraps the actual
physical JDBC driver calls and delegates to MySQL; it does not manufacture hook events. Business
rows are asserted independently of callback outcomes. Negative cells fail before their action and
therefore execute no operation SQL.
They create no data source: their zero driver count accompanies the unentered operation sentinel;
it is not an independent audit of arbitrary JDBC activity outside that operation.

The positive fixture uses two disposable containers for logical data sources `ds_0` and `ds_1`.
The measured prepared query selects the supplied synthetic user on `ds_1` and returns exactly one
synthetic row. Initialization, metadata access and a warm-up query precede the measurement window.
One counted physical execution is a separate check from one hook-reported physical attempt.

## Completion and failure handling

The runner verifies all nine input payloads and source/harness fingerprints before and after. It
retains every case result, raw process log and graph/classpath identity, even if a case fails. A
successful process must also have a current structured result matching its exact case, runtime,
loader sequence and expected outcome. A diagnostic subset is never reported as all six complete.
The runner reads the full log after JVM termination and rejects standard uncaught-thread throwable
output, including shutdown failures after an otherwise successful capture report.

First review the finite fixture, hashes and focused harness tests; only then execute this matrix.
If actual staged production bytes violate one of these existing contracts, retain the reproducer
and report the failure before proposing any production change. A setup/compiler/Docker failure is
not an expected negative. No retries without a diagnosed failure.

Evidence is local staged consumption. A-12 becomes `verified - MySQL` and its exact ShardingSphere
version only after real execution. Negative loader cases establish only their controlled loader
topology. This does not prove arbitrary async propagation, general plugin-container support,
performance, transaction commit, full routing plans, release publication or independent adoption.

## Reproducible commands

The focused harness checks do not run MySQL or rebuild first-party artifacts:

```bash
python3 -m unittest scripts/tests/test_verify_runtime_lifecycle_consumer.py
```

After the run-ready fixture review, supply the reviewed repository, receipt and verified Gradle
archive. `EVIDENCE_DIRECTORY` must not exist and must be outside this checkout. There is no retry
or subset switch; the plan is six fresh JVM cells and two fresh dependency-cache compile lanes.

```bash
python3 scripts/verify-runtime-lifecycle-consumer.py \
  --repository "$STAGED_REPOSITORY" \
  --staged-receipt "$REVIEWED_RECEIPT" \
  --staged-receipt-sha256 1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e \
  --staged-source-revision 86a0be5d2e444f3b73925122fa448d9d1a324edd \
  --java-home "$JAVA17_HOME" \
  --gradle-distribution-zip "$GRADLE_8_14_4_ZIP" \
  --evidence-directory "$EVIDENCE_DIRECTORY"
```

The consumer build, settings, exact runtime lock and strict verification metadata are copied from
the existing staged fixture; only its probe source and a compile/classpath evidence task differ.
No original staged-consumer JUnit test task is executed by this runner. The output retains commands,
toolchain, raw Gradle/JVM logs, classpath and compiled-class hashes, actual loader/provider/resource
inventories and one structured case result per completed JVM. `summary.json` stays `FAILED` if any
case, setup step or final source/receipt/payload binding fails.

Historical fixture verification on 2026-09-08: 14 focused Python harness tests passed. Java 17 compilation with
`--release 17 -Xlint:all -Werror` passed against available exact-version JAR inputs for both runtimes;
the launcher and its JSON helper also compiled with only the JDK. These are `verified - unit` and
compile-only observations. They did not alone establish either final strict consumer graph or runtime
acceptance; the subsequent corrected 4e execution resolved the two fresh locked graphs and executed
all six cells, with independent review recorded in the linked final evidence.

## First-run harness correction

The first finite run returned exit 0 and six provisional `PASS` reports. Its two A-12 raw JVM logs
then revealed `NoClassDefFoundError: org/testcontainers/utility/PathUtils` in Testcontainers cleanup
threads after `CAPTURED`. The launcher had closed its application URLClassLoader before JVM shutdown;
the old runner checked exit status and the earlier structured report, missing those late errors.
That run is retained as an unaccepted harness false positive, not clean six-cell acceptance.

The correction keeps both controlled loaders available for the entire fresh JVM, including third-party
shutdown hooks, while restoring TCCL as before. The runner now rejects uncaught-thread failures in
the complete terminated JVM log. Regression checks include the actual interleaved A-12-552 shutdown
tail. Product artifacts, runtime graph policies, six-case scope and capture expectations are unchanged.
One corrected finite run completed after the revised fixture was reviewed. All six full JVM logs
and post-run artifact/source/fixture bytes were independently accepted. The original failed run
is retained separately and is not counted as successful acceptance.

## Historical corrected 4e execution record

The historical corrected 4e run used Java 17.0.15, Gradle 8.14.4 and actual MySQL 8.4.11 with the pinned image.
For each exact runtime, A-11 rejected late provider attachment and A-13 rejected the split bridge
with the specified stable diagnostic before the action. A-12 returned the exact synthetic business
row with one action, one delegated physical JDBC execute and one hook-reported physical attempt;
capture was COMPLETE with zero callback failures. Both positive JVMs also completed shutdown
without the original uncaught cleanup error.

This post-run documentation does not alter the frozen executed inputs. Their hashes, full
reproduction command, raw evidence hashes, original rejection and corrected independent review
are recorded in the linked minimized evidence. The stated loader and operation boundaries above
remain the acceptance boundary.

## Accepted 86a0be5 execution record

The same finite six-case plan subsequently ran once against the new reviewed `86a0be5` staged
bytes from the frozen `3ad510a` fixture checkout. All six JVMs exited normally through EOF.
Both A-12 cells recorded one real MySQL 8.4.11 driver execution, one hook-reported attempt and
one returned callback, with the exact synthetic row and no callback failure. A-11 and A-13
retained their stable pre-action rejection behavior for both exact ShardingSphere versions.

Independent review accepted all six complete raw logs and loader observations, both strict/locked
consumer graphs, nine payload pins and all 22 before/after input hashes. Twenty inputs retain
the historical corrected-run hashes; the shared staged-consumer build and this acceptance
document are the two changed inputs. The new shared build preserves lifecycle-only compilation
and strengthens graph checks. No first-party artifact or production source was rebuilt or changed
by the lifecycle execution.

The [new minimized evidence](evidence/runtime-lifecycle-final-86a0be5-2026-09-08.json) binds the actual new source, receipt,
run-ready record, independent raw audit and unchanged historical evidence. This updated
acceptance document is a post-run copy; its bytes are not the frozen documentation fingerprint
recorded by that execution. The historical failure and corrected 4e acceptance remain separate.
