# CityPulse pilot: patch and recorded commands

This is the reproducibility companion to the [single-run result](citypulse-isolated-pilot-2026-09-08.md).
Use the [pinned CityPulse source](https://github.com/rexqd/citypulse-platform/tree/dccffc7a33965868a4b55ff9aae60bb831d76bad)
and the [unchanged two-file proposal patch](citypulse-routecontract-0.1.3-first-observation.patch).
The patch SHA-256 is `39b4e141347d88b3f3f9201102455090cd62bf7bf4764d8b2c33a96062c31b75`.
It adds the public RouteContract **0.1.3** test dependency and wraps the existing final lookup;
it preserves all 23 original assertion source calls in the class.

The commands below normalize the actual retained commands by replacing private host
paths with named variables. They describe the successful experiment; this documentation
revision did not rerun them. Host compilation used Java **17.0.15 / Maven 3.9.14**.
The actual test used Java **17.0.17 / Maven 3.9.11 inside a container**.
The direct Surefire command requires an already prepared, isolated environment.
It does not create a Docker network, initialize databases, start Redis or prevent host
service access on its own. The private Python isolation wrapper is not published here,
is not a portable product feature, and is not represented as a one-command reproducer.

## Source and patch provenance

At the pinned revision, the 442-file CityPulse tree contained no LICENSE, COPYING or
NOTICE file and no explicit project-license declaration in README or POM. Public
availability and third-party dependency licenses do not establish a CityPulse license.
This is an attributed, limited change proposal with 26 context lines, 2 removed lines
and 23 additions; it does not relicense upstream context or assert a grant of rights
for redistributing the application. No application archive, JAR, seed data or copied
DDL is distributed with the patch. Review the target project's licensing separately
before broader source reuse or redistribution.

The patch itself contains no credentials, connection strings, raw query output or
private filesystem paths. Its target files are [pom.xml](https://github.com/rexqd/citypulse-platform/blob/dccffc7a33965868a4b55ff9aae60bb831d76bad/pom.xml) and the
[existing integration test](https://github.com/rexqd/citypulse-platform/blob/dccffc7a33965868a4b55ff9aae60bb831d76bad/src/test/java/com/hmdp/VoucherOrderShardingIntegrationTest.java).

## Prepare a new checkout and compile

In a POSIX shell, replace these placeholders with new absolute directories and your
explicit Java/Maven installations. Do not point them at an owner's existing checkout,
Maven cache or configuration. `PILOT_PATCH` is the downloaded patch linked above.
`PILOT_EVIDENCE` and `PILOT_M2` are initially empty; the settings file contains no
repositories, credentials, profiles or extensions.

```sh
set -eu
PILOT_CHECKOUT='<new-absolute-checkout-directory>'
PILOT_PATCH='<absolute-path-to-the-linked-patch>'
PILOT_EVIDENCE='<new-absolute-evidence-directory>'
PILOT_M2='<new-absolute-Maven-repository-directory>'
PILOT_PRIVATE_HOME='<new-absolute-private-home-directory>'
PILOT_TMP='<new-absolute-temporary-directory>'
PILOT_SETTINGS='<absolute-isolated-settings.xml-path>'
PILOT_JAVA_HOME='<Java-17.0.15-home>'
PILOT_MVN='<Maven-3.9.14-bin/mvn>'
PILOT_AUXILIARY_PATH='<explicit-local-tool-bin-directories-separated-by-colons>'

for PILOT_NEW_DIR in "$PILOT_CHECKOUT" "$PILOT_EVIDENCE" "$PILOT_M2" "$PILOT_PRIVATE_HOME" "$PILOT_TMP"; do
  test ! -e "$PILOT_NEW_DIR"
done
test ! -e "$PILOT_SETTINGS"
mkdir -p "$PILOT_CHECKOUT" "$PILOT_EVIDENCE" "$PILOT_M2" \
  "$PILOT_PRIVATE_HOME" "$PILOT_TMP"
git -C "$PILOT_CHECKOUT" init
git -C "$PILOT_CHECKOUT" remote add origin https://github.com/rexqd/citypulse-platform.git
git -C "$PILOT_CHECKOUT" fetch --depth=1 origin dccffc7a33965868a4b55ff9aae60bb831d76bad
git -C "$PILOT_CHECKOUT" checkout --detach FETCH_HEAD
test "$(git -C "$PILOT_CHECKOUT" rev-parse HEAD)" = dccffc7a33965868a4b55ff9aae60bb831d76bad
git -C "$PILOT_CHECKOUT" apply --check "$PILOT_PATCH"
git -C "$PILOT_CHECKOUT" apply "$PILOT_PATCH"

cat > "$PILOT_SETTINGS" <<'XML'
<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"><interactiveMode>false</interactiveMode></settings>
XML
cd "$PILOT_CHECKOUT"
```

The actual host process received a scrubbed environment, private home, explicit Java
and empty Maven settings. `PILOT_AUXILIARY_PATH` replaces the two explicitly
allowed tool-bin directories from the recorded host environment; it does not import
the owner's ambient PATH. The following is the normalized compile/graph command:

```sh
env -i HOME="$PILOT_PRIVATE_HOME" JAVA_HOME="$PILOT_JAVA_HOME" \
  PATH="$PILOT_JAVA_HOME/bin:$PILOT_AUXILIARY_PATH:/usr/bin:/bin" TMPDIR="$PILOT_TMP" LANG=en_US.UTF-8 \
  "$PILOT_MVN" -B -ntp -s "$PILOT_SETTINGS" -gs "$PILOT_SETTINGS" \
  "-Dmaven.repo.local=$PILOT_M2" -DskipTests test-compile \
  org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree \
  -Dverbose "-DoutputFile=$PILOT_EVIDENCE/dependency-tree.txt" \
  org.apache.maven.plugins:maven-dependency-plugin:3.6.1:build-classpath \
  "-Dmdep.outputFile=$PILOT_EVIDENCE/test-classpath.txt" -Dmdep.includeScope=test
```

Compilation and dependency resolution are not a test pass. The recorded execution
compiled 204 application and 77 test files. Before using the resolved graph, check
that every resolved `org.apache.shardingsphere` artifact is 5.5.3 and the selected
RouteContract artifact is `routecontract-shardingsphere-5.5:0.1.3` in test scope.
The recorded graph had 276 JARs, including 73 ShardingSphere JARs. Verify the resolved
RouteContract JAR against SHA-256
`9e883e618eb09d9ecf30814151bb4b0a43eba02c78d288cc582fa7e57e6edba2`.
Do not substitute an unreleased local build.

The actual preparation also prefetched the offline Surefire provider, with tests
explicitly skipped. This command is preparation, not another test execution:

```sh
env -i HOME="$PILOT_PRIVATE_HOME" JAVA_HOME="$PILOT_JAVA_HOME" \
  PATH="$PILOT_JAVA_HOME/bin:$PILOT_AUXILIARY_PATH:/usr/bin:/bin" TMPDIR="$PILOT_TMP" LANG=en_US.UTF-8 \
  "$PILOT_MVN" -B -ntp -s "$PILOT_SETTINGS" -gs "$PILOT_SETTINGS" \
  "-Dmaven.repo.local=$PILOT_M2" -DskipTests \
  org.apache.maven.plugins:maven-surefire-plugin:3.1.2:test \
  org.apache.maven.plugins:maven-dependency-plugin:3.6.1:get \
  -Dartifact=org.apache.maven.surefire:surefire-junit-platform:3.1.2
```

## Required isolated services and schema

The actual environment was a new **internal Docker bridge network**, with no
published ports, host networking, inherited owner configuration, host devices or
Docker socket inside the test container. Use fresh disposable services and verify
their identity before the test. A host MySQL/Redis endpoint is not an equivalent
substitute. The test performs writes and cleanup even though the capture wraps a read.

| Component | Recorded immutable image |
| --- | --- |
| MySQL 8.4.11 | `mysql@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb` |
| Redis 7.4.2 | `redis@sha256:02419de7eddf55aa5bcf49efb74e88fa8d931b4d77c07eff8a6b2144472b6952` |
| Maven 3.9.11 / Temurin 17.0.17 | `maven@sha256:e4a7ace3dc0d645ed97f8d9ad0b0d3f0b14fa8d150138f27f116d7105a639b82` |

All three recorded images were ARM64. The test container had a 2 GiB memory limit,
2 CPUs, dropped capabilities, `no-new-privileges`, a read-only root filesystem and a
writable temporary filesystem. No other platform or resource setting was rerun here.
MySQL used a disposable user limited to the two synthetic schemas; the actual local
fixture enabled `--mysql-native-password=ON` and used that authentication mechanism.
Redis started empty, with persistence disabled. These are experiment settings, not
production deployment recommendations.

Create exactly **11 empty tables** in two new schemas. The experiment used logical
DataSources `ds_0` and `ds_1`, each mapped to its corresponding synthetic schema.
Use only the indicated CREATE TABLE definitions from the pinned source and rename the
physical order/router copies as below. Preserve their columns, defaults and keys.
Do not import the complete `hmdp.sql` file: it contains demo rows. Do not run
`scripts/prepare-order-sharding.sh` or the order migration/backfill scripts; they copy
data from another database. This experiment did not create or read the original
`hmdp` database and did not insert seed rows before the existing test ran.

| Synthetic schema | Empty physical tables | Definition source |
| --- | --- | --- |
| Both `ds_0` and `ds_1` schemas | `tb_voucher_order_0`, `tb_voucher_order_1` (4 total) | [Order definition](https://github.com/rexqd/citypulse-platform/blob/dccffc7a33965868a4b55ff9aae60bb831d76bad/src/main/resources/db/hmdp.sql#L267) |
| Both `ds_0` and `ds_1` schemas | `tb_voucher_order_router_0`, `tb_voucher_order_router_1` (4 total) | [Router definition](https://github.com/rexqd/citypulse-platform/blob/dccffc7a33965868a4b55ff9aae60bb831d76bad/src/main/resources/db/hmdp.sql#L292) |
| `ds_0` schema only | `tb_voucher_order_timeout_task` | [Timeout-task definition](https://github.com/rexqd/citypulse-platform/blob/dccffc7a33965868a4b55ff9aae60bb831d76bad/src/main/resources/db/hmdp.sql#L310) |
| `ds_0` schema only | `tb_voucher_order_reconciliation` | [Reconciliation definition](https://github.com/rexqd/citypulse-platform/blob/dccffc7a33965868a4b55ff9aae60bb831d76bad/src/main/resources/db/hmdp.sql#L331) |
| `ds_0` schema only | `tb_voucher_stock_ledger` | [Ledger definition](https://github.com/rexqd/citypulse-platform/blob/dccffc7a33965868a4b55ff9aae60bb831d76bad/src/main/resources/db/hmdp-plus-stock-ledger.sql#L13) |

The application's [sharding factory](https://github.com/rexqd/citypulse-platform/blob/dccffc7a33965868a4b55ff9aae60bb831d76bad/src/main/java/com/hmdp/config/ShardingDataSourceConfiguration.java)
and the test's direct cleanup connections read `HMDP_DB_HOST`, `HMDP_DB_PORT` and
`HMDP_SHARDING_DB_0/1`. Merely changing `spring.datasource.url` does not redirect them.
Their credential readers differ, so the environment and Spring property aliases below
must contain identical disposable credentials. Keep `application-local.yaml` absent;
do not inherit owner Spring, Redis URL/cluster/sentinel, Maven or JVM overrides.

Prepare these environment values for the test container; replace every angle-bracket
placeholder before use. `HMDP_RUN_SHARDING_TESTS` must be a real environment variable,
not only a JVM system property:

```dotenv
HMDP_RUN_SHARDING_TESTS=true
HMDP_DB_HOST=<dedicated-MySQL-alias-on-the-internal-network>
HMDP_DB_PORT=<dedicated-MySQL-port>
HMDP_DB_USERNAME=<disposable-user>
HMDP_DB_PASSWORD=<ephemeral-test-password>
HMDP_SHARDING_DB_0=<new-ds0-schema>
HMDP_SHARDING_DB_1=<new-ds1-schema>
HMDP_SCHEDULING_ENABLED=false
```

Prepare an `isolated.properties` file using the following operational settings from
the actual run. Replace the credential/endpoint placeholders with the same values
used to provision the synthetic services. Private credentials are not included here.
The debug/logging lines are retained for fidelity; the last logger setting did not
suppress the original ShardingSphere SQL logger, so raw output must remain private.

```properties
spring.datasource.username=<same-disposable-user>
spring.datasource.password=<same-ephemeral-test-password>
spring.data.redis.host=<dedicated-Redis-alias-on-the-internal-network>
spring.data.redis.port=<dedicated-Redis-port>
spring.data.redis.database=0
spring.data.redis.password=
spring.data.redis.username=
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.kafka.KafkaAutoConfiguration
spring.kafka.listener.auto-startup=false
spring.kafka.admin.auto-create=false
spring.kafka.bootstrap-servers=127.0.0.1:1
hmdp.scheduling.enabled=false
hmdp.delay-queue.enabled=false
hmdp.cache.shop.warmup.enabled=false
hmdp.cache.shop.geo-warmup.enabled=false
hmdp.cache.shop.bloom.enabled=false
hmdp.order-mq.type=redis-stream
debug=true
logging.level.com.hmdp=INFO
logging.level.org.apache.shardingsphere=INFO
logging.level.ShardingSphere-SQL=OFF
```

Here `127.0.0.1:1` is the test container's loopback, not the host, and Kafka
configuration is excluded. No Kafka broker was used. The actual
[custom scheduling gate](https://github.com/rexqd/citypulse-platform/blob/dccffc7a33965868a4b55ff9aae60bb831d76bad/src/main/java/com/hmdp/config/SchedulingConfig.java)
requires `hmdp.scheduling.enabled=false`; the original test's
`spring.task.scheduling.enabled=false` alone is insufficient. Redisson, Pub/Sub and
stream initialization still use Redis. The valid `redis-stream` branch retains an
idle consumer against that fresh Redis; these settings do not disable every background
client. The actual run used Redis with no authentication on its isolated network;
keep that fact separate from any owner's protected Redis service.

## Actual direct Surefire invocation

The following locations are **prepared container mounts**, not host defaults:

| Container location | Prepared content |
| --- | --- |
| `/workspace` | Patched pinned checkout, including the compiled `target/classes` and `target/test-classes` |
| `/m2` | The fresh dependency repository populated by compile and prefetch |
| `/settings.xml` | The empty isolated Maven settings file |
| `/pilot/isolated.properties` | The completed private properties file above, mounted read-only |
| `/tmp` | Writable private temporary filesystem |

The container environment already contains the required `HMDP_*` values above and
`MAVEN_OPTS=-Duser.home=/tmp`; it inherits none of the owner's application settings.
After verifying those services, mounts and environment, the recorded native Maven
invocation was:

```sh
cd /workspace
/usr/share/maven/bin/mvn -o -B -ntp -s /settings.xml -gs /settings.xml \
  -Dmaven.repo.local=/m2 \
  '-Dspring.config.location=classpath:/application.yaml,classpath:/application-sharding.yaml,file:/pilot/isolated.properties' \
  -Dspring.config.import= \
  -Dhmdp.scheduling.enabled=false \
  -DfailIfNoTests=true \
  '-Dtest=VoucherOrderShardingIntegrationTest#routesFourOrderCombinationsAndKeepsConditionalPayIdempotent' \
  org.apache.maven.plugins:maven-surefire-plugin:3.1.2:test
```

This directly invokes Surefire **offline** against previously compiled classes.
It is not the `mvn test` lifecycle and does not compile missing classes or repair a
missing dependency cache. It does not enable the environment-gated test by itself;
`HMDP_RUN_SHARDING_TESTS=true` must already be present. The private wrapper bounded
execution to 300 seconds; the actual run finished successfully in about 10 seconds.
A repeat attempt needs a new evidence directory and fresh disposable fixtures.

Inspect `target/surefire-reports/TEST-com.hmdp.VoucherOrderShardingIntegrationTest.xml`.
Require exactly the named method, one test, zero failures/errors/skips and an actual
`RouteContract pilot: observedAttempts=..., observedDataSources=...` aggregate line.
A Maven success with a skipped test is not a pilot pass. The recorded aggregate was
2 attempts and 1 observed DataSource; this one observation is not an approved budget.

After recording the result, remove only the containers, anonymous volumes and network
created for the experiment. Retain source, patch, graph, command and report hashes;
share aggregate results and stable failure classifications, not raw application logs
or connection settings. The original unpatched method and full test suite were not
executed in this experiment, and no maintainer adoption or approved regression contract
is established by following these steps.
