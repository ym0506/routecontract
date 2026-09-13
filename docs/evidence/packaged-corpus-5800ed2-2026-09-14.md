# Existing MySQL scenarios through the installed 0.2 candidate

An application can return the expected rows while a change makes it contact more
data sources or issue more physical JDBC execution attempts. The existing corpus
checks that RouteContract reports those changes when installed from its candidate
JARs in a separate project. Passing tests inside the development repository alone
would not establish that installation behavior.

**Verified on 2026-09-14:** all 28 existing MySQL tests in six suites passed with
the unsigned CI candidate from producer `5800ed2`. Both consumers used fresh
dependency caches and the existing assertions and golden inputs. No retry or
baseline regeneration was needed. This qualifies the packaged runtime binding
for these exact bytes; 0.2 remains unreleased and human baseline review remains
pending.

The [minimized machine-readable evidence](packaged-corpus-5800ed2-2026-09-14.json)
records exact method names, artifact and input hashes, graph counts and retained
result bindings. Raw logs, SQL, parameters, connection details, local paths and
process identities are not included in the public record.

## Execution and results

Two standalone Gradle 9.7.1 consumers ran sequentially on macOS/aarch64 with
Temurin 17.0.20.1+1 and Docker 29.2.1. Both used the digest-pinned MySQL 8.4.11
image. Each consumer's dependency cache began absent; only the checksum-pinned
Gradle distribution ZIP was seeded. Both native builds and the enclosing runner
exited 0.

| Exact ShardingSphere runtime | Suites / tests | Failures / errors / skips | Compile modules / artifacts | Runtime modules / artifacts |
| --- | --- | --- | --- | --- |
| 5.5.3 | 4 / 14 | 0 / 0 / 0 | 108 / 105 | 150 / 146 |
| 5.5.2 | 2 / 14 | 0 / 0 / 0 | 183 / 180 | 208 / 204 |

The original tests retain business-result checks, safe controls, changes that
expand observed execution, failure and ineligibility boundaries, secret
minimization, and the 5.5.3 datasource-proxy comparison. Each runtime includes
the existing eight shapes repeated 20 times and 20 concurrently open capture
pairs. These loops are part of the 28 tests. Physical callback overlap was not
forced or measured.

All 14 version-specific 5.5.2 corpus output files matched their unchanged golden
files. Existing manifest and report comparisons remained enabled. A supplemental
extension added zero test cases and recorded before/after provenance for all six
suites inside their actual test JVMs. All 12 records identified the expected
current API, core JAR, exact adapter and provider descriptors.

## Exact inputs and retained checks

- CI producer: `5800ed2960aefbf63c01d2ebaf2265278d662494`, from
  [CI run 34786348241](https://github.com/ym0506/routecontract/actions/runs/34786348241).
- Consumer checkout: `5c2ebb3e4af38571b2c127535d6a7b66195f0b0d`.
- Original corpus input revision: `fc80d17d0c7b888f7c6db024200870d29f21d7d9`.
- Receipt SHA-256: `9a4d745ff11508a8ab08dd8bced6a7893d8f6e6ff5baab34b3445aea652ba49c`.
- Gradle ZIP SHA-256: `acd53f1edaf02f1a8ff99879f8a34b302661a057d9b063ae9e35b552f804d20a`.

The nine coordinate-bound JAR/POM/module entries matched separately produced
local staging and retained local/CI Gradle and Maven consumer receipts before
execution. This is automated byte verification, not human baseline approval.
Production and publication inputs matched the staged producer throughout the
run. First-party dependencies resolved exclusively from the candidate repository;
third-party dependencies used Maven Central with strict locks and checksum
verification. Both lanes selected Jackson streaming 3.1.6 and the FasterXML
2.18.10 BOM; exact selected graphs remain bound to the evidence.

The runner revalidated both completed lanes after the second lane finished. A
separate read-only audit, performed by the same agent without another build or
test run, also checked the retained exits, all 28 JUnit identities, 39 original
inputs, executed fixture inputs, 54 original-copy occurrences, 635 selected
compile/runtime artifact occurrences, 350 runtime JAR occurrences, provenance
and staged bytes. These are verification counts, not additional tests or users.

## Reproduction

Use the recorded checkout and the CI artifact named
`routecontract-coordinated-ci-preparation-5800ed2960aefbf63c01d2ebaf2265278d662494`.
Verify its retained `SHA256SUMS` and receipt against the identities above. With
Java 17, a working local Docker socket and the pinned Gradle ZIP, run:

```sh
python3 scripts/verify-packaged-corpus-consumer.py \
  --repository /path/to/candidate/repository \
  --reviewed-receipt /path/to/candidate/consumer-receipt.json \
  --reviewed-receipt-sha256 9a4d745ff11508a8ab08dd8bced6a7893d8f6e6ff5baab34b3445aea652ba49c \
  --staged-source-revision 5800ed2960aefbf63c01d2ebaf2265278d662494 \
  --java-home /path/to/temurin-17.0.20.1/Contents/Home \
  --gradle-distribution-zip /path/to/gradle-9.7.1-bin.zip \
  --evidence-directory /path/to/new-absent-evidence-directory
```

The full producer commit must be available locally, and the evidence directory
must be outside both the checkout and candidate repository. CI artifacts have
retention limits; this record does not claim permanent artifact availability or
an immutable public 0.2 release. See the [acceptance contract](../packaged-corpus-acceptance.md)
for the exact input and failure requirements.

## Limits

The result covers synchronous, non-batch PreparedStatement workloads and
hook-reported physical JDBC execution attempts. It does not establish transaction
commit, a complete route plan, arbitrary async behavior, latency improvement,
another JDK, offline execution, a standalone CLI run or external adoption.

`humanReview: null`, `fullA23Complete: false` and `publicConsumption: false` remain
unchanged. Other matrices recorded for older candidates keep their original
producer and dependency graph; this run does not requalify those matrices.
