# Production-system adoption runbook

RouteContract is a test and integration-test CI guard for applications that embed Apache
ShardingSphere-JDBC. It is not a production daemon, an agent, an APM service, or a complete route
planner. A production team uses it to exercise a representative application operation in an
isolated test lane, compare the observed execution structure with a human-approved baseline, and
make the candidate assertion a required CI check.

This runbook describes operational adoption. It does not expand the support claims in the tagged
Release, [specification](specification.md), or [first-integration guide](first-integration.md).

## Release and support matrix

| RouteContract line | ShardingSphere-JDBC runtime | Status | Operational decision |
| --- | --- | --- | --- |
| immutable `v0.1.2` | exactly `5.5.3` | Released; verified with Java 17 and MySQL 8.4.11 in the documented synchronous boundary | Recommended released line for an isolated pilot. Use the pinned GitHub Release assets and the exact `0.1.2` guide; Maven Central publication is not claimed. |
| local `0.2.0` work | exactly `5.5.3` | Core/thin-adapter split, real-MySQL tests, split-consumer fixtures, and three-coordinate Central staging have passed local verification; unreleased | Do not treat local verification, a staged repository, or a signed test bundle as a supported Release. Public CI, immutable publication, and anonymous post-publication readback are still required. |
| local `0.2.0` work | exactly `5.5.2` | Exact-version adapter, real-MySQL tests, wrong-runtime and dual-adapter rejection, split-consumer fixtures, and three-coordinate Central staging have passed local verification; unreleased | Unsupported until the same revision passes public CI, is published immutably, and passes anonymous post-publication verification. |
| any other version or mixed graph | any | Unsupported | Stop; do not infer patch-line compatibility or suppress preflight failures. |

The proposed `0.2.0` layout and its required gates are recorded in
[versioned-shardingsphere-adapters.md](versioned-shardingsphere-adapters.md). That ADR is not a
release or support statement and does not modify the meaning of `v0.1.2`.

## Admission checklist

Adopt only when all of these are true:

- the RouteContract artifact, ShardingSphere runtime, Java version, build lane, and database match
  a documented supported combination;
- the target is an existing deterministic integration test around one normal-returning,
  non-interrupted, synchronous, non-batch `PreparedStatement` operation;
- the test already has a business-result assertion that remains in place;
- an authorized owner or maintainer of the consuming repository owns the baseline decision;
- RouteContract and its adapter are test-scoped and isolated from the shipped application runtime;
- the team can retain the approved baseline in reviewable version control and run a candidate check
  on every relevant change;
- the team accepts that the manifest is internal engineering metadata, not anonymized data.

Stop before integration for ShardingSphere-Proxy, batch, reactive execution, application `@Async`
propagation, SQL Federation coverage, automatic topology discovery, module-path/plugin-container or
shaded-classloader arrangements, zero-SQL certification, an unsupported database, or an
unsupported/mixed ShardingSphere graph. A stable diagnostic in an unsupported topology does not
make that topology supported.

## Smallest rollout

1. **Pin and isolate.** Pin one immutable RouteContract Release and one exact ShardingSphere
   runtime. Use the installation and build lane in the
   [first-integration guide](first-integration.md); do not add the adapter to the production runtime
   or every test suite initially.
2. **Select one representative operation.** Prefer a high-value operation with deterministic
   routing, a stable synthetic fixture, and an existing business assertion. Give it a static,
   non-sensitive operation ID.
3. **Create a candidate only.** Capture the operation and write a candidate under `build/` or
   `target/`. Do not create, overwrite, or update an approved baseline automatically.
4. **Review the first baseline.** An authorized consuming-repository maintainer reviews the exact
   operation ID, policy and budgets, aliases, counts, outcomes, parameter type shape, SQL
   fingerprints, build diff, and candidate bytes. Approval occurs through that repository's normal
   human review process.
5. **Require the candidate check.** Commit the separately approved baseline, rerun the unchanged
   representative operation, and require the RouteContract assertion in upstream CI. A business
   assertion and the route assertion must both pass.
6. **Expand slowly.** Add another operation only after the first check is stable and its owner can
   explain how to review an intentional manifest change. Do not mass-generate baselines.

## Day-two operation

For every mismatch, classify it before changing the baseline:

