# RouteContract in one test

A standalone example using **RouteContract 0.1.3 from Maven Central**, **Java 17**, exact
**ShardingSphere-JDBC 5.5.3**, and two disposable **MySQL 8.4.11** containers.

[Walkthrough: capture, review, check and CI](../../docs/first-project.md) ·
[한국어](../../docs/first-project.ko.md) · [Synthetic baseline review](baselines/README.md)

Start Docker, then run one build tool from this directory:

```bash
mvn -B test
# or, using the repository's Gradle wrapper:
../../gradlew -p . test --rerun-tasks
```

The example has its own build settings. Neither command builds RouteContract from the repository
sources. If you copy this directory to another repository, use that repository's Gradle wrapper
or an installed Gradle 8.14.4; Maven needs no parent project.

The test preserves the exact expected business row and checks against a reviewed synthetic
baseline. Expect **MATCH** in `build/routecontract/review.md` and `review.json`.

| Action | Maven option | Gradle option |
| --- | --- | --- |
| Capture an unapproved candidate | `-Droutecontract.mode=capture` | `-ProutecontractMode=capture` |
| Use another reviewed baseline | `-Droutecontract.baseline=baselines/first-review.approved.json` | `-ProutecontractBaseline=baselines/first-review.approved.json` |
| Demonstrate the intentional failing query | `-Droutecontract.query=range` | `-ProutecontractQuery=range` |

Check mode and the equality query are the defaults. Capture writes only
`build/routecontract/candidate.json`; it never approves or updates a baseline. Follow the
[review step](../../docs/first-project.md#capture-and-review-your-first-baseline) before creating one.
Check mode writes the candidate and both reports, then fails the ordinary test if it does not match.
Every invocation observes a fresh database operation; consecutive Gradle runs do not reuse cached
or up-to-date test results. Known prior candidate/report files are removed when JUnit starts, before database setup.
A dependency or compiler failure happens earlier; do not read an old report as that run's result.

The `range` variant uses `BETWEEN 3 AND 3` instead of `= 3`. The exact business row still matches,
but the configured inline sharding algorithm allows range queries across both data sources:
**1 → 2 hook-reported physical JDBC execution attempts**, **POLICY_VIOLATION**, **RCM201/RCM202**.
That build is supposed to fail. A dependency, Docker or compilation error is not this demonstration.

## Adapt the test

- [OrderContractTest.java](src/test/java/example/OrderContractTest.java) shows the integration:
  capture the return value, keep the business assertion, write a candidate, render reports, assert match.
- [OrderRepository.java](src/test/java/example/OrderRepository.java) contains the equality/range query.
- [OrderFixture.java](src/test/java/example/OrderFixture.java) and
  [sharding.yaml](src/test/resources/sharding.yaml) provision this demonstration's disposable databases.
  Keep your own application's existing setup when adapting the test.

The build files include the MySQL fixture's full runtime dependencies. An existing supported
ShardingSphere application adds the RouteContract test dependency to its own build. Both runtime
graphs must use ShardingSphere 5.5.3 throughout; this example is not a version-selection framework.
The support boundary is synchronous, non-batch `PreparedStatement`. Observed attempts are not
physical-table counts, a complete route plan, transaction-commit proof or performance measurements.

The reports omit SQL text, bind values and connection properties; keep your own manifests and
full test logs within your project's normal access controls. This maintainer-owned example is a
reproducible demonstration, not evidence of an external user's adoption.
