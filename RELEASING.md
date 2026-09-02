# Release checklist

This checklist produces reviewable release evidence; it does not publish to a
package repository or create a GitHub Release automatically. Publication must
remain a deliberate maintainer action until repository ownership, publication
credentials and the v0.1 no-signature policy below have been reviewed.

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
5. Run on a clean machine with exact Temurin 17.0.20.1+1 and Docker available. A general local
   Java 17 build remains useful for development but does not guarantee the stable Release
   Javadoc-classifier asset version:

   ```bash
   ./gradlew --no-daemon --no-build-cache clean check validateOfficialCycloneDxSbom \
     :routecontract-shardingsphere-5.5:assemble \
     :routecontract-shardingsphere-5.5:generatePomFileForMavenJavaPublication
   ```

   The opt-in built-asset/MySQL acceptance test is release evidence rather than a generic
   development check. It fails before building unless `ROUTECONTRACT_RELEASE_JAVA_HOME` (or
   `JAVA_HOME`) identifies exact Temurin 17.0.20.1+1:

   ```bash
   ROUTECONTRACT_RELEASE_JAVA_HOME=/absolute/path/to/jdk-17.0.20.1+1 \
   ROUTECONTRACT_RUN_RELEASE_ASSET_MYSQL_TEST=1 \
     python3 -m unittest -v \
       scripts.tests.test_install_release_assets.InstallReleaseAssetsTest.test_real_built_jars_install_and_run_isolated_mysql_consumer
   ```

6. Inspect the main, sources and Javadoc JARs, including the Javadoc classifier's closed
   `legal/`, `script-dir/`, `resources/`, and root static-asset inventory; generated POM; direct library
   SBOM; aggregate repository SBOM; `LICENSE`; `NOTICE`; and third-party
   notices. Recheck Connector/J's FOSS exception, Jakarta Transaction's SPDX
   expression, JNA's embedded libffi license, JTS Core's dual-license metadata,
   the absence of JTS I/O Common, and the selected MySQL platform image's
   package notices. Verify
   that no fixture credentials, raw SQL parameters or private paths are present.
7. Record the source revision, JDK/Gradle/Docker versions, exact command, test
   result, CI URL and SHA-256 checksums. A passing build alone is not evidence
   of transaction commit or a complete ShardingSphere route plan.
8. Refresh the pinned OSV database and rerun the exact-revision policy gate.
   The current policy has zero vulnerability exceptions and the pinned snapshot
   reports zero findings, so any new finding must fail until it is addressed or
   an explicit, evidence-backed policy change is reviewed. A successful scan is
   point-in-time evidence, not a vulnerability-free claim.

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
- resolves x64 Temurin 17.0.20.1+1 with package-signature verification when downloaded, requires
  unique exact release metadata and `java -fullversion`, and pins the Linux
  `jdk.javadoc.jmod` SHA-256 used to generate the classifier;
- after Git-only tag/revision/main binding, asserts that the checkout has no
  tracked, untracked or ignored residue and runs the documented Quick Start
  from an asserted-absent task-specific Gradle user home before any
  project-local Python or Gradle command; the outer script must exit `0` after
  it has verified real-MySQL child exit `0` and the intentional contract-gate
  child exit `1`;
- runs unit and real MySQL integration tests without reusing cached task results;
- generates `test-summary.txt` from the resulting JUnit XML and fails unless
  the exact seven expected suites contain 52 passing, non-skipped tests; the
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
an immutable public Release. For contest packaging, the tested RC tag must share the final stable
tag's exact `MAJOR.MINOR.PATCH` base. A corrected `v0.1.1` therefore cannot reuse
`v0.1.0-rc2` activation, recruitment, result, or cutoff evidence: it requires its own activated
`v0.1.1-rcN` recruitment window and a new stable tag/run/asset set, or a separately reviewed
contract change. Without one of those paths, final packaging remains blocked.

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

## Future Maven Central publication (a separately approved later release)

