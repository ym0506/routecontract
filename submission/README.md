# Contest report draft

This directory keeps the Korean content and a deterministic builder for the
official 2026 OSS Developer Contest result-report form.

The official template is intentionally retained outside this repository.
Create the version-pinned report-builder environment first (Python 3.10+):

```bash
python3 -m venv submission/private/report-builder-venv
submission/private/report-builder-venv/bin/python -m pip install \
  --only-binary=:all: --no-deps \
  --requirement submission/report-builder-requirements.txt
```

`--no-deps` is intentional: the requirements file pins the complete runtime
closure, including python-docx's `typing_extensions` dependency and the
`certifi` CA bundle used by the final public-evidence HTTPS checks. Build the
draft with that interpreter:

```bash
submission/private/report-builder-venv/bin/python \
  submission/tools/build_official_report.py \
  --template /absolute/path/to/official-result-report-template.docx \
  --content submission/report-content.ko.json \
  --assets-dir submission/assets \
  --output submission/draft/routecontract-result-report-draft.docx
```

The builder verifies the organizer template SHA-256 before changing a working
copy. It deletes the writing-guide page and the inapplicable runtime-AI
attachment, validates and inserts both 1200x675 PNG evidence figures, fills the
official body/SBOM tables, and preserves the two original page sections and
table geometry. The official supplemental guide caps this prioritized SBOM
summary at ten rows, so the builder accepts 1–10 and the checked-in content
uses exactly ten. Full declared dependencies remain in `THIRD_PARTY.md` and
the generated CycloneDX SBOM. Report-only Python tooling is pinned separately
and is not added to the official top-ten summary. `--assets-dir` is optional
when `assets/` is beside the content JSON.

`[[...]]` values are deliberate submission gates, not claims. Replace each one
with the exact application/public evidence value, then require the final gate:

```bash
submission/private/report-builder-venv/bin/python \
  submission/tools/build_official_report.py \
  --template /absolute/path/to/official-result-report-template.docx \
  --content submission/report-content.ko.json \
  --output submission/draft/routecontract-result-report-final.docx \
  --strict-final
```

After every content change, render every DOCX page and inspect it. Confirm that
the result-report body is at most five pages; Attachment 1 is not part of that
body limit and may occupy one or more trailing pages. Also export the final
DOCX to PDF with the same layout.

## Final submission package

The organizer's 2026 submission notice is the packaging authority:

- the upload ZIP contains the original report (`.docx`) and its PDF export;
- the notice requires a duplicate-benefit confirmation when it applies, but
  this gate currently refuses `status=required`: the organizer's exact form is
  retained outside tracked source, while its title, identity fields,
  placeholders and ZIP path are not yet implemented and validated here;
- source code is represented by exactly one public repository URL in the
  report;
- the demonstration is represented by a public YouTube URL in the report and
  must be no longer than 180 seconds. This project's final gate also requires
  a local video at least 1920x1080 with at least one audio stream, and a
  public, non-live, age-unrestricted YouTube upload with a downloadable 1080p
  or higher video format;
- Attachment 1 SBOM stays inside the report;
- Attachment 2 is removed because RouteContract has no runtime AI model or AI
  API path; development-time ChatGPT/Codex use remains disclosed in the main
  report;
- source archives, machine CycloneDX files, checksums and video files are
  release/internal verification evidence and must not be added to the upload
  ZIP.

`package_submission.py` implements those rules as a fail-closed final gate. It
rebuilds the DOCX with `build_official_report.py --strict-final`, checks the PDF
content and page boundary, checks the local video's duration, default playable
motion-stream dimensions, audio-stream presence, and narrow privacy-sensitive
format/stream/chapter/program metadata denylist with `ffprobe`, verifies the
exact Git revision/tag/public repository/green release-evidence run/GitHub
Release, verifies the release artifact checksums and all three staged SBOM
pairs, and emits
an exact two-file ZIP by default. It derives the DOCX, PDF and ZIP names from
the private manifest as
`2026 오픈소스 개발자대회 결과보고서_접수번호(팀명).{docx,pdf,zip}`;
the old fixed English report and ZIP filenames are rejected.

