# Public 0.1 release consumers

Status: post-publication verification commands for the single-module, exact ShardingSphere-JDBC 5.5.3 release.
Public 0.1.3 availability and consumer results remain unverified until the commands pass against
published bytes. This work does not change the v0.1.2 installer or the separate 0.2 adapter plan.

## Acceptance contract

- Accept only a separately reviewed format-1 receipt for stable `0.1.x`, patch 3 or later, with
  exactly the JAR, POM and Gradle module metadata of `routecontract-shardingsphere-5.5`.
  Validate all expected paths and SHA-256 values before network or consumer preparation.
- Copy the small consumer outside the checkout. Use a new absent Gradle user home or Maven
  local repository per invocation, rejecting checkout-local evidence or temporary roots and
  inherited cache, repository and build-option injection. The only configured dependency
  repository is anonymous `https://repo.maven.apache.org/maven2`.
- Resolve the sole release coordinate and exact ShardingSphere-JDBC 5.5.3 dependencies without
  a project dependency, local installation, source substitution or fallback. Pin the release
  payloads to the reviewed receipt; do not carry the legacy broad trusted-artifact exemption
  into public Gradle verification. Verify the actual loaded release JAR's name and SHA-256.
- Reuse the established two-datasource MySQL fixture and unchanged approved schema-1 manifest.
  Assert exact business row `(201, 3, PAID)` independently: equality is MATCH with one reported
  physical JDBC execution attempt; range returns the same row but two attempts and is rejected
  with RCM201/RCM202. Exercise `capture`, `captureResult`, SPI discovery and CLI review.
- Require exactly three passing real MySQL tests with no failures, errors or skips in each
  consumer. Retain graph, JUnit, candidate, review and business evidence. A missing version,
  unreviewed payload or expected-receipt change fails without a success summary.
- Run independent public-byte readback first. Maven consumes POM/JAR rather than `.module`;
  its complete three-payload publication claim needs the readback. Gradle's fixed configured
  repository does not independently constrain final redirect origins; reviewed hashes bind its
  selected bytes, and the separate readback rejects redirects.

The fixtures cover synchronous non-batch PreparedStatement operations only. They observe
`SQLExecutionHook`-reported physical JDBC execution attempts, not a complete route plan. Hook
callback return does not establish business success or transaction commit. Raw local logs may
contain synthetic SQL/JDBC URLs; sanitize any derivative before public sharing.

## Reproduce after publication

Use Java 17, Python 3.10+, Docker and network access; the Maven command requires Apache Maven
3.9.14 on PATH (or its explicit `--maven` path). Complete independent public-byte readback
against the reviewed signed bundle first, then pass its `consumer-receipt.json` to each command:

```sh
python3 -I scripts/verify-public-gradle-release-consumer.py \
  --receipt /absolute/path/to/consumer-receipt.json \
  --evidence-directory /absolute/path/to/new-public-gradle-evidence

python3 -I scripts/verify-public-maven-release-consumer.py \
  --receipt /absolute/path/to/consumer-receipt.json \
  --java-home "$JAVA_HOME" \
  --evidence-directory /absolute/path/to/new-public-maven-evidence
```

Gradle uses the existing checksum-pinned 8.14.4 wrapper distribution. Its dependency repository
is fixed to Maven Central; no custom repository option exists. The new Gradle fixture reuses the
standalone consumer's dependency declarations, third-party lock lines and verification hashes.
Preparation removes the installer's broad first-party trust exemption and adds exactly the
receipt's three SHA-256 values, plus one exact first-party lock entry. The original standalone
files are unchanged. Both first-party metadata files and the compile/runtime JAR resolve and
match those hashes before test compilation.

The shared MySQL source preserves the established two-datasource fixture and reviewed schema-1
baseline from the API migration consumer. It checks loaded API/CLI/provider JAR origins and
exact hash, both capture APIs, business equality, route policy rejection and four separate JVM
CLI invocations (MATCH/regression in Markdown/JSON). CLI exits must be 0 for MATCH and 1 for a
policy violation; reports must equal the public renderer's expected bytes. The shared test
source is copied into both consumers without build-tool-specific business changes.

## Local preparation evidence, 2026-09-07

`verified - unit`: all 16 Gradle wrapper preparation/failure tests pass. They cover strict stable
versions, first-party-only lock insertion, exact three-payload metadata, removal of legacy trust
exemptions, preserved third-party trust/fixture bytes, fresh cache/environment boundaries,
checkout/symlink rejection, changed receipts, exact JUnit cases and failure evidence retention.
Command: `python3 -m unittest discover -s scripts/tests -p test_verify_public_gradle_release_consumer.py`.