The immutable GitHub Releases `v0.1.0` and `v0.1.2` remain unchanged and are
not published to Maven Central. This section applies only to a later stable
version selected through a separate release approval. It does not authorize
overwriting, retagging, or describing `0.1.0` or `0.1.2` as a Central artifact,
and it does not plan or authorize another release by itself.

Use the current official [Central publishing guide](https://central.sonatype.org/publish/publish-portal-guide/),
[Portal API documentation](https://central.sonatype.org/publish/publish-portal-api/)
and [GPG requirements](https://central.sonatype.org/publish/requirements/gpg/)
at action time. Portal fields and response shapes can change; this checklist
records required invariants rather than copying an unstable JSON schema.

### Approval-bound candidate

Before any upload, record and independently compare:

- a stable project version strictly greater than `0.1.2`; its annotated `vVERSION` tag
  object OID, raw-object size and SHA-256; its peeled commit and tree; and the
  public `main` commit from which that tag was created;
- the successful release-evidence workflow identity and file SHA-256, run ID,
  `run_attempt` and `head_sha`, plus every evidence artifact ID, digest and flat
  filename allowlist, all bound to that peeled commit; also record the exact
  source checkout and clean-tree result;
- the generated POM coordinates and required project, license, developer and
  SCM metadata; Gradle Module Metadata; main, sources and Javadoc JARs; direct
  and aggregate CycloneDX JSON/XML SBOMs; supply-chain policy result; and the
  exact name, size and SHA-256 of every reviewed file;
- the source and Javadoc JAR contents, first-party package namespace, notices,
  and absence of credentials, private paths, generated local state and
  unrelated artifacts; and
- Central Portal namespace ownership showing `io.github.ym0506` as verified.

Any mismatch creates a new candidate. Do not repair an already uploaded or
published coordinate in place. Later upload, validation and Publish checks bind
to the immutable tag, peeled commit, tree and workflow run; unrelated later
development may advance `main`.

### Signing and local staging

The release signature uses the reviewed protected OpenPGP primary key selected
by its full uppercase fingerprint. Keep the private key and passphrase in a
protected maintainer-controlled GnuPG home; let `gpg-agent` request the
passphrase. Never store private-key material, passphrases or Central
credentials in Git, Gradle properties, shell history, command output, CI logs
or artifacts. Shell tracing must remain disabled. Recording the public primary
fingerprint and verified signature status in the private release receipt is
expected.

Central's current GPG requirements require the signing-capable primary key and
do not accept a signing subkey. Therefore the command below selects the exact
reviewed 40-hex primary fingerprint with `!`. If that official rule changes,
review the new rule before changing the release procedure.

For signed staging, the build also requires the options file to be an exact
single-link mode-0600 file in the private staging parent containing only the two
lines shown below. Its identity and the SHA-384 policy bytes are rechecked before
every publication signature and before final exposure.

CI may generate an ephemeral throwaway key only to test signing configuration.
That key and its signatures are test data, are never uploaded or retained as
artifacts, and are not release evidence.

From a fresh detached checkout of the reviewed tag, use a new private staging
parent and the checked-in Wrapper. The supplied repository path and its entire
existing parent chain must be canonical, normalized and free of symbolic links:

```bash
(
set -e
release_version=REPLACE_WITH_SEPARATELY_APPROVED_LATER_STABLE_VERSION
staging_parent=/absolute/path/to/new-private-central-staging
reviewed_primary_fingerprint=REPLACE_WITH_40_UPPERCASE_HEX
test ! -e "${staging_parent}"
mkdir -m 700 "${staging_parent}"
gpg_options="${staging_parent}/gpg-options"
printf '%s\n' \
  'no-auto-key-retrieve' \
  'digest-algo SHA384' > "${gpg_options}"
chmod 600 "${gpg_options}"
GNUPGHOME=/absolute/path/to/protected-gnupg-home ./gradlew \
  --no-daemon --no-build-cache --no-configuration-cache \
  :publishRouteContractCentralStaging \
  -ProutecontractCentralStagingDirectory="${staging_parent}/repository" \
  -ProutecontractCentralSigning=true \
  -Psigning.gnupg.executable=gpg \
  -Psigning.gnupg.optionsFile="${gpg_options}" \
  -Psigning.gnupg.keyName="${reviewed_primary_fingerprint}!"
)
```

The aggregate task is mandatory; invoking any per-project publication task
directly fails before staging begins. It writes only to the absent hidden
`.repository.routecontract-work` sibling, verifies the complete core, exact
5.5.3 adapter, and exact 5.5.2 adapter payload/signature sets, and uses a
descriptor-anchored, same-parent, no-replace atomic rename to expose the final
`repository` path. Finalization requires `/usr/bin/python3` and the platform's
descriptor-anchored no-replace rename primitive; an unsupported or unavailable
primitive fails closed as a HOLD. If any publication, verification, move or
post-move check fails or is interrupted,
preserve the observed work and final paths as a HOLD. Do not retry with the same
path and do not automatically delete, rename or complete either path; record
their read-only state first and prepare a new candidate only after explicit
reconciliation.

Before upload, recheck the official list of Central-supported keyservers and
distribute the exact public primary key to one currently supported server. In a
fresh empty private `GNUPGHOME`, receive/import it from that same server using
only read-only retrieval, then require the exact reviewed uppercase 40-hex
primary fingerprint and a signing-capable, current, nonexpired and nonrevoked
primary key. Stop if any condition or retrieval fails.

Confirm all three staged coordinates use `${release_version}`. Reject symlinks,
special files, nested surprises, unexpected names and files outside the
coordinated `routecontract-core`, exact 5.5.3 adapter, and exact 5.5.2 adapter
coordinates. Recompute every checksum over its named staged file and compare
the result, then use only the fresh keyring above to verify every detached
signature against the reviewed primary fingerprint. Compare all three POMs,
all three Gradle Module Metadata documents and all nine JAR bytes with the
approval-bound evidence. Gradle artifact-level `maven-metadata.xml` files are
local bookkeeping and are not part of the version upload bundle.

The direct and aggregate SBOMs and supply-chain policy result remain
evidence-only files: bind their exact names, sizes and bytes to the private
candidate receipt, but exclude them from the Central bundle. If a future
publication design intentionally adds any of them as Maven artifacts, review
that change first and include them in the upload allowlist and public readback.

### Credential-free deterministic upload bundle

After the signed staging tree and public-key-only verification home pass the
checks above, use `scripts/prepare-central-upload-bundle.py`. The script has no
HTTP client, Portal credential input, signing operation or publication mode. It
only reads one coordinated local Gradle Maven staging repository, a separately
reviewed payload manifest and a public-key-only GnuPG home, then creates a
deterministic ZIP plus a path-free receipt in a new absent output directory.
All file and directory arguments must be absolute normalized canonical paths;
the tool rejects a symlink in any argument's existing path.
Manifest, staging, tool, bundle, receipt and created output files must each be
regular files with exactly one hard link. Repository traversal stays anchored
to opened directories with `O_NOFOLLOW` and compares directory identities
before and after every read. The output directory is mode `0700`; its two files
are mode `0600`. A write, readback or descriptor-close failure closes every
descriptor it can and fails without any failure-time rename, unlink or directory
removal. The new output directory may therefore remain partial at the requested
path and must be inspected and removed manually before a fresh attempt. This
conservative rule prevents cleanup races from deleting or replacing unrelated
objects.
Secret-material names in the public GnuPG home fail even when they are symlink
aliases or dangling links.
The tool exports the exact verified public key into a tool-created private,
public-only temporary GnuPG home and uses that snapshot for every signature
check, so signature verification does not reopen the caller's keyring.

The reviewed payload manifest is a strict canonical JSON document with schema
version `2`. Its `coordinateSet` contains only the exact
`io.github.ym0506.routecontract` group, the exact ordered artifact IDs
`routecontract-core`, `routecontract-shardingsphere-5.5`, and
`routecontract-shardingsphere-5.5.2`, and one shared stable `0.2.x` SemVer. Its
`payloads` array contains exactly fifteen records ordered first by that artifact
order and then lexicographically by filename. Each record has only
`artifactId`, `name`, `size` and `sha256`. Every artifact contributes its POM,
Gradle Module Metadata, main JAR, sources JAR and Javadoc JAR. The manifest must
be produced and approved as part of the approval-bound candidate; the bundle
tool never creates or edits it and does not turn computed staging hashes into
approval. The release-evidence design must retain and review the exact Gradle
Module Metadata bytes; the current `v0.1.2` release evidence cannot be
substituted.

Before checking signatures, the tool verifies the dependency boundary in both
metadata formats. Core must contain no RouteContract or ShardingSphere
dependency. Each adapter must depend directly on the same-version core and use
the exact runtime anchor set for its ShardingSphere line. The 5.5.3 adapter
requires the 5.5.3 executor, SPI and database-connector-core anchors; the 5.5.2
adapter requires the 5.5.2 executor, SPI and infra-database-core anchors. Their
POM direct/managed roles and Module Metadata dependency/strict-constraint roles
must match exactly. Gradle `apiElements` and
`runtimeElements` must publish the reviewed core-owner or exclusive hook-slot
capability; the 5.5.2 adapter must also retain its legacy 5.5 artifact
capability. Module Metadata must bind each of its four variants to the staged
main, sources or Javadoc JAR by exact size and four digests. A missing artifact,
mixed version, extra edge, wrong ShardingSphere version, capability change or
metadata/JAR mismatch fails closed.

The upload ZIP contains exactly 90 regular files under the three Maven version
paths:

- the fifteen reviewed payloads;
- one detached ASCII-armored primary-key signature for each payload; and
- `.md5`, `.sha1`, `.sha256` and `.sha512` sidecars for each payload.

The local Gradle staging tree also contains four checksum sidecars for each
`.asc` file and one artifact-level `maven-metadata.xml` plus four checksums for
each coordinate. The tool requires that exact local-only inventory, verifies
every checksum and detached signature, and excludes those 75 files from the
upload ZIP. Signature sidecars do not need checksums, and artifact-level
metadata is local publication bookkeeping rather than version payload. Any
other file, directory, symlink or special file fails closed.

The ZIP uses lexicographic entry order, stored entries, the fixed ZIP epoch,
regular mode `0644`, no directory entries, no archive comment and no extra
fields. For identical signed staging bytes and reviewed manifest, its bytes and
SHA-256 are identical. The receipt is canonical sorted JSON and binds the exact
manifest bytes, tool bytes, coordinate set, primary fingerprint, ZIP name, byte
count, SHA-256 and every entry name, size and SHA-256. It explicitly records
that credentials, upload, validation, Publish, public readback and availability
are outside its scope.

Use a fresh GnuPG home containing only the independently retrieved public key.
The tool rejects secret-key material and verifies exactly one SHA-384 detached
signature per payload from the expected 40-character uppercase primary
fingerprint. It never retrieves a key or follows a network path.

```bash
python3 -I scripts/prepare-central-upload-bundle.py build \
  --repository /absolute/path/to/new-private-central-staging/repository \
  --reviewed-payload-manifest /absolute/path/to/reviewed-payloads.json \
  --public-gpg-home /absolute/path/to/fresh-public-only-gnupg-home \
  --expected-primary-fingerprint REPLACE_WITH_40_UPPERCASE_HEX \
  --output-directory /absolute/path/to/new-private-central-bundle

python3 -I scripts/prepare-central-upload-bundle.py verify \
  --repository /absolute/path/to/new-private-central-staging/repository \
  --bundle /absolute/path/to/new-private-central-bundle/routecontract-VERSION-central-upload.zip \
  --receipt /absolute/path/to/new-private-central-bundle/routecontract-VERSION-central-upload-receipt.json \
  --reviewed-payload-manifest /absolute/path/to/reviewed-payloads.json \
  --public-gpg-home /absolute/path/to/fresh-public-only-gnupg-home \
  --expected-primary-fingerprint REPLACE_WITH_40_UPPERCASE_HEX
```

The receipt is local bundle evidence only. Independently compare its reviewed
manifest binding, tag, commit, tree, workflow run, release evidence and public
key facts with the approval-bound candidate before recording upload intent.
Never pass the bundle to a network client merely because this verifier succeeds.
The CLI success marker uses the version and both SHA-256 values returned by the
same completed build or verification operation; it never reopens those paths to
construct a later attestation.

### Portal upload, validation and publication

1. Create one exact upload bundle containing only the reviewed payloads for all
   three same-version Maven coordinates, each payload's detached signature and
   required payload checksum sidecars. Record its SHA-256 and filename allowlist
   in a private receipt that contains no credential.
2. Upload once as `USER_MANAGED`, never automatic publication. Record an
   upload-intent entry before the request and then the returned deployment ID
   and observed result without editing earlier receipt entries.
3. Wait for Portal validation. A maintainer must inspect the exact deployment
   ID, namespace, version, component files, signatures and reported errors,
   and compare downloadable candidate bytes with the local reviewed bundle.
4. Record publish intent, then issue one explicit Publish action for that exact
   validated deployment. Do not use a retrying client for upload or Publish.
5. If an upload or Publish times out, loses its response, or otherwise has an
   ambiguous result, do not repeat the mutation. Reconcile only with read-only
   status, deployment listing and byte-download checks. Record the observed
   state; if the outcome cannot be proved, stop and make no availability
   claim.

Central credentials must never be stored or logged; supply them only as
action-time inputs and do not print them. Authenticated HTTP requests must use
the exact `central.sonatype.com` HTTPS origin and must not follow redirects.
Remove the credential from the environment immediately after the action.

### Public readback and availability claim

After Portal reports publication, wait for all three coordinates to appear
through the official public Maven Central repository. For each coordinate,
fetch the exact POM, Gradle metadata, main/sources/Javadoc JARs and other
published version files without authentication and compare them byte-for-byte
with the reviewed staged payloads. A Portal success response alone is not
public-availability evidence.

The post-publication `0.2.x` fresh-consumer gate is currently **not
implemented**. This is a release-blocking gap: the existing standalone consumer
belongs to the pre-split `0.1.x` artifact and must not be used as evidence for
the three-coordinate publication. Before any `0.2.x` Central publication, add
and review an independent clean-cache consumer that resolves
`routecontract-core` plus exactly one exact-version adapter at the same
candidate version, enforces the whole-graph adapter exclusivity policy, and
runs its compile and representative candidate check using only the public
unauthenticated Maven Central endpoint. It must also prove that selecting both
adapters, or the wrong adapter for the ShardingSphere runtime, fails closed.

That consumer must not use `mavenLocal()`, a file repository, a project
dependency, a composite build, an authenticated deployment endpoint or an old
cache. Do not claim Maven Central availability until both unauthenticated byte
readback and the still-to-be-implemented split-artifact fresh-consumer gate
pass.

Published Central coordinates are immutable. If any published byte, metadata,
signature or verification result is wrong, preserve the evidence, stop using
that version, fix the cause and release a higher stable version with a new
tag, tree, CI run, signatures and deployment. Never delete and reuse the
version.

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
  owner re-reviewed the evidence on 2026-08-24; the record remains exactly one
  `test-container`-scoped `manual-review-required` package-level review with no
  image-wide license conclusion and expires on 2026-12-05. Re-review
  immediately if the MySQL OCI digest, selected platform, embedded
  LICENSE/INFO_SRC evidence, or test-container use boundary changes; otherwise
  resolve, renew with new evidence, or remove the MySQL OCI package-level
  license review before the 2026-12-05 expiry.
- The test/example graph keeps ShardingSphere-JDBC 5.5.3, strictly constrains
  Calcite Core and linq4j to 1.42.0, excludes and forbids JTS I/O Common, and
  retains JTS Core 1.19.0. Recheck all four conditions from the final lock and
  SBOM instead of treating a successful earlier resolution as durable.
- A supply-chain policy pass may contain exactly one unresolved license review:
  the MySQL OCI component above. It is confined to the example/test graph and
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
