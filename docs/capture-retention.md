# Do completed captures leave live objects behind?

**No instances of the seven inspected per-capture classes remained at the measured
quiescent checkpoints in this fixture.** Three fresh JVMs each completed 100,000
operations with four reusable caller threads. This is a short repeated-operation
diagnostic, **not evidence of leak-free long-term operation**: each trial's measured
workload took about 11 seconds, excluding setup and diagnostic pauses.

Evidence labels: **verified - MySQL**, **verified - ShardingSphere-JDBC 5.5.3**.
The immutable public RouteContract 0.1.3 JAR was loaded from Maven Central.

## Workload and controls

The experiment reuses the first-project fixture: two disposable MySQL 8.4.11
instances, the same equality/range prepared queries, and the same complete expected
order. Every query independently checks its business result. Four caller threads
and the ShardingSphere executor remain alive across ten blocks per JVM.

Across the three measured trials:

- **270,000 operations returned normally.** Their captures were complete, reported
  no execution failure and observed the expected one/two physical JDBC execution
  attempts and exact fixture data-source names.
- **15,000 operations threw a checked exception and 15,000 threw an Error**, after
  a successful business query. The original thrown object was preserved. Later
  operations reused the same caller threads successfully. These are application
  failure/cleanup paths, not simulated MySQL/network failures.
- **30 post-workload checkpoints** found zero instances of `CapturedResult`,
  `RouteSnapshot`, `PhysicalExecutionAttempt`, `CaptureScope`, `CaptureToken`,
  `MutableCapture` and `MutableAttempt`. Six earlier released/warmup checkpoints
  also found zero. Static hook/context singletons and the singleton no-op
  `AttemptHandle` are not per-operation state and are outside this assertion.

Before each trial, the harness deliberately holds 16 successful capture results.
The same zero-instance assertion rejects that state and sees **16 result wrappers,
16 snapshots and 24 physical-attempt records**. Releasing the references restores
zero counts while the executors remain alive. This sensitivity control detects
intentional application-owned retention; it is not a newly discovered library leak.

## Observations

| Fresh JVM trial | Measured operations | Workload time, excluding checkpoints | Live object bytes after warmup | Live object bytes after 100,000 operations | Inspected per-capture instances at final checkpoint |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 100,000 | 11.129 s | 39,978,080 | 40,039,832 | 0 |
| 2 | 100,000 | 11.006 s | 39,977,664 | 40,042,008 | 0 |
| 3 | 100,000 | 10.940 s | 39,977,776 | 40,040,528 | 0 |

The byte totals sum the JVM's live-object histogram. They include all loaded
libraries and fixture state and are context, not a pass/fail memory threshold or
a measurement of RouteContract's object-graph retained size. Small growth can have
many causes; this experiment does not attribute it to a method or prove a plateau.

Environment: macOS/Darwin 25.4.0 arm64, 12 logical CPUs; Homebrew OpenJDK 17.0.15+0,
G1 with a fixed 512 MiB heap; Maven 3.9.14; Docker 29.2.1; exact ShardingSphere-JDBC
5.5.3 and MySQL 8.4.11. Each fork also runs 1,000 warmup and 16 retained-control
operations, excluded from the 300,000 measured total. All three trials, including
setup and diagnostics, are timestamped in the observation record.

## Inspect or reproduce

- [Measured harness revision `7cfe257`](https://github.com/ym0506/routecontract/commit/7cfe257728aa308c3e591c4e8bc6675295c8d82a)
- [Acceptance criteria and command](../examples/observer-cost/retention/README.md)
- [All selected checkpoints, dependency/source hashes and runtime identity](evidence/capture-retention-0.1.3-2026-09-11/observations.json)
- [Separate allocation/operation-time experiment](observer-cost.md)

```sh
# Select a Java 17 JDK containing both java and jcmd; start Docker first.
python3 examples/observer-cost/retention/run.py --output /absolute/new/retention-run
```

The public JSON is an explicitly minimized projection. All 39 full histograms were
reparsed locally and checked against their receipt hashes before extracting it.
Raw process logs and full histograms remain in the maintainer's local run directory,
outside the checkout; their hashes do not imply public availability or independent
verification. Rerunning the harness creates a new set of raw files for inspection.

The [CI smoke workflow](../.github/workflows/observer-cost-smoke.yml) runs a separate
320-operation protocol/fixture check with the retained-result control. Its
`SMOKE_ONLY_PASS` status cannot substitute for the full diagnostic. Parser/counter
negative tests reject truncated histograms, inconsistent totals, missing operation
counts, wrong runtime/JAR identity and retained instances of each inspected class.

## Limits

[`jcmd GC.class_histogram`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
is a high-impact diagnostic. The harness addresses only its own child JVM and omits
`-all`, which would include unreachable objects. Callers pause at checkpoints, so
this is not observation under uninterrupted natural GC. Histograms provide counts
and shallow object bytes, not native/RSS memory, retained-reference graphs, CPU,
allocation rate, latency overhead or application-tail latency.

No absent/idle performance comparison, long-duration soak, arbitrary async,
interruption, database/network fault, Java 21 or production workload was tested
here. A zero count at selected checkpoints does not prove that every possible
capture path is free of leaks. This maintainer-run experiment establishes neither
independent adoption nor an upstream defect and does not justify a new upstream
bug report by itself.
