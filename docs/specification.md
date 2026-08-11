# RouteContract v0.1 specification

Status: implemented draft; public-release and independent-user evidence pending

## 1. User-visible problem

A repository or ORM test can keep returning the expected rows while a SQL or sharding-rule change expands one observed physical JDBC execution into several data sources. Ordinary result assertions stay green, so the change can reach production with higher database load or an unintended target.

The v0.1 user is a Java developer testing an application that embeds Apache ShardingSphere-JDBC 5.5.3.

## 2. Identity and scope

A capture is identified internally by a random `captureId`. Its public stable identity is a caller-supplied `operationId`, such as `find-order-by-user`.

Exactly one capture may be active on a calling thread. A nested capture is rejected. ShardingSphere worker threads must inherit the immutable `captureId` through a tested context propagation mechanism.

The action boundary begins immediately before the caller invokes the application operation and ends
after that synchronous invocation returns or throws. A v0.1 contract is eligible to pass only when
the caller returns normally, is not interrupted at close, and every observed callback returns
normally. Callback-failure snapshots remain diagnostic evidence and cannot become an approved
contract.

## 3. Input

- non-blank `operationId`;
- a synchronous action;
- optional route budget;
- optional approved manifest path.

## 4. Output

A deterministic `RouteSnapshot` containing:

- schema version;
- operation ID;
- capture status;
- observed starts, returned callbacks, failure callbacks and unknown-outcome counts;
- sorted distinct data-source names reported by the hook;
- sorted multiset of value-minimized physical SQL signatures;
- trunk and worker counts;
- collector error codes without secrets.

`RouteSnapshot` is in-memory diagnostic evidence and includes the observed data-source names,
trunk/worker flags and reported exception class. The canonical manifest replaces data-source names
with caller-reviewed aliases, groups equivalent attempts, and excludes thread flags and failure
class because they are either scheduling-dependent or diagnostic-only. No timestamp, UUID, thread
ID or event arrival order is written to the canonical manifest.

## 5. Event semantics

`SQLExecutionHook.start` reports one physical JDBC execution attempt. In the exact 5.5.3 executor,
`finishSuccess` is reported to the hook provider after the wrapped physical `executeSQL` call
returns; `finishFailure` reports the shown execution exception path.

Neither callback proves that the enclosing JDBC operation or application action completed, nor that
a surrounding transaction committed. An execution may start after routing and rewriting, so the
collector does not prove the complete planned route set.

The 5.5.3 adapter pairs `start` and `finish` in one provider instance because that exact runtime
creates a fresh non-singleton `SQLExecutionHook` provider for each physical callback lifecycle.
Preflight verifies that the `infra-executor` and `infra-spi` implementation versions both report
5.5.3 and that exactly one RouteContract provider is discovered; it does not inspect every artifact
in the dependency graph. Real integration tests protect the broader bounded assumption, and support
is not inferred for another ShardingSphere version or a mixed-version graph.

## 6. Capture state machine

```text
OPEN
  -> CLOSED_COMPLETE
  -> CLOSED_REPORTED_EXECUTION_FAILURE
  -> CLOSED_INCOMPLETE
```

- `CLOSED_COMPLETE`: every observed start has a terminal callback and the collector recorded no diagnostic.
- `CLOSED_REPORTED_EXECUTION_FAILURE`: at least one observed attempt ended in `finishFailure`.
  This is diagnostic-only because the exact 5.5.3 parallel executor can leave other submitted
  workers unjoined after an execution failure.
- `CLOSED_INCOMPLETE`: an attempt lacks a terminal callback, the collector failed internally, or ownership is ambiguous.

An incomplete capture must never be treated as a passing contract.
A reported-execution-failure capture must also never be treated as a passing contract or approved
manifest.

## 7. Invariants

- RC-01: an event is attributed only to the capture ID active when ShardingSphere submitted or ran that execution.
- RC-02: within the supported synchronous path, callbacks observed while two caller capture scopes
  are concurrently open are attributed to only one of those captures. This does not claim that the
  physical callbacks overlapped in time.
