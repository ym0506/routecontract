# First real integration

This guide moves from the RouteContract Quick Start to one representative operation in your own
repository. It keeps the operation's existing business assertion, records a separate candidate,
requires a person to approve the first baseline, and checks later candidates in tests or CI.

This is a narrow test integration, not production instrumentation. The supported boundary is Java
17 with exactly Apache ShardingSphere-JDBC 5.5.3 and a normal-returning, non-interrupted,
synchronous non-batch `PreparedStatement` operation. Stop here if the operation uses
ShardingSphere-Proxy, batch execution, reactive or application-async propagation, SQL Federation,
another ShardingSphere version, or automatic topology discovery.
Published end-to-end database verification uses MySQL 8.4.11; behavior with other databases is
unverified.

## 1. Verify the published demo first

Run the exact-tag Quick Start before changing your repository. The checkout destination below must
be absent. The checks after `clone` bind the checkout to the published annotated tag object and
peeled release commit before any project script runs:

```bash
(
set -euo pipefail
source_dir="/absolute/path/to/routecontract-v0.1.2"
expected_tag_object="6adacbe04d60b3af83d9067a14a878d26a6c90f5"
expected_commit="fc4fdd16c21574afa1150654ce354cf8004b138b"

test ! -e "${source_dir}"
test ! -L "${source_dir}"
git clone --quiet --depth 1 --branch v0.1.2 --single-branch \
  https://github.com/ym0506/routecontract.git \
  "${source_dir}"
test "$(git -C "${source_dir}" cat-file -t refs/tags/v0.1.2)" = tag
test "$(git -C "${source_dir}" rev-parse refs/tags/v0.1.2)" = "${expected_tag_object}"
test "$(git -C "${source_dir}" rev-parse 'refs/tags/v0.1.2^{}')" = "${expected_commit}"
test "$(git -C "${source_dir}" rev-parse HEAD)" = "${expected_commit}"
symbolic_ref_status=0
symbolic_ref="$(git -C "${source_dir}" symbolic-ref -q HEAD)" || symbolic_ref_status=$?
test "${symbolic_ref_status}" -eq 1
test -z "${symbolic_ref}"
checkout_status="$(git -C "${source_dir}" status --short)"
test -z "${checkout_status}"
cd "${source_dir}"
./scripts/quickstart-demo.sh
)
```

The final output must include `[ROUTECONTRACT QUICKSTART VERIFIED]`, `realMysqlDemoExit 0`,
`intentionalCiGateExit 1`, and `quickstartExit 0`. The inner exit `1` is the expected contract
rejection; the outer exit `0` means that rejection was verified. Step 1 requires Git, Java 17,
Docker, Bash/POSIX tools, and network access for the public tag, uncached dependencies, and the
digest-pinned MySQL image. Step 2 additionally requires `curl` and Python 3.10 or newer. Neither
step requires a GitHub login, token, API call, or GitHub CLI.

## 2. Install the exact v0.1.2 Release assets

