# Maven staged consumer acceptance, 2026-09-08

All four bounded A-24 Maven cells passed against independently reviewed local
unsigned 0.2.0 staging. This is maintainer acceptance evidence for the Maven
component; it does not represent public consumption or completion of all A-24.

Evidence labels: `verified - MySQL`, `verified - ShardingSphere-JDBC 5.5.2`,
`verified - ShardingSphere-JDBC 5.5.3`, and `verified - unit` for the harness tests.

| Java | Exact ShardingSphere | Online MySQL | Offline MySQL | Negative controls | Frozen cache |
| --- | --- | --- | --- | --- | --- |
| 17.0.15 | 5.5.2 | 3 passed | 3 passed | 4 passed | 2,453 entries unchanged |
| 17.0.15 | 5.5.3 | 3 passed | 3 passed | 4 passed | 2,079 entries unchanged |
| 21.0.11 | 5.5.2 | 3 passed | 3 passed | 4 passed | 2,453 entries unchanged |
| 21.0.11 | 5.5.3 | 3 passed | 3 passed | 4 passed | 2,079 entries unchanged |

One sequential matrix ran 24 actual MySQL tests with no failures, errors or
skips, plus 16 negative controls. It used Maven 3.9.14 on macOS 26.4.1 arm64.
Java 17 and Java 21 fixtures compiled and executed classfiles with major versions
61 and 65 respectively. The 24 focused Python unit tests are a separate count.

Each positive lane verified actual core/adapter JAR origins and the exact
ShardingSphere dependency group: 122 selected 5.5.2 components or 75 selected
5.5.3 components. The same expected business row remained unchanged while the
hook-reported physical JDBC execution attempt count increased from one to two.
The reviewed baseline stayed unchanged, route-policy rejection produced
`RCM201` and `RCM202`, and both JSON and Markdown `ManifestReviewCli.run`
assertions returned code 1. These CLI calls execute in-process.

Every offline lane ran full Maven `clean verify` and dependency graph verification
against a disposable copy of its own frozen cache. Its original HTTP prime
endpoint had closed and refused a new connection. The same Java runtime passed
an independent OS-denial socket control, while loopback and the local Docker
socket remained available. Both actual MySQL/Ryuk no-pull policy calls were
observed, with identical locally inspected immutable images before and after
online/offline runs. All 9,064 frozen-cache entries retained their recorded bytes
across the four cells.

Every negative consumer started with an absent Maven cache and established its
specific cause from actual selected artifacts and native command evidence:

- Strict Maven checksum validation rejected the exact core JAR after one byte
  changed in a disposable staging copy. Original checksum sidecars stayed intact;
  exact GETs and native expected/actual checksum digests were bound to that JAR.
- Correct reviewed core/adapter bytes from the unintended repository ID were
  rejected by the expected-origin verifier. All four exact JAR/POM GETs and their
  origin markers were retained.
- A selected wrong runtime anchor was rejected by native `BannedDependencies`
  validation, identifying the exact ShardingSphere JAR and wrong version.
- A selected wrong non-anchor was rejected by the same exact native rule while
  all three correct anchors remained selected.

Nine reviewed JAR/POM/module payloads, the complete staging inventory, reviewed
receipt, source binding, and 14 executed fixture/helper files all passed the
final unchanged-input check. Maven consumes the reviewed JAR/POM payloads; the
global module-metadata byte check does not imply Gradle consumption.

The repository-side Central response cache began absent and imported no personal
or primed Maven cache. It retained 2,320 verified HTTP responses totaling
142,617,616 bytes, with 27,164 cache hits and 29,484 response objects returned.
Those response counters are distinct from completed Maven artifact consumption;
each online/negative consumer still used its own fresh Maven cache.

## Reproduction and evidence binding

Use the three independently reviewed inputs with the
[A-24 Maven runner invocation](../a24-maven-consumer-acceptance.md#current-source-invocation).
Do not compute the receipt's approval hash inside the invocation. The source
revision and expected hash for this run were:

- Full staged source: `4e066942f6e244345fe908970b81446f9e08f64e`.
- Reviewed receipt SHA-256: `38b2269eca162f121fd3996c56df8b894ae2f43cedeb08fcc627032cf70eaa43`.
- Executed harness SHA-256: `86d0e9fdfb56fde20d82e3c1c5afa79c3a005f4d1baf5347137dca4fa164fc76`.
- Raw aggregate SHA-256: `db7b84385e2ff9a0cbe4e092aa12954fe792d605099101dfd9f8c17b38667856`.

The [minimized machine-readable receipt](a24-maven-staged-consumer-2026-09-08.json)
retains exact payload, fixture, classfile, raw command/log/report and cell-summary
hashes, image identities, negative causes, and completion boundaries. Raw
commands, local paths, SQL/bind details and machine-specific endpoints stay
private. The successful invocation used the bundled Python runtime with
`SSL_CERT_FILE=/etc/ssl/cert.pem`; TLS certificate verification stayed enabled.

## Preserved failed attempt and limits

The first current-source attempt passed three online and three offline Java
17 / 5.5.2 tests, then hit `PermissionError` before the native checksum run:
the disposable JAR copy inherited the read-only reviewed staging permission.
After diagnosing the terminal failure, a focused regression and independent
review checked the fix that adds owner-write permission only to the disposable
checksum target. Original staging and copied checksum sidecars were preserved.
The successful matrix used a new evidence directory and a new absent response
cache. The failed attempt and earlier `008e125` diagnostics are retained and
excluded from the successful 24-test and 16-control totals.

The raw result records `completeMavenA24Matrix=true`, `finalInputsUnchanged=true`,
`complete=false`, `fullA24Complete=false`, and `publicConsumption=false`.
This evidence covers the exact synchronous, non-batch PreparedStatement MySQL
fixture and hook-reported physical JDBC execution attempts. It does not claim
arbitrary async/concurrency behavior, a complete route plan, Gradle Java 21
support, a public 0.2 release, or external adoption. Its kernel egress barrier
applies to harness processes; no-pull checks for the fixed fixture are not a
network sandbox for arbitrary Docker workloads.
