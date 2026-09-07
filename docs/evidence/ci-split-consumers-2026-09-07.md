# Split-consumer CI evidence, 2026-09-07

[CI 34110335880](https://github.com/ym0506/routecontract/actions/runs/34110335880)
completed successfully on attempt 1, with all five jobs passing. It tested PR
head `cd95ae6a128a26b7499afaba9ae5030235d1953c` through merge checkout
`9d6674ae573959a87bb9639f33ec97d6d787c458`. GitHub commit metadata, the checkout
log and artifact environment record agree; both commits have tree
`df62ea090f5cde1d0a76e26af74540f4095d0c83`.

The main runner used Ubuntu 24.04 amd64, Temurin 17.0.20.1+1, Gradle 8.14.4,
Maven 3.9.14 and Docker 28.0.4. This run predates the public Central verifier
implementation and does not validate that later source.

| Evidence | Observed result | Public artifact |
| --- | --- | --- |
| Core, adapters and MySQL examples | 20 raw JUnit suites, 135 tests: 107 unit/structural and 28 MySQL; zero failure/error/skip | [Main tests](https://github.com/ym0506/routecontract/actions/runs/34110335880/artifacts/10014955654) |
| Same-checkout standalone consumer | One additional raw JUnit test; zero failure/error/skip | Main tests above |
| Local staged Gradle consumers | Six raw MySQL JUnit tests and ten graph rejection cases over exact 5.5.2/5.5.3; zero failure/error/skip | [Staged Gradle](https://github.com/ym0506/routecontract/actions/runs/34110335880/artifacts/10014957290) |
| Local staged Maven consumers | Verified harness summaries report six MySQL tests and eight graph rejections; both exact-runtime graphs and MATCH/policy-rejection reports retained | [Minimized staged Maven](https://github.com/ym0506/routecontract/actions/runs/34110335880/artifacts/10014956460) |
| A-26 API migration | Six old-bytecode MySQL executions, 26 public types/167 descriptors and separate source/record/enum/codec/module probes; disclosed behavior changes remain | [Minimized A-26](https://github.com/ym0506/routecontract/actions/runs/34110335880/artifacts/10014956880) |
| Locally installed v0.1.2 configuration | Nine raw JUnit tests across Gradle Groovy/Kotlin and Maven; zero failure/error/skip. This group exercises manifest/POM consumption without SQL execution | [Installed consumers](https://github.com/ym0506/routecontract/actions/runs/34110335880/artifacts/10014956040) |

All five downloaded ZIP SHA-256 values match the artifact API digests. The
Maven and A-26 archives intentionally omit raw JUnit and rejection/probe logs;
their counts are minimized verifier summaries corroborated by successful
steps and the verifier source from this exact tree. Do not describe those two
archives as independent raw-JUnit replays.

The Python helper job discovered 599 tests: 595 passed and four documented
optional/platform checks were skipped. The full build separately validated
the twelve finalized SBOM documents. Other jobs passed the documented Kotlin,
Gradle/JDK/Boot and Maven/JDK21 assisted-pilot cells; those are separately
scoped v0.1.2 pilot evidence.

Both CI staged consumers used the same nine-payload receipt. Their three JARs
and three POMs match the earlier local 008e125 staging bytes, but all three
Gradle `.module` hashes differ. The minimized archives do not retain those
metadata bytes, so their precise difference is **unverified**. Review final
release metadata itself and derive the public-consumer receipt from its signed
bundle; do not substitute the older local receipt for the CI receipt.

Evidence labels are **verified - unit**, **verified - MySQL**, and the exact
ShardingSphere-JDBC 5.5.2/5.5.3 labels for the recorded lanes. This is local
staging consumed in public CI. It establishes neither anonymous Central
availability nor independent user adoption. Release acceptance beyond the
recorded checks remains separate.
