# v0.1.4 Maven Central evidence

Status: **published; public files and both fresh-cache consumers verified**.
The Portal was observed as `PUBLISHED` on 2026-09-13 at 20:04 UTC.
The reviewed coordinate is
`io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.4`.

## Publication inputs and candidate verification

The inputs are bound to annotated tag
[`v0.1.4`](https://github.com/ym0506/routecontract/releases/tag/v0.1.4), source commit
[`a1eb22087eaf3a49e894d12ba56516efac99343f`](https://github.com/ym0506/routecontract/tree/a1eb22087eaf3a49e894d12ba56516efac99343f)
and [tagged workflow 34681713954, attempt 1](https://github.com/ym0506/routecontract/actions/runs/34681713954).
The [GitHub record](release-0.1.4-github.md) covers its separate twelve-asset release.

| Record | Identity |
| --- | --- |
| Central deployment | `63eaece1-4adf-48a5-a3a6-a15e35f6bad9` |
| Signed bundle SHA-256 | `15204d31f4accb01d3483ba2d97740f728267e851d0b874a431c06cd31a78a78` |
| Bundle receipt SHA-256 | `75fde4d709de8e24053b360a79a75dd5e6d2b3c2fd61078cea6ceb5e43739a65` |
| Reviewed payload manifest SHA-256 | `660e66d563061a6d50a7e88dfe3a04b8933e9f51aac97f4a48eb5b0c6f4590e7` |
| Main JAR SHA-256 | `b912725183a982ccddbfd4fa73ebe6a274590a674c0d72d94b0e1883d22b2816` |

The owner signed the five reviewed payloads locally. The bundle builder and separate
verifier checked their exact bytes, all checksums and five SHA384 detached signatures
against the public primary key `B400A4E34CA280C5B8B88C5DBE51764D5AF7DFBE`.
The prepared archive contained exactly thirty version files.

One upload was followed by Portal `VALIDATED` for one of one components. Before
publication, all thirty candidate files were downloaded through the authenticated
Portal file controls and compared byte for byte with the reviewed bundle. The
[prepublication comparison](release-0.1.4-central/candidate-readback.json) records
that result. The in-app browser could not export those downloads; native Chrome
completed them. No 0.1.3 download exception was carried forward.

One explicit Publish submission followed the candidate comparison. The deployment
must be reconciled read-only; neither upload nor publication should be resubmitted.

## Public file verification

At 20:04:25–20:04:39 UTC on 2026-09-13, anonymous downloads from
`https://repo.maven.apache.org/maven2/` matched all thirty reviewed files byte for byte.
The check used TLS verification and rejected redirects, credentials, configured proxies
and alternate repositories. See the [public readback](release-0.1.4-central/public-readback.json)
and [consumer receipt](release-0.1.4-central/consumer-receipt.json).

The readback tool retains `consumerExecutionVerified: false` and `availabilityClaim: false`;
it verifies files, not application execution. The results below are separate runtime evidence.

## Public consumer verification

**verified - MySQL; verified - ShardingSphere-JDBC 5.5.3.** Separate consumer projects
used fresh resolver caches, anonymous Central resolution and the reviewed release receipt.
Both ran on macOS 26.4.1/aarch64 with Temurin 17.0.20.1+1 and Docker 29.2.1.
They used the tagged v0.1.4 scripts without rebuilding or locally installing RouteContract.

| Consumer | Tests / failures / errors / skips | Result |
| --- | --- | --- |
| Gradle 9.7.1 / Java 17 | 3 / 0 / 0 / 0 | [Verified summary](release-0.1.4-central/gradle-summary.json) |
| Maven 3.9.14 / Java 17 | 3 / 0 / 0 / 0 | [Verified summary](release-0.1.4-central/maven-summary.json) |

Both verified the loaded public JAR, retained the exact business row `(201, 3, PAID)`,
and distinguished equality (`MATCH`, one attempt) from the same-result range
(`POLICY_VIOLATION`, two attempts, `RCM201`/`RCM202`). Four separate-JVM CLI comparisons
per consumer covered Markdown/JSON match exit 0 and regression exit 1.
The normalized reviewed-receipt SHA-256 is
`4491b796a0b52263e34a071d699c5afd5ec06daec9bf4e94c58f1e2d937b7278`.

The Java 17 publication wrappers above are not Java 21 runs. Separately,
[First project run 34779973994](https://github.com/ym0506/routecontract/actions/runs/34779973994)
passed Maven and Gradle on both Java 17 and Java 21 against the pinned public 0.1.4 JAR.
Its example source was `4dc50fa73734314be381bd65ab6faafac2212585`, distinct from the released
library's tagged source. All four downloaded artifacts were inspected for the actual test
JVM, consumer/library class versions, public JAR hash, three JSON comparison stages and
three direct-assertion stages. See the [retained four-cell record](release-0.1.4-central/first-project-java17-java21.json).
Missing-baseline rejection and capture without approval also passed in each workflow cell.
The [maintained workflow](../../.github/workflows/first-project.yml) keeps this matrix as a
merge gate for the current example.
The earlier [Java 21 qualification](../java21-runtime-acceptance.md) remains a dated
0.1.3 record and is not relabeled as a 0.1.4 consumer run.

Maven's verified consumption covers POM/JAR; the separate thirty-file readback also
covers Gradle metadata. Gradle's configured repository does not independently constrain
final redirect origins; the separate public-byte readback rejects redirects.

## Reproduce

Use Java 17, Python 3.10+, Git, curl, Maven 3.9.14 and a running Docker daemon.
Start from tag `v0.1.4` (commit `a1eb22087eaf3a49e894d12ba56516efac99343f`).
Download the [consumer receipt](release-0.1.4-central/consumer-receipt.json) outside
the checkout and check its SHA-256:
`cb50fd4998f719d8b7cbd24d68fc70a72034929bcc92834df312b6cb23e87a13`.
With `JAVA_HOME` set to your Java 17 JDK, run from that tagged checkout:

```bash
python3 -I scripts/verify-public-gradle-release-consumer.py \
  --receipt /absolute/path/to/consumer-receipt.json \
  --evidence-directory /absolute/path/to/new-gradle-evidence

python3 -I scripts/verify-public-maven-release-consumer.py \
  --receipt /absolute/path/to/consumer-receipt.json \
  --java-home "$JAVA_HOME" --maven /absolute/path/to/maven-3.9.14/bin/mvn \
  --evidence-directory /absolute/path/to/new-maven-evidence
```

Evidence directories must be new and outside the checkout. These public consumers
need no signing key or Portal login. The full thirty-file readback tool additionally
needs the retained signed staging inputs; the public receipt alone does not recreate
that private release-preparation workspace. For the shorter current Java 17/21 example,
follow the [first-project guide](../first-project.md).

## Boundaries

These are maintainer-run distribution and compatibility checks. They do not establish
independent users, repeated external adoption, production use, performance improvement
or endorsement. Support remains exact ShardingSphere-JDBC 5.5.3 and synchronous,
non-batch PreparedStatement operations. Observations concern SQLExecutionHook-reported
physical JDBC execution attempts, not a complete route plan or transaction commit.
Historical 0.1.3 evidence and baselines retain their original meaning.
