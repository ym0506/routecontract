# Runtime lifecycle acceptance — candidate 86a0be5, 2026-09-08

Status: **accepted within the existing six A-11/A-12/A-13 cells** after independent review of
all complete terminated JVM logs, raw loader observations and final input bindings. The unchanged
six-case plan ran once, with six fresh JVMs and two fresh strict/locked dependency-cache lanes.
No first-party artifacts were rebuilt by this execution.

Production source: `86a0be5d2e444f3b73925122fa448d9d1a324edd`. Executed fixture checkout:
`3ad510a0af972231fbd074607936ee52be3cad1f`. Their production/publication inputs are identical.
The nine local staged 0.2.0 JAR/POM/module payloads are bound by reviewed receipt SHA-256
`1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e`.

| Existing ADR case | Exact ShardingSphere-JDBC 5.5.2 | Exact ShardingSphere-JDBC 5.5.3 |
| --- | --- | --- |
| A-11: first discovery hides the adapter, later TCCL exposes it | `RC_SHARDINGSPHERE_PROVIDER_NOT_ACTIVE`; action/driver/attempt counts 0/0/0; no snapshot | Same |
| A-12: first discovery sees the adapter, later TCCL hides it | MySQL capture `COMPLETE`; action/driver/attempt counts 1/1/1 | Same |
| A-13: separately defined bridge from the same core JAR | Automatic discovery and public capture both reject with `RC_ADAPTER_CLASSLOADER_MISMATCH`; counts 0/0/0; no snapshot | Same |

Both A-12 cells returned the independently asserted synthetic row `(orderId=201, userId=3,
status=PAID)` on `ds_1`, with one returned callback, zero callback failures, zero unknown outcomes
and no collector diagnostics. Cached provider Class, defining loader and code origin remained
unchanged after the TCCL hid the adapter. Each positive cell measured one real physical JDBC
execute delegation after initialization and warm-up, separately from its one hook-reported attempt.

Environment: macOS 26.4.1 aarch64, Python 3.12.14, Homebrew OpenJDK 17.0.15, Gradle 8.14.4,
Testcontainers 1.21.4 and MySQL Connector/J 26.7.0. Both positive cells used two disposable MySQL
8.4.11 containers with image digest
`b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb`.
A-12 is `verified - MySQL`; each cell is verified only for its exact stated runtime/topology.

All six JVMs exited zero, with no uncaught-thread or raw linkage error in their full EOF logs,
including shutdown. Ordinary Hikari configuration/direct-instantiation warnings remain in the
positive logs. The independent audit checked all 22 unchanged execution inputs, nine staged
payloads, both full compile/runtime graphs and compiled fixture bytes. Of the 22 inputs, 20 match
the prior corrected 4e execution; only the shared staged-consumer build and acceptance document
changed. The shared build strengthens graph checks while retaining lifecycle-only compilation.
The runner, corrected loader fixture, helpers, locks and wrapper retain their prior hashes.

The [previous corrected 4e evidence](runtime-lifecycle-final-candidate-2026-09-08.md) remains
unchanged and bound to its own source and receipt. Its original predecessor remains
**NOT_ACCEPTED** because uncaught Testcontainers `PathUtils` errors occurred during shutdown
after successful capture markers. This execution retains the reviewed correction: controlled
loaders remain alive through JVM shutdown, and the runner rejects uncaught-thread output after
process termination. Neither historical run is reclassified or counted as this new execution.

Reproduce from the executed fixture revision with matching reviewed artifacts; the output
directory must start absent outside the checkout:

```bash
python3 scripts/verify-runtime-lifecycle-consumer.py \
  --repository "$STAGED_REPOSITORY" \
  --staged-receipt "$REVIEWED_RECEIPT" \
  --staged-receipt-sha256 1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e \
  --staged-source-revision 86a0be5d2e444f3b73925122fa448d9d1a324edd \
  --java-home "$JAVA17_HOME" \
  --gradle-distribution-zip "$GRADLE_8_14_4_ZIP" \
  --evidence-directory "$EVIDENCE_DIRECTORY"
```

[Minimized JSON evidence](runtime-lifecycle-final-86a0be5-2026-09-08.json) records actual cell observations, nine payload pins,
22 executed input hashes, normalized command/environment, raw result/log hashes and both
historical bindings. Raw paths, SQL text and connection details remain omitted. This document
was prepared after execution and does not alter the frozen executed inputs.

A-13 discovery and capture occur sequentially in one fresh JVM per runtime. Negative cells create
no datasource; their zero driver count accompanies an unentered action sentinel. A-12 contains
one measured synchronous operation per exact runtime. These results do not establish concurrency,
performance, arbitrary async propagation or general plugin-container support. Hook observations
cover physical execution attempts, not complete route plans or transaction commit. Local staged
consumption does not prove public 0.2 availability, pinned release Temurin/Javadoc preparation,
human expectation review or independent adoption.
