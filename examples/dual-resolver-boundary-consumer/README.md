# Dual-resolver and opposite-runtime boundary fixtures

Status: **planned; preparation only**. These fixtures implement the finite ten-case
plan in [`docs/dual-resolver-boundary-acceptance.md`](../../docs/dual-resolver-boundary-acceptance.md).
They require the newly reviewed 0.2.0 candidate containing the A-09 guard correction.
Preparing or compiling synthetic fixture inputs is not evidence that a staged
resolver or runtime case passed.

There are four Gradle dual-adapter cases, four Maven dual-adapter cases and two
Maven-resolved external Java guard cases. Java is exactly 17. These minimal
resolver/runtime boundaries perform no SQL, MySQL, Docker or test execution.

## Template contract

The runner copies and substitutes these exact files into a new case directory.
It must validate every value against the finite plan and reject unresolved or
unknown `@@TOKEN@@` placeholders. Runtime strings and module identifiers come
from the plan, never arbitrary user text. No receipt hashes or local paths are
embedded in the committed templates.

| Source | Destination | Tokens |
| --- | --- | --- |
| `gradle/settings.gradle.template` | `settings.gradle` | none |
| `gradle/build.gradle.template` | `build.gradle` | `RUNTIME`, `FIRST_ADAPTER`, `SECOND_ADAPTER`, `DATABASE_ANCHOR` |
| `maven/dual-pom.xml.template` | `pom.xml` | `RUNTIME`, `SELECTED_ADAPTER`, `OPPOSITE_ADAPTER`, `FIRST_ADAPTER`, `SECOND_ADAPTER`, `DATABASE_ANCHOR` |
| `maven/guard-pom.xml.template` | `pom.xml` | `RUNTIME`, `OPPOSITE_RUNTIME`, `SELECTED_ADAPTER`, `DATABASE_ANCHOR` |
| `guard/src/main/java/.../OppositeRuntimeGuardProbe.java` | same path below `src/main/java` | none |

`RUNTIME` is the selected adapter's exact ShardingSphere version. `OPPOSITE_RUNTIME`
is the other version. `FIRST_ADAPTER` and `SECOND_ADAPTER` are the two ordinary
adapter module names in the measured declaration order. Their versions remain
literal `0.2.0`; neither tool excludes transitive dependencies or replaces the
published capabilities. The core must remain transitive from the adapters.

| Runtime | Adapter module | Database anchor module |
| --- | --- | --- |
| 5.5.2 | `routecontract-shardingsphere-5.5.2` | `shardingsphere-infra-database-core` |
| 5.5.3 | `routecontract-shardingsphere-5.5` | `shardingsphere-database-connector-core` |

`DATABASE_ANCHOR` follows `RUNTIME` for both dual-adapter templates, and
`OPPOSITE_RUNTIME` for the guard template. Each template directly declares the
executor, SPI and database anchors. Actual resolution must establish the complete
coherent selected ShardingSphere set; the templates do not assume Maven nearest
selection succeeds and do not claim the larger JDBC/MySQL fixture's component counts.

## Gradle native conflict

Use pinned Gradle 8.14.4 with actual Java 17, trusted IPv4 settings, an independent
private user home, strict receipt-backed verification metadata and a fresh
dependency cache. Supply the controlled URL through
`-ProutecontractRepositoryUrl=http://127.0.0.1:<port>/`. The build rejects all other
URL forms; only the first-party group can use that repository. The runner owns the
controlled HTTP server and its finalized request log.

The only fixture task is `resolveDualAdapters`. It first writes
`negative-graph.json` from `ResolutionResult` and then accesses the same
configuration's files without catching the native failure. No Java plugin,
compilation task, test task, dependency substitution, explicit capability request,
capability selection rule or fabricated rejection marker is installed.

The graph has this schema:

```text
schemaVersion: 1
tool: "gradle"
configuration: "dualAdapterRuntime"
requestedRuntime: exact runtime
routeContractVersion: "0.2.0"
declaredAdapters: [first GAV, second GAV]
declaredRuntimeAnchors: [executor GAV, SPI GAV, database GAV]
selectedComponents: [{coordinate, selectionReasons: [{cause, description}]}]
unresolved: [{requested, attempted, from, failureMessages: [{exceptionType, message}]}]
```

Module coordinates and selectors are Gradle's actual display names. Selected
components are sorted by coordinate; unresolved records by requested selector,
attempted selector and origin. Failure messages include each actual nested cause,
multi-cause and suppressed exception once by object identity. The runner must bind
the native error and both actual adapter selectors to an exact capability published
by both reviewed modules. A native legacy-GAV capability conflict retains that
identity; it is not described as a shared hook-slot conflict. A different dependency
failure does not pass.

