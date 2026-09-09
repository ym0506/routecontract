# Manifest runtime compatibility acceptance (A-22)

This suite implements the existing [A-22 requirement](versioned-shardingsphere-adapters.md)
at the decoded manifest and report boundary. It does not capture a JDBC operation or establish
new adapter/runtime support. The public v0.1.3 release is unchanged.

## Decoded identity pairs

`ManifestRuntimeCompatibilityMatrixTest` uses literal canonical JSON and a separately declared
acceptance table. The expected result never calls the implementation's `isSupported()` method.

| Identity category | Representative values |
| --- | --- |
| Exact supported | 5.5.3 executor/SPI; 5.5.2 executor/SPI |
| Unknown adapter semantics | Different adapter ID; contract revision 2 |
| Unknown runtime | Both components 5.5.4; only executor 5.5.4; only SPI 5.5.4 |
| Mixed supported component versions | Executor/SPI 5.5.2/5.5.3 and 5.5.3/5.5.2 |
| Non-exact version string | Both components 5.5.3-SNAPSHOT |

Each of these ten identities appears with schema 2 and positive unsupported schema 3.
Schema 1 adds the implicit exact 5.5.3 identity, giving 21 decoded fixtures and **441 ordered
baseline/candidate pairs**. This is a finite semantic category matrix, not an enumeration of
every possible unsupported string or integer. Every pair must preserve literal canonical bytes,
decode through both byte-array and stream APIs, and have the expected status, exact ordered
stable codes, severity, deterministic findings and report exit code.

The runtime decision table is:

| Baseline / candidate | Exact 5.5.3 | Exact 5.5.2 | Valid but unsupported |
| --- | --- | --- | --- |
| Exact 5.5.3 | RCM000 | RCM005 | RCM004 |
| Exact 5.5.2 | RCM005 | RCM000 | RCM004 |
| Valid but unsupported | RCM004 | RCM004 | RCM004 |

Either schema 3 adds `RCM001` first and suppresses `RCM000`. Unsupported identity and supported
identity mismatch are mutually exclusive findings. Non-matches are `INCOMPATIBLE` with strict
report exit 1; identical eligible supported evidence is `MATCH` with exit 0.

A separate precedence test combines each fixture with schema 1 in both directions, then adds an
operation mismatch, an ineligible baseline, an incomplete candidate and an exceeded attempt budget.
Only compatibility findings are emitted, ordered schema, runtime, operation, approved eligibility.

## Malformed documents

Independent malformed fixtures cover a missing identity; null, empty or incorrectly typed identity;
each missing/null/incorrectly typed identity field; invalid strings and length bounds; zero, negative
or overflowing revisions; duplicate fields (including identical duplicate values); unknown nested
and root fields; schema-1 explicit identity; unsupported schema missing identity; invalid schema
types/values; empty, truncated, concatenated, commented or otherwise malformed JSON.

Both decoder entry points must throw exactly `ManifestFormatException`. Each malformed fixture is
also passed to the CLI as the baseline and as the candidate, in JSON and Markdown report modes.
Every CLI invocation must return 2, create no report, emit no `RCM` finding, and leave both input
files unchanged. These are input errors, not `INCOMPATIBLE` reports.

## Reproduction and evidence boundary

Use Java 17 and the checked-in Gradle 8.14.4 wrapper:

```sh
./gradlew --no-daemon :routecontract-core:test \
  --tests io.github.ym0506.routecontract.manifest.ManifestRuntimeCompatibilityMatrixTest
```

Raw results are written below `routecontract-core/build/test-results/test/`. Run the complete core
suite after the focused suite. This test-only change neither changes production code nor regenerates
or approves any baseline. MySQL, packaged consumer, human-review and publication evidence retain
their original source identities and limitations; passing this suite cannot replace those gates.

Local evidence on 2026-09-09 is **verified - unit**, using Homebrew OpenJDK 17.0.15+0 and Gradle
8.14.4, on base source `d84291154f91bc7fb1c7d523e3ed314b37bb49c0` plus this test. The focused suite
passed 606 JUnit cases: 441 decoded pairs, two checks for each of 82 malformed documents, and one
precedence test containing 42 comparisons. The malformed CLI checks made 328 invocations. The full
core suite then passed **655 cases across six suites**, with zero failures, errors or skips. An
initial test compilation error used the wrong stream API name; changing it to `decode(InputStream)`
fixed the test. No product failure or product fix was observed.

The rebuilt core runtime and sources JARs are byte-identical to the retained `93eab99` candidate:
runtime SHA-256 `9115e1f6e96bece66d29045e3550fc72aa15a217ee82f3289598a9bc693e32ac`, sources
`5ef6a7cbeacb3a8a79e0453d3bfbe8dda1480b4380ec9d21ccc8af7f16c75abd`. Raw JUnit XML and all
three attempt logs are retained locally in `/private/tmp/routecontract-a22-validation-20260909/`
and the log paths recorded by its `validation.json`. This local result is not a new full CI,
database or packaged-consumer matrix result.

The first CI execution at merge `baeb8a832554d036da1fb921beef07def2867c9e` retained 25 raw JUnit
suites with 780 passing cases, including this suite's 606 cases and the existing 28 MySQL cases,
on Ubuntu 24 / Temurin 17.0.20.1+1 / Gradle 8.14.4. The **job failed after those tests**: the
summary tool's fixed inventory had not registered the new suite. Unsigned candidate preparation
and downstream steps were skipped. This failed job is not evidence of a completed candidate.

The inventory correction adds this exact suite with its required count of 606. The existing
submission tests maintain a separate acceptance fixture; that fixture also requires an explicit
update to 25 suites and 780 cases. The intermediate `3f471a9` CI job exposed that stale fixture
before reaching the Java tests. The final tests extend that existing acceptance suite and preserve
its historical 52-case contest-summary check. They reject an absent A-22 suite, 605 matrix cases,
duplicate or unknown suites, failures and missing original suites. All 314 submission-tool tests
passed locally on CPython 3.12.14 after the correction. Reprocessing the unchanged downloaded XML
with the corrected tool produces a 25-suite/780-case summary locally. That is a post-processing
check, not a successful rerun of either failed CI job.

The complete `scripts/tests` run also finished: 1,067 cases, with 1,064 passed and three existing
opt-in integration probes skipped (official CycloneDX checks and the release-asset MySQL consumer).
This local Python result does not substitute for those separate integration checks.

When adding Java suites or changing case counts, update both the summarizer inventory and
`submission/tools/tests/test_summarize_test_results.py`. Keep the acceptance fixture independent
of the production allowlist, and run both Python test roots used by CI:

```sh
python3 -m unittest discover -s submission/tools/tests -v
python3 -m unittest discover -s scripts/tests -v
```
