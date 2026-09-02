# ADR: version-scoped ShardingSphere-JDBC adapters for RouteContract 0.2.0

Status: implemented and verified in the local 0.2 candidate; not released and not a support claim.

Target release: `0.2.0`.

Decision scope: classpath and module-path isolation, artifact metadata, manifest compatibility,
verification, migration, and publication for exact Apache ShardingSphere-JDBC 5.5.2 and 5.5.3
runtimes.

This document uses two evidence classes deliberately:

- **Observed** means reproduced or inspected against the current 5.5.3 implementation, the initial
  5.5.2 spike, the current local 0.2 candidate, or the named upstream artifacts.
- **Planned** means a required 0.2.0 release gate. A planned item is not released, supported, or
  published merely because it appears in this ADR or is implemented in a local candidate.

The local 0.2 candidate now includes exact 5.5.2 and 5.5.3 adapters, real-MySQL coverage, and
separate Gradle and Maven split-artifact consumers. Those checks are local pre-release evidence;
they do not establish a public artifact, public CI result, or external adoption.

The current released contract remains exact ShardingSphere-JDBC 5.5.3. Multiple ShardingSphere
versions are explicitly outside the v0.1 scope. Nothing in this ADR changes the immutable `v0.1.2`
tag, Release, assets, or the meaning of
`io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.2`.

## 1. Context and observed facts

RouteContract is loaded as a ShardingSphere `SQLExecutionHook` provider. That makes binary
compatibility a precondition for ordinary ShardingSphere SQL, not only for calls wrapped in
`RouteContract.capture(...)`.

The following facts are verified at the design baseline used for this ADR.

| ID | Observed fact | Consequence |
| --- | --- | --- |
| O-01 | In ShardingSphere 5.5.2, `SQLExecutionHook.start(...)` accepts `org.apache.shardingsphere.infra.database.core.connector.ConnectionProperties`. | A 5.5.2 provider has a version-specific JVM method descriptor. |
| O-02 | In ShardingSphere 5.5.3, the same method accepts `org.apache.shardingsphere.database.connector.core.jdbcurl.parser.ConnectionProperties`; the interface also extends `ShardingSphereSPI`. | A provider compiled for 5.5.2 is not binary-compatible with 5.5.3, and vice versa. |
| O-03 | A copied 5.5.2 provider can be instantiated on a 5.5.3 runtime, but the first callback throws `AbstractMethodError`. The reverse combination fails symmetrically. | Capture-time preflight alone is too late; a wrong adapter can break ordinary SQL before a capture begins. |
| O-04 | The copied 5.5.2 spike and the 5.5.3 JAR share 36 class-file paths out of 37, including the public API, collector, provider FQCN, and service implementation. | Flat-classpath order silently selects one copy; duplicate-provider counting cannot reliably detect co-installation. |
| O-05 | The copied JARs produce split packages on the module path, and `--validate-modules` fails. | Full-module copying is not a JPMS-compatible isolation mechanism. |
| O-06 | The copied spike's strict build stops before compilation because 147 resolved 5.5.2 artifacts are absent from reviewed dependency-verification metadata. With dependency verification disabled, 38 unit tests pass. | The spike is useful ABI evidence only; it is not trusted-build, MySQL, or release evidence. |
| O-07 | The current 0.1.2 5.5.3 release-asset POM contains TTL and Jackson runtime dependencies but no ShardingSphere runtime dependency or compatibility constraint. Its Gradle metadata has no ShardingSphere constraint or mutual-exclusion capability. | A consumer resolver can currently assemble an unsupported mixed graph without metadata-level rejection. |
| O-08 | Both relevant ShardingSphere versions discover providers through `ServiceLoader.load(serviceClass)` and cache the discovered set globally per service-interface class. | The TCCL visible at first ShardingSphere discovery is a support boundary; later visibility cannot be assumed to attach a provider. |
| O-09 | The v0.1 manifest schema is `1` and contains no adapter/runtime identity. The current preflight checks only the `infra-executor` and `infra-spi` package implementation versions and exactly one current provider. | A structurally equal 5.5.2 candidate could otherwise be compared with a 5.5.3-approved baseline without declaring the changed runtime contract. |
| O-10 | At the design baseline, no 5.5.2 real-MySQL corpus, Maven consumer, Gradle consumer, wrong-runtime public CI lane, or released artifact existed. The local 0.2 candidate now provides the first three; public CI and a released artifact still do not exist. | Exact 5.5.2 support remains unreleased. Local pre-release evidence cannot establish a public support claim. |
| O-11 | The immutable `v0.1.0`, `v0.1.1`, and `v0.1.2` tag trees, plus the audited RC tag trees, contain the same all-in-one public classes, legacy hook-provider FQCN, capture registry, and hook service descriptor. | Collision handling must identify the pre-0.2 all-in-one layout, not special-case version 0.1.2. |

The hook evidence keeps the existing claim boundary: it is a ShardingSphere-reported physical JDBC
execution attempt, not a complete route plan, transaction result, or business-success signal.

## 2. Decision

RouteContract 0.2.0 will use one version-neutral core and two exact-version thin adapters. It will
not copy the complete 5.5.3 module, reuse one hook provider class across both ABIs, or reinterpret
the existing `5.5` artifact name as meaning every 5.5.x version.

### 2.1 Exact artifact and module graph

All three artifacts use group `io.github.ym0506.routecontract` and the coordinated version
`0.2.0`.

