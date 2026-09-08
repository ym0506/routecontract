# CityPulse isolated RouteContract pilot — 2026-09-08

**SELF-PREPARED · UNSENT · NOT ADOPTION**

The [patch and recorded-command guide](citypulse-isolated-pilot-reproduction-2026-09-08.md) provides the unchanged
[two-file patch](citypulse-routecontract-0.1.3-first-observation.patch), pinned source, exact command structure and
required synthetic service/configuration preparation. The direct test command assumes
that isolation is already prepared; it is not a one-command environment installer.
The guide also records the absence of an explicit license in the pinned target tree.

The proposed two-file RouteContract 0.1.3 patch compiled with the complete CityPulse
application and test sources. Its selected integration test then ran once against
fresh synthetic MySQL and Redis services and passed without being skipped.
The captured final order lookup reported **2 physical JDBC execution attempts across
1 observed DataSource**. The complete-capture and no-reported-execution-failure
assertions passed alongside the existing business assertions.

This experiment was prepared by the RouteContract side. The CityPulse maintainer did
not request, approve or run it. No issue, PR, comment, DM or other outreach was sent.

| Item | Verified result |
| --- | --- |
| Target | `rexqd/citypulse-platform`, pinned `dccffc7a33965868a4b55ff9aae60bb831d76bad` |
| Patch | Original proposal; only test dependency and existing integration-test code |
| Compilation | All 204 application and 77 test source files compiled; Java 17.0.15, Maven 3.9.14 |
| Resolved dependencies | 276 JARs; all 73 ShardingSphere JARs exactly 5.5.3 |
| RouteContract | Public immutable 0.1.3 binary; test scope |
| Actual test | `VoucherOrderShardingIntegrationTest.routesFourOrderCombinationsAndKeepsConditionalPayIdempotent` |
| Surefire result | 1 test, 0 failures, 0 errors, 0 skips |
| Runtime | Temurin 17.0.17, Maven 3.9.11, Spring Boot 3.2.12, MySQL 8.4.11, Redis 7.4.2 |
| Observation | Final lookup only; 2 reported physical attempts, 1 observed DataSource |
| Business assertions | All 23 assertion source calls in the original class preserved; only the selected method was executed |
| Cleanup | Disposable containers, anonymous volumes and internal network removed |

The [minimized evidence](citypulse-isolated-pilot-2026-09-08.json) records source,
artifact and raw-evidence hashes. A separate read-only audit checked the actual
JUnit record, aggregate output, classpath JARs, unchanged source/configuration and
disposable-resource cleanup, with zero findings. The public 0.1.3 JAR SHA-256 remains
`9e883e618eb09d9ecf30814151bb4b0a43eba02c78d288cc582fa7e57e6edba2`.

The runtime used a new internal Docker network with no published ports and no
inherited owner configuration. Two empty shard schemas contained eight sharded
order/router tables and three support tables, created from the pinned repository's
DDL. No original database, demo rows or preparation/migration script was used.
The existing test created and cleaned its own synthetic fixtures.

The actual scheduling property, `hmdp.scheduling.enabled`, was explicitly false.
Delay-queue processing and shop warmups were also disabled. Dedicated Redis remained
necessary for unconditional Redisson, Pub/Sub and stream startup. The valid
`redis-stream` branch kept an idle consumer against the new empty Redis; this was
not an all-background-clients-disabled configuration. Kafka auto-configuration was
excluded for this DB-only experiment. These settings are local isolation scaffolding,
not a proposed production configuration or proof of the application's Kafka mode.

The unpatched original method was not separately run, and the full application test
suite was not executed. The captured lookup does not cover the earlier payment writes,
transaction commit, all routing paths, repeated stability or production traffic.
This first count does not establish an approved budget or baseline. No intentional
execution regression has yet been shown to fail a contract.

The original application's SQL logging remained active in the private raw logs.
Those logs and connection settings are not part of this public projection; only
aggregate observations, versions, counters and evidence digests are included.
