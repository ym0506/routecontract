# Reproduce INSERT SELECT writing to the shadow database

This independent reproduction adds **released ShardingSphere-JDBC 5.5.3 + real
MySQL** evidence to [apache/shardingsphere#39750](https://github.com/apache/shardingsphere/issues/39750).
The issue and [proposed fix #39751](https://github.com/apache/shardingsphere/pull/39751)
are by **thswlsqls**. The original report targets master; this experiment does not
test that PR or claim discovery of the bug.

An affected-row assertion passes while the write goes to the wrong database.
Both operations below execute once, so an execution-count budget alone also
passes. An explicit expected data-source name detects the difference.

| Operation | Affected rows | Observed attempts | Hook-reported data source | Primary target rows | Shadow target rows |
| --- | ---: | ---: | --- | ---: | ---: |
| `INSERT VALUES`, `user_id=2` (nonmatching) | 1 | 1 | `primary` | 1 | 0 |
| `INSERT VALUES`, `user_id=1` (matching control) | 1 | 1 | `shadow` | 0 | 1 |
| `INSERT SELECT`, source `user_id=2` | 1 | 1 | `shadow` | 0 | 1 |

The configured `VALUE_MATCH` algorithm only matches inserts with `user_id=1`.
Both disposable databases contain the same one-row `t_order_backup`. Each case
starts with empty target tables. Direct JDBC reads of **both** target tables
verify the destination and synthetic row contents independently of RouteContract.

## Run

Requirements: JDK 17, Maven and a running Docker daemon. No application credentials
or existing database are used. Testcontainers creates and removes two MySQL
instances. The recorded run used Homebrew OpenJDK **17.0.15**, Maven **3.9.14**,
macOS/aarch64, and the pinned MySQL **8.4.11** image digest in the test.

From this directory:

```bash
mvn -B -ntp test
```

Expected: **3 tests, 0 failures, 0 errors, 0 skipped**. This command characterizes
the known defect: the INSERT SELECT case explicitly expects the primary-only
contract to reject the observed shadow name. A green characterization suite does
not mean ShardingSphere has been fixed.

To let that same primary-only contract fail the build:

```bash
mvn -B -ntp -Dshadow.enforceProduction=true \
  '-Dtest=ShadowInsertSelectTest#insertSelectReturnsOneButWritesToShadow' test
```

Expected: **exit 1**, **1 test, 1 failure**, with:

```text
expected observed data-source names [primary], but observed [shadow]
```

The affected-row check remains `assertEquals(1, captured.value())`. The failing
assertion is:

```java
RouteAssertions.assertThat(captured.snapshot())
        .hasExactlyObservedPhysicalAttempts(1)
        .observesExactlyDataSourceNames("primary");
```

The POM resolves released **RouteContract 0.1.3** from Maven Central; it does not
build the library from this checkout. The test checks the exact released JAR's
SHA-256 before starting the databases. Runtime logs stay in ignored `target/`;
[evidence.json](evidence.json) contains only selected versions, counts and the
expected failure, without connection details.

## What this proves

- **Verified — MySQL / ShardingSphere-JDBC 5.5.3:** the reported wrong-destination
  behavior occurs on the released version in this synthetic fixture.
- Both ordinary VALUES controls route as configured. The INSERT SELECT result is
  corroborated by direct reads, and the expected-name assertion fails the build.
- The observation is a hook-reported physical JDBC execution attempt, not a full
  route plan, transaction-commit signal or physical-table count.

This is one local verification of a small synchronous, non-batch
`PreparedStatement` fixture. It does not establish production impact, Proxy
behavior, arbitrary shadow configurations, the correctness of PR #39751, or
external adoption of RouteContract. Direct database assertions are also useful;
this example does not claim the defect can only be detected with RouteContract.

The SINGLE rule uses the logical `shadow_group` name. Shadow algorithm names are
explicit on the table, avoiding the separate YAML-default issue #39748.

Acceptance criteria: [ACCEPTANCE.md](ACCEPTANCE.md). Test implementation:
[ShadowInsertSelectTest.java](src/test/java/io/github/ym0506/routecontract/experiments/shadow/ShadowInsertSelectTest.java).

AI assistance: Codex helped prepare the fixture and this write-up. The reported
results come from the commands above; no human code-review or adoption claim is
inferred from those results.
