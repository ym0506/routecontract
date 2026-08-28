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
be absent before cloning:

```bash
git clone --depth 1 --branch v0.1.0 \
  https://github.com/ym0506/routecontract.git \
  "/absolute/path/to/routecontract-v0.1.0"
cd "/absolute/path/to/routecontract-v0.1.0"
./scripts/quickstart-demo.sh
```

The final output must include `[ROUTECONTRACT QUICKSTART VERIFIED]`, `realMysqlDemoExit 0`,
`intentionalCiGateExit 1`, and `quickstartExit 0`. The inner exit `1` is the expected contract
rejection; the outer exit `0` means that rejection was verified. Java 17, Docker, Bash/POSIX tools,
Git, GitHub CLI (`gh`), Python 3.10 or newer, and network access for uncached dependencies, the
digest-pinned MySQL image, and public Release assets are required. Authentication is not required
for this public Release download, though an authenticated `gh` session can provide a higher API
rate limit.

## 2. Install the exact v0.1.0 Release assets

RouteContract `0.1.0` is **not published to Maven Central**. Keep the exact `v0.1.0` checkout from
step 1, download every asset from the [immutable GitHub Release](https://github.com/ym0506/routecontract/releases/tag/v0.1.0),
and install the verified JAR and POM into a new, explicit local Maven repository. Replace all
absolute example paths in this guide. The Release-asset and Maven-repository destinations must both
be absent before step 2, and the Maven repository must not be `~/.m2/repository` or a path below it.

```bash
mkdir "/absolute/path/to/routecontract-release-assets"
gh release download v0.1.0 \
  --repo ym0506/routecontract \
  --dir "/absolute/path/to/routecontract-release-assets"

python3 "/absolute/path/to/routecontract-v0.1.0/scripts/install-release-assets.py" \
  --release-assets-dir "/absolute/path/to/routecontract-release-assets" \
  --repository "/absolute/path/to/routecontract-maven"

cd "/absolute/path/to/your-repository"
```

The installer verifies the exact asset inventory and checksums before writing and refuses to
overwrite an existing coordinate. Checksums provide download integrity, not publisher identity;
download the inputs from the exact public Release above.

Add the installed repository and exact test dependencies to the Gradle project containing your
integration test. Supply the local repository path through the `routecontractRepository` Gradle property or
`ROUTECONTRACT_REPOSITORY` environment variable; do not commit a machine-specific absolute path.
The RouteContract artifact is thin: your test owns the ShardingSphere/Jackson/Calcite alignment and
JTS exclusion.

```groovy
def routeContractRepository = providers.gradleProperty("routecontractRepository")
        .orElse(providers.environmentVariable("ROUTECONTRACT_REPOSITORY"))
        .getOrNull()
if (routeContractRepository == null || routeContractRepository.isBlank()) {
    throw new GradleException(
            "Set -ProutecontractRepository or ROUTECONTRACT_REPOSITORY")
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    exclusiveContent {
        forRepository {
            maven {
                name = "routeContractRelease"
                url = uri(routeContractRepository)
            }
        }
        filter { includeGroup("io.github.ym0506.routecontract") }
    }
    mavenCentral()
}

dependencies {
    testImplementation(platform("com.fasterxml.jackson:jackson-bom:2.18.9"))
    testImplementation("org.apache.shardingsphere:shardingsphere-jdbc:5.5.3") {
        exclude group: "org.locationtech.jts.io", module: "jts-io-common"
    }
    testImplementation("io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0")

    constraints {
        testImplementation("org.apache.calcite:calcite-core:1.42.0") {
            version { strictly "1.42.0" }
        }
        testImplementation("org.apache.calcite:calcite-linq4j:1.42.0") {
            version { strictly "1.42.0" }
        }
    }
}

tasks.withType(Test).configureEach {
    systemProperty "routecontract.projectDir", projectDir.absolutePath
}
```

Keep the runtime modules already required by your ShardingSphere-JDBC integration test. The
dependency block above does not configure a data source or replace your existing test fixture.
If `settings.gradle` enforces `RepositoriesMode.FAIL_ON_PROJECT_REPOS`, move both the
property/environment resolution and the `exclusiveContent` rule out of the project build and merge
this equivalent block into the existing settings file:

```groovy
def routeContractRepository = providers.gradleProperty("routecontractRepository")
        .orElse(providers.environmentVariable("ROUTECONTRACT_REPOSITORY"))
        .getOrNull()
if (routeContractRepository == null || routeContractRepository.isBlank()) {
    throw new GradleException(
            "Set -ProutecontractRepository or ROUTECONTRACT_REPOSITORY")
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = "routeContractRelease"
                    url = uri(routeContractRepository)
                }
            }
            filter { includeGroup("io.github.ym0506.routecontract") }
        }
        mavenCentral()
    }
}
```

If the repository uses dependency locks or dependency-verification metadata, update them through
the project's normal reviewed process for this exact graph; never disable those controls to make
the dependency resolve.

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
            "src/test/resources/route-contracts/orders.find-by-user-id.json");
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