| Gradle project / Maven artifactId | Exact role | Package ownership | Automatic module name (metadata only) |
| --- | --- | --- | --- |
| `routecontract-core` | ShardingSphere-neutral public API, capture registry, minimized model, manifest codec/verifier, and the narrow internal adapter bridge | `io.github.ym0506.routecontract`, `io.github.ym0506.routecontract.manifest`, `io.github.ym0506.routecontract.internal`, `io.github.ym0506.routecontract.spi` | `io.github.ym0506.routecontract.core` |
| `routecontract-shardingsphere-5.5` | Existing GAV, still exact ShardingSphere 5.5.3; depends on core through an API/transitive edge | `io.github.ym0506.routecontract.shardingsphere553.internal` only | `io.github.ym0506.routecontract.shardingsphere55` |
| `routecontract-shardingsphere-5.5.2` | New exact ShardingSphere 5.5.2 adapter; depends on core through an API/transitive edge | `io.github.ym0506.routecontract.shardingsphere552.internal` only | `io.github.ym0506.routecontract.shardingsphere552` |

The existing 5.5.3 automatic-module name is retained for artifact identity. Every JAR must carry
the table's `Automatic-Module-Name`, but 0.2.0 deliberately ships no `module-info.class` and does
not support JPMS module-path execution. The core extraction changes which JAR owns the public
packages, and an automatic adapter module cannot declare a reliable transitive readability edge or
the `uses`/`provides` graph required by the two service loaders. Supporting JPMS is a later ADR and
release lane; 0.2.0 fails module-path execution closed instead of treating accidental resolution as
support.

The documented public user API keeps its existing FQCNs and method descriptors in
`routecontract-core`. This compatibility promise excludes every `.internal` FQCN, including the
old public-at-the-bytecode-level
`io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook`; service providers are
implementation details and intentionally move to the version-specific packages.
`io.github.ym0506.routecontract.spi` is a public-at-the-JVM-boundary, documented-internal bridge,
not a supported user extension API. It contains only:

- `RouteContractRuntimeAdapter`, which returns a verified runtime identity and performs the
  version-specific runtime/provider preflight; and
- a narrow hook bridge with an opaque attempt handle so that an adapter can report start,
  callback-returned, callback-failure, and stable diagnostics without accessing core collector
  implementation classes directly.

No ShardingSphere class may appear in a core signature, constant pool, dependency, or service
descriptor. No `.class` path may occur in both adapter JARs. Shared implementation belongs in core,
not in a shared source set compiled into both adapters.

### 2.2 Exact providers and service graph

Each adapter JAR contains two distinct provider classes and two service declarations.

| Adapter | ShardingSphere hook provider | Core runtime-adapter provider |
| --- | --- | --- |
| 5.5.3 | `io.github.ym0506.routecontract.shardingsphere553.internal.RouteContract553SqlExecutionHook` | `io.github.ym0506.routecontract.shardingsphere553.internal.ShardingSphere553RuntimeAdapter` |
| 5.5.2 | `io.github.ym0506.routecontract.shardingsphere552.internal.RouteContract552SqlExecutionHook` | `io.github.ym0506.routecontract.shardingsphere552.internal.ShardingSphere552RuntimeAdapter` |

The service files are exact:

```text
META-INF/services/org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook
META-INF/services/io.github.ym0506.routecontract.spi.RouteContractRuntimeAdapter
```

The first file contains exactly the version-specific hook provider from the table. The second
contains exactly the matching runtime-adapter provider. There are no comments, fallback providers,
or multiple lines.

Core discovers its runtime adapter with the core-defining loader, equivalent to:

```java
ServiceLoader.load(RouteContractRuntimeAdapter.class, RouteContract.class.getClassLoader())
```

It requires exactly one visible provider. ShardingSphere continues to control discovery of the
`SQLExecutionHook`; RouteContract does not reset, replace, or reflectively modify ShardingSphere's
static service cache. The supported classpath therefore makes the same adapter provider visible to
both `RouteContract.class.getClassLoader()` and the TCCL used for the first ShardingSphere service
discovery, and both loaders must resolve the same core, bridge, and provider class identities.

### 2.3 Fail-closed runtime contract

The build metadata is the first line of defense. Runtime checks are a necessary second line for
Maven overrides and manually assembled classpaths that otherwise remain inside the supported
single-application-classloader topology. A stable diagnostic observed in a shaded application,
plugin container, or other unsupported topology does not make that topology supported. The guard
also does not prove every non-anchor JAR in an arbitrary manual classpath; whole-group protection
comes from the consumer resolver rule or the separately verified complete-graph tool.

There are two non-recursive verification phases.

**Hook-construction guard.** The version-specific hook constructor runs while ShardingSphere may be
inside its own `ServiceLoader` initialization. It must not call the core runtime-adapter
`ServiceLoader`, query ShardingSphere's cached provider collection, or instantiate another hook.
It performs only self-contained checks: exact version-specific runtime anchors, coherent anchor
origins, core bridge class identity, module-path rejection, and passive enumeration of service
descriptor resources needed to detect dual or legacy adapters. This phase protects ordinary SQL
before any RouteContract capture.

**Capture preflight.** After provider discovery has returned and immediately before the caller's
capture action, core may discover the core runtime adapter and inspect the already initialized
ShardingSphere provider set. It verifies all of the following:

1. exactly one core runtime-adapter provider is visible;
2. the provider, core bridge, and collector are compatible and use the supported loader
   relationship;
3. `infra-executor`, `infra-spi`, and the version-specific `ConnectionProperties` owner report the
   adapter's exact version;
