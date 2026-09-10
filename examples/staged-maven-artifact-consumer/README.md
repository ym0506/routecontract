# Independent Maven staged-artifact MySQL consumer

Status: unreleased 0.2 local staged-byte fixture. It is not public Maven Central consumption,
a release gate completion, or adoption evidence.

## Acceptance contract

- Each exact 5.5.2/5.5.3 lane runs in a fresh external consumer directory and fresh Maven local
  repository, using Maven 3.9.14 and Java 17. No reactor, source dependency, Maven Local fallback,
  or first-party Central fallback is permitted.
- The POM requests only the selected adapter GAV. Core must resolve transitively from its published
  POM. Selected core/adapter JAR and POM hashes must match the supplied staged-byte receipt, and
  their Maven origin records must identify the controlled staging mirror.
- Maven's mirror routes first-party paths only to the supplied staging tree and all other paths
  only to the official Maven Central origin. Missing first-party paths never fall back to Central.
- The consumer-owned Enforcer 3.6.3 rules require exact whole-group ShardingSphere selection and
  prohibit the opposite adapter and pre-0.2 all-in-one artifacts. An independent dependency tree
  audit checks selected versions and the transitive core edge.
- Copy the existing StagedArtifactMySqlTest and two approved resources into the temporary consumer,
  unchanged. No source test module is linked. Both real-MySQL lanes assert the exact immutable row
  `(order_id=201,user_id=3,status=PAID)`, reviewed schema-2 MATCH, and identical business rows with
  attempts growing from 1 to 2 rejected by the candidate assertion and CLI reports with strict exit 1.
- Negative ordinary dependencies exercise wrong runtime, a wrong non-anchor while the three anchors
  remain correct, and both adapter declaration orders. Failures must name BannedDependencies;
  missing-download/network failures do not count as a policy pass.
- Preserve staged receipt, copied inputs, dependency trees, JUnit, reports, mirror requests and
  command output on failure/timeout. Empty, skipped, partial or failed test evidence never passes.
- Retain publicConsumption=false. The release workflow is not changed by this fixture.

## Run

Supply a previously reviewed coordinated staging tree containing all three 0.2.0 coordinates:

```sh
python3 scripts/verify-staged-maven-artifact-consumer.py --repository /absolute/staging --evidence-directory /absolute/new/maven-consumer-evidence --java-home /absolute/jdk17/home
```

`--maven` can select Maven 3.9.14 explicitly. Otherwise the harness uses `MAVEN_BIN` or `mvn` on PATH.
Java 17, Docker and network access for initially uncached third-party dependencies/plugins are
required. The harness never builds/uploads first-party artifacts and never writes to the supplied
staging tree. Select a new evidence directory outside the checkout and staging tree on rerun.

Python must have a working CA trust store for HTTPS Central requests. If its installation has no
default bundle, supply an existing trusted bundle with `SSL_CERT_FILE` (for example,
`/etc/ssl/cert.pem` on the verified macOS host). Certificate verification remains enabled.

This fixture does not claim that default Maven dependency mediation enforces adapter exclusivity:
the consumer-owned Enforcer policy supplies that boundary. Manual legacy classpath, offline,
corruption, public post-publication, and remaining full ADR gates are separate work.
