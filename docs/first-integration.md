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
source_dir="/absolute/path/to/routecontract-v0.1.0"
expected_tag_object="e3944631ad827e88d4936b75e9b738ef50a22b20"
expected_commit="db203cfd9202ff10cd22c41cf04034eca5177341"

test ! -e "${source_dir}"
test ! -L "${source_dir}"
git clone --quiet --depth 1 --branch v0.1.0 --single-branch \
  https://github.com/ym0506/routecontract.git \
  "${source_dir}"
test "$(git -C "${source_dir}" cat-file -t refs/tags/v0.1.0)" = tag
test "$(git -C "${source_dir}" rev-parse refs/tags/v0.1.0)" = "${expected_tag_object}"
test "$(git -C "${source_dir}" rev-parse 'refs/tags/v0.1.0^{}')" = "${expected_commit}"
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

## 2. Install the exact v0.1.0 Release assets

RouteContract `0.1.0` is **not published to Maven Central**. Keep the exact `v0.1.0` checkout from
step 1, download every asset from the [immutable GitHub Release](https://github.com/ym0506/routecontract/releases/tag/v0.1.0),
and install the verified JAR and POM into a new, explicit local Maven repository. Replace all
absolute example paths in this guide. The Release-asset and Maven-repository destinations must both
be absent before step 2, and the Maven repository must not be `~/.m2/repository` or a path below it.

```bash
(
set -euo pipefail
asset_dir="/absolute/path/to/routecontract-release-assets"
repository_dir="/absolute/path/to/routecontract-maven"
source_dir="/absolute/path/to/routecontract-v0.1.0"
release_base="https://github.com/ym0506/routecontract/releases/download/v0.1.0"
expected_index_sha256="820ed33eb8bfe8d47f3ec8782d2aa99f2879227c4ee066ecafc467e61abb8684"
expected_installer_sha256="d21a7c71eb725e8d5f0675cfb88815b26be130d63711dc025a06347317652d33"
expected_tag_object="e3944631ad827e88d4936b75e9b738ef50a22b20"
expected_commit="db203cfd9202ff10cd22c41cf04034eca5177341"
assets=(
  SHA256SUMS
  routecontract-0.1.0-source.zip
  routecontract-shardingsphere-5.5-0.1.0.jar
  routecontract-shardingsphere-5.5-0.1.0-sources.jar
  routecontract-shardingsphere-5.5-0.1.0-javadoc.jar
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
test "$(git -C "${source_dir}" rev-parse refs/tags/v0.1.0)" = "${expected_tag_object}"
test "$(git -C "${source_dir}" rev-parse 'refs/tags/v0.1.0^{}')" = "${expected_commit}"
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

The immutable `v0.1.0` installer is intentionally time-bounded by its embedded MySQL OCI
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
    def routeContractRepository = providers.gradleProperty("routecontractRepository")
            .orElse(providers.environmentVariable("ROUTECONTRACT_REPOSITORY"))
    if (!routeContractRepository.isPresent()
            || routeContractRepository.get().isBlank()) {
        throw new GradleException(
                "Set -ProutecontractRepository or ROUTECONTRACT_REPOSITORY for the pilot")
    }

    def pilot = sourceSets.create("routeContractPilot") {
        java.srcDir("src/routeContractPilot/java")
        resources.srcDir("src/routeContractPilot/resources")
        compileClasspath += sourceSets.main.output + sourceSets.test.output
        runtimeClasspath += output + compileClasspath
    }
    configurations.named(pilot.implementationConfigurationName) {
        extendsFrom(configurations.testImplementation)
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
                "io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0")
    }

    tasks.named(pilot.compileJavaTaskName, JavaCompile) {
        javaCompiler = javaToolchains.compilerFor {
            languageVersion = JavaLanguageVersion.of(17)
        }
        options.release = 17
    }
    tasks.register("routeContractPilot", Test) {
        group = "verification"
        testClassesDirs = pilot.output.classesDirs
        classpath = pilot.runtimeClasspath
        javaLauncher = javaToolchains.launcherFor {
            languageVersion = JavaLanguageVersion.of(17)
        }
        useJUnitPlatform()
        systemProperty "routecontract.projectDir", projectDir.absolutePath
    }
}
```

This lane reuses the representative fixture's existing test dependencies, including its exact
ShardingSphere-JDBC 5.5.3 edge; do not add a second ShardingSphere dependency or change the
project-wide Java toolchain or dependency management. Inspect the complete
`routeContractPilotRuntimeClasspath` before adding the test. A different ShardingSphere version,
missing runtime module, or incompatible graph is a blocker, not a successful integration. If the
repository uses dependency locks or verification metadata, update them through its normal reviewed
process and never disable them. Gradle's dependency-report task can still exit `0` while printing
`FAILED` or another unresolved node: stop if either appears, and do not treat `BUILD SUCCESSFUL`
alone as a usable graph.

If `settings.gradle` enforces `RepositoriesMode.FAIL_ON_PROJECT_REPOS`, place the same conditional
`exclusiveContent` repository in the existing `dependencyResolutionManagement` block instead; the
repository path must not be read when the pilot property is absent. If the repository cannot
isolate this lane, uses Maven, or needs Kotlin DSL, stop and report that fit blocker rather than
adding an untested generic build fragment. RouteContract's runtime library is not inherently tied
to Gradle, but `v0.1.0` currently documents only this tested Gradle Groovy DSL path.

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

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.fail;

@Test
void keepsTheApprovedExecutionStructure() throws Exception {
    Path projectDir = Path.of(System.getProperty("routecontract.projectDir"))
            .toAbsolutePath()
            .normalize();
    Path approvedPath = projectDir.resolve(
            "src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json");
    Path candidatePath = projectDir.resolve(
            "build/routecontract/orders.find-by-user-id.candidate.json");
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

First inspect the complete owning-module pilot graph, then run only the new test with a fresh
candidate capture. Replace `:owning-module` with the actual Gradle project path; use
`:routeContractPilot` for a root project.

```bash
ROUTECONTRACT_REPOSITORY="/absolute/path/to/routecontract-maven" \
  ./gradlew -ProutecontractPilot=true \
  :owning-module:dependencies \
  --configuration routeContractPilotRuntimeClasspath

ROUTECONTRACT_REPOSITORY="/absolute/path/to/routecontract-maven" \
  ./gradlew -ProutecontractPilot=true \
  --no-build-cache --rerun-tasks \
  :owning-module:routeContractPilot \
  --tests com.example.orders.OrderQueryIntegrationTest.keepsTheApprovedExecutionStructure
```

The candidate file is an undeclared test side effect, so `--no-build-cache --rerun-tasks` is
required instead of an up-to-date or cached test result. Each executed, business-green,
contract-eligible test that reaches the manifest phase writes a separate candidate. With no
approved file, the first run deliberately fails as described next. Do not accept an arbitrary
nonzero build result as that expected first-run failure: confirm the business assertion passed, the
candidate exists, and the only failing assertion is the explicit missing-baseline message.

## 4. Review and approve the first baseline

A first supported, business-green, contract-eligible run that reaches the manifest phase creates no
approved file; it writes the candidate at
`build/routecontract/orders.find-by-user-id.candidate.json`. If the explicit policy assertions pass
and no approved file exists, the test then deliberately fails. Before approving it, review at least:

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

After approving and committing the baseline, run the same fresh-capture Gradle command from step 3
again. An exact match passes. A budget or structural drift within the reviewed target universe
fails `ManifestAssertions.assertMatched` with stable RCM codes while leaving the business assertion
intact. Keep the reviewed `ManifestPolicy.strict(...)` values explicit on every run: changing them
must not be hidden by silently inheriting the approved file's policy. An otherwise comparable
candidate reports `RCM300 POLICY_CHANGED`; a candidate exceeding the approved baseline's budget is
rejected earlier with `RCM201` or `RCM202`.

Because `v0.1.0` is not on Maven Central, every fresh CI job must repeat the exact Release download
and installer before Gradle. The following GitHub Actions fragment uses runner-temporary paths,
verifies the checked-out tag object and commit, and makes the installed repository available only
to the opt-in task:

```yaml
- name: Install exact RouteContract v0.1.0 Release assets
  shell: bash
  run: |
    set -euo pipefail
    source_dir="${RUNNER_TEMP}/routecontract-v0.1.0"
    asset_dir="${RUNNER_TEMP}/routecontract-v0.1.0-assets"
    repository_dir="${RUNNER_TEMP}/routecontract-v0.1.0-maven"
    release_base="https://github.com/ym0506/routecontract/releases/download/v0.1.0"
    expected_index_sha256="820ed33eb8bfe8d47f3ec8782d2aa99f2879227c4ee066ecafc467e61abb8684"
    expected_installer_sha256="d21a7c71eb725e8d5f0675cfb88815b26be130d63711dc025a06347317652d33"
    expected_tag_object="e3944631ad827e88d4936b75e9b738ef50a22b20"
    expected_commit="db203cfd9202ff10cd22c41cf04034eca5177341"
    assets=(
      SHA256SUMS
      routecontract-0.1.0-source.zip
      routecontract-shardingsphere-5.5-0.1.0.jar
      routecontract-shardingsphere-5.5-0.1.0-sources.jar
      routecontract-shardingsphere-5.5-0.1.0-javadoc.jar
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
    git clone --quiet --depth 1 --branch v0.1.0 --single-branch \
      https://github.com/ym0506/routecontract.git "${source_dir}"
    test "$(git -C "${source_dir}" cat-file -t refs/tags/v0.1.0)" = tag
    test "$(git -C "${source_dir}" rev-parse refs/tags/v0.1.0)" = \
      "${expected_tag_object}"
    test "$(git -C "${source_dir}" rev-parse 'refs/tags/v0.1.0^{}')" = \
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
  run: |
    ./gradlew -ProutecontractPilot=true \
      --no-build-cache --rerun-tasks \
      :owning-module:routeContractPilot \
      --tests com.example.orders.OrderQueryIntegrationTest.keepsTheApprovedExecutionStructure
```

The fixed public asset URLs need no GitHub token or API call. The runner needs Git, `curl`, Python
3.10 or newer, Java 17, Docker, and network access. Use the equivalent fresh
download-and-install sequence on another CI service. Make this job a required check if you want the
assertion to gate a merge. For an intentional change, review the new candidate and explicitly
replace the approved file in a normal code-review change; never update the approved file
automatically in CI.

## 6. Report the stage reached

The [stable v0.1.0 feedback form](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml)
records the highest consecutive stage reached, including blockers and not-a-fit results. An
optional public evidence URL can make a run independently inspectable, but the form or URL alone
does not establish production use, adoption, performance, security, or endorsement. Do not publish
raw SQL, bind values, JDBC URLs, real topology, full logs, private paths, or customer information.
