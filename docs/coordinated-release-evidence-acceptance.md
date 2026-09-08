# Coordinated 0.2 release preparation acceptance

Status: preparation implementation with focused unit and local payload evidence;
exact Release-toolchain execution remains pending. The specification preceded
implementation. This adds preparation and inspection for
one coordinated stable `0.2.x` candidate. The existing publication hold remains
active. A preparation receipt never approves a payload, signs it, publishes it,
closes the remaining adapter ADR rows, or approves a baseline.

## Required artifact boundary

Collect exactly fifteen main/sources/Javadoc JAR, POM and Gradle Module Metadata
payloads across `routecontract-core`, `routecontract-shardingsphere-5.5` and
`routecontract-shardingsphere-5.5.2`, in that order, at one version. Preserve their
actual bytes. Bind exact source revision/tree, toolchain, generated metadata,
class/source namespace and service ownership, embedded LICENSE/NOTICE, classifiers,
and all referenced JAR sizes/digests. Missing, mixed, extra, altered, linked,
ambiguous or unsafe inputs must fail. The historical single-artifact installer
and its format-1 receipts retain their current meaning and rejection behavior.

A distinct format-2 unsigned preparation receipt records the coordinate set and
all fifteen payload hashes. It also binds the exact source archive, six-role
JSON/XML SBOM pairs, sanitized exact-revision license/OSV policy evidence, strict
root JUnit summary and release JDK identity. Payload-only validation may inspect
local unsigned artifacts but must label its narrower scope and cannot produce a
complete release-preparation result without the other inputs. A reviewed public
consumer receipt remains a separately reviewed nine-primary-payload shape.

## Required preparation checks

- Source revision is exact and all tracked publication inputs are unchanged;
  the retained source archive equals `git archive` for that revision.
- The release JDK is the already specified Temurin `17.0.20.1+1`, with the
  existing Linux Javadoc module SHA-256. Local Homebrew payload inspection cannot
  satisfy this release-toolchain gate.
- All three exact publication graphs and all four Gradle variants agree with
  the existing split metadata/signing-bundle contract. No signer rewrite or
  mutation of a shared verifier is part of this work.
- Every SBOM and POM is bound to the existing supply-chain policy's exact
  revision/tree, locks, scanner/database identity and result. Reuse its semantic
  verification; merely seeing a successful string or hashing a report is not
  sufficient.
- The strict root test summary is regenerated/compared from the exact expected
  raw suites, and output contains no raw SQL, connection values or private paths.
- Output is a new absent directory with a closed inventory and checksums. A
  second inspection detects substitutions, missing/extra files, source or
  evidence drift. No complete receipt is emitted for an incomplete candidate.

## Workflow behavior and acceptance

The workflow dispatches stable `0.2.x` preparation to the coordinated path and
keeps the historical `0.1.x` path unchanged. It retains the complete unsigned
candidate before the final intentional 0.2 publication failure. Split-aware
local staged consumers consume those retained bytes; they do not use the
historical all-in-one installer or claim anonymous public availability.

First establish failing tests for absent coordinated collection, altered/missing
payloads, incomplete evidence and historical/0.2 dispatch. Then implement the
smallest coherent preparation path and prove the publication hold still fails.
Run focused unit/acceptance checks and actual unsigned reviewed-artifact
inspection when inputs permit. If release JDK, SBOM/OSV or exact-source evidence
is missing, retain a concrete failure; do not replace it with fixture evidence.

Signatures, final human reviews, remaining A01–A29 release rows, annotated-tag/run
identity, Portal actions and post-publication anonymous consumers stay separate.
No new build-tool, JDK, database or user-adoption matrix is introduced here.

## Commands and retained scope

Run from the clean source revision after the existing strict root build and
exact-revision supply-chain scan, using the already generated unsigned aggregate
staging repository and the pinned release JDK:

```sh
python3 scripts/prepare-coordinated-release-evidence.py collect \
  --repository "$UNSIGNED_COORDINATED_REPOSITORY" --source-root "$PWD" \
  --version 0.2.0 --revision "$REVIEWED_REVISION" --java-home "$JAVA_HOME" \
  --output "$PWD/build/central-candidate-evidence"
python3 scripts/prepare-coordinated-release-evidence.py verify \
  --source-root "$PWD" --version 0.2.0 --revision "$REVIEWED_REVISION" \
  --java-home "$JAVA_HOME" --output "$PWD/build/central-candidate-evidence"
```

The output retains the unsigned Maven repository, fifteen-payload format-2
`candidate-payloads.json`, a nine-primary-payload `consumer-receipt.json`, the
source archive and six-role evidence, and a closed `SHA256SUMS`. The generated
consumer receipt is a byte inventory awaiting maintainer review; it does not
turn a computed hash into approval. The candidate document is distinct from the
strict approved schema-2 payload manifest accepted by the signing-bundle tool.

Verification recomputes the existing six-role policy from the source checkout's
retained raw scan and inventory, compares its sanitized result exactly, and
recomputes the strict summary from raw JUnit. Those raw inputs remain outside
the uploaded preparation set. A downloaded candidate without the required
source/raw evidence cannot claim that full revalidation passed. Reinspection
rejects changed inputs, missing/extra output and a receipt relabeled as approved.

For a deliberately narrower local unsigned inspection:

```sh
python3 scripts/prepare-coordinated-release-evidence.py inspect-payloads \
  --repository "$UNSIGNED_COORDINATED_REPOSITORY" --source-root "$SOURCE_CHECKOUT" \
  --version 0.2.0
```

That command validates the fifteen actual payloads, source/classifier ownership,
legal bytes, metadata graph and checksum references, but explicitly reports
`releasePreparationVerified: false`. On 2026-09-08 it passed against the frozen
`4e066942f6e244345fe908970b81446f9e08f64e` unsigned local payloads. Full collection
on the available Homebrew 17.0.15 runtime failed at the pinned Temurin check and
left the requested output absent. No release Javadoc, full release preparation,
new MySQL execution, signature, publication, or external use is claimed from
that narrower inspection. The workflow will run the existing independent staged
Gradle and Maven MySQL consumers against the retained candidate repository and
reinspect it afterward; this new workflow path has not yet executed in public CI.