4. the three runtime anchors have coherent code-source origins and do not form a mixed 5.5.2/5.5.3
   graph; and
5. ShardingSphere's cached hook-provider set contains exactly the matching RouteContract hook; and
6. no audited pre-0.2 all-in-one JAR, legacy provider class, or legacy provider service entry is
   visible alongside any 0.2.0 core or adapter.

The constructor phase turns an ordinary-SQL wrong-runtime failure into a stable RouteContract
diagnostic before the JVM attempts the incompatible `start(...)` dispatch. Keeping it separate
from capture preflight prevents recursive `ServiceLoader` entry. A process-global, unkeyed
`verified` boolean is forbidden. Any cache must be scoped to the provider/core classloader and the
complete verified runtime-anchor tuple; otherwise verification occurs for every capture/provider
construction.

The planned stable runtime markers are:

| Marker | Meaning |
| --- | --- |
| `RC_ADAPTER_NOT_FOUND` | No core runtime-adapter provider is visible. |
| `RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS` | More than one versioned RouteContract adapter is visible. |
| `RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME` | The selected adapter and an observed runtime anchor have different or unavailable exact versions. |
| `RC_MIXED_SHARDINGSPHERE_RUNTIME` | Runtime anchors report different supported versions or incompatible code-source origins. |
| `RC_ADAPTER_CLASSLOADER_MISMATCH` | Core, bridge, adapter, or provider class identity crosses an unsupported loader boundary. |
| `RC_SHARDINGSPHERE_PROVIDER_NOT_ACTIVE` | The matching adapter exists, but ShardingSphere's first-use cache does not contain its hook provider. |
| `RC_LEGACY_ADAPTER_COLLISION` | A pre-0.2 all-in-one JAR/provider layout is visible with a 0.2.0 core or adapter. |
| `RC_UNSUPPORTED_MODULE_PATH` | RouteContract 0.2.0 was loaded as named modules rather than on the supported classpath. |

These errors must preserve the marker in the top-level exception message or stable cause chain.
Wrong-version and dual-adapter tests must explicitly prove that neither `AbstractMethodError` nor a
silently empty successful capture escapes instead.

## 3. Runtime identity and baseline compatibility

### 3.1 Manifest schema 2

New captures and candidates use snapshot/manifest schema `2`. The canonical manifest contains this
object immediately after `schemaVersion`:

```json
{
  "schemaVersion": 2,
  "runtimeIdentity": {
    "adapterId": "apache-shardingsphere-jdbc/sql-execution-hook",
    "adapterContractVersion": 1,
    "infraExecutorImplementationVersion": "5.5.3",
    "infraSpiImplementationVersion": "5.5.3"
  },
  "operationId": "orders.find-by-user-id",
  "captureStatus": "COMPLETE",
  "policy": {},
  "counts": {},
  "attempts": []
}
```

For a 5.5.2 capture, both implementation-version strings are exactly `5.5.2`. The public immutable
value type is `io.github.ym0506.routecontract.ShardingSphereRuntimeIdentity`. It belongs to the
capture model because the identity is frozen before a manifest exists; the manifest package
consumes rather than owns it.

The identity records the callback contract being approved, not a claim about the complete
dependency graph. Java/JVM version, database version, RouteContract distribution version, code
sources, and the connection-properties anchor belong in reproducibility receipts and runtime
preflight evidence, not in this canonical identity. A semantic change to capture meaning requires
an `adapterContractVersion` or schema increment.

The verified identity is fixed when the capture opens, stored in `RouteSnapshot`, and copied to the
manifest. Candidate creation must not infer it later from an ambient classpath.

The old documented-public constructor descriptors for `RouteSnapshot` and
`ObservedExecutionManifest` remain as explicit overloads so existing bytecode can link. They
create only schema-1/implicit-5.5.3 values. This is a binary-linkage bridge, not a promise that
source recompilation, reflective record-component enumeration, `toString`/equality shape,
serialization, code-source location, or module-path ownership is unchanged. Those migration
surfaces have separate tests and release notes. In particular, recompiling old source that passes
`CURRENT_SCHEMA_VERSION` to a legacy constructor inlines the new value `2`, which that schema-1-only
overload must reject; such source must migrate to the explicit-identity constructor. New code must
not use the legacy overloads to fabricate a 5.5.2 identity. No `.internal` constructor or FQCN is
covered by this bridge.

### 3.2 Schema-1 normalization and comparison

Schema 1 has one defensible implicit meaning: exact 5.5.3 with adapter contract 1. The v0.1.2
preflight admitted only the 5.5.3 executor/SPI pair. Therefore a schema-1 baseline can be read
without being rewritten and normalized for comparison as:

```text
adapterId = apache-shardingsphere-jdbc/sql-execution-hook
adapterContractVersion = 1
infraExecutorImplementationVersion = 5.5.3
infraSpiImplementationVersion = 5.5.3
```

Compatibility is exact:

