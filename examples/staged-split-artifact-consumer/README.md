# Independent staged-artifact MySQL consumer

The current 0.2 fixture uses `io.github.ym0506.routecontract.api.RouteContract`.
See the [entry migration contract](../../docs/current-entry-migration-acceptance.md)
for automatic collision checks and the clean-classpath compatibility facade.
Use newly staged 0.2 bytes that include this entry; older staging does not contain it.

Status: unreleased 0.2 development fixture. This checks supplied local staged bytes; it does not
claim Maven Central availability, public anonymous consumption, external adoption, or release readiness.

## Acceptance contract

- Copy this consumer outside the source checkout and give each exact 5.5.2/5.5.3 lane a fresh
  Gradle user home. Resolve first-party code only from the supplied Maven repository. No composite
  build, project dependency, Maven Local, source compilation, or first-party Central fallback.
- Bind resolved core and selected adapter JAR/POM/module bytes to a receipt of the supplied staging
  tree, with strict Gradle checksum verification and reviewed per-lane third-party locks.
- Require exactly core plus the selected adapter at 0.2.0. Every selected/requested ShardingSphere
  dependency must match the exact lane. Verify the executing core/provider JAR names and SHA-256.
- Exercise real MySQL 8.4.11: equality returns the exact row `(order_id=201, user_id=3, status=PAID)`, one reported physical JDBC execution
  attempt and a schema-2 MATCH against the unchanged reviewed baseline. The range predicate returns
  the same row while attempts grow 1 to 2; candidate assertions and the report CLI must reject it
  with POLICY_VIOLATION and RCM201/RCM202.
- Retain separate business assertions, minimized reports, raw JUnit and dependency-graph evidence.
- Wrong whole runtime and wrong non-anchor dependencies must fail through the exact-version policy;
  both ordinary adapter dependency orders must fail through the shared published capability,
  without a custom `requireCapability` request. A pre-0.2 all-in-one
  request must fail through consumer policy before artifact resolution. This last check does not
  establish manual-classpath legacy collision behavior.
- Missing/changed staged bytes, a nonzero/unexpected/empty/skipped JUnit result, or missing success
  markers fail the harness. Never change or approve a baseline automatically.

The Java fixture copies the existing reviewed schema-2 example baselines byte-for-byte. It does
not take a dependency on source tests. Paths and checksums identify local test evidence, not approval
or provenance from an external publisher. Reports expose only synthetic minimized fixture data.

## Run

Prepare a coordinated staging directory with the existing root publication task (no upload):

```sh
routecontract_stage_parent="$(mktemp -d)"
routecontract_stage_parent="$(cd "$routecontract_stage_parent" && pwd -P)"
./gradlew publishRouteContractCentralStaging -ProutecontractCentralSigning=false "-ProutecontractCentralStagingDirectory=$routecontract_stage_parent/repository"
python3 scripts/verify-staged-split-artifact-consumer.py --repository "$routecontract_stage_parent/repository" --evidence-directory "$PWD/build/staged-consumer-evidence"
```

The staging parent must be a canonical private directory; `mktemp` plus `pwd -P` supplies one.
Choose a new evidence directory on rerun. Remove the temporary staging directory yourself after
retaining the receipt and evidence you need.

Java 17, Docker and network access for the first third-party dependency download are required.
The supplied repository and evidence directory must be different, and the evidence directory must
not already exist. The harness itself never publishes/builds first-party artifacts and never
writes to the supplied repository. Keep the receipt, logs and JUnit from the same run together.

This is one consumer build tool and one bounded MySQL scenario. The public Gradle/Maven consumer,
full route-risk corpus, offline/corruption matrix and other ADR release gates remain separate work.
The release-evidence workflow remains fail-closed for 0.2.
