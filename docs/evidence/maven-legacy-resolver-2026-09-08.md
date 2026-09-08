# Maven legacy resolver acceptance, 2026-09-08

The local Maven portion of ADR A-27 passed **45/45 actual consumer cases** on
Maven 3.9.14 and Java 17. Together with the separately recorded
[37 Gradle cases](gradle-legacy-resolver-2026-09-08.md), this supplies both A-27
resolver lanes for the reviewed staging inputs. A-28 manual classpath guards,
SQL execution, other release gates, and public 0.2 publication remain separate.
No production source or published artifact changed for this work.

The [acceptance specification](../maven-legacy-resolver-acceptance.md) preceded
implementation. The [compact receipt](maven-legacy-resolver-2026-09-08.json)
binds every case to its generated POM, selected first-party JARs, real command
logs, result hashes, reviewed inputs and exact tested fixture hashes.

## Observed Maven behavior

| Case, repeated for all four distributed legacy versions | Cases | Actual result |
| --- | ---: | --- |
| Legacy alone | 4 | Exact published legacy JAR resolves. |
| Legacy + core, both orders | 8 | Actual graph and classpath materialize; consumer Enforcer rejects the legacy node. |
| Legacy + adapter 5.5.2, both orders | 8 | Actual graph and classpath materialize; consumer Enforcer rejects the legacy node. |
| Equal-depth same-GA requests, legacy first | 4 | Maven selects the legacy JAR; consumer Enforcer rejects it. |
| Equal-depth same-GA requests, current first | 4 | Maven selects exact current adapter553 + core JARs, with no legacy JAR on the classpath; Enforcer 3.6.3 rejects the losing legacy node. |
| Explicit consumer dependency management to 0.2.0, both orders | 8 | Both requests align to current adapter553/core; graph, materialized bytes and validation pass. |
| Incompatible hard singleton ranges, both orders | 8 | Maven's actual resolver reports both incompatible RouteContract requirements. |
| Latest legacy + core, ownership policy omitted | 1 | Both exact JARs resolve; matching policy-enabled cases reject the combination. |

The totals are **13 resolved controls, 24 Enforcer rejections and 8 strict
resolver conflicts**. Every successful current selection independently checks
the complete resolved ShardingSphere group at exactly 5.5.3, including the
executor anchor, and verifies the first-party JAR hashes and repository origins.
The rejected legacy/5.5.2 combinations are dependency-policy evidence; they do
not establish a supported mixed runtime.