| Approved manifest | Candidate manifest/snapshot | Result before ordinary policy/drift checks |
| --- | --- | --- |
| schema 1, implicit 5.5.3 | schema 1, implicit 5.5.3 | Comparable; existing structural rules apply. |
| schema 1, implicit 5.5.3 | schema 2, explicit 5.5.3 | Comparable; structural equality may produce `MATCH`. |
| schema 2, explicit 5.5.3 | schema 1, implicit 5.5.3 | Comparable; structural equality may produce `MATCH`. |
| schema 1, implicit 5.5.3 | schema 2, explicit 5.5.2 | `INCOMPATIBLE` with `RCM005`. |
| schema 2, explicit 5.5.2 | schema 2, explicit 5.5.2 | Comparable; structural rules apply. |
| schema 2, explicit 5.5.3 | schema 2, explicit 5.5.2 | `INCOMPATIBLE` with `RCM005`. |
| either supported identity | decoded schema 2 with a structurally valid but unknown, mixed, or unsupported identity value | `INCOMPATIBLE` with `RCM004`. |
| decoded positive unsupported schema with all fields valid for the decoder | any decoded candidate | `INCOMPATIBLE` with existing `RCM001`. |
| missing/null/malformed `runtimeIdentity`, duplicate/unknown JSON property, invalid field type, or otherwise undecodable document | any | `ManifestFormatException`; verification does not run and emits no `RCM` finding. |

The new stable manifest findings are:

- `RCM004` / `UNSUPPORTED_RUNTIME_IDENTITY`: the adapter ID/revision or executor/SPI pair is not
  supported;
- `RCM005` / `RUNTIME_IDENTITY_MISMATCH`: both identities are individually supported but differ.

Both are `BLOCKING`. Compatibility precedence is `RCM001` schema, `RCM004` unsupported identity,
`RCM005` identity mismatch, `RCM002` operation, then `RCM003` approved eligibility. A schema-2
document missing `runtimeIdentity` is malformed at decode time; `RCM004` is only for a decoded,
structurally valid identity whose values are unsupported. Likewise, `RCM001` is only a verifier
result for a successfully decoded manifest, not a substitute for strict JSON/schema-shape errors.
No verification path rewrites, approves, or replaces the human-owned approved baseline.

## 4. Dependency-resolution contract

### 4.1 Gradle

Each adapter publishes its normal component capability and the same exclusive capability on both
`apiElements` and `runtimeElements`:

```groovy
def exclusiveAdapterCapability =
        'io.github.ym0506.routecontract:routecontract-shardingsphere-hook-adapter:1'

['apiElements', 'runtimeElements'].each { configurationName ->
    configurations.named(configurationName) {
        outgoing.capability("${project.group}:${project.name}:${project.version}")
        outgoing.capability(exclusiveAdapterCapability)
        if (project.name == 'routecontract-shardingsphere-5.5.2') {
            outgoing.capability(
                    "${project.group}:routecontract-shardingsphere-5.5:${project.version}")
        }
    }
}
```

The capability version `1` identifies one mutually exclusive hook slot; it is not the RouteContract
release version. A graph containing both adapters must fail resolution regardless of declaration
order. In addition, the 5.5.2 adapter publishes this compatibility alias on both variants:

```text
io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.2.0
```

That is the implicit/default capability already owned by the existing 5.5.3 GAV. Giving the 5.5.2
adapter the same capability makes Gradle detect both new-adapter co-installation and
5.5.2-adapter-0.2.0 + any same-GA pre-0.2 all-in-one release without requiring immutable legacy
metadata to be changed. Generated module-metadata tests assert both the shared hook-slot capability
and this legacy-GAV alias.

The 5.5.2 adapter uses a literal strict executor dependency and literal strict anchor constraints:

```groovy
dependencies {
    api project(':routecontract-core')

    implementation('org.apache.shardingsphere:shardingsphere-infra-executor') {
        version { strictly('5.5.2') }
        because 'SQLExecutionHook has an exact 5.5.2 binary descriptor'
    }
    constraints {
        implementation('org.apache.shardingsphere:shardingsphere-infra-spi') {
            version { strictly('5.5.2') }
        }
        implementation('org.apache.shardingsphere:shardingsphere-infra-database-core') {
            version { strictly('5.5.2') }
        }
    }
}
```

The 5.5.3 adapter has the same structure with exact `5.5.3` and
`shardingsphere-database-connector-core` as the connection-properties anchor. Published Gradle
module metadata must contain the strict constraints and exclusive capability; generated metadata
is tested, not inferred from the build script.

Anchor constraints alone are insufficient. A different non-anchor ShardingSphere component can
still introduce a mixed graph. Each supported Gradle consumer must also apply a fail-closed group
rule to every dependency request and selected component whose group is exactly
`org.apache.shardingsphere`: every such component must resolve to the adapter's exact version.
RouteContract publishes the audited rule as copyable consumer policy and applies it in every
fixture. The checked-in lock and dependency-verification metadata enumerate the reviewed complete
closure. A negative fixture keeps executor/SPI/database anchors correct while forcing one
non-anchor component to the other version; resolution must fail before compilation.

The consumer rule has two assertions rather than silently rewriting a request: reject any explicit
request in that group whose version is not the expected literal, then inspect the completed
`ResolutionResult` and reject any selected component in that group whose version is not the same
literal. For a 5.5.2 lane the literal is `5.5.2`; for a 5.5.3 lane it is `5.5.3`. A versionless or
dynamic request is rejected unless a reviewed platform has already converted it to a literal
before this policy runs.

### 4.2 Maven and manual classpaths

Each adapter POM publishes `routecontract-core` as a compile dependency and the matching
`shardingsphere-infra-executor` as a non-optional, literal exact runtime dependency. The generated
POM dependency management records the exact `infra-spi` and version-specific database-core anchor.
It must not use `[5.5.2]`, `[5.5.3]`, a range, or a property that can silently select another
version. The 5.5.2 POM must contain no `5.5.3` reference, and the 5.5.3 POM must contain no `5.5.2`
reference.

