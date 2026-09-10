# Use RouteContract in one project

[한국어](first-project.ko.md) · [Runnable example](../examples/first-project/README.md) · [Report API](ci-review-report.md)

This is a test you run with Maven or Gradle: a query returns the correct order, but changing
its predicate makes it query an extra configured data source. RouteContract makes the added
execution assertion fail while keeping the order assertion. The example below has the database
setup and reviewed expectation file ready to use.

This guide uses **RouteContract 0.1.3 from Maven Central**, **Java 17 or 21** and exact
**ShardingSphere-JDBC 5.5.3**. It covers synchronous, non-batch `PreparedStatement` calls.
[Run locally](#run-the-published-dependency) to see pass → fail → pass, or use the browser steps below.
For a preview without running anything, [read the report](evidence/ci-review-report-example.md).

## Try in your browser

You need a GitHub account and permission to run Actions in your own fork. Java, Docker and the
build tool run on GitHub's hosted runner; **no local installation is required**.

1. [Fork RouteContract](https://github.com/ym0506/routecontract/fork) into your account.
2. In **your fork**, open **Actions**. Enable Actions if GitHub asks you to, then select
   **First project** from the workflow list.
3. Click **Run workflow**, keep the `main` branch and default **Maven**, then run it.
   You can choose **Gradle** or **Both** instead. Select Java **17** (default), **21**, or **Both**.
   If these choices are missing in an older fork, sync its main branch first.
4. Open the new run and read its **Summary** once it finishes:

   | Stage | Exact business row | Observed attempts / aliases | Contract |
   | --- | --- | --- | --- |
   | Normal query | Order 201 / user 3 / PAID | 1 / 1 | `MATCH` |
   | Same-result range query | Same row | 2 / 2 | `POLICY_VIOLATION`: 2 executions and 2 sources exceed the limits of 1 |
   | Normal query restored | Same row | 1 / 1 | `MATCH` |

   **The demonstration is green only after verifying the expected rejection and recovery.**
   The range-query test itself fails. Dependency, compiler or Docker failures cannot count as
   that rejection; an unfinished stage appears as not verified in the summary.
5. Download **first-project-Maven** or **first-project-Gradle** from the run's **Artifacts**.
   Java 21 artifacts have a **-java21** suffix.
   Under `build/lifecycle-evidence/`, `match/`, `range/` and `restored/` retain each verified
   stage's `candidate.json`, `review.json` and `review.md`. Start with `range/review.md`.

The workflow also verifies that capture cannot approve a missing baseline. It compares against
the example's existing reviewed synthetic baseline and keeps that file unchanged. This exercise
does not approve a baseline for your application. Next, [adapt one existing test](#adapt-one-existing-test).

If **Run workflow** is absent, check that you are in your own fork and that the workflow is on
its default branch. See GitHub's [manual-run instructions](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

## Run the published dependency

For local execution, install Java 17 or 21 and start Docker. The first run downloads Java dependencies
and the MySQL image.

Clone the examples, then choose **one** build tool. The example lives on the repository's main
branch and resolves the released library from Central; it does not build RouteContract from source.

```bash
git clone https://github.com/ym0506/routecontract.git
cd routecontract/examples/first-project
```

**Maven** (3.9.x):

```bash
mvn -B test
```

**Gradle** (the repository wrapper):

```bash
../../gradlew -p . test --rerun-tasks
```

Maven compiles and runs the example with the JDK selected by `JAVA_HOME`; use Java 17 or 21.
Gradle defaults to Java 17. To use an installed Java 21 JDK, add `-ProutecontractJavaVersion=21`
to **each** Gradle command in this guide, or set `ROUTECONTRACT_EXAMPLE_JAVA_VERSION=21`
for the shell session. The test verifies its actual JVM, compiled consumer class and unchanged
Central JAR. See the [runtime checks and limitations](java21-runtime-acceptance.md).

The default check uses the example's reviewed synthetic baseline. Expect a passing test and
`MATCH` in `build/routecontract/review.md` and `review.json`. The test also asserts that the query
returns exactly the expected order. See the example's baseline review record before adapting it.

The first run can take longer while dependencies and the database image download. A Docker,
dependency or compiler failure is a setup failure; it does not demonstrate contract rejection.

## See a change fail

Use the same included baseline as the passing run above. The range-query variant still returns
order `201 / 3 / PAID`, but it makes two observed JDBC execution attempts against two data
sources instead of one. Choose the same build tool:

**Maven:**

```bash
mvn -B test -Droutecontract.query=range
```

**Gradle:**

```bash
../../gradlew -p . test --rerun-tasks -ProutecontractQuery=range
```

**This command should fail.** The test first verifies the returned order, writes its report,
then fails the execution assertion. Open `build/routecontract/review.md`:

| Entry | What it means | This example |
| --- | --- | --- |
| `POLICY_VIOLATION` | An observed count exceeds an allowed maximum. | The test fails even though the order assertion passed. |
| `RCM201` | Too many hook-reported physical JDBC execution attempts. | Observed 2; baseline allows 1. |
| `RCM202` | Too many distinct observed data-source aliases. | Observed 2; baseline allows 1. |

An **alias** is a non-sensitive label for a configured data source; this fixture maps `ds_0`
to `orders-even` and `ds_1` to `orders-odd`. A **budget** is the allowed maximum. These numbers
are not counts of physical tables or proof of a performance regression.

Read the report, then rerun the original command without the query option to restore `MATCH`.
The generated report is replaced on each run; the included baseline remains unchanged.
For a real change, inspect the SQL and sharding configuration. Fix unintended extra execution,
or review an updated expectation when the change is intentional.

## Adapt one existing test

For execution-count checks, keep the expectations in your Java test. **A JSON baseline is optional.**
Add the [Central test dependency](../README.md#install-013), retain your existing ShardingSphere
setup and wrap one synchronous repository/service call. For example:

```java
var captured = RouteContract.captureResult("orders.find-paid", () -> orders.findPaidOrders("equality"));
assertEquals(expectedOrders, captured.value());
RouteAssertions.assertThat(captured.snapshot())
        .hasAtMostObservedPhysicalAttempts(1)
        .hasAtMostDistinctObservedDataSourceNames(1);
```

Import `RouteContract` and `RouteAssertions` from `io.github.ym0506.routecontract`, and
`assertEquals` from JUnit. Here `orders` and `expectedOrders` belong to your existing test;
replace the operation and expected limits with ones you have reviewed for that fixture.
The limit of one above belongs to this guide's synthetic example. These assertions reject
incomplete captures as well as counts above the limit, and failures fail the ordinary test/CI build.

Run the included example this way with either build tool:

```bash
mvn -B test -Droutecontract.mode=assert
# Or:
../../gradlew -p . test --rerun-tasks -ProutecontractMode=assert
```

Add `-Droutecontract.query=range` for Maven or `-ProutecontractQuery=range` for Gradle to see
the same order returned followed by `expected at most 1 observed physical attempts, but observed 2`.
Rerun the original command to pass again. Read the console or JUnit result in this mode: it does
not read or write a JSON baseline, candidate or review report. Any existing report belongs to a
previous run. The direct-assertion lifecycle is also checked by the First project workflow.

The two assertions above check counts only. They do not compare SQL fingerprints, parameter-type
shapes or a saved data-source set, and do not produce the manifest report's `RCM` codes.
If you need those comparisons and Markdown/JSON reports, use the baseline workflow below.
All ShardingSphere modules in the test runtime must still be exactly **5.5.3** on **Java 17 or 21**.

## Capture and review your first baseline

The default check mode uses an existing **baseline**: the reviewed JSON file that records expected
execution and allowed counts. A **candidate** records the current run. If you choose JSON
comparison for your own test, first capture a candidate and review it before establishing its baseline.
You can rehearse that process below with a new path, using the same build tool:

<details>
<summary>Maven</summary>

```bash
mvn -B test -Droutecontract.mode=capture \
  -Droutecontract.baseline=baselines/first-review.approved.json
```

</details>

<details>
<summary>Gradle</summary>

```bash
../../gradlew -p . test --rerun-tasks -ProutecontractMode=capture \
  -ProutecontractBaseline=baselines/first-review.approved.json
```

</details>

Open `build/routecontract/candidate.json`. Capture mode checks the operation and proposed budget,
but it does not compare against an approved baseline or establish a passing CI contract.

Review the candidate together with the test and sharding configuration:

- Does the operation still assert the intended business result?
- Do the observed attempts and stable data-source aliases match the intended execution?
- Are the allowed counts intentional? The example permits one attempt and one observed alias.
- Are the SQL fingerprints and parameter-type shapes expected for this operation?

For this synthetic exercise, after reviewing the candidate, explicitly create your baseline:

```bash
cp -n build/routecontract/candidate.json baselines/first-review.approved.json
```

Use a new absent destination; `cp -n` keeps an existing baseline unchanged. For your application,
review the candidate through your repository's normal process and commit the reviewed baseline
with the test. The example's baseline is valid only for its own fixture.

Now run the comparison:

<details>
<summary>Maven</summary>

```bash
mvn -B test -Droutecontract.baseline=baselines/first-review.approved.json
```

</details>

<details>
<summary>Gradle</summary>

```bash
../../gradlew -p . test --rerun-tasks \
  -ProutecontractBaseline=baselines/first-review.approved.json
```

</details>

Expect `MATCH`. If the baseline is missing, check mode must fail and leave a candidate for review.
Creating a candidate must never silently substitute for that review.

### Connect JSON comparison to your test

Use [OrderContractTest](../examples/first-project/src/test/java/io/github/ym0506/routecontract/examples/firstproject/OrderContractTest.java)
as a working reference for the optional saved comparison:

1. Keep the operation and returned-value assertion from your test. Map every observed data-source
   name to a non-sensitive alias
   with `DataSourceAliases`, and choose `ManifestPolicy.strict` budgets for that operation.
2. Write the candidate with `ManifestStore.writeCandidate`, using separate candidate and baseline
   paths. Capture the initial candidate locally and have the project owner review it.
3. In the normal test, compare the reviewed baseline with the new candidate using
   `ManifestReviewReport.compare`. Write its Markdown/JSON output, then call
   `ManifestAssertions.assertMatched(report.verification())` so a non-match fails the build.

Only the synthetic fixture belongs in the example. Your application's test should use its own
existing setup, operation, expected result and approved baseline. The [manifest reference](reference-guide.md#approved-manifests-and-structural-manifest-diffs)
explains the API in detail.

## Keep the result beside CI

For JSON comparison, run **check mode** in CI with the reviewed baseline committed to the repository.
Capture mode is an explicit local preparation step. Start with a clean checkout and a fresh build-output directory.

After your ordinary test step, use an always-running step to display a report if it was produced:

```yaml
- name: Show RouteContract review
  if: always()
  shell: bash
  run: |
    report=examples/first-project/build/routecontract/review.md
    if test -f "$report"; then
      cat "$report" >> "$GITHUB_STEP_SUMMARY"
    fi
```

Adapt the path to your test module. Keep the test step's nonzero exit; do not add
`continue-on-error` to the application check. Save the candidate and report with your existing
CI artifact policy. [CI review reports](ci-review-report.md#ci-use) explains the output and
[the first-project workflow](../.github/workflows/first-project.yml) exercises the public example.

## When you get stuck

| What you see | Next step |
| --- | --- |
| Docker cannot start | Start the Docker engine and confirm your normal Testcontainers test works. |
| Dependency resolution or compilation fails | Check Java 17 or 21 and the whole ShardingSphere runtime graph for exact 5.5.3. |
| Baseline is missing | Run capture locally, review the candidate, then create the baseline explicitly. |
| Capture has no eligible observation | Confirm that the selected operation actually reaches supported synchronous, non-batch JDBC execution. |
| `RCM201` / `RCM202` | Execution attempts / distinct data sources exceed the baseline limit. Compare actual and allowed counts, then inspect the SQL and sharding rules. |
| A different non-match status | Use the report's finding codes and next steps. Do not accept the candidate automatically. |

Tell us your version, build tool, stage reached and the short error code in the
[feedback form](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml).
Keep private SQL, bind values, connection details and full logs in your own environment.
An unsuccessful attempt is useful feedback too.

After a successful integration, try the check on your next real SQL or configuration change.
Tell us whether the result helped, was confusing, or led you to remove the check. Running this
example is a demonstration; use in your own project and later reuse are recorded separately in
the [feedback guide](user-feedback.md#recording-use-and-evidence).
