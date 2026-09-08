# Runtime lifecycle acceptance — final local candidate, 2026-09-08

Status: **accepted within the six existing A-11, A-12 and A-13 cells** after independent review.
All six complete terminated JVM logs were checked, including shutdown tails. No uncaught-thread
or raw linkage failure remained; nine staged payloads, 22 frozen inputs, both exact graphs and
compiled fixture bytes matched their before/after records. A-12 is `verified - MySQL`; all cells
are verified within their exact ShardingSphere-JDBC 5.5.2 or 5.5.3 runtime and stated topology.

Production source is `4e066942f6e244345fe908970b81446f9e08f64e`. The nine local staged 0.2.0
JAR/POM/module payloads use the externally pinned reviewed receipt
`38b2269eca162f121fd3996c56df8b894ae2f43cedeb08fcc627032cf70eaa43`.
This is local staged consumption, not evidence of public 0.2 availability or independent adoption.

| Existing ADR case | Exact 5.5.2 observation | Exact 5.5.3 observation |
| --- | --- | --- |
| A-11: first discovery hides adapter; later TCCL exposes it | `RC_SHARDINGSPHERE_PROVIDER_NOT_ACTIVE`; action 0, no snapshot | Same |
| A-12: first discovery sees adapter; later TCCL hides it | Real MySQL capture `COMPLETE`; action 1, physical driver execute 1, hook-reported physical attempt 1 | Same |
| A-13: separately defined bridge from the same core JAR | Actual automatic discovery and public capture both reject with `RC_ADAPTER_CLASSLOADER_MISMATCH`; action 0, no snapshot | Same |

A-12 returned the independently asserted synthetic row `(orderId=201, userId=3, status=PAID)`
on `ds_1`, with one returned callback, zero callback failures, zero unknown outcomes and no
collector diagnostics. Its cached provider Class, defining loader and code origin remained the
same when the TCCL hid the adapter. Instance equality is not required: ShardingSphere caches
non-singleton provider classes and may construct new hook instances.

The corrected execution used six fresh JVMs and two independently resolved, strict/locked Gradle
consumer graphs with initially absent dependency caches. No first-party artifact was rebuilt.
Environment: macOS 26.4.1 aarch64, Python 3.12.14, OpenJDK 17.0.15, Gradle 8.14.4,
Testcontainers 1.21.4 and MySQL Connector/J 26.7.0. Each positive cell used two disposable MySQL
8.4.11 containers pinned to image digest
`b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb`.
Initialization and warm-up precede the single measured synchronous PreparedStatement operation.

The first six-cell execution remains **NOT_ACCEPTED**. Although its capture reports and process
exit codes looked successful, independent review found uncaught Testcontainers `PathUtils`
linkage errors during JVM shutdown. The harness correction keeps its controlled loaders alive
through shutdown and rejects uncaught-thread output in the full terminated process log. An exact
original-tail regression is included. This corrected six-cell run was executed once; it is not a
claim that the rejected predecessor passed.

Reproduce from the matching fixture and supplied reviewed artifacts; the evidence directory must
start absent outside the checkout:

```bash
python3 scripts/verify-runtime-lifecycle-consumer.py \
  --repository "$STAGED_REPOSITORY" \
  --staged-receipt "$REVIEWED_RECEIPT" \
  --staged-receipt-sha256 38b2269eca162f121fd3996c56df8b894ae2f43cedeb08fcc627032cf70eaa43 \
  --staged-source-revision 4e066942f6e244345fe908970b81446f9e08f64e \
  --java-home "$JAVA17_HOME" \
  --gradle-distribution-zip "$GRADLE_8_14_4_ZIP" \
  --evidence-directory "$EVIDENCE_DIRECTORY"
```

[The minimized machine-readable evidence](runtime-lifecycle-final-candidate-2026-09-08.json)
records all nine payload pins, 22 executed input fingerprints, normalized command/environment,
actual cell observations, raw log/report hashes, predecessor review and corrected independent
review. Raw evidence remains separately retained; local paths and database connection details
are omitted from this document.

The limits are narrow. A-13's discovery and capture occur sequentially inside the same fresh JVM
per runtime. Negative cells instantiate no datasource; their zero driver counter accompanies the
unentered operation sentinel. A-12 is one measured operation per exact runtime, not concurrency,
performance, arbitrary async propagation or general plugin-container evidence. SQLExecutionHook
reports physical JDBC execution attempts, not complete route plans or transaction commit.
