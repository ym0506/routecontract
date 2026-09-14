# Old application bytecode on the current 0.2 candidate

An upgrade check should tell a user whether existing compiled code works with
the new library and its intended dependencies. The previous example could print
success while its lock selected older Jackson versions. It did not qualify the
current candidate's dependency combination.

The unchanged example actually resolved successfully (native exit 0), selecting
streaming Jackson 3.1.5 and FasterXML 2.18.9. A new graph assertion rejected that
selection with `RC_MIGRATION_DEPENDENCY_GRAPH_MISMATCH` (native exit 1). The fixture
now selects FasterXML 2.18.10 only for 0.2, and Gradle 9.7.1 regenerated only its
0.2 lock, selecting streaming Jackson 3.1.6. This fixes qualification evidence;
it does not demonstrate a production crash.

The complete existing A-26 harness then passed once on producer
`5800ed2960aefbf63c01d2ebaf2265278d662494`. The consumer revision and exact graph
are recorded in the [minimized receipt](public-api-migration-5800ed2-2026-09-14.json).
The separately cross-checked candidate receipt SHA-256 is
`9a4d745ff11508a8ab08dd8bced6a7893d8f6e6ff5baab34b3445aea652ba49c`.
Production/publication inputs and all 20 migration inputs remained unchanged
during execution. The check did not rebuild production artifacts.

| Check | Observed result |
| --- | --- |
| Tests compiled on public 0.1.2 | Three passed on the old graph |
| Same compiled tests, unchanged, on 0.2 | Three passed on the current graph |
| Public API inventory | 26 old types and 167 member descriptors retained |
| Same business row, wider execution | Equality reported one physical JDBC execution attempt; range reported two and failed the existing budgets |
| Source, model and identity probes | Existing required probes passed |
| Documented unsupported cases | Existing constant, enum and module-path rejection probes behaved as specified |

The 0.1.2 lock, public JAR/POM pins, schema-1 baseline, Java workload and API
inventory were preserved. Old captures use schema 1; current captures use
schema 2. Seven retained old class files, six exact JUnit cases, both dependency
graphs and 73 retained files were cross-checked after execution.

Environment: Temurin Java 17.0.20.1+1, Gradle 9.7.1, exact ShardingSphere-JDBC
5.5.3, macOS arm64, and MySQL 8.4.11 at digest
`b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb`.
Evidence labels: **verified - MySQL**, **verified - ShardingSphere-JDBC 5.5.3**.

Use a Java 17 `JAVA_HOME`, the pinned public 0.1.2 repository, the supplied
current repository and a new evidence directory:

```sh
python3 scripts/verify-public-api-migration.py \
  --legacy-repository /path/to/pinned-0.1.2-repository \
  --repository /path/to/verified-0.2-repository \
  --evidence-directory /path/to/new-migration-evidence
```

Independently compare the candidate receipt and production inputs before and
after the run; this runner's CLI does not accept those binding arguments.
The receipt is an integrity record, not a human approval.

This remains bounded classpath compatibility evidence. Legacy constructors,
inlined schema constants, record identity and exhaustive enum switches retain
their documented migration requirements. It does not prove universal behavioral
compatibility, module-path support, public 0.2 availability, human baseline
approval or adoption. Original A-28 remains **FAILED**; A-29 is separate.
The [86a0be5 result](public-api-migration-86a0be5-2026-09-08.md) remains historical
evidence for its own bytes and environment.