RouteContract `0.1.2` is **not published to Maven Central**. Keep the exact `v0.1.2` checkout from
step 1, download every asset from the [immutable GitHub Release](https://github.com/ym0506/routecontract/releases/tag/v0.1.2),
and install the verified JAR and POM into a new, explicit local Maven repository. Replace all
absolute example paths in this guide. The Release-asset and Maven-repository destinations must both
be absent before step 2, and the Maven repository must not be `~/.m2/repository` or a path below it.

Important release boundary: the immutable `v0.1.2` Release body and tagged README still point to
the `v0.1.0` onboarding path. This `main` guide is a post-release bridge for the immutable `v0.1.2`
assets, not evidence that `v0.1.2` is a self-contained immutable onboarding Release. The installer
and assets below come from the immutable tag. Every helper or verifier introduced after that tag is
fetched through the exact bridge-commit permalink for the implementation commit and verified
against the SHA-256 recorded here.

```bash
(
set -euo pipefail
asset_dir="/absolute/path/to/routecontract-release-assets"
repository_dir="/absolute/path/to/routecontract-maven"
source_dir="/absolute/path/to/routecontract-v0.1.2"
release_base="https://github.com/ym0506/routecontract/releases/download/v0.1.2"
expected_index_sha256="7849adf417f0170b08d01902b023e8b328d8796f7c2aeacc471eb7acf8e2b217"
expected_installer_sha256="134b265709ac071dedd395da269426d83f1972f602c3b3f7d2201eecc525e204"
expected_tag_object="6adacbe04d60b3af83d9067a14a878d26a6c90f5"
expected_commit="fc4fdd16c21574afa1150654ce354cf8004b138b"
assets=(
  SHA256SUMS
  routecontract-0.1.2-source.zip
  routecontract-shardingsphere-5.5-0.1.2.jar
  routecontract-shardingsphere-5.5-0.1.2-sources.jar
  routecontract-shardingsphere-5.5-0.1.2-javadoc.jar
  routecontract-shardingsphere-5.5.pom
  routecontract-shardingsphere-5.5-cyclonedx.json
  routecontract-shardingsphere-5.5-cyclonedx.xml
  routecontract-aggregate-cyclonedx.json
  routecontract-aggregate-cyclonedx.xml
  supply-chain-evidence.json
  test-summary.txt
)

test ! -e "${asset_dir}"
test ! -L "${asset_dir}"
test ! -e "${repository_dir}"
test ! -L "${repository_dir}"
mkdir "${asset_dir}"
for asset in "${assets[@]}"; do
  curl --disable --proto '=https' --tlsv1.2 --fail --location \
    --silent --show-error --retry 3 --connect-timeout 15 --max-time 300 \
    --max-filesize 5242880 \
    --output "${asset_dir}/${asset}" \
    "${release_base}/${asset}"
done

actual_index_sha256="$(python3 -I -c \
  'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' \
  "${asset_dir}/SHA256SUMS")"
test "${actual_index_sha256}" = "${expected_index_sha256}"
test "$(git -C "${source_dir}" rev-parse refs/tags/v0.1.2)" = "${expected_tag_object}"
test "$(git -C "${source_dir}" rev-parse 'refs/tags/v0.1.2^{}')" = "${expected_commit}"
test "$(git -C "${source_dir}" rev-parse HEAD)" = "${expected_commit}"
checkout_status="$(git -C "${source_dir}" status --short)"
test -z "${checkout_status}"
installer="${source_dir}/scripts/install-release-assets.py"
test -f "${installer}"
test ! -L "${installer}"
actual_installer_sha256="$(python3 -I -c \
  'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' \
  "${installer}")"
test "${actual_installer_sha256}" = "${expected_installer_sha256}"
python3 -I "${installer}" \
  --release-assets-dir "${asset_dir}" \
  --repository "${repository_dir}"
)
```

The fixed public URLs require no GitHub account or token. The block pins the checksum index and the
installer from the exact checkout; the installer then verifies the exact 12-file inventory and
every payload checksum before writing, and refuses to overwrite an existing coordinate. A failed
attempt leaves its new directory for inspection; retry only with another absent destination.
Checksums provide download integrity, not publisher identity.

The immutable `v0.1.2` installer is intentionally time-bounded by its embedded MySQL OCI
package-level manual review through UTC `2026-12-05`. Beginning `2026-12-06` UTC it fails closed.
Use a newer immutable Release with renewed evidence at that point; do not edit the tag or installer
or bypass the expiry.

### Gradle Groovy DSL opt-in lane

Do not add the local repository or RouteContract dependency to the default build. The following
block creates a separate source set and task only when `-ProutecontractPilot=true` is present. Put
the adapted test under `src/routeContractPilot/java` and its approved manifest under
`src/routeContractPilot/resources`. The normal build and IDE sync must still succeed without the
pilot property and without the local Release repository.

```groovy
def routeContractPilotEnabled = providers.gradleProperty("routecontractPilot")
        .map { value -> value == "true" }
        .orElse(false)

if (routeContractPilotEnabled.get()) {
    def expectedRouteContractJarSha256 =
            "d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc"
    def routeContractRepository = providers.gradleProperty("routecontractRepository")
            .orElse(providers.environmentVariable("ROUTECONTRACT_REPOSITORY"))
    if (!routeContractRepository.isPresent()
            || routeContractRepository.get().isBlank()) {
        throw new GradleException(
                "Set -ProutecontractRepository or ROUTECONTRACT_REPOSITORY for the pilot")
    }

    def pilot = sourceSets.create("routeContractPilot") {
        compileClasspath += sourceSets.main.output + sourceSets.test.output
        runtimeClasspath += output + compileClasspath
    }
    configurations.named(pilot.implementationConfigurationName) {
        extendsFrom(configurations.testImplementation)
        exclude group: "org.locationtech.jts.io", module: "jts-io-common"
        exclude group: "com.google.protobuf", module: "protobuf-java"
    }
    configurations.named(pilot.runtimeOnlyConfigurationName) {
        extendsFrom(configurations.testRuntimeOnly)
    }

    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = "routeContractRelease"
                    url = uri(routeContractRepository.get())
                }
            }
            filter { includeGroup("io.github.ym0506.routecontract") }
        }
    }
    dependencies {
        add(
                pilot.implementationConfigurationName,
                enforcedPlatform("com.fasterxml.jackson:jackson-bom:2.18.9"))
        constraints {
            add(
                    pilot.implementationConfigurationName,
                    "org.apache.calcite:calcite-core") {
                version { strictly("1.42.0") }
            }
            add(
                    pilot.implementationConfigurationName,
                    "org.apache.calcite:calcite-linq4j") {
                version { strictly("1.42.0") }
            }
            add(
                    pilot.implementationConfigurationName,
                    "net.minidev:json-smart") {
                version { strictly("2.4.10") }
            }
            add(
                    pilot.implementationConfigurationName,
                    "net.minidev:accessors-smart") {
                version { strictly("2.4.9") }
            }
        }
        add(
                pilot.implementationConfigurationName,
                "io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.2")
    }

    def verifyRouteContractPilotGraph = {
        def artifacts = configurations
                .getByName(pilot.runtimeClasspathConfigurationName)
                .resolvedConfiguration.resolvedArtifacts.toList()
        def routeContractCoordinates = artifacts.findAll { artifact ->
            artifact.moduleVersion.id.group == "io.github.ym0506.routecontract" &&
                    artifact.name == "routecontract-shardingsphere-5.5"
        }
        if (routeContractCoordinates.size() != 1 || routeContractCoordinates.any { artifact ->
            artifact.moduleVersion.id.version != "0.1.2" ||
                    artifact.extension != "jar" || artifact.classifier != null
        }) {
            throw new GradleException(
                    "RouteContract runtime coordinate must resolve to exactly one " +
                            "unclassified 0.1.2 JAR")
        }
        def shardingSphere = artifacts.findAll { artifact ->
            artifact.moduleVersion.id.group == "org.apache.shardingsphere"
        }
        if (shardingSphere.isEmpty() || shardingSphere.any { artifact ->
            artifact.moduleVersion.id.version != "5.5.3"
        }) {
            throw new GradleException(
                    "Every resolved ShardingSphere artifact must be exactly 5.5.3")
        }
        def shardingSphereJdbcCoordinates = artifacts.findAll { artifact ->
            artifact.moduleVersion.id.group == "org.apache.shardingsphere" &&
                    artifact.name == "shardingsphere-jdbc"
        }
        if (shardingSphereJdbcCoordinates.size() != 1 ||
                shardingSphereJdbcCoordinates.any { artifact ->
                    artifact.moduleVersion.id.version != "5.5.3" ||
                            artifact.extension != "jar" || artifact.classifier != null
                }) {
            throw new GradleException(
                    "ShardingSphere-JDBC runtime coordinate must resolve to exactly one " +
                            "unclassified 5.5.3 JAR")
        }
        [
                ["org.apache.calcite", "calcite-core", "1.42.0"],
                ["org.apache.calcite", "calcite-linq4j", "1.42.0"],
        ].each { expected ->
            def matches = artifacts.findAll { artifact ->
                artifact.moduleVersion.id.group == expected[0] &&
                        artifact.name == expected[1]
            }
            if (matches.size() != 1 || matches.any { artifact ->
                artifact.moduleVersion.id.version != expected[2] ||
                        artifact.extension != "jar" || artifact.classifier != null
            }) {
                throw new GradleException(
                        "Required ${expected[0]}:${expected[1]} runtime artifact must be " +
                                "one unclassified JAR at ${expected[2]}")
            }
        }
        [
                ["net.minidev", "json-smart", "2.4.10"],
                ["net.minidev", "accessors-smart", "2.4.9"],
        ].each { expected ->
            def matches = artifacts.findAll { artifact ->
                artifact.moduleVersion.id.group == expected[0] &&
                        artifact.name == expected[1]
            }
            if (!matches.isEmpty() && (matches.size() != 1 || matches.any { artifact ->
                artifact.moduleVersion.id.version != expected[2] ||
                        artifact.extension != "jar" || artifact.classifier != null
            })) {
                throw new GradleException(
                        "Optional ${expected[0]}:${expected[1]} runtime artifact must be " +
                                "one unclassified JAR at ${expected[2]} when present")
            }
        }
        def jackson2 = artifacts.findAll { artifact ->
            def artifactGroup = artifact.moduleVersion.id.group
            artifactGroup == "com.fasterxml.jackson" ||
                    artifactGroup.startsWith("com.fasterxml.jackson.")
        }
        if (jackson2.isEmpty() || jackson2.any { artifact ->
            artifact.moduleVersion.id.version != "2.18.9" ||
                    artifact.extension != "jar" || artifact.classifier != null
        }) {
            throw new GradleException(
                    "Every resolved FasterXML Jackson artifact must be an unclassified " +
                            "JAR exactly at 2.18.9")
        }
        [
                ["org.locationtech.jts.io", "jts-io-common"],
                ["com.google.protobuf", "protobuf-java"],
        ].each { forbidden ->
            if (artifacts.any { artifact ->
                artifact.moduleVersion.id.group == forbidden[0] &&
                        artifact.name == forbidden[1]
            }) {
                throw new GradleException(
                        "Forbidden runtime dependency is present: ${forbidden.join(':')}")
            }
        }
        def artifactPath = routeContractCoordinates[0].file.toPath()
        if (!java.nio.file.Files.isRegularFile(
                artifactPath, java.nio.file.LinkOption.NOFOLLOW_LINKS)) {
            throw new GradleException(
                    "RouteContract runtime JAR must be a regular non-symlink file")
        }
        def actualSha256 = java.util.HexFormat.of().formatHex(
                java.security.MessageDigest.getInstance("SHA-256").digest(
                        java.nio.file.Files.readAllBytes(artifactPath)))
        if (actualSha256 != expectedRouteContractJarSha256) {
            throw new GradleException(
                    "RouteContract runtime JAR SHA-256 mismatch: ${actualSha256}")
        }
        artifactPath.toRealPath()
    }

    tasks.register("routeContractPilotGraph") {
        group = "verification"
        doLast {
            verifyRouteContractPilotGraph()
            println "ROUTECONTRACT_GRADLE_GRAPH VERIFIED"
        }
    }

    tasks.named(pilot.compileJavaTaskName, JavaCompile) {
        javaCompiler = javaToolchains.compilerFor {
            languageVersion = JavaLanguageVersion.of(17)
        }
        options.release = 17
    }
    def routeContractCandidateFile = layout.buildDirectory
            .file("routecontract/orders.find-by-user-id.candidate.json")
    def routeContractReportFile = layout.buildDirectory
            .file("test-results/routeContractPilot/TEST-com.example.orders.OrderQueryIntegrationTest.xml")
    def routeContractBuildRoot = layout.buildDirectory.get().asFile.toPath()
            .toAbsolutePath().normalize()
    def expectedRouteContractBuildRoot = projectDir.toPath().resolve("build")
            .toAbsolutePath().normalize()
    if (routeContractBuildRoot != expectedRouteContractBuildRoot) {
        throw new GradleException(
                "This verified pilot lane requires the owning module's default build directory")
    }
    def routeContractPilotPrepare = tasks.register("routeContractPilotPrepare") {
        group = "verification"
        doLast {
            [routeContractCandidateFile, routeContractReportFile].each { fileProvider ->
                def path = fileProvider.get().asFile.toPath()
                        .toAbsolutePath().normalize()
                if (!path.startsWith(routeContractBuildRoot)
                        || path == routeContractBuildRoot) {
                    throw new GradleException(
                            "Pilot evidence path must stay below the build directory: ${path}")
                }
                def ancestor = path.parent
                while (ancestor != null && ancestor.startsWith(routeContractBuildRoot)) {
                    if (java.nio.file.Files.isSymbolicLink(ancestor)
                            || (java.nio.file.Files.exists(
                                    ancestor, java.nio.file.LinkOption.NOFOLLOW_LINKS)
                                    && !java.nio.file.Files.isDirectory(
                                            ancestor,
                                            java.nio.file.LinkOption.NOFOLLOW_LINKS))) {
                        throw new GradleException(
                                "Refusing to traverse a non-directory or symlink " +
                                        "pilot evidence ancestor: ${ancestor}")
                    }
                    if (ancestor == routeContractBuildRoot) {
                        break
                    }
                    ancestor = ancestor.parent
                }
                if (java.nio.file.Files.isSymbolicLink(path)
                        || (java.nio.file.Files.exists(
                                path, java.nio.file.LinkOption.NOFOLLOW_LINKS)
                                && !java.nio.file.Files.isRegularFile(
                                        path, java.nio.file.LinkOption.NOFOLLOW_LINKS))) {
                    throw new GradleException(
                            "Refusing to replace a non-regular pilot evidence path: ${path}")
                }
                java.nio.file.Files.deleteIfExists(path)
            }
        }
    }
    tasks.register("routeContractPilot", Test) {
        group = "verification"
        dependsOn(routeContractPilotPrepare)
        testClassesDirs = pilot.output.classesDirs
        classpath = pilot.runtimeClasspath
        javaLauncher = javaToolchains.launcherFor {
            languageVersion = JavaLanguageVersion.of(17)
        }
        useJUnitPlatform()
        systemProperty "routecontract.projectDir", projectDir.absolutePath
        systemProperty "routecontract.candidateRoot", "build/routecontract"
        systemProperty "routecontract.artifactJarName", "routecontract-shardingsphere-5.5-0.1.2.jar"
        doFirst {
            def artifactPath = verifyRouteContractPilotGraph()
            systemProperty "routecontract.artifactJarPath", artifactPath.toRealPath().toString()
        }
    }
}
```

This lane reuses the representative fixture's existing test dependencies, including its exact
ShardingSphere-JDBC 5.5.3 edge; do not add a second ShardingSphere dependency or change the
project-wide Java toolchain or dependency management. Its configuration-local enforced Jackson
BOM, Calcite/minidev constraints, and exact exclusions apply only to this opt-in source set.
Inspect the complete
`routeContractPilotRuntimeClasspath` before adding the test, then require the dedicated graph task
to verify the exact RouteContract JAR SHA-256, every resolved ShardingSphere artifact at 5.5.3, the
reviewed Jackson/Calcite versions, any minidev artifacts when present, and the forbidden dependency
set. A missing runtime
module or incompatible graph is a blocker, not a successful integration. If the repository uses dependency locks or
verification metadata, update them through its normal reviewed process and never disable them.
Gradle's dependency-report task can still exit `0` while printing `FAILED` or another unresolved
node: stop if either appears, and do not treat `BUILD SUCCESSFUL`
alone as a usable graph. The dedicated graph task is the mechanical decision; the dependency
report remains the human-readable review record.

The `SourceSet` already owns Gradle's conventional `src/routeContractPilot/java` and
`src/routeContractPilot/resources` paths; do not add those same paths again. Before the selected
test task, the dedicated preparation task removes only its exact generated candidate and exact
JUnit XML report after proving each path stays below the build directory and refusing a symlink or
non-directory at every existing ancestor through that build root. It also refuses a symlink or
non-regular evidence file. It still runs when the test has no sources, so stale evidence cannot
satisfy the shell postconditions. It never deletes, creates, or replaces the approved manifest
under `src/routeContractPilot/resources`, so both the first review run and every approved rerun
start from a fresh capture without turning approval into automation.

The copy-paste lane also fails closed when the owning module changes Gradle's default `build`
directory because its Java system property and shell postconditions use that literal path. If the
project uses a custom build directory, adapt the provider paths, candidate root, JUnit XML path,
and shell postconditions together and verify that adapted lane before relying on it.

If `settings.gradle` enforces `RepositoriesMode.FAIL_ON_PROJECT_REPOS`, place the same conditional
`exclusiveContent` repository in the existing `dependencyResolutionManagement` block instead; the
repository path must not be read when the pilot property is absent. If the repository cannot
isolate this lane, stop and report that fit blocker rather than weakening repository policy.

### Gradle Kotlin DSL opt-in lane

The repository includes a runnable
[Gradle Kotlin DSL pilot](../examples/gradle-kotlin-pilot/README.md). Its `build.gradle.kts` contains
the complete adaptation block between `ROUTECONTRACT_KOTLIN_DSL_START` and
`ROUTECONTRACT_KOTLIN_DSL_END`; a contract test requires this guide to keep pointing at those
tested bytes. The block uses fully qualified Gradle types and the explicitly aliased JDK types in
the prelude below, and the verifier extracts those
exact marker-bounded bytes into a fresh script with only this tested prelude:

```kotlin
import java.nio.file.Files as JFiles
import java.nio.file.LinkOption as JLinkOption
import java.nio.file.Path as JPath
import java.security.MessageDigest as JMessageDigest
import java.util.HexFormat as JHexFormat

plugins { java }

repositories { mavenCentral() }
```

The lane uses the same inactive-by-default source-set, exclusive local-Maven-repository isolation,
exact GAV resolution, canonical coordinate JAR and POM paths and hashes, dependency graph, evidence
cleanup, candidate, and human-approval boundaries as the Groovy lane. The exclusive-content filter
prevents the RouteContract module from falling back to Maven Central. Unlike a target's ordinary
test configuration, the pilot configuration declares its own exact
ShardingSphere-JDBC 5.5.3, MySQL Connector/J 26.7.0, Testcontainers 1.21.4, JUnit 5.14.3, and JUnit
Platform 1.14.3 dependencies. The complete fixture has been exercised with the repository's
SHA-256-pinned Gradle 8.14.4 wrapper, Java 17, and the digest-pinned MySQL 8.4.11 image. This does
not claim compatibility with another Gradle release.

Run the internal verifier against an already downloaded exact `v0.1.2` Release-asset directory:

```bash
./scripts/verify-gradle-kotlin-pilot.sh \
  --release-assets-dir "/absolute/path/to/routecontract-release-assets" \
  --provenance-output "/absolute/path/to/absent/gradle-kotlin-provenance.json"
```

For an external repository, copy the tested prelude if it is not already present and then copy the
full marker-bounded block into the owning module's `build.gradle.kts`. Adapt only the
operation-specific candidate and JUnit-report paths. Pass `routecontractRepository` as an absolute
local filesystem directory whose real path is identical and contains no symlink component; do not
pass a `file:` URI. The exact coordinate JAR must also be a real regular file below that directory.
The pilot task independently requests a Java 17 launcher and compiler but does not provision a
JDK. A preinstalled JDK 17 is required. If the target has only a newer toolchain, stop and report
that fit blocker rather than claiming this fixture covers it. A passing local fixture is not
evidence that a different Java-21-only target is integrated. Do not lower the normal toolchain
merely to make this pilot pass.

Use the same reusable Gradle commands and success marker as the Groovy lane, replacing
`:owning-module` with the actual project path:

```bash
ROUTECONTRACT_REPOSITORY=/absolute/real/path/to/routecontract-maven \
  ./gradlew -ProutecontractPilot=true \
  :owning-module:dependencies --configuration routeContractPilotRuntimeClasspath
ROUTECONTRACT_REPOSITORY=/absolute/real/path/to/routecontract-maven \
  ./gradlew -ProutecontractPilot=true :owning-module:routeContractPilotGraph
test "$(ROUTECONTRACT_REPOSITORY=/absolute/real/path/to/routecontract-maven \
  ./gradlew -q -ProutecontractPilot=true :owning-module:routeContractPilotGraph \
  | grep -Fxc 'ROUTECONTRACT_GRADLE_GRAPH VERIFIED')" -eq 1
ROUTECONTRACT_REPOSITORY=/absolute/real/path/to/routecontract-maven \
  ./gradlew -ProutecontractPilot=true --no-build-cache --rerun-tasks \
  :owning-module:routeContractPilot
```

The checked-in fixture bootstraps one immutable wrapper-pinned Gradle 8.14.4 distribution, then
gives the marker, repository-path, GAV-negative, profile-off, GAV-origin, graph, missing-baseline,
and matched cases separate HOME, temporary, Gradle-user-home, and project-cache directories under
an `env -i` allowlist. An origin-only, non-transitive fresh-cache configuration proves exact
RouteContract GAV selection. A valid ordinary decoy cannot rescue an incomplete designated
repository, and a poisoned ordinary decoy is ignored when the designated repository is valid. It
also rejects wrong, missing-metadata, POM-tampered, and JAR-tampered designated GAV layouts before
accepting the exact opt-in graph. The full dependency graph and MySQL operation remain online and
enforce the listed selected invariants; this is not a claim of a locked, hermetic full dependency
closure. The test JVM verifies the JAR/POM hashes and API/provider/SPI origins before MySQL or the
representative RouteContract operation starts, and rehashes immediately around that operation.
The live runtime observation uses temporary paths and is validated before cleanup. The preserved
path-free JSON receipt records exact artifact identities, toolchain/wrapper pins, source-binding
status, candidate/JUnit/runtime-observation hashes, and the deletion boundary; it does not claim
that the temporary JAR, POM, caches, or reports remain available. It keeps `externalUser`,
`humanApprovedBaseline`, `adoption`, and `endorsement` false. The synthetic copy remains CI
scaffolding rather than human approval or external adoption. A target repository that only runs H2,
including H2 `MODE=MySQL`, still has only `verified - H2` evidence;
that mode does not satisfy the published MySQL 8.4.11 boundary.

### Maven 3.9.14 opt-in profile lane

The repository includes a runnable [two-module Maven pilot](../examples/maven-pilot/README.md) for
the Maven path. It verifies the profile-off build and an opt-in test profile with Apache Maven
3.9.14, Java 17, ShardingSphere-JDBC 5.5.3, and MySQL 8.4.11. It also verifies a fresh private
consumer cache, repository-scoped SHA-256 transfer validation, a corrupted-checksum rejection,
candidate creation, the explicit missing-baseline failure, and a separate mechanical match run.
That same-checkout fixture and its synthetic match are CI scaffolding, not human approval or
external adoption.

Use this lane only when the representative operation is already a synchronous Surefire integration
test in one owning module and its resolved graph can preserve the tested
boundary. The checked-in fixture pins Jackson 2.18.9 and Calcite Core/linq4j 1.42.0,
pins `json-smart` 2.4.10 and `accessors-smart` 2.4.9 when either artifact is present,
and excludes `jts-io-common` and `protobuf-java`. A different ShardingSphere version, an unresolved node, an incompatible graph,
or a framework that needs RouteContract in a production runtime classloader is a fit blocker for
this generic lane. Do not copy the fixture's dependency-management block into a production graph
without reviewing its effect.

The immutable `v0.1.2` installer writes only the four Maven artifacts. Before Maven consumes that
repository, create exact Maven checksum sidecars with the helper introduced after `v0.1.2`. The
exact helper is downloaded separately because the immutable tag cannot contain a later file; its
transport URL is pinned to the exact bridge implementation commit and accepted only with the fixed
helper digest below.
The helper rebinds each installed artifact to both immutable SHA-1 and SHA-256 values, uses
no-follow file descriptors, refuses every existing sidecar or extra file, and publishes an exact
twelve-file coordinate inventory. It is POSIX-only and assumes a private, single-writer directory;
if it fails, keep that directory for inspection and repeat the Release installation into another
absent destination rather than repairing it in place.

```bash
(
set -euo pipefail
repository_dir="/absolute/path/to/routecontract-maven"
checksum_helper="/absolute/path/to/new-prepare_maven_v0_1_2_checksums.py"
checksum_helper_url="https://raw.githubusercontent.com/ym0506/routecontract/2264b6e6292ee80f131148f2acef601cbaede096/scripts/prepare_maven_v0_1_2_checksums.py"
expected_checksum_helper_sha256="ee1928e578819fb597fffe7f1c72c055ff74ec6b36d37fe35f29c7fbd382b7b7"

test ! -e "${checksum_helper}"
test ! -L "${checksum_helper}"
curl --disable --proto '=https' --tlsv1.2 --fail --location \
  --silent --show-error --retry 3 --connect-timeout 15 --max-time 120 \
  --remove-on-error --max-filesize 131072 \
  --output "${checksum_helper}" \
  "${checksum_helper_url}"
test -f "${checksum_helper}"
test ! -L "${checksum_helper}"
actual_checksum_helper_sha256="$(python3 -I -c \
  'import hashlib,pathlib,sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' \
  "${checksum_helper}")"
test "${actual_checksum_helper_sha256}" = "${expected_checksum_helper_sha256}"
python3 -I "${checksum_helper}" --repository "${repository_dir}"
)
```

Keep every pilot-only graph control inside an inactive-by-default profile in the owning module.
Do not override the module's normal Surefire includes. The separate source root keeps the pilot
test out of default compilation. Copy the complete profile boundary below: the Jackson BOM,
direct pilot dependencies, versions, scopes, and exclusions are part of the verified contract, not
optional fixture detail. With the profile inactive, none of these controls changes the production
dependency graph.

```xml
<profile>
  <id>routecontract-pilot</id>
  <activation>
    <property>
      <name>routecontractPilot</name>
      <value>true</value>
    </property>
  </activation>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.fasterxml.jackson</groupId>
        <artifactId>jackson-bom</artifactId>
        <version>2.18.9</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
      <dependency>
        <groupId>org.apache.calcite</groupId>
        <artifactId>calcite-core</artifactId>
        <version>1.42.0</version>
      </dependency>
      <dependency>
        <groupId>org.apache.calcite</groupId>
        <artifactId>calcite-linq4j</artifactId>
        <version>1.42.0</version>
      </dependency>
      <dependency>
        <groupId>net.minidev</groupId>
        <artifactId>json-smart</artifactId>
        <version>2.4.10</version>
      </dependency>
      <dependency>
        <groupId>net.minidev</groupId>
        <artifactId>accessors-smart</artifactId>
        <version>2.4.9</version>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <repositories>
    <repository>
      <id>routecontract-verified-file-repository</id>
      <url>${routecontractRepositoryUrl}</url>
      <releases>
        <enabled>true</enabled>
        <updatePolicy>never</updatePolicy>
        <checksumPolicy>fail</checksumPolicy>
      </releases>
      <snapshots>
        <enabled>false</enabled>
      </snapshots>
    </repository>
  </repositories>
  <dependencies>
    <dependency>
      <groupId>io.github.ym0506.routecontract</groupId>
      <artifactId>routecontract-shardingsphere-5.5</artifactId>
      <version>0.1.2</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.apache.shardingsphere</groupId>
      <artifactId>shardingsphere-jdbc</artifactId>
      <version>5.5.3</version>
      <scope>compile</scope>
      <exclusions>
        <exclusion>
          <groupId>org.locationtech.jts.io</groupId>
          <artifactId>jts-io-common</artifactId>
        </exclusion>
        <exclusion>
          <groupId>com.google.protobuf</groupId>
          <artifactId>protobuf-java</artifactId>
        </exclusion>
      </exclusions>
    </dependency>
    <dependency>
      <groupId>org.apache.calcite</groupId>
      <artifactId>calcite-core</artifactId>
      <version>1.42.0</version>
      <scope>compile</scope>
      <exclusions>
        <exclusion>
          <groupId>org.locationtech.jts.io</groupId>
          <artifactId>jts-io-common</artifactId>
        </exclusion>
        <exclusion>
          <groupId>com.google.protobuf</groupId>
          <artifactId>protobuf-java</artifactId>
        </exclusion>
      </exclusions>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>build-helper-maven-plugin</artifactId>
        <version>3.6.1</version>
        <executions>
          <execution>
            <id>add-routecontract-pilot-source</id>
            <phase>generate-test-sources</phase>
            <goals><goal>add-test-source</goal></goals>
            <configuration>
              <sources><source>src/routeContractPilot/java</source></sources>
            </configuration>
          </execution>
        </executions>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.4</version>
        <configuration>
          <systemPropertyVariables>
            <routecontract.projectDir>${project.basedir}</routecontract.projectDir>
            <routecontract.candidateRoot>target/routecontract</routecontract.candidateRoot>
            <routecontract.artifactJarName>routecontract-shardingsphere-5.5-0.1.2.jar</routecontract.artifactJarName>
            <routecontract.artifactJarPath>${routecontract.artifactJarPath}</routecontract.artifactJarPath>
          </systemPropertyVariables>
        </configuration>
      </plugin>
    </plugins>
  </build>
</profile>
```

If the owning POM already has a production `shardingsphere-jdbc` dependency, leave that base
declaration unchanged. The profile-local declaration above intentionally repeats the same Maven
dependency key with the exact 5.5.3 version, its existing compile scope, and pilot exclusions;
Maven applies that override only while `routecontractPilot=true`. If the existing edge is runtime
or test scoped, preserve that scope in the profile-local copy instead of changing it merely for the
pilot. The profile-local dependency management pins Calcite and any minidev artifacts that are
present while preserving their resolved compile, runtime, or test scopes. Confirm that the
profile-off build remains
RouteContract-free, then require the profile-on parser below to observe exactly one direct,
unclassified JDBC JAR. If another direct production dependency still introduces `jts-io-common`
or `protobuf-java`, repeat that dependency inside this inactive profile with its production
version and scope plus the matching exclusion. Do not edit the base dependency merely to make the
pilot pass. If the resulting isolated graph cannot satisfy the parser, stop and report the fit
blocker.

Every onboarding attempt must begin with a new explicit consumer cache and the
repository-ID-scoped Resolver option below. The graph step may reuse that cache only after the
profile-off absence check. The graph can then populate the RouteContract POM; verify that POM's
hash, SHA-256 sidecar, and repository binding before the candidate step reuses the cache. After the
candidate step, verify both the cached JAR and POM the same way. Never share the cache across jobs or
repositories. Maven 3.9.14 selects the first available configured checksum algorithm; with this
option that is SHA-256. The presence of both sidecar types does not mean that one transfer validated
both. Maven has no Gradle `exclusiveContent` equivalent, so inspect the complete graph and the
cache's `_remote.repositories` binding instead of claiming group-exclusive resolution.

For a multi-module reactor, first run and install the profile-off reactor slice through the owning
module, then invoke only the owning module with the test selector. Passing `-Dtest`
together with `-am` can make upstream modules fail because they do not contain that test. Replace
every placeholder below and keep the new cache absent before the first command:

```bash
set -euo pipefail
consumer_cache="/absolute/path/to/new-routecontract-maven-consumer-cache"
repository_dir="/absolute/path/to/routecontract-maven"
reactor_pom="/absolute/path/to/your-repository/pom.xml"
owning_pom="/absolute/path/to/your-repository/owning-module/pom.xml"
profile_off_evidence="/absolute/path/to/your-repository/owning-module/target/surefire-reports/TEST-com.example.orders.ExistingBusinessTest.xml"
profile_off_class="com.example.orders.ExistingBusinessTest"
profile_off_method="existingBusinessBehaviorRemainsGreen"
expected_maven_line="Apache Maven 3.9.14 (996c630dbc656c76214ce58821dcc58be960875b)"
expected_jar_sha256="d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc"
expected_pom_sha256="70b5d4161d1532e9f9cb699071790a7806d87658511d931477544fa06037b85d"
repository_id="routecontract-verified-file-repository"
coordinate_dir="${consumer_cache}/io/github/ym0506/routecontract/routecontract-shardingsphere-5.5/0.1.2"
cached_jar="${coordinate_dir}/routecontract-shardingsphere-5.5-0.1.2.jar"
cached_pom="${coordinate_dir}/routecontract-shardingsphere-5.5-0.1.2.pom"
graph_log="/absolute/path/to/new-routecontract-maven-dependency-tree.log"
repository_uri="$(python3 -I -c \
  'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True).as_uri())' \
  "${repository_dir}")"
maven_version="$(mvn -version 2>&1)"
sha256_file() {
  python3 -I -c \
    'import hashlib,pathlib,sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' \
    "$1"
}

test ! -e "${consumer_cache}"
test ! -L "${consumer_cache}"
test ! -e "${graph_log}"
test ! -L "${graph_log}"
printf '%s\n' "${maven_version}" | grep -Fqx "${expected_maven_line}"
printf '%s\n' "${maven_version}" | grep -Eq '^Java version: 17\.'
mvn -B -ntp -f "${reactor_pom}" \
  "-Dmaven.repo.local=${consumer_cache}" \
  -P=-routecontract-pilot \
  -DskipTests=false \
  -Dmaven.test.skip=false \
  -Dmaven.test.failure.ignore=false \
  -pl your.group.id:owning-artifact-id -am clean install
test -f "${profile_off_evidence}"
test ! -L "${profile_off_evidence}"
python3 -I - "${profile_off_evidence}" "${profile_off_class}" "${profile_off_method}" <<'PY'
import pathlib
import sys
import xml.etree.ElementTree as ET

report = pathlib.Path(sys.argv[1])
root = ET.fromstring(report.read_bytes())
assert root.attrib.get("failures") == "0"
assert root.attrib.get("errors") == "0"
matches = [
    case for case in root.findall("testcase")
    if case.attrib.get("classname") == sys.argv[2]
    and case.attrib.get("name") == sys.argv[3]
]
assert len(matches) == 1
assert not matches[0].findall("failure")
assert not matches[0].findall("error")
assert not matches[0].findall("skipped")
PY
routecontract_cache_root="${consumer_cache}/io/github/ym0506/routecontract/routecontract-shardingsphere-5.5"
test ! -e "${routecontract_cache_root}"
test ! -L "${routecontract_cache_root}"

mvn -B -ntp -Dstyle.color=never -f "${owning_pom}" \
  "-Dmaven.repo.local=${consumer_cache}" \
  -DroutecontractPilot=true \
  "-DroutecontractRepositoryUrl=${repository_uri}" \
  "-Droutecontract.artifactJarPath=${cached_jar}" \
  -Daether.checksums.algorithms.routecontract-verified-file-repository=SHA-256 \
  -DskipTests=false \
  -Dmaven.test.skip=false \
  -Dmaven.test.failure.ignore=false \
  -Dtest=com.example.orders.OrderQueryIntegrationTest#keepsTheApprovedExecutionStructure \
  org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree >"${graph_log}" 2>&1

test -f "${graph_log}"
test ! -L "${graph_log}"
if grep -Eiq \
  'Could not validate integrity|Checksum validation failed|no checksums available' \
  "${graph_log}"; then
  printf 'successful Maven graph log contains an integrity warning: %s\n' "${graph_log}" >&2
  exit 1
fi
python3 -I - "${graph_log}" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
pattern = re.compile(
    r"^(?P<prefix>(?:(?:\|  | {3})*(?:\+- |\\- ))?)"
    r"(?P<group>[A-Za-z0-9_.-]+):(?P<artifact>[A-Za-z0-9_.-]+):"
    r"(?P<type>[A-Za-z0-9_.-]+):(?:(?P<classifier>[^:\s]+):)?"
    r"(?P<version>[^:\s]+):(?P<scope>[^:\s]+)(?:\s.*)?$"
)
root_pattern = re.compile(
    r"(?P<group>[A-Za-z0-9_.-]+):(?P<artifact>[A-Za-z0-9_.-]+):"
    r"(?P<type>[A-Za-z0-9_.-]+):(?P<version>[^:\s]+)"
)
section_pattern = re.compile(
    r"^\[INFO\] --- (?:dependency|maven-dependency-plugin):3\.11\.0:tree "
    r"\([^)]*\) @ [^ ]+ ---$"
)
sections = []
current = None
for line in text.splitlines():
    if section_pattern.fullmatch(line):
        if current is not None:
            sections.append(current)
        current = {"roots": [], "coordinates": [], "root_seen": False}
        continue
    if current is None:
        continue
    if line.startswith("[INFO] --- "):
        sections.append(current)
        current = None
        continue
    if not line.startswith("[INFO] "):
        continue
    payload = line[len("[INFO] "):]
    root_match = root_pattern.fullmatch(payload)
    if root_match:
        if current["root_seen"]:
            raise SystemExit("dependency-tree section contains more than one project root")
        current["root_seen"] = True
        current["roots"].append(root_match.groupdict())
        continue
    match = pattern.fullmatch(payload)
    if match:
        if not current["root_seen"]:
            raise SystemExit("dependency coordinate appeared before the project root")
        prefix = match.group("prefix")
        depth = 0 if not prefix else 1 + (len(prefix) - 3) // 3
        current["coordinates"].append({
            "prefix": prefix,
            "depth": depth,
            "group": match.group("group"),
            "artifact": match.group("artifact"),
            "type": match.group("type"),
            "classifier": match.group("classifier"),
            "version": match.group("version"),
            "scope": match.group("scope"),
        })
if current is not None:
    sections.append(current)
if len(sections) != 1 or len(sections[0]["roots"]) != 1:
    raise SystemExit("expected exactly one dependency-tree plugin section and one project root")
coordinates = sections[0]["coordinates"]
if not coordinates:
    raise SystemExit("no Maven dependency coordinates were parsed")
versions = {coordinate["version"] for coordinate in coordinates
            if coordinate["group"] == "org.apache.shardingsphere"}
if versions != {"5.5.3"}:
    raise SystemExit(f"unexpected ShardingSphere versions: {sorted(versions)}")

def require_exact_dependency(
        expected, *, expected_depth, allowed_scopes, required=True):
    group, artifact, version = expected
    matches = [
        coordinate for coordinate in coordinates
        if (coordinate["group"], coordinate["artifact"]) == (group, artifact)
    ]
    if not matches and not required:
        return
    if len(matches) != 1 or any(
        coordinate["type"] != "jar"
        or coordinate["classifier"] is not None
        or coordinate["version"] != version
        or coordinate["scope"] not in allowed_scopes
        or (expected_depth is not None and coordinate["depth"] != expected_depth)
        for coordinate in matches
    ):
        relationship = "direct " if expected_depth == 1 else ""
        raise SystemExit(
            f"expected exactly one {relationship}unclassified JAR "
            f"{group}:{artifact}:{version}, found {matches}"
        )

require_exact_dependency(
    (
        "io.github.ym0506.routecontract",
        "routecontract-shardingsphere-5.5",
        "0.1.2",
    ),
    expected_depth=1,
    allowed_scopes={"test"},
)
require_exact_dependency(
    ("org.apache.shardingsphere", "shardingsphere-jdbc", "5.5.3"),
    expected_depth=1,
    allowed_scopes={"compile", "runtime", "test"},
)
for expected in (
    ("org.apache.calcite", "calcite-core", "1.42.0"),
    ("org.apache.calcite", "calcite-linq4j", "1.42.0"),
):
    require_exact_dependency(
        expected,
        expected_depth=None,
        allowed_scopes={"compile", "runtime", "test"},
    )
for expected in (
    ("net.minidev", "json-smart", "2.4.10"),
    ("net.minidev", "accessors-smart", "2.4.9"),
):
    require_exact_dependency(
        expected,
        expected_depth=None,
        allowed_scopes={"compile", "runtime", "test"},
        required=False,
    )
def is_fasterxml_jackson(group):
    return group == "com.fasterxml.jackson" or group.startswith("com.fasterxml.jackson.")

jackson_versions = {
    coordinate["version"] for coordinate in coordinates
    if is_fasterxml_jackson(coordinate["group"])
}
if jackson_versions != {"2.18.9"}:
    raise SystemExit(f"unexpected FasterXML Jackson versions: {sorted(jackson_versions)}")
jackson = [
    coordinate for coordinate in coordinates
    if is_fasterxml_jackson(coordinate["group"])
]
if any(
    coordinate["type"] != "jar"
    or coordinate["classifier"] is not None
    or coordinate["scope"] not in {"compile", "runtime", "test"}
    for coordinate in jackson
):
    raise SystemExit("FasterXML Jackson dependencies must be unclassified JARs in an allowed scope")
forbidden = {
    ("org.locationtech.jts.io", "jts-io-common"),
    ("com.google.protobuf", "protobuf-java"),
}
present_forbidden = sorted({
    (coordinate["group"], coordinate["artifact"])
    for coordinate in coordinates
    if (coordinate["group"], coordinate["artifact"]) in forbidden
})
if present_forbidden:
    raise SystemExit(f"resolved graph contains forbidden dependencies {present_forbidden}")
PY

test -f "${cached_pom}"
test ! -L "${cached_pom}"
test "$(sha256_file "${cached_pom}")" = "${expected_pom_sha256}"
test "$(tr -d '\n' < "${cached_pom}.sha256")" = "${expected_pom_sha256}"
grep -Fqx \
  "routecontract-shardingsphere-5.5-0.1.2.pom>${repository_id}=" \
  "${coordinate_dir}/_remote.repositories"
```

The first command must run the normal tests in that reactor slice and remain RouteContract-free.
Point `profile_off_evidence` at the exact repository-specific Surefire XML report below a directory
that `clean` removes; its parsed, non-skipped testcase proves that expected normal test ran.
Maven success alone is not that proof. The cache begins absent but intentionally warms ordinary
project dependencies; the explicit path check proves that the RouteContract coordinate is still
absent before profile-on resolution. In the second command, verify the exact
RouteContract coordinate occurs once, all ShardingSphere artifacts are 5.5.3, the reviewed
Jackson/Calcite versions and any present minidev artifacts are exact, forbidden dependencies are
absent, and no checksum warning appears. Then use the
same module-only invocation for the representative Surefire test. Failsafe, a different test
runner, Surefire `additionalClasspath*` injection, or a custom runtime classloader remains a fit
blocker until a matching executable fixture
exists. The explicit false-valued skip and failure-ignore properties are defensive. The
profile-off suite counts must also remain failure/error-free, and every selected-test report below
verifies its exact suite counts and testcase outcome, so a failure-ignored or skipped suite cannot
pass as evidence. The report and candidate postconditions are the final controls against a
zero-test build.

## 3. Add one representative operation

Choose one deterministic integration test whose business result is already asserted. Adapt the
query line, expected result, operation ID, observed data-source name, stable non-sensitive alias,
and reviewed budgets in this example. Do not remove or weaken the business assertion.

```java
import io.github.ym0506.routecontract.RouteAssertions;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteSnapshot;
import io.github.ym0506.routecontract.manifest.DataSourceAliases;
import io.github.ym0506.routecontract.manifest.ManifestAssertions;
import io.github.ym0506.routecontract.manifest.ManifestPolicy;
import io.github.ym0506.routecontract.manifest.ManifestStore;
import io.github.ym0506.routecontract.manifest.ManifestVerifier;
import io.github.ym0506.routecontract.manifest.ObservedExecutionManifest;
import org.junit.jupiter.api.Test;

import java.net.JarURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

private static final String SERVICE_DESCRIPTOR =
        "META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook";
private static final String PROVIDER_CLASS =
        "io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook";
private static final String ARTIFACT_JAR_NAME =
        System.getProperty("routecontract.artifactJarName");
private static final String ARTIFACT_JAR_PATH =
        System.getProperty("routecontract.artifactJarPath");

@Test
void keepsTheApprovedExecutionStructure() throws Exception {
    Path expectedArtifactJar = expectedArtifactJar();
    assertEquals(expectedArtifactJar, classOrigin(RouteContract.class),
            "RouteContract must be loaded from the exact cached Release JAR");
    Class<?> providerClass = Class.forName(
            PROVIDER_CLASS, false, Thread.currentThread().getContextClassLoader());
    assertEquals(expectedArtifactJar, classOrigin(providerClass),
            "the SPI provider class must be loaded from the exact cached Release JAR");
    assertEquals(List.of(expectedArtifactJar), matchingServiceDescriptorJars(),
            "the pilot must expose exactly one matching provider descriptor "
                    + "from the exact cached Release JAR");

    Path projectDir = Path.of(System.getProperty("routecontract.projectDir"))
            .toAbsolutePath()
            .normalize();
    Path approvedPath = projectDir.resolve(
            "src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json");
    String candidateRoot = System.getProperty("routecontract.candidateRoot");
    if (candidateRoot == null || candidateRoot.isBlank()) {
        fail("routecontract.candidateRoot must be set by the isolated pilot task");
    }
    Path candidateRootPath = Path.of(candidateRoot);
    if (candidateRootPath.isAbsolute()) {
        fail("routecontract.candidateRoot must be relative to the owning module");
    }
    Path candidateDirectory = projectDir.resolve(candidateRootPath).normalize();
    if (!candidateDirectory.startsWith(projectDir) || candidateDirectory.equals(projectDir)) {
        fail("routecontract.candidateRoot must stay below the owning module");
    }
    Path candidatePath = candidateDirectory
            .resolve("orders.find-by-user-id.candidate.json");
    if (Files.exists(candidatePath) || Files.isSymbolicLink(candidatePath)) {
        fail("Stale candidate exists before capture: " + candidatePath);
    }
    ManifestStore store = new ManifestStore();

    int reviewedMaxAttempts = 1;
    int reviewedMaxDataSources = 1;
    ManifestPolicy policy = ManifestPolicy.strict(
            reviewedMaxAttempts,
            reviewedMaxDataSources); // Explicit reviewed constants on every run.

    RouteSnapshot snapshot = RouteContract.capture("orders.find-by-user-id", () -> {
        long actualId = orderQueryService.findByUserId(3L).id(); // Adapt one real operation.
        assertEquals(201L, actualId); // Keep the existing business assertion.
    });

    RouteAssertions.assertThat(snapshot)
            .hasCompleteCapture()
            .hasNoReportedExecutionFailures();

    DataSourceAliases aliases = DataSourceAliases.of(Map.of(
            "ds_0", "orders-shard-a",
            "ds_1", "orders-shard-b")); // Map the reviewed expected target universe.
    ObservedExecutionManifest candidate = ObservedExecutionManifest.from(
            snapshot, aliases, policy);
    store.writeCandidate(approvedPath, candidatePath, candidate);

    if (Files.notExists(approvedPath)) {
        // A first-run candidate that exceeds the proposed policy must fail before approval.
        RouteAssertions.assertThat(snapshot)
                .hasAtMostObservedPhysicalAttempts(reviewedMaxAttempts)
                .hasAtMostDistinctObservedDataSourceNames(reviewedMaxDataSources);
        fail("No approved baseline. Review " + candidatePath
                + " and copy it to " + approvedPath + " only after human approval.");
    }

    ManifestAssertions.assertMatched(
            new ManifestVerifier().verify(store.read(approvedPath), candidate));
}

private static Path expectedArtifactJar() throws Exception {
    assertEquals("routecontract-shardingsphere-5.5-0.1.2.jar", ARTIFACT_JAR_NAME);
    if (ARTIFACT_JAR_PATH == null || ARTIFACT_JAR_PATH.isBlank()) {
        fail("routecontract.artifactJarPath must identify the exact cached Release JAR");
    }
    Path configured = Path.of(ARTIFACT_JAR_PATH);
    if (!configured.isAbsolute() || Files.isSymbolicLink(configured)) {
        fail("routecontract.artifactJarPath must be an absolute non-symlink path");
    }
    Path actual = configured.toRealPath();
    assertEquals(ARTIFACT_JAR_NAME, actual.getFileName().toString());
    return actual;
}

private static Path classOrigin(Class<?> type) throws Exception {
    var codeSource = type.getProtectionDomain().getCodeSource();
    if (codeSource == null || !"file".equals(codeSource.getLocation().getProtocol())) {
        fail(type.getName() + " must expose a file-backed code source");
    }
    return Path.of(codeSource.getLocation().toURI()).toRealPath();
}

private static List<Path> matchingServiceDescriptorJars() throws Exception {
    Enumeration<URL> descriptors = Thread.currentThread()
            .getContextClassLoader()
            .getResources(SERVICE_DESCRIPTOR);
    List<Path> result = new ArrayList<>();
    while (descriptors.hasMoreElements()) {
        URL descriptor = descriptors.nextElement();
        var connection = descriptor.openConnection();
        String content;
        try (var stream = connection.getInputStream()) {
            content = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }
        if (content.lines().map(String::trim).anyMatch(PROVIDER_CLASS::equals)) {
            if (!(connection instanceof JarURLConnection)) {
                fail("matching RouteContract provider descriptor must come from a JAR");
            }
            JarURLConnection jarConnection = (JarURLConnection) connection;
            result.add(Path.of(jarConnection.getJarFileURL().toURI()).toRealPath());
        }
    }
    return result;
}
```

`RouteContract.capture` observes physical JDBC execution attempts reported through
ShardingSphere-JDBC 5.5.3 `SQLExecutionHook`. It does not expose a complete route plan, decide SQL
semantic equivalence, or prove completion of the surrounding JDBC operation, transaction commit,
or business success. The business assertion above remains the source of the business-result check.
RouteContract does not discover the complete target universe: define the expected mapping yourself,
keep every alias unique, review it with the baseline, and version changes to it. Never silently
rebind a different observed name to an existing alias. A data-source name outside that mapping
fails closed during candidate construction rather than being silently added. The mapping source
still contains the raw observed names even though manifests do not; use non-sensitive test-fixture
names in a public repository or keep that configuration private.

First inspect and mechanically verify the complete owning-module pilot graph, then run only the new
test with a fresh candidate capture. For Gradle, replace `:owning-module` with the actual project
path; use `:routeContractPilotGraph` and `:routeContractPilot` for a root project. Set
`gradle_project_dir` to that owning module's absolute directory, not the repository root unless the
root owns the test. Run this whole block as one standalone shell script so every postcondition is
enforced.

```bash
set -euo pipefail
gradle_project_dir="/absolute/path/to/owning-module"
candidate_path="${gradle_project_dir}/build/routecontract/orders.find-by-user-id.candidate.json"
report_path="${gradle_project_dir}/build/test-results/routeContractPilot/TEST-com.example.orders.OrderQueryIntegrationTest.xml"
approved_path="${gradle_project_dir}/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json"
graph_log="$(mktemp "${TMPDIR:-/tmp}/routecontract-gradle-graph.XXXXXX")"
test ! -e "${candidate_path}"
test ! -L "${candidate_path}"
test ! -e "${report_path}"
test ! -L "${report_path}"
test ! -e "${approved_path}"
test ! -L "${approved_path}"

ROUTECONTRACT_REPOSITORY="/absolute/path/to/routecontract-maven" \
  ./gradlew -ProutecontractPilot=true \
  :owning-module:dependencies \
  --configuration routeContractPilotRuntimeClasspath >"${graph_log}" 2>&1
if grep -Eq '(^|[[:space:]])FAILED([[:space:]]|$)|Could not resolve|UNRESOLVED' \
  "${graph_log}"; then
  printf 'Gradle dependency report is not usable: %s\n' "${graph_log}" >&2
  exit 1
fi

ROUTECONTRACT_REPOSITORY="/absolute/path/to/routecontract-maven" \
  ./gradlew -ProutecontractPilot=true \
  :owning-module:routeContractPilotGraph >>"${graph_log}" 2>&1
test "$(grep -Fxc 'ROUTECONTRACT_GRADLE_GRAPH VERIFIED' "${graph_log}")" -eq 1

first_run_status=0
set +e
ROUTECONTRACT_REPOSITORY="/absolute/path/to/routecontract-maven" \
  ./gradlew -ProutecontractPilot=true \
  --no-build-cache --rerun-tasks \
  :owning-module:routeContractPilot \
  --tests com.example.orders.OrderQueryIntegrationTest.keepsTheApprovedExecutionStructure
first_run_status=$?
set -e
test "${first_run_status}" -ne 0
test -s "${candidate_path}"
test -f "${candidate_path}"
test ! -L "${candidate_path}"
test -f "${report_path}"
test ! -L "${report_path}"
python3 -I - "${report_path}" "${candidate_path}" "${approved_path}" <<'PY'
import pathlib
import sys
import xml.etree.ElementTree as ET

report, candidate, approved = map(pathlib.Path, sys.argv[1:])
root = ET.fromstring(report.read_bytes())
cases = root.findall("testcase")
assert root.attrib.get("tests") == "1"
assert root.attrib.get("failures") == "1"
assert root.attrib.get("errors") == "0"
assert root.attrib.get("skipped") == "0"
assert len(cases) == 1
assert cases[0].attrib.get("classname") == "com.example.orders.OrderQueryIntegrationTest"
assert cases[0].attrib.get("name") == "keepsTheApprovedExecutionStructure()"
failures = cases[0].findall("failure")
assert len(failures) == 1
expected = (
    f"No approved baseline. Review {candidate} "
    f"and copy it to {approved} only after human approval."
)
assert expected in failures[0].attrib.get("message", "")
PY
test ! -e "${approved_path}"
test ! -L "${approved_path}"
```

For Maven, continue in the same shell as the complete Maven lane above so its verified variables and
`sha256_file` function remain available. Run the module alone so the selector is not applied to
upstream reactor modules:

```bash
set -euo pipefail
owning_dir="$(python3 -I -c \
  'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True).parent)' \
  "${owning_pom}")"
candidate_path="${owning_dir}/target/routecontract/orders.find-by-user-id.candidate.json"
approved_path="${owning_dir}/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json"
surefire_report="${owning_dir}/target/surefire-reports/TEST-com.example.orders.OrderQueryIntegrationTest.xml"
test ! -e "${candidate_path}"
test ! -L "${candidate_path}"
test ! -e "${surefire_report}"
test ! -L "${surefire_report}"
test ! -e "${approved_path}"
test ! -L "${approved_path}"

first_run_status=0
set +e
mvn -B -ntp -f "${owning_pom}" \
  "-Dmaven.repo.local=${consumer_cache}" \
  -DroutecontractPilot=true \
  "-DroutecontractRepositoryUrl=${repository_uri}" \
  "-Droutecontract.artifactJarPath=${cached_jar}" \
  -Daether.checksums.algorithms.routecontract-verified-file-repository=SHA-256 \
  -DskipTests=false \
  -Dmaven.test.skip=false \
  -Dmaven.test.failure.ignore=false \
  -Dtest=com.example.orders.OrderQueryIntegrationTest#keepsTheApprovedExecutionStructure \
  clean test
first_run_status=$?
set -e
test "${first_run_status}" -eq 1
test -f "${candidate_path}"
test ! -L "${candidate_path}"
test -f "${surefire_report}"
test ! -L "${surefire_report}"
python3 -I - "${surefire_report}" "${candidate_path}" "${approved_path}" <<'PY'
import pathlib
import sys
import xml.etree.ElementTree as ET

report = pathlib.Path(sys.argv[1])
root = ET.fromstring(report.read_bytes())
cases = root.findall("testcase")
assert root.attrib.get("tests") == "1"
assert root.attrib.get("failures") == "1"
assert root.attrib.get("errors") == "0"
assert root.attrib.get("skipped") == "0"
assert len(cases) == 1
assert cases[0].attrib.get("classname") == "com.example.orders.OrderQueryIntegrationTest"
assert cases[0].attrib.get("name") == "keepsTheApprovedExecutionStructure"
failures = cases[0].findall("failure")
assert len(failures) == 1
expected_message = (
    f"No approved baseline. Review {sys.argv[2]} "
    f"and copy it to {sys.argv[3]} only after human approval."
)
assert failures[0].attrib.get("message", "") == expected_message
PY
test ! -e "${approved_path}"
test ! -L "${approved_path}"

test -f "${cached_jar}"
test ! -L "${cached_jar}"
test "$(sha256_file "${cached_jar}")" = "${expected_jar_sha256}"
test "$(tr -d '\n' < "${cached_jar}.sha256")" = "${expected_jar_sha256}"
test "$(sha256_file "${cached_pom}")" = "${expected_pom_sha256}"
test "$(tr -d '\n' < "${cached_pom}.sha256")" = "${expected_pom_sha256}"
grep -Fqx \
  "routecontract-shardingsphere-5.5-0.1.2.jar>${repository_id}=" \
  "${coordinate_dir}/_remote.repositories"
grep -Fqx \
  "routecontract-shardingsphere-5.5-0.1.2.pom>${repository_id}=" \
  "${coordinate_dir}/_remote.repositories"
```

The Maven candidate path is `target/routecontract/orders.find-by-user-id.candidate.json`; the
Gradle path is `build/routecontract/orders.find-by-user-id.candidate.json`.

The candidate file is an undeclared test side effect. The Gradle lane therefore requires
`--no-build-cache --rerun-tasks`; the Maven lane uses `clean test` so a stale `target` candidate
cannot satisfy the run. Each executed, business-green, contract-eligible test that reaches the
manifest phase writes a separate candidate. With no approved file, the first run deliberately
fails as described next. Do not accept an arbitrary nonzero build result as that expected first-run
failure: confirm the business assertion passed, the candidate exists, and the only failing
assertion is the explicit missing-baseline message.

## 4. Review and approve the first baseline

A first supported, business-green, contract-eligible run that reaches the manifest phase creates no
approved file; it writes the candidate under the pilot build directory described in step 3. If the
explicit policy assertions pass and no approved file exists, the test then deliberately fails.
Before approving it, review at least:

- the operation ID and `strict` budgets;
- the observed attempt count and callback outcomes;
- every actual data-source name to stable, non-sensitive alias mapping;
- the parameter-type shape and rewritten-SQL fingerprint as structural evidence, not SQL meaning.

If and only if the candidate describes the intended operation and the explicit policy assertions
passed, create
`src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json` from those exact
reviewed candidate bytes in a separate human action. Review the baseline, test, alias mapping,
budgets, and pilot build diff together, then commit them through the repository's normal review
process. Record that the baseline was human-reviewed; a tool or CI result cannot make that decision.
RouteContract provides no approval API. `writeCandidate` refuses to write to the approved path, and
neither the test nor CI should copy, replace, or auto-approve the baseline.

Manifests exclude raw SQL, bind values, connection properties, and exception messages. Operation
IDs, aliases, Java type names, and unsalted fingerprints can still be sensitive engineering
metadata, so inspect the candidate before committing or sharing it.

## 5. Run the candidate check in CI

After approving and committing the baseline, run the same fresh-capture Gradle or Maven command from
step 3 again. An exact match passes. A budget or structural drift within the reviewed target
universe fails `ManifestAssertions.assertMatched` with stable RCM codes while leaving the business
assertion intact. Keep the reviewed `ManifestPolicy.strict(...)` values explicit on every run:
changing them must not be hidden by silently inheriting the approved file's policy. An otherwise
comparable candidate reports `RCM300 POLICY_CHANGED`; a candidate exceeding the approved
baseline's budget is rejected earlier with `RCM201` or `RCM202`.

For the Gradle lane, make the shared graph verifier and the selected test separate required
postconditions. The preparation task deletes only the prior generated candidate and exact prior
JUnit XML before the test task, so a disabled or source-less test cannot reuse old evidence. Replace
the owning-module path and absolute directory exactly as in step 3:

```bash
set -euo pipefail
gradle_project_dir="/absolute/path/to/owning-module"
candidate_path="${gradle_project_dir}/build/routecontract/orders.find-by-user-id.candidate.json"
report_path="${gradle_project_dir}/build/test-results/routeContractPilot/TEST-com.example.orders.OrderQueryIntegrationTest.xml"
approved_path="${gradle_project_dir}/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json"
graph_log="$(mktemp "${TMPDIR:-/tmp}/routecontract-gradle-ci-graph.XXXXXX")"
approved_identity() {
  python3 -I - "$1" <<'PY'
import hashlib
import os
import pathlib
import stat
import sys

path = pathlib.Path(sys.argv[1])
metadata = os.lstat(path)
assert stat.S_ISREG(metadata.st_mode)
print(":".join(map(str, (
    metadata.st_dev,
    metadata.st_ino,
    metadata.st_mode,
    metadata.st_size,
    metadata.st_mtime_ns,
    hashlib.sha256(path.read_bytes()).hexdigest(),
))))
PY
}
approved_before="$(approved_identity "${approved_path}")"

ROUTECONTRACT_REPOSITORY="/absolute/path/to/routecontract-maven" \
  ./gradlew -ProutecontractPilot=true \
  :owning-module:routeContractPilotGraph >"${graph_log}" 2>&1
test "$(grep -Fxc 'ROUTECONTRACT_GRADLE_GRAPH VERIFIED' "${graph_log}")" -eq 1

ROUTECONTRACT_REPOSITORY="/absolute/path/to/routecontract-maven" \
  ./gradlew -ProutecontractPilot=true \
  --no-build-cache --rerun-tasks \
  :owning-module:routeContractPilot \
  --tests com.example.orders.OrderQueryIntegrationTest.keepsTheApprovedExecutionStructure
test -s "${candidate_path}"
test -f "${candidate_path}"
test ! -L "${candidate_path}"
test -f "${report_path}"
test ! -L "${report_path}"
python3 -I - "${report_path}" <<'PY'
import pathlib
import sys
import xml.etree.ElementTree as ET

root = ET.fromstring(pathlib.Path(sys.argv[1]).read_bytes())
cases = root.findall("testcase")
assert root.attrib.get("tests") == "1"
assert root.attrib.get("failures") == "0"
assert root.attrib.get("errors") == "0"
assert root.attrib.get("skipped") == "0"
assert len(cases) == 1
assert cases[0].attrib.get("classname") == "com.example.orders.OrderQueryIntegrationTest"
assert cases[0].attrib.get("name") == "keepsTheApprovedExecutionStructure()"
assert not cases[0].findall("failure")
assert not cases[0].findall("error")
assert not cases[0].findall("skipped")
PY
test "$(approved_identity "${approved_path}")" = "${approved_before}"
```

For the Maven lane, every approved CI job must start with another absent `consumer_cache` and repeat
the complete Maven sequence in step 2: profile-off reactor tests, RouteContract-coordinate absence,
the exact selected-test dependency graph, and the cached-POM hash, sidecar, and origin readback.
Do not carry the review-run cache into CI. Then, with the approved file present, do not reuse the
intentional first-run status assertion: run the same exact selected test and require the fresh
candidate, one-test Surefire result, and post-candidate JAR/POM readback explicitly. Keep the step 2
and following block in the same CI `run` shell; the latter intentionally consumes only the variables
and functions that the complete step 2 block just established:

```bash
set -euo pipefail
owning_dir="$(python3 -I -c \
  'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True).parent)' \
  "${owning_pom}")"
candidate_path="${owning_dir}/target/routecontract/orders.find-by-user-id.candidate.json"
surefire_report="${owning_dir}/target/surefire-reports/TEST-com.example.orders.OrderQueryIntegrationTest.xml"
approved_path="${owning_dir}/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json"
cached_jar="${coordinate_dir}/routecontract-shardingsphere-5.5-0.1.2.jar"
approved_identity() {
  python3 -I - "$1" <<'PY'
import hashlib
import os
import pathlib
import stat
import sys

path = pathlib.Path(sys.argv[1])
metadata = os.lstat(path)
assert stat.S_ISREG(metadata.st_mode)
print(":".join(map(str, (
    metadata.st_dev,
    metadata.st_ino,
    metadata.st_mode,
    metadata.st_size,
    metadata.st_mtime_ns,
    hashlib.sha256(path.read_bytes()).hexdigest(),
))))
PY
}
test ! -e "${candidate_path}"
test ! -L "${candidate_path}"
test ! -e "${surefire_report}"
test ! -L "${surefire_report}"
approved_before="$(approved_identity "${approved_path}")"
mvn -B -ntp -f "${owning_pom}" \
  "-Dmaven.repo.local=${consumer_cache}" \
  -DroutecontractPilot=true \
  "-DroutecontractRepositoryUrl=${repository_uri}" \
  "-Droutecontract.artifactJarPath=${cached_jar}" \
  -Daether.checksums.algorithms.routecontract-verified-file-repository=SHA-256 \
  -DskipTests=false \
  -Dmaven.test.skip=false \
  -Dmaven.test.failure.ignore=false \
  -Dtest=com.example.orders.OrderQueryIntegrationTest#keepsTheApprovedExecutionStructure \
  clean test
test -f "${candidate_path}"
test ! -L "${candidate_path}"
test -f "${surefire_report}"
test ! -L "${surefire_report}"
python3 -I - "${surefire_report}" <<'PY'
import pathlib
import sys
import xml.etree.ElementTree as ET

report = pathlib.Path(sys.argv[1])
root = ET.fromstring(report.read_bytes())
cases = root.findall("testcase")
assert root.attrib.get("tests") == "1"
assert root.attrib.get("failures") == "0"
assert root.attrib.get("errors") == "0"
assert root.attrib.get("skipped") == "0"
assert len(cases) == 1
assert cases[0].attrib.get("classname") == "com.example.orders.OrderQueryIntegrationTest"
assert cases[0].attrib.get("name") == "keepsTheApprovedExecutionStructure"
assert not cases[0].findall("failure")
assert not cases[0].findall("error")
assert not cases[0].findall("skipped")
PY
test -f "${cached_jar}"
test ! -L "${cached_jar}"
test "$(sha256_file "${cached_jar}")" = "${expected_jar_sha256}"
test "$(tr -d '\n' < "${cached_jar}.sha256")" = "${expected_jar_sha256}"
test "$(sha256_file "${cached_pom}")" = "${expected_pom_sha256}"
test "$(tr -d '\n' < "${cached_pom}.sha256")" = "${expected_pom_sha256}"
grep -Fqx \
  "routecontract-shardingsphere-5.5-0.1.2.jar>${repository_id}=" \
  "${coordinate_dir}/_remote.repositories"
grep -Fqx \
  "routecontract-shardingsphere-5.5-0.1.2.pom>${repository_id}=" \
  "${coordinate_dir}/_remote.repositories"
test "$(approved_identity "${approved_path}")" = "${approved_before}"
```

For Maven CI, do not hand-stitch the long review and matched blocks. The checked-in
`scripts/verify-external-maven-integration.sh` is the executable form of those controls. It accepts
only explicit absolute project paths and test identities, creates private absent Release and Maven
cache directories, verifies the source-POM profile nesting and that the profile-off effective model
remains RouteContract-free before checking the graph, and then verifies exactly one selected
Surefire result plus a fresh candidate.
`ROUTECONTRACT_EXPECTED_OUTCOME=review` requires an
absent baseline both before and after the exact deliberate missing-baseline failure; `matched`
requires an existing regular approved manifest, a passing exact match, and unchanged file identity,
metadata, and SHA-256 across the run. All candidate and report paths must begin absent and stay
normalized below the owning module's `target` without symlink ancestors. The script never creates,
copies, replaces, or deletes the approved manifest. It also does not echo raw Maven output on
failure because application logs can contain sensitive data. The following steps run after checkout
and exact JDK 17 setup; replace every repository-specific path and identity:

```yaml
- name: Install exact Apache Maven 3.9.14
  shell: bash
  run: |
    set -euo pipefail
    maven_archive="${RUNNER_TEMP}/apache-maven-3.9.14-bin.tar.gz"
    maven_home="${RUNNER_TEMP}/apache-maven-3.9.14"
    maven_url="https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.14/apache-maven-3.9.14-bin.tar.gz"
    expected_sha512="d50af8ab5e6005b46a07f0ce9d3719e67cfdf898da988a84871304cd59fb1af0fef2f99dea709e6e66f21f732f905979b5c2dce6b6860406f60a70e84d9cf0b8"
    test ! -e "${maven_archive}"
    test ! -e "${maven_home}"
    curl --disable --proto '=https' --tlsv1.2 --fail --location \
      --silent --show-error --retry 3 --connect-timeout 15 --max-time 300 \
      --remove-on-error --max-filesize 20971520 \
      --output "${maven_archive}" "${maven_url}"
    printf '%s  %s\n' "${expected_sha512}" "${maven_archive}" \
      | sha512sum --check --strict
    tar --extract --gzip --file "${maven_archive}" --directory "${RUNNER_TEMP}"
    test -x "${maven_home}/bin/mvn"
    printf '%s\n' "${maven_home}/bin" >> "${GITHUB_PATH}"

- name: Verify approved RouteContract Maven integration
  shell: bash
  env:
    ROUTECONTRACT_EXPECTED_OUTCOME: matched
    ROUTECONTRACT_REACTOR_POM: ${{ github.workspace }}/pom.xml
    ROUTECONTRACT_OWNING_POM: ${{ github.workspace }}/owning-module/pom.xml
    ROUTECONTRACT_REACTOR_SELECTOR: your.group.id:owning-artifact-id
    ROUTECONTRACT_PROFILE_OFF_REPORT: ${{ github.workspace }}/owning-module/target/surefire-reports/TEST-com.example.orders.ExistingBusinessTest.xml
    ROUTECONTRACT_PROFILE_OFF_CLASS: com.example.orders.ExistingBusinessTest
    ROUTECONTRACT_PROFILE_OFF_METHOD: existingBusinessBehaviorRemainsGreen
    ROUTECONTRACT_TEST_CLASS: com.example.orders.OrderQueryIntegrationTest
    ROUTECONTRACT_TEST_METHOD: keepsTheApprovedExecutionStructure
    ROUTECONTRACT_CANDIDATE_PATH: ${{ github.workspace }}/owning-module/target/routecontract/orders.find-by-user-id.candidate.json
    ROUTECONTRACT_APPROVED_PATH: ${{ github.workspace }}/owning-module/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json
    ROUTECONTRACT_SUREFIRE_REPORT: ${{ github.workspace }}/owning-module/target/surefire-reports/TEST-com.example.orders.OrderQueryIntegrationTest.xml
  run: |
    set -euo pipefail
    tool_dir="${RUNNER_TEMP}/routecontract-onboarding-tools"
    test ! -e "${tool_dir}"
    mkdir "${tool_dir}"
    download_tool() {
      name="$1"
      expected="$2"
      url="$3"
      curl --disable --proto '=https' --tlsv1.2 --fail --location \
        --silent --show-error --retry 3 --connect-timeout 15 --max-time 120 \
        --remove-on-error --max-filesize 262144 \
        --output "${tool_dir}/${name}" "${url}"
      actual="$(python3 -I -c \
        'import hashlib,pathlib,sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' \
        "${tool_dir}/${name}")"
      test "${actual}" = "${expected}"
    }
    download_tool \
      install-release-assets.py \
      134b265709ac071dedd395da269426d83f1972f602c3b3f7d2201eecc525e204 \
      https://raw.githubusercontent.com/ym0506/routecontract/v0.1.2/scripts/install-release-assets.py
    download_tool \
      prepare_maven_v0_1_2_checksums.py \
      ee1928e578819fb597fffe7f1c72c055ff74ec6b36d37fe35f29c7fbd382b7b7 \
      https://raw.githubusercontent.com/ym0506/routecontract/2264b6e6292ee80f131148f2acef601cbaede096/scripts/prepare_maven_v0_1_2_checksums.py
    download_tool \
      verify-external-maven-integration.sh \
      69f233a5935f36a2e9068c25517fc3f15df4ef7da119e7a02feb9184df49e472 \
      https://raw.githubusercontent.com/ym0506/routecontract/2264b6e6292ee80f131148f2acef601cbaede096/scripts/verify-external-maven-integration.sh
    bash "${tool_dir}/verify-external-maven-integration.sh"
```

The installer URL above is pinned to immutable `v0.1.2`; the helper and verifier URLs are pinned to
bridge implementation commit `2264b6e6292ee80f131148f2acef601cbaede096`, and every download
retains its exact content-hash gate. This Maven workflow becomes usable only after this documentation
commit is published. Until then, do not count this lane as available onboarding.

For either supported build tool, every fresh CI job must repeat the exact Release download and use
an absent tool-specific cache; neither lane may inherit the review run's downloaded or resolved
artifacts.

Because `v0.1.2` is not on Maven Central, every fresh Gradle CI job must repeat the exact Release
download and installer. The following Gradle fragment uses
runner-temporary paths, verifies the checked-out tag object and commit, and makes the installed
repository available only to the opt-in task. Maven jobs use the self-contained verifier above:

```yaml
- name: Install exact RouteContract v0.1.2 Release assets
  shell: bash
  run: |
    set -euo pipefail
    source_dir="${RUNNER_TEMP}/routecontract-v0.1.2"
    asset_dir="${RUNNER_TEMP}/routecontract-v0.1.2-assets"
    repository_dir="${RUNNER_TEMP}/routecontract-v0.1.2-maven"
    release_base="https://github.com/ym0506/routecontract/releases/download/v0.1.2"
    expected_index_sha256="7849adf417f0170b08d01902b023e8b328d8796f7c2aeacc471eb7acf8e2b217"
    expected_installer_sha256="134b265709ac071dedd395da269426d83f1972f602c3b3f7d2201eecc525e204"
    expected_tag_object="6adacbe04d60b3af83d9067a14a878d26a6c90f5"
    expected_commit="fc4fdd16c21574afa1150654ce354cf8004b138b"
    assets=(
      SHA256SUMS
      routecontract-0.1.2-source.zip
      routecontract-shardingsphere-5.5-0.1.2.jar
      routecontract-shardingsphere-5.5-0.1.2-sources.jar
      routecontract-shardingsphere-5.5-0.1.2-javadoc.jar
      routecontract-shardingsphere-5.5.pom
      routecontract-shardingsphere-5.5-cyclonedx.json
      routecontract-shardingsphere-5.5-cyclonedx.xml
      routecontract-aggregate-cyclonedx.json
      routecontract-aggregate-cyclonedx.xml
      supply-chain-evidence.json
      test-summary.txt
    )

    test ! -e "${source_dir}"
    test ! -L "${source_dir}"
    test ! -e "${asset_dir}"
    test ! -L "${asset_dir}"
    test ! -e "${repository_dir}"
    test ! -L "${repository_dir}"
    git clone --quiet --depth 1 --branch v0.1.2 --single-branch \
      https://github.com/ym0506/routecontract.git "${source_dir}"
    test "$(git -C "${source_dir}" cat-file -t refs/tags/v0.1.2)" = tag
    test "$(git -C "${source_dir}" rev-parse refs/tags/v0.1.2)" = \
      "${expected_tag_object}"
    test "$(git -C "${source_dir}" rev-parse 'refs/tags/v0.1.2^{}')" = \
      "${expected_commit}"
    test "$(git -C "${source_dir}" rev-parse HEAD)" = "${expected_commit}"
    symbolic_ref_status=0
    symbolic_ref="$(git -C "${source_dir}" symbolic-ref -q HEAD)" \
      || symbolic_ref_status=$?
    test "${symbolic_ref_status}" -eq 1
    test -z "${symbolic_ref}"
    test -z "$(git -C "${source_dir}" status --short)"

    mkdir "${asset_dir}"
    for asset in "${assets[@]}"; do
      curl --disable --proto '=https' --tlsv1.2 --fail --location \
        --silent --show-error --retry 3 --connect-timeout 15 --max-time 300 \
        --max-filesize 5242880 \
        --output "${asset_dir}/${asset}" \
        "${release_base}/${asset}"
    done
    actual_index_sha256="$(python3 -I -c \
      'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' \
      "${asset_dir}/SHA256SUMS")"
    test "${actual_index_sha256}" = "${expected_index_sha256}"
    installer="${source_dir}/scripts/install-release-assets.py"
    test -f "${installer}"
    test ! -L "${installer}"
    actual_installer_sha256="$(python3 -I -c \
      'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' \
      "${installer}")"
    test "${actual_installer_sha256}" = "${expected_installer_sha256}"
    python3 -I "${installer}" \
      --release-assets-dir "${asset_dir}" \
      --repository "${repository_dir}"
    printf 'ROUTECONTRACT_REPOSITORY=%s\n' "${repository_dir}" >> "${GITHUB_ENV}"

- name: Run integration tests and RouteContract candidate check
  shell: bash
  run: |
    set -euo pipefail
    gradle_project_dir="${GITHUB_WORKSPACE}/owning-module"
    candidate_path="${gradle_project_dir}/build/routecontract/orders.find-by-user-id.candidate.json"
    report_path="${gradle_project_dir}/build/test-results/routeContractPilot/TEST-com.example.orders.OrderQueryIntegrationTest.xml"
    approved_path="${gradle_project_dir}/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json"
    graph_log="${RUNNER_TEMP}/routecontract-gradle-graph.log"
    approved_identity() {
      python3 -I - "$1" <<'PY'
    import hashlib
    import os
    import pathlib
    import stat
    import sys

    path = pathlib.Path(sys.argv[1])
    metadata = os.lstat(path)
    assert stat.S_ISREG(metadata.st_mode)
    print(":".join(map(str, (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        hashlib.sha256(path.read_bytes()).hexdigest(),
    ))))
    PY
    }
    test ! -e "${graph_log}"
    test ! -L "${graph_log}"
    approved_before="$(approved_identity "${approved_path}")"
    ./gradlew -ProutecontractPilot=true \
      :owning-module:routeContractPilotGraph >"${graph_log}" 2>&1
    test "$(grep -Fxc 'ROUTECONTRACT_GRADLE_GRAPH VERIFIED' "${graph_log}")" -eq 1
    ./gradlew -ProutecontractPilot=true \
      --no-build-cache --rerun-tasks \
      :owning-module:routeContractPilot \
      --tests com.example.orders.OrderQueryIntegrationTest.keepsTheApprovedExecutionStructure
    test -s "${candidate_path}"
    test -f "${candidate_path}"
    test ! -L "${candidate_path}"
    test -f "${report_path}"
    test ! -L "${report_path}"
    python3 -I - "${report_path}" <<'PY'
    import pathlib
    import sys
    import xml.etree.ElementTree as ET

    root = ET.fromstring(pathlib.Path(sys.argv[1]).read_bytes())
    cases = root.findall("testcase")
    assert root.attrib.get("tests") == "1"
    assert root.attrib.get("failures") == "0"
    assert root.attrib.get("errors") == "0"
    assert root.attrib.get("skipped") == "0"
    assert len(cases) == 1
    assert cases[0].attrib.get("classname") == "com.example.orders.OrderQueryIntegrationTest"
    assert cases[0].attrib.get("name") == "keepsTheApprovedExecutionStructure()"
    assert not cases[0].findall("failure")
    assert not cases[0].findall("error")
    assert not cases[0].findall("skipped")
    PY
    test "$(approved_identity "${approved_path}")" = "${approved_before}"
```

The fixed public asset URLs need no GitHub token or API call. The runner needs Git, `curl`, Python
3.10 or newer, Java 17, Docker, and network access. Use the equivalent fresh
download-and-install sequence on another CI service. Make this job a required check if you want the
assertion to gate a merge. For an intentional change, review the new candidate and explicitly
replace the approved file in a normal code-review change; never update the approved file
automatically in CI.

## 6. Report the stage reached

The [stable v0.1.2 feedback form](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml)
records the highest consecutive stage reached, including blockers and not-a-fit results. An
optional public evidence URL can make a run independently inspectable, but the form or URL alone
does not establish production use, adoption, performance, security, or endorsement. Do not publish
raw SQL, bind values, JDBC URLs, real topology, full logs, private paths, or customer information.
