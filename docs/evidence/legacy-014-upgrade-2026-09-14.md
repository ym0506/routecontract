# Upgrade checks now include the installed 0.1.4 release

A user upgrading to 0.2 may leave their installed 0.1.4 JAR on the classpath or
in a dependency declaration. The current migration checks still listed four
older artifacts. Their passing results therefore did not cover the newest
public release that an upgrading user would have installed.

**Verified on 2026-09-14:** the current-entry check passed all 76 fresh JVM
cases, and the Gradle and Maven resolver checks passed all 46 and 56 cases,
respectively. Each matrix ran once against the unsigned CI candidate from
`5800ed2`, with the actual published legacy artifacts. No production JAR was
rebuilt or changed for these checks.

## What changed

Three acceptance tests first reproduced missing 0.1.4 coverage in the actual
current-entry, Gradle and Maven plans. The implementation adds a separate
format-2 registry containing the same four historical entries plus the published
0.1.4 JAR, POM and Gradle metadata. Public 0.1.4 bytes matched the retained
release receipt; its class and provider layout was inspected directly.

The original format-1 registry, tag-only records, original A-28 failure and
historical matrix results remain unchanged. Current runners require format 2.
An additional acceptance test reproduced silent fallback to the old registry in
all three runners before that fallback was rejected. A successful 64-case
subset cannot qualify the current 76-case plan.

The [machine-readable evidence](legacy-014-upgrade-2026-09-14.json) contains exact
case identities, outcomes and retained log/result hashes. Raw SQL, parameters,
connection details, local paths, process IDs and exception messages remain
outside the public record.

## Actual results

| Check | Result | What was observed |
| --- | --- | --- |
| Current capture entry | 40 collision cases passed | Five legacy JARs × two exact ShardingSphere versions × two physical JAR orders × two current capture methods |
| Ordinary SQL before bootstrap | 20 collision cases passed | Five legacy JARs × two exact versions × two physical JAR orders |
| Clean controls | 12 cases passed | Eight no-SQL captures and four real-MySQL operation controls |
| Startup rejection | 4 cases passed | Missing and wrong adapters for each exact runtime |
| Gradle resolver | 46 cases passed | 16 expected resolutions, 20 capability rejections and 10 strict-version conflicts |
| Maven resolver | 56 cases passed | 16 expected resolutions, 30 Enforcer rejections and 10 singleton-range conflicts |

All 60 collision cases produced `RC_LEGACY_ADAPTER_COLLISION` before the action
or business driver execution, with no linkage failure. The current API entry
and guard originated in the reviewed core JAR. All 76 JVM process identities
were distinct. This includes twelve collision cases for public 0.1.4.

The eight no-SQL captures entered their actions once and returned INCOMPLETE
snapshots with zero attempts and `RC_NO_START_CALLBACK_OBSERVED`. The four MySQL
controls each returned the fixed synthetic row `201:3:PAID` with one business
driver execution. Both captured-SQL controls returned COMPLETE one-attempt
snapshots. The owned disposable MySQL container was removed after execution.

The resolver cases kept the existing policy-disabled diagnostic controls.
Maven selection and Enforcer rejection were evaluated separately; choosing a
newer artifact did not silently excuse a conflicting legacy dependency.
Each resolver case began with its own absent dependency cache. No new SQL or
MySQL claim follows from the resolver cases.

## Bindings and review

- Candidate producer: `5800ed2960aefbf63c01d2ebaf2265278d662494` from
  [CI run 34786348241](https://github.com/ym0506/routecontract/actions/runs/34786348241).
- Consumer checkout: the full `6c1992e` revision recorded in JSON.
- Staged receipt SHA-256: `9a4d745ff11508a8ab08dd8bced6a7893d8f6e6ff5baab34b3445aea652ba49c`.
- Current registry SHA-256: `15d1f7fea7eba3496fce142ab81434134ad4058844457cf58020f5565273ab99`.
- Actual tools: Gradle 9.7.1, Maven 3.9.14 and Temurin 17.0.20.1+1 on
  macOS/aarch64; digest-pinned MySQL 8.4.11 for A-29 controls.

Both Python roots passed: 346 submission tests and 1,080 script tests, including
three existing optional skips. The focused set passed all 93 tests. No failures
or errors remained. These counts are separate from the actual JVM and resolver
executions above.

After native execution, separate read-only automated audits checked the exact
case sets, unique process identities, original/current registry bindings,
fixture and repository bytes, retained native logs and result hashes, selected
artifact records and Maven classpath JAR bytes. The audits were performed by the
same agent and did not provide human approval or rerun a resolver/JVM.

## Reproduce

Use the recorded checkout, the pinned Gradle ZIP and the candidate repository
and receipt. The current registry also supplies all five legacy releases.
The three runners are:

- [Current-entry runner](../../scripts/verify-current-entry-successor.py): no
  `--case` or `--prepare-only`; provide the independently checked receipt digest.
- [Gradle resolver runner](../../scripts/verify-gradle-legacy-artifact-consumer.py):
  no `--case`; provide the pinned Gradle 9.7.1 ZIP.
- [Maven resolver runner](../../scripts/verify-maven-legacy-artifact-consumer.py):
  no `--case`; use Maven 3.9.14 and Java 17.

Each takes `--repository`, `--staged-receipt`, `--staged-source-revision`,
`--java-home` and a separate absent `--evidence-directory`. Optional
`--legacy-payload-directory` files must match the current registry exactly.
Use `--help` for the tool-specific arguments. These runs used two resolver
workers; production/publication inputs matched the staged producer throughout.

## Limits

The supported current entry is `io.github.ym0506.routecontract.api.RouteContract`.
Manually mixed, legacy-first calls to the old FQCN retain their documented
diagnostic limitation; original A-28 remains FAILED. A-26 API migration, A-24
offline/extra-JDK profiles, final publication and authentic baseline review are
separate requirements. No public 0.2 availability, transaction-commit guarantee,
performance improvement or external adoption is established by this result.