Run the new test from your consumer repository with a fresh candidate capture:

```bash
ROUTECONTRACT_REPOSITORY="/absolute/path/to/routecontract-maven" \
  ./gradlew --no-build-cache --rerun-tasks test
```

The candidate file is an undeclared test side effect, so `--no-build-cache --rerun-tasks` is
required instead of an up-to-date or cached test result. Each executed, business-green,
contract-eligible test that reaches the manifest phase writes a separate candidate. With no
approved file, the first run deliberately fails as described next. If the selected integration
test belongs to a custom Gradle task such as `integrationTest`, replace `test` in both commands in
this guide with that actual task while retaining `--no-build-cache --rerun-tasks`.

## 4. Review and approve the first baseline

A first supported, business-green, contract-eligible run that reaches the manifest phase writes
only `build/routecontract/orders.find-by-user-id.candidate.json`. If the explicit policy assertions
pass and no approved file exists, the test then deliberately fails. Before approving it, review at
least:

- the operation ID and `strict` budgets;
- the observed attempt count and callback outcomes;
- every actual data-source name to stable, non-sensitive alias mapping;
- the parameter-type shape and rewritten-SQL fingerprint as structural evidence, not SQL meaning.

If and only if the candidate describes the intended operation and the explicit policy assertions
passed, copy it in a separate human action
to `src/test/resources/route-contracts/orders.find-by-user-id.json`, review that tracked diff, and
commit it with the test. RouteContract provides no approval API. `writeCandidate` refuses to write
to the approved path, and neither the test nor CI should copy, replace, or auto-approve the
baseline.

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
and installer before Gradle. For GitHub Actions, this step uses new runner-temporary paths and makes
the verified repository available to the later Gradle step:

```yaml
- name: Install exact RouteContract v0.1.0 Release assets
  shell: bash
  env:
    GH_TOKEN: ${{ github.token }}
  run: |
    source_dir="${RUNNER_TEMP}/routecontract-v0.1.0-source"
    asset_dir="${RUNNER_TEMP}/routecontract-v0.1.0-assets"
    repository_dir="${RUNNER_TEMP}/routecontract-v0.1.0-maven"
    test ! -e "${source_dir}"
    test ! -e "${asset_dir}"
    test ! -e "${repository_dir}"
    mkdir "${asset_dir}"
    gh release download v0.1.0 \
      --repo ym0506/routecontract \
      --dir "${asset_dir}"
    mkdir "${source_dir}"
    python3 -m zipfile -e \
      "${asset_dir}/routecontract-0.1.0-source.zip" \
      "${source_dir}"
    python3 "${source_dir}/routecontract-0.1.0/scripts/install-release-assets.py" \
      --release-assets-dir "${asset_dir}" \
      --repository "${repository_dir}"
    printf 'ROUTECONTRACT_REPOSITORY=%s\n' "${repository_dir}" >> "${GITHUB_ENV}"

- name: Run integration tests and RouteContract candidate check
  run: ./gradlew --no-build-cache --rerun-tasks test
```

The workflow or job must retain `contents: read`; `${{ github.token }}` is used only so `gh` can
download the public Release assets. The runner needs `gh`, Python 3.10 or newer, Java 17, Docker,
and network access. Use the equivalent fresh download-and-install sequence on another CI service.
Make this existing Gradle test job a required check if you want the assertion to gate a merge. For an
intentional change, review the new candidate and explicitly replace the approved file in a normal
code-review change; never update the approved file automatically in CI.

## 6. Report the stage reached

The [stable v0.1.0 feedback form](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml)
records the highest consecutive stage reached, including blockers and not-a-fit results. An
optional public evidence URL can make a run independently inspectable, but the form or URL alone
does not establish production use, adoption, performance, security, or endorsement. Do not publish
raw SQL, bind values, JDBC URLs, real topology, full logs, private paths, or customer information.
