# RouteContract product roadmap

Planning snapshot: 2026-09-08. Items below are not release or delivery promises.
The August contest schedule in [development-plan.md](development-plan.md) is historical;
this document describes subsequent product work. Released scope remains in the README.

## Product direction

Make observed database-execution regressions easy to understand and review in a pull request.
The core stays a local test library with deterministic contracts. Distribution, actionable
reports and repeated independent use take priority over a hosted dashboard.

The first audience is a ShardingSphere-JDBC developer or team changing sharding predicates, SQL
rewrites, routing configuration or middleware versions. The job is to catch a changed execution
structure while preserving the application's existing result assertions.

## Delivery sequence and completion evidence

| Order | Outcome | Completion evidence | Current boundary |
| --- | --- | --- | --- |
| 1 | Understand a result without a stack trace | JSON/Markdown reports agree with the verifier; real-MySQL same-result `1 → 2`; same-count drift; incomplete capture; strict non-match exit | Released in [v0.1.3](ci-review-report.md) |
| 2 | Choose one short onboarding path | Newcomer identifies fit, runs one example, explains the rejection; record time and failure as well as success | [First project with v0.1.3](first-project.md); external usability unverified |
| 3 | Install through ordinary Gradle/Maven coordinates | Exact release resolved from public Central with empty caches and no credentials in both consumers | v0.1.3 published; [public readback and consumer evidence](evidence/release-0.1.3-central.md) |
| 4 | Support exact version lanes | Review [PR #62](https://github.com/ym0506/routecontract/pull/62); real DB tests and wrong-version/dual-adapter failures in each lane | Candidate supports 5.5.2/5.5.3; not released |
| 5 | Demonstrate repeated independent value | External developer uses a reviewed baseline and candidate check in their own project, then on a later real change; record assistance and verification separately | Private projects qualify; public case studies require separate evidence and permission |
| 6 | Offer shared review history if needed | At least three independent teams repeatedly need cross-run review and agree to a bounded pilot | Hypothesis; no hosted-service or revenue claim |

## Technical depth to pursue

- **Compatibility as a measured contract.** Test exact middleware/JDK/database/build lanes. Test
  adapter selection failures as well as the happy path. Separate MySQL from H2 evidence.
- **Sensitivity and stability.** Retain safe controls, budget mutations, same-count shape changes,
  incomplete captures and known blind spots. Record false positives and undetected mutations,
  not only passing test counts. Keep business outputs as an independent oracle.
- **Observer cost.** Compare library absent, present with capture disabled, capture enabled, and
  enabled with report generation outside the timed operation. Measure allocation/retention,
  CPU, latency and incomplete captures under stated concurrency and workload. Do not infer
  production performance from the existing correctness corpus. The [first local experiment](observer-cost.md)
  records operation time and estimated allocation for absent/idle/capture-plus-checks. Timing
  direction varies between blocks. A [separate lifecycle diagnostic](capture-retention.md) checks live per-capture
  object counts after repeated operations on four caller threads. Object-graph retained size,
  long-duration behavior, CPU, report cost and concurrency-related performance remain unmeasured.
- **Baseline evolution.** Human review stays explicit. A future version migration tool must show
  compatibility/semantic differences and never silently bless new fingerprints.
- **Failure explanation.** Stable findings and next steps must reflect the verifier's precedence.
  Reports must distinguish no regression, needs review, ineligible evidence and invalid input.

## Adoption work

Start with a short question about a recent SQL/sharding change and the existing verification method;
installation and a public repository are not prerequisites for that conversation. If there is a fit,
help the developer apply the library to one representative operation. Record conversation, demo,
project pilot, completed integration and repeat use separately from assistance, verification and
permission to publish. Private-project use is valid; label self-reported use as self-reported instead
of treating it as independently verified. Downloads, stars and maintainer-run examples are not
substitutes for external use. Record abandoned and failed attempts with their causes. Use the
[shared definitions](user-feedback.md#recording-use-and-evidence).

Prefer a small number of permission-based pilots over unsolicited patches. After fixing a
reported blocker, ask whether the same maintainer can finish the step independently. Public
case studies need the maintainer's agreement and reproducible links; do not expose private SQL,
bind values, connection properties or topology to recruit users.

Potential first contributions: improve a confusing diagnostic with an acceptance case; add a
distinct safe control to the regression corpus; reproduce an exact documented compatibility
failure. Every issue should state inputs, expected decision, a local command and supported scope.

## Conditions for a hosted service

A future service would store minimized results and commit/run identity, support team review,
retention/deletion and cross-run navigation, and integrate with repository checks. Start with
GitHub job summaries and artifacts; they already place reports next to failing CI.

If repeated team demand justifies hosting, first implement installation-scoped authorization,
idempotent event processing, superseded-commit handling, bounded ingestion, tenant isolation,
retention, deletion and an outage policy. The local check must remain usable during a service
outage. Never accept a self-submitted report as proof that the named commit executed it. Model
artifact provenance and baseline review as separate records.

No batch, Proxy, generic-JDBC, reactive or automatic-baseline expansion is promised. Admit a new
adapter only when its observed unit, operation attribution, error boundary and maintenance cost
are defined and demanded by a concrete user.

## Sources informing the design

- [datasource-proxy](https://jdbc-observations.github.io/datasource-proxy/docs/current/user-guide/)
  already provides JDBC listeners and query metrics; basic counting is not RouteContract's novelty.
- [GitHub job summaries](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#adding-a-job-summary)
  allow Markdown in the workflow run; this supports a small first review surface.
- [Central publication](https://central.sonatype.org/publish/publish-portal-guide/)
  requires verified namespace and validated components; published coordinates are immutable.
- [GitHub Apps](https://docs.github.com/en/apps/creating-github-apps/about-creating-github-apps/about-creating-github-apps)
  are a possible future installation/permission boundary, not a prerequisite for the local tool.
