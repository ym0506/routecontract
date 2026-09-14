# A-29 current-entry successor: reviewed 86a0be5 staging, 2026-09-08

**All 64 existing A-29 cases passed once on the reviewed final candidate.**
The [minimized receipt](current-entry-successor-86a0be5-2026-09-08.json) records
all cases, counters, snapshots, normalized class origins and raw evidence hashes.
Producer: `86a0be5d2e444f3b73925122fa448d9d1a324edd`; frozen consumer checkout:
`3ad510a0af972231fbd074607936ee52be3cad1f`, with identical production/publication
inputs. The reviewed receipt SHA-256 is
`1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e`.

**Original A-28 remains FAILED.** The [historical A-29 result](current-entry-successor-4e06694-2026-09-08.md)
and earlier focused eight-case result remain unchanged. A-29 verifies the
[current entry contract](../current-entry-migration-acceptance.md): new callers
use `io.github.ym0506.routecontract.api.RouteContract`. Legacy-first calls through
the old FQCN retain their documented diagnostic limit.

| Existing group | Passed | Observation |
| --- | ---: | --- |
| Capture collisions | 32/32 | Both methods, four actual old JARs, exact 5.5.2/5.5.3 and both physical orders; collision rejected before action |
| Ordinary SQL collisions | 16/16 | No prior API/bootstrap; datasource construction entered and collision rejected before business driver execution |
| Clean controls | 12/12 | Current/compatibility captures, ordinary MySQL, and full startup verification followed by captured MySQL |
| Startup rejections | 4/4 | Missing/wrong adapter pairs rejected before datasource, action or business execution |

All 48 collision cases returned `RC_LEGACY_ADAPTER_COLLISION` with zero action
entries and zero business driver executions. The new entry and guard came from
the reviewed core in every case. Legacy-first layouts selected the actual old
compatibility entry and collector, demonstrating the separate current entry.

Eight clean no-SQL captures entered their action once and returned schema-2
INCOMPLETE snapshots with zero attempts and `RC_NO_START_CALLBACK_OBSERVED`.
Four MySQL controls returned the fixed synthetic row with one business driver
execution each. Both captured-SQL controls returned COMPLETE one-attempt
snapshots with matching startup and snapshot identities.

All 64 process IDs were distinct. The input audit checked 30 frozen source files,
nine staged and nine registry-bound legacy payloads, both strict locked graphs,
compiled probe bytes and every command/classpath/origin against actual JAR bytes.
The 5.5.2 graph held 203 runtime artifacts (122 ShardingSphere); 5.5.3 held 145
(75 ShardingSphere). Both used Java 17.0.15, Gradle 8.14.4 and digest-pinned
MySQL 8.4.11. The owned disposable MySQL container was removed.

A separate audit reconstructed the 64 combinations without the runner's case
builder or classifier. All 64 JVM logs, the outer runner log and subprocess
assertion XML were read through EOF. The 52 expected caught exception chains
matched the observations; no uncaught, trailing, linkage or shutdown error was
found. The JSON binds both independent audit hashes.

Reproduce with the unchanged [runner](../../scripts/verify-current-entry-successor.py)
and the complete placeholder command in the JSON. Use the reviewed receipt,
producer revision, pinned Java/Gradle inputs and an absent evidence directory.
No subset, preparation-only run or production rebuild was used.

This is reviewed local staged-byte evidence. It does not establish public 0.2
availability, all release gates, module-path support, transaction commit or
independent adoption. A-26 old-bytecode migration remains a separate gate and has
its own [final candidate result](public-api-migration-86a0be5-2026-09-08.md).
The business driver counter excludes schema setup and datasource metadata SQL.
Raw paths, SQL, connection details, full causes and process IDs remain local.
