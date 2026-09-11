# Direct immutable v0.1.2 Release consumption with Gradle

This source-only example shows an ordinary Gradle consumer resolving the exact RouteContract
`v0.1.2` JAR directly from its immutable GitHub Release. It does not use Maven Local, JitPack,
Maven Central, or a rebuilt checkout for RouteContract.

The fixed inputs are:

- coordinate `io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.2`;
- Release base URL
  `https://github.com/ym0506/routecontract/releases/download/v0.1.2`;
- file `routecontract-shardingsphere-5.5-0.1.2.jar`, 75,891 bytes;
- SHA-256 `d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc`;
- runtime dependencies `transmittable-thread-local:2.14.2` and
  `tools.jackson.core:jackson-core:3.1.5`; and
- JDK 17 plus only Apache ShardingSphere `5.5.3` modules.

The GitHub Release is exposed through an `exclusiveContent`, artifact-only Ivy repository. A
non-transitive configuration resolves one fixed module, verifies its coordinate, filename, file
type, byte length, digest, module name, required classes, and exact SPI descriptor, then atomically
stages a verified copy under `build/`. Only that staged copy enters the compile and runtime
classpath.

The checked-in `gradle.lockfile` fixes the complete selected module graph. The fixture-specific
`gradle/verification-metadata.xml` uses `verify-metadata=true`, has no trusted-artifact bypass,
and records SHA-256 values for the direct Release JAR and every JAR, POM, and Gradle module metadata
file requested from Maven Central. Every command below explicitly uses strict dependency
verification.

The locked graph preserves the published libraries' reviewed Jackson split: ShardingSphere's
FasterXML Jackson 2 modules resolve to `2.18.10`, while the shared
`com.fasterxml.jackson.core:jackson-annotations` artifact resolves to `2.21` as selected by the
Jackson 3.1.5 BOM used by `tools.jackson.core:jackson-core`. This example does not force that shared
annotations artifact down to 2.18.10.

## Run the self-contained compatibility probe

Use a local JDK 17. From the RouteContract repository root, invoke this example's byte-identical
copy of the already reviewed, checksum-pinned Gradle 9.5.1 wrapper:

```bash
JAVA_HOME=/absolute/path/to/jdk-17 \
  ./examples/gradle-direct-release/gradlew \
  -p examples/gradle-direct-release \
  --dependency-verification=strict \
  --no-daemon --no-build-cache clean check
```

The run must end with these three markers:

```text
ROUTECONTRACT_DIRECT_RELEASE_ARTIFACT_VERIFIED
ROUTECONTRACT_DIRECT_RELEASE_RUNTIME_CLASSPATH_VERIFIED
ROUTECONTRACT_DIRECT_RELEASE_RUNTIME_PROBE_VERIFIED
```

The Java probe finds the RouteContract `SQLExecutionHook` with
`ServiceLoader.Provider.type()`, verifies the provider type's CodeSource, byte length, and digest,
and only then calls `Provider.get()`. Its later `ShardingSphereServiceLoader` check is a
post-verification compatibility assertion. ShardingSphere's loader instantiates providers
internally and is not claimed as a pre-instantiation security boundary.

## Copy the lane into an ordinary consumer

Do this in a branch of the repository that owns the representative operation:

1. Copy the relevant repository, dependency, staging, and verification task blocks from
   `build.gradle.kts` into an isolated source set or module. Do not add RouteContract to the
   default application graph before the owner reviews that build-shape change.
2. Treat this fixture's `gradle.lockfile` and `gradle/verification-metadata.xml` as reviewed
   reference inputs. Merge the exact RouteContract entry and generate target-owned lock and strict
   verification records for the target's complete resolved graph; never replace or blindly copy an
   existing consumer lockfile or verification file. Do not copy the root RouteContract repository's
   broad verification metadata.
3. Use that repository's wrapper only if it is checksum-pinned and compatible. To reproduce this
   fixture exactly, copy its four wrapper files byte-for-byte:
   `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`, and
   `gradle/wrapper/gradle-wrapper.properties`. The properties pin Gradle 9.5.1 and its
   distribution SHA-256.
