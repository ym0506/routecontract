# Empirical comparison: datasource-proxy 1.11.0

Last checked: 2026-08-11

This comparison asks one narrow question: on the same synchronous
ShardingSphere-JDBC 5.5.3/MySQL operation whose application result stays at one
row while its `SQLExecutionHook`-reported physical JDBC execution attempts change from one to two, what
does a strong generic JDBC interception library provide directly, and what
application code is still required to create an operation contract?

The comparison is deliberately favorable to datasource-proxy. It does not
argue that the generic library is incapable. The fixture implements the
missing pieces in test code to demonstrate that an equivalent narrow workflow
is buildable.

## Why datasource-proxy

datasource-proxy is a stronger DIY comparison than a log parser:

- version `1.11.0` is the current Maven Central release and was published on
  2025-07-14 ([Maven Central artifact](https://central.sonatype.com/artifact/net.ttddyy/datasource-proxy/1.11.0),
  [signed upstream release](https://github.com/jdbc-observations/datasource-proxy/releases/tag/datasource-proxy-1.11.0));
- it wraps any `DataSource` and exposes a custom `QueryExecutionListener`;
- `ExecutionInfo` exposes a configured proxy name, callback success/failure and
  connection information;
- `QueryInfo` exposes SQL and parameter-set operations, so an application can
  build its own minimization and baseline layer;
- the core artifact has no required transitive libraries for this use
  ([official installation guide](https://jdbc-observations.github.io/datasource-proxy/docs/current/user-guide/#_dependency)).

Those capabilities make it a credible alternative, not a straw man.

## Reproducible fixture

The executable evidence is
[`DataSourceProxyComparisonMySqlTest`](../examples/mysql/src/test/java/io/github/ym0506/routecontract/example/DataSourceProxyComparisonMySqlTest.java).
It uses the same pinned MySQL image and the same equality-to-single-value-range
mutation as the RouteContract regression corpus.

Run only this comparison with:

```bash
./gradlew --no-daemon --no-build-cache \
  :mysql-example:test \
  --tests '*DataSourceProxyComparisonMySqlTest'
```

The test prints one non-sensitive summary marker after all assertions pass:

```text
ROUTECONTRACT_DATASOURCE_PROXY_COMPARISON businessRows=1->1 outerLogicalCallbacks=1->1 innerPhysicalCallbacks=1->2 routeContractAttempts=1->2 diyWiring=[physical-wrappers,ttl-correlation,minimization,canonicalization,diff,assertion]
```

This line is a summary, not standalone proof. The JUnit XML result and the
source assertions are the evidence.

## Placement changes what is observed

datasource-proxy observes calls made through the exact JDBC object it wraps.
Its statement proxy invokes listeners around that wrapped statement's
`execute*` call ([tagged `StatementProxyLogic`](https://github.com/jdbc-observations/datasource-proxy/blob/datasource-proxy-1.11.0/src/main/java/net/ttddyy/dsproxy/proxy/StatementProxyLogic.java)).
Therefore the fixture tests both valid placements:

| Placement | Equality | Same-value range | Meaning |
|---|---:|---:|---|
| One wrapper outside `ShardingSphereDataSource` | 1 callback | 1 callback | The application's one logical JDBC call |
| One wrapper around each physical `DataSource` supplied to ShardingSphere | 1 callback | 2 callbacks | The backing JDBC calls made through those wrappers |
| RouteContract `SQLExecutionHook` capture | 1 observed attempt | 2 observed attempts | ShardingSphere 5.5.3 hook-reported physical JDBC attempts |

The external physical-data-source map is a supported ShardingSphere factory
input ([tagged 5.5.3 factory source](https://github.com/apache/shardingsphere/blob/5.5.3/jdbc/src/main/java/org/apache/shardingsphere/driver/api/yaml/YamlShardingSphereDataSourceFactory.java#L76-L105)).
This lets the test give datasource-proxy the inner placement needed to observe
fan-out. It also demonstrates the integration cost: every physical data
source must be created or intercepted before ShardingSphere is constructed.

ShardingSphere 5.5.3 reflects connection metadata from the supplied outer
`DataSource` object and does not unwrap a generic proxy. The fixture therefore
adds a public, test-only delegating adapter that exposes only URL, username and
password bean getters while all connections still pass through the real
datasource-proxy object. This is fixture compatibility wiring, not a
RouteContract advantage hidden from the comparison
([tagged metadata creator](https://github.com/apache/shardingsphere/blob/5.5.3/infra/data-source-pool/core/src/main/java/org/apache/shardingsphere/infra/datasource/pool/props/creator/DataSourcePoolPropertiesCreator.java#L63-L65),
[tagged reflection logic](https://github.com/apache/shardingsphere/blob/5.5.3/infra/data-source-pool/core/src/main/java/org/apache/shardingsphere/infra/datasource/pool/creator/DataSourcePoolReflection.java#L66-L104)).

The `ExecutionInfo.getDataSourceName()` values in that setup are names assigned
by `ProxyDataSourceBuilder.name(...)`. They are not storage-unit names
discovered from ShardingSphere. The fixture deliberately assigns matching
`ds_0` and `ds_1` labels so the comparison is useful and fair.

## What datasource-proxy provides directly

With inner wrappers and a listener, the fixture receives:

- one or two physical-layer callbacks in this non-batch scenario;
- the application-configured proxy label;
- the rewritten SQL string;
- the parameter setter operations and bound values;
- a callback success flag.

The official listener contract describes `ExecutionInfo` as execution context
and `QueryInfo` as the actual query and parameters
([user guide](https://jdbc-observations.github.io/datasource-proxy/docs/current/user-guide/#_queryexecutionlistener),
[`ExecutionInfo` API](https://jdbc-observations.github.io/datasource-proxy/docs/current/api/net/ttddyy/dsproxy/ExecutionInfo.html),
[`QueryInfo` API](https://jdbc-observations.github.io/datasource-proxy/docs/current/api/net/ttddyy/dsproxy/QueryInfo.html)).
The test asserts that the raw inner observation contains a rewritten physical
table name and the `PAID` bind value. It never prints that raw observation.

This is not a claim that datasource-proxy forces unsafe logging. A production
custom listener can immediately reduce the values. This comparison instead
keeps them only in memory for the duration of the test so it can make explicit
raw-capability assertions and then derive minimized manifests; it never prints
or persists the raw observations.
The precise difference is that the listener surface supplies the raw material
and the application owns the retention and persistence policy.

## Additional wiring implemented for the fair comparison

The test-only `DiyOperationCollector`, `DiyManifest` and
`DiyManifestVerifier` show the extra pieces needed to turn the interception
primitive into this narrow contract workflow:

1. wrap and name every physical data source;
2. add a caller operation token;
3. propagate that token through ShardingSphere worker submissions with a
   `TransmittableThreadLocal`;
4. associate active captures through a concurrent registry;
5. derive SHA-256 fingerprints before any baseline persistence;
6. retain parameter count/type information while discarding values;
7. map configured proxy labels to stable aliases;
8. sort attempts and encode deterministic baseline bytes;
9. calculate budget and structural-drift findings;
10. turn those findings into a failing CI assertion.

The DIY verifier correctly fails the unchanged-business-result `1 -> 2`
candidate with attempt-budget, data-source-budget and structural-drift codes.
The RouteContract path in the same test fails with its packaged `RCM201` and
`RCM202` semantics.

The DIY implementation is intentionally bounded and honest. It supports only
the synchronous, normal-return, non-batch PreparedStatement scenario used by
this experiment. It does not provide RouteContract's exact-runtime/SPI
preflight, incomplete-capture diagnostics, strict manifest decoder, atomic
candidate storage, format compatibility checks, concurrent regression corpus
or public API. It must not be copied into production as a general contract
library.

Its parameter-type sequence follows the JDBC setter-call sequence. That is
stable for this fixture's single-pass `setObject(1..N)` binding, but it is not a
general canonicalization rule for repeated or out-of-order setter calls.

## Operation-correlation boundary

datasource-proxy's built-in count storage is thread-local or global
([`ThreadQueryCountHolder`](https://github.com/jdbc-observations/datasource-proxy/blob/datasource-proxy-1.11.0/src/main/java/net/ttddyy/dsproxy/listener/ThreadQueryCountHolder.java),
[`SingleQueryCountHolder`](https://github.com/jdbc-observations/datasource-proxy/blob/datasource-proxy-1.11.0/src/main/java/net/ttddyy/dsproxy/listener/SingleQueryCountHolder.java)).
For inner wrappers, ShardingSphere may invoke listeners on worker threads. A
caller-thread bucket can therefore miss events, while a single global bucket
can mix concurrent operations. The fixture's custom TTL token and registry are
the additional correlation layer implemented for this experiment. The present
comparison executes its two captures sequentially; it does not itself prove
concurrent-operation isolation. RouteContract's separate concurrency corpus is
the relevant evidence for RouteContract's bounded concurrency claim. That corpus
holds caller capture scopes open concurrently; it does not force or measure
temporal overlap between the physical hook callbacks themselves.

This finding does not mean datasource-proxy cannot correlate operations. It
means correlation is application-supplied rather than a documented built-in
multi-execution operation abstraction.

## Defensible conclusion

The empirical result supports this positioning:

> datasource-proxy is a capable JDBC interception primitive. With physical
> data-source wrapping and application-owned correlation, minimization,
> canonicalization, diff and assertion code, it can implement a comparable
> narrow check. RouteContract packages that ShardingSphere-JDBC 5.5.3-specific
> workflow without requiring every physical data source to be wrapped.

It does **not** support any of these claims:

- datasource-proxy cannot observe physical executions;
- datasource-proxy is unsafe;
- RouteContract invented JDBC query counting;
- either callback stream proves transaction commit or business success;
- the comparison covers batch execution, arbitrary async work, SQL Federation
  or another ShardingSphere version.

datasource-proxy is MIT-licensed
([tagged license](https://github.com/jdbc-observations/datasource-proxy/blob/datasource-proxy-1.11.0/license.txt)).
Because it is a comparison-test dependency, it must also appear in the final
dependency inventory, SBOM and release license review.
