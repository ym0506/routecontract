# Award-oriented development plan: August 11-27, 2026

This is an execution plan for one student developer with substantial available time. It cannot guarantee an award. Its purpose is to maximize the amount of reviewer-verifiable evidence before the submission deadline while preventing a technically interesting but unfinished prototype.

The [official contest schedule](https://www.oss.kr/pages/2) and organizer orientation require the result report, source and a demonstration video of up to three minutes by August 27. The later [official submission guide](https://osscontest.kr/notice/39) sets the exact cutoff at **2026-08-27 18:00**; the package gate models this Korean contest cutoff as KST (+09:00). Internal feature freeze is one day earlier.

## Outcome and scope freeze

By August 26, the public repository must let a new Java developer run one command and see both of these outcomes on real MySQL:

1. a control application operation returns its expected business result and satisfies its approved observed-execution contract;
2. a functionally acceptable mutation returns the expected business result but fails because the observed physical-attempt manifest or budget expanded.

Everything else is secondary. The v0.1 scope remains ShardingSphere-JDBC 5.5.3, synchronous `PreparedStatement`, Java 17/21 only if both are verified, JUnit 5 and MySQL Testcontainers. Dashboard, Java Agent, Spring Boot starter, batch, arbitrary application async propagation, ShardingSphere-Proxy, automatic topology discovery, multiple ShardingSphere versions and AI features are cut.

## Capacity assumption

The plan assumes three adjustable focused blocks rather than a guaranteed number of hours:

- Build block: core implementation and focused tests.
- Evidence block: real-MySQL reproduction, comparison, clean-room verification and artifacts.
- Public-work block: issue/PR review, documentation, release, report and video.

At high availability this is roughly 8-10 focused hours per day. If actual capacity is lower, remove P2 work first; never trade away a P0 verification gate to add features.

| Priority | Must finish |
|---|---|
| P0 | Activation/preflight, correlation invariants, canonical manifest record/verify/diff, four-risk/two-control MySQL corpus, clean clone, Linux CI, privacy tests, license/SBOM, report and video |
| P1 | One generic-tool comparison, one external clean install, `v0.1.0` release/checksums, upstream/community question, polished bilingual quick start |
| P2 | Extra assertion syntax, more corpus cases, Java 21 if not already a public claim, package-registry publication, performance measurement |

## Go/no-go gates

| Gate | Deadline | Pass condition | If it fails |
|---|---|---|---|
| G0: observation boundary | Aug 12, 18:00 | Service provider activation is checked; single and fan-out MySQL operations produce complete captures; callback failures/incompleteness fail closed | If no reliable fan-out observation, stop RouteContract and do not submit a query-counter shell |
| G1: isolation | Aug 13, 23:00 | 20 repeated captures have one structural signature; 20 concurrent control/fan-out pairs have zero mixed captures; worker reuse and raw child-thread behavior are explicit | Narrow the public scope to the proven boundary. If concurrent ShardingSphere worker attribution itself is unreliable, no-go |
| G2: product loop | Aug 15, 23:00 | `record -> approved JSON -> verify -> actionable structural manifest/attempt diff with stable RCM codes` works from a documented JUnit or CLI path; missing/malformed baselines fail safely | Cut every optional feature. If deterministic record/verify cannot work, reconsider submission because the central product claim is absent |
| G3: credible corpus | Aug 18, 18:00 | At least four route-risk mutations and two safe controls run on the same fixture; one Audit comparison and one close generic alternative are documented without inflated claims | Reduce breadth but retain at least two materially different risks plus two controls; never invent a six-case result |
| G4: open-source usability | Aug 20, 23:00 | Public repository, clean Ubuntu run, claimed JDK matrix green, license/third-party inventory and draft SBOM; quick start succeeds from a clean directory | Feature freeze immediately. Fix installation, CI and licensing before any polish |
| G5: independent use | Aug 22, 23:00 | At least one non-author attempts the exact quick start and creates or confirms a public feedback record; the latest activated RC assets/checksums are accessible | Report "no external validation" if none occurs. Use a recorded clean VM as reproducibility evidence but never call it an external user |
| G6: submission story | Aug 24, 23:00 | Five-page report draft and a <=3:00 rough cut contain only E-item-backed claims; every figure is legible and reproducible | Freeze code except release blockers; remove weak claims/features rather than compressing unverifiable material |
| G7: release freeze | Aug 26, 18:00 | Submitted revision tagged, archive/SBOM/checksums fixed, clean verification passes, original report/PDF/video links all open | No feature changes. Only fix exclusion-level packaging or factual errors, then regenerate all affected checksums/artifacts |

## Daily plan

| Date | Engineering outcome | Evidence/public outcome | Stop condition for the day |
|---|---|---|---|
| Aug 11 | Freeze specification and terms; finish provider activation/preflight; make local unit and two-data-source MySQL suites green | Publish origin/prior-work boundary; create real milestone and issues for E01-E14; initial commit must honestly import today's work without fabricated history | No API expansion until the failure/completeness semantics are reviewed |
| Aug 12 | Harden stale/late event handling, duplicate finish, collector-fault containment and privacy tests | PR 1: specification + adapter + preflight + control/fan-out evidence; run G0 | If G0 fails, decide no-go before investing in UI/docs |
| Aug 13 | Finish operation correlation and bounded concurrency tests; test Java thread inheritance and ShardingSphere executor reuse separately | PR 2: correlation invariants and exact limitation statement; archive canonical 20x/20-pair result | Do not generalize to `@Async` or arbitrary executors |
| Aug 14 | Implement versioned canonical model and deterministic JSON writer/reader; prevent operation names from becoming file paths | Issue and draft PR 3 with schema example, compatibility rules and missing/malformed baseline tests | No cosmetic JSON features until byte-for-byte determinism passes |
| Aug 15 | Implement approved-baseline record/verify and structural added/removed/changed diff; make violations actionable | Merge PR 3 after self-review and CI; capture a 20-second demo flow; run G2 | If record/verify is not end-to-end, cut comparison work and finish it |
| Aug 16 | Add two safe controls and two route-risk mutations on one deterministic fixture | PR 4 begins with the expected business oracle and route-contract oracle for every case | Each case must state why it is a distinct risk, not just another SQL spelling |
| Aug 17 | Reach at least four risk mutations and two controls; add built-in Audit comparison | Commit raw measured results through a reproducible evidence command; table maps every number to a test | If a case is flaky or poorly explained, remove it rather than count it |
| Aug 18 | Add one close alternative comparison, preferably datasource-proxy or Sniffy, on the same narrow scenario | Finish E06 and E11; run G3; publish comparison limitations | Never claim the generic tool is incapable when custom wiring could reproduce behavior |
| Aug 19 | Linux CI, JDK 17 and 21 only if claimed, dependency/cache-independent setup, repeated clean test | PR 5: reproducibility workflow; document image and dependency versions/digests | No new features after today unless a P0 gate requires them |
| Aug 20 | Clean-clone quick start, packaging, source archive, license/NOTICE/third-party inventory and SBOM generation | E08/E12 draft artifacts; public CI permalinks; run G4 | A green local machine is insufficient; fix CI/install first |
| Aug 21 | Preserve the failed `v0.1.0-rc1` attempt; cut `v0.1.0-rc2` only after the focused release-evidence fix and full verification | E09 candidate; invite targeted reviewers only after the RC2 activation gate | Do not move the RC1 tag, call an RC stable, or fabricate download/adoption numbers |
| Aug 22 | Fix only blockers found by independent install/review | Record E10 environment, success/failure, blocker, issue and resulting commit; post a concise RouteContract-specific upstream question; run G5 | No response is a valid outcome; do not chase endorsement or make acceptance deadline-critical |
| Aug 23 | Finalize architecture, quick start, limitations, security/privacy and contribution paths | Close documentation issues through normal PRs; prepare report figures from E01-E14 | Every screenshot/table must have a source revision and generation path |
| Aug 24 | Fix P0 defects only; rerun full clean suite | Complete five-page report draft and first <=3:00 video cut; run G6 | Remove any claim that cannot be traced to an artifact-ready E-item |
| Aug 25 | Release candidate verification and evaluator rehearsal on a clean environment | Independent proofreading; captions, fonts, audio, links and QR codes; generate report PDF from final original | If demo timing exceeds 3:00, remove exposition rather than speeding past readable output |
| Aug 26 | Tag final `v0.1.0`; regenerate SBOM, archives and checksums from that exact revision | Run all E-item checks; freeze original/PDF/video/source URLs at 18:00; run G7 | After freeze, no dependency or source change without regenerating every derived artifact |
| Aug 27 | Exclusion-risk fixes only | Submit by 15:00 KST; download the submitted files, replay video, clone URL and record confirmation before the 18:00 cutoff | Do not use the final hour for ordinary polishing |

## Individual GitHub workflow

The contest gives six first-round points to individual project-management discipline. A solo project can show good discipline, but it must not imitate a team that does not exist. GitHub describes Issues as a way to track ideas, feedback, tasks and bugs ([official Issues documentation](https://docs.github.com/en/issues/tracking-your-work-with-issues/about-issues)); pull requests provide discussion and review around a proposed change ([official pull-request documentation](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests)). Use those records for real decisions.

### Issue rule

Open one issue for each coherent user-visible outcome, not one issue per commit and not one mega-issue for the whole contest. Each issue contains:

1. problem and user;
2. exact supported boundary and non-scope;
3. acceptance test or artifact;
4. privacy/license effect;
5. evidence ID;
6. go/no-go or rollback condition.

Suggested labels are `type:feature`, `type:bug`, `type:docs`, `evidence`, `privacy`, `license`, `release-blocker` and `good-first-issue`. Add `good-first-issue` only when an outsider could actually complete it from public instructions.

### Branch and PR rule

- Branch from a green `main` using names such as `feat/manifest-diff`, `test/mysql-route-corpus` and `docs/quickstart`.
- Open a draft PR after the specification/failing test is visible, not after all work is silently finished.
- Link the issue with a supported closing keyword so the relationship is visible ([GitHub linking documentation](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue)).
- Keep one reviewable concern per PR. Six to eight real PRs are stronger evidence than dozens of artificial micro-PRs.
- Let CI finish, inspect the complete diff, run the evidence command and leave a dated self-review note before merge.
- The author cannot provide independent review of their own work. Label it **self-review**. Credit external review only when another person actually reviewed it.
- Do not backdate commits, split completed work to simulate duration, create fake accounts/reviews or rewrite history to manufacture activity.

Suggested PR sequence:

1. Adapter, preflight and lifecycle semantics.
2. Correlation, privacy and concurrency invariants.
3. Canonical manifest, record/verify and structural manifest/attempt diff with stable RCM codes.
4. MySQL corpus and built-in Audit comparison.
5. CI, clean-clone evidence and generic-tool comparison.
6. Licensing, SBOM, packaging and release candidate.
7. External-feedback fixes and documentation.
8. Final release/submission corrections only if genuinely needed.

### Commit rule

Use small causal commits such as `test: reproduce range fan-out with equal business result` and `feat: fail incomplete captures before budget checks`. A commit should explain one decision and keep tests with the behavior they protect. Formatting or generated SBOM updates can be separate mechanical commits when that makes review clearer.

For AI-assisted work, the PR must state what was assisted and what the owner personally verified. AI output is not external review. The owner remains responsible for every shipped line, claim, license and test result.

## Daily closeout and evidence hygiene

End each day with a 20-minute audit:

1. Update the linked issue and PR with actual status, not planned status.
2. Record command, exit code, environment, revision and raw-result path for every new claim.
3. Rerun the narrow changed test and the relevant MySQL control.
4. Search artifacts for credentials, raw parameters, private notes and machine-specific paths.
5. Update [the evidence matrix](evidence-matrix.md); do not promote a row without its exit criteria.
6. Write tomorrow's first failing test or smallest unblocker.

## Report and video allocation

The report body must stay within the organizer's five-page limit:

1. Problem, user, claim boundary and architecture.
2. Three product capabilities with one actual manifest diff.
3. Corpus method and measured results, including safe controls and limitations.
4. Utility, competitive comparison and open-source/community evidence.
5. Reproducibility, license/SBOM, project-management trail, limitations and roadmap.

The video target is 2:50-2:58, leaving upload/player timing margin:

- 0:00-0:20: business tests can stay green while observed JDBC work expands.
- 0:20-0:40: existing facilities and the precise gap.
- 0:40-1:40: clean `record/verify` demo with the business-green/contract-red mutation.
- 1:40-2:15: structural diff and two or three measured corpus results.
- 2:15-2:40: package, CI, release, docs and external feedback.
- 2:40-2:55: exact supported scope and one-sentence conclusion.

Do not spend video time listing every feature. The evaluator should see the failure, understand why ordinary assertions missed it, and know how to reproduce it.

## Award-readiness verdict

The project is award-credible only if G0-G4 pass and the submission contains E04-E08 plus E12 as artifact-ready evidence. E09, E10, E13 and E14 materially strengthen the open-source-growth and community scores; they cannot be replaced by extra code at the end.

If the core manifest loop, real-MySQL corpus or clean-clone verification is still pending on August 20, the correct move is to cut scope and finish those items. A broad prototype with no immutable evidence is not a competitive substitute.
