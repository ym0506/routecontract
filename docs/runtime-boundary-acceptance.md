# Remaining staged runtime boundary acceptance

Status: **FAILED — 24 of 28 cases passed** against the reviewed `4e06694` artifacts.
The finite plan below was established before implementation and remains unchanged.
See the [executed evidence](evidence/runtime-boundary-4e06694-2026-09-08.md) and
[public evidence record](evidence/runtime-boundary-4e06694-2026-09-08.json).
This covers existing ADR A-01–A-08, A-10, A-18 and A-19 obligations against the
reviewed unsigned 0.2.0 artifacts from `4e06694`. It does not add support promises,
JDKs, database versions or workload families. A-09, A-11–A-13 and A-23's complete
corpus/human review are owned by separate evidence tasks. Original A-28 remains
FAILED; the completed A-29 runner, fixtures and results remain unchanged.

## Finite plan: 28 fresh JVMs

Use exact ShardingSphere-JDBC 5.5.2 and 5.5.3, Java 17, and digest-pinned MySQL
8.4.11. Every cell uses actual reviewed core/adapter JARs and the corresponding
locked third-party graph. There are no legacy JARs or production source substitutes.

| Group | Cells | Existing obligation and required result |
| --- | ---: | --- |
| Ordered isolation | 2 | A-01/A-02/A-03: one JVM per exact matching pair; ordinary SQL → capture → ordinary SQL → second capture. All four operations return the fixed row, each delegates once to the actual driver; each capture contains only its own one-attempt operation. |
| Wrong adapter capture | 2 | A-04/A-05: each wrong exact pair, current `capture` action sentinel unentered; `RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME`. |
| Wrong adapter ordinary SQL | 2 | A-06: each wrong exact pair, no earlier API/bootstrap, datasource provider construction rejects with `RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME`; no business driver delegation or linkage error. |
| Both adapters on classpath | 8 | A-07/A-08: both exact runtimes × both physical adapter orders × current capture/ordinary SQL. All reject with `RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS` before action/business SQL. |
| Core-only ordered sequence | 2 | A-10: ordinary SQL succeeds without a RouteContract adapter, then current capture rejects with `RC_ADAPTER_NOT_FOUND`; action remains unentered. |
| Named consumer, one adapter | 4 | A-18: both exact matching pairs × capture/ordinary SQL. Consumer, core and adapter are actually named modules; stable `RC_UNSUPPORTED_MODULE_PATH`, zero action/business driver calls. |
| Named consumer, both adapters | 8 | A-19: both exact runtimes × both physical module-path adapter orders × capture/ordinary SQL. Stable `RC_UNSUPPORTED_MODULE_PATH` in every cell, without linkage error or accidental success. |

Before runtime execution, retain successful `jar --describe-module` output for
all three reviewed JARs. Required automatic names are
`io.github.ym0506.routecontract.core`,
`io.github.ym0506.routecontract.shardingsphere552`, and
`io.github.ym0506.routecontract.shardingsphere55` (existing 5.5.3 coordinate).
This metadata check is not evidence of JPMS execution support.

The named consumer has its own real module descriptor. Put only the named
consumer and the selected actual RouteContract artifacts on the module path;
keep the exact ShardingSphere/JDBC dependency graph on the classpath. The consumer
explicitly reads that unnamed graph through `--add-reads`; this avoids unrelated
third-party module resolution failures while exercising the documented
RouteContract named-module boundary. Resolve all selected adapter modules,
including both orders in dual-adapter cells. The named launcher explicitly roots
`java.instrument` and `jdk.unsupported` alongside `ALL-MODULE-PATH`. The unchanged
unnamed third-party graph needs `ClassFileTransformer` and `sun.misc.Unsafe`; both
were verified in the actual Java 17 JMODs. Keep all RouteContract types named and
retain the required unsupported-module diagnostic. Record actual module names and named
status, code sources, and loader identities after the tested invocation. The named
fixture compiler uses `--release 17 -Xlint:unchecked,-module -Werror`: the existing
`ym0506` namespace triggers javac's terminal-digit module-naming convention warning,
so that naming lint is explicitly excluded. Module resolution and the actual
module-path execution boundary remain required.

## Observations and completion

The fixed representative SELECT returns `201:3:PAID`. Its real driver wrapper
counts immediately before delegation and records the exact driver SQL hash,
without putting SQL text or parameter values in the final public projection.
Direct schema setup and datasource metadata SQL are outside the business counter.
No hook evidence is a transaction-commit claim.

