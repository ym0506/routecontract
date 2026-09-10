# A-24 Maven staged-byte matrix

This harness extends acceptance evidence for the unreleased 0.2 candidate. It does not
publish artifacts or broaden released 0.1 compatibility. Each of Maven Java 17 and the
bounded Maven Java 21 fixture runs exact ShardingSphere 5.5.2 and 5.5.3 separately.

Every new run requires three explicit review inputs: `--reviewed-receipt`,
`--reviewed-receipt-sha256`, and `--staged-source-revision`. The expected digest
must come from independent review; the runner must never turn the receipt's own
computed digest into approval. The strict receipt loader must require exactly
nine unique, coordinate-bound JAR/POM/module payloads for 0.2.0. Check those bytes
against the supplied repository and bind the full source commit to unchanged
production/publication inputs with the existing `source_binding` verifier.
Retain the reviewed receipt, input inventory, source binding and executable
fixture hashes; recheck all of them before any complete-result claim. Existing
`008e125` offline and checksum evidence below remains historical diagnostic data.

The current-source Maven scope is exactly four cells: Java 17 and Java 21, each
on ShardingSphere 5.5.2 and 5.5.3. Each cell needs online, its own frozen-cache
offline replay, checksum, wrong-origin, wrong-anchor and wrong-non-anchor runs.
Every resolver-negative consumer must start with an absent Maven dependency
cache; copying the successful prime is reserved for offline replay. Maven-only
completion is recorded separately and never implies that the Gradle lanes or
all of A-24 are complete.

The actual negative graph must retain exactly the reviewed core and intended
adapter, materialize their pinned JAR/POM bytes from the controlled origin, and
identify the injected ShardingSphere dependency. Non-anchor negatives retain
all three correct runtime anchors. The native validation failure must identify
the complete exact ShardingSphere JAR coordinate on the banned-node line and
name `BannedDependencies`; version prefixes, separate mentions, unrelated rules
or download failures cannot substitute for that result.

Wrong-origin evidence first establishes the expected bytes and actual unintended
origin, then requires rejection by the expected-origin verifier. After the
repository has stopped, retain successful GETs for all four exact core/adapter
JAR/POMs, endpoint/settings identity, origin-marker hashes, actual commands/logs
and selected graph. Graph negatives retain their actual `negative-pom.xml` hash.

An initially absent repository-side Central response cache may reuse verified
third-party HTTP responses during one matrix run. It imports no developer or
primed Maven cache and preserves certificate validation, body/deadline bounds
and final byte verification. Every online/negative Maven consumer still fetches
into its own absent cache with strict checksums. The receipt records response
reuse separately from consumed artifact identity.

## Final86 Maven result, 2026-09-08

All four existing Maven Java 17/21 × ShardingSphere 5.5.2/5.5.3 profiles passed
against reviewed local unsigned source `86a0be5d2e444f3b73925122fa448d9d1a324edd`,
using independently supplied receipt SHA-256
`1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e`.
The [final packaged-consumer evidence](evidence/a24-maven-final-86a0be5-2026-09-08.md)
and [machine-readable receipt](evidence/a24-maven-final-86a0be5-2026-09-08.json)
record this new execution separately from the historical `4e06694` records below.

One sequential run finished with exit 0 and full EOF: **24 actual MySQL test
executions, 16 negative controls**, zero failures/errors/skips and no uncaught
thread exception in the complete retained logs. Each of the four profiles passed
three online and three offline tests plus exact checksum, wrong-origin,
wrong-anchor and wrong-non-anchor controls. Actual JVM/classfile boundaries,
closed prime endpoints, OS egress denial, same local images and invoked no-pull
controls were independently checked. The existing CLI assertions invoke
`ManifestReviewCli.run` in-process.

Independent audit rechecked 56 commands, 40 compiled classfile occurrences,
9,064 frozen cache entries, 3,380 offline cloned JAR/POM/module payload
occurrences and 2,320 repository response bodies. All 14 executed fixture/helper
inputs matched their prefreeze and retained copied consumer inputs; the runner
does not create separate executed-harness copies. The shared Gradle build was
recorded at SHA-256 `7f465d3ed2bf656853bf1afe913468e5aaa5c1505e9f8cabf9bc248411dc835f`;
Maven copies its own POM and the shared source without executing that Gradle
build. All 69 production/publication files, 90 staged files, nine primary
payloads, tools, certificate, receipt and review decision remained unchanged.

Raw aggregate SHA-256:
`230340c7063cb2bd49540038bdfe1b4f55c4d32dfa3e5a96ab6f6b7a6a4b7f40`.
Independent retained audit SHA-256:
`34527b53575710699f91210679ec8e0812994d345a5b8c8f9f681e70a376a306`.

