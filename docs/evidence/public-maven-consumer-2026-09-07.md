# Public Maven consumer preparation — 2026-09-07

Evidence label: **verified - unit** for verifier preparation and failure behavior.
Successful anonymous public consumption is **unverified**. No release guard was removed and no
artifact was published by this work.

The public wrapper accepts the strict reviewed nine-payload receipt and supports stable `0.2.x`
patch versions. It uses the existing Maven POM and unchanged MySQL Java/resources through optional
version/origin arguments in the staged harness. Staged defaults remain unchanged. Each public
runtime gets a fresh external consumer/cache, explicit user and global settings, and a single
`mirrorOf=*` mirror at `https://repo.maven.apache.org/maven2`.

The public commands set `maven.resolver.transport=native` and
`aether.connector.http.followRedirects=false`. Maven 3.9.14's native preference selects its HTTP
transport for the verified probe; this does not assert that the Wagon implementation is removed.
The shared runner also clears `MAVEN_DEBUG_OPTS`, pins `MAVEN_BASEDIR` to its controlled working
directory, and requires exact non-comment origin records without extra repository origins.

## Verification performed

The final focused suite passed **36 tests with no failures or skips** on both Python 3.12.14 and
3.13.0: 8 shared receipt tests, 21 retained staged/mirror tests, and 7 new public tests.

```sh
PYTHONPATH=scripts/tests python3 -m unittest test_public_split_artifacts test_staged_maven_repository test_verify_staged_maven_artifact_consumer test_verify_public_maven_artifact_consumer -v
```

For Python 3.12.14 the executable was
`/Users/ym56/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`.
The tests cover strict receipts, fixed Central command/settings construction, fresh caches,
stable `0.2.1` POM/Enforcer/graph/negative-request binding, unchanged Java resources, mixed-version
rejection, exact origin/hash checks, retained failure evidence, and launcher isolation.
The positive orchestration test uses mocked lanes and is not live-public success evidence.

A real local transport-negative check used Maven 3.9.14 / Java 17.0.15, a fresh cache and a
loopback-only Maven parent-POM endpoint returning HTTP 302. With the final transport flags, Maven
exited 1 explicitly reporting 302, the source endpoint recorded one request, and the redirect
target recorded zero. No external network, public coordinates, plugins, source build, or MySQL
were used. Raw command, POM/settings, logs, request counts, and inspected primary transport
bytecode are retained at:

`/private/tmp/routecontract-public-maven-transport-negative-20260907/`

## Actual unpublished-version observation

One real public command used the previously reviewed `0.2.0` receipt:

```sh
python3 scripts/verify-public-maven-artifact-consumer.py --receipt /private/tmp/routecontract-staged-consumer-008e125/evidence-final/staged-receipt.json --evidence-directory /private/tmp/routecontract-public-maven-unpublished-20260907 --java-home /opt/homebrew/Cellar/openjdk@17/17.0.15/libexec/openjdk.jdk/Contents/Home
```

Maven 3.9.14 failed to resolve
`io.github.ym0506.routecontract:routecontract-shardingsphere-5.5.2:0.2.0` from the configured fixed
Central endpoint. The wrapper exited 1; the retained summary has `complete=false`,
`publicRepositoryConsumptionVerified=false`, and no completed lanes. No MySQL test ran and the
5.5.3 lane was not reached. This is an observed missing-artifact failure, not a policy rejection.

Raw evidence at `/private/tmp/routecontract-public-maven-unpublished-20260907/` contains
`reviewed-receipt.json`, `central-settings.xml`, `toolchain.log`, `summary.json`, and
`5.5.2/maven.log`, copied POM/Java/resources, and Maven's missing-download records.
This absence check preceded adding the final native/redirect command flags. Their behavior was
then verified separately by the real local 302 probe above; no second public absence check or
unchanged MySQL fixture run was needed.

## Remaining unverified cases

Both public runtime lanes still require successful loaded JAR/POM hash and Central origin checks,
transitive core resolution, exact whole ShardingSphere group selection, six real-MySQL assertions
including schema-2 MATCH and same-result 1-to-2 candidate/CLI rejection, and eight ordinary bad
graph rejections. The prior local staged MySQL evidence is separate and does not satisfy these
public checks. Public byte readback, Gradle consumption, release/CI wiring, and publication are
outside this focused Maven change.
