# Release checklist

This checklist produces reviewable release evidence; it does not publish to a
package repository or create a GitHub Release automatically. Publication must
remain a deliberate maintainer action until repository ownership, signing and
credentials have been verified.

## Prepare

1. Work from a clean revision on `main` and close or document every release
   blocker.
2. Set and verify the intended non-SNAPSHOT `MAJOR.MINOR.PATCH` or strict
   `MAJOR.MINOR.PATCH-rcN` version consistently in the root build, changelog,
   compatibility statement, user coordinates, protocol and limitations.
3. Reconcile `THIRD_PARTY.md` with `gradle.properties`, the module build files,
   and the generated CycloneDX SBOM.
4. Confirm the checked-in Gradle Wrapper JAR and distribution checksums against
   Gradle's official checksum page.
5. Run on a clean machine with JDK 17 and Docker available:

   ```bash
   ./gradlew --no-daemon --no-build-cache clean check validateOfficialCycloneDxSbom \
     :routecontract-shardingsphere-5.5:assemble \
     :routecontract-shardingsphere-5.5:generatePomFileForMavenJavaPublication
   ```

6. Inspect the main, sources and Javadoc JARs; generated POM; direct library
   SBOM; aggregate repository SBOM; `LICENSE`; `NOTICE`; and third-party
   notices. Recheck Connector/J's FOSS exception, Jakarta Transaction's SPDX
   expression, JNA's embedded libffi license, JTS Core's dual-license metadata,
   JTS I/O Common's embedded Apache Mahout code and unresolved NOTICE
   redistribution treatment, and the selected MySQL platform image's package
   notices. Verify
   that no fixture credentials, raw SQL parameters or private paths are present.
7. Record the source revision, JDK/Gradle/Docker versions, exact command, test
   result, CI URL and SHA-256 checksums. A passing build alone is not evidence
   of transaction commit or a complete ShardingSphere route plan.
8. Refresh the pinned OSV database and rerun the exact-revision policy gate.
   Review the three current test/example-graph advisories and remove, upgrade,
   or renew every exception before its expiry; test-only reachability does not
   make a finding harmless.

## Tag and collect evidence

Create an annotated tag matching the Gradle project version, including the
leading `v` (for example, project version `0.1.0-rc1` uses tag `v0.1.0-rc1`,
and `0.1.0` uses `v0.1.0`). The release installer accepts only these stable or
strict `-rcN` forms and rejects snapshots. The planned final contest package
uses the immutable stable `v0.1.0` release. If that release fails a required
post-publication verification check, it remains immutable; final evidence must
instead name a corrected later stable patch with its own tag, revision, assets
and evidence run. Pushing a matching tag runs the read-only `Release evidence`
workflow. The workflow:

- accepts only a tag-push event, validates the Wrapper and annotated
  tag/version match, and requires the peeled tag commit to equal both the
  workflow revision and the current public `origin/main` head;
- runs unit and real MySQL integration tests without reusing cached task results;
- generates `test-summary.txt` from the resulting JUnit XML and fails unless
  the exact seven expected suites contain 50 passing, non-skipped tests; the
  fixed summary records the Git revision and per-suite counts but deliberately
  omits test names, timings, hostnames, paths, ports, SQL and captured output;
- builds reproducible-order JARs and the generated Maven POM;
- generates direct and aggregate CycloneDX JSON/XML SBOMs and fails unless
  every first-party component declares Apache-2.0, Connector/J includes its
  Universal FOSS Exception and MySQL example BOMs contain the digest-pinned,
  test-only MySQL container component in both formats, then validates all six
  finalized documents with the checksum-pinned official CycloneDX CLI 0.33.1;
- runs the checksum-pinned offline OSV policy gate from the exact clean tag,
  retains only its sanitized `supply-chain-evidence.json` summary and never
  stages or uploads the raw OSV report;
- creates a revision-bound source archive with one `routecontract-VERSION/`
  root; this archive is release evidence and a GitHub Release asset, not a
  separate contest-upload file;
- validates that source archive's bounded and unambiguous ZIP structure, exact
  versioned root, required project/hook sources, every Java path/package pair
  under conventional `src/main/java` and `src/test/java` roots, canonical
  `ym0506` provider namespace, and absence of paths matching the explicit
  private/generated/credential-like denylist before installing any binary
  artifact;
- stages the exact public Release payload set and creates `SHA256SUMS` over
  those payloads only;
- installs that checksummed set into an explicit empty file Maven repository,
  then verifies a standalone real-MySQL consumer against the installed final
  JAR/POM rather than `publishToMavenLocal` or a Gradle project dependency;
- records runner architecture and the resolved MySQL image ID, architecture
  and repository digests;
- uploads the public payloads and checksum together with workflow-only
  environment, MySQL-image and final-asset-consumer logs plus the example
  JSON/XML SBOM pair as one workflow artifact. The example pair is not a
  public Release payload and is not listed in `SHA256SUMS`.

