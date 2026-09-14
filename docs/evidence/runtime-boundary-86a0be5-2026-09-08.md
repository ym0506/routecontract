# Runtime boundary evidence for `86a0be5`

**28 of 28 planned cases passed** against the reviewed unsigned local 0.2.0
artifacts. The unchanged gate covers ADR A-01–A-08, A-10, A-18 and A-19 on Java 17,
exact ShardingSphere-JDBC 5.5.2/5.5.3 and MySQL 8.4.11.

The four formerly failing named dual-adapter ordinary-SQL cases—both runtimes and
both physical adapter orders—now emit the required `RC_UNSUPPORTED_MODULE_PATH`
before descriptor classification. Action entries and physical business-driver
calls remain zero. Both single-adapter named SQL cases also pass. Ordered
ordinary/capture isolation, wrong-adapter rejection and core-only behavior pass.

All 28 JVM identities were distinct. Input and command checks passed, and an
independent audit read all 620 JVM log lines through EOF with no additional
uncaught, shutdown or linkage errors. Exact former failures and raw evidence
hashes are in the [public record](runtime-boundary-86a0be5-2026-09-08.json).

The two earlier `4e06694` runs remain **FAILED: 22/28 and 24/28**. The first exposed
a fixture startup issue; the corrected fixture then exposed the four diagnostic
priority failures. Their records are preserved in the
[earlier evidence](runtime-boundary-4e06694-2026-09-08.md).

JPMS execution remains unsupported. This scoped result does not replace A-09,
A-11–A-13, full A-23 or A-29, and makes no release or adoption claim. Original
A-28 remains FAILED.
