# Remaining A-15 / A-17 resolver and runtime boundaries

Status: four Gradle cases against the reviewed `86a0be5` candidate passed and
their raw evidence has been audited. The third native attempt then stopped in
the first Maven download because the disposable repository omitted checksum
sidecars. No Maven boundary case has completed; all six remain pending the
reviewed fixture correction. Earlier failed attempts remain failed. Existing
audited A-24 anchor and non-anchor controls remain separate evidence; positive
MySQL cases are not repeated here.

The finite plan contains exactly ten Java 17 cases:

| Tool | Selected adapter runtime | Case | Count |
| --- | --- | --- | ---: |
| Gradle 8.14.4, Groovy | 5.5.2 and 5.5.3 | Both ordinary adapter declaration orders | 4 |
| Maven 3.9.14 | 5.5.2 and 5.5.3 | Both ordinary adapter declaration orders | 4 |
| Maven 3.9.14, external Java process | 5.5.2 and 5.5.3 | One adapter with all three coherent opposite-runtime anchors, without Enforcer | 2 |

Every case owns a new consumer directory, private user home, initially absent
dependency cache, process commands and HTTP request log. No dependency cache is
copied from positive cases or from another negative. A checksum-pinned Gradle
distribution is the only permitted seed. Remove inherited proxy/JVM/build-tool
options and use the exact selected Java 17 runtime with trusted IPv4 settings.

Before execution, require an independently reviewed nine-payload staging receipt,
its separately supplied SHA-256, the exact production source revision, and a
reviewed fingerprint map of every executed fixture/helper. Preserve the original
staging and copy only the nine receipt-pinned payloads and their existing `md5`,
`sha1`, `sha256` and `sha512` sidecars into disposable evidence. First verify each
payload against the reviewed receipt, independently calculate each algorithm's
digest from those bytes, and require the existing sidecar to contain that exact
digest. Reject missing, malformed, mismatched or symlinked sidecars; do not derive
replacements or change the original staging. Record each copied sidecar's exact
bytes hash, size, algorithm, digest and receipt-pinned payload identity in a
separate inventory. Keep the nine-payload inventory and Gradle verification
metadata unchanged. Maven `--strict-checksums` remains mandatory. All first-party
requests use a controlled repository; retain its finalized method/path/status
log, the exact generated build/POM, native command and exit, selected or unresolved
dependency graph, actual consumed-file hashes and origin records. A different
receipt or resolver-relevant metadata cannot be silently substituted.

Gradle must fail natively while resolving the configuration containing both
ordinary 0.2.0 adapter requests and three direct anchors requesting the selected
exact runtime. Retain the actual five root dependency requests, their constraint
flags and resolved or unresolved destinations, in addition to every selected
component and unresolved edge. The two adapter edges must remain ordinary,
transitive declarations. No published dependency or capability may be rewritten.

Require exactly two first-party unresolved edges and both native module rejection
sections. Each must name its exact counterpart GAV and `runtimeElements` variant,
and an exact capability published by both reviewed modules. A legacy-GAV conflict
is not relabeled as a shared hook-slot conflict. Capability-only and capability
with intrinsic strict-anchor collisions are distinct reported outcomes; a strict
collision never substitutes for either adapter capability cause.

The ordinary rejected graph can also contain executor/SPI version failures:
both adapters publish contradictory strict 5.5.2 and 5.5.3 requirements for those
two modules. Permit only these additional unresolved coordinates and native
exception chains, with both adapter paths, strict versions, dependency-versus-
constraint kind and reasons matched to the receipt-pinned `runtimeElements`
metadata. Every other native contributing path must start at a directly requested
anchor module and contain only ShardingSphere coordinates at 5.5.2/5.5.3, ending
at that same executor/SPI module. Its native path can describe intermediate
selections that are absent from the partially rejected component set. Reject duplicated
edges, foreign versions/modules, extra causes, missing paths and unbound reasons.
Retain these intrinsic failures explicitly. A partially rejected graph is not a
coherent or executable ShardingSphere runtime; normal runtime-coherence evidence
remains in the separate existing A-24 checks.

