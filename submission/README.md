# Submission report and package build

This directory contains the Korean report content, its deterministic
official-form builder, and the fail-closed final package gate for the 2026 OSS
Developer Contest.

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
`certifi` CA bundle used by the final public-evidence HTTPS checks. This local,
cross-platform file is version-pinned rather than wheel-checksum-locked. The
Ubuntu CI workflows instead use the platform-specific
`report-package-ci-requirements.txt` with exact CPython 3.12.14 wheel hashes and
pip `--require-hashes`. Build the draft with the local interpreter:

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
uses exactly ten. `THIRD_PARTY.md` retains the broader human inventory; the
generated CycloneDX files retain the Gradle-resolved dependency profiles and
intentionally exclude classifier-only files. The top ten puts the two GPL-family
entries first and separates the stable-Release Javadoc classifier's OpenJDK,
jQuery and jQuery UI assets by license and official source repository. The
digest-pinned MySQL OCI image remains explicitly unresolved in `THIRD_PARTY.md`
and the machine SBOM rather than receiving a fabricated image-wide license in
the official summary. CycloneDX build tooling, secondary test-only HikariCP and
datasource-proxy remain in the broader inventories; datasource-proxy also
remains in the comparison prose. Report-only Python tooling is pinned separately
and is not added to the official top-ten summary. `--assets-dir` is optional
when `assets/` is beside the content JSON.

`[[...]]` values are deliberate submission gates, not claims. Never put private
final values in the tracked source. Create the ignored final copy, replace gates
only there with exact application/public evidence values, then require the final
gate:

