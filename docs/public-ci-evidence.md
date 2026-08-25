# Public CI evidence

Status date: 2026-08-11 KST

This record promotes a bounded set of local claims to revision-bound public CI evidence. It is not a stable release, an external-user result, a performance benchmark or a claim of production support.

## Immutable references

| Item | Public reference |
|---|---|
| Verified revision | [`54f1c927182f2008b1a5ff0ecedcdc36fe47f8c5`](https://github.com/ym0506/routecontract/commit/54f1c927182f2008b1a5ff0ecedcdc36fe47f8c5) |
| Main CI run | [run `31501026857`](https://github.com/ym0506/routecontract/actions/runs/31501026857) |
| Java/MySQL/SBOM job | [job `93810748190`](https://github.com/ym0506/routecontract/actions/runs/31501026857/job/93810748190) |
| Workflow source at the revision | [`.github/workflows/ci.yml`](https://github.com/ym0506/routecontract/blob/54f1c927182f2008b1a5ff0ecedcdc36fe47f8c5/.github/workflows/ci.yml) |
| First clean-run failure | [run `31500146399`](https://github.com/ym0506/routecontract/actions/runs/31500146399) |
| Public diagnosis and fix | [Issue #5](https://github.com/ym0506/routecontract/issues/5), [PR #6](https://github.com/ym0506/routecontract/pull/6) |
| PR CI including Dependency Review | [run `31500629240`](https://github.com/ym0506/routecontract/actions/runs/31500629240) |

The first bootstrap run is intentionally linked rather than hidden. A clean Ubuntu Gradle home resolved 17 plugin-classpath metadata artifacts that the initial checksum file did not cover. Issue #5 and PR #6 added only their exact SHA-256 entries; dependency verification stayed enabled. The PR then passed Dependency Review and the full build before merge.

## Commands and observed result

The main job ran the following product gate from a clean GitHub-hosted checkout:

```bash
python3 -m unittest discover -s submission/tools/tests -v
python3 -m unittest discover -s scripts/tests -v
./gradlew --no-daemon --no-build-cache clean check assemble prepareVerifiedSbom
./scripts/verify-standalone-consumer.sh
```

The downloaded JUnit artifact contains seven normal suites with `50` tests and one standalone-consumer suite with `1` test. Both sets have `0` failures, `0` errors and `0` skips. The normal suite includes real ShardingSphere-JDBC 5.5.3 tests against digest-pinned MySQL 8.4.11; the standalone suite publishes the library into an isolated temporary Maven repository, auto-discovers its SPI provider from the JAR and performs one real MySQL capture.

The runner evidence records:

- Git revision `54f1c927182f2008b1a5ff0ecedcdc36fe47f8c5`
- GitHub runner image `ubuntu24`, image version `20260720.247.2`
- Temurin OpenJDK `17.0.19+10`
- Gradle `8.14.4`
- Docker client/server `28.0.4`
- MySQL `8.4.11` image `sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb`

## Raw artifacts and retention boundary

| Artifact | Contents | Actions artifact digest | Expiry |
|---|---|---|---|
| [test and environment evidence](https://github.com/ym0506/routecontract/actions/runs/31501026857/artifacts/9105129708) | Eight JUnit XML files plus the runner environment | `sha256:0f1942a89f438797e720f9e8f451d99535091e8671da441f531ac39fe2d4f03c` | 2026-11-09 |
| [aggregate SBOM](https://github.com/ym0506/routecontract/actions/runs/31501026857/artifacts/9105129364) | Verified CycloneDX JSON and XML | `sha256:15920eba5724df010c575cce12dfcd0bdbcac09f870e173bbff6d1cc6f2661e5` | 2026-11-09 |

These Actions artifacts have 90-day retention and are therefore development evidence, not the final archival distribution. The final `v0.1.0` release must regenerate and publish revision-bound source, JAR, POM, SBOM, sanitized supply-chain summary, test summary and checksums as permanent release assets. The raw OSV report is not a release asset.

To reproduce the 50-test summary after downloading the test artifact with GitHub CLI:

```bash
evidence_dir="$(mktemp -d)"
gh run download 31501026857 \
  --repo ym0506/routecontract \
  --name routecontract-test-evidence-54f1c927182f2008b1a5ff0ecedcdc36fe47f8c5 \
  --dir "$evidence_dir"
git show \
  54f1c927182f2008b1a5ff0ecedcdc36fe47f8c5:scripts/summarize-test-results.py \
  > "$evidence_dir/summarize-test-results-54f1c927.py"
python3 "$evidence_dir/summarize-test-results-54f1c927.py" \
  --revision 54f1c927182f2008b1a5ff0ecedcdc36fe47f8c5 \
  --results-dir "$evidence_dir/routecontract-shardingsphere-5.5/build/test-results/test" \
  --results-dir "$evidence_dir/examples/mysql/build/test-results/test" \
  --output "$evidence_dir/test-summary.txt"
```

The summarizer is intentionally read from the same historical revision. The current source tree's
planned stable `0.1.0` contract has two additional manifest-storage regression tests and therefore
expects 52 rather than 50; using its summarizer on the historical XML would correctly reject the
suite mismatch. This source-tree statement does not claim that a stable tag or Release exists.

## Claim boundary

This evidence supports the exact synchronous `PreparedStatement` and ShardingSphere-JDBC 5.5.3 scope documented in the specification. It does not prove a complete route plan, physical-table count, transaction commit, business success, arbitrary async propagation, ShardingSphere-Proxy support, a stable install path or external adoption.
