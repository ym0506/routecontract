# Published adapter core project dependency

The corrected twelve-document local SBOM inventory rejects the adapter's direct core
dependency because its POM uses Maven's default JAR dependency, while the pinned Gradle
producer represents the same first-party component with
`project_path=%3Aroutecontract-core`. The retained failed inventory log has SHA-256
`cb57f12c79db38b4a8688b0d79a4916d0e631f1aee8f85cd3178cb0d6b58cae0`.

The observed edge is an adapter at version `0.2.0` directly depending on
`io.github.ym0506.routecontract:routecontract-core:0.2.0`. Its generated POM declares
`compile` scope; the core SBOM component has `cdx:maven:package:test=false`.

Treat that project representation as the POM's core JAR only when the root is one of
`routecontract-shardingsphere-5.5` or `routecontract-shardingsphere-5.5.2`, the core version
matches the verified root version, and the exact core name, group and project path agree.
Third-party default-JAR dependencies still require resolved `type=jar` components.

Acceptance:

1. Both adapter roots accept the exact same-version core project edge and preserve its
   first-party compile scope and the third-party runtime closure.
2. Another core version, project path or name, or an unsupported root, remains rejected.
3. A third-party `type=pom` component cannot satisfy a POM default-JAR dependency.
4. A core component reachable only transitively cannot satisfy the direct POM dependency.
5. A runtime-scoped core POM dependency remains rejected by the existing compile-scope rule.

Use a composed existing fixture without inheriting and rerunning its test class. Establish
the positive acceptance failure before the production fix, then run
`python3 -B -m unittest discover -s scripts/tests -p test_published_core_project_inventory.py -v`.
Evidence is `verified - unit` after the focused suite passes. Rechecking retained local SBOM
copies is separate from a Java rebuild, a complete source scan, CI completion or release approval.
This change does not alter the frozen ANTLR/H2/Stax2 license decisions or publication controls.

Local verification on 2026-09-08, Python 3.12.14: both adapter cases failed before the fix;
all eight focused methods and all 127 existing policy tests pass afterward. The retained
twelve-document inventory advances past core identity checking but remains failed at runtime
closure equality. Its 5.5.2 producer graph merges compile and runtime configurations and includes
two annotation coordinates locked only to the compile classpath. That separate configuration
issue is retained for diagnosis; this change does not relax closure equality or claim a complete
inventory or exact-source scan pass.
