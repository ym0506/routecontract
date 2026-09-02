# Local Gradle consumer for the RouteContract 0.2 split

This nested build is a local development fixture for the unpublished `0.2.0` split. It consumes
`routecontract-core` plus exactly one exact-version adapter through composite substitution, so it
does not publish snapshots to Maven Local, create a Central staging tree, or alter the immutable
`v0.1.2` example.

Run both configured exact-version resolution lanes with the repository's wrapper and JDK 17:

```bash
./gradlew -p examples/gradle-split-artifact-consumer \
  -ProutecontractAdapterVersion=5.5.2 clean check

./gradlew -p examples/gradle-split-artifact-consumer \
  -ProutecontractAdapterVersion=5.5.3 clean check
```

Each run proves four bounded properties before reporting success:

1. the runtime graph contains `routecontract-core:0.2.0` and exactly one selected
   `routecontract-shardingsphere-*` adapter at `0.2.0`;
2. explicit requests and selected components in group `org.apache.shardingsphere` are accepted
   only at the adapter's exact `5.5.2` or `5.5.3` version;
3. a wrong-version non-anchor request for `shardingsphere-infra-common` fails resolution before
   compilation; and
4. both adapter declaration orders fail resolution because the two adapters provide the same
   `io.github.ym0506.routecontract:routecontract-shardingsphere-hook-adapter:1` capability.

The positive lane also compiles and runs an empty capture to exercise core-to-adapter discovery and
the exact runtime preflight. It is a compatibility probe, not a representative database operation,
MySQL evidence, an approved baseline, external adoption, or a release artifact verification.

The fixture intentionally has no lockfile or dependency-verification metadata while the 0.2
artifacts are local unpublished projects. A later repository-backed/publication consumer must use
target-owned strict locks and reviewed verification metadata rather than copying those files from
the immutable `v0.1.2` fixture.
