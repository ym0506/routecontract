# Contest report draft

This directory keeps the Korean content and a deterministic builder for the
official 2026 OSS Developer Contest result-report form.

The official template is intentionally retained outside this repository. Build
the draft with the bundled workspace Python runtime:

```bash
python submission/tools/build_official_report.py \
  --template /absolute/path/to/official-result-report-template.docx \
  --content submission/report-content.ko.json \
  --assets-dir submission/assets \
  --output submission/draft/routecontract-result-report-draft.docx
```

The builder verifies the organizer template SHA-256 before changing a working
copy. It deletes the writing-guide page and the inapplicable runtime-AI
attachment, validates and inserts both 1200x675 PNG evidence figures, fills the
official body/SBOM tables, and preserves the two original page sections and
table geometry. `--assets-dir` is optional when `assets/` is beside the content
JSON.

`[[...]]` values are deliberate submission gates, not claims. Replace each one
with the exact application/public evidence value, then require the final gate:

```bash
python submission/tools/build_official_report.py \
  --template /absolute/path/to/official-result-report-template.docx \
  --content submission/report-content.ko.json \
  --output submission/draft/routecontract-result-report-final.docx \
  --strict-final
```

After every content change, render every DOCX page and inspect it. Confirm that
the result-report body is at most five pages; Attachment 1 is not part of that
body limit. Also export the final DOCX to PDF with the same layout.

## Final submission package

The organizer's 2026 submission notice is the packaging authority:

- the upload ZIP contains the original report (`.docx`) and its PDF export;
- a duplicate-benefit confirmation is the only permitted third file, and only
  when it actually applies;
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
an exact two-file ZIP by default.

Before the final run, install and confirm these host tools: a Python runtime
with `python-docx` and Pillow for the report builder; Poppler's `pdfinfo`,
`pdfdetach`, and `pdftotext`; `ffprobe` (or macOS `mdls`) for the local video;
and `yt-dlp` for the public YouTube duration check. A missing verifier is a
hard failure, not a skipped check.

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
  --output submission/package/routecontract-v0.1.0
```

The command refuses an existing output directory so a previous package cannot
be silently overwritten. On success, upload only the generated
`RouteContract_2026_OSS_Contest.zip`. `PACKAGE-METADATA.json` and
`SHA256SUMS` are local pre-submission audit evidence, not organizer uploads.
Finally, verify that the contest site shows `제출 완료` and that the completion
email arrived; a local ZIP cannot prove the website submission itself.