POM `dependencyManagement` is descriptive/default-selection metadata, not enforcement. A consumer
can override it, and it says nothing about an unlisted non-anchor component. Maven POMs also cannot
express Gradle capabilities, while an Enforcer execution declared by a dependency does not execute
in the consuming build. Therefore RouteContract publishes a consumer-owned Enforcer snippet and
tests it in a separate Maven fixture. Its `bannedDependencies` ranges apply to the entire
`org.apache.shardingsphere` group, not only the three runtime anchors. For the 5.5.2 adapter the
relevant rules are:

```xml
<dependencyConvergence>
  <includes>
    <include>org.apache.shardingsphere</include>
  </includes>
</dependencyConvergence>
<bannedDependencies>
  <searchTransitive>true</searchTransitive>
  <excludes>
    <exclude>org.apache.shardingsphere:*:(,5.5.2)</exclude>
    <exclude>org.apache.shardingsphere:*:(5.5.2,)</exclude>
    <exclude>io.github.ym0506.routecontract:routecontract-shardingsphere-5.5</exclude>
    <exclude>io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:(,0.2.0)</exclude>
  </excludes>
</bannedDependencies>
```

The 5.5.3 snippet substitutes `5.5.3` and excludes
`routecontract-shardingsphere-5.5.2`; it also contains the exact same-GA
`routecontract-shardingsphere-5.5:(,0.2.0)` ban shown above. Enforcer inspects the selected Maven
graph: if ordinary mediation selects only 0.2.0, it cannot report an unselected pre-0.2 declaration,
so the fixture separately asserts the selected artifact/version and absence of legacy bytes. A
selected version below 0.2.0 in an asserted 0.2 lane fails. Runtime guards remain mandatory because
a consumer may omit Enforcer or manually assemble a classpath.

The published snippet pins Maven Enforcer Plugin and Enforcer Rules 3.6.3. For that audited version,
`bannedDependencies` parses the third pattern field as the artifact version; the three-field form
is therefore intentional and verified against the rule implementation, not inferred from generic
Maven coordinate notation. Generated-fixture tests keep all three anchors correct, inject one
wrong-version non-anchor component, and assert that `bannedDependencies` itself reports the
version-range violation rather than relying only on `dependencyConvergence`.

### 4.3 Pre-0.2 all-in-one collision boundary

Every audited pre-0.2 release uses the all-in-one layout and predates both the core split and the
exclusive Gradle capability. Those artifacts contain the public API/collector classes and the
legacy hook provider in the same JAR. The new capability cannot retroactively change their
published metadata. Therefore any graph or manual classpath containing a pre-0.2 all-in-one JAR
together with `routecontract-core` or either 0.2.0 adapter is invalid, even when all ShardingSphere
artifacts are 5.5.3.

The 0.2.0 core additionally publishes a distinct ownership capability:

```text
io.github.ym0506.routecontract:routecontract-core-owner:1
```

The 5.5.2 adapter's legacy-GAV capability already conflicts with the legacy artifact's implicit
capability because those are different components providing the same slot. For the narrower case
where legacy is combined with the extracted core but no new adapter, supported Gradle consumers
apply a component-metadata rule that gives every selected
`routecontract-shardingsphere-5.5` version below `0.2.0` the synthetic core-owner capability. The
release gate enumerates every publicly distributed pre-0.2 coordinate and audits its JAR/tag layout
against the legacy provider/resource signature before relying on this range rule. The rules are
tested against each released stable legacy version + core and + the 5.5.2 adapter in both
declaration orders.

Legacy pre-0.2 releases and the new 5.5.3 adapter 0.2.0 are versions of the same GA. Normal
Gradle/Maven mediation may pass only when the selected component is exactly 0.2.0 and the resolved
files contain no pre-0.2 bytes. A consumer that strictly requires both versions must fail
resolution. Normal same-GA mediation is not evidence for a manually assembled classpath containing
both physical JARs; that case remains a runtime negative test.

The runtime constructor guard passively scans all visible hook service resources and legacy class
origins without instantiating another provider. Detection keys on the audited legacy provider FQCN,
service entry, public-class origin, and all-in-one layout signature rather than trusting a single
version string. It fails with `RC_LEGACY_ADAPTER_COLLISION` before ordinary SQL when resolver
protections were bypassed. Both physical-JAR orders are mandatory black-box cases because an
old-first classpath can otherwise shadow the new public API classes.

## 5. TCCL, classloader, shading, and JPMS boundary

The supported 0.2.0 topology is the classpath, with one application classloader that can see
exactly one core JAR, one versioned adapter JAR, and the matching exact ShardingSphere runtime
before the first ShardingSphere SQL execution. The adapter must be visible simultaneously to the
core-defining loader used for RouteContract adapter discovery and to the exact TCCL used for the
first ShardingSphere hook discovery. Both paths must resolve the same core bridge and adapter class
objects, not merely equal class names.

The following boundaries are normative:

- Core-owned adapter discovery uses the core-defining classloader, not ambient TCCL. Visibility
  only through the TCCL is insufficient.
- ShardingSphere-owned hook discovery remains subject to its first-use TCCL and static cache.
- Late attachment after first ShardingSphere discovery is unsupported and must fail visibly; the
  implementation must not claim that changing TCCL repairs an already-empty cache.
- A first discovery with the adapter visible may continue to use the cached provider after TCCL
  changes only when the cached provider class, core bridge, adapter class, and code-source checks
  still resolve to the originally verified identities. A second visible copy is a mismatch, not a
  fallback.
- Parent/child arrangements that duplicate core, isolate the hook from the core bridge, or create
  incompatible copies of the service interface are unsupported and fail with
  `RC_ADAPTER_CLASSLOADER_MISMATCH`.