`verified - unit`: all 15 Maven preparation/failure tests pass, including receipt/version
validation, fixed repository settings and isolated homes, resolve-before-compile ordering,
first-party JAR/POM hashes/origins, exact whole-group ShardingSphere selection, exact JUnit cases,
receipt mutation and failure evidence. Command:
`python3 -m unittest discover -s scripts/tests -p test_verify_public_maven_release_consumer.py`.
Both wrappers and the shared fixture received independent review. These checks are preparation
evidence; they do not make a public availability claim.

Gradle 8.14.4 configured the copied fixture successfully with offline `help`. The expected hashes
in that configuration-only test were synthetic offline inputs; no dependency was resolved.
Local log: `/private/tmp/routecontract-public-single-gradle-preparation-20260907/offline-gradle-help.log`.

An exploratory compile against the immutable public v0.1.2 JAR failed because that release does
not contain `ManifestReviewCli` or `ManifestReviewReport`. This new fixture deliberately requires
the CLI APIs already present on main for the 0.1.3 candidate. It does not prove a defect in the
0.1.3 candidate or justify skipping those APIs. The failed probe is retained separately as
`/private/tmp/routecontract-public-single-gradle-preparation-20260907/java-source-compile.log`.

The same source subsequently compiled against the actual local 0.1.3 candidate JAR with Java 17,
`--release 17 -Xlint:all -Werror`. Candidate JAR SHA-256:
`9e883e618eb09d9ecf30814151bb4b0a43eba02c78d288cc582fa7e57e6edba2`.
This is source compilation using cached dependencies, not resolution or MySQL evidence.
Receipt: `/private/tmp/routecontract-public-single-gradle-preparation-20260907/candidate-source-compile-receipt.json`.

`verified - MySQL` (local candidate control): that compiled source then passed all three tests
against the same candidate JAR and cached dependencies on exact 5.5.3 / MySQL 8.4.11, with zero
failures, skips or aborts. Both queries returned exactly `(201, 3, PAID)`; MATCH/one attempt became
POLICY_VIOLATION/two attempts with RCM201/RCM202. All four separate JVM CLI checks passed.
This one control used a temporary JUnit launcher, not either public resolver wrapper. Its scope
explicitly says `publicRepositoryConsumptionVerified: false`.

Local launcher source, exact command, receipt, log and reports:
`/private/tmp/routecontract-public-single-local-mysql-20260907`. To repeat the retained local
control, use the saved `command.json` with a new `routecontract.evidenceDirectory`; the fixture
intentionally refuses to overwrite existing route evidence. The temporary launcher compilation
emitted optional API-annotation warnings because it used the runtime classpath; the consumer
source itself had already compiled with `-Werror` against the compile classpath.

## Missing public 0.1.3 attempt

On 2026-09-07, both wrappers were run once with fresh caches against the real `0.1.3` coordinate.
The expected receipt was generated from the actual **local development candidate** JAR/POM/module
bytes, not reviewed final release bytes. Its separate scope and receipt are retained at
`/private/tmp/routecontract-013-development-consumer-inputs-20260907`. No invented future version
or publication success was used. Input SHA-256 values were:

| Development payload | SHA-256 |
| --- | --- |
| JAR | `9e883e618eb09d9ecf30814151bb4b0a43eba02c78d288cc582fa7e57e6edba2` |
| POM | `1db9eb4e8527341ed12184111913b7a56de979c5fc4195afcbdb162cb4e730d9` |
| Gradle module | `bc472c7dafc7075cba7ee2466bccc7c67ce9261b01c16e7406f8826708405770` |

Gradle 8.14.4 exited 1 in `verifyPublicResolution`: the release `.module` and `.pom` could not be
found at the fixed official Central URLs. Test compilation and MySQL did not run. Maven 3.9.14
on Java 17.0.15 exited 1 during dependency resolution: the release POM/JAR could not be found at
the same repository. Maven compilation and tests did not run. Neither wrote a success summary;
Maven retained `failure.json` with `complete: false` and
`publicRepositoryConsumptionVerified: false`.

Exact commands are the two commands above with the development receipt substituted. The wrappers
and shared fixture were commits `3ae29bc` (Gradle/Java) and `3ec9b3e` (Maven); later changes in this
worktree only document evidence. Retained logs, source inputs, locks/settings and receipts:

- `/private/tmp/routecontract-public-gradle-missing-013-20260907`
- `/private/tmp/routecontract-public-maven-missing-013-20260907`

These failures establish negative availability evidence for those attempts only. They are not
waived checks, reviewed release-byte verification, or public MySQL evidence. Fresh positive
Gradle and Maven runs must still use the final reviewed receipt after independent public readback.

Public 0.1.3 resolver/compile, real-MySQL and CLI results remain **unverified** until the full
commands pass against actual published bytes. Preparation and local candidate results cannot
stand in for publication or user adoption.
