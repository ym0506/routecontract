# Use RouteContract in one project

[한국어](first-project.ko.md) · [Runnable example](../examples/first-project/README.md) · [Report API](ci-review-report.md)

Start with one existing test whose result matters to you. RouteContract adds a comparison of
observed physical JDBC execution attempts while keeping that test's business assertion.

This guide uses **RouteContract 0.1.3 from Maven Central**, **Java 17** and exact
**ShardingSphere-JDBC 5.5.3**. It covers synchronous, non-batch `PreparedStatement` calls.
The example needs a running Docker engine and downloads MySQL and Java dependencies on first use.
For a preview without installation, [read the report](evidence/ci-review-report-example.md).

## Run the published dependency

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

The default check uses the example's reviewed synthetic baseline. Expect a passing test and
`MATCH` in `build/routecontract/review.md` and `review.json`. The test also asserts that the query
returns exactly the expected order. See the example's baseline review record before adapting it.

The first run can take longer while dependencies and the database image download. A Docker,
dependency or compiler failure is a setup failure; it does not demonstrate contract rejection.

## Capture and review your first baseline

To rehearse first-time setup, create a candidate for a new baseline path. Choose the same build tool
as above:

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

## See a change fail

The example has a range-query variant that keeps the same exact business result while the
hook-reported physical JDBC execution attempts increase from **1 to 2**.

<details>
<summary>Maven</summary>

```bash
mvn -B test -Droutecontract.query=range \
  -Droutecontract.baseline=baselines/first-review.approved.json
```

</details>

<details>
<summary>Gradle</summary>

```bash
../../gradlew -p . test --rerun-tasks -ProutecontractQuery=range \
  -ProutecontractBaseline=baselines/first-review.approved.json
```

</details>

**This command should fail.** Open `build/routecontract/review.md`: expect `POLICY_VIOLATION`,
`RCM201` (attempt budget) and `RCM202` (observed-alias budget). The test's business assertion passes
before the contract comparison fails. The approved baseline stays unchanged.

Remove the query option and rerun the check to return to `MATCH`. These counts describe observed
attempts and aliases, not physical-table counts or a complete route plan. More attempts alone do
not establish a latency regression; investigate whether the change was intended.

## Adapt one existing test

Use the example's test as a working reference. In your existing project:

1. Add the [Central test dependency](../README.md#install-013). Keep your application's existing
   ShardingSphere and data-source setup; the test runtime must use 5.5.3 throughout the
   ShardingSphere dependency group.
2. Put one representative repository/service call inside `RouteContract.captureResult`. Assert its
   returned value before writing a candidate or comparing a contract, as the example does.
   Alternatively use `capture` and keep the business assertion inside its operation.
3. Give the operation a stable ID. Map every observed data-source name to a non-sensitive alias
   with `DataSourceAliases`, and choose `ManifestPolicy.strict` budgets for that operation.
4. Write the candidate with `ManifestStore.writeCandidate`, using separate candidate and baseline
   paths. Capture the initial candidate locally and have the project owner review it.
5. In the normal test, compare the reviewed baseline with the new candidate using
   `ManifestReviewReport.compare`. Write its Markdown/JSON output, then call
   `ManifestAssertions.assertMatched(report.verification())` so a non-match fails the build.

Only the synthetic fixture belongs in the example. Your application's test should use its own
existing setup, operation, expected result and approved baseline. The [manifest reference](reference-guide.md#approved-manifests-and-structural-manifest-diffs)
explains the API in detail.

## Keep the result beside CI

Run **check mode** in CI with the reviewed baseline committed to the repository. Capture mode is
an explicit local preparation step. Start with a clean checkout and a fresh build-output directory.

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
| Dependency resolution or compilation fails | Check Java 17 and the whole ShardingSphere runtime graph for exact 5.5.3. |
| Baseline is missing | Run capture locally, review the candidate, then create the baseline explicitly. |
| Capture has no eligible observation | Confirm that the selected operation actually reaches supported synchronous, non-batch JDBC execution. |
| `POLICY_VIOLATION` | Inspect the governing baseline budget and changed attempts/aliases before deciding whether to change the query or review a new baseline. |
| A different non-match status | Use the report's finding codes and next steps. Do not accept the candidate automatically. |

Tell us your version, build tool, stage reached and the short error code in the
[feedback form](https://github.com/ym0506/routecontract/issues/new?template=stable-feedback.yml).
Keep private SQL, bind values, connection details and full logs in your own environment.
An unsuccessful attempt is useful feedback too.

After a successful integration, try the check on your next real SQL or configuration change.
Tell us whether the result helped, was confusing, or led you to remove the check. Running this
example is a demonstration; use in your own project and later reuse are recorded separately in
the [feedback guide](user-feedback.md#recording-use-and-evidence).