- RC-03: a closed capture does not receive events from a later operation.
- RC-04: callback code never propagates an internal RouteContract exception into the application SQL path.
- RC-05: every reported start is classified as callback-returned, callback-failure or unknown outcome.
- RC-06: canonical output is identical for the same semantic event multiset regardless of worker completion order.
- RC-07: raw parameter values and connection properties are never retained.
- RC-08: a contract violation fails after the application operation, not inside the JDBC callback.
- RC-09: a collector failure yields `INCOMPLETE`, not a false pass.
- RC-10: at most 10,000 attempts are retained per capture; the next start records
  `RC_ATTEMPT_LIMIT_EXCEEDED`, stops retaining additional attempts and makes the capture
  `INCOMPLETE`.

## 8. Privacy model

The in-memory snapshot stores:

- hook-reported data-source name;
- SHA-256 fingerprint of the exact hook SQL `String` encoded as UTF-8;
- parameter count and Java type names;
- trunk/worker flag;
- callback outcome and reported exception class name.

The canonical manifest stores:

- caller-provided, reviewed alias for the hook-reported data-source name;
- the same SQL fingerprint;
- parameter count and Java type names;
- callback outcome and structural multiplicity.

It does not store parameter values, connection properties or exception messages. Aliases must be
static and non-sensitive; using a raw data-source name as the alias exposes that name. Human-readable
SQL templates are outside the default v0.1 manifest until a safe opt-in policy is implemented and
tested.

## 9. Contract policies

The v0.1 verifier supports:

- maximum observed physical attempts;
- exact observed physical attempts;
- maximum distinct observed data-source names;
- allowed observed data-source-name set;
- complete capture and no callback-reported execution failures;
- approved canonical manifest equality with semantic added/removed signatures.

An automatic `FULL_ROUTE` or `BROADCAST` policy is not provided without an explicitly declared target universe.

## 10. Failure behavior

- blank operation ID or nested capture: reject before the action starts;
- application exception: close the capture without masking the original exception;
- hook internal exception: contain the non-fatal runtime exception at the callback boundary, record a diagnostic code and make verification incomplete;
- missing `finish` callback: mark the attempt incomplete;
- interrupted caller at capture close: record `RC_CALLER_INTERRUPTED_AT_CLOSE` and mark incomplete;
- callback-reported execution failure: retain minimized diagnostics but refuse route budgets and
  manifest matching;
- late/stale worker context: do not attach it to another capture; record diagnostic evidence when possible;
- missing baseline in verify mode: fail with an actionable message;
- malformed baseline: fail without rewriting it.

## 11. Alternatives considered

- Log parsing: rejected because it is configuration-dependent, may expose parameters and lacks deterministic operation ownership.
- Wrapping every physical `DataSource`: feasible for query counting, but requires application-specific wiring and does not use ShardingSphere's hook-reported data-source name.
- Java Agent: rejected for v0.1 because deployment and version risk exceed the contest schedule.
- Kernel `RouteContext` interception: rejected because it couples to non-public internals and observes planned rather than attempted execution.
- Global single capture: rejected after bounded MySQL tests proved caller/worker correlation for the supported synchronous path; arbitrary application async propagation remains out of scope.

## 12. Verification gates

Before concurrency support is published:

- MySQL single route and fan-out route;
- trunk and worker events share the correct capture;
- 20 identical repetitions produce the same manifest;
- two concurrently open caller operations remain isolated for their observed callbacks; the test
  must state separately whether physical callback overlap was forced or measured;
- worker reuse does not leak a closed capture;
- callback fault injection does not break the SQL result;
- Java 17 Linux CI passes on the exact supported dependency set.

The concurrency claim is limited to normally returned, non-interrupted synchronous
`PreparedStatement` operations. ShardingSphere 5.5.3 may return early from failure and interruption
paths without joining every submitted worker; RouteContract therefore fails those paths closed
instead of claiming a complete execution set.

Before release:

- at least four route-risk mutations and two safe controls;
- business assertion green / route contract red demonstration;
- comparison with Sharding Audit and a generic JDBC query-count tool;
- clean clone quick start;
- license, notice, third-party inventory and SBOM review.
