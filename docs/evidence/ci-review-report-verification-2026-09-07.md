# CI review report verification — 2026-09-07

Evidence labels: `verified - unit`, `verified - MySQL`, `verified - ShardingSphere-JDBC 5.5.3`.
Source implementation: `c9265eab305bb0a78d28080500c56347607562e0`, based on main
`925efb600b2871f67c95d142308aa77194b0e47c`. Documentation-only follow-up changes do not change
the measured source. These are local maintainer-machine results, not independent adoption or
Linux CI results. The feature is not in released v0.1.2.

## Environment and commands

- macOS arm64; Homebrew OpenJDK 17.0.15+0; Gradle 8.14.4; Docker client/server 29.2.1.
- ShardingSphere-JDBC 5.5.3; MySQL 8.4.11 image
  `sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb`.
- `./gradlew check assemble`: success; 48 library tests and 14 MySQL integration tests,
  zero failures/errors/skips. Ten report/CLI tests are included in the 48.
- `python3 -m unittest discover -s scripts/tests`: 520 run, three skipped, no errors/failures.
- After README layout edits: seven onboarding tests and 17 public-installer tests rerun successfully.
- The report task was invoked for the committed matching pair and the committed `1 → 2` regression:
  Gradle exit 0 / report MATCH / strict exit 0; Gradle exit 1 / POLICY_VIOLATION / strict exit 1.

One full rerun before the final bounded-output change executed all 16 Gradle tasks. The final
incremental `check assemble` reran the changed library and dependent MySQL tests; seven tasks
executed and nine were up-to-date. Counts above come from the final JUnit XML, not the log's
number of task lines. The existing corpus includes its own repeated cases; this is one final
suite invocation, not a new repetition or load-test claim.

## Reproduced result

The real-MySQL `functionallyEquivalentRangeQueryFailsCanonicalManifestContractWithActionableCiEvidence`
test retains both business-result assertions, captures baseline/candidate, and writes the
[Markdown report](ci-review-report-example.md) and [JSON report](ci-review-report-example.json).
They show attempts and distinct aliases `1 → 2`, `RCM201` and `RCM202`, and strict failure.
The reports are copied from test output; running the report against committed JSON alone does not
count as another database experiment.

Report tests also cover same-count structural drift, candidate budget inflation, review-only drift,
schema/eligibility precedence, incomplete and callback-failure evidence, untrusted identifier
omission, deterministic output, malformed/oversized/missing input, existing file/symlink/hard-link
protection, and 120 structural findings reduced to 100 displayed findings with 20 explicitly omitted.
Full verifier findings remain available to the API caller and the final decision is unchanged.

## Raw local result paths, relative to this checkout

- `routecontract-shardingsphere-5.5/build/test-results/test/TEST-*.xml`
- `examples/mysql/build/test-results/test/TEST-*.xml`
- `examples/mysql/build/routecontract-demo/review.{md,json}`
- `build/review-smoke/{match,regression}.json` and `receipt.json`
- `build/growth-verification/summary.json` and command logs

Build paths are ignored and can be regenerated; copied examples are versioned. Raw local logs are
not published because child processes can print synthetic SQL or connection details. The normal
CI artifact retention policy remains unchanged.

## Limits

No Central publication, hosted service, performance improvement, external adoption, human baseline
approval or complete route-plan claim follows from these checks. A canonical digest identifies
content, not original input bytes, origin, freshness or execution provenance. The CLI creates a new
output file; its parent directory must already exist. Input/output errors exit 2 at the Java CLI
layer; Gradle wraps a nonzero Java process result as a failing Gradle task.

Self-review and implementation were AI-assisted. This is not an independent review or a statement
that the repository owner personally executed the tests. Future release checks and PR #62's
core/adapter migration remain separate work.
