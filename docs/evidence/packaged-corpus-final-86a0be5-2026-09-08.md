# Existing MySQL corpus on final packaged JARs

**Verified on 2026-09-08:** all 28 existing MySQL tests passed against the reviewed
unsigned local 0.2.0 candidate. This completes the final packaged runtime binding
for this fixed corpus. `humanReview: null`, `fullA23Complete: false`, and
`publicConsumption: false` remain unchanged.

The [machine-readable evidence](packaged-corpus-final-86a0be5-2026-09-08.json)
retains exact JUnit method identities, source/input hashes, artifact inventories,
per-suite provenance hashes and output bindings without raw SQL, parameters,
connection details, local paths or process identities.

## Actual execution

The existing six suites and all original golden assertions ran unchanged. Two
standalone Gradle 8.14.4 consumers executed sequentially on Java 17.0.15, each
with an initially absent dependency cache and copied inputs. The run completed
once, with exit 0 and full output received; no retry was needed.

| ShardingSphere | Original suites | Existing tests | Failures / errors / skips | Compile modules / artifacts | Runtime modules / artifacts |
| --- | ---: | ---: | --- | --- | --- |
| 5.5.3 | 4 | 14 | 0 / 0 / 0 | 108 / 105 | 150 / 146 |
| 5.5.2 | 2 | 14 | 0 / 0 / 0 | 182 / 179 | 207 / 203 |

The exact 28 method names are listed in JSON; no extra or supplemental test
cases count toward this total. All existing business-result, safe-control,
route-risk, failure/ineligibility, secret-minimization and versioned golden
assertions remained enabled, including the 5.5.3 datasource-proxy comparison.
Each runtime's existing eight-shape × 20-repetition check and 20 concurrently
open caller-capture pairs passed. Those loops belong to the original tests;
they are not added JUnit cases. Physical callback overlap was neither forced
nor measured.

## Packaged source and runtime binding

- Reviewed production source: `86a0be5d2e444f3b73925122fa448d9d1a324edd`.
- Consumer checkout: `3ad510a0af972231fbd074607936ee52be3cad1f`.
- Unchanged original corpus source: `9184de3cb9d0e71bf5b9a07fa180e9c31a220d98`.
- Independently supplied receipt SHA-256: `1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e`.
- Pinned Gradle distribution SHA-256: `f1771298a70f6db5a29daf62378c4e18a17fc33c9ba6b14362e0cdf40610380d`.

| Actual runtime artifact | SHA-256 |
| --- | --- |
| `routecontract-core:0.2.0` | `9115e1f6e96bece66d29045e3550fc72aa15a217ee82f3289598a9bc693e32ac` |
| `routecontract-shardingsphere-5.5:0.2.0` | `e48e67b2ce2c5d75d60d6794fe93c34d34697daff810a7b1f9c977095c5a02e5` |
| `routecontract-shardingsphere-5.5.2:0.2.0` | `d5e73f86004fc5a00ebdf3069440d16f8eaf2e033e8b57a7d096ace26630fbe4` |

A supplemental JUnit extension recorded provenance before and after each
original suite inside its actual test JVM: 12 class-level observations across
six suites. It verified the current `io.github.ym0506.routecontract.api.RouteContract`
entry, core, selected adapter/hook and provider descriptors against the reviewed
JARs. It added zero cases and did not instantiate another hook. Actual selected
compile/runtime graphs, strict locks, verification metadata and runtime artifact
bytes were checked; no production class directory or project dependency
substituted for the staged JARs.

The independent audit rehashed 633 selected compile/runtime artifact occurrences
and 349 runtime-classpath JAR occurrences against the retained evidence and
strict verification metadata. It also verified 27 compiled test/supplemental
class files, 39 original inputs, 16 executed fixture/helper inputs, 54 applicable
original-copy occurrences, 74 consumer inputs, nine primary staged payloads,
90 staging files and 69 production/publication source-tree entries. These are
binding counts, not additional runtime tests.

## Golden and retained-evidence checks

All 14 version-specific 5.5.2 corpus observation files matched their unchanged
source goldens byte-for-byte. Eleven generated report/demo files were retained
and checked. Generation remained disabled. The report comparisons used the
report API; this corpus run does not assert a standalone CLI invocation.

Both lanes were revalidated after the second lane finished: raw commands, logs
and exit records, exact JUnit XML, provenance, copied inputs, selected artifacts
and outputs. The final global source, fixture, original-input, receipt and
staging checks also passed. A separate read-only audit independently checked
these retained results without another build, test or JVM run.

| Retained binding | SHA-256 |
| --- | --- |
| Aggregate raw summary | `9935445605d255c364797394ab1c3ee296e4af583d42fb91d30a4a07c666ee9d` |
| 5.5.3 raw lane summary | `5c24650ade17a0afa302678a89519e9da1b355918f6610c387bcfcb4d87f60e8` |
| 5.5.2 raw lane summary | `88122894fe4b82dba8a8f77d559dce71e4ef0c240d1ce35020c6b12d0fc4f830` |
| Independent retained audit | `91fa10c8f834a4d5e7028cdd9d3d858bb6c76afb5b55613724d0dd8a7dc34ab9` |
| Independent audit script | `947a5e6d846751f03de9cedddac312f6c7e980b9959f64e6a6cc008f50707357` |

## Remaining boundary

This is local packaged-consumption evidence for synchronous, non-batch
PreparedStatement workloads and hook-reported physical JDBC execution attempts.
It does not establish a complete route plan, transaction success, arbitrary
async behavior, physical callback overlap, another JDK, offline behavior,
a public release or external adoption. The earlier `4e06694` candidate had only
preparation evidence and no full corpus execution.

Passing technical golden comparisons does not provide authentic human baseline
approval. That separate review remains pending, so the complete A-23 acceptance
claim remains false even though this packaged runtime binding passed.
