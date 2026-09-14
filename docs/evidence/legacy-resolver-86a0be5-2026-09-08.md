# A-27 resolver evidence for candidate 86a0be5

Evidence label: **verified - local Gradle/Maven resolver**. On 2026-09-08,
Gradle **37/37** and Maven **45/45** passed their complete existing matrices
against reviewed unsigned 0.2 staging from `86a0be5d2e444f3b73925122fa448d9d1a324edd`.
Each matrix ran once. Both outer processes exited 0, and complete command logs,
expected rejection causes, materialized first-party bytes and final EOF were
independently audited. This is dependency-resolution evidence.

| Consumer | Actual cases | Outcomes |
| --- | ---: | --- |
| Gradle 8.14.4 / Java 17 | 37 | 13 resolved selections/controls; 16 capability conflicts; 8 strict-version conflicts |
| Maven 3.9.14 / Java 17 | 45 | 13 resolved selections/controls; 24 Enforcer rejections; 8 strict-range conflicts |

The [machine-readable receipt](legacy-resolver-86a0be5-2026-09-08.json) retains all 82 case identities,
requests and orders, ownership-policy settings, outcomes, selected first-party
JAR hashes, raw-result/log digests, fixture pins and independent-audit digests.
The [earlier 4e06694 evidence](legacy-resolver-4e06694-2026-09-08.md) remains
historical evidence for its own bytes; no old case was substituted into these runs.

## What the cases establish

Both lanes use the real registry-pinned public `0.1.0`, `0.1.2`, `0.1.3` and
`0.1.0-rc2` artifacts. Tag-only `0.1.1` and `0.1.0-rc1` are excluded from executable
inputs. Legacy-only and ownership-policy-disabled consumers are explicit controls.
Capability ownership rules and Maven Enforcer are consumer configuration; adding
an arbitrary RouteContract dependency does not install these policies automatically.

Gradle checks both declaration orders for legacy/current combinations, ordinary
same-GA mediation and incompatible strict versions. Maven separately records
ordinary equal-depth mediation, explicit dependency management and hard singleton
ranges. In Maven's current-first bare case, exact current adapter553/core JARs are
selected but Enforcer 3.6.3 still rejects the losing legacy request. The actual
graph and the policy outcome are recorded separately. Explicit dependency
management aligns both orders to current bytes. Strict-range negatives require
a real resolver conflict containing both requirements; network errors and missing
artifacts do not count as passing rejections.

Gradle materialized **22 first-party JAR occurrences directly from its isolated
verified file repository**. Each of its 37 dependency caches began absent; only
the pinned wrapper distribution was seeded. This gate does not demonstrate
first-party HTTP delivery, cache-only offline consumption or dependency locking.

Maven retained **119 command logs**, **74 selected first-party JAR occurrences**
and **232 consumed pinned JAR/POM occurrences**. Every case used a fresh Maven
cache, explicit local/global settings and strict checksums. Candidate, legacy
and 16 POM-only request carriers came through the controlled loopback repository;
consumed hashes and origin markers were checked. The per-run Central response
cache started absent and imported no developer Maven cache. It verified
1,120 third-party responses (50,429,767 bytes);
response reuse alone is not evidence of completed HTTP delivery or Maven consumption.

## Input binding and reproduction

The tested consumer checkout was `3ad510a0af972231fbd074607936ee52be3cad1f`. Its
production/publication inputs match producer `86a0be5d2e444f3b73925122fa448d9d1a324edd`.
The reviewed nine-payload staged receipt SHA-256 was checked externally before
and after execution:

`1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e`

Both runs used Homebrew OpenJDK 17.0.15+0, CPython 3.12.14, macOS 26.4.1 aarch64
and the default two case workers. This local environment is separate from pinned
release CI. Maven was 3.9.14; Gradle was 8.14.4 with distribution SHA-256
`f1771298a70f6db5a29daf62378c4e18a17fc33c9ba6b14362e0cdf40610380d`.

