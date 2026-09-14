# A-26 public API migration: reviewed 86a0be5 staging, 2026-09-08

**The existing bounded A-26 gate passed once on final 86a0be5 staged bytes.** Six real
MySQL tests passed, and all 26 legacy public types and 167 member descriptors
were retained. The [minimized receipt](public-api-migration-86a0be5-2026-09-08.json)
binds the new execution, inputs and independent raw audits.

Producer: `86a0be5d2e444f3b73925122fa448d9d1a324edd`; consumer checkout:
`3ad510a0af972231fbd074607936ee52be3cad1f`, with identical production/publication
inputs. The independently reviewed receipt SHA-256 is
`1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e`.
The runner and its 21 inputs were unchanged from the earlier accepted run.

The pinned public 0.1.2 adapter JAR/POM were reused from retained release inputs.
The existing 5.5.3 adapter GAV resolved transitive core on 0.2. The three compiled
old MySQL classes ran unchanged on both graphs, each with a distinct initially
empty Gradle cache, strict dependency verification and locks. No RouteContract
production build or public first-party download occurred.

Both graphs passed their three required tests. The same synthetic business row
was returned by equality and range queries; equality reported one physical JDBC
execution attempt and matched, while range reported two and was rejected with
`RCM201` and `RCM202`. Actual captures used schema 1 on 0.1.2 and schema 2 on 0.2.

Existing model/codec, source recompilation and identity migration probes passed.
The documented exceptions were also observed: legacy constructors accept only
schema 1, recompiled constants are 2, record identity affects reflection and value
semantics, and exhaustive enum switches need migration for two new values.
Module-path capture returned `RC_UNSUPPORTED_MODULE_PATH` before action entry.
This result does not promise universal source or behavioral compatibility.

All 75 retained files, actual payload receipts, class inventories, graphs and
six-test XML were independently checked. All logs and XML were read through EOF;
only the five planned negative logs failed as expected, with no additional
uncaught or shutdown errors. The fixed environment was Java 17.0.15,
Gradle 8.14.4, exact ShardingSphere-JDBC 5.5.3 and digest-pinned MySQL 8.4.11.

Reproduce with the unchanged [runner](../../scripts/verify-public-api-migration.py)
and the placeholder command in the JSON. Supply the reviewed staged repository,
pinned 0.1.2 repository and an absent evidence directory; use the Java 17 home.
The external before/after binding record supplies the receipt/source checks
that this runner's CLI does not accept directly.

The [historical 4e result](public-api-migration-final-candidate-2026-09-08.md)
remains unchanged. **Original A-28 remains FAILED.** A-29 is a separate current-entry
contract. This is local staged-byte evidence for exact 5.5.3; it does not establish
public 0.2 distribution, complete release readiness, module-path support or adoption.
Raw local paths, SQL and connection details are omitted from this public copy.
