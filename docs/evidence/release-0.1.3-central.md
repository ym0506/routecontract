# v0.1.3 Maven Central evidence

**Published files and both public consumers verified.**
The Portal showed `PUBLISHED` on 2026-09-08 at 00:18 UTC for deployment
`3660893a-c13e-40c0-98f9-d7ec16508069`, following one upload and one Publish submission.
The coordinate is `io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.3`.

The inputs are bound to annotated tag [`v0.1.3`](https://github.com/ym0506/routecontract/releases/tag/v0.1.3),
source commit [`f1efd71e32078dd5812268a1ad24ee73110ff61f`](https://github.com/ym0506/routecontract/tree/f1efd71e32078dd5812268a1ad24ee73110ff61f)
and successful tagged [release workflow 34122514785, attempt 1](https://github.com/ym0506/routecontract/actions/runs/34122514785).
The separate [GitHub release record](release-0.1.3-github.md) covers its immutable twelve-asset release.

## Public file verification

At 00:18:29–00:18:39 UTC on 2026-09-08, anonymous requests to
`https://repo.maven.apache.org/maven2/` matched all **30 files** against the reviewed signed
upload bundle: main/sources/Javadoc JARs, POM and Gradle Module Metadata, each with a signature
and four checksum files. The readback rejected redirects and compared exact response bytes.

| Record | SHA-256 |
| --- | --- |
| Signed upload bundle | `b57fe15bb6e911e625d945786e30916e1ee5fa4412889687a6a189c9f17acb22` |
| Bundle verification receipt | `37dc4684b808bd0bc206db7a15af50f7a9a47ac3c2fa5a7ee4238bc26acaa59e` |
| [Public readback JSON](release-0.1.3-central/public-readback.json) | `128d029c21585a9cca4b803c4210bebcf5fa8619cae4441e58357a431aaa95c2` |
| [Consumer receipt JSON](release-0.1.3-central/consumer-receipt.json) | `c8dbe046018f7b5ecc66b44c9bc18ce6d1712528ac02b5d80e120d103506a242` |

The JSON files contain public coordinates, paths, sizes, hashes and verification metadata. The readback's
`publicReadbackVerified=true` proves its file comparison; `consumerExecutionVerified=false`
and `availabilityClaim=false` remain unchanged because that tool does not run consumers.
The consumer receipt pins the public JAR, POM and module metadata; it is distinct from the
bundle verification receipt.

The prepublication remote candidate-byte comparison remains **unverified**: the available
authenticated download tooling could not transfer the Portal candidate for comparison.
This is a recorded exception to the prepublication procedure. Matching the later public files
does not retroactively complete that earlier check; not every prepublication gate passed.

## Public consumer verification

**verified - MySQL; verified - ShardingSphere-JDBC 5.5.3.** On 2026-09-08, separate
consumer projects ran locally with fresh resolver caches against public Central bytes.
These are maintainer-run distribution checks, not independent external-user adoption.

| Consumer | Tests / failures / errors / skips | Retained summary SHA-256 |
| --- | --- | --- |
| [Gradle 8.14.4 / Java 17](release-0.1.3-central/gradle-summary.json) | 3 / 0 / 0 / 0 | `42edd8ae5bb42f293202fb57188fa02aa75fb7f5c36f204e80f1f13a09c18808` |
| [Maven 3.9.14 / Java 17.0.15](release-0.1.3-central/maven-summary.json) | 3 / 0 / 0 / 0 | `f31d7a08ec7cca9a56e5b1a27f7b6fddf9f2e574731c248f68f4acf223bb8987` |

Both wrappers recorded normalized reviewed-receipt SHA-256
`03e99a90ca8e09c0440d534d30141295796131756b6899c457e615a8ab71c624`;
this normalized JSON hash differs from the published receipt's original-byte hash above.
Maven recorded Homebrew Java 17.0.15 on macOS 26.4.1/aarch64.

The fixtures retained business row `(201, 3, PAID)`: equality was `MATCH` with one
observed attempt; a same-result range had two attempts and failed with `RCM201`/`RCM202`.
Loaded JAR identity and four separate-JVM CLI checks passed: Markdown/JSON MATCH exited 0,
while both regression reports exited 1. Independent local review also confirmed the
Maven business rows, unchanged approved baseline, CLI outputs and retained source
(review-record SHA-256 `f53ffeb873f89abd504283f15f5efc9838704567734bee4a0f3a8cfb919d05c8`).
Independent Gradle review confirmed the three clean tests, four CLI comparisons,
loaded JAR identity and retained source
(review-record SHA-256 `27e6215a6fd433b51938bd7e8e6356cd63c40de7e3ba32ff62124e750139f959`).
Earlier local and missing-version attempts remain in the [consumer history](../public-release-consumers.md).

## Reproduce the public consumers

You need Git, Python 3.10+, curl, a working Docker daemon, network access, a Java 17 JDK
and exact Apache Maven 3.9.14. Set the two tool paths below to your installed tools.
The published receipt and tagged scripts are sufficient; no Portal login, signing key or
private staging repository is needed. Evidence directories must be new and outside the checkout.

```bash
(
set -e
export JAVA_HOME="/absolute/path/to/jdk-17"
maven_bin="/absolute/path/to/apache-maven-3.9.14/bin/mvn"
run_root="$(mktemp -d "${TMPDIR:-/tmp}/routecontract-central-reproduce.XXXXXX")"
run_root="$(cd "${run_root}" && pwd -P)"
git clone --depth 1 --branch v0.1.3 --single-branch \
  https://github.com/ym0506/routecontract.git "${run_root}/source"
test "$(git -C "${run_root}/source" rev-parse refs/tags/v0.1.3)" = e65484c2fb50b8e73235acca9a4daed27a9e703a
test "$(git -C "${run_root}/source" rev-parse HEAD)" = f1efd71e32078dd5812268a1ad24ee73110ff61f
curl --disable --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
  https://raw.githubusercontent.com/ym0506/routecontract/main/docs/evidence/release-0.1.3-central/consumer-receipt.json \
  --output "${run_root}/consumer-receipt.json"
python3 -I -c 'import hashlib,pathlib,sys; actual=hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest(); sys.exit(0 if actual=="c8dbe046018f7b5ecc66b44c9bc18ce6d1712528ac02b5d80e120d103506a242" else "consumer receipt checksum mismatch")' "${run_root}/consumer-receipt.json"
python3 -I "${run_root}/source/scripts/verify-public-gradle-release-consumer.py" \
  --receipt "${run_root}/consumer-receipt.json" \
  --evidence-directory "${run_root}/gradle-evidence"
python3 -I "${run_root}/source/scripts/verify-public-maven-release-consumer.py" \
  --receipt "${run_root}/consumer-receipt.json" \
  --java-home "${JAVA_HOME}" --maven "${maven_bin}" \
  --evidence-directory "${run_root}/maven-evidence"
)
```

Each wrapper creates a fresh resolver cache and requires three MySQL tests with no failures,
errors or skips. It checks the expected release bytes and exact ShardingSphere 5.5.3 graph.
Gradle's configured Central URL does not independently prove final redirect origins; the
separate file readback rejects redirects. Maven's configured native transport rejects them.

The full `verify-public-release-central-readback.py` wrapper additionally requires the
maintainer-retained staging repository, signed bundle, bundle receipt, reviewed payload
manifest and public-key GPG home. Those prepublication signing/review inputs are not supplied
by the public JSON records, so the consumer commands above do not rerun that full wrapper.
Verification itself does not require the private signing key.

Support remains Java 17, exact ShardingSphere-JDBC 5.5.3 and synchronous non-batch
`PreparedStatement` operations. Evidence concerns `SQLExecutionHook`-reported physical JDBC
execution attempts, not complete routing, transaction commit, external adoption, production
use or performance. Keep business assertions and reviewed baselines. Historical v0.1.2
pins and evidence remain unchanged; the 0.2 adapter work is separate.
