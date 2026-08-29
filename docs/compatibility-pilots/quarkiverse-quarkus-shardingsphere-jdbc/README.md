# Quarkiverse ShardingSphere-JDBC local H2 compatibility pilot

This directory seals a **RouteContract-maintainer local feasibility check** against the public
[`quarkiverse/quarkus-shardingsphere-jdbc`](https://github.com/quarkiverse/quarkus-shardingsphere-jdbc)
repository. The tested upstream revision is commit
`90e023ce45d58842011724d5b7e7e04d710eb459`, tree
`523e367826826da44e5b75249a828645eb032889`.

Evidence boundary: `verified - H2` and `verified - ShardingSphere-JDBC 5.5.3`. This is **not MySQL
evidence**, an upstream contribution, an independent execution, a user result, adoption, production
support or endorsement by Quarkiverse or Apache ShardingSphere. No external maintainer participated.
No human-approved baseline is included or created.

## What the pilot established

- With the opt-in profile disabled, the patched checkout's full four-module `clean test` reactor
  passed the exact existing `ShardingsphereJdbcTest#writeYourOwnUnitTest`,
  `ShardingsphereJdbcDevModeTest#writeYourOwnDevModeTest`, and `ShardingTablesTest#test` cases with
  no failure, error, or skip. RouteContract was absent from that build and no candidate was
  produced.
- With `-DroutecontractPilot=true`, RouteContract `0.1.0` is placed in **compile scope only inside
  the opt-in integration-test profile** so the provider is available to the Quarkus application
  runtime. The sealed run proves successful discovery and callbacks with that scope; it does not
  seal a test-scope comparison or the exact discovery time.
- The pilot deliberately invokes the injected CDI resource directly inside `RouteContract.capture`.
  The existing RestAssured test is not captured because its application HTTP handoff is outside the
  supported synchronous caller boundary; this packet makes no HTTP-capture claim.
- The representative INSERT kept all four original preconditions, changed only
  `ds_1.t_account_1` from zero to one row, and produced a `COMPLETE` snapshot with one
  `SQLExecutionHook`-reported physical JDBC execution attempt, no callback failure and observed
  data source `ds_1`.
- Two clean, profile-on runs produced byte-identical 679-byte candidates with SHA-256
  `60e94c17e2df96ff7f4769f33a6a7b4f3431b0cd0995d47906e6f63a3d1601e4`. Each run then stopped
  at the single intended failure: the human-approved baseline was absent.

`COMPLETE` is RouteContract's capture status. It is not a claim that the snapshot is a complete
route plan or that the enclosing transaction committed. Each attempt begins with
`SQLExecutionHook.start`. In this successful snapshot, `CALLBACK_RETURNED` means ShardingSphere
5.5.3 subsequently invoked `finishSuccess` after the wrapped `executeSQL` call returned.

## Sealed files

| File | Purpose | SHA-256 |
| --- | --- | --- |
| `routecontract-pilot.patch` | Exact two-path opt-in patch | `8265c2a9525ef8b6506ca90fdc5774996888e00d09c802624feeca7be967cfbe` |
| `reproduce.sh` | Fail-closed profile-off plus two-run profile-on reproducer | `bb37e66cde57d0398c2fc4abf5b5431b497f3939b00c22581d4b77951300130a` |
| `maven-settings.xml` | Exact empty user/global Maven settings used by every Maven call | `132df1e0d6c1fc8da8e0bf7fc7fc4534505fa8cc3e50f3870150a580c17b7c4f` |
| `expected-candidate.sha256` | Expected generated candidate digest | `4961872ab916d7556b9be1fec2722a5479e42731126a1a70d8b98939404efde6` |
| `receipt.json` | Machine-readable environment, results and claim boundary | See the file itself; it does not self-hash. |

The patch changes exactly these upstream paths:

1. `integration-tests/pom.xml`
2. `integration-tests/src/routeContractPilot/java/io/quarkiverse/shardingsphere/jdbc/it/RouteContractInsertPilotTest.java`

It deliberately contains no file at
`integration-tests/src/routeContractPilot/resources/route-contracts/accounts.insert.json`.

## Reproduce in a disposable checkout

Requirements are Git, Python 3, JDK 17, Apache Maven 3.9.14 and network access for the upstream
Maven dependencies. `JAVA_HOME` must be an absolute, already-canonical JDK 17 home rather than a
symlink or a different JDK hidden behind `PATH`. Obtain these exact RouteContract v0.1.0 Release
assets in one directory:

| Asset | SHA-256 |
| --- | --- |
| `routecontract-shardingsphere-5.5-0.1.0.jar` | `d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc` |
| `routecontract-shardingsphere-5.5.pom` | `05570bfa238ef77db255a46efdd5bbb25e994ae0137db86491a46a25e28deac9` |
| `SHA256SUMS` | `820ed33eb8bfe8d47f3ec8782d2aa99f2879227c4ee066ecafc467e61abb8684` |

Then create a clean detached checkout and run the verifier:

```bash
git clone --no-tags https://github.com/quarkiverse/quarkus-shardingsphere-jdbc.git \
  /absolute/path/to/disposable-quarkiverse
git -C /absolute/path/to/disposable-quarkiverse checkout --detach \
  90e023ce45d58842011724d5b7e7e04d710eb459

export JAVA_HOME=/absolute/path/to/jdk-17
/absolute/path/to/this-directory/reproduce.sh \
  /absolute/path/to/disposable-quarkiverse \
  /absolute/path/to/routecontract-v0.1.0-release-assets
```

The script verifies the upstream commit/tree, clean status, release-asset hashes, bundled empty
settings, Maven/JDK versions and exact two-path patch before running anything. It invokes
`JAVA_HOME/bin/java` directly, requires Maven's reported Java 17 runtime to resolve to that same
canonical home, disables Maven rc files, clears Maven/Java command-injection environment variables,
and passes the bundled settings as both user and global settings on every Maven call. It uses a
private temporary Maven local repository, forces SHA-256 for the file-repository transfer, and
deletes that private scratch area on exit. After both opt-in runs it reads the dependency back from
the consumer cache, verifies the exact JAR/POM hashes and lowercase-hex SHA-256 sidecars (with or
without Maven's optional final LF), and requires both cache
entries to name only `routecontract-v0.1.0-local` in `_remote.repositories`. Set `MAVEN_REPO_SEED`
to an absolute existing Maven repository only to reduce downloads; the script rejects a seed
containing symbolic links, copies it into scratch, rechecks the copy for symbolic links, and only
then removes the RouteContract coordinate before resolution.

The script applies the patch and intentionally leaves the disposable upstream checkout modified.
Its successful final output is:

```text
ROUTECONTRACT_QUARKIVERSE_PROFILE_OFF fullReactor=PASS pilotDependency=ABSENT
ROUTECONTRACT_QUARKIVERSE_PROFILE_ON run1=EXPECTED_BASELINE_FAILURE run2=EXPECTED_BASELINE_FAILURE
ROUTECONTRACT_QUARKIVERSE_CANDIDATE sha256=60e94c17e2df96ff7f4769f33a6a7b4f3431b0cd0995d47906e6f63a3d1601e4 bytes=679 deterministicRuns=2
ROUTECONTRACT_QUARKIVERSE_BOUNDARY environment=H2 humanApprovedBaseline=false externalUser=false adoption=false endorsement=false
```

The profile-on command selects only `RouteContractInsertPilotTest`. The existing upstream
integration test inserts the same account id and shares the Quarkus H2 application state when both
tests are selected together. Every profile-on run uses `clean` so Quarkus re-augments the application
with the opt-in dependency.

## Human review remains unresolved

The candidate is a proposal, not an approval. A repository owner would still need to review the
operation boundary, aliases and budgets, then deliberately approve exact baseline bytes in their
own repository. This local packet does not make that decision, and therefore does not satisfy the
project's strict definition of an actual external user integration.