- Fat JARs, shading, relocation, OSGi, hot reload, application-server plugin loaders, and custom
  layers remain unsupported until each topology has its own black-box evidence. Missing
  `Implementation-Version` fails closed.
- The two 0.2.0 adapters own disjoint packages, but every audited pre-0.2 all-in-one JAR collides
  with core public packages. Both cases are covered by resolver and runtime collision tests.
- JPMS module-path execution is unsupported in 0.2.0. The JARs carry stable automatic-module names
  for identity and future migration only. If `RouteContract`, its bridge, or either adapter is in a
  named module, preflight/provider construction fails with `RC_UNSUPPORTED_MODULE_PATH` before the
  action or ordinary SQL. `jar --describe-module` success is metadata evidence only.

## 6. Required black-box acceptance matrix

Every process-level row runs in a fresh JVM. Online and resolver-negative rows start with a fresh
empty dependency cache unless the row explicitly tests first-use caching. An offline row uses an
isolated cache primed exactly once by a successful online run from the same staged bytes, then
frozen and reused with network disabled; “offline from an empty cache” is not a valid requirement.
An action-sentinel row supplies an `AtomicBoolean` action that must remain `false` when preflight
rejects the graph. No test may satisfy a real-MySQL row with H2, a directly constructed hook, or a
mocked service collection.

