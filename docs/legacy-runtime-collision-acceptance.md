# Physical legacy JAR runtime acceptance (ADR A-28)

This specification preceded the executable fixture. The [2026-09-08 run](evidence/legacy-runtime-collision-2026-09-08.md)
executed all required cells and failed four direct-capture diagnostic assertions.
A-28 remains failed until every required cell satisfies the original ADR; a
different early error does not pass the required collision diagnostic.

Use the four distributed inputs in `scripts/legacy-artifact-inputs.json`:
0.1.0, 0.1.2, 0.1.3 and 0.1.0-rc2. Verify the public JAR/POM/layout bytes against
that registry. Verify all nine supplied current staging payloads against the
reviewed receipt and compare production/publication source inputs with its
separately supplied source revision. Never rebuild or replace a legacy class/provider.

Resolve each current exact 5.5.2/5.5.3 dependency graph independently with the
existing staged consumer's strict verification metadata and locks, then insert
the actual legacy JAR into a manually assembled classpath. This intentionally
bypasses resolver mediation to exercise the separate runtime requirement.

For each legacy version and each current adapter/runtime, run legacy first and
legacy last in **separate fresh JVMs** for both entry paths (32 collision cells):

- Ordinary ShardingSphere SQL before any capture. A clean split control must
  return exactly order 201, user 3, status PAID from real pinned MySQL. A JDBC
  driver delegate records entry into the actual physical business execution;
  collision cells must fail before that delegation and return no business row.
- Direct `RouteContract.capture` with an action sentinel, before any datasource,
  hook discovery, or other RouteContract call. The sentinel must remain false.

Every collision cell must contain `RC_LEGACY_ADAPTER_COLLISION` in its exception
chain, without an `AbstractMethodError`, other linkage failure, action entry,
physical business execution or silent success. Record selected `RouteContract`
and registry code sources to expose shadowing, rather than initializing the new
preflight from the fixture. Keep existing failure details; never normalize a
legacy error into the expected code. A clean capture control must enter its
sentinel and return an INCOMPLETE snapshot with zero observed attempts and
`RC_NO_START_CALLBACK_OBSERVED`.

Each cell retains its actual JVM command, classpath file hashes, process result,
exception classes/codes, local log and a machine result. A Python-generated JUnit
summary describes these subprocess assertions; it is not raw JUnit from the
product. Partial or failed runs cannot produce a verified A-28 summary. Public
summaries omit SQL, parameters, JDBC URLs and connection properties. The runner's
`summary.json`, per-case observations and generated JUnit retain raw exception
messages locally; curate a separate minimized receipt before publication. This proves
only the supplied local staged bytes and exact Java 17 / MySQL environment, not
public availability of 0.2 artifacts or production adoption.
