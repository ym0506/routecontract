# Observer cost of public RouteContract 0.1.3

Status: **planned**. Do not quote performance numbers until a completed run and its limitations
are recorded. This standalone JMH experiment consumes the published JAR, not local project
classes. It reuses the first-project example's `OrderFixture`, `OrderRepository` and YAML.

## Acceptance and measurement scope

1. Use Java 17, exact ShardingSphere-JDBC 5.5.3 and two disposable MySQL 8.4.11 containers.
   Never accept an application database URL. Container startup and data-source initialization
   happen outside timed operations; each fork starts the same synthetic fixture.
2. Run the equality query and the same-value range query. Both must return exactly the existing
   expected order. In the checked condition, every capture must be complete, have no reported
   execution failures, and observe respectively one or two physical JDBC execution attempts.
   These are fixture expectations, not automatically approved production baselines.
3. Compare three classpaths/operations: `absent` excludes only the published RouteContract JAR;
   `idle` includes it but does not call capture; `checked` includes it and calls `captureResult`
   plus completeness, callback-outcome and attempt-count assertions. Keep all other dependency
   bytes identical. Verify both the class and SPI-provider presence for each fork.
4. Time one connection acquisition, prepared query, materialized result and business assertion
   per invocation. The checked condition additionally includes capture and route assertions.
   Do not call the difference pure hook overhead. No manifest/report serialization is timed.
5. Use one benchmark worker, JMH AverageTime in microseconds per operation, separate warmup and
   measurement iterations, fresh JVM forks and the GC profiler. Record normalized allocation
   in bytes/op as an estimate, not retained heap, a leak test, CPU cost or service tail latency.
6. Rotate condition order across three blocks. Keep each block's JMH JSON, logs, runtime and
   dependency hashes. Failed or incomplete runs must not produce an aggregate success result.
   Calculate block comparisons and expose variation; do not treat iterations as independent
   users, production requests or deployment environments.

The initial result is exploratory maintainer-run evidence on one machine. It cannot establish
production overhead, concurrency scalability or a statistically stable small difference. In
particular, fixture startup, JIT state, GC and local Docker scheduling can dominate differences.

## Reproduction

Requires Maven, a Java 17 JDK, Python 3 and a running Docker daemon. The runner uses Central-only
Maven settings and an output directory outside the source tree. It starts only disposable
containers through the shared fixture. A complete run uses three blocks, five one-second
warmups and five one-second measurements per fresh JVM. A smoke run is never a performance result.

```sh
python3 examples/observer-cost/run.py --output /absolute/new/output-directory
```

Set `JAVA_HOME` to a Java 17 JDK if Maven otherwise selects another version. Dependency downloads
and eighteen fixture/JVM startups can make the full experiment take several minutes.

## Method references

- [OpenJDK JMH: standalone projects and command-line execution](https://github.com/openjdk/jmh)
- [JMH benchmark modes](https://github.com/openjdk/jmh/blob/1.37/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_02_BenchmarkModes.java)
- [JMH profilers and allocation interpretation](https://github.com/openjdk/jmh/blob/1.37/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_35_Profilers.java)

JMH is an experiment dependency; it is not bundled into the RouteContract release.