Before creating a public tag, verify through the repository API that release
immutability is enabled; an HTTP success alone is insufficient, and the parsed
response must contain `enabled: true`. Record `enforced_by_owner` too: `false`
does not negate the enabled setting, but means owner-level enforcement is not
protecting the future-release setting. Immediately before the tag push, record
the current public `main`; do not advance `main` until the workflow's identity
step has compared it to the peeled tag commit. After the annotated tag's exact
revision has a green release-evidence run, re-read `main`, the peeled tag commit
and the run `head_sha`, then download and inspect that run's artifact.

Create a **draft** GitHub Release with `--verify-tag`. For an `-rcN` tag, mark
that draft as a prerelease. While it is still a draft, attach an explicit list
of exactly these twelve assets: the checksummed source archive,
main/sources/Javadoc JARs, generated POM, direct and aggregate JSON/XML SBOMs,
`supply-chain-evidence.json`, `test-summary.txt`, and `SHA256SUMS`. Do not use a
broad filesystem glob. Before publication, verify all of the following against
the tagged revision and the release-evidence run:

- the annotated tag peels to the intended full commit and the run uses that
  same `head_sha`;
- the Release is still `draft: true`, has the intended prerelease flag, and
  exposes exactly the twelve expected asset names, each fully uploaded;
- every one of the eleven payload hashes matches `SHA256SUMS`, and the separately
  recorded SHA-256 of `SHA256SUMS` itself matches;
- the source archive, SBOMs, test summary, POM/JAR identity, and standalone
  release-asset consumer pass their documented verification gates.

Only after every draft check passes may the draft be published. Re-read the
repository immutable-releases API immediately before publication and again
require `enabled: true`; the earlier tag-time result is not a permanent setting
lock. Before running any GitHub CLI attestation or release-verification command,
run the repository's shared local-only preflight:

```bash
python3 scripts/gh_cli_release_safety.py
```

