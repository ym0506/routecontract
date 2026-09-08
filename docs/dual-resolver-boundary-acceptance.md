# Remaining A-15 / A-17 resolver and runtime boundaries

Status: implementation and preparation under review. The final ten cases require
the newly reviewed candidate containing the A-09 guard correction. No execution
against older staged bytes can complete this plan. Existing audited A-24 anchor
and non-anchor controls remain separate evidence; positive MySQL cases are not
repeated here.

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
staging and copy only receipt-pinned files into disposable evidence. All first-party
requests use a controlled repository; retain its finalized method/path/status
log, the exact generated build/POM, native command and exit, selected or unresolved
dependency graph, actual consumed-file hashes and origin records. A different
receipt or resolver-relevant metadata cannot be silently substituted.

Gradle must fail natively while resolving the configuration containing both
ordinary 0.2.0 adapter requests and the selected exact runtime. The captured graph
must identify both requests and their actual unresolved selectors. Bind a native
capability conflict to both adapter coordinates and an exact capability published
by both reviewed modules. A legacy-GAV capability conflict is not relabeled as a
shared hook-slot conflict. Missing artifacts, incompatible runtime constraints,
checksum failures or unrelated resolution errors cannot count. The module metadata
requests and cached metadata bytes must match the receipt. No consumer source is
compiled and no test runs in these four cases.

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
only those existing identities; a subset cannot complete the native ten-case matrix.

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
