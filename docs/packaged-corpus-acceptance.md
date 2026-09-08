# Final packaged runtime binding for the existing MySQL corpus

Status: planned. This finite A-23 check binds the existing six MySQL suites to
reviewed local 0.2.0 JARs. It does not add workloads, regenerate goldens, approve
an application baseline, or complete the separate human review.

## Fixed scope

Use Java 17 and the checksum-pinned Gradle 8.14.4 distribution. Run two standalone
consumers sequentially: exact ShardingSphere 5.5.3 with the four existing suites
under `examples/mysql` (14 tests), and exact 5.5.2 with the two suites under
`examples/mysql-5.5.2` (14 tests). The exact class/method allowlist and original
source/resource hashes are frozen in `examples/packaged-corpus-consumer/expected-corpus.json`.

The existing corpus assertions retain safe controls, route-risk mutations,
expected business results, failure/ineligibility boundaries, secret minimization,
the 5.5.3 datasource-proxy comparison, and version-specific golden observations.
Each runtime retains its eight-shape × 20-repetition structural-signature check
and 20 concurrently open caller-capture pairs. Physical callback overlap is not
forced or measured; arbitrary async or application concurrency is outside scope.

## Independent packaged consumption

Before execution, require an independently supplied receipt path, expected
SHA-256, and full staged source revision. Validate all nine unique coordinate-bound
JAR/POM/module payloads, their actual repository bytes, and the unchanged
production/publication source binding. Do not derive approval from a freshly
computed receipt hash. The present reviewed source is `4e066942f6e244345fe908970b81446f9e08f64e`;
the supplied receipt digest is
`38b2269eca162f121fd3996c56df8b894ae2f43cedeb08fcc627032cf70eaa43`.

Each consumer and dependency cache must begin absent. Copy the original tests,
resources, and manifest inputs byte-for-byte into a disposable consumer, retain
the copy mapping, and recheck original and copied inputs after execution.
Preserve each original Gradle dependency declaration except for replacing its
single adapter project dependency with the reviewed Maven coordinate. Preserve
the original complete third-party lock entries and add only the reviewed core
and selected adapter coordinates. Strict locks must match the full selected
compile/runtime graphs; project components, production class directories,
unreviewed first-party artifacts, or mixed ShardingSphere versions must fail.
First-party resolution is exclusive to reviewed staging; other modules use
ordinary HTTPS Maven Central with existing strict verification metadata.

A separate supplemental JUnit extension adds no test cases. It runs before and
after each existing suite in that suite's test JVM, verifies the current
`io.github.ym0506.routecontract.api.RouteContract` entry, core, selected hook and
SPI descriptor originate in the exact expected JARs, and records JAR SHA-256,
code-source paths, class-loader/JVM identity and suite identity. It must not
instantiate additional hooks or replace corpus assertions. The actual test
runtime classpath and selected artifact inventory are retained separately.

Force `routecontract.generate552Evidence=false` and reject the opt-in project
property. Ordinary existing tests may write their observations/reports to build
output, but their golden comparisons must execute and golden inputs must remain
unchanged. `humanReview` remains `null` even when every test passes.

## Required evidence and failure handling

Require the exact 28 JUnit class/method identities with no additional cases,
duplicates, failures, errors or skips. Verify the existing output markers and
version-specific report/golden comparisons; bind repetition/isolation claims to
their exact unmodified test source and successful JUnit case, including cases
whose source prints no marker. Retain actual commands, exits, Gradle version,
full selected graphs and artifact hashes, same-JVM provenance, JUnit XML,
standard output, all generated observations/reports, original/copy inventories,
strict locks/metadata and wrapper identity.

At completion recheck receipt bytes, all staged payloads and repository inventory,
source binding, every executed fixture/helper file, and all original/copy inputs.
Only the final packaged runtime binding can become complete. The result must
leave full A-23/human approval/public consumption false or pending as appropriate.
No source-project MySQL result may substitute for this packaged execution.

Before the full runtime run: implement focused meaningful regressions for exact
JUnit/provenance/hash/graph/copy/generation checks, perform independent read-only
review, freeze all inputs and record a run-ready handoff. Preserve a failed
attempt honestly. An observation timeout does not authorize restarting a live
run; any retry needs a diagnosed terminal cause and new evidence directory.

No offline, additional JDK, production build, signing, release, publication or
user-adoption claim belongs to this check. Raw SQL/bind/connection details remain
private; public evidence must contain minimized outcomes and hash bindings only.