Before the final run, install the pinned report-builder environment above and
confirm these host tools: Poppler's `pdfinfo`, `pdfdetach`, `pdftotext`, `pdftohtml`, and
`pdftoppm`; LibreOffice Writer (`soffice`) in the same version used to export
the supplied PDF; an absolute regular `FONTCONFIG_FILE` naming the exact font
configuration used for both exports and matching the reviewed SHA-256
`1aad4c0015115d649ca8d3be015141539fd5f037445408a8ee14a0306af6c5d1`;
`ffprobe` for the local video; `yt-dlp --check-all-formats` for public
availability, non-live and age-unrestricted status, duration, and downloadable
1080p format evidence (the verifier checks all reported formats first);
and GitHub CLI 2.93.0 or newer with
`gh release verify` and `gh release verify-asset`. The advisory also covers
`gh attestation` commands. Versions through 2.92.0 are refused before any
affected verification command because they are affected by
[GHSA-8xvp-7hj6-mcj9](https://github.com/cli/cli/security/advisories/GHSA-8xvp-7hj6-mcj9).
A missing, malformed-version, or outdated verifier is a hard failure, not a
skipped check. Upgrade from an official GitHub CLI distribution before
continuing. Repository remediation is tracked in
[issue #21](https://github.com/ym0506/routecontract/issues/21). If an affected
command may already have run, stop and follow the advisory's owner-only token
remediation and log-review guidance; never paste authentication or audit details
into public evidence. If duplicate-benefit status is required, obtain and
retain the exact organizer form and implement its title/identity/placeholder
validation before enabling that path; do not substitute an arbitrary document.

The video gate does not require a particular codec and does not grade narration
loudness, clipping, or visual readability. The owner must still watch and listen
to the checksummed local file and the logged-out public 1080p playback from
start to finish before setting `final_video_watchthrough_completed=true`.
The `yt-dlp` result is downloadable-format inventory evidence; the gate does not
download the entire public video or replace that owner playback review.

The report gate re-exports the generated strict DOCX twice with independent
LibreOffice profiles and the same `FONTCONFIG_FILE`, requires those canonical
exports to have identical rasters, then rasterizes the supplied PDF at 144 DPI
with the same Poppler command and requires exact page-by-page PNG bytes. Text,
row-association, page geometry, metadata and
privacy checks remain additional gates; a hidden text layer under a white or
partial overlay cannot substitute for the visible report.

Do not put personal final values in the public content template. Copy the
templates to ignored paths first:

```bash
mkdir -p submission/private
cp submission/report-content.ko.json \
  submission/private/report-content.final.ko.json
cp submission/package-manifest.example.json \
  submission/private/package-manifest.final.json
```

Replace every `[[...]]` gate in those private copies, export the PDF from the
strictly generated DOCX, and set every participant attestation to `true` only
after checking it. In particular,
`report_free_text_contains_no_external_evidence_claims` is a human-review gate:
the participant confirms that development hardware, public-link prose and owner
voice do not add an external-result, adoption or stable-validation claim outside
the generated `외부 검증` row. The tool does not pretend to classify arbitrary
natural-language paraphrases. The final tag must be an annotated, stable `vMAJOR.MINOR.PATCH`
tag and its GitHub Release must be public, non-draft, non-prerelease and
immutable. The selected Actions evidence must be a successful push run for that
exact tag and revision; the gate cryptographically verifies the Release and
every one of its attached public assets with GitHub's release attestations.

Do not replace the `외부 검증` report sentence manually. Fill the structured
`external_evidence` object instead; the strict builder and package gate generate
that sentence from exactly one enabled branch:

- `rc_only`: `tested_tag` is one exact `-rcN` tag and the generated text states
  that the single result is neither final-stable validation nor adoption and
  that final stable external validation was not obtained before the cutoff.
  Supply its immutable activation-record permalink and the Issue #9 recruitment
  comment permalink;
- `zero`: `tested_tag` is one exact `-rcN` tag, the counted-result total is integer
  `0`, and `result_issue_url` is JSON `null`. Supply the same two RC/recruitment
  evidence types instead of implying that recruitment happened from the protocol
  URL alone.

`final_stable` is deliberately unavailable in this candidate. The reviewed
participant form and protocol are RC-specific and contain statements that
cannot truthfully serve as final-stable evidence. A future change must add and
review a distinct stable form/protocol before re-enabling that branch; the
package gate fails closed meanwhile.

Both enabled branches retain the fixed public Issue #9 protocol URL and an exact UTC
cutoff no later than the package validation instant; an RC tag must share the
final stable tag's version. For RC branches, the activation permalink is the
full-commit schema-v2 JSON produced by the one-file direct-child workflow. The
record must be the current `main` of the repository that the package gate verifies as public, and
must have reached it through one squash pull request. The gate binds that PR's server `merged_at`
strictly after the RC prerequisites and strictly before the recruitment comment and cutoff. Commit
author/committer dates alone are not accepted as publication time. GitHub's current API does not
reconstruct historical repository visibility or branch protection at `merged_at`; that narrower
history remains an explicit owner review rather than an automated claim. The
Issue #9 comment must contain all three exact lines/values:

```text
ROUTECONTRACT_PUBLIC_RECRUITMENT_OPEN tag=<exact-rc-tag>
ROUTECONTRACT_RC_ACTIVATION_VERIFIED tag=<tag> commit=<tagCommit> run=<runId> artifact=<artifactId> assets=12
ACTIVATION_RECORD_PERMALINK <exact-full-commit-record-url>
```

Every RC result Issue must copy that comment's exact permalink as the top-level
visible line `PUBLIC_RECRUITMENT_RECORD_PERMALINK <Issue-9-comment-permalink>`;
this binds the participant record to the same public opening used by the
chronology gate.

The final gate resolves those permalinks through GitHub, validates the
version-derived `independent-rcN-install.yml` bytes (the contest RC1 and RC2
forms each have a reviewed SHA-256 allowlist entry) and activation chronology,
and enumerates the repository Issue API by following every validated `rel=next`
link until GitHub returns no next relation. The
asserted count and URL must equal that enumeration; the renderer receives the
enumeration-derived values, never a hand-selected URL. API reads request cache
revalidation. A result must be an Issue opened by a non-owner `User` account
whose checked statement self-attests non-authorship, with an allowed
association, all 14 exact top-level visible checked self-attestations
(each required label appears exactly once), exact tag token, allowed Task-A
first outcome, labels and—for an RC result—the
two activation lines. An authenticated GraphQL query must match the REST Issue
and opener exactly while reporting no editor, last edit, retained body edit or
title rename. Creation must be strictly after release/recruitment and the current
row's creation/last-update timestamps must fall by cutoff. HTML comments, code
blocks, blockquotes, equal-second prerequisites, a post-cutoff edit,
foreign/partial pagination, duplicate Issue, or two countable results fail.
The automatic result predicate does not semantically grade the form's remaining
free-text answers; report and video wording is deliberately limited to those 14
checkboxes, the enumerated Task-A first outcome, and the API-visible fields.

The generated count means only “currently GitHub-API-visible in both packaging
observations, with row timestamps inside the cutoff window.” GitHub's current
API cannot reconstruct a permanently deleted historical Issue. The owner must
therefore manually attest that no eligible outcome or evidence Issue was
maintainer-edited, deleted, hidden, transferred, or knowingly omitted. The gate
binds that exact statement's digest and `true` value; it does not certify the
statement's truth.

The tracked report body is otherwise closed: only the documented private
identity, environment, public-link and owner-voice values may differ, and the
external row is generated. The participant manually attests that those private
free-text values do not introduce an external-result, adoption or stable-validation
claim. This is a human semantic review, not an NLP classifier. Stable Release
metadata in its designated fields is allowed; a stable external-validation claim
outside the generated row is not. Packaging verifies every canonical value in
the DOCX, exact generated external text in DOCX/PDF, and the PDF's complete
visible-character inventory and page/table anchors. A
partial placeholder fill, altered generated-text marker, tracking Issue
substituted for a participant result, mismatched tag, unsupported count, future
cutoff, nonexistent public reference, or mixed branch fact is a hard failure.

Set `submission_identity.receipt_number`, `team_name`,
`registered_project_name`, `team_size`, `division` and `task_type` to the exact
values shown in the application. The corresponding report metadata must match
all five visible identity values exactly. Text must already be Unicode NFC;
receipt number and team name must also be filename-safe. The gate refuses
unsafe, differently normalized or mismatched values instead of silently
changing them.

For the selected successful `Release evidence` run, record the artifact's
numeric GitHub artifact ID and API `digest` (copy the 64 hexadecimal characters
after `sha256:`) in the private manifest. Download that exact artifact as an
intact ZIP through the GitHub artifact API, then extract the ZIP without
changing any file bytes into `--release-evidence-dir`. If authentication is
needed, provide `GITHUB_TOKEN` or `GH_TOKEN` only through the process
environment; never write a token into the manifest or command line. The gate
ties the artifact ID, name, digest, workflow run and final commit together and
requires the extracted directory to be byte-identical to the downloaded ZIP.
For either RC report branch, the public-evidence collector also uses the
authenticated, safety-version-checked `gh api` path to re-download the exact
activation-record artifact ID. It requires the API byte size/digest, the exact
flat 17-regular-file allowlist, equality between all 12 Release members and the
Release/SHA256SUMS digests, exactly five workflow-only members, and no raw
`osv-raw.json` member.

Attach only the exact checksummed public release allowlist to the matching
GitHub Release: source ZIP; main, sources and Javadoc JARs; generated POM;
direct and aggregate CycloneDX JSON/XML files; the strict, revision-bound
`test-summary.txt`; the sanitized exact-revision
`supply-chain-evidence.json`; and `SHA256SUMS`. The v0.1 gate requires an empty
`signature_filenames` list; do not attach unimplemented `.asc` or `.sig`
claims. Environment, MySQL-image and standalone-consumer
logs and the example-profile CycloneDX JSON/XML pair remain workflow-artifact
evidence and must not be GitHub Release assets.
Raw JUnit XML and raw OSV JSON are not release assets; the fixed test summary exposes only the
expected suite identities and result counts. `SHA256SUMS` must declare exactly
the other public payloads, excluding itself; the five workflow-only files are
instead bound by the Actions artifact ID/digest, byte-identical extraction and
exact evidence allowlist. The package gate re-runs the semantic finalizer and
the pinned official CycloneDX CLI across all three JSON/XML pairs from that
exact extracted artifact, and binds the sanitized scan summary to the final
commit/tree, tracked scanner/database/policy inputs, all six SBOM documents,
published dependency lock and POM. The flat artifact therefore has exactly 17
files; the verifier's payload/evidence count is 16 after excluding
`SHA256SUMS`. Then run:

```bash
submission/private/report-builder-venv/bin/python \
  submission/tools/package_submission.py \
  --manifest submission/private/package-manifest.final.json \
  --template /absolute/path/to/official-result-report-template.docx \
  --content submission/private/report-content.final.ko.json \
  --report-pdf submission/private/RouteContract_Result_Report.pdf \
  --video-file submission/private/RouteContract_Demo.mp4 \
  --release-evidence-dir build/release-evidence \
  --release-evidence-artifact submission/private/routecontract-release-evidence.zip \
  --builder-python submission/private/report-builder-venv/bin/python \
  --output submission/package/routecontract-v0.1.0
```

The command refuses an existing output directory so a previous package cannot
be silently overwritten. On success, upload only the generated official-name
ZIP printed as `upload_zip=...`. With the currently enabled
`not_applicable` duplicate-benefit status, it contains only the same
official-name DOCX and PDF.
`PACKAGE-METADATA.json` and `SHA256SUMS` are local pre-submission audit
evidence, not organizer uploads. Finally, verify that the contest site shows
`제출 완료` and that the completion email arrived; a local ZIP cannot prove the
website submission itself.
