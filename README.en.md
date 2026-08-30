# RouteContract for ShardingSphere-JDBC

[한국어](README.md) | [English](README.en.md)

[![CI](https://github.com/ym0506/routecontract/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ym0506/routecontract/actions/workflows/ci.yml?query=branch%3Amain)

> **Start an assisted pilot with a 30-minute fit check — no setup before opting in**
>
> If you maintain a public Java 17 repository with exactly ShardingSphere-JDBC 5.5.3 and one
> existing synchronous non-batch `PreparedStatement` test, [leave the three-line `interested`
> reply in Discussion #34](https://github.com/ym0506/routecontract/discussions/34). I will inspect
> the public code first and return a fit/not-fit answer; if it fits, I will prepare a private
> first-pass patch for one representative operation. Nothing is published, baseline-approved,
> or described as adoption without your separate confirmation.

[Apache ShardingSphere-JDBC](https://github.com/apache/shardingsphere) is JDBC middleware that can split one logical SQL operation across multiple data sources inside a Java application. RouteContract is a Java testing library that compares execution-structure changes missed by business-result tests with a human-reviewed baseline and fails a manifest assertion. Configuring that assertion as a required CI check can stop an unapproved change from merging.

- **Who:** developers and teams using or evaluating Apache ShardingSphere-JDBC 5.5.3
- **Missed change:** a functional assertion can return the same row and pass while hook-reported physical JDBC execution attempts and data sources each change from `1 → 2`
- **CI decision:** in the verified `1 → 2` fixture, attempt-count and data-source-budget overruns fail the manifest assertion with `RCM201` and `RCM202`; configuring it as a required check can block the merge, while RouteContract does not label `1 → 2` itself as a performance defect and requires a person to review whether the change is intentional
- **Verified boundary:** Java 17, exactly ShardingSphere-JDBC 5.5.3, normal-returning and non-interrupted synchronous non-batch `PreparedStatement`; it does not decide SQL semantic equivalence or reconstruct a complete route plan, commit, or business success

[Watch the 2:54 demo](https://www.youtube.com/watch?v=pcgvNNxd1mM)

![A verified real-MySQL case where the business result stays the same while observed attempts and reviewed data-source aliases change from one to two, producing RCM201 and RCM202](submission/assets/baseline-candidate.png)

## Quick Start

Prerequisites are Git, Java 17, a running Docker daemon, Bash/POSIX tools, and the executable Gradle
Wrapper. The first run may need network access for the public tag, Gradle and Maven Central
dependencies, and the digest-pinned MySQL container image when it is not already available locally.

```bash
(
set -euo pipefail
source_dir="routecontract-v0.1.2"
test ! -e "${source_dir}"
test ! -L "${source_dir}"
git clone --quiet --depth 1 --branch v0.1.2 --single-branch \
  https://github.com/ym0506/routecontract.git "${source_dir}"
test "$(git -C "${source_dir}" cat-file -t refs/tags/v0.1.2)" = tag
test "$(git -C "${source_dir}" rev-parse refs/tags/v0.1.2)" = 6adacbe04d60b3af83d9067a14a878d26a6c90f5
test "$(git -C "${source_dir}" rev-parse 'refs/tags/v0.1.2^{}')" = fc4fdd16c21574afa1150654ce354cf8004b138b
test "$(git -C "${source_dir}" rev-parse HEAD)" = fc4fdd16c21574afa1150654ce354cf8004b138b
test -z "$(git -C "${source_dir}" status --short)"
cd "${source_dir}"
./scripts/quickstart-demo.sh
)
```

This command verifies the real-MySQL `1 → 2` observed-execution regression
while the business result stays unchanged, then feeds the same candidate to
the CI gate and checks the expected `RCM201`/`RCM202` rejection. A final
`[ROUTECONTRACT QUICKSTART VERIFIED]`, `realMysqlDemoExit 0`,
`intentionalCiGateExit 1`, and `quickstartExit 0` means the whole flow behaved
as expected.

<details>
<summary>Exact exit-code and output boundary</summary>

Exit `1` belongs to the intentionally rejecting inner CI gate;
exit `0` from the quickstart means that rejection was verified. A preflight or
verification failure exits `2`. The wrapper does not echo raw child-process
output that could contain SQL, parameters, or connection details.

</details>

## Next step: assess a first integration

After the Quick Start passes, read the support boundary and stop conditions in the
[first real integration guide](docs/first-integration.md), then choose one representative existing
ShardingSphere-JDBC 5.5.3 integration test whose business assertion will remain. The guide connects
capture → candidate → human-approved baseline → candidate check in an isolated Gradle Groovy or
Maven 3.9.14 pilot. Repository-specific build isolation and human review are
required, so no completion time is
promised. `v0.1.2` is not published to Maven Central; the guide installs
verified GitHub Release assets into a separate local Maven repository.

Important: the immutable `v0.1.2` Release body and the README stored in that tag still point to the
`v0.1.0` onboarding path. The current `main` documentation and guide are a post-release bridge for
consuming `v0.1.2` assets; they do not make `v0.1.2` a self-contained immutable onboarding Release.
Helpers and verifiers added after the tag are pinned to the exact bridge implementation commit and
the SHA-256 recorded in the guide.

Do not read the roughly 1,700-line guide linearly. Use this shortest supported path:

1. [Install the pinned Release assets](docs/first-integration.md#2-install-the-exact-v012-release-assets).
2. Choose exactly one build lane: [Gradle Groovy](docs/first-integration.md#gradle-groovy-dsl-opt-in-lane)
   or [Maven 3.9.14](docs/first-integration.md#maven-3914-opt-in-profile-lane).
3. Continue through the shared [representative operation](docs/first-integration.md#3-add-one-representative-operation)
   → [human baseline review](docs/first-integration.md#4-review-and-approve-the-first-baseline)
   → [CI candidate check](docs/first-integration.md#5-run-the-candidate-check-in-ci).

Maven users can run the checked-in [two-module reference fixture](examples/maven-pilot/README.md)
first and compare its boundaries with their own repository. If neither lane matches exactly, stop
there instead of forcing a generic fragment into the build.
After preparing the two Maven pilot tests, copy the [six-field example JSON](examples/maven-pilot/assisted-pilot.example.json)
and use the [one-command runner](examples/maven-pilot/README.md#one-command-runner-for-an-adapted-external-maven-pilot)
instead of assembling the existing verifier's twelve inputs by hand for `review` and `matched`.

After a first run—or after deciding that the current scope is not a fit—use the
[stable v0.1.2 feedback form](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml)
to share a success, blocker, unsupported setup, or not-a-fit result. Do not put raw SQL, bind values,
JDBC URLs, real topology, full logs, or other sensitive information in the public Issue.

## Smallest usage example

```java
RouteSnapshot snapshot = RouteContract.capture("orders.find-by-user-id", () -> {
    Order actual = orderRepository.findByUserId(3L);
    assertEquals(201L, actual.id()); // Keep the existing functional assertion.
});

RouteAssertions.assertThat(snapshot)
        .hasCompleteCapture()
        .hasNoReportedExecutionFailures()
        .hasExactlyObservedPhysicalAttempts(1)
        .observesExactlyDataSourceNames("ds_1");
```

## Approved manifests and structural manifest diffs

During one application operation, RouteContract turns the **physical JDBC execution attempts reported through `SQLExecutionHook`** into a deterministic manifest and checks per-operation budgets and structural fields. A **structural manifest diff** compares attempt counts, aliases, callback outcomes, exact rewritten-SQL fingerprints, and parameter shape; it does not decide SQL semantic equivalence or reconstruct the complete route plan.

```java
DataSourceAliases aliases = DataSourceAliases.of(Map.of(
        "ds_0", "orders-a",
        "ds_1", "orders-b"));
ManifestPolicy policy = ManifestPolicy.strict(1, 1);

ObservedExecutionManifest candidate = ObservedExecutionManifest.from(
        snapshot, aliases, policy);

Path approvedPath = Path.of("route-contracts/orders.find-by-user-id.json");
Path candidatePath = Path.of("build/routecontract/orders.find-by-user-id.candidate.json");
new ManifestStore().writeCandidate(approvedPath, candidatePath, candidate);

ObservedExecutionManifest approved = new ManifestStore().read(approvedPath);
ManifestVerificationResult result = new ManifestVerifier().verify(approved, candidate);
ManifestAssertions.assertMatched(result); // A mismatch fails CI with stable RCM codes.
```

Writing a candidate never overwrites the approved file automatically. When a change is intentional, a person must review the diff and explicitly replace the approved baseline.

[examples/manifests](examples/manifests/README.md) contains canonical JSON from the real MySQL equality baseline and the same-result `BETWEEN` candidate, together with verifier output. The integration test regenerates these files on every run and checks byte-for-byte equality and deterministic structural manifest diffs with stable RCM codes.

<details>
<summary>Alias trust boundary and strict/budgetOnly policy details</summary>

The data-source alias mapping is trusted configuration and part of the approval contract. The manifest stores caller-provided aliases, so aliases must be stable and non-sensitive. Reusing a real data-source name as its alias exposes that name. Quietly mapping a different real data source to an existing alias can hide drift. Review the mapping in version control alongside the manifest.

- `ManifestPolicy.strict(...)` blocks structural signature changes, including fingerprint changes.
- `ManifestPolicy.budgetOnly(...)` blocks changes in attempt count, data-source set, and callback outcomes, while returning signature-only changes as `REVIEW_REQUIRED`.
- Canonical JSON excludes timestamps, UUIDs, thread assignment, raw SQL, parameter values, and exception messages. It stores data sources only as caller-provided aliases, and callers remain responsible for keeping those aliases non-sensitive.

In a MySQL fixture that preserves the returned rows, one observed attempt, and
the same data source while changing an additional filter and predicate order,
only the fingerprint and parameter-type order drift. This is an observation
about that fixture, not a claim that the two SQL forms are generally
semantically equivalent.

| Policy | Result for this signature-only change | Tradeoff |
|---|---|---|
| `strict` | `DRIFT`; blocking `RCM301`/`RCM302`; assertion fails | Forces review and approval of small rewritten-SQL structural changes, but also blocks intentional changes until the baseline is updated |
| `budgetOnly` | `REVIEW_REQUIRED`; non-blocking `RCM301`/`RCM302`; `passesBlockingChecks=true` | Still blocks budget, data-source-set, and callback-outcome changes, but a missed manual review can allow a signature-only structural regression through CI |

The `ManifestAssertions.assertMatched(result)` call above also rejects `REVIEW_REQUIRED`. A
`budgetOnly` policy that intentionally lets signature-only review items pass CI must make that
choice explicit with `ManifestAssertions.assertPassesBlockingChecks(result)`.

</details>

## Verified core scenarios

| Scenario | Verified result |
|---|---|
| Same value, `=` → `BETWEEN` | Business row unchanged; observed attempts `1 → 2`; data sources `[ds_1] → [ds_0, ds_1]` |
| Reduced and modified fixture inspired by public issue #38456 | JOIN and subquery both return `COUNT=1`; observed attempts are `1` and `8`, respectively; this is not claimed as a faithful reproduction of the original issue |
| Configuration regression | Removing the table strategy keeps the attempt count and data sources unchanged but produces SQL-fingerprint drift |
| Determinism | Across 160 captures—8 corpus cases repeated 20 times—each case produced exactly one structural signature |
| Concurrently open caller-operation scopes | Across 20 single-attempt/multi-attempt scope pairs, no events were attributed across operations; temporal overlap of physical callbacks was neither forced nor measured |
| Generic JDBC-tool comparison | With datasource-proxy outside ShardingSphere, callbacks stay `1 → 1`; with wrappers around physical data sources, they become `1 → 2`; RouteContract also observes `1 → 2` |
| Isolated consumer build | In the same checkout, a standalone consumer using only the generated JAR and POM in a temporary Maven repository passed SPI auto-discovery and a MySQL execution test; this is not evidence of external adoption |
| Isolated Maven 3.9.14 pilot | In the same checkout, an inactive profile, fresh caches, a SHA-256 negative check, a MySQL candidate, and a mechanical match passed; this is not human approval, an external user, or adoption evidence |

Run the full 52-test verification:

```bash
./gradlew --no-daemon --no-build-cache clean check assemble validateOfficialCycloneDxSbom
./scripts/verify-standalone-consumer.sh
./scripts/verify-maven-pilot.sh
```

The first command runs 52 core and MySQL-corpus tests on Java 17, ShardingSphere-JDBC 5.5.3, and a digest-pinned MySQL 8.4.11 Testcontainers image, then generates the JAR, Javadoc, and SBOM. The second command runs one separate consumer test. The third requires exact Apache Maven 3.9.14 and verifies the isolated profile-off, checksum, and candidate paths. All require Docker.

## Precise comparison with existing tools

RouteContract's contribution is packaging ShardingSphere-JDBC 5.5.3 observations into one repeatable workflow: caller-defined application-operation boundary → worker correlation → value-minimized manifest → human approval → deterministic structural diff → stable RCM codes → CI assertion.

- ShardingSphere-Proxy `PREVIEW SQL`, together with ShardingSphere `sql-show` and Agent, provides planning, logging, and operational telemetry.
- ShardingSphere Audit checks whether built-in algorithms recognize a sharding condition.
- Sniffy and datasource-proxy support SQL-count assertions or custom JDBC collection.
- RouteContract does not replace these tools. Its structural manifest diff compares manifest fields, not SQL semantics.

datasource-proxy is a credible do-it-yourself alternative, not a strawman. By wrapping every physical data source and adding application-owned correlation, minimization, canonicalization, diff, and assertion code, it can implement a comparable narrow check. RouteContract's scoped contribution is packaging the approval workflow for 5.5.3 without requiring every physical data source to be wrapped.

See [competitive-analysis.md](docs/competitive-analysis.md) for the sourced comparison and limitations, and [empirical-comparison.md](docs/empirical-comparison.md) for the measured datasource-proxy fixture.

## Code and public-evidence boundaries

Code map (representative boundaries; a directory is not assumed to have only one role):

| Boundary | Representative paths | Role |
|---|---|---|
| Shipped library | `routecontract-shardingsphere-5.5/src/main` | Consumer API and 5.5.3 SPI provider included in the Release JAR. |
| Public verification and examples | `routecontract-shardingsphere-5.5/src/test`, `examples/` | Unit, real-MySQL, and standalone-consumer fixtures; not included in the library JAR. |
| Mixed automation | `scripts/`, `.github/workflows/`, `security/`, `gradle/` | `scripts/` contains user-facing Quick Start and Release-asset installation tools plus maintainer release, supply-chain, and demonstration-verification tools. None is a consumer runtime API. |
| Verification/submission support | `submission/`, `scripts/video-demo-session.sh`, `docs/evidence-matrix.md` | Evidence tracking, result-report, and reproducible packaging material; not part of the shipped product. |

This source declares release-target project version `0.1.2`, with corresponding tag name `v0.1.2`.
A version string or checkout does not prove that an annotated tag, public immutable
non-prerelease Release, same-revision release-evidence run, or external-user result exists.
Use public assets only after verifying tag/Release/evidence-run revision identity and every
postpublication check in the [release procedure](RELEASING.md).

<details>
<summary>Exact evidence boundary for historical RC and public-CI records</summary>

`v0.1.0-rc1` is retained as the historical annotated tag for the first release-evidence attempt.
That run failed while resolving a digest-pulled MySQL image through a mutable local tag and created
no Release. Do not use RC1 as an activated installation candidate or move its tag.
`v0.1.0-rc2` corrected that failure and is retained as the historical prerelease activated through
the [fixed activation record](docs/evidence/independent-rc-activation-v0.1.0-rc2.json). Its assets
and RC-scoped results are not promoted to stable `v0.1.0` validation or adoption.

The earlier public CI snapshot's 50 normal tests and one same-checkout isolated consumer test
passed with zero failures, errors, or skips for [public-main revision
`54f1c92`](https://github.com/ym0506/routecontract/actions/runs/31501026857). That historical run
does not verify the `v0.1.0-rc2` revision, the stable `v0.1.0` revision, or either Release's assets,
and the isolated consumer is not external adoption evidence. See the
[public CI evidence record](docs/public-ci-evidence.md) for its environment, raw artifacts, and
limitations. None of these results implies production support or general performance.

</details>

## Consume public Release assets without a registry

This path becomes usable only after an annotated `v0.1.2` tag, a public immutable non-prerelease
Release, a successful same-revision release-evidence run, and the exact asset set all exist.
Download every public asset attached to that Release into a new empty directory, then install it to
an empty absolute repository path rather than relying on `~/.m2`. [Step 2 of the first real
integration guide](docs/first-integration.md#2-install-the-exact-v012-release-assets) uses fixed
public URLs and a pinned checksum-index SHA-256, without a GitHub login, token, or API call.

Do not add the resulting local Maven repository or RouteContract dependency directly to the
default build. The [Gradle Groovy DSL](docs/first-integration.md#gradle-groovy-dsl-opt-in-lane) and
[Gradle Kotlin DSL](docs/first-integration.md#gradle-kotlin-dsl-opt-in-lane) lanes activate a
separate source set, task, and repository only when the pilot property is present; the same guide
also provides a Maven 3.9.14 lane with an inactive-by-default profile, a fresh consumer cache, and
repository-scoped SHA-256 validation. All three reuse a representative fixture's existing
ShardingSphere-JDBC 5.5.3 dependency, and the normal build and IDE sync must succeed without the
pilot or local Release repository. Build layouts, toolchains, repositories, graphs, or
classloaders outside the verified boundary of the selected lane remain fit blockers.

The embedded MySQL OCI package-level manual review in the immutable `v0.1.2` installer is valid
through UTC `2026-12-05`. Beginning `2026-12-06` UTC, the installer fails closed; use a newer
immutable Release with renewed evidence and do not bypass the expiry.

<details>
<summary>Exact supply-chain boundary enforced by the installer</summary>

The installer performs no network access. Before writing, it validates the
exact public-asset set, `SHA256SUMS`, the sanitized supply-chain summary's
hash binding to the public SBOM/POM assets, non-SNAPSHOT POM coordinate, JAR
structure and namespace-path rules, sources-JAR Java-package rules, a parent- and
relocation-free POM, the
source ZIP's single versioned root, required `LICENSE` and `NOTICE`, conventional
source-root/first-party-package/path-to-declaration agreement for every Java file,
compiled-`.class` and JTS/Mahout name/package boundaries, and the canonical
`ym0506` provider namespace.
It copies only the main, sources, and Javadoc JARs plus the POM into the
explicit Maven layout, refuses to overwrite an existing coordinate, and rejects
the conventional `~/.m2/repository` and every path below it as its target. Checksums verify download
integrity, not publisher identity, so obtain the assets from the public Release
for that exact tag. These are name, path, declared-package, and dependency
checks; they do not determine the semantic provenance of renamed or copied code.
The final submission packaging
gate separately proves that the release archive has the same tracked-file
content, paths, and executable permissions as the final tagged Git tree.

</details>

To exercise a real MySQL consumer from the same source checkout with that file
repository as the exclusive RouteContract source, use a separate empty target:

```bash
./scripts/verify-release-assets-consumer.sh \
  /absolute/path/to/downloaded-release-assets \
  /absolute/path/to/empty-verification-maven
```

This is release-packaging evidence from the same checkout, not evidence of
external adoption.

For the shortest business-green/contract-red demonstration, run:

```bash
./scripts/run-demo.sh
```

This runs a real MySQL scenario in which changing equality to a same-value range preserves the business result but expands observed attempts from `1 → 2` and data sources from `1 → 2`. The strict manifest reports `RCM201` and `RCM202` as CI failures. The command succeeds because the test verifies that the expected violation occurs.

To reproduce an actual non-zero CI-gate exit using only two verified manifest files, run:

```bash
./scripts/demo-manifest-ci-failure.sh
```

This command does not require Docker. It prints `RCM201` and `RCM202`, then intentionally exits with code `1`. It is a dedicated fixture excluded from the regular `test` and `check` tasks.

To regenerate and compare the canonical files against real MySQL, then fail the build against the same approved baseline, run:

```bash
./scripts/demo-end-to-end-ci-failure.sh
```

Even when the preceding stages succeed, this command intentionally exits with code `1` at the final contract assertion.

## Exact evidence boundary

RouteContract observes:

- the data-source name reported to the hook;
- the SHA-256 fingerprint of the exact rewritten SQL string reported to the hook;
- parameter count and Java type names;
- the trunk/worker flag;
- start, callback return, callback failure, and missing-terminal-callback states.

RouteContract does not observe or prove:

- the complete route plan or `RouteContext`;
- every planned execution unit or every target shard;
- the exact number of physical tables;
- automatic `FULL_ROUTE` or `BROADCAST` classification;
- transaction commit or business success.

The ShardingSphere SPI method name `finishSuccess()` does not mean that a transaction committed or that a business operation succeeded. RouteContract uses `CALLBACK_RETURNED` only to mean that ShardingSphere 5.5.3 reported `finishSuccess` to this hook provider after the physical `executeSQL` call returned. It does not prove completion of the surrounding JDBC operation, transaction, or application action.

## v0.1 support boundary

This problem is not limited to one ORM or repository API. Apache ShardingSphere-JDBC can be used with direct JDBC and integration surfaces such as MyBatis, JPA, and Hibernate; RouteContract's capture API is not ORM-specific. That describes the problem and API surface, not verified end-to-end compatibility with each of MyBatis, JPA, and Hibernate.

- Java 17
- Apache ShardingSphere-JDBC **exactly 5.5.3**
- Synchronous `PreparedStatement` operations that return normally and whose caller is not interrupted when capture closes
- Integration verification against MySQL 8.4.11
- Concurrent operations on different caller threads and multi-attempt worker callbacks in the test fixture

Out of scope:

- ShardingSphere-Proxy
- JDBC batch and reactive execution
- Application-owned `@Async` boundaries
- Every SQL Federation execution path
- Other ShardingSphere versions
- Legitimate zero-SQL operation verification
- Contract approval for operations with a callback failure or caller interruption

The preflight only checks that the classpath's `shardingsphere-infra-executor` and `shardingsphere-infra-spi` report implementation version `5.5.3`, and that the service loader finds exactly one RouteContract provider. It does not prove version consistency across the complete ShardingSphere runtime artifact set. A capture cannot pass when those checks fail or no start callback is observed inside the capture. RouteContract does not claim to identify or explicitly reject every out-of-scope execution path, including Proxy, batch, and reactive paths.

After a parallel execution failure, ShardingSphere 5.5.3 may not wait for every worker it already submitted. A `REPORTED_EXECUTION_FAILURE` snapshot is therefore diagnostic-only and cannot pass route budgets or manifest matching.

One capture retains at most 10,000 physical execution attempts. At the next attempt, it stops growing the retained set and becomes `INCOMPLETE` with the `RC_ATTEMPT_LIMIT_EXCEEDED` diagnostic.

## Dependency and Release compatibility details

The exact coordinate in the postpublication-verified stable `v0.1.2` Release is
`io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.2`; it is not claimed to exist
on Maven Central. Do not add it directly to the default dependency graph. Use it only in the
isolated pilot from the [first real integration guide](docs/first-integration.md), which reuses the
existing ShardingSphere-JDBC 5.5.3 fixture and requires inspection of its complete runtime
classpath.

The RouteContract build does not configure dependency embedding. Its
module-level `compileOnly` ShardingSphere/BOM declarations are not published as
consumer version constraints. In the verified
Gradle test/runtime graph, the Jackson 2 core, databind, datatype-jdk8, and
datatype-jsr310 modules in ShardingSphere 5.5.3's compatibility graph resolve to
2.18.9, while Calcite Core and linq4j resolve to 1.42.0. JTS Core 1.19.0 remains,
but JTS I/O Common must be absent from the graph. In the runtime that also contains Jackson 3.1.5, the shared
`jackson-annotations` artifact resolves to 2.21 through the Jackson 3 BOM. This
does not replace or downgrade RouteContract's separate product runtime,
`tools.jackson.core:jackson-core:3.1.5`.

The stable-Release Javadoc classifier produced by the exact release-evidence
workflow uses pinned Temurin 17.0.20.1+1 and contains OpenJDK standard-doclet
static assets and `legal/` notices. A general local build requires Java 17 but
does not guarantee the same classifier-asset version. These assets are not
main-JAR/runtime dependencies; see [THIRD_PARTY.md](THIRD_PARTY.md) for the
shipped-file inventory.

## Data minimization and security

Snapshots and manifests do not store raw SQL, parameter values, connection properties, or exception messages. However, data-source names, operation IDs, Java type names, and unsalted SQL fingerprints can still be sensitive engineering metadata. A SHA-256 fingerprint is not anonymization. v0.1 therefore assumes deterministic `PreparedStatement` tests that do not inline confidential literals. See [SECURITY.md](SECURITY.md) for details.

## Contributing and extension gates

If you are reviewing the `v0.1.2` documentation, Quick Start, Release installation, or fit for the
first time, use the [short stable feedback form](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml)
for a successful, blocked, unsupported, or not-a-fit outcome. This record is self-reported usability
and fit feedback; it does not by itself establish production use, adoption, security, performance,
or endorsement.

Report a bug or feature proposal through the
[Issue forms](https://github.com/ym0506/routecontract/issues/new/choose) with the exact
ShardingSphere version, a user-visible regression or missing capability, and a minimized synthetic
fixture. An implementation change should include a failing test, real-MySQL verification, and an
explicit support boundary.

A new adapter or reporter is considered only after public demand, a version-specific fixture, and real-MySQL CI exist. The current v0.1 boundary remains exactly 5.5.3. See the [contribution guide](CONTRIBUTING.md) for the full workflow.

## Documentation and reproduction paths

- [Technical specification](docs/specification.md)
- [Architecture and trust boundaries](docs/architecture.md)
- [Competitive analysis](docs/competitive-analysis.md)
- [Empirical datasource-proxy comparison](docs/empirical-comparison.md)
- [Verification evidence matrix](docs/evidence-matrix.md)
- [Isolated same-checkout Maven-publication consumer](examples/standalone-consumer/README.md)
- [Isolated Maven 3.9.14 onboarding pilot](examples/maven-pilot/README.md)
- [SBOM generation and review](docs/sbom.md)
- [Provenance and prior-work boundary disclosure](ORIGIN_AND_PRIOR_WORK.md)
- [AI-assistance disclosure](AI_ASSISTANCE.md)
- [Contribution guide](CONTRIBUTING.md)

## Trademark and license

RouteContract is an independent project and is not affiliated with or endorsed by the Apache Software Foundation. Apache ShardingSphere and Apache are trademarks of the Apache Software Foundation.

RouteContract is distributed under the [Apache License 2.0](LICENSE). See [THIRD_PARTY.md](THIRD_PARTY.md) for direct and test dependencies and whether they are included in distributed artifacts.