For ordered isolation, record each step's action/driver deltas and business rows,
two complete schema-2 snapshots, callback outcome/counts, datasource alias,
parameter shape and fingerprints. Each snapshot's one fingerprint must match the
corresponding actual driver statement. Compare the two captures and the two exact
runtime lanes for this representative operation's callback/count/fingerprint
parity, excluding the intentionally versioned runtime identity and operation IDs.
This is the existing ordered representative operation obligation; the full A-23
corpus remains separate.

Capture-negative cells must fail before datasource construction or action entry.
Ordinary-SQL-negative cells must reach datasource factory construction without any
prior RouteContract API/bootstrap, include the actual adapter construction guard
in the cause stack, and keep the business driver count zero. Core-only cells
must preserve the successful preceding ordinary step and fail only at capture.
Named cells additionally prove that the consumer and selected first-party types
are in the requested named modules. Keep the real exception classes/messages and
frames locally; do not turn raw linkage or setup failures into passing markers.

Hash the nine reviewed staged payloads, source inputs, exact classpaths/module
paths, compiled classpath/named consumer outputs, commands, logs and observations.
Use the independently reviewed receipt SHA-256
`38b2269eca162f121fd3996c56df8b894ae2f43cedeb08fcc627032cf70eaa43`.
Recheck inputs after execution. Full verification requires exactly all 28 planned
case definitions, 28 distinct JVM process identities, every assertion passing and
both ordered parity observations. A diagnostic subset remains incomplete, even
when every selected cell succeeds. Preparation verifies/compiles fixtures and
module metadata only; it cannot pass this runtime gate.

Freeze the implementation, tests, plan and reviewed-input hashes and return the
ready command before a full execution. Any actual product failure is retained
and reported before considering a production fix. No signing, publication,
credential access or overwrite of earlier evidence is part of this runner.

## Preserved first execution and fixture correction

The original full 28-cell execution completed with **22 passes and six failures**.
Its raw summary SHA-256 is
`eef95298efbc53a0226f8b062c0d76debdafe7854d3823fcbc5acc1f33020ae5`.
Every named ordinary-SQL cell failed during third-party setup before any
RouteContract construction guard: the 5.5.2 TTL path could not load
`java.lang.instrument.ClassFileTransformer`, and the 5.5.3 Caffeine/Groovy path
could not load `sun.misc.Unsafe`. These actual classes belong to `java.instrument`
and `jdk.unsupported` in the same tested JDK. The named-main launcher had not
resolved those JDK roots.

The corrected fixture explicitly adds exactly those two JDK modules to the named
launch roots. Production JARs, the 28-cell plan and required
`RC_UNSUPPORTED_MODULE_PATH` remain unchanged. The earlier FAILED record remains
immutable. The corrected frozen fixture was subsequently executed once. Both single-adapter
named SQL cells passed. All four named dual-adapter SQL cells reached hook provider
construction and failed the unchanged criterion: descriptor validation produced
`RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS` before the required
`RC_UNSUPPORTED_MODULE_PATH`. Action entries and physical business-driver calls
were zero. This establishes a product diagnostic-priority failure; it is separate
from the earlier setup failures. An independent audit read all 658 original log lines
through EOF and found no extra uncaught or shutdown exceptions beyond the recorded
failure chains.


## Corrected execution: 24 of 28 passed

The full unchanged plan executed in 28 distinct JVMs. Ordered capture parity and
all other rows passed; the four A-19 ordinary-SQL cells failed in both exact
runtimes and both physical adapter orders. The actual discovered provider was
the 5.5.2 hook in all four cases; physical module-path order does not guarantee
ServiceLoader discovery order. Provider construction was triggered during query
execution after datasource creation, before physical business-driver delegation.

All six executed source files, 27 source fingerprints and nine reviewed staged
payloads remained unchanged. The independent raw audit read all 646 log lines
through EOF and found no additional uncaught, shutdown or linkage errors. The
[public evidence record](evidence/runtime-boundary-4e06694-2026-09-08.json) retains
both execution histories and their raw summary and audit hashes.

This result remains **FAILED**. A coordinated production guard-priority fix must
be tested using separately reviewed candidate bytes. The original `4e06694`
results cannot validate that later change or establish module-path support.
