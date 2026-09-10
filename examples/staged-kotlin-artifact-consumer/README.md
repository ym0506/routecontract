# Staged Kotlin DSL consumer acceptance

Status: current HTTP repository and test-launcher adaptations are `unverified` until
the A-24 driver runs this exact build against its reviewed current-source staging receipt.
Historical local online Kotlin DSL / Java 17 results are retained below with their exact
source revisions; they do not verify these adaptations. The complete ADR A-24 matrix remains
unverified. This fixture resolves packaged unreleased `0.2.0` artifacts; it does not
include the RouteContract source build or claim public availability.

The A-24 driver assembles this build and `settings.gradle.kts` outside the checkout,
copies the existing `examples/staged-split-artifact-consumer/src` unchanged, and supplies
that fixture's reviewed `gradle-locks/<runtime>.lockfile` as `gradle.lockfile`. It also
copies the pinned Gradle wrapper and strict verification metadata containing the expected
nine staged JAR/POM/module hashes. No baseline is created or rewritten by this build.

The acceptance behavior specified before implementation is:

- Accept exactly `routecontractRuntime=5.5.2` or `5.5.3`, exactly one designated repository
  property, and exact `routecontractSha256.routecontract-core` and
  `routecontractSha256.<selected-adapter>` properties. `routecontractRepository` is a
  legacy absolute staged-directory path; `routecontractRepositoryUrl` must be canonical
  `http://127.0.0.1:<1-65535>` with an optional trailing slash. The HTTP listener is owned
  by the driver. Other hosts, schemes, paths, credentials, queries and fragments fail
  before dependency resolution. A frozen-cache-only offline claim requires HTTP priming
  and shutdown of that endpoint, then the identical URL with native `--offline`.
- Resolve only the coordinated `0.2.0` core and selected adapter, verify their JAR hashes,
  reject source/project components, and require every ShardingSphere request and selected
  component to use the selected exact runtime. Strict locks and native Gradle dependency
  verification remain enabled.
- Pin Java compilation and the actual Gradle test launcher to Java 17, and supply
  `java.net.preferIPv4Stack=true` to each test JVM. The A-24 driver separately controls
  daemon/client JVM options, installs its generated no-pull policy, and verifies the
  actual JVM and policy invocation. When the driver supplies
  `ROUTECONTRACT_A24_PRIVATE_HOME`, the test JVM uses that exact absolute `user.home`
  to isolate local Testcontainers configuration; ordinary consumers retain their default.
  Launcher configuration is not executed-JVM proof.
- Run the unchanged three MySQL tests and CLI checks: the exact business row remains the
  same while the range regression increases reported physical JDBC execution attempts
  from one to two and fails the approved policy. Retain the existing graph/MySQL markers.
- Expose `verifyWrongAnchor` and `verifyWrongNonAnchor` separately so the driver can give
  each a fresh process and empty dependency cache. The non-anchor case must retain the
  selected adapter and all three correct runtime anchors while rejecting one wrong-version
  `shardingsphere-infra-common` request. Each task retains a JSON report containing the
  actual unresolved selector and cause chains, requested wrong coordinate, selected adapter,
  and correct anchors in addition to the readable resolver report.
- Retain selected graph/JAR hashes and real resolver failure causes. Missing downloads,
  checksum failures, lock failures or compilation failures do not count as graph-policy
  rejection. Both ordinary adapter orders and the historical legacy request remain separate
  graph controls; they do not prove manual-classpath legacy handling.

The assembled consumer uses Java 17 and Gradle 8.14.4:

```sh
./gradlew --no-daemon --no-build-cache --no-configuration-cache \
  --dependency-verification=strict \
  -ProutecontractRuntime=5.5.2 \
  "-ProutecontractRepositoryUrl=${STAGING_URL:?Set the driver-owned loopback HTTP URL}" \
  "-ProutecontractSha256.routecontract-core=${CORE_SHA256:?Set the reviewed core hash}" \
  "-ProutecontractSha256.routecontract-shardingsphere-5.5.2=${ADAPTER_SHA256:?Set the reviewed adapter hash}" \
  clean test verifySelectedGraph
```

For 5.5.3, select `routecontractRuntime=5.5.3` and the
`routecontractSha256.routecontract-shardingsphere-5.5` property. The A-24 driver must
independently exercise frozen-cache offline, corrupted-checksum and wrong-origin cases;
an online `check` alone does not close A-24 or establish Java 21 support.

## Historical local online verification, 2026-09-08

Each runtime ran once with a fresh dependency cache; only the wrapper's SHA-256-verified
Gradle 8.14.4 distribution ZIP was seeded. The supplied nine-payload staging receipt and
packaged implementation came from revision `008e125a0648ed615842a572d60fd453698bb5aa`.
The consumer fixture was based on `3a136a6f006c8040b0facadafc18606d2a63600a`; its exact
uncommitted Kotlin build bytes and unchanged shared Java/resources/locks are hashed in
the retained input snapshot. This is not a rebuild or byte-identity claim for another revision.

| Exact runtime | Selected ShardingSphere components | MySQL tests | Graph controls |
| --- | ---: | ---: | ---: |
| 5.5.2 | 122, all 5.5.2 | 3 passed | 5 rejected as expected |
| 5.5.3 | 75, all 5.5.3 | 3 passed | 5 rejected as expected |

Both JUnit suites report zero failures, errors and skips. Each lane retains the exact
compile/runtime core and adapter JAR hashes, the selected graph, correct-anchor evidence,
policy/capability failure causes, and the unchanged fixture's MATCH and 1-to-2 regression
reports. The graph controls in this online `check` share that lane's cache; the separate
fresh-cache negative tasks, offline, corruption and wrong-origin executions belong to
the full A-24 driver and are not counted as completed here.

Host: macOS arm64, Homebrew Java 17.0.15, Gradle 8.14.4, Docker 29.2.1 and digest-pinned
MySQL 8.4.11. Raw input snapshots, exact commands, logs, JUnit, reports and the private
assembly/validation script are retained at
`/private/tmp/routecontract-a24-kotlin-online-20260908/`. No source project, Maven Local,
composite substitution, baseline rewrite, external adoption or production-support claim
is part of this evidence. Reported attempts are the bounded `SQLExecutionHook` observations,
not a complete route plan or transaction/business-success guarantee.
