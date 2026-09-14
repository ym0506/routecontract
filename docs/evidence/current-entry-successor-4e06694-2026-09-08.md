# A-29 current-entry successor: reviewed 4e06694 staging, 2026-09-08

**A-29 passed 64/64 fresh-JVM checks** against independently reviewed, unsigned
local 0.2.0 staging from source `4e066942f6e244345fe908970b81446f9e08f64e`.
The [minimized receipt](current-entry-successor-4e06694-2026-09-08.json) binds the
exact artifacts, class origins, counters, snapshots and retained raw evidence.

**Original A-28 remains FAILED.** Its acceptance, harness and receipts are
unchanged, as is the earlier eight-cell focused regression. A-29 verifies the
[new application-entry contract](../current-entry-migration-acceptance.md): new
0.2 callers use `io.github.ym0506.routecontract.api.RouteContract`. An old-FQCN
call with an immutable old JAR first retains its documented diagnostic limit.

| Verified group | Passed | Required observation |
| --- | ---: | --- |
| Current capture collisions | 32/32 | Both methods, four actual old JARs, two exact runtimes, both JAR orders; collision cause from the current guard before action |
| Ordinary-SQL collisions | 16/16 | No prior API/bootstrap; actual datasource construction guard; zero business driver executions |
| Clean controls | 12/12 | Current and compatibility captures, ordinary MySQL, full startup verification followed by captured MySQL |
| Startup rejections | 4/4 | Missing/wrong exact adapters rejected before datasource, action or business execution |

The legacy inputs were the registry-bound **0.1.0, 0.1.2, 0.1.3 and 0.1.0-rc2**
JARs. Every collision produced `RC_LEGACY_ADAPTER_COLLISION`; all 48 collision
cells had zero action entries and zero physical business executions, with no
linkage failure. The new entry and guard always came from the reviewed core.
Legacy-first cases still selected the compatibility entry and collector from the
actual old JAR, demonstrating the new entry's separate protection.

Eight clean no-SQL captures entered their action once and returned schema-2
INCOMPLETE snapshots with zero attempts and `RC_NO_START_CALLBACK_OBSERVED`.
The four real MySQL controls each returned the fixed fixture row with exactly
one business driver execution. The two captured-SQL controls also returned
COMPLETE one-attempt snapshots and matching startup/snapshot runtime identities.

Both locked dependency graphs were independently resolved with strict checksum
verification and fresh caches. The 5.5.2 lane contained 203 runtime artifacts,
including 122 ShardingSphere artifacts; the 5.5.3 lane contained 145, including
75 ShardingSphere artifacts. Both used OpenJDK **17.0.15** and pinned MySQL
**8.4.11**; the receipt includes the image digest. The disposable container was
removed after completion.

The runner's **25 unit tests passed**. A separate audit reconstructed all 64
required combinations without reusing the runner's classifier and found zero
discrepancies and 64 distinct process IDs. Another audit checked every raw
command/observation/result/log hash, staged and legacy payloads, dependency graph,
compiled probe, source binding and preserved evidence. The prepared and final
probe bytecode matched; no RouteContract production build occurred in this run.

Key retained hashes:

- Raw summary: `19284cd39359f2ef393e97ff4841f2612cb75654618d24d47d0152d3a836deb4`
- Reviewed nine-payload receipt: `38b2269eca162f121fd3996c56df8b894ae2f43cedeb08fcc627032cf70eaa43`
- Independent raw-observation audit: `2f957fd148ee7e0c012ca206cb8e977ea8462c5ed322405f0a29727635450f6e`
- Independent input/record audit: `00552aff8b9a48206966e76be9fb075645bbb95432efc186924b8f3382d1fc25`

This is a local staged-byte result. It does not establish public 0.2 availability,
independent adoption, an independent reproducible build, transaction commit or
completion of all release gates. The business driver counter excludes direct
schema setup and datasource metadata SQL. A-26 old-bytecode migration remains a
separate gate. Raw paths, JDBC details, full cause messages and process IDs stay
local; this receipt is a minimized projection of the retained observations.

These result files and the acceptance status update were written after the run
and both audits. The receipt retains the original execution-time document hash;
the historical focused result continues to describe its earlier, narrower scope.
