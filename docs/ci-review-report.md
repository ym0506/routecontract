# CI review reports

Status: development feature in this checkout; not part of the published v0.1.2 assets.

## Acceptance contract

A reviewer should see the governing baseline budgets, observed count changes, stable RCM codes,
and the next investigation step without reading a Java stack trace. Reports must use
`ManifestVerifier` as the only decision engine. They must preserve its precedence: incompatibility,
ineligible capture, budget violation, structural drift, review required, match.

- A real-MySQL operation returning the same business result with attempts `1 → 2` must produce
  `POLICY_VIOLATION`, `RCM201`, `RCM202`, and a failing strict CI exit.
- Schema-2 manifests from the same supported exact runtime may match. A 5.5.2/5.5.3
  identity mismatch must produce `INCOMPATIBLE`, `RCM005`, and strict exit 1 before budget
  checks. Unsupported identities produce `RCM004`; legacy schema 1 remains implicitly 5.5.3.
- Same-count SQL/type-shape changes must remain visible as structural drift.
- `REVIEW_REQUIRED` must never be presented as `MATCH`. The CLI requires an exact match (exit 0);
  any valid non-match exits 1; invalid input, arguments or output errors exit 2.
- JSON and Markdown must be deterministic, network-free, and derived from the same result.
- At most 100 findings are rendered, with total and omitted counts in both formats. The full
  verifier result remains available through the Java API; truncation never changes the decision.
- The CLI reads at most the manifest codec's one-MiB limit per input. It creates a new output
  file and never replaces a baseline, candidate, existing report, hard link or symlink.
- Error output must not echo parser exception details, file paths or manifest values.
- Markdown contains only fixed messages, counts, codes and canonical manifest digests. User
  operation IDs, aliases, class names and free-form diff details are omitted from both formats.
  This reduces disclosure and avoids Markdown/HTML injection; it is not a security certification.
- Digests identify the decoded, canonically re-encoded manifest, not original file bytes, origin,
  freshness or human approval. Approval provenance stays in the repository's review process.
- No command approves a baseline, uploads artifacts, posts a PR comment or connects to a database.

## Run against the included example

Java 17 and this source checkout are required. No Docker is needed to review the committed
example; this command alone does not constitute a new database experiment.

The unreleased 0.2 source exposes this command from `routecontract-core`, without loading a
ShardingSphere adapter. The previous `:routecontract-shardingsphere-5.5:reviewManifest` task remains
a compatibility alias. After an intentional runtime migration, recapture and separately review
the baseline; editing its runtime identity does not establish approval.

```bash
mkdir -p build
./gradlew --quiet :routecontract-core:reviewManifest \
  -PapprovedManifest=examples/manifests/find-paid-orders-by-user.approved.json \
  -PcandidateManifest=examples/manifests/find-paid-orders-by-user.candidate.json \
  -PreviewReportOutput=build/review-first.md
```

The Gradle task intentionally fails because the example violates the contract. The Markdown
report remains at `build/review-first.md`. Choose a new output path for each invocation.
Add `-PreviewReportFormat=json` for JSON. Paths are relative to the repository root.

From an application test, call `ManifestReviewReport.compare(approved, candidate)`, then
`toMarkdown()` or `toJson()`. Use `verification()` with the existing assertions; the report is
a presentation layer. The CLI main class is
`io.github.ym0506.routecontract.manifest.ManifestReviewCli`, accepting exactly
`--baseline PATH --candidate PATH --format markdown|json --output PATH`.

## CI use

Generate the report in the same job as the candidate check. In a following `if: always()` step,
append the Markdown to `$GITHUB_STEP_SUMMARY` only when the new file exists. Upload it alongside
the candidate and test results with the repository's existing artifact policy. Keep the check's
failure; do not replace it with the success of the artifact-upload step. Use a fresh job output
directory so an earlier successful report cannot be mistaken for the current result.

The report deliberately omits free-form structural details. Review the minimized candidate and
baseline in the repository when investigating a changed fingerprint/type shape. An approved
policy still governs comparison even if the candidate raises its own budget. The reader must
retain the business-result assertion: a hook callback return is neither a commit nor business
success, a physical attempt is not a physical-table count, and budget growth alone does not
prove a performance regression.