The result records `completeMavenA24Matrix=true`, `finalInputsUnchanged=true`,
`complete=false`, `fullA24Complete=false`, and `publicConsumption=false`.
It establishes the finite Maven component only; independent Gradle lanes,
Gradle Java 21, public release and external adoption are not established here.
The final86 matrix ran once without a retry and reuses none of the historical
executions in its totals. No source, staging, baseline or workload changes were
needed for this final-byte execution.

## Current-source invocation

Use an independently reviewed receipt and expected hash supplied together with
the full staged source revision. The hash must be supplied as a reviewed input;
do not replace it with a command that computes approval from the input file.
The evidence directory must not exist and must be outside source and staging.

```sh
python3 scripts/verify-a24-maven-consumer.py \
  --repository "$REVIEWED_STAGED_REPOSITORY" \
  --reviewed-receipt "$REVIEWED_STAGED_RECEIPT" \
  --reviewed-receipt-sha256 "$INDEPENDENTLY_REVIEWED_RECEIPT_SHA256" \
  --staged-source-revision "$REVIEWED_STAGED_SOURCE_REVISION" \
  --evidence-directory "$NEW_EVIDENCE_DIRECTORY" \
  --java17-home "$JAVA17_HOME" \
  --java21-home "$JAVA21_HOME" \
  --maven "$MAVEN_3_9_14_EXECUTABLE"
```

Omitting cell selectors runs exactly Maven Java 17/21 × ShardingSphere 5.5.2/5.5.3.
`--positive-only --java-feature 17 --runtime 5.5.2` runs one diagnostic online/offline
pair and cannot complete the Maven matrix. Even a full Maven run leaves top-level
`complete=false` and `fullA24Complete=false`; only `completeMavenA24Matrix` can
become true after all four cells and final input rechecks. This does not establish
Gradle/Java 21 support or complete the independent Gradle A-24 lanes.

Historical unit evidence for the unchanged harness (`verified - unit`): 24 focused tests cover explicit
review-input validation, exact graph/origin rejection, empty negative caches,
both Java compilation boundaries, and final receipt-change rejection. Stubbed
cell aggregation tests make no Maven/MySQL claim. The first historical `4e06694`
matrix attempt passed the Java 17 / 5.5.2 online and offline runs, three MySQL
tests each, then stopped before native checksum validation because the copied
reviewed JAR retained read-only permissions. The regression fix makes only the
disposable checksum target writable; original staging and copied sidecars remain
unchanged. That failed partial run is preserved and excluded from the successful
historical four-cell `4e06694` result below; neither contributes to final86 totals.

## Historical 4e06694 Maven result, 2026-09-08

`verified - MySQL`, `verified - ShardingSphere-JDBC 5.5.2`, and
`verified - ShardingSphere-JDBC 5.5.3`: all four Maven cells passed against the
independently reviewed unsigned local staging from full source revision
`4e066942f6e244345fe908970b81446f9e08f64e`. The supplied reviewed-receipt SHA-256
was `38b2269eca162f121fd3996c56df8b894ae2f43cedeb08fcc627032cf70eaa43`.

| Java / ShardingSphere | Online MySQL | Offline MySQL | Negative controls | Frozen cache entries |
| --- | --- | --- | --- | --- |
| 17.0.15 / 5.5.2 | 3 passed | 3 passed | 4 passed | 2,453 unchanged |
| 17.0.15 / 5.5.3 | 3 passed | 3 passed | 4 passed | 2,079 unchanged |
| 21.0.11 / 5.5.2 | 3 passed | 3 passed | 4 passed | 2,453 unchanged |
| 21.0.11 / 5.5.3 | 3 passed | 3 passed | 4 passed | 2,079 unchanged |

The single successful sequential matrix used Maven 3.9.14 on macOS 26.4.1 arm64.
Its 24 actual MySQL test executions had no failures, errors or skips. Every
online/offline pair retained the expected business row while the hook-reported
physical JDBC execution attempt count changed from one to two; the approved
baseline stayed unchanged, route-policy rejection was verified, and both JSON
and Markdown CLI assertions returned the expected regression code. The fixture
compiled and executed Java 17 classfiles (major 61) or Java 21 classfiles (major 65)
in their corresponding lanes. This is the exact synchronous PreparedStatement,
non-batch fixture, not a broader application or concurrency claim.

