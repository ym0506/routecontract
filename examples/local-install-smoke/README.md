# Test the printed Gradle and Maven installation snippets

This fixture compiles and runs against an already installed, checked `v0.1.2` release.
The verifier calls the same renderer functions used by `scripts/install-local.py`,
then adds a Java 17/JUnit test harness for Gradle Groovy, Gradle Kotlin DSL and Maven.
Each consumer starts with a new dependency cache and independent project directory.

From the RouteContract source root, with Java 17 and Maven on the command path:

```bash
python3 scripts/verify-local-install-consumers.py \
  --repository /absolute/path/to/installed/.routecontract-v0.1.2 \
  --work-dir /absolute/path/to/new-consumer-check
```

The work directory must not exist. Keep it to inspect each consumer's generated build,
version output, build log and raw JUnit XML. A successful run writes `summary.json`
and reports `LOCAL_INSTALL_CONSUMERS_VERIFIED formats=3 tests=9`.

The three tests in each consumer check that:

- an unchanged approved schema-1 manifest passes the published assertion;
- the committed `1 → 2` candidate raises the expected `RCM201` and `RCM202` violation;
- the loaded RouteContract JAR has the immutable release checksum, and its POM brings
  the expected TTL and Jackson runtime dependencies without manual declarations.

The manifest inputs are copied unchanged from `examples/manifests`. This fixture does
not execute SQL or establish ShardingSphere compatibility, MySQL behavior or external
adoption. Those require the separate integration tests and actual consumer evidence.