Use a clean checkout at the tested consumer revision. Set the following path
variables to the reviewed staging repository, receipt, Java 17 installation,
Maven 3.9.14 executable, pinned Gradle ZIP and verified legacy input directory.
Each legacy payload lives under `<version>/<registered-filename>` and must match
the [legacy registry](../../scripts/legacy-artifact-inputs.json). Both evidence
directories must be absent and outside the checkout. The receipt digest is an
external trust check; these runners have no expected-receipt-digest argument.
The commands require these prepared inputs, not public 0.2 coordinates.

```sh
set -eu
export REVIEWED_STAGED_RECEIPT
export PYTHONDONTWRITEBYTECODE=1
export SSL_CERT_FILE="$TRUSTED_CA_BUNDLE"

python3 -B -c 'import hashlib,os,pathlib; p=pathlib.Path(os.environ["REVIEWED_STAGED_RECEIPT"]); assert hashlib.sha256(p.read_bytes()).hexdigest()=="1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e"'

python3 -B scripts/verify-gradle-legacy-artifact-consumer.py \
  --repository "$REVIEWED_STAGED_REPOSITORY" \
  --staged-receipt "$REVIEWED_STAGED_RECEIPT" \
  --staged-source-revision 86a0be5d2e444f3b73925122fa448d9d1a324edd \
  --evidence-directory "$NEW_GRADLE_EVIDENCE_DIRECTORY" \
  --java-home "$JAVA17_HOME" \
  --gradle-distribution-zip "$PINNED_GRADLE_8_14_4_ZIP" \
  --legacy-payload-directory "$PINNED_LEGACY_INPUT_DIRECTORY"

python3 -B scripts/verify-maven-legacy-artifact-consumer.py \
  --repository "$REVIEWED_STAGED_REPOSITORY" \
  --staged-receipt "$REVIEWED_STAGED_RECEIPT" \
  --staged-source-revision 86a0be5d2e444f3b73925122fa448d9d1a324edd \
  --evidence-directory "$NEW_MAVEN_EVIDENCE_DIRECTORY" \
  --java-home "$JAVA17_HOME" \
  --maven "$MAVEN_3_9_14_EXECUTABLE" \
  --legacy-payload-directory "$PINNED_LEGACY_INPUT_DIRECTORY"
```

The block exports `REVIEWED_STAGED_RECEIPT` and stops on a failed digest check.
Use the system trusted
CA bundle for the Python installation; the tested macOS run used `/etc/ssl/cert.pem`
with normal certificate validation. Retain exact argument arrays, toolchain,
input hashes before/after, every case report and full command output through
EOF. Do not pass a case filter. Recheck the receipt after each command and audit
the completed raw records; a progress marker or exit code alone is insufficient.
The [Gradle](../legacy-resolver-acceptance.md) and
[Maven acceptance specifications](../maven-legacy-resolver-acceptance.md) define
the required semantic checks.

| Retained private artifact | SHA-256 |
| --- | --- |
| Gradle summary | `41a935ee6004755ee5d4f9aafb8cf327b9a1706aa3d3ab781d3c7419a1e95cec` |
| Maven summary | `31f3c49ddf607cfe224928c1be0a08afeb8e2dadc55da5d6c174d6cb9cd22484` |
| Gradle independent raw audit | `b6017a1e13ae6293868e07806cc5a27f3b440ddf8373ee4637bd2143d90d6ffb` |
| Maven independent raw audit | `01614abab07dc8868d90f32f37590e1fd47d96f82e059f3e18cd2250284933a4` |
| Maven independent transport/EOF audit | `40f9c87739bb52a640f6df1d805ba6d17def9f464188dfe8bbfd72f6714a5a53` |

Raw local paths and log bodies are omitted from the public receipt. No SQL or
MySQL execution, runtime guard, complete release, public 0.2 availability or
external adoption follows from A-27. Original A-28 remains **FAILED**. A-24,
A-26, A-29 and publication checks retain their own acceptance boundaries.
