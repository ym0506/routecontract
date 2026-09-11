# Repeated capture lifecycle and live objects

Status: [a completed 300,000-operation diagnostic and its limits](../../../docs/capture-retention.md) are recorded. This is a diagnostic
experiment against public RouteContract 0.1.3, not a production leak-free claim.
It reuses the first-project MySQL fixture and the observer-cost dependency POM;
it does not modify the library or time a JMH benchmark.

## Acceptance before implementation

1. Verify the loaded public 0.1.3 JAR checksum, Java 17 and hook presence. Use
   exact ShardingSphere-JDBC 5.5.3 and two disposable MySQL 8.4.11 containers.
   Do not accept application database configuration.
2. Keep four application caller threads and the shared ShardingSphere executor
   alive across ten blocks of 10,000 operations each. Alternate equality/range
   prepared queries; independently assert the exact returned business row.
   Successful captures must be complete and observe the expected 1/2 physical
   JDBC execution attempts. Each caller executes its operation synchronously.
3. Five percent of operations throw a synthetic checked exception after the
   query, and five percent throw a synthetic Error. Require the original object
   to be rethrown. Continue on the same caller threads, so leaked scope state
   cannot hide behind thread termination. No database failure is claimed.
4. At quiescent checkpoints, all submitted operations have returned and their
   frames/results have been released, but caller/database executors remain alive.
   Use `jcmd <exact child PID> GC.class_histogram` without `-all`. Require zero
   live instances of the seven per-capture classes listed by the runner.
   Static hook/context singletons and the no-op AttemptHandle are not per-capture
   objects and are intentionally outside this assertion.
5. Before the workload, deliberately retain 16 successful CapturedResult objects.
   The same zero-retention check MUST fail and detect 16 snapshots and 24
   physical-attempt records. Clear those references and require zero again.
   This control tests detection sensitivity; user-owned result retention is not
   a library defect. Never claim a product bug merely from this control.
6. Run three fresh JVM trials with a fixed 512 MiB heap. Record every checkpoint,
   exact commands, source/dependency hashes, JVM/OS, operation/error counts and
   elapsed workload time. A short `--smoke` run has a distinct status and cannot
   satisfy the full experiment. Missing, malformed or partial output fails.
7. Record the histogram's total live object bytes as context, without a pass/fail
   threshold: driver caches/JIT and other dependencies also affect it. A histogram
   gives instance counts and shallow sizes, not object-graph retained size, native
   memory/RSS, natural-GC behavior, CPU cost, allocation rate or request latency.

This experiment covers completed synchronous calls in this fixture, with deliberate
exceptions after successful business queries. It does not cover arbitrary async,
interruption, driver/network failure, application-held snapshots, other JDKs or
production workloads. It tests 300,000 measured operations, not months of uptime.
Zero observed instances at these checkpoints is narrower than proof of no leaks.

## Reproduce

Use a Java 17 JDK with `java` and `jcmd`, Maven 3.9.x, Python 3.10+ and Docker.
The runner writes to a **new directory outside the checkout** and resolves public
artifacts using the repository's Central-only settings. Only disposable fixture
containers are started. Diagnostics address only the child JVM launched by the runner.

```sh
python3 examples/observer-cost/retention/run.py --output /absolute/new/retention-run
# Short fixture/protocol check; never a full experiment result:
python3 examples/observer-cost/retention/run.py --smoke --output /absolute/new/retention-smoke
```

The process pauses between blocks while the external histogram is collected.
Checkpoints deliberately perturb GC and execution; elapsed time is descriptive,
not a throughput benchmark. Keep the process alive until its receipt is complete.
Raw logs/histograms stay outside the repository; publish only selected aggregate
observations and dependency/source hashes after checking them for sensitive data.

Method: [JDK 17 jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
documents heap histograms as high-impact diagnostics; `-all` also includes
unreachable objects, so it is deliberately omitted here.
