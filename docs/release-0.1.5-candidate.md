# 0.1.5 ShardingSphere 5.4.1 to 5.5.2 support

Status: **candidate, not published.** No tag, signature, upload or publication exists yet.

0.1.5 publishes two artifacts with the same group and version:

| Artifact | ShardingSphere-JDBC | Distribution |
| --- | --- | --- |
| `io.github.ym0506.routecontract:routecontract-shardingsphere-5.5` | exactly 5.5.3 | Maven Central and the GitHub Release, as for 0.1.4 |
| `io.github.ym0506.routecontract:routecontract-shardingsphere-5.4.1-5.5.2` | exactly 5.4.1, 5.5.0, 5.5.1 or 5.5.2 | Maven Central only |

## Developer problem and scope

Public projects that shard with ShardingSphere-JDBC today use 5.4.1 to 5.5.2, for example
TencentBlueKing/bk-job (5.4.1), TencentBlueKing/bk-ci (5.5.0) and 201206030/novel (5.5.1).
RouteContract 0.1.4 links only to 5.5.3. ShardingSphere 5.5.3 moved the `ConnectionProperties`
type used by `SQLExecutionHook`, so one JAR cannot implement the hook for both API generations.

The new artifact is the same library built from the shared sources with its own hook,
`ShardingSphere541To552Preflight` and `RuntimePreflight`. It compiles against only the three
ShardingSphere 5.5.2 modules its sources use. The shared operation-correlation and
failure-boundary MySQL tests run once on each of 5.4.1, 5.5.0, 5.5.1 and 5.5.2.

Changes to the 5.5 artifact since public 0.1.4:

- its version error now names the 5.4.1-5.5.2 artifact;
- shared capture code calls a per-artifact `RuntimePreflight` that delegates to the unchanged
  `ShardingSphere553Preflight`;
- three Javadoc sentences in shared classes no longer name 5.5.3; and
- packaging, staging and signing rules moved to `gradle/routecontract-library.gradle` without
  changing the generated POM.

The support boundary otherwise stays the same: Java 17 or 21, synchronous non-batch
`PreparedStatement` operations, no Proxy, batch, application async, topology discovery or
production-performance claim. Library bytecode remains Java 17.

## Supply-chain boundary for the second artifact

Both artifacts publish the same runtime graph: `com.alibaba:transmittable-thread-local:2.14.2`
and `tools.jackson.core:jackson-core:3.1.6`. The tag workflow requires the two POMs, Gradle Module
Metadata files and locked `runtimeClasspath` sets to be identical
(`scripts/verify-shared-runtime-graph.py`). The sanitized supply-chain evidence, SBOM policy and
OSV scan are produced for the 5.5 artifact and cover the second artifact only through that
identity. The second artifact's compile-only ShardingSphere 5.5.2 API JARs are not published.

## Release acceptance checklist

1. Review the full source delta from the published `v0.1.4` tag, with clean source and consistent
   0.1.5 coordinates for both artifacts.
2. Run the current Java/MySQL, Python/packaging and official SBOM checks, including the four
   5.4.1-5.5.2 runtime tasks. Use the release JDK Temurin 17.0.20.1+1 for release artifacts.
3. Refresh the pinned OSV database and run the existing policy without new exceptions. The MySQL
   license review in `security/supply-chain-policy.json` expires on 2026-12-05; a tag-time run
   after that date fails until the review is renewed.
4. Bind an annotated `v0.1.5` tag, the final public `main` commit and a new release-evidence run.
   Retain the twelve 5.5 GitHub assets, the 5.5 Central candidate and the separate
   `routecontract-central-candidate-routecontract-shardingsphere-5.4.1-5.5.2-<sha>` candidate,
   with observed names, sizes and SHA-256 values.
5. Review both five-payload sets, sign each from its own staging repository with the reviewed
   primary key, and verify one deterministic 30-file bundle per artifact.
6. Upload each bundle as its own `USER_MANAGED` deployment, verify each submitted candidate before
   publication, then publish each exactly once.
7. After publication, perform anonymous byte-for-byte readback for both artifacts and fresh
   Maven/Gradle MySQL consumption for each before switching installation instructions.

Exact procedures remain in [RELEASING.md](RELEASING.md). Maintainer-run validation and
publication do not establish independent external adoption or production results.