4. Keep JDK 17 explicit for Gradle, compilation, tests, and runtime. Reject any ShardingSphere
   component that does not resolve to 5.5.3.
5. Re-run strict dependency verification and graph review after any dependency change. A freshly
   generated Maven Central checksum is trust-on-first-use evidence only until a human reviews the
   changed coordinate, repository source, and hash. Never regenerate checksums and accept them
   blindly.

This probe's empty capture validates loading and compatibility only. It is not a representative
database operation, candidate baseline, external integration, or user.

## Apply one representative operation in your project

Follow the current [first-integration guide](../../docs/first-integration.md) in a public or private
repository you are authorized to modify. Keep the business assertion, capture a separate candidate,
have the target's authorized owner or maintainer review and approve the baseline, and run the
candidate check locally or in the team's CI. Publishing code or CI is not required for use.
[Record the use stage separately from assistance, verification and publication permission](../../docs/user-feedback.md#recording-use-and-evidence).

### Historical public upstream integration evidence standard

The earlier public-evidence standard required all five steps below, including an independently
inspectable upstream CI result. It is retained to explain the boundary of those public claims;
it is not a prerequisite for private or local project use:

1. An external repository chooses one deterministic representative ShardingSphere-JDBC operation
   that already has a business-result assertion. Keep that assertion.
2. The repository adapts the isolated pilot test so `RouteContract.capture` observes that exact
   operation, defines explicit aliases and budgets, and writes only a separate candidate under
   `build/routecontract/`. The approved path must begin absent.
3. The first candidate run is expected to fail with “No approved baseline” after producing the
   candidate. A script, bot, contributor, or RouteContract itself must not create or approve the
   baseline.
4. A human authorized to approve changes for that external repository reviews the operation,
   business assertion, aliases, budgets, and exact candidate bytes. Only that person may explicitly
   copy those exact bytes to the approved path and commit them through the repository's normal
   review process.
5. The external repository then runs the same representative operation and candidate comparison
   in its upstream public CI with `--dependency-verification=strict`. CI must prove the approved
   file is unchanged and the fresh candidate matches it.

Completing all five steps publicly can establish a publicly inspectable upstream integration.
A private project can reach the same use stage without publishing its evidence. A clone, download,
this empty local probe, draft PR or maintainer comment alone still does not establish that someone
used RouteContract on their own representative operation. Record an actual project result at its
observed stage and evidence quality; do not relabel this author-run compatibility fixture as an
external user, completed integration or repeated use.

## Run the repository-owned verifier

The verifier copies the fixture to disposable directories and never writes caches or logs into this
example. Its first dependency-resolution case starts with an absent dependency cache and project
cache, performs an online resolution with an intentionally wrong first-party verification
checksum, and requires Gradle strict verification to reject it before staging or compilation. A
second fresh-cache case proves the independent fixed SHA gate. A third corrupts one Maven POM
checksum and requires `verify-metadata=true` to reject it before runtime verification or
compilation. Those negatives are followed by a clean online success and an offline repeat.

```bash
JAVA_HOME=/absolute/path/to/jdk-17 \
  python3 scripts/verify-gradle-direct-release.py
```

If an existing Gradle 9.5.1 wrapper cache contains the distribution ZIP, the verifier can reuse
only that ZIP while retaining wholly fresh dependency caches. It independently requires the
wrapper-pinned SHA-256, copies neither extracted files nor an `.ok` marker, and lets this example's
wrapper validate and extract the ZIP:

```bash
JAVA_HOME=/absolute/path/to/jdk-17 \
  python3 scripts/verify-gradle-direct-release.py \
  --wrapper-distribution-cache \
  /absolute/gradle-user-home/wrapper/dists/gradle-9.5.1-bin
```

The source example intentionally ignores and must not retain `.gradle/`, `build/`,
`gradle-user-home/`, `project-cache/`, `test-results/`, or log files.
