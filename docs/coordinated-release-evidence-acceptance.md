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
  the existing split metadata/signing-bundle contract. The historical installer
  keeps its default validation boundary; split Javadoc validation explicitly uses
  the Java packages in the exact module source inventory. Shared pinned doclet
  and legal-file checks remain active.
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

## CI execution before a release tag

For a literal stable `0.2.x` source version, the existing Java 17 CI job must run
coordinated unsigned preparation after its root `clean check assemble`, twelve
SBOM validations and strict JUnit summary. Run the existing final supply-chain
scanner at exact `GITHUB_SHA`, then stage all three modules from that same clean
checkout and its generated build outputs. The scanner refreshes its existing
twelve SBOM and three POM inputs; it does not repeat the MySQL matrix. The signing
smoke's separate archive with a changed version cannot supply this candidate.
Create an absent private staging parent for the aggregate's existing filesystem
contract in both CI and tag preparation; leave the shared runner temporary
directory permissions unchanged.

Collect and verify the closed candidate with the already pinned Temurin runtime,
then upload it under a distinct CI preparation artifact name. Keep run context
outside the closed candidate inventory and bind it to the candidate manifest
hash. For pull requests, explicitly record the tested merge SHA and the distinct
PR head SHA; neither represents a release tag. Other version families skip these
new preparation steps. Historical CI steps and all publication holds remain.

Focused workflow checks must first fail for missing wiring, then prove stable
version dispatch, exact-source/scan/staging order, successful-verification-only
upload, PR merge/head provenance and unchanged existing jobs. These local checks
are implementation evidence only. Full pinned-Temurin preparation remains
unverified until this CI path actually completes; no signature, publication,
human baseline approval or complete A-25 claim follows from adding the workflow.

## CI summary and split Javadoc corrections — 2026-09-08

The [CI run for PR head `9a15d7f`](https://github.com/ym0506/routecontract/actions/runs/34233812330)
tested merge `0e378fb59558931b33eca2f1afb87d0f9266ef27`. Its retained 24 JUnit
suites contain **174 passing tests**, including all 28 MySQL tests, with no
failures, errors or skips; all 12 official SBOM validations also passed.
The following summary step failed because `ArtifactIsolation552Test` still
expected eight tests after two publication/dependency checks raised its actual
count to ten. All other 23 suite counts matched. The exact-source scan,
coordinated collection and candidate upload were skipped; this run produced no
coordinated candidate or context sidecar.

The correction requires all ten tests. A regression first demonstrated that the
old summary rejected complete ten-test results and accepted incomplete eight-test
results. All nine summary tests then passed. Reprocessing the retained CI XML
with the corrected script produced 24/174/0 failures/0 errors/0 skips locally;
this is a local replay of existing results, not a successful CI rerun.

Separately, a read-only inventory check reproduced rejection of the existing
three split Javadocs by the historical package allowlist. The coordinated path
now derives its permitted HTML package paths and ancestor directories from the
exact module's Java sources. Foreign modules, undeclared nested packages and
non-HTML payloads remain rejected; the historical default boundary and pinned
standard-doclet/legal checks are unchanged. This was not the failed CI step.

**`verified - unit`**, local Python 3.13: 22 coordinated preparation tests, eight
CI wiring tests and nine summary tests passed. The installer suite passed 69
tests and retained its one opt-in real-MySQL/Temurin skip. An earlier installer
run was interrupted while Git waited for an iCloud file; the completed run used
an independent local checkout. These tests use synthetic doclet fixtures and do
not replace successful collection on the pinned release JDK.

```sh
python3 -m unittest discover -s submission/tools/tests -p test_summarize_test_results.py -v
python3 -m unittest discover -s scripts/tests -p test_coordinated_release_evidence.py -v
python3 -m unittest discover -s scripts/tests -p test_coordinated_ci_preparation.py -v
python3 -m unittest discover -s scripts/tests -p test_install_release_assets.py -v
```

The three retained Javadoc inventories pass the corrected package check without
changing their bytes. Full release-doclet validation and coordinated collection
remain pending actual new CI execution. No new stage, packaged-consumer result,
human approval or public 0.2 release is established by these corrections.