Apply only `java-base` to register the standard JVM attribute compatibility rules,
so dependencies targeting Java 8 remain eligible under Java 17. Do not apply the
`java` plugin, create source sets, compile sources or run tests. Missing artifacts,
Guava/variant failures, transport errors, checksum failures and any other unrelated
resolution cause still fail this verification. Module metadata requests and cached
bytes must match the separately reviewed receipt.

The first native attempt is preserved as failed: it contains both exact adapter
capability causes, intrinsic executor/SPI collisions, and unrelated Java-variant
failures from the prior base-only fixture. Reusing its raw messages in unit tests
does not reclassify that attempt as passing. A corrected fixture needs new frozen
fingerprints, review and a new evidence directory before any native rerun.

Maven dual-adapter cases first resolve and retain their actual dependency graph
without entering the lifecycle. The same generated POM then reaches `validate`
and fails specifically through Enforcer 3.6.3 `BannedDependencies`, naming the
opposite adapter. Both ordinary adapter declarations and their order, both resolved
adapter JARs, transitive core, and coherent exact ShardingSphere anchors must be
verified. Retain the raw rejection and selected graph; a summary label alone is
insufficient. No consumer compilation or test execution is allowed.

The two runtime-guard controls use a separate POM intentionally containing no
Enforcer execution. Maven must actually compile a fixture against the current
`io.github.ym0506.routecontract.api.RouteContract` entry and emit Java 17 classes.
Launch the selected Java executable in a new external process with the recorded
resolved classpath. The fixture must independently verify loaded core/adapter JAR
origins and receipt digests, the complete selected ShardingSphere coordinate set,
and all three actual opposite-runtime anchor identities before making one measured
`capture` call. An action sentinel must remain false. Accept only the coherent
opposite-runtime `RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME` result; missing anchors,
unavailable versions, mixed runtimes, legacy/provider collisions, linkage failures
or any action execution fail the case. These controls perform no SQL or MySQL work.

Preparation writes the explicit ten-case manifest, fixture input fingerprints and
generated build/POM/Java inputs with zero executed cases. Without the new reviewed
candidate it remains `PREPARED_WAITING_FOR_REVIEWED_STAGE`. Final execution must be
explicit and must reject stale input fingerprints before starting a build tool.
Only ten exact completed identities, every native cause check and an independent
raw-evidence audit can complete this bounded plan. This does not establish a public
release, external adoption, full A-24 completion or broader Java/platform support.

The preparation command is:

```sh
python3 scripts/verify-dual-resolver-boundaries.py \
  --prepare-only --evidence-directory /absolute/new-boundary-preparation
```

It writes `summary.json`, `explicit-case-plan.json`, `fixture-inputs.json`,
`prepared-case-inputs.json` and the ten generated consumer inputs. It launches no
Gradle, Maven or Java process. Supplying one or more `--case-id` arguments selects
only those existing identities; a subset cannot complete a native ten-case run.

Execution additionally requires all four independently reviewed staging arguments
(`--repository`, `--reviewed-receipt`, `--reviewed-receipt-sha256`,
`--staged-source-revision`), explicit `--java17-home`, `--maven`, the externally
pinned `--gradle-distribution-zip`, and the reviewed `--expected-input-manifest`.
Use a new evidence directory and explicit `--execute` only after the new candidate
and frozen inputs are reviewed. The runner rejects stale fingerprints before any
build command. A failed or timed-out command keeps its process identity, exact
arguments, partial native log and exit; the runner does not retry it automatically.

Passing native execution sets `nativeBoundaryMatrixComplete` only for all ten
identities. `completeBoundaryMatrix` and `independentlyAudited` remain false in the
runner output until a separate review establishes the raw-evidence audit. Unit
parser/preparation checks are labeled `verified - unit`; configuration-only or
synthetic Java compilation checks never stand in for staged native execution.

A separate aggregate audit may close the ten obligations using the four retained
Gradle passes and a later run of exactly the six pending Maven identities. Before
reuse, bind the Gradle commands, generated inputs, actual graph and native causes,
consumed metadata bytes, request origins, reviewed receipt and original staging
inventory. Show that the sidecar correction changes neither those nine payloads
nor the effective Gradle configuration, command construction or cause validation.
The aggregate must name both executions and their distinct runner/input hashes,
account for each identity exactly once, and retain all failed-attempt summaries.
It must report four plus six completed cases across executions, never a single
successful ten-case invocation or a successful Maven case from the failed attempt.
