# Maven split-artifact consumer fixture

This local release-gate fixture resolves `routecontract-core:0.2.0` through exactly one exact-version
adapter from a separately staged Maven repository. It verifies both configured exact-version lanes:

- `routecontract-shardingsphere-5.5` with an all-`5.5.3` ShardingSphere graph; and
- `routecontract-shardingsphere-5.5.2` with an all-`5.5.2` ShardingSphere graph.

The consumer owns its Maven Enforcer policy because a dependency POM cannot activate Enforcer in
the consuming build and Maven POM metadata cannot express Gradle capabilities. The pinned Enforcer
3.6.3 rules require convergence, reject every lower or higher version in the entire
`org.apache.shardingsphere` group, reject the opposite RouteContract adapter, and reject selected
pre-0.2 all-in-one bytes in a 0.2 lane.

Positive `verify` runs also execute an empty compatibility capture in a fresh Maven JVM and require
the public API to come from `routecontract-core-0.2.0.jar`, the runtime provider to come from the
selected adapter JAR, and the runtime identity to match the selected exact ShardingSphere version.

The repository URL must point at a reviewed staged repository containing all three RouteContract
0.2 artifacts. For example, after creating an unsigned local staging directory with the repository's
coordinated staging task:

```text
JAVA_HOME=/absolute/jdk17 mvn --batch-mode \
  -Dmaven.repo.local=/absolute/empty-maven-cache \
  -Droutecontract.repositoryUrl=file:///absolute/routecontract-stage \
  -Proutecontract-553 clean verify
```

Replace `routecontract-553` with `routecontract-552` for the other positive lane. The release gate
must also show that `wrong-non-anchor` and `dual-adapter` fail during `validate` in both version
profiles. The two version profiles make the dual-adapter declarations appear in both effective
orders: 5.5.3 then 5.5.2, and 5.5.2 then 5.5.3.

The repository-level verifier performs the coordinated staging, exact Maven/JDK check, two
fresh-cache positive runs, staged-origin readback, and all four negative cases in one isolated
temporary directory:

```text
JAVA_HOME=/absolute/jdk17 MAVEN_BIN=/absolute/apache-maven-3.9.14/bin/mvn \
  python3 -I scripts/verify-maven-split-artifact-consumer.py
```

This is same-checkout, staged-publication evidence. It is not Maven Central consumption, an external
team's integration, a human-approved baseline, a representative business operation, or production
adoption. Those remain separate gates.
