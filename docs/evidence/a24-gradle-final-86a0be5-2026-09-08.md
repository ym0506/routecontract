# Gradle A-24 final-candidate consumer result

**28/28 cases passed** against reviewed unsigned RouteContract 0.2.0 source
`86a0be5d2e444f3b73925122fa448d9d1a324edd`. This was one complete run on
macOS 26.4.1 arm64, Gradle 8.14.4, Java 17.0.15, MySQL 8.4.11 and
Testcontainers 1.21.4. The process exited 0 and its full EOF was retained.

| DSL | Exact ShardingSphere-JDBC | Cases | MySQL JUnit executions | Rejections | Disabled-origin controls |
| --- | --- | ---: | ---: | ---: | ---: |
| Groovy | 5.5.2 | 7/7 | 6 | 4 | 1 |
| Groovy | 5.5.3 | 7/7 | 6 | 4 | 1 |
| Kotlin | 5.5.2 | 7/7 | 6 | 4 | 1 |
| Kotlin | 5.5.3 | 7/7 | 6 | 4 | 1 |

Each group ran online, offline, native checksum rejection, protected wrong
origin, a separate disabled-origin control, wrong anchor and wrong non-anchor.
The eight positive phases ran **24 actual MySQL tests**, with zero failures,
errors or skips. The 16 rejection cases and four controls passed their exact
validators. No full-matrix retry or internal MySQL startup retry occurred.

The unchanged representative fixture observed the same expected business row
while hook-reported physical JDBC execution attempts increased from one to two;
its budget assertions and in-process `ManifestReviewCli.run` JSON/Markdown
regression checks detected that change. Selected and executing core/adapter JARs
matched the reviewed hashes. Every positive graph contained the exact selected
ShardingSphere version throughout its closure: 122 components for 5.5.2 and
75 for 5.5.3.

Offline replay used each group's immutable primed cache, its closed HTTP
endpoint, native offline mode, the verified exact-JDK OS egress barrier, and
actual no-pull policy invocations for fixed MySQL/Ryuk images. Native checksum
failures bound the exact core coordinate, reviewed repository, deliberately
incorrect expected SHA-256 and unchanged actual JAR hash in one failure section.
Protected origin cases made no request to the unintended endpoint; separate
controls resolved the same reviewed bytes there. Wrong-version cases retained
the actual rejected selector and causal policy result, including all three
correct anchors for the non-anchor case. Those diagnostic tasks exited 0 after
successfully recording the expected rejection; they did not run MySQL tests.

An independent final audit rechecked all 28 cases after execution: 40 major-61
classfiles, 6,026 frozen-cache files, 9,041 metadata-bound cached payload
occurrences, 140 copied-source occurrences and 660 retained evidence files.
It also checked all 23 runner inputs plus the supplementary imported helper,
69 production/publication files, the original 90 staging files and nine copied
payloads. All remained bound to the reviewed source/receipt. All 64 retained
logs were scanned without uncaught exception headers. The eight positive
phases recorded 16 MySQL starts, exactly two per phase.

Evidence labels: `verified - MySQL`, `verified - ShardingSphere-JDBC 5.5.2`,
`verified - ShardingSphere-JDBC 5.5.3`.

SHA-256 bindings:

- Raw summary: `11c06fb9b79f08b98ffb3422174df9b2d24bfe2c2873f29d41fa3b0bb37ffdf4`
- Independent retained-evidence audit: `19031ef87d89eae6f434b91dfe8c3c4726ba7ac559c66cb2aff46963197e553c`
- Reviewed staging receipt: `1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e`
- Reviewed input manifest: `f115fc28b0042e039ad807b3a0ba82c332ab96ec596a6f0919f3f853f0b83b79`
- Final external input closure: `189cb429f74664190f19573da4f132f51c4b3853c58ec62f74fdb2b08d5c40d2`

[The minimized JSON](a24-gradle-final-86a0be5-2026-09-08.json) contains the 28 exact
identities, outcomes, JAR hashes and per-case evidence digests. Raw commands,
logs, endpoint addresses, SQL/bind details and connection properties remain
private. The [earlier 4e06694 result](a24-gradle-consumer-2026-09-08.md) is
historical and contributes no executions to these totals.

This closes the existing Gradle portion on the final staged bytes.
[Maven Java 17/21 acceptance](a24-maven-final-86a0be5-2026-09-08.md) is separate;
this result establishes neither Gradle Java 21 nor broader platform support.
These are three representative methods per positive phase, distinct from the
separate full-corpus gate. The CLI checks run in process. Network isolation
covers the build/JVM descendants and fixed fixture's no-pull behavior, not
Docker daemon/container networking or unrelated local proxies. This single
local run does not establish longevity, external adoption, public 0.2
availability, or release approval. Human review of the 14 expected 5.5.2 corpus
manifests remains unrecorded (`humanReview: null`).
