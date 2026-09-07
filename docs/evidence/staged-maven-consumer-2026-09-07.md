# Independent Maven staged-byte MySQL acceptance — 2026-09-07

Evidence label: **verified — MySQL** for the supplied local staged `0.2.0` bytes.
Public Maven Central availability, external adoption, and the complete release matrix remain
unverified. This fixture does not remove the `0.2.x` public-consumer release blocker.

## Scope and result

The independent Maven fixture requests only the selected adapter GAV and obtains core transitively
from that adapter's staged POM. Each runtime gets a fresh external consumer directory and a fresh
Maven local repository. The existing `StagedArtifactMySqlTest` and approved schema-2 resources are
copied into that directory unchanged; no reactor, source project, or composite is attached.

| Exact ShardingSphere runtime | MySQL tests | Failures / errors / skips | Selected ShardingSphere components | Ordinary negative graphs |
| --- | ---: | --- | ---: | ---: |
| 5.5.2 | 3 | 0 / 0 / 0 | 122, all 5.5.2 | 4 rejected |
| 5.5.3 | 3 | 0 / 0 / 0 | 75, all 5.5.3 | 4 rejected |

Each positive lane verifies the loaded core and unique hook provider JAR hashes against the
staged receipt. Both business queries must return exactly the immutable row
`(order_id=201,user_id=3,status=PAID)`. The equality capture matches the existing reviewed schema-2
baseline. The range candidate preserves that same row while increasing physical JDBC execution
attempts from 1 to 2; the candidate assertion rejects it, and JSON/Markdown CLI reports return
strict exit 1 with `POLICY_VIOLATION`, `RCM201`, and `RCM202`. This is evidence about
SQLExecutionHook-reported execution attempts, not a complete route plan, transaction commit,
business success in a deployment, or performance.

All eight negative cases use ordinary POM dependencies: wrong runtime, wrong non-anchor with all
three expected anchors still selected correctly, and both adapter declaration orders. Retained
dependency trees prove the bad selection. Every rejection names the offending GAV and
`BannedDependencies`; missing downloads or another build failure do not count as a policy pass.
The Maven policy is consumer-owned Enforcer 3.6.3, as required by the adapter ADR. Default Maven
mediation alone is not claimed to enforce adapter exclusivity.

Maven mirrors all repository IDs to a local group-aware HTTP endpoint. First-party paths are served
only from supplied staging; all other requests use HTTPS `repo.maven.apache.org/maven2/`, with
certificate verification, no inherited proxy credentials, and restricted redirects. The resolved
core and adapter JAR/POM hashes and `_remote.repositories` records are independently checked.
This establishes local staged-byte consumption, not public publisher provenance.

## Reproduction and retained evidence

The implementation was based on source `0f0a0caab3d6c3176d0e8c5eb8731e16f96054a0`.
The successful real-MySQL execution used the POM and copied Java/resources committed with this
note. A subsequent input-precondition change rejects evidence directories inside the source
checkout; its regression test passed without repeating unchanged production behavior.

```sh
SSL_CERT_FILE=/etc/ssl/cert.pem python3 scripts/verify-staged-maven-artifact-consumer.py --repository /private/tmp/routecontract-staged-consumer-008e125/repository --evidence-directory /private/tmp/routecontract-staged-maven-evidence-initial-tls --java-home /opt/homebrew/Cellar/openjdk@17/17.0.15/libexec/openjdk.jdk/Contents/Home
python3 -m unittest discover -s scripts/tests -p '*staged*maven*.py' -v
```

Results: harness exit 0, 6 MySQL tests and 8 negative graphs; 21 focused Python tests passed.
The Python tests cover mirror isolation, traversal/symlinks, redirect and transfer bounds,
transitive core, whole-group versions, ordinary declaration orders, origin/hash mismatch, missing
download rejection, and retained evidence after a lane timeout.

Host: macOS 26.4.1 arm64, Python 3.13, Maven 3.9.14
(`996c630dbc656c76214ce58821dcc58be960875b`), Homebrew Java 17.0.15, Docker 29.2.1.
MySQL 8.4.11 uses the pinned multi-platform digest
`b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb`.
The local `docker image inspect --platform linux/arm64` reports platform manifest/image ID
`c9be23757267a888182ff13a633118a84ce7ad360abaa0f12a9c357ddf628b61`.

Raw evidence is retained outside the checkout at
`/private/tmp/routecontract-staged-maven-evidence-initial-tls/`:

- `summary.json`, `toolchain.log`, `staged-receipt.json`, `controlled-settings.xml`, and
  `repository-requests.jsonl`.
- `<runtime>/junit/TEST-io.github.ym0506.routecontract.consumer.StagedArtifactMySqlTest.xml`.
- `<runtime>/maven.log`, `resolved-graph.json`, `consumer-pom.xml`, and unchanged `inputs/src/`.
- `<runtime>/reports/<runtime>/` contains baseline, candidate and both CLI report formats.
- `<runtime>/resolved-first-party/` retains downloaded JAR/POM files and Maven origin records.
- `<runtime>/<negative-case>/` contains ordinary POM requests, selected graph, and rejection log.

The 9-payload staged receipt exactly matches the previously reviewed Gradle consumer receipt in
`/private/tmp/routecontract-staged-consumer-008e125/evidence-final/staged-receipt.json`.
Its JSON file SHA-256 is `ff4ad23aca357baa0a29f6ddac3a8b3708f1dbe62e0a73f200f84737449fdb41`.

| Staged JAR | SHA-256 |
| --- | --- |
| core | `def89f37cf6b4eab02e593bddf77b493c8d52e7b7e66c8ef8f830dc0c67664e8` |
| adapter 5.5.2 | `752090d09ac287c5a21c2118b9c79f4077efc72a7d624b72ed5690303fdf2c18` |
| adapter 5.5.3 | `6d139b136e714cb3dfd033aa47dfcbfedffd3e87f6f5aaa2c7762975a714f64e` |

An earlier attempt in `/private/tmp/routecontract-staged-maven-evidence-initial/` failed before
dependency resolution because the host Python installation had no default CA bundle. Its logs,
receipt and incomplete summary remain preserved. The successful fresh-cache run used the existing
macOS trust bundle explicitly; certificate verification was not disabled.

## Remaining boundary

The new Maven fixture is a local staged acceptance path. Public unauthenticated Central byte
readback and public consumers for both exact runtimes remain separate requirements: implement and
review their verifiers before upload, then execute them after publication before claiming Central
availability. Ordinary CI invokes this harness against its coordinated staging files and uploads
minimized summaries, dependency graphs and reports. Raw local logs/JUnit are not included in that
new artifact. This fixture does not cover legacy physical-classpath cases, offline or corruption
matrices, the full route-risk corpus, or a Central account workflow. Its implementation changes no
production library code or existing baseline, and the release guard remains in place.