- **unexpected:** revert or fix the application, SQL, sharding rule, dependency, or test change;
- **intentional:** review the minimized diff and budgets, then approve the exact replacement in a
  separate human-reviewed change;
- **incomplete/unsupported:** stop the lane and diagnose preflight, callback, interruption,
  classpath, or version evidence; never convert it into a passing baseline;
- **flaky:** remove the check from required status while investigating, but do not auto-approve
  alternating candidates or weaken the policy merely to make CI green.

RouteContract findings are review signals. A change from one attempt/data source to two is not by
itself a performance defect, and a `MATCH` does not prove transaction commit, business success,
complete route coverage, or acceptable latency.

## Rollback and removal

Rollback is consumer-controlled and must not mutate a published RouteContract tag or Release.

1. Revert the consuming integration change or make the RouteContract job non-required.
2. Remove the RouteContract adapter and core artifacts from the test runtime classpath; do not leave
   a stale `SQLExecutionHook` service provider behind.
3. Run the original business integration test and inspect the resolved graph to confirm that no
   RouteContract provider remains.
4. Preserve the last candidate, approved baseline, CI URL, and failure classification as internal
   review evidence. Archive or delete them later under the consuming repository's own retention
   policy; RouteContract does not own that decision.
5. If removal follows a wrong-version, provider, or classloader failure, do not retry with another
   adapter until the exact graph is supported and verified.

## Privacy and threat boundary

The canonical manifest omits raw SQL, bind values, connection properties, exception messages,
timestamps, UUIDs, and thread IDs. It still contains clear-text operation IDs, caller-reviewed
data-source aliases, unsalted SQL SHA-256 fingerprints, parameter counts and Java type names,
callback outcomes, multiplicities, counts, and policy values. These fields can reveal operation or
topology information and a low-entropy SQL fingerprint can be guessed.

- Use synthetic, deterministic fixtures without confidential inline literals.
- Use static, non-sensitive operation IDs and aliases; never derive them from untrusted requests.
- Keep snapshots, manifests, diffs, and CI logs inside the audience authorized to see the tested
  operation and topology.
- Do not publish raw logs or production manifests as adoption evidence.
- Treat aliases as reviewed policy: remapping a new physical source to an old alias can hide drift.
- Report vulnerabilities through the private path in [SECURITY.md](../SECURITY.md).

RouteContract has no phone-home telemetry. The consuming team owns its artifacts, access controls,
retention, and incident response.

## Operational and release metrics

Record metrics locally without SQL text, bind values, customer data, hostnames, or private paths:

- candidate-check duration and its change from the pre-RouteContract test;
- complete, incomplete, reported-failure, mismatch, and match counts by static operation ID;
- intentional versus unexpected mismatch classifications;
- time from intentional mismatch to human baseline decision;
- flaky-candidate count and required-check disablements;
- exact RouteContract, adapter, ShardingSphere, Java, database, and tested commit identities.

Project release readiness is tracked separately. A supported new adapter requires exact-version
unit and real-MySQL evidence, wrong-runtime and dual-adapter rejection, Gradle and Maven consumer
verification, dependency metadata and lock review, schema/baseline migration tests, SBOM and supply
chain gates, a public immutable tag/Release, and anonymous post-publication verification. Download,
clone, view, star, local fixture, or same-maintainer CI counts are not user metrics.

## Maintenance and service level

RouteContract is a library with one public maintainer account, not a hosted service. There is no
uptime, response-time, compatibility, or security-fix SLA. Consumers must pin an immutable version,
own their baseline reviews, keep a removal path, and decide whether the check is required under
their own risk policy. Only the latest tagged `0.1.x` receives security fixes during the initial
project phase; see [SECURITY.md](../SECURITY.md) for the current policy and private reporting path.

## Evidence required to call a repository an actual user

An actual external-user result exists only when an external team or developer has, in a repository
they own or are authorized to maintain:

1. applied the RouteContract dependency to one representative operation;
2. retained the existing business assertion;
3. had an authorized human review and approve the exact baseline;
4. run the candidate assertion successfully in that repository's upstream public CI; and
5. exposed public evidence tying the dependency, operation, approved baseline, approval record,
   tested commit, and CI run together.

Consent, a draft PR, a local or fork run, Quick Start, artifact download, workflow approval, or a
self-reported comment is useful progress but is not production use, adoption, endorsement, or an
actual external-user result.
