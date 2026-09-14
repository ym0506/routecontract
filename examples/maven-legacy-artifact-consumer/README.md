# Maven legacy dependency ownership fixture

This maintainer fixture checks how **Maven 3.9.14 on Java 17** resolves real
pre-0.2 RouteContract artifacts alongside reviewed local 0.2 staging. The 0.2
artifacts are unpublished inputs; this is not a public installation guide.

The runner creates 45 separate consumer projects with initially absent Maven
dependency caches. Every case uses strict checksums and explicit settings that
route all requests through a controlled loopback repository. RouteContract
JAR/POM bytes are pinned to the legacy registry and staged receipt. Third-party
Central responses are downloaded once per run and may be reused by the HTTP
repository; no developer Maven cache is imported.

| Requests | Required result |
| --- | --- |
| Each legacy version alone | Its exact published JAR resolves. |
| Legacy plus current core or adapter 5.5.2, both orders | Actual graph resolves, then consumer Enforcer rejects the legacy node. |
| Equal-depth legacy/current same-GA requests, legacy first | Maven selects legacy; consumer Enforcer rejects it. |
| Same requests, current first | Maven selects current adapter/core bytes; Enforcer 3.6.3 still rejects the losing legacy node in its verbose graph. |
| Explicit consumer dependency management to 0.2.0, both orders | Both requests align to the exact current adapter/core; validation passes. |
| Incompatible hard singleton ranges, both orders | The Maven resolver reports both incompatible RouteContract requirements. |
| Latest legacy plus core, no ownership policy | Both JARs resolve, demonstrating why consumer policy is required. |

`legacy-ownership-enforcer.xml` is the copyable consumer-owned plugin fragment
for an asserted 0.2 lane. Insert it under `build/plugins`. It complements the
exact ShardingSphere version checks in the
[adapter design](../../docs/versioned-shardingsphere-adapters.md); it does not
replace them. A passing ordinary selected graph alone does not establish that
Enforcer accepts the declaration graph. To upgrade, remove the legacy request
or deliberately manage it to the reviewed current version; do not skip the rule.

Run from the repository root after preparing reviewed staging and installing
the pinned toolchain. All paths below are caller-supplied absolute paths; the
evidence directory must not exist and must be outside the checkout.

```bash
python3 scripts/verify-maven-legacy-artifact-consumer.py \
  --repository /absolute/path/to/reviewed-staged-repository \
  --staged-receipt /absolute/path/to/reviewed-staged-receipt.json \
  --staged-source-revision REVIEWED_SOURCE_COMMIT \
  --evidence-directory /absolute/path/to/new-maven-legacy-evidence \
  --java-home /absolute/path/to/jdk-17 \
  --maven /absolute/path/to/apache-maven-3.9.14/bin/mvn
```

An optional `--legacy-payload-directory` can point at previously downloaded
release payloads laid out as `<version>/<pinned-name>`; their bytes are checked
against the registry before use. Omitting it downloads the pinned public
payloads. `--case CASE_ID` selects a diagnostic subset and can never establish
the full matrix. `--workers` accepts 1–4; its default is 2.

The retained evidence contains tool versions, generated POMs, exact commands,
selected graphs, materialized JAR hashes, actual failure logs and final input
rechecks. A partial or failed run is not full A-27 Maven coverage. The checks
exercise dependency resolution and consumer Enforcer; they do not run SQL,
establish A-28 classpath guards, publish 0.2, or demonstrate external adoption.

See the [acceptance specification](../../docs/maven-legacy-resolver-acceptance.md)
for the complete proof requirements.
