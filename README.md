<h1 align="center">
  <img src="docs/assets/routecontract-banner.png" alt="RouteContract — Test the execution behind the result." width="900">
</h1>

<p align="center">
  <a href="https://github.com/ym0506/routecontract/actions/workflows/ci.yml?query=branch%3Amain"><img src="https://github.com/ym0506/routecontract/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://central.sonatype.com/artifact/io.github.ym0506.routecontract/routecontract-shardingsphere-5.5/0.1.3"><img src="https://img.shields.io/badge/Maven_Central-0.1.3-277DA1" alt="Maven Central 0.1.3"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache_2.0-182C38" alt="Apache License 2.0"></a>
</p>

<p align="center">
  <a href="#install-013">Install</a> · <a href="#usage">Usage</a> · <a href="#see-it-work">Demo</a> · <a href="#documentation">Documentation</a> · <a href="README.ko.md">한국어</a>
</p>

**The query result can stay the same while database execution changes.**

RouteContract is a Java test library for [Apache ShardingSphere-JDBC](https://github.com/apache/shardingsphere).
It records physical JDBC execution attempts reported by `SQLExecutionHook` and compares them
with explicit budgets and a human-reviewed baseline. Keep your existing result assertions;
add a check for changes in observed execution counts, data sources and rewritten-SQL structure.

In the included MySQL example, the same row is returned while observed attempts increase
from **1 to 2**. RouteContract catches the change in CI.

## Install 0.1.3

For an existing **Java 17 · ShardingSphere-JDBC 5.5.3** test project.
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

<a id="approved-manifests-and-structural-manifest-diffs"></a>

### Review a baseline, then check it in CI

1. Capture a representative operation and write a **candidate manifest**.
2. Review its observations, non-sensitive data-source aliases and budgets in version control.
3. Approve the baseline explicitly. Compare subsequent candidates against that baseline in CI.

Candidates never approve themselves. Intentional changes need a new review.
Follow [one project from Central install to a failing CI check](docs/first-project.md),
with runnable Maven and Gradle examples.
The [manifest example](docs/reference-guide.md#approved-manifests-and-structural-manifest-diffs)
shows the Java API; [CI review reports](docs/ci-review-report.md) add Markdown or JSON output
with stable diagnostic codes and investigation steps.

## See it work

[Watch the 2:54 demo](https://www.youtube.com/watch?v=pcgvNNxd1mM) ·
[Open the actual CI report](docs/evidence/ci-review-report-example.md)

![Illustration of the verified MySQL fixture: the same business row, physical JDBC execution attempts 1 to 2 and observed data-source aliases 1 to 2; the strict contract rejects the candidate with RCM201 and RCM202.](docs/assets/execution-comparison.svg)

This illustration summarizes the [checked-in MySQL manifests](examples/manifests/README.md).
The counts describe **hook-reported physical JDBC execution attempts and observed aliases**.
They do not measure physical tables, a complete route plan or performance.

<a id="quick-start"></a>

### Try an example

| Try it | Requirements | What to expect |
| --- | --- | --- |
| [Generate the v0.1.3 CI report](docs/ci-review-report.md#try-the-released-report-without-docker) | Git, Java 17; initial dependency downloads | Compares committed manifests; writes `POLICY_VIOLATION` with `RCM201` / `RCM202`. The example deliberately fails the check. No Docker. |
| [Reproduce the MySQL change](docs/reference-guide.md#quick-start) | Git, Java 17, Docker; initial downloads | Historical **v0.1.2** demo, pinned to its immutable tag. The wrapper succeeds after verifying the expected contract rejection. |
| [Run the v0.1.3 first-project example](docs/first-project.md) | Git, Java 17, Docker; Maven or the Gradle wrapper | Capture a candidate, review a baseline, see `MATCH`, then reproduce the same-result `1 → 2` failure. Adapt one existing test. |

## Supported scope

| Area | Published v0.1.3 |
| --- | --- |
| Java | 17 |
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
| See an application experiment | [CityPulse: one isolated test with public 0.1.3](docs/evidence/citypulse-isolated-pilot-2026-09-08.md) · Self-prepared; no maintainer adoption |
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
