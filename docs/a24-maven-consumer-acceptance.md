# A-24 Maven staged-byte matrix

This harness extends acceptance evidence for the unreleased 0.2 candidate. It does not
publish artifacts or broaden released 0.1 compatibility. Each of Maven Java 17 and the
bounded Maven Java 21 fixture runs exact ShardingSphere 5.5.2 and 5.5.3 separately.

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

The resumed offline prerequisite diagnostic must additionally establish all of the
following before another full matrix is attempted:

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
The diagnostic may execute one positive Java 17 / 5.5.2 online/offline pair against
the retained reviewed `008e125` staging. Its result must say diagnostic-only and
leave A-24 incomplete; checksum/origin/graph negatives and final-source full-matrix
evidence remain separate requirements. Preserve the original failed receipts.

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

## Offline prerequisite result, 2026-09-08

`verified - MySQL`, `verified - ShardingSphere-JDBC 5.5.2`: one Java 17 /
Maven 3.9.14 positive-only diagnostic against the retained reviewed `008e125`
staging passed three online and three offline fixture tests. The actual Java
network probe rejected external access with the native permission error, the
closed prime endpoint refused a new connection, both image policies were invoked,
and all 2,453 frozen cache entries retained identical path/size/SHA-256 inventories.
Both lanes used the same pinned MySQL and Ryuk image manifests. This is maintainer
staged-byte evidence, not public consumption, independent adoption, or a completed
A-24 matrix.

The across-lane image-manifest guard was added after that run and directly checked
against all four retained before/after manifests. Its rejection case has a focused
unit test; the later harness revision has not rerun the full matrix. An earlier
diagnostic failed in the online mirror because its Python distribution lacked a
usable CA store. The successful command used the bundled Python runtime and
`SSL_CERT_FILE=/etc/ssl/cert.pem`; certificate verification remained enabled.

At the end of this positive-only run, exact modified-core-JAR checksum rejection
binding was still outstanding; the separate diagnostic below subsequently verified
that control. Origin/graph negatives, all required Java/runtime/build-tool cells,
and a complete run against the final newly reviewed staged source remain. This
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

One diagnostic against retained `008e125` staging may establish this behavior;
it does not close the final-source matrix, other negative controls, or A-24.

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
