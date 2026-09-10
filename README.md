<h1 align="center">
  <img src="docs/assets/routecontract-banner.png" alt="RouteContract — Test the execution behind the result." width="900">
</h1>

<p align="center">
  <a href="https://github.com/ym0506/routecontract/actions/workflows/ci.yml?query=branch%3Amain"><img src="https://github.com/ym0506/routecontract/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://central.sonatype.com/artifact/io.github.ym0506.routecontract/routecontract-shardingsphere-5.5/0.1.3"><img src="https://img.shields.io/badge/Maven_Central-0.1.3-277DA1" alt="Maven Central 0.1.3"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache_2.0-182C38" alt="Apache License 2.0"></a>
</p>

<p align="center">
  <a href="#see-it-work">How it works</a> · <a href="#install-013">Install</a> · <a href="#usage">Usage</a> · <a href="#documentation">Documentation</a> · <a href="README.ko.md">한국어</a>
</p>

**Add checks for database execution to your ShardingSphere-JDBC tests.**

RouteContract is a Java library for integration tests that use [Apache ShardingSphere-JDBC](https://github.com/apache/shardingsphere). Wrap one repository or service
call, keep the assertion on its returned value, and also assert how many JDBC execution attempts
it should make and which configured data sources it should use.

For example, a query can still return the right order after a SQL change starts querying a second
data source. The result assertion passes; the added execution assertion fails. Your normal
JUnit/Maven/Gradle test run then fails in CI as well.

## See it work

The included test asks for the paid orders of user `3`. Both query forms return the same
complete order: **order 201, user 3, status PAID**. The example's sharding rules send equality
to one data source, while a range visits both configured data sources.

| Query predicate and bound values | Returned order | JDBC execution attempts | Data sources observed |
| --- | --- | --- | --- |
| `user_id = ?` with `3` | `201 / 3 / PAID` | 1 | 1 |
| `user_id BETWEEN ? AND ?` with `3, 3` | `201 / 3 / PAID` | 2 | 2 |

The test allows **at most one execution attempt and one data source**. A *budget* is this
allowed maximum. The range query exceeds both limits, so its report says:

| Report entry | Meaning in this example |
| --- | --- |
| `POLICY_VIOLATION` | At least one allowed limit was exceeded; the contract assertion fails. |
| `RCM201` | **Too many JDBC execution attempts:** observed 2, allowed 1. |
| `RCM202` | **Too many distinct data sources:** observed 2, allowed 1. The report counts their non-sensitive aliases. |

Check the changed query and sharding rules before deciding whether the extra work is intended.
An intentional change needs a reviewed expectation; a larger count alone does not prove a
performance problem. These are `SQLExecutionHook`-reported attempts, not physical-table counts
or a complete routing plan.

![Same order returned; execution attempts and observed data sources rise from one to two, exceeding the test's limits.](docs/assets/execution-comparison.svg)

[Run this example](#quick-start) · [Read the report without installing anything](docs/evidence/ci-review-report-example.md) ·
[Inspect the query](examples/first-project/src/test/java/io/github/ym0506/routecontract/examples/firstproject/OrderRepository.java)

**A reported upstream defect:** [INSERT SELECT can return “1 row affected” while
writing to the shadow database](experiments/shadow-insert-select/README.md).
The released-5.5.3 MySQL reproduction shows why checking the expected data-source
name matters even when the result and execution count stay equal. It credits the
original reporter and includes both control cases and the failing contract command.

## Install 0.1.3

For an existing **Java 17 or 21 · ShardingSphere-JDBC 5.5.3** test project.
Supported operations are **synchronous, non-batch `PreparedStatement`** calls.

**Gradle** — Groovy or Kotlin DSL:

```kotlin
repositories { mavenCentral() }

dependencies {
    testImplementation("io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.3")
}
```

<details>
<summary><strong>Maven</strong> — add to your pom.xml dependencies</summary>

```xml
<dependency>
  <groupId>io.github.ym0506.routecontract</groupId>
  <artifactId>routecontract-shardingsphere-5.5</artifactId>
  <version>0.1.3</version>
  <scope>test</scope>
</dependency>
```

</details>

Keep your existing ShardingSphere and data-source configuration. Every ShardingSphere module
in the test runtime must be **exactly 5.5.3**; RouteContract does not supply ShardingSphere or
align its dependency graph. No repository clone or local installer is needed for this dependency.

<a id="smallest-usage-example"></a>
<a id="가장-작은-사용-예"></a>

## Usage

Wrap one operation in an existing integration test:

```java
import io.github.ym0506.routecontract.RouteAssertions;
import io.github.ym0506.routecontract.RouteContract;
import io.github.ym0506.routecontract.RouteSnapshot;

import static org.junit.jupiter.api.Assertions.assertEquals;

RouteSnapshot snapshot = RouteContract.capture("orders.find-by-user-id", () -> {
    Order actual = orderRepository.findByUserId(3L);
    assertEquals(201L, actual.id()); // Keep the business-result assertion.
});

RouteAssertions.assertThat(snapshot)
        .hasCompleteCapture()
        .hasNoReportedExecutionFailures()
        .hasExactlyObservedPhysicalAttempts(1)
        .observesExactlyDataSourceNames("ds_1");
```

`Order` and `orderRepository` stand for your existing test fixture. The operation must use the
supported JDBC execution scope; adapt the operation, expected result, data-source name and
budget to your fixture. A hook callback returning does not prove a transaction committed.

These Java assertions check the observation directly. The runnable example also writes a report
and compares the current execution with a reviewed JSON file, as described next.

<a id="approved-manifests-and-structural-manifest-diffs"></a>

### Review a baseline, then check it in CI

A **manifest** is a JSON file containing the observed execution, data-source aliases and limits.
The **candidate** describes this run; the **baseline** is the reviewed file used as the expectation.

1. Capture a representative operation and write a **candidate manifest**.
2. Review its observations, non-sensitive data-source aliases and budgets in version control.
3. Approve the baseline explicitly. Compare subsequent candidates against that baseline in CI.

Candidates never approve themselves. Intentional changes need a new review.
Follow [one project from Central install to a failing CI check](docs/first-project.md),
with runnable Maven and Gradle examples.
The [manifest example](docs/reference-guide.md#approved-manifests-and-structural-manifest-diffs)
shows the Java API; [CI review reports](docs/ci-review-report.md) add Markdown or JSON output
with stable diagnostic codes and investigation steps.

<a id="quick-start"></a>

## Try an example

Use **Java 17 or 21, Maven 3.9.x and a running Docker engine**. The first run downloads dependencies
and the MySQL image. The example uses **released 0.1.3 from Maven Central** and already includes
a reviewed expectation file for its synthetic data.

```bash
git clone https://github.com/ym0506/routecontract.git
cd routecontract/examples/first-project
mvn -B test
```

Expect a passing test and `MATCH` in `build/routecontract/review.md`: the returned order and
observed execution agree with the example's expectation. Now change the query:

```bash
mvn -B test -Droutecontract.query=range
```

**This test should fail.** The order assertion still passes, but execution attempts and data
sources both increase from 1 to 2. Open `build/routecontract/review.md` to see the two exceeded
limits (`RCM201` and `RCM202`, explained above). A download, compiler or Docker error is a setup
failure, not this expected rejection.

Run `mvn -B test` again to restore the original query and get `MATCH`. Each run replaces the
example's generated report, so read the failing report before restoring the query.

[Gradle commands and applying it to your own test](docs/first-project.md) ·
[Run the same MySQL demo in GitHub Actions](docs/first-project.md#try-in-your-browser)

## Supported scope

| Area | Published v0.1.3 |
| --- | --- |
| Java | 17 and 21; [runtime verification](docs/java21-runtime-acceptance.md) |
| ShardingSphere | JDBC, **exactly 5.5.3** |
| Execution | Synchronous, non-batch `PreparedStatement` operations that return normally, without caller interruption |
| Database verification | MySQL 8.4.11; [published Gradle and Maven consumer evidence](docs/evidence/release-0.1.3-central.md) |
| Checks | Capture completeness, callback outcomes, attempt/data-source budgets, structural manifest differences |
| CI output | Java assertions, deterministic Markdown/JSON reports, `ManifestReviewCli` |

Proxy, batch, reactive execution, application-owned async propagation and SQL Federation
coverage are outside this release's scope. Operations with no observed SQL, callback failures
or caller interruption cannot establish a passing contract. See the
[full capture boundary](docs/reference-guide.md#v01-support-boundary).

**Project status:** v0.1.3 is published on Maven Central. The
[0.2 core/adapter split](https://github.com/ym0506/routecontract/pull/62) is in development;
5.5.2 support is unreleased. Published consumer checks are maintainer-run evidence.
Independent integration and repeat use have not yet been verified.

## Documentation

| Topic | Guide |
| --- | --- |
| Find your next step | [Start here](docs/start-here.md) |
| Apply the released library to one project | [First project](docs/first-project.md) · [한국어](docs/first-project.ko.md) |
| API, policies and detailed reproduction | [Detailed guide](docs/reference-guide.md) · [한국어 상세 가이드](docs/reference-guide.ko.md) |
| Review failures in CI | [Report guide and CLI](docs/ci-review-report.md) · [Example report](docs/evidence/ci-review-report-example.md) |
| Understand what is observed | [Architecture](docs/architecture.md) · [Specification](docs/specification.md) |
| Compare with existing tools | [Tool comparison](docs/competitive-analysis.md) · [Measured datasource-proxy fixture](docs/empirical-comparison.md) |
| Inspect observer cost | [Public 0.1.3: three conditions, raw measurements and limitations](docs/observer-cost.md) |
| Examine application code | [Three evaluations: destination changes, query budgets and existing tests](docs/application-evaluations.md) · [한국어](docs/application-evaluations.ko.md) · Author-run experiments |
| Inspect release evidence | [v0.1.3 Central verification](docs/evidence/release-0.1.3-central.md) · [Evidence matrix](docs/evidence-matrix.md) |
| Explore earlier integration tooling | [v0.1.2 integration guide](docs/first-integration.md) — pinned historical workflow |
| Contribute | [Contributing](CONTRIBUTING.md) · [Roadmap](docs/product-roadmap.md) |

### Data handling

Snapshots and manifests omit raw SQL, bind values, connection properties and exception
messages. Operation IDs, type names, data-source names and SQL fingerprints can still contain
sensitive engineering information; fingerprints are not anonymization. Use non-sensitive
aliases and synthetic test inputs. Read [SECURITY.md](SECURITY.md) before sharing evidence.

## Help shape the next release

Using ShardingSphere-JDBC? [Tell us your version and how you test SQL or configuration changes](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml).
A short description of a missing check or installation blocker is useful; no installation or
public repository is required to start the conversation. Keep private SQL, bind values,
connection details and full logs out of public issues.

For a reproducible bug, use the [issue forms](https://github.com/ym0506/routecontract/issues/new/choose)
with a minimal synthetic fixture. See [how we record use and feedback](docs/user-feedback.md).

## License

[Apache License 2.0](LICENSE). [Third-party notices](THIRD_PARTY.md) ·
[Prior-work disclosure](ORIGIN_AND_PRIOR_WORK.md) · [AI-assistance disclosure](AI_ASSISTANCE.md).

RouteContract is an independent project, not affiliated with or endorsed by the Apache Software
Foundation. Apache and Apache ShardingSphere are trademarks of the Apache Software Foundation.
