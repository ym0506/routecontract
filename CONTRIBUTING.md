# Contributing

Start with a small change that makes a test or its result easier to trust. Documentation
corrections, confusing diagnostics and missing regression cases are useful contributions.
You do not need to maintain a public application or reproduce the entire release process.

## Choose a starting point

| What you found | How to contribute | What to check |
| --- | --- | --- |
| An unclear explanation or broken link | Open a focused documentation PR; a separate issue is optional. | Check the linked target, examples and rendered page. Preserve recorded versions and results. |
| A failed installation or confusing result | Use the [question and feedback form](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml). | Include the version, build tool, step reached and a short error code. A successful setup is not required. |
| A reproducible behavior defect | Open a bug report or a focused fix with a small synthetic reproducer. | Keep the expected business result and the execution condition separate; show the failing and corrected cases. |
| A new capability or supported environment | Discuss the problem and proposed scope in an issue first. | Explain the observation point, failure boundary and required compatibility checks. |

For code changes, [design decisions](docs/design-decisions.md) links each invariant to its
implementation and tests. [The roadmap](docs/product-roadmap.md) separates released behavior,
candidate work and ideas. Keep private SQL, parameter values, connection details and full logs
out of public reports.

## Development prerequisites

- JDK 17 to compile the library; JDK 21 as well for the additional runtime check
- Docker for MySQL integration tests
- Git, Python 3.10+ available as `python3`, Bash, and POSIX tools including `tar`
- `curl` and network access for public release checks and uncached dependencies

Use the checked-in wrapper: the root build and Kotlin pilot use Gradle 9.7.1. The separately
pinned `gradle95-build-shape` and `gradle-direct-release` fixtures retain Gradle 9.5.1 to test
their stated compatibility boundary. Earlier evidence records retain the version actually run.

When regenerating the root wrapper, review its JAR and distribution checksum against the
[official Gradle checksums](https://gradle.org/release-checksums/) and run
`git add --renormalize -- gradlew.bat` before reviewing the staged diff. The existing attributes
keep Windows working files in CRLF while storing normalized text in Git. Verify a fresh checkout
is clean so wrapper changes do not fail CI's source-state checks before any build starts.

## Change workflow

1. State the user-visible problem in the issue or PR. Discuss new behavior or wider support in an issue before implementation; a focused documentation correction does not need a separate issue.
2. For behavior changes, add or update the specification and a failing test. For prose-only corrections, identify the source or recorded evidence that supports the text.
3. Keep the implementation focused on one contract or invariant.
4. Run the checks affected by the change. Behavior changes require unit tests, and changes through the ShardingSphere execution hook require real MySQL integration tests.
5. Document exact versions, evidence and limitations in the pull request.

## Claims and privacy

Use the terminology in [docs/specification.md](docs/specification.md). Never include real credentials, production or sensitive parameter values, customer identifiers, or production topology in fixtures, logs, or issues. Synthetic, non-sensitive test values are allowed; RouteContract snapshots and manifests must not retain their raw values.

## Verification

For library code, start with the module's unit tests:

```bash
./gradlew --no-daemon :routecontract-shardingsphere-5.5:test
```

This checks the library module without starting the separate MySQL example. It does not
replace integration testing for execution-hook changes. For prose-only changes, check links,
rendering and agreement with the referenced API or evidence; run affected documentation checks.
If you change runnable examples, verify those examples in their documented environment.

Run the complete unit, real-MySQL integration and SBOM checks on macOS arm64/x86_64 or
Linux x86_64. These are the hosts supported by the checksum-pinned
[official CycloneDX validator](scripts/validate-official-cyclonedx.py):

```bash
./gradlew --no-daemon --no-build-cache clean check validateOfficialCycloneDxSbom
```

To keep Java 17 library bytecode and run the existing core/MySQL tests on Java 21:

```bash
./gradlew --no-daemon --no-build-cache --no-configuration-cache --rerun-tasks \
  -ProutecontractTestJavaVersion=21 \
  :routecontract-shardingsphere-5.5:test :mysql-example:test
```

Both JDKs must be available to Gradle. The [runtime acceptance record](docs/java21-runtime-acceptance.md)
explains actual-JVM verification and the public Central Maven/Gradle matrix.

Verify that a standalone consumer can resolve and run this checkout's generated Maven publication
from an isolated temporary repository rather than use an in-repository Gradle project dependency with:

```bash
./scripts/verify-standalone-consumer.sh
```

This is same-checkout packaging evidence, not proof of a public Release, registry publication,
external installation, or adoption. After a Release exists, use
`scripts/verify-release-assets-consumer.sh` for its downloaded assets.

The checked-in Maven compatibility fixture keeps Java 17 as its default and has one explicit Java
21/full-MySQL cell:

```bash
./scripts/verify-maven-pilot.sh
./scripts/verify-maven-pilot.sh --java 21
```

Both commands require exact Apache Maven 3.9.14 and Docker. The Java 21 cell is same-checkout
compatibility evidence only; it does not broaden the Java 17 external assisted-runner/starter
contract or prove adoption.

A change through the ShardingSphere execution hook is not complete until it passes the appropriate
real-MySQL test, not only an in-memory substitute. Use the packaging checks above when changing
dependencies or publication metadata.

## Future Maven Central changes

The current public release is **0.1.4**; see its [Central installation evidence](docs/evidence/release-0.1.4-central.md).
The older immutable `v0.1.2` GitHub Release is not a Maven Central publication.
Changes intended for a separately approved later stable version must follow the
approval, signing, `USER_MANAGED` upload, human validation, explicit Publish
and public-readback checklist in [RELEASING.md](RELEASING.md). Never put the
protected release private key, its passphrase or a Central credential in the
repository or CI. An ephemeral throwaway CI key may test signing configuration
only; never upload or artifact it or treat it as release evidence.

For a local publication-wiring check only, stage an unsigned candidate in a
new private directory:

```bash
(
set -e
staging_parent=/absolute/path/to/new-private-central-smoke
test ! -e "${staging_parent}"
mkdir -m 700 "${staging_parent}"
./gradlew --no-daemon --no-build-cache --no-configuration-cache \
  :routecontract-shardingsphere-5.5:publishMavenJavaPublicationToCentralStagingRepository \
  -ProutecontractCentralStagingDirectory="${staging_parent}/repository" \
  -ProutecontractCentralSigning=false
)
```

This smoke test uses no release key or Portal credential, performs no network
publication and is not evidence of a signed candidate or public availability.

## Release feedback

For a question before installation or feedback on current stable **0.1.4**, use the
[question or user feedback form](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml).
You can report a test using reviewed Java execution assertions or the optional JSON-baseline
comparison. Neither installation nor a public application repository is required to ask a question.
The [first-project guide](docs/first-project.md#adapt-one-existing-test) covers both paths.
Successful, blocked, unsupported, and not-a-fit outcomes are equally useful. This short form records
self-reported usability and fit feedback; it does not by itself prove an independent run, production
use, adoption, security, performance, or endorsement.

For a reproducible regression, product bug, or feature proposal, use the corresponding Issue Form
and include the exact version, environment, minimized reproduction, and documented claim boundary.
First failures and later assistance must remain visible.

The [independent installation study](docs/independent-install-study.md) and its RC1/RC2 forms are
retained as version-bound evidence contracts. Use a dedicated RC form only while that candidate's
activation gate and recruitment window are active and public `main` remains its activation-record
commit. After that lifecycle ends, do not present ordinary stable feedback, same-checkout tests, or
AI runs as counted independent-install evidence.
