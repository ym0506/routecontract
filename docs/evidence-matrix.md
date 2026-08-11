# 2026 contest evidence matrix

Status date: 2026-08-11 KST

This is a working audit ledger, not a score prediction. The [official 2026 contest page](https://www.oss.kr/pages/2) confirms the student division, the August 27 submission date, the report/source/three-minute-video deliverables, and the later functional and license verification stages. The detailed point allocation below comes from the organizer-supplied July 23 orientation material retained with the submission source archive.

## Status vocabulary

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
| E02 | 5.5.3 adapter and activation proof | Tagged source permalink for the `SQLExecutionHook` provider, service descriptor, fail-closed activation/preflight test and supported compatibility-artifact versions | `verified-local` | Provider, service descriptor, compatibility preflight and fail-closed lifecycle exist; preflight checks that `infra-executor` and `infra-spi` each report 5.5.3 and that exactly one RouteContract provider is discovered, not that every dependency-graph artifact has the same version. The latest uncached core run reports 36 tests total, including 3 preflight tests, with 0 failures. The XML remains ephemeral until linked to an immutable public revision and CI run. |
| E03 | Single-data-source MySQL control | Real MySQL + ShardingSphere-JDBC 5.5.3 command, one business assertion, one complete capture and one observed attempt/data-source result | `verified-local` | `OperationCorrelationMySqlTest` reports 5/5 passing against digest-pinned MySQL 8.4.11, including the one-attempt control. A public clean-run CI link is pending. |
| E04 | Business-green / contract-red demonstration | Same returned business result for control and mutation; mutation exceeds a declared observed-attempt or data-source budget; raw and summarized result | `verified-local` | The one-command equality/range demo prints `businessResult=UNCHANGED`, observed attempts `1->2`, `POLICY_VIOLATION` and blocking codes `RCM201,RCM202`; assertions also verify expansion from `ds_1` to both data sources. A separate file-based task reads the resulting approved/candidate pair and exits non-zero through an uncaught contract assertion. The issue-#38456-inspired reduced and modified pair returns `COUNT=1` for both forms while observing `1` versus `8` attempts; it is not an exact upstream reproduction. Public immutable artifacts are pending. |
| E05 | Canonical manifest and semantic diff | Versioned JSON schema, deterministic record, verify mode, added/removed/change summary, malformed/missing baseline behavior and sample raw JSON | `verified-local` | Core includes strict streaming codec, explicit aliases, atomic candidate-only write, strict/budget-only policy, stable RCM-coded diff and CI assertions. Manifest tests report 15/15 passing, including malformed, zero-event, over-limit and path-alias rejection. The repository now contains an actual MySQL-generated canonical approved/candidate pair plus expected diff; the MySQL test regenerates and compares the bytes, and the intentional gate task exits `1` with `RCM201/RCM202`. A public CI artifact is still pending. |
| E06 | Regression corpus and comparison | At least four route-risk mutations and two safe controls on real MySQL; expected business result; RouteContract result; `sql-show`/Audit/generic-tool comparison where applicable | `verified-local` | MySQL corpus reports 7/7 passing: six safe cases (one equality baseline plus five syntactic controls), five risk shapes including strategy removal, Audit-positive controls and the issue-#38456-inspired reduced/modified `1` versus `8` pair. The latter is not an exact upstream reproduction. The same-attempt/same-data-source table-strategy-removal case proves a strict manifest failure with blocking structural codes `RCM301/RCM302`; a separate additional-filter/predicate-reorder fixture returns the same rows in that bounded test and demonstrates strict blocking versus non-blocking `budgetOnly` review on real MySQL, without claiming general SQL semantic equivalence. Eight case signatures were each repeated 20 times. A separate datasource-proxy comparison passes 1/1 and measures outer callbacks `1->1`, inner physical callbacks `1->2` and RouteContract attempts `1->2`; public artifacts remain pending. |
| E07 | Determinism and concurrent caller-operation isolation | At least 20 repeated captures with one semantic manifest plus at least 20 pairs of concurrently open caller capture scopes with zero mixed captures; exact environment and raw output | `verified-local` | Local MySQL test output reports `repetitions=20`, `uniqueSignatures=1`, `simultaneousPairs=20`, `mixedCaptures=0`. Here `simultaneousPairs` is the historical output-marker name: the test opens caller capture scopes concurrently but does not force or measure physical hook-callback overlap. This is a bounded local test of the synchronous PreparedStatement scenario, not proof for arbitrary async work or callback simultaneity. Commit a canonical runner/result before report use. |
| E08 | Clean clone and Linux CI | Public clean-clone quick start; Ubuntu CI on claimed JDKs; no local cache assumptions; functional and privacy tests; immutable workflow link | `verified-local` | CI workflow and a standalone published-JAR consumer exist. The release workflow additionally derives a fixed, revision-bound `test-summary.txt` from JUnit XML and refuses any result other than the exact seven-suite, 50-test, zero-failure/error/skip set; its exact format cannot carry test names, timings, hostnames, paths, ports, SQL or captured output. The same-checkout publication script passed 1/1 locally using an isolated temporary Maven repository, its own dependency locks/checksums, SPI auto-discovery and real MySQL 8.4.11; this is packaging evidence, not external adoption. The final-release path is implemented to install only the exact checksummed public assets into an explicit empty repository before running that consumer, but no public Ubuntu release-evidence run or independent clean clone exists yet. |
| E09 | Release and supply-chain identity | Public `v0.1.0` release, source/tag, checksums, generated artifacts, reproducible install coordinates or an explicit no-registry install path | `pending` | The no-registry installer requires an exact flat public-asset set, the canonical `io.github.ym0506.routecontract` group, a stable POM coordinate, unfolded JAR manifest identity, canonical package namespace, JAR structure and a `SHA256SUMS` containing exactly the public payloads; its fail-closed deterministic suite passes locally, including no implicit `~/.m2` write, no symlink target and no overwrite. The release workflow stages and checksums public payloads first, consumes those exact assets in real MySQL, and keeps environment/MySQL/consumer logs outside the public checksum under the immutable workflow-artifact digest and exact evidence allowlist. No public repository release, final-asset workflow run or checksum set exists. |
| E10 | Independent user evidence | At least one non-author follows the public quick start without private help; record environment, outcome, time/blockers and resulting issue/fix | `pending` | No external RouteContract user or independent installation result exists. Do not substitute an AI review or the author's second machine for an external user. |
| E11 | Competitive analysis | Source-linked capability comparison; no "first/only" claim; one reproducible close-alternative comparison | `verified-local` | [Competitive analysis](competitive-analysis.md) provides the source-based landscape, and [the datasource-proxy experiment](empirical-comparison.md) is reproducible against the same real-MySQL mutation. It proves packaged integration value, not categorical superiority; public immutable output is still pending. |
| E12 | License, notices, dependency inventory and SBOM | Project license, NOTICE where required, third-party licenses, dependency lock/inventory, generated SBOM, license/security scan and manual review notes | `verified-local` | Apache-2.0 `LICENSE`, `NOTICE`, `THIRD_PARTY.md`, pinned wrapper, root/module/standalone dependency locks, root/standalone SHA-256 verification metadata and CycloneDX generation exist. The focused `prepareVerifiedSbom` run exited `0`: aggregate/library-direct/MySQL-direct JSON/XML contain `154/48/153` dependency components and `3/1/2` exact-group first-party components. Separate verify-only assertions exited `0`; all first-party components carry Apache-2.0 plus its official URL, Connector/J 26.7.0 carries `GPL-2.0-only WITH Universal-FOSS-exception-1.0`, and each MySQL-example BOM contains exactly one `excluded`, `GPL-2.0-only` MySQL 8.4.11 container at digest `b3b90af2…fd3fb` with one dependency edge, while the library-only BOM contains neither MySQL component. All three XML files validate against the CycloneDX 1.6 XSD. The finalizer refuses conflicting first-party, Connector/J or container metadata; other third-party metadata stays plugin-generated. An SBOM is an inventory, not a security scan or legal conclusion; release-revision retention, vulnerability/license scanning and final manual/legal review remain pending. |
| E13 | Individual project-management trail | Real GitHub issues, focused branches/PRs, specification-first discussion, CI, line-by-line self-review, linked merges and milestones | `pending` | The repository has no registered public remote/Issue/PR history yet. Local file creation or artificial/backdated activity does not satisfy this evidence. |
| E14 | Upstream/community question | A concise RouteContract-specific design or integration question to the relevant community, public response if any, and honest disposition | `pending` | The related upstream PR [#39112](https://github.com/apache/shardingsphere/pull/39112), opened by GitHub user `Develop-KIM`, was closed without merge after substantive review. Until participant ownership of that account is confirmed, it is external problem-analysis history rather than participant prior-work or community-credit evidence. It is not upstream acceptance of RouteContract, and no RouteContract-specific upstream question or endorsement exists. |

### Local verification snapshot

The following facts are useful for development triage but are not yet final submission evidence:

- `RouteContractTest`: 18 tests, 0 failures.
- `ShardingSphere553PreflightTest`: 3 tests, 0 failures.
- `ObservedExecutionManifestTest`: 15 tests, 0 failures.
- `OperationCorrelationMySqlTest`: 5 tests, 0 failures.
- `ObservedExecutionRegressionCorpusMySqlTest`: 7 tests, 0 failures.
- `FailureBoundaryMySqlTest`: 1 test, 0 failures.
- `DataSourceProxyComparisonMySqlTest`: 1 test, 0 failures.
- Root build total: 50 tests, 0 failures; isolated published-JAR consumer: 1 test, 0 failures.
- Canonical command `./gradlew --no-daemon --no-build-cache clean check assemble prepareVerifiedSbom`: `BUILD SUCCESSFUL` in 1 minute 10 seconds on the author's Java 17.0.15/macOS/Docker Engine 29.2.1 environment. The run compiled with warnings-as-errors, executed all 50 normal tests, assembled the library artifacts, generated aggregate/direct JSON and XML SBOMs, and verified Apache-2.0 first-party component metadata with counts `3/1/2` for aggregate/library/MySQL BOMs. Container startup dominates wall time; individual JUnit suite durations must not be presented as end-to-end runtime.
- `./scripts/verify-standalone-consumer.sh` independently resolved the locally published Maven coordinate, auto-discovered the packaged SPI provider and passed 1/1 real-MySQL test.
- `python3 -m unittest discover -s scripts/tests -v` passed the default fail-closed installer suite; the opt-in final-asset MySQL test separately passed against stable Release-shaped assets generated from the local build. Neither result is external adoption.
- `./scripts/demo-manifest-ci-failure.sh` intentionally exited `1` after printing `RCM201` and `RCM202`; this red task is isolated from normal `test`/`check` and proves that the checked-in candidate propagates an uncaught build failure.

These files are normally ignored build output, can be overwritten by a later run and do not identify an immutable Git revision. Promote them into E02-E07 only through a canonical evidence command and a small committed summary that records revision, JDK, Docker/MySQL image digest, ShardingSphere version and limitations.

## First-round rubric: 30 points

The orientation allocates six points to each item. The table maps what a reviewer must be able to click or reproduce; it does not award points internally.

| Official item | Evidence IDs | What the submission must make verifiable | Current risk |
|---|---|---|---|
| Code structure and completeness — 6 | E02, E03, E05, E06, E07, E08 | Small public API, isolated 5.5.3 adapter, fail-closed activation, complete lifecycle, deterministic model, real-MySQL coverage and clean build | Medium: local product gates pass; public Linux evidence and immutable artifacts remain |
| Open-source growth — 6 | E09, E10, E13, E14 | Public release, usable contribution path, independent install feedback, visible issue/PR discussion and an upstream/community touchpoint | Critical: all four are pending |
| Documentation — 6 | E01, E05, E06, E08, E11, E12 | Problem and scope, five-minute quick start, architecture/event semantics, reproducible evidence, limits, license/SBOM and comparison | Medium: runnable docs and local comparison exist; public immutable evidence does not |
| Innovation — 6 | E01, E04, E06, E11 | Demonstrated gap between business assertions and observed execution, a credible prior-art comparison and a reusable solution beyond one demo | Medium: differentiating corpus and generic-tool comparison run locally; public evidence remains |
| Individual project management — 6 | E13 plus links to E01-E12 | Issues precede work, PRs are scoped, commits explain decisions, CI and self-review are visible, no fake collaboration | Critical until the repository is public and real history begins |

## Final-round rubric: 70 points

| Official item | Points | Evidence IDs | Required proof, not aspiration | Current risk |
|---|---:|---|---|---|
| Presentation | 10 | E01, E04, E05, E06, E11 | One-sentence problem, live business-green/contract-red story, one readable diff, measured limits and no inflated terminology | Pending report/video |
| Utility | 15 | E04, E06, E08, E10 | A real regression caught, useful safe controls, a clean installation and at least one independent user's result | Critical until E06/E08/E10 |
| Demonstration | 10 | E03, E04, E05, E08 | Reproducible setup and one end-to-end capture/verify failure within the three-minute video | One-command real-MySQL demo passes locally; public artifact and final video remain pending |
| Community expansion | 10 | E09, E10, E13, E14 | Release, contribution process, public feedback and community interaction with honest outcomes | Critical: no release/user/upstream response yet |
| Open-source appropriateness | 10 | E02, E08, E09, E11, E12, E13 | Reusable package, public source/history, clear license, dependency transparency, extensions and non-project-specific API | License base exists; distribution/history pending |
| Functional test | 10 | E03, E04, E06, E07, E08 | Evaluator can reproduce core, negative, concurrency, privacy and malformed-input cases on the promised scope | Local 50-test root suite plus one isolated published-JAR consumer pass; public Linux and independent clean clone remain pending |
| License | 5 | E12 | SBOM and license scan match the shipped revision; notices and redistribution obligations are reviewed | Medium-high: local SBOM succeeds, but release-revision review and required submission form remain |

## Mandatory submission ledger

The public contest page lists result report, source code and a demonstration video of up to three minutes for the August 27 submission ([official schedule](https://www.oss.kr/pages/2)). The organizer-supplied orientation adds the following controls for this submission:

| Deliverable/control | Current status | Exit condition |
|---|---|---|
| One public source repository | `pending` | Evaluator-accessible URL at the exact submitted revision; private notes and unrelated ShardLens code excluded |
| Result report, original file + PDF | `pending` | Body no longer than five pages, all numbers linked to E-items, both files open correctly |
| Public YouTube demonstration, at most 3:00 | `pending` | Duration checked after upload; URL works without login; captions and 1080p text legibility checked |
| SBOM | `verified-local` | Verified aggregate JSON/XML generated with component-level Apache-2.0 assertions; regenerate, verify, checksum and submit from the final public release revision. This inventory is not a security scan or legal conclusion |
| Source archive/checksum | `pending` | Archive rebuilds, checksum recorded, no credentials or private material |
| Deadline | active constraint | Submit before **2026-08-27 18:00 KST**; internal freeze is August 26 |

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
