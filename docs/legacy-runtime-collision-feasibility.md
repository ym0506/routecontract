# A-28 legacy-first API shadowing: feasibility boundary

The original A-28 diagnostic requirement is a release gate. A runtime rejection
with a different diagnostic does not pass it. This note records a demonstrated
limitation and an architecture option, not a gate waiver or an implemented fix.
The [actual matrix](evidence/legacy-runtime-collision-2026-09-08.md) passed 28/32
collision assertions and all four clean controls, preserving four failures.
The executable fixture is specified in
[legacy-runtime-collision-acceptance.md](legacy-runtime-collision-acceptance.md).

## Path that bypasses current library code

The distributed 0.1.0, 0.1.2, 0.1.3 and 0.1.0-rc2 JARs own these same fully
qualified classes. Their relevant class bytes and service layout are pinned by
[the public input registry](../scripts/legacy-artifact-inputs.json).
With the legacy JAR first, the fresh JVM observations bind both public entry and
collector to that actual old JAR:

1. `io.github.ym0506.routecontract.RouteContract.capture(String, ThrowingRunnable)`
   calls `io.github.ym0506.routecontract.internal.CaptureRegistry.open(String)`.
2. That legacy `open` validates the operation ID, then calls the legacy
   `io.github.ym0506.routecontract.internal.ShardingSphere553Preflight.verify()`.
3. The old preflight checks the implementation version of
   `SQLExecutionHook` and `ShardingSphereServiceLoader` against **5.5.3** before
   discovering service providers.
4. On exact 5.5.2, that first version check throws the old exact-version error.
   Neither the current `RuntimeAdapterRegistry` nor the new adapter constructor
   executes. The capture action is not entered, but the exception has no
   `RC_LEGACY_ADAPTER_COLLISION` code.

On a clean split classpath, the same legacy public API descriptor resolves to
current core and its `CaptureRegistry.open` calls `RuntimeAdapterRegistry.verify`.
That clean compatibility is distinct from a classpath containing the old class
first. A guard inserted into current `RouteContract`, `CaptureRegistry`, or the
new adapter cannot execute before an invocation wholly owned by unchanged old
classes. Altering old bytes, replacing the application class loader, injecting
an agent, or changing which method the application calls would change the input
or execution contract; none is a small repair to the shadowed current method.

## Explicit current entry or bootstrap option

A new, non-colliding public class absent from every legacy JAR could give 0.2
applications an explicit current entry point, or a startup bootstrap called
before datasource construction and capture. Its first step would use a new,
non-colliding internal guard to enumerate class/service resources and compare
origins, rejecting legacy/core duplication before loading old collector code or
executing an action. It must not delegate to the shadowable legacy entry before
that check. Naming, API shape and implementation remain undecided. Adding only a new
method to the existing `RouteContract` class would instead resolve the old class
first and can fail with `NoSuchMethodError`; the public class name itself must
be absent from registered legacy JARs.

The existing public `RouteContract.capture` and `captureResult` descriptors could
remain available on clean split classpaths, retaining old-bytecode compatibility
through transitive core. Resolver enforcement remains necessary for ordinary
Gradle/Maven dependency consumers. An explicit bootstrap is an additional
application obligation: callers can omit it, and an already invoked old method
cannot be retroactively intercepted. Merely adding and testing this new entry
would **not** close the original direct-old-API A-28 failures.

Before choosing this design, specify the exact required entry sequence and its
relationship to the original gate; prove absent-name collisions against all
registered old JARs; test real old-first/last SQL and capture with the new entry;
rerun clean old-bytecode/source compatibility and both exact MySQL lanes after
any production change. Public release guards remain closed while the original
requirement is unresolved. No production code was changed for this investigation.

## Scope

The executable matrix uses separate cold JVMs with the complete, fixed classpath
visible to their default loader. It does not prove warmed ShardingSphere caches,
TCCL replacement, hidden providers, or same-process retry semantics. An old-only
provider registry initialized before a later class-loader change is a separate
risk hypothesis; it must not be presented as an observed result of this matrix.
