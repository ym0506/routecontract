# Isolated Maven pilot fixture

This internal fixture exercises the narrow reference Maven path intended for adaptation in
external repositories. It is a
two-module reactor with a normal business test and an inactive
`routecontract-pilot` profile. With the profile absent, the local RouteContract repository,
dependency, pilot source, Jackson/Calcite/minidev convergence, and graph exclusions are all
inactive; the default test sources do not contain the pilot, its class is not compiled, and the
candidate and provider are absent. The verifier checks that boundary in Maven's generated effective
POM as well as in the source POM and resolved tree. With the profile active, a consumer cache that
began absent and was seeded by a profile-off reactor install—while the exact RouteContract
coordinate remained absent—must resolve the exact installed JAR and POM through
`checksumPolicy=fail`, run one ShardingSphere-JDBC 5.5.3/MySQL 8.4.11 operation, preserve the
business assertion, and write a candidate. Maven may also download ordinary plugins and project
dependencies during the seed.

The verifier deliberately exercises two outcomes:

1. the first opt-in run writes a candidate and fails only because no human-approved baseline
   exists;
2. an ephemeral test-harness copy of those exact candidate bytes is used to prove the mechanical
   candidate-match path.

The second step is test scaffolding, not human approval. This fixture, its synthetic baseline copy,
and maintainer-run CI are not external-user or adoption evidence.

Run it from the RouteContract repository root with Java 17, exact Apache Maven 3.9.14, Python
3.10 or newer, Docker, `curl`, and network access:

```bash
./scripts/verify-maven-pilot.sh
```

The external integration guide must continue to require a person to review and approve a real
repository's candidate. Never reuse this fixture's candidate, alias, policy, or synthetic copy as
another repository's baseline.