```bash
mkdir -p submission/private
cp submission/report-content.ko.json \
  submission/private/report-content.final.ko.json
submission/private/report-builder-venv/bin/python \
  submission/tools/build_official_report.py \
  --template /absolute/path/to/official-result-report-template.docx \
  --content submission/private/report-content.final.ko.json \
  --assets-dir submission/assets \
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
  must be no longer than 180 seconds. This project's caption-first final gate
  narrows the final duration to 173 through 175 seconds inclusive and also
  requires a local video at least 1920x1080, at least 20 decoded frames per
  second on average, exactly zero audio streams, burned-in Korean captions, and
  a public, non-live, age-unrestricted YouTube upload with a downloadable 1080p
  or higher video format. The selected branch's final tracked cue must fit in
  the manifest, local, and public durations. The storyboard requires actual
  screen frames through 173.000 seconds, so 173.000 seconds is the effective
  minimum even though the final cue ends at 172.500 seconds;
- Attachment 1 SBOM stays inside the report;
- Attachment 2 is intentionally removed under the organizer's development-
  assistance disclosure option because RouteContract has no runtime AI model
  or AI API path; development-time ChatGPT/Codex use remains disclosed in the
  main report;
- source archives, machine CycloneDX files, checksums and video files are
  release/internal verification evidence and must not be added to the upload
  ZIP.

`package_submission.py` implements those rules as a fail-closed final gate. It
rebuilds the DOCX with `build_official_report.py --strict-final`, checks the PDF
content and page boundary, requires the local and public video durations to be
within the inclusive 173-through-175-second window, checks the default playable
motion-stream dimensions, at least 20 decoded frames per second on average,
exactly zero audio streams, a complete selected-stream decode, post-decode file
hash stability, a final rehash immediately before audit-metadata creation, and
a narrow privacy-sensitive format/stream/chapter/program metadata denylist with
`ffprobe`. It also binds the fixed `submission/video-caption-cues.json` path,
schema and source SHA-256, renders the selected `zero` or `rc_only` SRT
deterministically, and records the selected-cue and SRT hashes. It verifies the
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
`ffprobe` for local-video metadata and `ffmpeg` for a full decode of the
selected motion stream, including the at-least-20 average decoded-fps check and
post-decode file-hash recheck; `yt-dlp --check-all-formats` for public
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

The video gate does not require a particular codec and cannot grade whether the
burned-in captions match the visible real execution or remain readable from
pixels alone. The owner must still watch the checksummed local file from start
to finish, confirm
that it shows the actual recorded screens and the selected generated captions,
and only then set
`final_local_video_actual_screen_caption_watchthrough_completed=true`.
The owner must also watch the logged-out public 1080p playback and attest that
its frames, zero-audio behavior, and captions are equivalent to that reviewed
local file before setting
`final_public_video_frame_audio_caption_equivalence_review_completed=true`.
The `yt-dlp` result is downloadable-format inventory evidence: this gate does
not download the entire public video or perform public/local pixel, audio, or
caption comparison, so that equivalence remains participant-attested.

Every final terminal take must invoke `scripts/video-demo-session.sh` with
`--final-recording`. Before starting its child command, that opt-in mode requires
the exact sealed commit, tree, canonical origin and annotated stable tag through
the four documented `ROUTECONTRACT_FINAL_*` environment values, then verifies
the exact repository root, HEAD/tree/tag binding and a clean tracked/untracked
worktree. The ordinary one-argument modes remain available for rehearsal and do
not claim that the recorded checkout is the final revision.

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

The current private input manifest is schema version `5`. Version `1` predates
the declared video evidence branch; versions `1` and `2` predate the bounded
participant-understanding attestation contract; version `3` predates the
AI-assistance-aware owner-voice attestation; version `4` predates the fixed-path
caption-source binding, selected-SRT hashes, and split local/public video review
attestations. All older versions are deliberately
rejected; recopy the example instead of silently treating an older file as complete.

Replace every `[[...]]` gate in those private copies, export the PDF from the
strictly generated DOCX, and set every participant attestation to `true` only
after checking it. In particular,
`core_behavior_boundaries_artifacts_and_dependency_roles_reviewed_and_explainable`
is a focused human-understanding gate, not a claim of line-by-line authorship or
a legal or security review of every transitive dependency. Before setting it to
`true`, the participant must review the final submitted diff, reproduce the clean
build and Quick Start, and be able to explain the capture/callback lifecycle,
fail-closed and concurrency limits, privacy boundary, candidate/approved
manifest policy and evidence limits. The participant must also explain the
purpose and non-proof limits of the generated JAR, POM, source archive, SBOM,
checksum, test-summary and report artifacts, plus the roles and scopes of the
runtime, compile-only, test, build/audit and report-tool dependencies used by
those paths.

Separately,
`report_free_text_contains_no_external_evidence_claims` is a human-review gate:
the participant confirms that development hardware, public-link prose and owner
voice do not add an external-result, adoption or stable-validation claim outside
the generated `외부 검증` row. The tool does not pretend to classify arbitrary
natural-language paraphrases. The final tag must be an annotated, stable `vMAJOR.MINOR.PATCH`
tag and its GitHub Release must be public, non-draft, non-prerelease and
immutable. The selected Actions evidence must be a successful push run for that
exact tag and revision; the gate cryptographically verifies the Release and
every one of its attached public assets with GitHub's release attestations.

The `개발 소감` owner-voice block may use AI drafting or editing only when that
assistance is disclosed. Before setting
`owner_voice_ai_assistance_disclosed_and_participant_reviewed=true`, the
participant must review and adopt the final text as an accurate first-person
account, verify its concrete statements about the hardest problem, their own
analysis or experiments, lessons learned, and active-maintenance priority, order,
and intended period, and be able to explain it. This attestation does not claim
participant-only authorship. Set `maintenance_order_and_period_confirmed=true`
separately after confirming that concrete maintenance commitment. Contest rule Article
10(3) requires a selected excellent or award-winning team to keep the public
repository Public for five years from the award date. Set
`five_year_public_repository_visibility_obligation_if_selected_accepted=true`
only after understanding that conditional visibility obligation; it is not an
active-maintenance promise. Confirm the tracked provenance statement with
`origin_and_prior_work_statement_confirmed=true`; that is a participant
self-attestation, not independent proof. The tool does not semantically decide
whether the owner voice, its AI-assistance disclosure, or provenance statement is
true or adequate.

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

Set `video.external_evidence_branch` to that same exact `rc_only` or `zero`
branch. Packaging rejects a report/manifest branch-declaration mismatch; it
does not infer audiovisual meaning from the video bytes. Keep
`video.caption_contract.source_path` fixed at
`submission/video-caption-cues.json`, its schema at `1`, and its SHA-256 equal
to the tracked file. Generate the branch-selected SRT from that sole caption
authority with:

```bash
python3 submission/tools/video_caption_contract.py \
  --branch zero \
  --expected-source-sha256 e698947f8b5a8df610d5b4e521758ef781a11e4f694618340aff2f54721f3f83 \
  --output /absolute/private/path/routecontract-zero.srt
