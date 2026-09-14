# Six dependency corrections: source verification

The retained local diagnostic reported **six findings across 318 Maven packages**. This correction repairs the exact ShardingSphere-JDBC 5.5.2 dependency graph while preserving the 5.5.3 policy and existing expected behavior. The subsequent clean-revision scan found **zero findings in the exact 306-package inventory**, using the pinned advisory database. This is a point-in-time result for that graph.

| Previous dependency | Reviewed correction | Primary source |
| --- | --- | --- |
| protobuf-java 3.21.9 | 4.31.1 in 552 compile/runtime; runtime already used 4.31.1 | [Maintainer advisory](https://github.com/protocolbuffers/protobuf/security/advisories/GHSA-735f-pc8j-v9w8) |
| commons-lang 2.4 | aggdesigner 6.0 → 6.1 migrates its usages to Lang3, coordinated with Calcite 1.42 | [Apache advisory](https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/2025/48xxx/CVE-2025-48924.json), [producer history](https://github.com/julianhyde/aggdesigner/blob/main/HISTORY.md) |
| json-smart 2.5.0 | 2.5.2, with accessors-smart 2.5.2 | [Publisher release](https://github.com/netplex/json-smart-v2/releases/tag/2.5.2) |
| calcite-core 1.38.0 | core/linq4j 1.42.0 and Avatica core/metrics 1.28.0 | [Apache advisory](https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/2026/46xxx/CVE-2026-46718.json) |
| commons-lang3 3.15.0 | 3.18.0 | [Apache advisory](https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/2025/48xxx/CVE-2025-48924.json) |
| httpcore5 5.2.3 | 5.4.3 | [Apache advisory](https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/2026/54xxx/CVE-2026-54399.json) |

**Publication boundary.** The 552 adapter now declares Lang3 directly in its generated POM and Gradle runtime metadata. The other repairs are constraints in the full JDBC fixtures. The thin adapter does not supply a complete dependency policy for arbitrary applications. No new exclusions, scanner allowances, HTTP client or HTTP/2 dependencies were introduced. Each graph has its own reviewed lock: source 552 selects commons-logging 1.3.5, while the external 552 fixture retains its strict 1.2 selection.

**Executed evidence — `verified - unit`, `verified - MySQL`, `verified - ShardingSphere-JDBC 5.5.2`.** Java 17.0.15 and Gradle 8.14.4, with strict dependency verification, passed all 31 adapter tests and 14 unchanged MySQL tests: 45 methods across 8 suites, with no failures, errors or skips. The original eight-shape × 20 repetitions and 20 capture-pair loop ran; this does not claim callback overlap. Both new publication tests failed meaningfully before the repair and passed afterward. All 14 corpus goldens, two operation manifests and 21 retained generated outputs were audited. All 28 original corpus methods remain unchanged; the 553 methods were not rerun for this correction.

Six actual SBOM pairs passed inventory checks for 306 Maven packages, and all 12 documents passed official CycloneDX validation. Independent review checked 17 new payload pins against publisher files and checksum sidecars, complete source/external locks, and the strict source graph. Compared with the reviewed acquisition graph, strict resolution preserved all artifact lists and added only expected lock constraints.

**Execution versus integration.** These results came from a frozen modified working tree based on `e43585ec2de21676942f9339f891d21d75f03029`, with 14 changed files bound by snapshot SHA-256 `58f7927410831451e7c3ee0cfba17b57a5c3f30cfd2aecf78ddd182d3670d104`. They were not executed as clean `5fdfc3d` or `cef11a1` checkouts. Exact dependency files were subsequently integrated at `5fdfc3dcd3f4190e4c2b9e381b0b096169b387bb`. The corpus fingerprint update was integrated at `cef11a11284d95b7bca9c16f97db5ded11bc64e0`: only its source revision and two reviewed build/lock fingerprints changed; 37 other input pins stayed unchanged. The later scan executed successfully from that clean revision, independently of the earlier working-tree source tests.

**Clean-revision scan.** Local Homebrew Java 17 execution on `cef11a1` completed with exit 0 and full EOF. All 12 SBOM documents passed official validation; three published POM/lock pairs passed the policy checks; the 306 scanned packages exactly matched the inventory. All six previous vulnerable coordinates are absent. OSV-Scanner 2.5.0 used Maven database generation `1788523358826365` with an empty explicit configuration: zero findings and zero accepted vulnerability exceptions. The existing single license-review exception remains recorded under unchanged policy. Source and tool pins stayed unchanged. The retained inventory is a labeled canonical reconstruction matching the runner's hash, because its temporary original was intentionally removed. This was local verification, not Temurin CI or release preparation.

**Repeat the checks.** From a clean checkout of `cef11a11284d95b7bca9c16f97db5ded11bc64e0`, use Java 17.0.15 and the Gradle 8.14.4 wrapper. Docker must be running for the MySQL tests. Replaying these named source tasks verifies the integrated inputs; it does not recreate the original modified working-tree execution.

```bash
./gradlew --no-daemon --no-build-cache --console=plain \
  --dependency-verification=strict --max-workers=2 \
  :routecontract-shardingsphere-5.5.2:test :mysql-5.5.2-example:test

bash scripts/run-final-supply-chain-scan.sh \
  --revision cef11a11284d95b7bca9c16f97db5ded11bc64e0
```

Earlier failed attempts remain retained: a diagnostic directory-hashing error, synthetic SBOM fixture adjustments, and a missing POM trust record discovered before task execution. Each cause was diagnosed before correction; strict verification was preserved.

The [companion JSON](six-dependency-correction-2026-09-08.json) binds the hashes and independent reviews. This evidence does not establish corrected packaged consumption, a new stage or consumer matrix, public 0.2 availability, user adoption, SQL Federation coverage, offline/no-pull behavior or release approval. Historical 86 results remain unchanged, and `humanReview` remains `null`.