## Maven native policy and runtime controls

Use Maven 3.9.14 with recorded actual Java 17, trusted IPv4 settings, private home,
fresh local repository, strict checksums and explicit private global/user settings
that route every first-party request through the controlled repository.

For a dual case, run the following explicit plugin goals before a separate
`validate` invocation against the same generated POM and cache:

```text
org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
  -DoutputType=json -DoutputFile=<absolute graph path>
org.apache.maven.plugins:maven-dependency-plugin:3.11.0:resolve
```

These goals do not enter the lifecycle. The graph must actually select both
declared adapters, transitive core and a coherent selected ShardingSphere set;
the resolver must retrieve both receipt-pinned adapter JARs. `validate` must fail
specifically through Enforcer 3.6.3 `BannedDependencies` and name the opposite
adapter. Other failures cannot substitute for this native policy cause.

For a guard case, the separate POM contains no Enforcer plugin, execution, profile
or parent. Resolve and record its graph, run `compile` with compiler plugin 3.14.1
and `release=17`, and produce the runtime classpath using
`org.apache.maven.plugins:maven-dependency-plugin:3.11.0:build-classpath` with
`-Dmdep.includeScope=runtime -Dmdep.outputFile=<absolute classpath path>`.
The runner must check the actual complete graph, source import of the current API,
compiled class major version 61 and exact runtime JAR bytes before launch.

Launch the selected `JAVA_HOME/bin/java` as a new direct child of the Python runner,
with `-Djava.net.preferIPv4Stack=true`, `-Duser.home=<canonical private home>` and
the recorded absolute `target/classes` plus resolved runtime JAR classpath. Invoke
`io.github.ym0506.routecontract.boundary.OppositeRuntimeGuardProbe` with exactly
`--expectations <absolute Properties file>`. Do not use Maven `exec:java`, invoke
the adapter/hook constructors, warm service loaders or call `verifyRuntime` first.

The runner-written Java Properties file contains exactly these keys:

| Key | Required value |
| --- | --- |
| `adapterRuntime` | selected adapter version, 5.5.2 or 5.5.3 |
| `observedRuntime` | coherent opposite ShardingSphere version |
| `coreSha256`, `adapterSha256` | lowercase SHA-256 from the separately reviewed receipt |
| `coreByteCount`, `adapterByteCount` | corresponding receipt JAR byte counts |
| `expectedUserHome` | existing canonical private home path |
| `expectedParentPid` | PID of the process directly launching this external Java process |
| `expectedShardingSphereCoordinates` | unique lexically sorted comma-separated `group:artifact:version` set from the actual audited Maven graph |

Serialize the file using Java Properties escaping, including backslashes and
Unicode escapes where needed; `Properties.load(InputStream)` is the reader.
The probe independently inspects every actual classpath JAR's ShardingSphere
`pom.properties`, file hash and module uniqueness, then verifies the three loaded
opposite-runtime anchor classes, manifests and distinct origins. JAR manifest
`Class-Path` entries cannot add files outside the recorded runtime classpath. Its core and
adapter origins must match the receipt before and after the measured call.

Only one measured current-API `capture` call is made. All environmental and loaded
identity prechecks are outside its exception handler. The only accepted failure is
an exact `IllegalStateException`, with no cause or suppressed exceptions, whose
entire message is
`RC_UNSUPPORTED_SHARDINGSPHERE_RUNTIME: exact adapter <selected> observed <opposite>`.
The call cannot return and the action sentinel must remain false. Missing anchors,
unavailable versions, mixed versions, linkage errors or other diagnostics fail.

After successful verification, stdout contains exactly one fixture result line
prefixed `BOUNDARY_RUNTIME_RESULT ` followed by JSON. Its fields are:

```text
schemaVersion, adapterRuntime, observedRuntime, currentApi,
javaFeature, javaVersion, userHome, preferIPv4Stack, pid, parentPid,
core, adapter, anchors, shardingSphereCoordinates, shardingSphereJars,
actionInvoked, diagnosticCode, diagnosticMessage, exceptionType
```

`core`, `adapter` and each `shardingSphereJars` entry contain `coordinate`, `path`,
`sha256`, `byteCount`. Each anchor adds `role`, `className`, `implementationVersion`.
Paths and process IDs are private raw evidence; any public summary must remove
them. The native command, exit, stdout/stderr and input fingerprints remain the
runner's evidence responsibility. No template-generated marker alone completes
the ten-case plan.