It fails closed unless the installed stable GitHub CLI is at least `2.93.0`.
Versions through `2.92.0` are affected by
[GHSA-8xvp-7hj6-mcj9](https://github.com/cli/cli/security/advisories/GHSA-8xvp-7hj6-mcj9):
the affected `gh attestation`, `gh release verify`, and
`gh release verify-asset` commands could send authentication tokens to hosts
that should not receive them. Do not run those commands on an affected or
unparseable version. Upgrade through an official GitHub CLI distribution. If
an affected command was already run or the history is uncertain, stop the
release; the repository owner must revoke the authentication credential used
by GitHub CLI, upgrade `gh`, authenticate again with a replacement credential,
and review the personal security log plus relevant organization or enterprise
audit logs. These credential and account-review actions are owner attestations,
not steps that this repository automates. Implementation is tracked in
[#21](https://github.com/ym0506/routecontract/issues/21).

After the preflight passes, publish the verified draft. Immediately after
publication, require the Release API to report `immutable: true`, run
`gh release verify`, and run `gh release verify-asset` successfully for each of
the twelve downloaded assets. If an RC prepublication or postpublication check
fails, stop and create a new `-rcN` tag after fixing the cause. If an immutable
stable release fails a postpublication check, stop using it as final evidence,
fix the cause, create a new stable patch version and update the final manifest
and documentation to that corrected release. Never replace an asset or retag
an immutable public Release.

For an RC only, publication still does not activate independent recruitment. Copy
`docs/evidence/independent-rc-activation.example.json` to the exact versioned path documented in
the protocol. Replace every occurrence of `[[STRICT_RC_TAG]]`, `[[RC_VERSION_WITHOUT_V]]`, and
`[[VERSION_DERIVED_ISSUE_FORM_FILENAME]]` consistently. The last value must be derived from the
strict tag suffix: `v0.1.0-rc1` uses `independent-rc1-install.yml`, `v0.1.0-rc2` uses
`independent-rc2-install.yml`, and no generic form name is accepted. Replace every other string
`[[...]]` field with the complete observed value; in particular, the artifact-digest field consumes
GitHub's complete `sha256:` value. Replace the two integer `0` sentinels at
`releaseEvidence.artifactId` and `releaseEvidence.runId` with positive, unquoted JSON integers, and
set `releaseImmutability.enforcedByOwner` to the observed unquoted JSON boolean. Confirm the record's
`issueFormFilename`, commit-pinned `issueFormPermalink`, and interactive `issueFormUrl` all use that
same derived filename. Do not prewrite a form containing anticipated future-RC coordinates or
outcomes: the future RC candidate must add and review its derived form before its annotated tag.
The activation-record commit must be the direct child of the annotated tag commit, add only that
one ordinary JSON file, and be the unchanged public `main` head while validation and recruitment
occur. Land that record through one pull request into `main` using squash so the resulting
single-parent commit preserves this shape; the activation validator and final package gate bind
GitHub's server-side
`merged_at` for that exact commit before recruitment and cutoff. The gate verifies that the
repository is public at activation validation time, but GitHub's current API cannot reconstruct
historical visibility or branch protection at `merged_at`; treat that narrower history as an
owner-reviewed boundary. A direct push, ordinary two-parent merge, unrelated-branch association or
post-cutoff merge is not activation evidence. The active
derived version-specific form must already be an ordinary non-executable blob in
the tag. The generic validator binds only the active form; preservation of earlier version-specific
forms is a separate reviewed tag-history and owner gate. Before a future RC tag, retain each reviewed
earlier form, add and review the new derived form, and add a version-line-specific preservation
check. Commit the record without changing tagged code or forms, then run the fail-closed validator
from a clean checkout at that exact record commit with all twelve downloaded Release assets:

```bash
python3 scripts/validate-rc-activation-record.py \
  --record docs/evidence/independent-rc-activation-v0.1.0-rc2.json \
  --release-assets-dir /absolute/path/to/downloaded-release-assets
```

The validator must verify the single-file direct-child record commit and public `main`, strict RC
tag/version, local and remote annotated tag identity, public
repository/commit/run/artifact/immutable-prerelease metadata, exact assets and checksums, safe
GitHub CLI version, Release attestation and every asset attestation. Only its fixed
`ACTIVATION_RECORD_PERMALINK` and complete `ROUTECONTRACT_RC_ACTIVATION_VERIFIED` marker may
activate recruitment. A template, uncommitted record,
missing tag, draft or mutable Release, failed run, different revision, asset mismatch or unverifiable
attestation remains NO-GO.

The environment record, resolved MySQL image record, standalone-consumer log
and example JSON/XML SBOM pair remain only in the revision-bound workflow
artifact. The test summary and sanitized supply-chain summary are present in
both places; `SHA256SUMS` declares exactly the eleven public payloads (not
itself) and never the five workflow-only files. The gate checks the public checksum set separately,
then binds the entire public-plus-private evidence directory through the Actions artifact ID/digest
and exact flat-file allowlist. The validator does not write extracted members to disk: it streams
each exact member, verifies its declared/observed size and digest, and compares the twelve public
member bytes with separately downloaded Release assets. The resulting workflow artifact contains exactly
17 flat files: eleven public payloads, `SHA256SUMS`, and five workflow-only
files. The package verifier counts 16 payload/evidence files after excluding
`SHA256SUMS`. The intended immutable final `v0.1.0` Release,
or a corrected later stable patch selected by the final manifest, must use a
new stable tag/revision/evidence run with `prerelease=false`; never retag or
promote RC assets as if they were the final stable evidence.

The v0.1 packaging gate requires no signature assets because no signing
workflow or key-management policy is implemented. Add signing only in a future
release with an explicit design and verification path. Do not imply SLSA
provenance or reproducible builds unless those properties have been separately
implemented and verified.

## Known supply-chain boundaries

- Maven and Gradle artifacts are resolved over HTTPS, the Wrapper distribution
  is SHA-256 pinned, and checked-in dependency checksums must be reviewed when
  dependencies change. Checksums establish artifact integrity, not publisher
  identity or vulnerability status.
- The MySQL Testcontainers fixture pins the verified multi-architecture digest
  for `mysql:8.4.11`. Release evidence must also record the resolved platform
  image ID and runner architecture; a multi-architecture tag digest alone does
  not make the entire environment byte-for-byte reproducible. The image also
  contains an Oracle Linux base, MySQL Shell and other packages, so its SBOM
  uses an unresolved-review property plus documentation external reference,
  not an image-wide GPL-only conclusion or a fabricated license name. The
  owner must resolve, renew with new evidence or remove this review before its
  2026-08-27 expiry.
- JTS I/O Common 1.19.0 has a concluded compound SPDX expression, but its
  Mahout-derived Apache-2.0 source references an ASF `NOTICE` missing from the
  Central artifacts and tagged JTS tree. The exact component remains a
  time-bounded manual review because JTS's redistribution notice treatment is
  unconfirmed even though the originating Mahout 0.8 archive and notice are
  pinned. The owner must resolve and document the treatment, renew with new
  evidence or remove the record before its 2026-08-27 expiry.
- A supply-chain policy pass may contain exactly two unresolved license reviews
  because MySQL and JTS I/O Common are confined to the example/test graph and
  absent from the published module/runtime closure. Stable release and
  submission materials must report that count and must not call it completed
  legal review.
- Dependabot proposes updates; CI and human review still decide whether an
  update preserves compatibility and the project's evidence claims.
- The checksum-pinned offline OSV policy is a point-in-time database and policy
  check, not a guarantee of zero vulnerabilities or legal suitability. The raw
  OSV JSON is never staged or uploaded. Only the sanitized summary is
  checksummed; the package gate binds its revision/tree, scanner and database
  lock, policy, aggregate/direct SBOMs, POM and dependency lock back to the
  exact final source and public assets. Manual license/NOTICE review remains
  required.
- The release installer proves the downloaded source ZIP's checksum, bounded
  structure, required paths, Java packages and provider namespace. It does not
  by itself prove Git-tree identity; the final submission packaging gate
  recreates `git archive` from the final commit and compares tracked paths,
  content and executable permissions before accepting it.
- The source-path denylist is not a general secret or content scanner. It
  rejects the declared private/build/environment/key-like path patterns; the
  final Git-tree comparison and maintainer review remain required.
