# Isolated Gradle Kotlin DSL pilot fixture

This internal fixture exercises the inactive-by-default Gradle Kotlin DSL lane documented in
`docs/first-integration.md`. The default test graph has no RouteContract repository or dependency.
The opt-in source set resolves the exact installed `v0.1.0` Release GAV
`io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0` through an exclusive
absolute local Maven repository, verifies the canonical coordinate JAR and POM paths and SHA-256
values, class origin, and reviewed dependency graph, and runs one synchronous
ShardingSphere-JDBC 5.5.3 operation against the digest-pinned MySQL 8.4.11 image. That
RouteContract module cannot fall back to Maven Central.

The marker-bounded block is copyable with this tested prelude and no imports outside the markers:

```kotlin
import java.nio.file.Files as JFiles
import java.nio.file.LinkOption as JLinkOption
import java.nio.file.Path as JPath
import java.security.MessageDigest as JMessageDigest
import java.util.HexFormat as JHexFormat

plugins { java }

repositories { mavenCentral() }
```

The target must have a preinstalled JDK 17. This fixture deliberately does not install or provision
a JDK and therefore is not proof that a Java-21-only target such as the current HsinDumas checkout
is ready. The repository property must be an absolute, real local directory with no symlink path
components; a `file:` URI is not accepted.

The verifier bootstraps one immutable, wrapper-pinned Gradle 8.14.4 tool distribution, then gives
every independent semantic case a distinct Gradle user home and project cache that are absent when
that case starts. An origin-only, non-transitive configuration resolves the exact RouteContract GAV
offline from a fresh cache, which proves that this module cannot fall back to a remote repository.
The full selected-invariant graph and MySQL run remain online; this lane does not claim a locked,
hermetic closure. The verifier proves marker-only compilation, rejects relative and symlink-backed
repositories plus wrong, missing-metadata, POM-tampered, and JAR-tampered GAV layouts, proves a
missing-baseline failure, and proves a separate synthetic match in a temporary copy. That copy is
test scaffolding, not human approval or external adoption. Run from the repository root:

```bash
./scripts/verify-gradle-kotlin-pilot.sh \
  --release-assets-dir /absolute/path/to/the/exact-v0.1.0-release-assets \
  --provenance-output /absolute/path/to/an/absent/provenance.json
```

For an adapted owning module, inspect the graph and require the standard marker before running the
pilot:

```bash
ROUTECONTRACT_REPOSITORY=/absolute/real/path/to/routecontract-maven \
  ./gradlew -ProutecontractPilot=true \
  :owning-module:dependencies --configuration routeContractPilotRuntimeClasspath
ROUTECONTRACT_REPOSITORY=/absolute/real/path/to/routecontract-maven \
  ./gradlew -ProutecontractPilot=true :owning-module:routeContractPilotGraph
# exact output line: ROUTECONTRACT_GRADLE_GRAPH VERIFIED
ROUTECONTRACT_REPOSITORY=/absolute/real/path/to/routecontract-maven \
  ./gradlew -ProutecontractPilot=true --no-build-cache --rerun-tasks \
  :owning-module:routeContractPilot
```

Do not reuse the fixture candidate, alias, policy, or synthetic copy as another repository's
baseline.
