# Current API entry and legacy migration contract (0.2 candidate)

Status: implementation acceptance, adopted before implementation. The focused
local regression passed; the full successor release gate remains pending. See
[retained results](evidence/current-entry-regression-2026-09-08.md) for exact
evidence labels and limits.
This is a changed application-entry contract, not a repair of immutable legacy
bytecode and not a passing result for original ADR A-28.

## Decision and preserved failure

New 0.2 applications use `io.github.ym0506.routecontract.api.RouteContract`.
Both `capture` and `captureResult` automatically reject an audited pre-0.2
all-in-one JAR before collector initialization, runtime service discovery, or
application-action entry. A caller does not have to remember a separate
bootstrap to obtain this capture-entry protection.

Original A-28 remains **FAILED**: its retained run observed four legacy-first,
5.5.2 direct-old-API diagnostic failures. The old `RouteContract` and
`CaptureRegistry` executed the immutable 5.5.3-only preflight before new code
could run. All 32 original collision cases prevented action and physical
business execution, but that observation does not satisfy the four missing
`RC_LEGACY_ADAPTER_COLLISION` diagnostics. The original acceptance, harness,
observations and receipts must remain unchanged.

The existing `io.github.ym0506.routecontract.RouteContract` FQCN remains a
compatibility facade on clean split dependency graphs. Previously compiled
public method and constructor descriptors remain usable there. When a consumer
bypasses dependency mediation and physically places an old JAR first, an old-FQCN
call can still execute old code; the new collision diagnostic is not guaranteed
for that unsupported mixed graph. This limitation is explicit, rather than
normalizing the old version diagnostic into a successful collision check.

This successor contract is an additional migration obligation. A future release
decision must identify it separately and preserve A-28's failed history; adding
this API alone does not close all 0.2 release gates.

## Product surface and implementation constraints

The new final utility class provides the existing `capture(String,
ThrowingRunnable)` and `captureResult(String, ThrowingSupplier<T>)` signatures,
returning the existing `RouteSnapshot` and `CapturedResult<T>` types. Existing
model and manifest packages do not move. Capture action exception identity,
cleanup, synchronous scope and nested-capture behavior remain unchanged.
The two public capture limits remain available on both entry classes. The old
facade is not annotated `@Deprecated` in this release.

The new `verifyRuntime()` returns the verified `ShardingSphereRuntimeIdentity`.
It performs the passive collision check and the existing complete runtime/SPI
preflight. Applications needing startup validation call it before constructing
their ShardingSphere datasource. It must not report success for a missing adapter,
a wrong exact runtime, or an invalid cached provider set.

`internal.CurrentRuntimeGuard` and the new public class must be absent from all
four actual, registry-verified distributed legacy JARs. Before touching a
collector or loading a runtime provider, the guard uses only JDK resource APIs
and class-name strings. It anchors inspection to its own/new public entry's
classloader and code source, checks the legacy hook class/service signature and
core duplicates, and then validates current core origins without initialization.
It must not anchor discovery to the shadowable old public class. It has no
success cache. A legacy collision produces `RC_LEGACY_ADAPTER_COLLISION` with an
actionable removal/re-resolution message and without private paths or raw SQL.
Other unsupported classloader or module layouts retain their explicit failure
boundary. Ordinary-SQL adapter constructor checks and full cached-provider
preflight are preserved; passive resource scanning does not replace either.

The supported topology remains one application classloader with a fixed complete
classpath before first ShardingSphere discovery. Fat JARs, relocation, arbitrary
custom loaders, hot attachment and module-path support are not added here.
Gradle/Maven consumer conflict policies remain required migration protections.

## Acceptance and evidence sequence

1. Establish the existing four failures from the retained original observations
   and verify the actual legacy JAR hashes and absence of the two new names.
2. Add focused unit/API tests for guard-before-action ordering, both capture
   entry methods, passive resource failures, duplicate/origin checks, no cached
   collision success, complete `verifyRuntime`, and clean old-FQCN compatibility.
   Run the relevant existing capture semantic tests; do not replace their API
   assertions with source-text checks.
