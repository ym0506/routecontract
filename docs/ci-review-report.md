# CI review reports

Available in v0.1.3 through [GitHub Release assets](https://github.com/ym0506/routecontract/releases/tag/v0.1.3)
and a [Maven Central test dependency](../README.md#install-013); see the
[Central verification record](evidence/release-0.1.3-central.md).
The v0.1.2 local installer does not include these APIs.

## See the result first

Open the [Markdown example](evidence/ci-review-report-example.md) or
[JSON example](evidence/ci-review-report-example.json) without installing anything.
The report shows attempts and observed data-source aliases changing from `1` to `2`,
so the test fails with `POLICY_VIOLATION` (an allowed maximum was exceeded):

| Code | Plain meaning | Example values |
| --- | --- | --- |
| `RCM201` | Too many physical JDBC execution attempts were observed. | Actual 2; allowed 1. |
| `RCM202` | Too many distinct data-source aliases were observed. | Actual 2; allowed 1. |

A budget is an allowed maximum; an alias is a non-sensitive label for a configured data source.
The approved baseline supplies these limits. Inspect the changed query and sharding rules to
understand why the extra execution happened, then fix it or review an intentional change.

## Try the released report without Docker

You need Git and Java 17. The first run needs network access for Gradle and Java
dependencies. This checks the committed example manifests; it does not start a
database or constitute a new MySQL experiment.

Run this from a directory where `routecontract-v0.1.3-review` does not already exist:

```bash
(
set -e
git clone --depth 1 --branch v0.1.3 --single-branch \
  https://github.com/ym0506/routecontract.git routecontract-v0.1.3-review
cd routecontract-v0.1.3-review
mkdir -p build
./gradlew --quiet :routecontract-shardingsphere-5.5:reviewManifest \
  -PapprovedManifest=examples/manifests/find-paid-orders-by-user.approved.json \
  -PcandidateManifest=examples/manifests/find-paid-orders-by-user.candidate.json \
  -PreviewReportOutput=build/review-first.md
)
```

**Expected result:** Gradle reports a failure because the example violates the
contract. Open `routecontract-v0.1.3-review/build/review-first.md` to see the
`POLICY_VIOLATION` report with `RCM201` and `RCM202`. A failed command without that
report is not a successful demonstration; inspect the setup or build error.

For JSON, run the same Gradle command from the cloned directory with
`-PreviewReportFormat=json` and `-PreviewReportOutput=build/review-first.json`.
Use a new output path each time; an existing report is never overwritten.

To see a passing unchanged-input comparison, run this from the cloned directory:

```bash
./gradlew --quiet :routecontract-shardingsphere-5.5:reviewManifest \
  -PapprovedManifest=examples/manifests/find-paid-orders-by-user.approved.json \
  -PcandidateManifest=examples/manifests/find-paid-orders-by-user.approved.json \
  -PreviewReportOutput=build/review-match.md
```

This command exits successfully and writes `MATCH`. It compares the same committed
fixture on both sides; your own project's baseline still needs its normal review.

This path uses the immutable v0.1.3 source tag. The [v0.1.2 MySQL Quick Start](reference-guide.md#quick-start)
remains a separate database demonstration. The [release verification record](evidence/release-0.1.3-github.md)
identifies the published binaries and the tagged CI run.

## Use in an application test

The [first-project guide](first-project.md) connects the published dependency, one MySQL test,
candidate capture, baseline review and a failing CI comparison with Maven or Gradle.

With the v0.1.3 library on the test classpath, call
`ManifestReviewReport.compare(approved, candidate)`, then `toMarkdown()` or `toJson()`.
Use `verification()` with the existing assertions; the report is a presentation layer.
The CLI main class is `io.github.ym0506.routecontract.manifest.ManifestReviewCli`,
accepting exactly `--baseline PATH --candidate PATH --format markdown|json --output PATH`.
It needs the library's runtime dependencies on the classpath; the published JAR is
not a self-contained executable JAR.

To discuss whether the output would help your CI review, use the
[short feedback form](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml).
A description of what was clear or missing is enough; running this example is not
the same as integrating RouteContract into your own project.

## Acceptance contract

A reviewer should see the governing baseline budgets, observed count changes, stable RCM codes,
and the next investigation step without reading a Java stack trace. Reports must use
`ManifestVerifier` as the only decision engine. They must preserve its precedence: incompatibility,
ineligible capture, budget violation, structural drift, review required, match.

- A real-MySQL operation returning the same business result with attempts `1 → 2` must produce
  `POLICY_VIOLATION`, `RCM201`, `RCM202`, and a failing strict CI exit.
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