```

Use `--branch rc_only` when that is the selected report/video branch. Burn the
generated SRT into the actual recorded screens, then complete the two local and
public review attestations described above; the storyboard mirror is not a
second caption source.

`final_stable` is unavailable because the reviewed participant form and
protocol are RC-specific; the package gate rejects that branch.

Both enabled branches retain the fixed public Issue #9 protocol URL and an exact UTC
cutoff no later than the package validation instant; an RC tag must share the
final stable tag's version. For RC branches, the activation permalink is the
full-commit schema-v2 JSON produced by the one-file direct-child workflow. The
record must be the unchanged public `main` during activation validation and recruitment, and must
have reached it through one squash pull request. At final stable packaging, public `main` is the
later stable commit; the package gate instead requires the activation-record commit to remain its
ancestor and binds the exact record bytes, permalink, and squash PR. The gate binds that PR's server
`merged_at` strictly after the RC prerequisites and strictly before the recruitment comment and
cutoff. Commit author/committer dates alone are not accepted as publication time. GitHub's current
API does not reconstruct historical repository visibility or branch protection at `merged_at`;
that narrower history remains an explicit owner review rather than an automated claim. The
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

The tracked report body is otherwise closed: only the documented structured
metadata and six owner free-text overlays may differ, and the external row is
generated. The six `OWNER_FREE_TEXT_OVERLAY_STRING_PATHS` are `개발 장비`,
`재현과 패키징`, `설치·릴리스`, `라이선스 검토 상태`, `공개 증거 gate`, and
`개발 소감`; the high-confidence lexical privacy scanner applies only to those six values. It
rejects common credential, contact, local-path, private-topology and raw-SQL
leak forms, but it is a heuristic and cannot prove that arbitrary prose or
topology is safe. The participant manually attests that those six free-text
values do not introduce an external-result, adoption or stable-validation claim
and sets `report_free_text_privacy_reviewed=true` only after manual privacy
review. These are human attestations, not NLP classifiers. Structured
registration identity is not checked by that lexical scanner: its six
`submission_identity` values are exact-bound to the application, private
manifest, report fields and official filenames where applicable, and the
participant must manually review their exactness and disclosure. Reader-facing
`E01`–`E14` audit IDs are rejected from every private overlay and from the final
DOCX/PDF; the public crosswalk stays in
`docs/evidence-matrix.md`. The check applies after Unicode compatibility and
case normalization, so those tokens are reserved even when they would be part
of a hardware model name; rewrite such a model descriptively in the private
hardware disclosure. Stable Release metadata in its designated fields is allowed; a stable
external-validation claim outside the generated row is not. Packaging verifies every canonical value in
the DOCX, exact generated external text in DOCX/PDF, and the PDF's complete
visible-character inventory and page/table anchors. A
partial placeholder fill, altered generated-text marker, tracking Issue
substituted for a participant result, mismatched tag, unsupported count, future
cutoff, nonexistent public reference, or mixed branch fact is a hard failure.

Set `submission_identity.receipt_number`, `team_name`,
`registered_project_name`, `team_size`, `division` and `task_type` to the exact
values shown in the application. The corresponding report metadata must match
all five visible identity values exactly. The official report has one
`과제유형` cell: copy the exact registered value into both private inputs. Do
not invent, append, or combine a detail that the application does not display;
for example, a registration that shows only `자유과제` must remain
`자유과제`. Text must already be Unicode NFC;
receipt number and team name must also be filename-safe. The gate refuses
unsafe, differently normalized or mismatched values instead of silently
changing them.

The private `설치·릴리스` overlay must show the full Maven coordinate
`io.github.<owner>.routecontract:routecontract-shardingsphere-5.5:<tag without v>`,
and the private `공개 증거 gate` overlay must show the exact 40-character final
commit SHA. The package gate binds both reader-visible values to the manifest;
a group-only coordinate, wrong artifact/version, or abbreviated/different SHA
is rejected.

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
evidence, not organizer uploads. The emitted audit metadata is schema version
`4`; it includes the video/report external-evidence branch, the bound silent-video
decode evidence, source/selected-cue/SRT caption hashes, explicit `false`
automatic pixel/equivalence fields, and the two participant-review attestations.
It must not be interpreted with the older schema. Finally, verify that the contest site shows
`제출 완료` and that the completion email arrived; a local ZIP cannot prove the
website submission itself.
