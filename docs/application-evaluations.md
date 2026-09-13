# Application evaluations

[한국어](application-evaluations.ko.md) · [Try the released demo](first-project.md#try-in-your-browser)

**Which execution changes can a passing business test miss?** These experiments use
code from three public projects to examine that question with RouteContract 0.1.3.
They were prepared and run by the RouteContract maintainer with synthetic data.
They are not customer stories, maintainer endorsements or independently completed integrations.

| Question | Experiment | Observation |
| --- | --- | --- |
| Can the destination change while the result and counts stay equal? | [Egon-COLA routing configuration](#same-count-different-data-source) | 1 attempt and 1 alias in every case; the observed alias changes. |
| Can two mapper queries return the same entity with different execution budgets? | [SCG order queries](#same-order-different-query-budgets) | 1 attempt / 1 alias versus 8 attempts / 8 aliases. |
| Can capture be added to an existing application test? | [CityPulse order lookup](#capture-inside-an-existing-test) | One patched integration test passes; its final lookup reports 2 attempts / 1 alias. |

Here, an **attempt** means a physical JDBC execution attempt reported by
ShardingSphere's `SQLExecutionHook`. An alias identifies an observed data-source name.
Neither count measures physical tables, network round trips, transaction commits or latency.

The released support boundary remains **Java 17, exactly ShardingSphere-JDBC 5.5.3,
synchronous non-batch `PreparedStatement` operations**. The Java 21 and PostgreSQL
results below describe the specific evaluated paths and dependency graphs.
They do not establish general support for those environments.

## Same count, different data source

**Egon-COLA · `verified - ShardingSphere-JDBC 5.5.3` · PostgreSQL synthetic experiment**

The [pinned Light template](https://github.com/AllenDEricDAlexander/Egon-COLA/tree/61c9fbc2bd38f199d7355662a75d2113f02c6586/egon-cola-archetypes/source-projects/egon-cola-source-light)
maps tenant slots to database and table nodes. The experiment uses its two routing
classes and rule template unchanged. The query, minimal schema and test rows are
authored fixtures; the same complete row is deliberately placed in both possible
destinations so result equality cannot reveal the destination change.

| Configuration | Business row | Attempts / aliases | Observed alias | Comparison with reference |
| --- | --- | --- | --- | --- |
| Reference map | Same complete row | 1 / 1 | `synthetic-left` | Reference observation |
| Reorder the map entries | Same complete row | 1 / 1 | `synthetic-left` | `MATCH` |
| Swap database assignments; retain table suffixes | Same complete row | 1 / 1 | `synthetic-right` | `DRIFT` |
| Restore the reference map | Same complete row | 1 / 1 | `synthetic-left` | `MATCH` |

The SQL fingerprint and parameter-type shape also remain equal. All captures are
complete, with no reported callback failures or unknown outcomes. Count-only checks
pass all four configurations. An expected-data-source assertion rejects the moved
case; structural comparison reports `RCM304` (observed data-source set changed),
`RCM301` and `RCM302` (the source-scoped attempt signature was removed and added).
Those signature findings do **not** mean the SQL fingerprint changed.

Reordering and restoring the map provide controls for the intended comparison. This
does not prove a defect in Egon-COLA or observe a real migration or tenant-data leak.
The target application, original service methods and mappers were not executed.
No application baseline was approved. The diagnostic report's “Baseline” column is
the synthetic reference observation, not an approval by the target maintainer.

**Inspect or reproduce:** [pinned test, preparation helper and evidence](https://gist.github.com/ym0506/392bd5f05419225876c93f1a6c98c578/538e306ea8027836598de432510f2a8002c3f499#file-readme-md)
· [actual drift report](https://gist.github.com/ym0506/392bd5f05419225876c93f1a6c98c578/538e306ea8027836598de432510f2a8002c3f499#file-moved-review-md).
The helper fetches three pinned source files and checks their hashes before preparing
a new directory. The bundle does not redistribute those upstream files; their
original license applies.

Recorded environment: Homebrew OpenJDK 21.0.11, Maven 3.9.14, ShardingSphere-JDBC
5.5.3, pgJDBC 42.7.13, PostgreSQL 17.11, macOS/aarch64 host and a digest-pinned
PostgreSQL container. One JUnit test covers the four configurations. It passed once
in the original harness and once through the portable helper, each with an initially
empty Maven cache. Both runs had zero failures, errors or skips; all 12 observation
and review output files were byte-identical. These are two author executions of one
test, not two independent validations.

## Same order, different query budgets

**SCG · `verified - MySQL` · `verified - ShardingSphere-JDBC 5.5.3`**

The [pinned SCG project](https://github.com/leoli5695/scg-dynamic-admin/tree/a6ecc490160707722b7f4478354901318f809ea3)
contains two order queries: `selectByUserAndSeckill` and `selectByOrderNo`. The
experiment executes the original mapper, entity and ShardingSphere configuration
unchanged through MyBatis, using a separate evaluation POM and synthetic schema.
Fresh sessions ensure the queries reach JDBC instead of being satisfied by the
first-level session cache.

| Query | Business result | Observed attempts | Observed aliases |
| --- | --- | --- | --- |
| User and activity | Same complete order entity | 1 | 1 |
| Order number | Same complete order entity | 8 | 8 |

Both captures are complete, with no reported callback failures or unknown outcomes.
A single-attempt or single-data-source budget rejects the order-number query. That
does not establish that this query should have either budget: the application owner
must decide which execution behavior is required for each operation.

These are **two existing queries**, not a regression attributed to a real commit.
The setup uses one MySQL server with eight schemas and 16 order tables per schema;
eight observed attempts do not mean eight servers or an eightfold slowdown. The full
Spring application and its dependency graph were not built or started.

**Inspect or reproduce:** [pinned test, local-checkout preparation helper and evidence](https://gist.github.com/ym0506/d1a9b9c5612ab2bf906fcf386e1381b0/22006f31050ee84ef717c1b013550d84d2ab0676#file-readme-md).
The helper requires a local target checkout, verifies the three Java files and
license, and leaves that checkout unchanged. The bundle does not redistribute SCG
source; follow the target's evaluation and distribution conditions.

Recorded environment: Homebrew OpenJDK 21.0.11, Maven 3.9.14, ShardingSphere-JDBC
5.5.3, MyBatis 3.5.15, MyBatis-Plus core 3.5.5 and digest-pinned MySQL 8.4.11.
One JUnit test passed in the original harness and again through the portable helper,
each with zero failures, errors or skips. No baseline was approved.

## Capture inside an existing test

**CityPulse · `verified - MySQL` · `verified - ShardingSphere-JDBC 5.5.3`**

A two-file patch adds the public test dependency and capture around the final order
lookup in an existing integration test at
[CityPulse revision `dccffc7a`](https://github.com/rexqd/citypulse-platform/tree/dccffc7a33965868a4b55ff9aae60bb831d76bad).
All 204 application and 77 test source files compiled. One selected patched test ran
against isolated synthetic MySQL and Redis services and passed without being skipped,
preserving its existing business assertions.

The final lookup reports **2 physical JDBC execution attempts across 1 observed
data-source alias**, with complete capture and no reported execution failures. No
budget, approved baseline or regression-failure demonstration was established.
Capture covers that lookup, not the earlier payment writes or transaction commit.
The full test suite and the unpatched original method were not separately run.

**Inspect or reproduce:** [experiment and exact runtime](evidence/citypulse-isolated-pilot-2026-09-08.md)
· [patch and recorded-command guide](evidence/citypulse-isolated-pilot-reproduction-2026-09-08.md).
The runtime used Temurin 17.0.17, Maven 3.9.11, Spring Boot 3.2.12,
ShardingSphere-JDBC 5.5.3, MySQL 8.4.11 and Redis 7.4.2. The guide requires an already
prepared isolated environment; it is not a one-command installer.

## Choose a contract for your operation

Keep the business-result assertion. Use the execution property that matters for the
operation: a budget when fan-out matters, or expected aliases and structural
comparison when counts alone cannot express the requirement. Review intentional
changes before approving a new baseline; a difference by itself does not prove a bug.

[Try the browser demonstration](first-project.md#try-in-your-browser),
[apply 0.1.3 to one existing test](first-project.md), or
[ask about a version or missing check](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml).
No installation is needed to ask about fit. See [how use and feedback are recorded](user-feedback.md)
for the distinction between an author experiment, a project integration and repeat use.
