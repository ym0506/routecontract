# Final-candidate A-27 resolver evidence

Evidence label: **verified — local Gradle/Maven resolver**. Executed on
2026-09-08 against the unsigned 0.2 candidate produced from
`4e066942f6e244345fe908970b81446f9e08f64e`. This records dependency resolution,
consumer policy and materialized artifact identity; it does not establish SQL
behavior, public availability or external adoption.

## Result

| Consumer | Required cases | Observed results |
| --- | --- | --- |
| Gradle 8.14.4 / Java 17 | 37/37 | 13 resolved controls/selections, 16 capability conflicts, 8 strict-version conflicts |
| Maven 3.9.14 / Java 17 | 45/45 | 13 resolved controls/selections, 24 Enforcer rejections, 8 strict-range conflicts |

Both complete runners exited 0. Expected rejection cases passed only when the
actual resolver or explicit consumer policy produced the required diagnostic.
An infrastructure failure is not a successful rejection. The retained historical
[Gradle](gradle-legacy-resolver-2026-09-08.md) and
[Maven](maven-legacy-resolver-2026-09-08.md) records remain unchanged; these new
runs use the candidate containing the new `api.RouteContract` entry.

The independently reviewed nine-payload receipt has SHA-256
`38b2269eca162f121fd3996c56df8b894ae2f43cedeb08fcc627032cf70eaa43`.
The supplied core, both exact adapters and their POM/module metadata were
rechecked after each run. The production source binding and executed fixture
hashes were unchanged. Distributed legacy inputs are the registry-bound actual
0.1.0, 0.1.2, 0.1.3 and 0.1.0-rc2 artifacts; tag-only inputs are not counted as
distributed releases.

## Reproduction and retained evidence

Use the named runners with an absent external evidence directory, the reviewed
staged repository/receipt and source revision. Both runs used Java 17.0.15+0,
CPython 3.12.14 and macOS 26.4.1 arm64, with two case workers. The Gradle
distribution was the checked-in SHA-256-pinned 8.14.4 ZIP. Review the receipt
digest independently before invoking the runners; their receipt parameter is
not a substitute for that review.

```sh
python3 scripts/verify-gradle-legacy-artifact-consumer.py \
  --repository /path/to/reviewed-staging \
  --staged-receipt /path/to/reviewed-staged-receipt.json \
  --staged-source-revision 4e066942f6e244345fe908970b81446f9e08f64e \
  --evidence-directory /path/to/absent-gradle-evidence \
  --java-home /path/to/jdk-17 \
  --gradle-distribution-zip /path/to/gradle-8.14.4-bin.zip \
  --legacy-payload-directory /path/to/verified-legacy-payloads \
  --workers 2

python3 scripts/verify-maven-legacy-artifact-consumer.py \
  --repository /path/to/reviewed-staging \
  --staged-receipt /path/to/reviewed-staged-receipt.json \
  --staged-source-revision 4e066942f6e244345fe908970b81446f9e08f64e \
  --evidence-directory /path/to/absent-maven-evidence \
  --java-home /path/to/jdk-17 \
  --maven /path/to/maven-3.9.14/bin/mvn \
  --legacy-payload-directory /path/to/verified-legacy-payloads \
  --workers 2
```

The [Gradle receipt](gradle-legacy-resolver-4e06694-2026-09-08.json) and
[Maven receipt](maven-legacy-resolver-4e06694-2026-09-08.json) retain every case,
request/order where applicable, outcome, materialized first-party hashes,
source/fixture pins and raw-result/audit digests. Exact invoked argument arrays
and environment records remain in the local execution handoff.

| Retained local artifact | SHA-256 |
| --- | --- |
| Gradle summary | `4a1e7a3a020e7cd91569dacef818e27324b9d5391df38603aa427c5eff1bc7cc` |
| Maven summary | `8ee7bfc09536136a2b2bb58b5049dee7db749b4415a35708534fe6c69796021d` |
| Gradle independent audit | `f7795ea8f1ddc92cc703460f410f23d74eeff6f543776c86165533242bcfad35` |

Local raw directories are
`/private/tmp/routecontract-a27-gradle-4e06694-final-20260908` and
`/private/tmp/routecontract-a27-maven-4e06694-final-20260908`; the combined
invocation/session record is
`/private/tmp/routecontract-a27-4e06694-final-execution-20260908.json`.
These local artifacts are not implied to be publicly downloadable.

## Interpretation

Gradle started each case with an absent dependency cache, seeded only with the
pinned wrapper distribution. First-party JARs were materialized directly from
the isolated file repository; this is not evidence of first-party HTTP delivery
or cache-only offline consumption. Maven used a controlled HTTP repository and
an absent per-case Maven cache. Its server-side Central response cache began
empty and reused only verified responses from this run.

Capability ownership rules and Maven Enforcer are explicit consumer policies.
They are not automatically installed into an arbitrary application by adding a
RouteContract dependency. Ordinary Maven equal-depth mediation follows request
order; explicit dependency management is tested separately. A-24 installation,
A-26 clean migration and A-29 runtime-collision behavior have separate scopes.
The original A-28 result remains **FAILED**.
