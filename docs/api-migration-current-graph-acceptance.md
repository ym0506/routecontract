# Public API migration against the integrated candidate graph

A consumer checking an upgrade needs to know whether previously compiled
application code still works with the new artifact and its actual dependencies.
The existing 0.2 migration lock still selects Jackson streaming 3.1.5, while the
integrated core publishes 3.1.6. Its shared fixture also selects the older
FasterXML 2.18.9 BOM. That stale new-version lane cannot qualify the current
candidate's dependency graph.

Status: acceptance before correction and full execution.

The unchanged fixture actually resolved successfully with Gradle 9.7.1
(native exit 0), but its retained graph selected streaming 3.1.5 and
FasterXML 2.18.9. This is a missing graph qualification check, not a
reproduced native dependency-resolution failure or a production failure.

First add a current-lane graph check and show that it rejects those actual
stale selections before it reports migration success. Require streaming
3.1.6 on the runtime classpath and FasterXML core, databind, JDK8 and JSR310
2.18.10 on both compile and runtime classpaths. Then select BOM 2.18.10 only
for the 0.2 lane and regenerate only its lock with Gradle 9.7.1. Preserve the
0.1.2 lock, immutable public JAR/POM pins, approved schema-1 baseline, Java
test/probe source, public API inventory and record-shape expectations.

Run the complete existing A-26 harness against the same reviewed unsigned
candidate bytes, with an external pre/post receipt and production-source
binding because this runner does not accept those review arguments directly.
The old classes must be compiled once on 0.1.2 and execute unchanged on both
graphs. Require all six existing MySQL test executions, descriptor retention,
source/reflection/value semantics and documented enum/module-path rejection
probes. A compile-only control cannot replace this result.

Keep the older candidate results and their graphs as historical evidence.
No new production artifact, expected business result, golden, workload, JDK
profile, authentic baseline approval or public 0.2 release is created here.