Every cell also passed the four fresh-cache controls: native strict rejection
of the exact one-byte-corrupted core JAR, rejection of correct reviewed bytes
from the wrong repository origin, native Enforcer rejection of the exact wrong
runtime anchor, and native Enforcer rejection of the exact wrong non-anchor
while all three correct anchors remained selected. Every offline run used its
own frozen prime after the original HTTP endpoint had closed, with OS-denied
external access and the same locally inspected MySQL/Ryuk images under an
actually invoked no-pull policy. All nine reviewed payloads, staging inventory,
reviewed receipt, source binding and 14 executed fixture/helper hashes passed
the final unchanged-input check.

The raw aggregate SHA-256 is
`db7b84385e2ff9a0cbe4e092aa12954fe792d605099101dfd9f8c17b38667856`;
the executed harness SHA-256 is
`86d0e9fdfb56fde20d82e3c1c5afa79c3a005f4d1baf5347137dca4fa164fc76`.
The raw result records `completeMavenA24Matrix=true`, `finalInputsUnchanged=true`,
`complete=false`, `fullA24Complete=false`, and `publicConsumption=false`.
This closes the finite Maven component only. It does not establish Gradle Java 21
support, completion of the independent Gradle A-24 lanes, a public 0.2 release,
or external user adoption. The earlier `008e125` diagnostics below remain
historical and are not added to the 24-test or 16-control totals.

## Per-cell acceptance contract

Each cell starts with an absent consumer, Maven repository and private home. One online
prime compiles and executes the three existing MySQL tests, including exact business-row,
route-policy, provider-origin, privacy and JSON/Markdown CLI assertions. The selected
whole ShardingSphere group and staged core/adapter JAR/POM origins must match. Java 21
uses Maven/JVM 21, compiles both the boundary probe and fixture tests to classfile 65,
and executes the same MySQL assertions; it does not imply support for another profile.

After that successful prime, retain a read-only cache snapshot and complete relative
path/size/SHA-256 inventory. Copy it into a disposable writable offline cache. A separate
fresh consumer performs full `clean verify` and graph verification using Maven `-o`
inside the independently proved macOS outbound-network sandbox. The online repository
proxy is stopped before this step. Loopback and the local Docker socket remain available.
The immutable snapshot must be unchanged before and after offline execution.

Each current-source run also establishes all of the following offline controls:

- Run a compiled Java socket control using the exact requested JDK under the same
  kernel policy as Maven. The trusted `JAVA_TOOL_OPTIONS` value must force IPv4
  for Maven and every inherited Java child. A reachable external address must be
  rejected with the native permission error while loopback remains usable.
- Remove inherited proxy and Java option variables. Preserve only the verified local
  Docker Unix endpoint, pin the container host to loopback, and use a fresh private
  home so personal Testcontainers configuration cannot affect the run.
- Inspect the exact MySQL image referenced by the fixture and a pinned Ryuk image
  locally before each execution. Do not pull missing images. Install a public
  Testcontainers `ImagePullPolicy` implementation that always returns false and
  require its actual invocation for both images in the successful MySQL run. Check
  that the test JVM received the IPv4 property and the intended policy class.
  The disposable fixture may normalize the existing combined MySQL tag/digest
  spelling to the digest-only Docker reference, preserving the exact immutable
  digest. Record this mapping; never fall back to a mutable tag or fetch an image.
  Keep the complete online image manifest pinned for the offline lane; deriving
  different Ryuk digests independently from a mutable tag must fail before replay.
- Prove that the exact HTTP prime endpoint refuses a connection after shutdown,
  retain its URL unchanged for Maven `--offline`, and keep the complete frozen
  cache inventory unchanged. A live `file:` or HTTP repository is not cache-only
  evidence.

This is a direct kernel egress barrier for the harness processes plus a no-pull
policy for the fixed Testcontainers fixture, not a general network sandbox for an
arbitrary Docker workload or protection against an unrelated host loopback proxy.
These prerequisites were first exercised in a positive Java 17 / 5.5.2
online/offline diagnostic against retained reviewed `008e125` staging. That
historical result remains diagnostic-only and leaves A-24 incomplete. It does
not substitute for the checksum/origin/graph controls or the historical
`4e06694` matrix above. The original failed receipts are preserved.

Every cell also requires actual negative executions in separate disposable consumers:

- A staged core JAR has one byte changed while original checksum sidecars remain. A new
  first-party download must fail Maven strict checksum verification, not a missing URL.
- Correct first-party bytes are downloaded from a separate unintended repository endpoint
  and ID. Byte checks pass but the controlled-origin gate rejects its actual origin records.
- An ordinary POM selects a wrong runtime anchor; the selected dependency graph identifies
  it and Enforcer rejects that exact dependency.