| ID | Fixture and action | Required result |
| --- | --- | --- |
| A-01 | Exact 5.5.2, core + only 5.5.2 adapter; run ordinary ShardingSphere JDBC SQL before any capture, then capture the representative operation against digest-pinned MySQL 8.4.11. | Ordinary SQL succeeds; capture is complete and contains only the wrapped operation's reported attempts. `verified - MySQL`, exact 5.5.2. |
| A-02 | Exact 5.5.3, core + only existing-coordinate 5.5.3 adapter; same sequence. | Existing physical-attempt callback semantics, capture isolation/status, counts, and fingerprints remain at parity. Disclosed schema-2, runtime-identity, record-shape, package-ownership, code-source, and module-path migrations are not called “unchanged.” `verified - MySQL`, exact 5.5.3. |
| A-03 | For each version, execute SQL before capture, inside capture, and after capture, then open a second capture. | Pre/post SQL does not leak; the second snapshot contains only its own operation. |
| A-04 | 5.5.2 adapter + 5.5.3 runtime; call capture with action sentinel. | Preflight fails with `RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME`; sentinel remains false. |
| A-05 | 5.5.3 adapter + 5.5.2 runtime; call capture with action sentinel. | Same fail-closed result; sentinel remains false. |
| A-06 | Each wrong pair from A-04/A-05; execute ordinary ShardingSphere SQL before capture. | Provider discovery fails with a stable RouteContract marker; no `AbstractMethodError` appears as the exposed failure. |
| A-07 | Both adapters + exact 5.5.2 runtime, classpath adapter order 5.5.2→5.5.3 and 5.5.3→5.5.2. | Both orders fail identically with `RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS`; no SQL action runs. |
| A-08 | Both adapters + exact 5.5.3 runtime, both classpath orders. | Same deterministic dual-adapter failure. |
| A-09 | Mixed executor/SPI/database-anchor versions, including every 5.5.2/5.5.3 anchor combination and both artifact orders; separately keep all anchors correct and force one non-anchor `org.apache.shardingsphere` component to the other version. | Every resolver-controlled mixed graph fails before compilation through the whole-group rule. A bypassed/manual mismatch among the three audited anchors fails with `RC_MIXED_SHARDINGSPHERE_RUNTIME`; no order-dependent success. Arbitrary manual non-anchor mixes remain outside the bounded runtime guarantee. |
| A-10 | Core present, no RouteContract adapter; execute ordinary SQL, then call capture with sentinel. | Ordinary SQL remains usable; capture fails with `RC_ADAPTER_NOT_FOUND`; sentinel remains false. |
| A-11 | First ShardingSphere discovery under a TCCL that hides the adapter; then change to a TCCL that exposes it and call capture. | Capture fails with `RC_SHARDINGSPHERE_PROVIDER_NOT_ACTIVE`; late attachment is not reported as working. |
| A-12 | First discovery with the matching adapter visible to both required loaders; then change TCCL to one that hides the adapter while the core-defining loader continues to see the original adapter, and capture. | The already-cached matching provider remains valid and the representative operation succeeds, proving capture discovery did not switch to ambient TCCL. |
| A-13 | Put an adapter in a child loader with a duplicated/separately loaded core or bridge. | Fail with `RC_ADAPTER_CLASSLOADER_MISMATCH`, never an empty `COMPLETE` snapshot or raw linkage error. |
| A-14 | Gradle consumer, each correct adapter/runtime pair. | Dependency resolution, compile, representative operation, capture, and verify pass; resolved ShardingSphere anchors are the exact requested version. |
| A-15 | Gradle consumer with wrong anchor runtime, with one wrong non-anchor `org.apache.shardingsphere` component while anchors remain correct, then with both adapters in each declaration order. | Anchor and non-anchor mismatches fail whole-group exact-version resolution; dual adapters fail legacy-GAV/shared-capability resolution before tests. |
| A-16 | Maven consumer with its documented Enforcer rules, each correct pair. | `validate`, compile, representative operation, capture, and verify pass with dependency convergence. |
| A-17 | Maven consumer with wrong anchor runtime, with correct anchors plus one wrong-version non-anchor component, then both adapters in each declaration order. | `validate` fails through consumer Enforcer before tests; the non-anchor case names `bannedDependencies` as the failing rule. A separate no-Enforcer anchor-mismatch fixture proves the bounded runtime guard also fails closed. |
| A-18 | Run `jar --describe-module` for all three 0.2.0 JARs, then place core + one adapter on the module path and attempt ordinary SQL/capture from a named consumer. | Exact automatic-module names are present, but execution fails closed with `RC_UNSUPPORTED_MODULE_PATH`; documentation makes no JPMS support claim. |
| A-19 | Put both adapters on the module path in each path order. | The unsupported-module-path boundary fails deterministically; no accidental success, split-package support claim, or raw linkage error. |
| A-20 | JAR-content audit. | Adapter `.class` intersection is empty; no 0.2.0 JAR contains `module-info.class`; each adapter has exactly one hook descriptor line and one core-adapter descriptor line; core has no ShardingSphere references. |
| A-21 | Decode canonical schema-1 golden files from 0.1.2 and compare them with schema-2 5.5.3 candidates. | Golden schema-1 bytes still decode; comparison follows the compatibility table without rewriting approved files. |
| A-22 | Compare every successfully decoded supported/unsupported identity pair, including schema 1↔2 and mixed executor/SPI strings; separately feed missing/null/malformed identity, duplicate/unknown properties, invalid field types, and malformed JSON. | Decoded values produce exact deterministic `RCM001`, `RCM004`, or `RCM005` precedence and `INCOMPATIBLE`; malformed documents throw `ManifestFormatException` and emit no `RCM` result. A 5.5.2 candidate never silently matches a 5.5.3 baseline. |
| A-23 | Run the complete existing route-risk, safe-control, physical-failure, 20-repeat determinism, and 20-pair isolation corpus separately on exact 5.5.2 and exact 5.5.3 MySQL fixtures. | Each version has independent raw evidence. Test source may be shared; expected counts, fingerprints, aliases, and approved baselines are version-specific and human-reviewed. |
| A-24 | Maven Java 17, Gradle Groovy Java 17, Gradle Kotlin Java 17, and the existing bounded Java 21 lane; fresh-empty-cache online, isolated-cache offline after one successful staged-byte online prime, corrupted checksum, wrong artifact origin, and an exact-anchor/non-anchor-version-mismatch case in every build tool. | Both version lanes preserve whole-group ShardingSphere exactness, locks, checksums, fail-closed artifact identity, and documented Java boundaries. The offline run disables network and reuses only the frozen primed cache. Java 21 evidence does not broaden another lane by inference. |
| A-25 | Strict root build, dependency verification, direct and aggregate SBOMs, license inventory, pinned OSV scan, sources/Javadoc/signature/checksum validation. | No verification bypass; every new 5.5.2 and core artifact is reviewed and represented in release evidence. |
| A-26 | Compare the documented public API of 0.1.2 `routecontract-shardingsphere-5.5` with 0.2.0 through that same GAV; exclude `.internal`/provider FQCNs. Run an old-bytecode consumer, source recompilation, reflection over record components, equality/`toString`, code-source checks, and the documented classpath/module migration examples separately. | Old documented method and legacy-constructor descriptors link through transitive core on the classpath. Source/reflection/record-shape/code-source changes are either compatible or called out explicitly; module-path migration is rejected with the documented 0.2.0 boundary rather than claimed compatible. |
| A-27 | Gradle and Maven resolver fixtures combine every released stable pre-0.2 all-in-one version with core alone and with the different-GAV 5.5.2 adapter in both declaration orders. Separately request each same-GA legacy version and 0.2.0 with ordinary mediation, then with strict dual-version requirements; audit any RC-tag/release layout against the same registry. | Different-component combinations fail through the legacy-GAV/core-owner capability or consumer Enforcer. Ordinary same-GA mediation passes only when exactly 0.2.0 is selected and no pre-0.2 file is present; strict incompatible requirements fail resolution. |
| A-28 | For each released stable pre-0.2 all-in-one version, manually assemble legacy + core-0.2.0 + adapter-0.2.0 classpaths with the legacy JAR first and last, for both new adapters; execute ordinary SQL before capture and a capture sentinel. | Every version and order fails with `RC_LEGACY_ADAPTER_COLLISION` before SQL/action; no old-class shadowing, double capture, `AbstractMethodError`, or silent success. A tag-only RC layout may be covered by a byte/layout-identity proof plus oldest/latest executable cases; any distributed RC artifact is executed directly. |

Rows A-01 through A-28 are release gates, not an aspirational sample. Failures may not be waived by a
narrower unit test or by relabeling the lane experimental in final release metadata.

## 7. Migration plan

Implementation follows the repository's specification-first workflow.

1. **Freeze evidence.** Save 0.1.2 public API descriptors, schema-1 golden files, JAR/service
   contents, automatic-module metadata, current 5.5.3 MySQL corpus results, and exact dependency
   metadata. Classify documented public API separately from `.internal` provider classes.
2. **Add failing contracts first.** Add schema identity compatibility tests, wrong-runtime ordinary
   SQL tests, action-sentinel tests, dual/legacy-adapter classpath-order tests, whole-group
   non-anchor mismatch tests, TCCL/loader tests, module-path rejection tests, and generated-metadata
   assertions before moving production code.
3. **Extract core without semantic change.** Move existing public API, collector, and manifest code
   to `routecontract-core`; retain public FQCNs and old constructor descriptors. Make the existing
   GAV a thin exact-5.5.3 adapter with an `api` edge to core.