This corrects an earlier selected-only assumption in the
[adapter design](../versioned-shardingsphere-adapters.md). Maven's ordinary
equal-depth mediation follows declaration order, as described in its
[dependency guide](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html).
Pinned Enforcer 3.6.3 examines a verbose graph including conflict-loser nodes;
its [implementation](https://github.com/apache/maven-enforcer/blob/enforcer-3.6.3/enforcer-rules/src/main/java/org/apache/maven/enforcer/rules/dependency/BannedDependenciesBase.java#L99-L129)
and the actual current-first failure logs agree. Dependency management is an
explicit consumer decision, not automatic highest-version selection.

The copyable [ownership policy](../../examples/maven-legacy-artifact-consumer/legacy-ownership-enforcer.xml)
complements exact ShardingSphere group-version checks. A consumer must remove
or deliberately align legacy requests when upgrading; skipping Enforcer is
not a passing asserted 0.2 lane.

## Inputs, isolation and environment

Execution used CPython 3.13.0, Homebrew OpenJDK 17.0.15, Maven 3.9.14
(`996c630dbc656c76214ce58821dcc58be960875b`), and macOS 26.4.1 aarch64.
Two cases ran concurrently. Each case started outside the checkout with its own
copied consumer and absent Maven dependency cache, explicit local/global
settings, and strict checksum handling.

The [legacy registry](../../scripts/legacy-artifact-inputs.json) supplied the
real distributed `0.1.0`, `0.1.2`, `0.1.3` and `0.1.0-rc2` payloads. All nine
legacy JAR/POM/module payloads were rechecked against their pins and class/service
layout before use. `0.1.1` and `0.1.0-rc1` remain tag-only source/layout evidence;
they were not substituted for executable releases. Maven consumes JAR/POM
metadata; checking the public 0.1.3 `.module` does not make it Maven evidence.

The nine current staged payloads were bound to reviewed source
`008e125a0648ed615842a572d60fd453698bb5aa`. The checkout was
`3a136a6f006c8040b0facadafc18606d2a63600a` plus the recorded fixture/runner
files. Production and publication inputs, including LICENSE/NOTICE, were
unchanged relative to that staged source. These remain reviewed local staging
bytes, not a public 0.2 release or a claim of identity to later CI metadata.
Repeat the gate if the publication payload set changes.

Sixteen generated POM-only carriers expressed distinct same-depth requests.
Their exact bytes and requested versions are retained; they contain no
substitute RouteContract JARs or classes. All first-party and carrier payloads
came exclusively from the controlled loopback repository, with consumed
JAR/POM hashes and Maven origin markers checked independently.

Third-party traffic used the existing anonymous, certificate-validating
Central-only transport. A new per-run repository response cache downloaded
1,120 unique third-party responses totaling 50,429,767 bytes. It imported no
developer Maven cache. Every Maven case still fetched its own files over HTTP
into a fresh dependency cache with strict checksums. Cache body/metadata IO
rejects symlink entries, checks byte identity on reuse and completion, and
enforces a 100 MiB response bound plus a 600-second initial-download deadline
checked after every read, including EOF.

The cache returned 29,298 verified response objects, including 28,178 reuses.
Those counts do not prove completed HTTP delivery or Maven consumption;
selected graphs, classpaths, hashes and origin markers provide that evidence.
The controlled repository retained 29,762 HTTP request records, all status 200.

- Registry SHA-256: `f03dc0d63a23e68fd4cc6895efff1ba1175143e084b76f25f8e70fd19a04419f`.
- Staged receipt SHA-256: `ff4ad23aca357baa0a29f6ddac3a8b3708f1dbe62e0a73f200f84737449fdb41`.
- Full summary SHA-256: `282c62bf54e2ac01debf243a4b47426936b0dda222328fde55447cf0d265357b`.
- Central response receipt SHA-256: `493c07997ff1b96ba59fbace3238a090890d7e168fda97b830d399e8ac29511c`.

## Verification and reproduction

Evidence label `verified - unit`: **40/40 focused Python tests** passed for
fixture generation, case coverage, graph/classpath ownership, consumed bytes
and origins, semantic failure classification, and the per-run response cache.
The cache's pre-fix regression run reproduced four failures covering symlink
ancestor writes/readbacks/receipts and late EOF acceptance. Added classifier
regressions reject unrelated coordinates, widened ranges, version prefixes,
and infrastructure errors masquerading as expected failures.

The full matrix ran only after those fixes and an independent input review.
Every required case finished and the driver rechecked fixture hashes, the
reviewed receipt, production/publication source binding, all isolated input
bytes and all cache response hashes before writing `VERIFIED`. Earlier partial
diagnostics remain separate; they do not replace any case in this result.

The [fixture README](../../examples/maven-legacy-artifact-consumer/README.md)
explains the policy and input layout. From the tested checkout, set the path
variables to reviewed inputs and a new absent evidence directory:

```sh
python3 scripts/verify-maven-legacy-artifact-consumer.py \
  --repository "$REVIEWED_STAGED_REPOSITORY" \
  --staged-receipt "$REVIEWED_STAGED_RECEIPT" \
  --staged-source-revision 008e125a0648ed615842a572d60fd453698bb5aa \
  --evidence-directory "$NEW_EVIDENCE_DIRECTORY" \
  --java-home "$JAVA17_HOME" \
  --maven "$MAVEN_3_9_14_EXECUTABLE" \
  --legacy-payload-directory "$PINNED_LEGACY_INPUT_DIRECTORY" \
  --workers 2
```

The recorded local Python installation used its normal TLS validation with
`SSL_CERT_FILE=/etc/ssl/cert.pem`, the system CA bundle. No TLS verification was
disabled. Omit the legacy payload directory to download the pinned public
payloads instead. A `--case` subset can produce only partial verification.

Raw evidence retains the exact invocation/toolchain, controlled settings,
source/input snapshots, repository request and cache receipts, plus every
`cases/<case-id>/{case-inputs.json,commands.json,consumer/pom.xml,result.json}`
and actual Maven log. Successfully resolved cases additionally retain the
selected graph and materialized classpath. The public receipt omits private
paths and log bodies while binding those retained artifacts by hash.

This is Maven/Java dependency-resolution and materialization evidence. It
contains no SQL or MySQL execution and supplies no A-28 guard, public 0.2
publication, or external-adoption claim.
