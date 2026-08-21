# 2026 contest evidence matrix

Status date: 2026-08-11 KST

This is a dated historical snapshot. The source now declares candidate version `0.1.0-rc1`, but
that string does not update any row or prove publication. Event-dependent RC facts belong in the
validated fixed activation record; final stable evidence remains a separate gate.

This is a working audit ledger, not a score prediction. The [official 2026 contest page](https://www.oss.kr/pages/2) confirms the student division, the August 27 submission date, the report/source/three-minute-video deliverables, and the later functional and license verification stages. The detailed point allocation below follows the organizer's [August 20 judging notice](https://osscontest.kr/notice/41), which supersedes the earlier orientation allocation.

## Status vocabulary

These terms describe artifact maturity. They are independent of the technical environment labels
in `AGENTS.md` such as `verified - unit`, `verified - MySQL`, and
`verified - ShardingSphere-JDBC 5.5.3`; a measured claim must retain both axes.

| Status | Meaning |
|---|---|
| `implemented-worktree` | Relevant source or test exists locally, but that alone is not a reproducible contest artifact. |
| `verified-local` | A local run produced inspectable output on the named environment. It is not yet clean-clone or CI evidence. |
| `artifact-ready` | Raw result, exact command, environment, revision and human-readable verification are committed and linked. |
| `externally-verified` | A non-author independently installed, ran or reviewed it, and the public record is linked. |
| `pending` | The required evidence does not exist yet. |

Only `artifact-ready` or `externally-verified` evidence should be quoted as a final report result. A source file existing is not proof that the documented behavior passed.

## Evidence register E01-E14

| ID | Evidence package | Minimum acceptance criteria | Current status | Current evidence and missing work |
|---|---|---|---|---|
| E01 | Public problem evidence | Public issue with version, reproduction, expected/actual behavior and relevance to the problem | `pending` | Upstream issue [apache/shardingsphere#38456](https://github.com/apache/shardingsphere/issues/38456) provides real public problem evidence. A RouteContract repository issue that narrows the general product requirement, links the external issue and states this tool's acceptance boundary is still pending. |
| E02 | 5.5.3 adapter and activation proof | Tagged source permalink for the `SQLExecutionHook` provider, service descriptor, fail-closed activation/preflight test and supported compatibility-artifact versions | `verified-local` | The provider, service descriptor and fail-closed lifecycle are now present at an immutable public revision, and the [public main CI](https://github.com/ym0506/routecontract/actions/runs/31501026857) contains 3/3 passing preflight tests. The preflight checks that `infra-executor` and `infra-spi` each report 5.5.3 and that exactly one RouteContract provider is discovered, not that every dependency-graph artifact has the same version. This row still requires a tagged release permalink before promotion. |
| E03 | Single-data-source MySQL control | Real MySQL + ShardingSphere-JDBC 5.5.3 command, one business assertion, one complete capture and one observed attempt/data-source result | `artifact-ready` | The [revision-bound public CI evidence](public-ci-evidence.md) contains 5/5 passing `OperationCorrelationMySqlTest` cases against digest-pinned MySQL 8.4.11, including the complete one-attempt control. Raw JUnit XML and the runner environment are retained in the linked Actions artifact. |
| E04 | Business-green / contract-red demonstration | Same returned business result for control and mutation; mutation exceeds a declared observed-attempt or data-source budget; raw and summarized result | `artifact-ready` | The public CI revision verifies the equality/range pair with `businessResult=UNCHANGED`, observed attempts `1->2`, `POLICY_VIOLATION` and blocking codes `RCM201,RCM202`; assertions also verify expansion from one to both data sources. A separate checked-in file-based task is locally verified to propagate a non-zero assertion exit, but is intentionally excluded from green CI. The issue-#38456-inspired reduced and modified pair returns `COUNT=1` for both forms while observing `1` versus `8` attempts; it is not an exact upstream reproduction. See the [raw-result and limitation record](public-ci-evidence.md). |
| E05 | Canonical manifest and semantic diff | Versioned JSON schema, deterministic record, verify mode, added/removed/change summary, malformed/missing baseline behavior and sample raw JSON | `artifact-ready` | The immutable revision contains canonical MySQL-generated approved/candidate pairs plus expected RCM-coded diffs. Its public CI artifact has 15/15 passing manifest tests covering malformed, zero-event, over-limit and path-alias rejection, and the MySQL suite regenerates the examples byte-for-byte. This proves the current revision, not a stable release format commitment. |
| E06 | Regression corpus and comparison | At least four route-risk mutations and two safe controls on real MySQL; expected business result; RouteContract result; `sql-show`/Audit/generic-tool comparison where applicable | `artifact-ready` | The public MySQL artifact reports 7/7 corpus cases plus the 1/1 datasource-proxy comparison. It covers six safe cases, five risk shapes, Audit-positive controls, strict versus `budgetOnly` policy sensitivity, the reduced/modified `1` versus `8` issue-inspired pair, and the same-budget `RCM301/RCM302` drift. Eight case signatures were each repeated 20 times. The datasource-proxy result supports a packaging-and-defaults claim, not categorical superiority; see [the bounded public evidence](public-ci-evidence.md). |
| E07 | Determinism and concurrent caller-operation isolation | At least 20 repeated captures with one semantic manifest plus at least 20 pairs of concurrently open caller capture scopes with zero mixed captures; exact environment and raw output | `artifact-ready` | The public MySQL result records `repetitions=20`, `uniqueSignatures=1`, `simultaneousPairs=20` and `mixedCaptures=0`. The historical `simultaneousPairs` marker means caller capture scopes were concurrently open; physical callback overlap was not forced or measured. This is bounded to the documented synchronous PreparedStatement scenario, not arbitrary async work. |
| E08 | Clean clone and Linux CI | Public clean-clone quick start; Ubuntu CI on claimed JDKs; no local cache assumptions; functional and privacy tests; immutable workflow link | `verified-local` | [Main run `31501026857`](https://github.com/ym0506/routecontract/actions/runs/31501026857) passed from a clean Ubuntu 24 checkout on Temurin 17: 45 submission-package tests, the default fail-closed installer suite, 50 normal Java/MySQL tests, verified SBOM generation and one isolated same-checkout generated-publication/MySQL consumer test. The [environment, raw XML, artifact digests and retention boundary](public-ci-evidence.md) are recorded. However that workflow did not invoke `./scripts/quickstart-demo.sh` itself, so this combined row stays below `artifact-ready` until the public clean-clone Quick Start criterion is also exercised. |
| E09 | Release and supply-chain identity | Public immutable stable release selected by the final manifest (planned `v0.1.0`), source/tag, checksums, generated artifacts, reproducible install coordinates or an explicit no-registry install path | `pending` | The no-registry installer requires an exact flat public-asset set, canonical coordinates, strict version/JAR/source structure and semantic binding of the sanitized supply-chain summary to the public SBOM/POM assets. The final package gate additionally binds that summary to the exact commit/tree, scanner/database lock, policy and published dependency lock. An RC remains prerelease evidence. The planned final is a new stable `v0.1.0`; if it fails a required post-publication verification, select a corrected immutable stable patch rather than replacing assets or retagging. The release workflow keeps environment/MySQL/consumer logs outside the public checksum under the immutable workflow-artifact digest and exact evidence allowlist. At this matrix's 2026-08-11 cutoff, no public release, final-tag run or checksum set was recorded; later RC facts belong only in a validated activation record. |
| E10 | Independent user evidence | At least one non-author follows the public quick start without private help; record environment, outcome, time/blockers and resulting issue/fix | `pending` | No external RouteContract user or independent installation result exists. Do not substitute an AI review or the author's second machine for an external user. |
| E11 | Competitive analysis | Source-linked capability comparison; no "first/only" claim; one reproducible close-alternative comparison | `artifact-ready` | [Competitive analysis](competitive-analysis.md) provides the source-based landscape, and the [datasource-proxy experiment](empirical-comparison.md) ran in the same public MySQL job as RouteContract. It proves that a comparable narrow workflow is buildable and supports packaged-integration value, not categorical superiority. |
| E12 | License, notices, dependency inventory and SBOM | Project license, NOTICE where required, third-party licenses, dependency lock/inventory, generated SBOM, license/security scan and manual review notes | `verified-local` | Apache-2.0 `LICENSE`, `NOTICE`, `THIRD_PARTY.md`, pinned wrapper, locks, checksum metadata and CycloneDX generation are public. The candidate exact-revision gate checks aggregate/direct profile partition, JSON/XML pairs, generated POM/runtime closure, licenses and a pinned offline OSV database, and the release integration retains only a sanitized summary. The local candidate audit reports three time-bounded reviewed findings in the example/test profile, not zero vulnerabilities. This row still requires the reviewed changes to merge, a successful immutable final-tag run and the owner's manual license/NOTICE review. |
| E13 | Individual project-management trail | Real GitHub issues, focused branches/PRs, specification-first discussion, CI, line-by-line self-review, linked merges and milestones | `artifact-ready` | The bootstrap was honestly imported as one root commit rather than fabricated history. The first clean-CI failure is linked to [Issue #5](https://github.com/ym0506/routecontract/issues/5); [PR #6](https://github.com/ym0506/routecontract/pull/6) contains a focused checksum-only fix, owner self-review, green build and Dependency Review, and a linked merge. Milestone `v0.1.0` and Issues #7-#11 track genuinely unfinished work. This is an early single-maintainer trail and contains no independent review claim. |
| E14 | Upstream/community question | A concise RouteContract-specific design or integration question to the relevant community, public response if any, and honest disposition | `pending` | The related upstream PR [#39112](https://github.com/apache/shardingsphere/pull/39112), opened by GitHub user `Develop-KIM`, was closed without merge after substantive review. Until participant ownership of that account is confirmed, it is external problem-analysis history rather than participant prior-work or community-credit evidence. It is not upstream acceptance of RouteContract, and no RouteContract-specific upstream question or endorsement exists. |

### Public CI and local verification snapshot

The seven normal suites and the isolated consumer result below are available in the [revision-bound public CI artifact](public-ci-evidence.md). The local timing remains development context rather than public performance evidence:

- `RouteContractTest`: 18 tests, 0 failures.
- `ShardingSphere553PreflightTest`: 3 tests, 0 failures.
- `ObservedExecutionManifestTest`: 15 tests, 0 failures.
- `OperationCorrelationMySqlTest`: 5 tests, 0 failures.
- `ObservedExecutionRegressionCorpusMySqlTest`: 7 tests, 0 failures.
- `FailureBoundaryMySqlTest`: 1 test, 0 failures.
- `DataSourceProxyComparisonMySqlTest`: 1 test, 0 failures.
- Root build total: 50 tests, 0 failures; isolated same-checkout generated-publication consumer: 1 test, 0 failures.
- Canonical command `./gradlew --no-daemon --no-build-cache clean check assemble prepareVerifiedSbom`: `BUILD SUCCESSFUL` in 1 minute 10 seconds on the author's Java 17.0.15/macOS/Docker Engine 29.2.1 environment. The run compiled with warnings-as-errors, executed all 50 normal tests, assembled the library artifacts, generated aggregate/direct JSON and XML SBOMs, and verified Apache-2.0 first-party component metadata with counts `3/1/2` for aggregate/library/MySQL BOMs. Container startup dominates wall time; individual JUnit suite durations must not be presented as end-to-end runtime.
- `./scripts/verify-standalone-consumer.sh` independently resolved the locally published Maven coordinate, auto-discovered the packaged SPI provider and passed 1/1 real-MySQL test.
- An exact-revision local audit of the PR #19 dependency candidate observed 3 reviewed OSV matches versus 12 in the older main graph. Separately, its 50-test root build and 1-test standalone consumer were green. The integration candidate stages only the sanitized summary in exact-tag release evidence. At this matrix's cutoff, no public final-tag run or immutable Release was recorded; later RC facts require the separate activation record, and the raw OSV report remains excluded.
- `python3 -m unittest discover -s scripts/tests -v` passed the default fail-closed installer suite. The opt-in test separately used real locally built JARs and the generated POM rewritten to a strict `1.2.3-rc1` coordinate, together with synthetic source-ZIP/SBOM/test-summary fixtures, then installed that checksummed set into an isolated repository and passed the real-MySQL consumer. It is not a real Git archive, published Release or external-user result.
- `./scripts/demo-manifest-ci-failure.sh` intentionally exited `1` after printing `RCM201` and `RCM202`; this red task is isolated from normal `test`/`check` and proves that the checked-in candidate propagates an uncaught build failure.

Local copies of these files are ignored build output and can be overwritten. The linked Actions copies identify an immutable revision but expire after 90 days; the final release must publish permanent, checksummed replacements.

## First-round rubric: 30 points

The orientation allocates six points to each item. The table maps what a reviewer must be able to click or reproduce; it does not award points internally.

| Official item | Evidence IDs | What the submission must make verifiable | Current risk |
|---|---|---|---|
| Code structure and completeness — 6 | E02, E03, E05, E06, E07, E08 | Small public API, isolated 5.5.3 adapter, fail-closed activation, complete lifecycle, deterministic model, real-MySQL coverage and clean build | Medium-low at the cutoff: public Linux/MySQL evidence existed; a tagged release and independent install had not been recorded |
| Open-source growth — 6 | E09, E10, E13, E14 | Public release, usable contribution path, independent install feedback, visible issue/PR discussion and an upstream/community touchpoint | Critical at the cutoff: real Issue/PR history had begun, but a release, external user and upstream contact had not been recorded |
| Documentation — 6 | E01, E05, E06, E08, E11, E12 | Problem and scope, five-minute quick start, architecture/event semantics, reproducible evidence, limits, license/SBOM and comparison | Medium-low: runnable docs and public CI evidence exist; stable-release and external-user documentation remain |
| Innovation — 6 | E01, E04, E06, E11 | Demonstrated gap between business assertions and observed execution, a credible prior-art comparison and a reusable solution beyond one demo | Medium: the differentiating corpus and generic-tool comparison are public, but the contribution remains a bounded workflow integration rather than a new observation primitive |
| Individual project management — 6 | E13 plus links to E01-E12 | Issues precede work, PRs are scoped, commits explain decisions, CI and self-review are visible, no fake collaboration | Medium-high: one genuine failure-to-Issue-to-PR-to-merge trail exists, but the public history is still short |

## Final-round rubric: 70 points

| Official item | Points | Evidence IDs | Required proof, not aspiration | Current risk |
|---|---:|---|---|---|
| Presentation | 10 | E01, E04, E05, E06, E11 | One-sentence problem, live business-green/contract-red story, one readable diff, measured limits and no inflated terminology | Pending report/video |
| Utility | 15 | E04, E06, E08, E10 | A real regression caught, useful safe controls, a clean installation and at least one independent user's result | Critical until E06/E08/E10 |
| Demonstration | 10 | E03, E04, E05, E08 | Reproducible setup and one end-to-end capture/verify failure within the three-minute video | Public real-MySQL artifacts exist; the final three-minute video remains pending |
| Community expansion | 5 | E09, E10, E13, E14 | Release, contribution process, public feedback and community interaction with honest outcomes | Critical at the cutoff: project history had begun, but no release, external user or upstream response was recorded |
| Open-source appropriateness | 15 | E02, E08, E09, E11, E12, E13 | Reusable package, public source/history, clear license, dependency transparency, extensions and non-project-specific API | Public source/history/license/SBOM exist; stable distribution and external consumption remain pending |
| Functional test | 10 | E03, E04, E06, E07, E08 | Evaluator can reproduce core, negative, concurrency, privacy and malformed-input cases on the promised scope | Public Ubuntu CI has 50 normal tests plus one isolated consumer test; independent-user reproduction remains pending |
| License | 5 | E12 | SBOM and license scan match the shipped revision; notices and redistribution obligations are reviewed | Medium: the bound final-tag scan path is implemented in the integration candidate, but merge, the immutable final run, manual review and the required submission form remain |

## Mandatory submission ledger

The public contest page lists result report, source code and a demonstration video of up to three minutes for the August 27 submission ([official schedule](https://www.oss.kr/pages/2)). The organizer-supplied orientation and later [official submission guide](https://osscontest.kr/notice/39) add the following controls for this submission:

| Deliverable/control | Current status | Exit condition |
|---|---|---|
| One public source repository | `artifact-ready` | [Public repository](https://github.com/ym0506/routecontract) and immutable revisions exist; the exact final submitted tag is still pending. Private notes, generated drafts and unrelated ShardLens code are excluded by the source archive boundary |
| Result report, original file + PDF | `pending` | Body no longer than five pages, all numbers linked to E-items, both files open correctly |
| Public YouTube demonstration, at most 3:00 | `pending` | Duration checked after upload; URL works without login; captions and 1080p text legibility checked |
| SBOM | `artifact-ready` | The current public revision has a digest-identified aggregate JSON/XML Actions artifact. The final tag must regenerate and checksum those SBOMs, publish its sanitized point-in-time scan summary and complete the required manual license review. Neither artifact is a legal conclusion or zero-vulnerability claim |
| Source archive/checksum | `pending` | Archive rebuilds, checksum recorded, no credentials or private material |
| Deadline | active constraint | The official submission guide states **2026-08-27 18:00**; the package gate models the Korean contest cutoff as KST (+09:00). Submit by the internal 15:00 target; internal freeze is August 26 |

Missing report, source or video is an exclusion risk according to the supplied orientation. Do not wait for the final hour to discover an upload, visibility or codec problem.

## Claim promotion checklist

Before changing any `pending` or `verified-local` row to `artifact-ready`, require all of the following:

1. Public immutable revision or release tag.
2. Exact copy-paste command that exits with the claimed result.
3. JDK, OS, Docker engine, MySQL image/digest and ShardingSphere version where relevant.
4. Fixture/schema/configuration and reset behavior.
5. Raw machine-readable result plus a semantic verifier or test assertion.
6. Repetition/concurrency count when a stability claim is made.
7. Explicit limitation and supported boundary.
8. A link from the report statement back to this E-item.

Never promote a claim from a screenshot alone, an uncommitted temporary directory, a test name, an AI-generated review or a result that cannot be tied to the submitted revision.