3. Build new local candidate bytes. Using the retained exact 5.5.2 dependency
   graph and each actual old JAR first, run the original four failing inputs
   through **both new capture methods** in fresh JVMs. Keep actual classpath
   hashes, commands, selected entry/collector origins, action sentinels, exception
   classes and unmodified diagnostic text. Require the new collision marker,
   no action entry and no linkage failure. This is a focused local regression
   result, not full successor-contract or released-artifact verification.
4. Hold the full new matrix until final candidate bytes and their fingerprints
   are reviewed. That later gate must exercise every distributed legacy JAR,
   both exact runtime adapters, both physical JAR orders and both new capture
   methods; clean controls must cover new and old API behavior, startup preflight
   and actual MySQL operation evidence. Existing ordinary-SQL and API migration
   gates still apply to the final candidate.

Public evidence must distinguish source/unit checks, locally built candidate
bytes, reviewed staging, and public distribution. Never claim independent use,
0.2 publication, full A-28 success, or a full successor-matrix pass from the
focused local regression. Original v0.1.3 bytes and documentation stay immutable.

### A-29 final staged-byte plan

The full successor is a separate finite plan of 64 fresh-JVM checks, held until
all three coordinated candidate artifacts and their new receipt are reviewed:

- **32 capture collisions:** four actual distributed legacy JARs, two exact
  runtimes, legacy first/last, and both current capture methods. The action must
  remain unentered and the real cause chain must include the collision marker.
- **16 ordinary-SQL collisions:** the same legacy/runtime/order inputs, without
  any prior RouteContract API or bootstrap call. The actual MySQL business driver
  execution counter must remain zero when provider construction rejects the graph.
- **12 clean controls:** per runtime, both methods on the current and compatibility
  entries without SQL (four); ordinary SQL before any API (one); full
  `verifyRuntime()` followed by current `captureResult` around a real MySQL operation
  (one). No-SQL controls require action entry and an INCOMPLETE zero-attempt
  snapshot with `RC_NO_START_CALLBACK_OBSERVED`. SQL controls require the reviewed
  business result and one driver execution; captured SQL additionally requires a
  complete one-attempt schema-2 snapshot with the matching runtime identity.
- **Four startup rejections:** a missing adapter on each runtime and both
  wrong-exact-adapter pairs. Complete `verifyRuntime()` must fail before datasource
  construction or action entry, with the documented missing/wrong-runtime marker.

Every input JAR, resolved classpath and compiled probe is hashed before and after
execution. Record the selected current entry, compatibility entry, guard and
collector origins, the unmodified cause chain and the action/driver counters.
The plan runs against one frozen reviewed staging receipt; a partial selection
must report incomplete. The focused eight-cell runner and original A-28 runner
keep their existing scopes. The A-26 old-bytecode migration gate remains separate.
This paragraph specifies planned checks; it does not report a 64-cell execution.

## Application migration

For a new 0.2 application, replace the capture-entry import:

```java
// Previous compatibility entry:
// import io.github.ym0506.routecontract.RouteContract;

// Current guarded 0.2 entry:
import io.github.ym0506.routecontract.api.RouteContract;
```

Existing model, assertion and manifest imports stay the same. Existing calls to
`RouteContract.capture(...)`, `captureResult(...)` and the two capture-limit
constants keep their source shape after the import changes.

Remove the pre-0.2 all-in-one dependency and manually copied old JARs, select
exactly one matching 0.2 adapter, apply the documented Gradle/Maven consumer
conflict policy, re-resolve dependencies and restart the application JVM. Do not
try to fix a collision by changing physical JAR order. An application requiring
startup validation can invoke `RouteContract.verifyRuntime()` before datasource
construction; both capture methods enforce the entry check independently.

This page describes the unreleased 0.2 source candidate. The public v0.1.3
installation and its original API remain unchanged.
