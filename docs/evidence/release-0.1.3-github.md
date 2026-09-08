# v0.1.3 GitHub release verification

Verified on 2026-09-07 UTC. [GitHub v0.1.3](https://github.com/ym0506/routecontract/releases/tag/v0.1.3)
is a published, immutable, non-prerelease release. Maven Central publication was pending
at this September 7 verification; this record does not establish Central installation or external project use.
See the separate [September 8 Central publication and consumer evidence](release-0.1.3-central.md).

## Source and release files

- Annotated tag: `v0.1.3`, object `e65484c2fb50b8e73235acca9a4daed27a9e703a`.
- Source commit: [`f1efd71e32078dd5812268a1ad24ee73110ff61f`](https://github.com/ym0506/routecontract/tree/f1efd71e32078dd5812268a1ad24ee73110ff61f).
- Source tree: `64b7a9d955fb684b3fbe57c825153f3475d0c723`.
- Successful tagged [release workflow 34122514785, attempt 1](https://github.com/ym0506/routecontract/actions/runs/34122514785).
- [Release API](https://api.github.com/repos/ym0506/routecontract/releases/384084222):
  `draft=false`, `prerelease=false`, `immutable=true`; twelve attached assets.
- [`SHA256SUMS`](https://github.com/ym0506/routecontract/releases/download/v0.1.3/SHA256SUMS)
  SHA-256: `a5db817d6851675c6de1e9cd889cae78abe0aaa0df623e776e21150175a4a49e`.
- Main JAR SHA-256: `9e883e618eb09d9ecf30814151bb4b0a43eba02c78d288cc582fa7e57e6edba2`.

Both original Actions artifact ZIPs matched the API digests and exact 17-file release
evidence / 6-file unsigned Central candidate inventories. The three JARs and POM
were identical across those artifacts. All four Gradle metadata file references
matched their JAR sizes and hashes. Source archive members and modes, source JAR
Java files, and LICENSE/NOTICE contents matched the tagged source.

The draft's twelve uploaded files were downloaded and compared before publication.
After publication, all twelve were downloaded anonymously and matched the reviewed
bytes again. The repository's GitHub CLI safety preflight passed with `gh 2.97.0`;
`gh release verify` and `gh release verify-asset` for all twelve files succeeded.
These are GitHub release attestations; no protected-key Central artifact signature
or Maven Central availability is claimed by this record.

## Runtime and supply-chain evidence

**verified - MySQL; verified - ShardingSphere-JDBC 5.5.3.** The tagged workflow used
Linux x86_64, Temurin 17.0.20.1+1 and Gradle 8.14.4. Its revision-bound
[`test-summary.txt`](https://github.com/ym0506/routecontract/releases/download/v0.1.3/test-summary.txt)
records 62 passing source tests, with zero failures, errors or skips. A separate
standalone MySQL consumer passed against the final installed v0.1.3 JAR/POM.
The summary and workflow logs support these results; raw JUnit files are not part
of the seventeen-file release artifact.

The six generated CycloneDX documents passed validation. The pinned OSV check
covered 154 Maven packages and reported zero vulnerability findings or exceptions
at its recorded snapshot. Exactly one existing test-container MySQL OCI license
manual review remains open, expiring on 2026-12-05. The sanitized
[`supply-chain-evidence.json`](https://github.com/ym0506/routecontract/releases/download/v0.1.3/supply-chain-evidence.json)
binds the source, policy and database snapshot; it is not a container OS scan or
a claim that the outstanding license review is complete.

Support remains Java 17, exact ShardingSphere-JDBC 5.5.3 and synchronous non-batch
`PreparedStatement` operations. The library observes `SQLExecutionHook`-reported
physical JDBC execution attempts; retain business assertions and baseline review.

## Released report example

**verified - unit.** On 2026-09-08 KST, the documented
[report commands](../ci-review-report.md#try-the-released-report-without-docker) were
run from a new v0.1.3 clone with a new Gradle user home, macOS arm64 OpenJDK 17.0.15
and Gradle 8.14.4. HEAD and the annotated tag matched the identities above.
The Markdown and JSON non-match commands exited 1 and produced bytes identical
to the checked-in report previews. Comparing the approved fixture with itself
exited 0 and produced `MATCH`. Docker was not invoked. This is a source-fixture
report check, not a new MySQL experiment, Central install or external integration.
