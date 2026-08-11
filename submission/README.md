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
closure, including python-docx's `typing_extensions` dependency. Build the
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
  this gate currently refuses `status=required`: the organizer's exact source
  form is not retained locally, so its title, identity fields and placeholders
  cannot yet be verified safely;
- source code is represented by exactly one public repository URL in the
  report;
- the demonstration is represented by a public YouTube URL in the report and
  must be no longer than 180 seconds;
- Attachment 1 SBOM stays inside the report;
- Attachment 2 is removed because RouteContract has no runtime AI model or AI
  API path; development-time ChatGPT/Codex use remains disclosed in the main
  report;
- source archives, machine CycloneDX files, checksums and video files are
  release/internal verification evidence and must not be added to the upload
  ZIP.

`package_submission.py` implements those rules as a fail-closed final gate. It
rebuilds the DOCX with `build_official_report.py --strict-final`, checks the PDF
content and page boundary, checks the local video with `ffprobe`, verifies the
exact Git revision/tag/public repository/green release-evidence run/GitHub
Release, verifies the release artifact checksums and aggregate SBOM, and emits
an exact two-file ZIP by default. It derives the DOCX, PDF and ZIP names from
the private manifest as
`2026 오픈소스 개발자대회 결과보고서_접수번호(팀명).{docx,pdf,zip}`;
the old fixed English report and ZIP filenames are rejected.

Before the final run, install the pinned report-builder environment above and
confirm these host tools: Poppler's `pdfinfo`, `pdfdetach`, and `pdftotext`;
`ffprobe` (or macOS `mdls`) for the local video; and `yt-dlp` for the public
YouTube duration check. A missing verifier is a hard failure, not a skipped
check. If duplicate-benefit status is required, obtain and retain the exact
organizer form and implement its title/identity/placeholder validation before
enabling that path; do not substitute an arbitrary document.

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
after checking it. The final tag must be an annotated, stable `vMAJOR.MINOR.PATCH`
tag and its GitHub Release must be public, non-draft and non-prerelease.

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

Attach only the exact checksummed public release allowlist to the matching
GitHub Release: source ZIP; main, sources and Javadoc JARs; generated POM;
direct and aggregate CycloneDX JSON/XML files; the strict, revision-bound
`test-summary.txt`; and `SHA256SUMS`. The v0.1 gate requires an empty
`signature_filenames` list; do not attach unimplemented `.asc` or `.sig`
claims. Environment, MySQL-image and standalone-consumer
logs remain workflow-artifact evidence and must not be GitHub Release assets.
Raw JUnit XML is not a release asset; the fixed test summary exposes only the
expected suite identities and result counts. `SHA256SUMS` must declare exactly
the other public payloads, excluding itself; the three workflow-only logs are instead bound by the
Actions artifact ID/digest, byte-identical extraction and exact evidence
allowlist. Then run:

```bash
python3 submission/tools/package_submission.py \
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
