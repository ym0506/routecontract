# 2026 contest evidence matrix

Evidence snapshot status date: 2026-08-11 KST

Rubric source checked: 2026-08-21 KST

This is a dated historical snapshot. All status and current-evidence statements are evaluated at
the 2026-08-11 KST snapshot unless a later provenance date is stated. A later RC or stable version
in the containing tree does not update any row or prove publication. Event-dependent RC facts
belong in the validated fixed activation record; final stable evidence requires separate observed
proof.

This is a working audit ledger, not a score prediction. The [official 2026 contest page](https://www.oss.kr/pages/2) confirms the student division, the August 27 submission date, the report/source/three-minute-video deliverables, and the later functional and license verification stages. The detailed point allocation below reproduces the organizer's [August 20 judging notice](https://osscontest.kr/notice/41), the latest public scoring notice found as of 2026-08-21 KST. The evidence mappings and risk assessments are project strategy, not organizer-issued sub-scores.

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
| E05 | Canonical manifest and structural-attempt diff | Versioned JSON schema, deterministic record, verify mode, attempt-budget/data-source/callback/signature diagnostics, malformed/missing baseline behavior and sample raw JSON | `artifact-ready` | The immutable revision contains canonical MySQL-generated approved/candidate pairs plus expected RCM-coded diffs. Its public CI artifact has 15/15 passing manifest tests covering malformed, zero-event, over-limit and path-alias rejection, and the MySQL suite regenerates the examples byte-for-byte. This proves deterministic structural-attempt comparison for that revision, not SQL semantic equivalence or a stable-release format commitment. |
| E06 | Regression corpus and comparison | At least four route-risk mutations and two safe controls on real MySQL; expected business result; RouteContract result; `sql-show`/Audit/generic-tool comparison where applicable | `artifact-ready` | The public MySQL artifact reports 7/7 corpus cases plus the 1/1 datasource-proxy comparison. It covers six safe cases, five risk shapes, Audit-positive controls, strict versus `budgetOnly` policy sensitivity, the reduced/modified `1` versus `8` issue-inspired pair, and the same-budget `RCM301/RCM302` drift. Eight case signatures were each repeated 20 times. The datasource-proxy result supports a packaging-and-defaults claim, not categorical superiority; see [the bounded public evidence](public-ci-evidence.md). |
| E07 | Determinism and concurrent caller-operation isolation | At least 20 repeated captures with one structural execution signature plus at least 20 pairs of concurrently open caller capture scopes with zero mixed captures; exact environment and raw output | `artifact-ready` | The public MySQL result records `repetitions=20`, `uniqueSignatures=1`, `simultaneousPairs=20` and `mixedCaptures=0`. The historical `simultaneousPairs` marker means caller capture scopes were concurrently open; physical callback overlap was not forced or measured. This is bounded to the documented synchronous PreparedStatement scenario, not arbitrary async work. |
| E08 | Clean clone and Linux CI | Public clean-clone quick start; Ubuntu CI on claimed JDKs; no local cache assumptions; functional and privacy tests; immutable workflow link | `verified-local` | [Main run `31501026857`](https://github.com/ym0506/routecontract/actions/runs/31501026857) passed from a clean Ubuntu 24 checkout on Temurin 17: 45 submission-package tests, the default fail-closed installer suite, 50 normal Java/MySQL tests, verified SBOM generation and one isolated same-checkout generated-publication/MySQL consumer test. The [environment, raw XML, artifact digests and retention boundary](public-ci-evidence.md) are recorded. That snapshot workflow did not invoke `./scripts/quickstart-demo.sh`; later public main run [32440114569](https://github.com/ym0506/routecontract/actions/runs/32440114569) exercised it but did not prove a fresh Gradle home. The exact final stable revision must bind the clean-clone Quick Start with a fresh Gradle home in its release-evidence run, so this row remains `verified-local`. |
| E09 | Release and supply-chain identity | Public immutable stable release selected by the final manifest (planned `v0.1.0`), source/tag, checksums, generated artifacts, reproducible install coordinates or an explicit no-registry install path | `pending` | The no-registry installer requires an exact flat public-asset set, canonical coordinates, strict version/JAR/source structure and semantic binding of the sanitized supply-chain summary to the public SBOM/POM assets. The final package gate additionally binds that summary to the exact commit/tree, scanner/database lock, policy and published dependency lock. An RC remains prerelease evidence. The planned final is a new stable `v0.1.0`; if it fails a required post-publication verification, select a corrected immutable stable patch rather than replacing assets or retagging. The release workflow keeps environment/MySQL/consumer logs outside the public checksum under the immutable workflow-artifact digest and exact evidence allowlist. At this matrix's 2026-08-11 cutoff, no public release, final-tag run or checksum set was recorded; later RC facts belong only in a validated activation record. |
| E10 | Independent user evidence | At least one non-author follows the public quick start without private help; record environment, outcome, time/blockers and resulting issue/fix | `pending` | At this matrix's 2026-08-11 cutoff, no external RouteContract user or independent installation result was recorded. Do not substitute an AI review or the author's second machine for an external user. |
| E11 | Competitive analysis | Source-linked capability comparison; no "first/only" claim; one reproducible close-alternative comparison | `artifact-ready` | [Competitive analysis](competitive-analysis.md) provides the source-based landscape, and the [datasource-proxy experiment](empirical-comparison.md) ran in the same public MySQL job as RouteContract. It proves that a comparable narrow workflow is buildable and supports packaged-integration value, not categorical superiority. |
| E12 | License, notices, dependency inventory and SBOM | Project license, NOTICE where required, third-party licenses, dependency lock/inventory, generated SBOM, license/security scan and manual review notes | `verified-local` | Apache-2.0 `LICENSE`, `NOTICE`, `THIRD_PARTY.md`, pinned wrapper, locks, checksum metadata and CycloneDX generation are public. The candidate exact-revision gate checks aggregate/direct profile partition, JSON/XML pairs, generated POM/runtime closure, licenses and a pinned offline OSV database, and the release integration retains only a sanitized summary. The aligned local successor audit reports one time-bounded reviewed finding in the example/test profile, not zero vulnerabilities. This row still requires the reviewed changes to merge, a successful immutable final-tag run and the owner's manual license/NOTICE review. |
| E13 | Project collaboration and management trail | Public GitHub issues, focused branches/PRs, specification-first discussion, CI, account-attributed review records, linked merges and milestones | `artifact-ready` | The public history begins with one root commit. The first clean-CI failure is linked to [Issue #5](https://github.com/ym0506/routecontract/issues/5); [PR #6](https://github.com/ym0506/routecontract/pull/6) contains a focused checksum-only fix, a review comment posted by the repository-owner account, a green build and Dependency Review, and a linked merge. Milestone `v0.1.0` and Issues #7-#11 were public tracking records at this snapshot. This is an early single-maintainer trail and contains no independent review claim. |
| E14 | Upstream/community question | A concise RouteContract-specific design or integration question to the relevant community, public response if any, and honest disposition | `pending` | The related upstream PR [#39112](https://github.com/apache/shardingsphere/pull/39112), opened by GitHub user `Develop-KIM`, was closed without merge after substantive review. `Develop-KIM` is not the participant's account, so this is external problem-analysis history rather than participant prior-work or community-credit evidence. It is not upstream acceptance of RouteContract, and no RouteContract-specific upstream question or endorsement exists. |

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

## 1차 평가(서면): 30 points

The August 20 judging notice allocates six points to each of five criteria. The table maps what a reviewer must be able to click or reproduce; it does not award points internally.

| Official item | Evidence IDs | What the submission must make verifiable | Current risk |
|---|---|---|---|
| 프로젝트 구조 및 코드 완성도 — 6 | E02, E03, E05, E06, E07, E08 | Readable code and useful comments, rational structure, purpose-fit behavior, isolated 5.5.3 adapter, fail-closed lifecycle, deterministic model, real-MySQL coverage and clean build | Medium-low at the cutoff: public Linux/MySQL evidence existed; a tagged release and independent install had not been recorded |
| 오픈소스 프로젝트로의 발전 가능성 — 6 | E09, E10, E13, E14 | Public release, usable contribution path, evidence-gated roadmap, independent install feedback, visible issue/PR discussion and an upstream/community touchpoint | Critical at the cutoff: real Issue/PR history had begun, but a release, external user and upstream contact had not been recorded |
| 개발 문서의 구체성 — 6 | E01, E05, E06, E08, E11, E12 | Concrete, purpose-fit and easy-to-understand problem/scope, quick start, architecture/event semantics, reproducible evidence, limits, license/SBOM and comparison | Medium-low: runnable docs and public CI evidence exist; stable-release and external-user documentation remain |
| 프로젝트 혁신성 — 6 | E01, E04, E06, E11 | Demonstrated gap between business assertions and observed execution, technical capability, appropriate current-technology use, credible prior-art comparison and a reusable solution beyond one demo | Medium: the differentiating corpus and generic-tool comparison are public, but the contribution remains a bounded workflow integration rather than a new observation primitive |
| 프로젝트 협업 및 관리체계 — 6 | E13 plus links to E01-E12 | Issues, reviews, pull requests, commits and community activity expose the management method; single-maintainer review remains account-attributed and no independent review is implied | Medium-high: one public failure-to-Issue-to-PR-to-merge trail exists, but the public history is still short |

## 2차 평가(발표): 70 points

| Official item | Points | Evidence IDs | Required proof, not aspiration | Current risk |
|---|---:|---|---|---|
| 작품발표(PT) | 10 | E01, E04, E05, E06, E11 | The presentation must explain the problem, evidence, limits, structural-attempt comparison and manifest diff clearly | Pending report/video and later presentation rehearsal |
| 활용성 | 15 | E04, E05, E06, E08, E09, E10 | Whether the submitted work can be used or applied is supported by a caught regression, reviewed manifest workflow, useful controls, clean installation, stable distribution and bounded independent-user evidence | At the cutoff, E04–E06 were artifact-ready; E08 still lacked the public clean-clone Quick Start, and E09/E10 were pending |
| 작품 데모(완성도) | 10 | E03, E04, E05, E08 | A systematic demo faithfully expresses the product, reproduces an end-to-end capture/verify failure and supports stable answers to evaluator questions; this is broader than the submission video alone | Public real-MySQL artifacts exist; the final three-minute video and evaluator rehearsal remain pending |
| 커뮤니티 확장 가능성 | 5 | E09, E10, E13, E14 | Quality management, development methodology and roadmap are visible; public feedback, community participation and intellectual-asset sharing have honest outcomes | Critical at the cutoff: project history had begun, but no release, external user or upstream response was recorded |
| 오픈소스SW 적절성 | 15 | E02, E03, E06, E08, E09, E11, E12 | Other open-source software is adopted appropriately for the project and the integrated system operates normally, with source, dependency, license and compatibility boundaries documented | Public source, SPI activation, real-MySQL integration, comparison, license and SBOM evidence exist; stable distribution and the two owner license/NOTICE reviews remain pending |
| 기능테스트 | 10 | E03, E04, E06, E07, E08 | The evaluator can run core, negative, concurrency, privacy and malformed-input paths without unintended errors, bugs, hangs or abnormal termination on the promised scope | Public Ubuntu CI has 50 normal tests plus one isolated consumer test; later main run 32440114569 exercised the Quick Start without proving a fresh Gradle home, while the final stable exact-revision release-evidence run must bind the clean-clone Quick Start with a fresh home |
| 라이선스 검증 | 5 | E12 | SBOM and license scan match the shipped revision; notices, conflicts and redistribution obligations are reviewed | Medium: the bound final-tag scan path is implemented in the integration candidate, but merge, the immutable final run, manual review and the required submission form remain |

The second round applies only to first-round passers. The organizer calculates the final score by combining the first-round 30 points and second-round 70 points.

## Mandatory submission ledger

The public contest page lists result report, source code and a demonstration video of up to three minutes for the August 27 submission ([official schedule](https://www.oss.kr/pages/2)). The organizer-supplied orientation and later [official submission guide](https://osscontest.kr/notice/39) add the following controls for this submission:

| Deliverable/control | Current status | Exit condition |
|---|---|---|
| One public source repository | `artifact-ready` | [Public repository](https://github.com/ym0506/routecontract) and immutable revisions exist; the exact final submitted tag is still pending. Private notes, generated drafts and unrelated ShardLens code are excluded by the source archive boundary |
| Result report, original file + PDF | `pending` | Body no longer than five pages; every measured-claim category used in the reader-facing report appears in the crosswalk below; the exact repository, CI, Release and video URLs are visible in the report; the package manifest's structured public-evidence record binds the final revision/tag; both files open correctly |
| Public YouTube demonstration, at most 3:00 | `pending` | Duration checked after upload; URL works without login; captions and 1080p text legibility checked |
| SBOM | `artifact-ready` | The current public revision has a digest-identified aggregate JSON/XML Actions artifact. The final tag must regenerate and checksum those SBOMs, publish its sanitized point-in-time scan summary and complete the required manual license review. Neither artifact is a legal conclusion or zero-vulnerability claim |
| Source archive/checksum | `pending` | Archive rebuilds, checksum recorded, no credentials or private material |
| Deadline | active constraint | The official submission guide states **2026-08-27 18:00**; the package gate models the Korean contest cutoff as KST (+09:00). Submit by the internal 15:00 target; internal freeze is August 26 |

Missing report, source or video is an exclusion risk according to the supplied orientation. Do not wait for the final hour to discover an upload, visibility or codec problem.

## Reader-facing report claim crosswalk

The report uses descriptive Korean labels instead of inserting audit IDs into every paragraph. The table below is the explicit crosswalk; a matching E-ID only identifies the evidence package and does not promote a `pending` or `verified-local` row. The report's `공개 증거 gate` is an owner-supplied visible prose slot, not a structured evidence object. Final packaging separately requires the exact repository, CI, Release and video URLs to be present in the DOCX and binds revision/tag/run/Release facts through the package manifest's structured public-evidence record.

`개발 장비`, `개발 보조 AI`, `선행 작업 경계` and `개발 소감` are identity/disclosure/provenance/owner-voice blocks governed by closed static/private content plus participant-attestation gates rather than E-ID measured-evidence claims. `ORIGIN_AND_PRIOR_WORK.md` is a participant provenance declaration, not independent proof that the ShardLens design was unimplemented or that no application code was copied.

| Reader-facing report block | Evidence IDs | Evidence boundary carried into the report |
|---|---|---|
| 한 문장 소개; 사용자·검출 공백; 해결 방식 | E02, E04, E05 | Exact 5.5.3 Hook adapter, observed-attempt regression and approved/candidate manifest workflow; not a complete route plan |
| 검증된 효과; 실제 MySQL business-green / contract-red; 시연; 재현한 적용 결과 | E04, E05, E06, E08 | Same returned row with `1→2`, RCM-coded structural diff and intentional non-zero gate. At the 2026-08-11 snapshot E08 remained `verified-local`; later public main run [32440114569](https://github.com/ym0506/routecontract/actions/runs/32440114569) exercised the documented Quick Start, while the exact final submitted revision must still rerun and bind it. The standalone consumer is a separate one-success-path package check |
| 공개 문제 근거 | E01, E04 | The issue-inspired fixture is reduced and modified; it is not an exact reproduction of the whole upstream environment |
| 언어·대상; 빌드·검증; 재현과 패키징; 설치·릴리스; stable 배포 후 4단계 적용 흐름 | E02, E08, E09, E12 | Version/runtime boundary, clean build/SBOM path and conditional stable-release installation; E09 must be complete before the release wording becomes a final fact |
| 관측·계약 흐름; 상관관계·Fail-closed; 정보 경계; Operation 단위 관측 계약; 승인 manifest와 structural manifest diff; 활용 경계 | E02, E03, E05, E07, E08 | Named-operation correlation, fail-closed lifecycle, minimized-but-not-anonymized fields and deterministic manifest comparison within the explicitly denied route-plan/commit/business-success boundary; E08 also carries the clean-clone Quick Start privacy checks |
| 재현성·operation 격리 | E06, E07 | Eight cases repeated 20 times and 20 concurrently open caller-operation pairs; no claim of forced physical callback overlap or arbitrary async support |
| 차별성 | E11 | A reproducible datasource-proxy comparison supports workflow-packaging value, not exclusive observability or categorical superiority |
| 오픈소스SW 조합; 현재 한계; 라이선스 검토 상태 | E02, E08, E11, E12 | SPI/Testcontainers/thin-JAR/SBOM roles, exact scope, the non-bundled JTS/Mahout boundary and the unresolved MySQL OCI owner review without implying legal clearance |
| 공개 증거 gate | E08, E09, E12, E13, E14 | Visible exact public URLs plus the separately structured package evidence, including any qualifying upstream/community package record; no completion claim before the final tag gates pass |
| 외부 검증 | E10 | Exactly one generated `rc_only` or `zero` sentence from the cutoff enumeration; an RC result is not stable validation or adoption |
| 품질관리·발전 로드맵 | E13, E14 | Public issue/PR/CI history and a proposed roadmap; upstream/community credit is used only when a qualifying public record exists |

## Claim promotion checklist

Before changing any `pending` or `verified-local` row to `artifact-ready`, require all of the following:

1. Public immutable revision or release tag.
2. Exact copy-paste command that exits with the claimed result.
3. JDK, OS, Docker engine, MySQL image/digest and ShardingSphere version where relevant.
4. Fixture/schema/configuration and reset behavior.
5. Raw machine-readable result plus a purpose-built verifier or test assertion.
6. Repetition/concurrency count when a stability claim is made.
7. Explicit limitation and supported boundary.
8. An explicit E-ID mapping in the reader-facing crosswalk for every measured report-claim category, visible exact public URLs in the report, and the exact final revision/tag/run/Release binding in the package manifest's structured public-evidence record.

Never promote a claim from a screenshot alone, an uncommitted temporary directory, a test name, an AI-generated review or a result that cannot be tied to the submitted revision.