4. **Restore bounded 5.5.3 semantic parity.** Pass the entire existing
   unit/MySQL/Maven/Gradle/release-evidence suite for physical-attempt callback meaning, capture
   isolation/status, counts, and fingerprints before adding a positive 5.5.2 claim. Schema-2,
   runtime-identity, record-shape, code-source, package ownership, and module-path changes are
   intentional migrations and are verified/disclosed separately rather than called unchanged.
5. **Add the isolated 5.5.2 adapter.** Add only the version-specific hook, runtime adapter,
   descriptors, literal dependencies/constraints, locks, and reviewed verification metadata.
6. **Run the complete matrix.** Produce separate 5.5.2 and 5.5.3 raw evidence, including MySQL and
   external-build-tool fixtures. Baselines remain human-approved per exact runtime.
7. **Update distribution surfaces.** Update compatibility tables, installer, direct-release
   examples, Central metadata, SBOMs, release-evidence workflow, checksums, and first-integration
   guide. Publish the Gradle legacy-capability/group-version rules and Maven consumer-owned Enforcer
   rules. Do not call the old artifact generic 5.5.x support or claim JPMS support.
8. **Stage one coordinated 0.2.0 set.** Stage core and both adapters together. Verify generated POM
   and Gradle metadata from the staged repository and repeat anonymous fresh-cache consumers before
   release.

No existing approved baseline is automatically migrated, renamed, copied between runtime-version
directories, or approved by RouteContract. A 5.5.2 integration requires its external maintainer to
approve the exact 5.5.2 baseline.

## 8. Publication and rollback gates

Publication is all-or-nothing for the 0.2.0 three-artifact graph. It is blocked unless:

- every acceptance row passes on the exact staged bytes;
- generated POMs and Gradle module metadata encode the graph in this ADR;
- consumer fixtures prove whole-group exact ShardingSphere selection and every audited pre-0.2
  all-in-one collision is rejected rather than relying only on three anchor constraints;
- sources, Javadoc, signatures, checksums, SBOMs, licenses, and vulnerability evidence cover all
  three artifacts;
- old bytecode using the documented public classpath API remains linkable through the
  existing-coordinate 5.5.3 adapter; source/reflection/code-source changes and the unsupported
  module-path migration are disclosed separately;
- anonymous fresh-cache Maven and Gradle consumers reproduce both exact version lanes; and
- documentation labels each exact version honestly and preserves all hook/approval claim
  boundaries.

Rollback rules are intentionally asymmetric around immutable publication:

- Before publication, discard the staging repository and revert the local branch if any gate
  fails. Continue to recommend immutable 0.1.2 for exact 5.5.3 only.
- A failing 5.5.2 gate does not justify publishing a partial 0.2.0 graph or weakening the test. The
  new adapter remains `planned`/`experimental`.
- Never move, delete, replace, or reinterpret the immutable v0.1.2 tag, Release, assets, or GAV.
- After an immutable 0.2.0 publication, do not overwrite artifacts. Publish a clear advisory and a
  corrected later version only after the same gates pass; keep schema-1 and already published
  schema-2 manifests readable.
- If a runtime defect can affect ordinary SQL, documentation must tell consumers to remove the
  affected adapter version immediately rather than merely disable captures.

## 9. User-growth consequence and non-claim

Read-only candidate audits found otherwise plausible Java/ShardingSphere repositories pinned to
5.5.2. The exact-5.5.3-only adapter cannot be safely offered to them because of the verified ABI
failure. A released, independently verified 5.5.2 adapter would therefore enlarge the technically
addressable consent-only pilot pool while preserving the already supported 5.5.3 lane.

That is a product-distribution opportunity, not adoption evidence. An artifact build, download,
fork, star, local fixture, draft PR, maintainer comment, or green RouteContract-owned CI run does
not create a user. A qualifying external user still requires all of the following in the external
repository:

1. the matching RouteContract dependency;
2. a representative application operation;
3. an exact baseline approved by an authorized external human;
4. a candidate check; and
5. successful upstream public CI evidence.

Until that evidence exists, the actual external-user count remains unchanged. This ADR must not be
cited as support, adoption, endorsement, or permission to contact repositories in parallel with an
active consent-only pilot.

## 10. Rejected alternatives

### Copy the entire 5.5.3 module and change imports

Rejected. It duplicates public classes and provider identities, creates classpath-order behavior
and JPMS split packages, drifts security fixes, and already failed strict dependency verification.

### One hook provider class for both versions

Rejected. The `start(...)` JVM descriptors are different. Overloading both methods would still
couple one provider artifact to both incompatible API graphs and would allow the wrong service
provider to activate during ordinary SQL.

### Rely only on capture preflight

Rejected. ShardingSphere activates the hook for ordinary SQL before RouteContract capture
preflight, and the observed failure is `AbstractMethodError`.

### Rely only on Gradle capabilities or Maven metadata

Rejected. Capabilities do not protect Maven or manual classpaths, and Maven cannot activate an
Enforcer rule supplied by a dependency. Resolver metadata and runtime guards are complementary.

### Treat every schema-1 baseline as version-agnostic

Rejected. Schema 1 was produced under an exact-5.5.3-only preflight. Letting it match 5.5.2 would
hide the runtime contract change from the human approval boundary.

### Encode runtime identity in a sidecar or filename

Rejected. A sidecar can be missing, stale, or replaced independently of the atomically stored
manifest. A filename convention also conflicts with the rule that `operationId` is opaque and is
never interpreted as a path.