- An ordinary POM selects a wrong non-anchor while all three runtime anchors stay correct;
  the actual graph and exact Enforcer rejection are retained.

No unavailable dependency, generic process failure, skipped test, help-only offline run,
fabricated graph or changed baseline counts as acceptance. Raw evidence stays private.
Public evidence is a minimized result with source/receipt hashes and explicit boundaries.

## Historical offline prerequisite result, 2026-09-08

`verified - MySQL`, `verified - ShardingSphere-JDBC 5.5.2`: one Java 17 /
Maven 3.9.14 positive-only diagnostic against the retained reviewed `008e125`
staging passed three online and three offline fixture tests. The actual Java
network probe rejected external access with the native permission error, the
closed prime endpoint refused a new connection, both image policies were invoked,
and all 2,453 frozen cache entries retained identical path/size/SHA-256 inventories.
Both lanes used the same pinned MySQL and Ryuk image manifests. This is maintainer
staged-byte evidence, not public consumption, independent adoption, or a completed
A-24 matrix.

The across-lane image-manifest guard was added after that diagnostic and directly checked
against all four retained before/after manifests. Its rejection case has a focused
unit test; the later historical `4e06694` matrix above exercised that guard in all four
cells. An earlier
diagnostic failed in the online mirror because its Python distribution lacked a
usable CA store. The successful command used the bundled Python runtime and
`SSL_CERT_FILE=/etc/ssl/cert.pem`; certificate verification remained enabled.

At the end of this positive-only run, exact modified-core-JAR checksum rejection
binding was still outstanding; the separate diagnostic below subsequently verified
that control. Origin/graph negatives and a complete run against newly reviewed
staging were still outstanding at that point; the historical `4e06694` Maven result
above now supplies them for its four cells. This
positive diagnostic retains `diagnosticOnly=true` and `complete=false`.

The no-pull behavior was checked against Testcontainers 1.21.4's public
[`RemoteDockerImage` implementation](https://github.com/testcontainers/testcontainers-java/blob/1.21.4/core/src/main/java/org/testcontainers/images/RemoteDockerImage.java)
and the exact cached JAR. The custom policy directly implements `ImagePullPolicy`;
it does not extend `AbstractImagePullPolicy`, which can permit a missing-image pull
before consulting its subclass.

## Exact checksum negative proof

Before accepting a checksum negative, independently establish the original core JAR
against the reviewed receipt, then change exactly one byte in a disposable staging
copy. Retain the original and corrupted SHA-256, size, changed offset, and the
original/corrupted native Maven checksum digests. Checksum sidecars must retain
their exact original bytes and must describe the original JAR.

The native Maven process must run strict checksum mode and exit nonzero. Its
rejection must identify the exact core **JAR** coordinate and controlled repository
ID/URL, and report a checksum mismatch whose expected and actual values match the
original and deliberately corrupted JAR. The mirror must record a successful GET
for that exact JAR and the checksum sidecar used by Maven. A HEAD request, 404/502,
different artifact/POM, unrelated checksum text plus a core mention, changed
sidecar, different checksum value, or a mismatch from another repository cannot
prove this control. Retain the exact matching native rejection line and request
records, together with hashes of the full raw log, request log and command record.

This control was first exercised in one historical diagnostic against retained
`008e125` staging. That result does not close the final-source matrix, other
negative controls, or A-24; the historical `4e06694` matrix above records its own
checksum execution in every cell.

`verified - unit`: 16 focused harness tests passed, including rejection of unrelated
POM checksum text plus a separate core mention, incorrect endpoints/digests,
changed sidecars, HEAD/non-200 requests, and permissive checksum mode. The previous
generic checksum classifier can no longer accept a checksum case.

In a separate actual Maven 3.9.14 / Java 17 dependency-resolution diagnostic,
the one-byte-changed `routecontract-core:jar:0.2.0` was downloaded from
the controlled HTTP endpoint and rejected with native exit code 1. Maven's exact
transfer exception reported original SHA-1 `d66f94d2b201a971af7839d8c404eb5641676d7c`
and corrupted SHA-1 `92495fec9b3df96007de65322b5ef615f542dea8`. Both core JAR GETs and
both unchanged SHA-1 sidecar GETs completed with status 200. Independent SHA-256
checks bound these native digests to the reviewed original and one-byte-corrupted
JAR; other staging files and the frozen cache remained unchanged. The diagnostic
used the retained 5.5.2 dependency graph and did not execute new MySQL tests. It
retains `diagnosticOnly=true`, `checksumControlComplete=true`, and `complete=false`.
