# Runtime boundary evidence for `4e06694`

**FAILED: 24 of 28 cases passed.** This checks the existing ADR A-01–A-08,
A-10, A-18 and A-19 representative boundaries against reviewed unsigned local
0.2.0 artifacts, Java 17 and exact ShardingSphere-JDBC 5.5.2/5.5.3 with MySQL 8.4.11.

Four named dual-adapter ordinary-SQL cases—both runtimes and both physical
adapter orders—emit `RC_MULTIPLE_ROUTE_CONTRACT_ADAPTERS`. The required diagnostic
is `RC_UNSUPPORTED_MODULE_PATH`. All four reject during hook provider construction
before physical business-driver delegation, with zero action entries. Both
single-adapter named SQL cases produce the required diagnostic. Named capture,
classpath rejection and ordered capture-isolation checks pass.

The first execution remains separately **FAILED: 22 of 28 passed**. Its six named
SQL failures occurred before product guards because the fixture omitted two JDK
module roots. Adding exactly `java.instrument` and `jdk.unsupported` exposed the
four product diagnostic-priority failures above; no acceptance criterion changed.

The corrected execution used 28 distinct JVMs. Inputs remained unchanged, and an
independent review checked all 646 raw log lines through process EOF, finding no
additional uncaught, shutdown or linkage errors. The earlier 658-line audit and
both executions' raw evidence hashes are preserved in the
[public evidence record](runtime-boundary-4e06694-2026-09-08.json).

Original A-28 remains FAILED; A-29 is unchanged. This evidence does not establish
JPMS support, release readiness or production adoption. A-09, A-11–A-13 and full
A-23 remain separate. Any production fix needs newly reviewed artifacts and a
separate runtime result.
