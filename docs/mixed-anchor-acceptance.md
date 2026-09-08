# A-09 manual mixed-anchor acceptance

Status: the complete manual 14-case matrix is verified on newly reviewed `86a0be5` staging;
the original `4e06694` execution remains FAILED. Whole-group resolver evidence remains separate. This gate retains the ADR's exact
`RC_MIXED_SHARDINGSPHERE_RUNTIME` requirement; an unavailable class is retained in the cell, and a different stable
marker is a failed mixed cell, not an excuse to omit that cell. Whole-group resolver
rejection is separate A-24 evidence, and this runner does not prove arbitrary manual
non-anchor compatibility, SQL behavior, or a public release.

## Verified candidate result

The [2026-09-08 result](evidence/mixed-anchor-final-candidate-2026-09-08.md) and its
[minimized receipt](evidence/mixed-anchor-final-candidate-2026-09-08.json) retain all 14 final observations.
Source `86a0be5d2e444f3b73925122fa448d9d1a324edd`, reviewed receipt
`1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e`, and frozen runner
`3ad510a0af972231fbd074607936ee52be3cad1f` identify this new candidate run.
All 12 mixed cells reject with the required top-level marker before action entry;
both clean no-SQL controls return the exact incomplete snapshot. Independent raw/input
review found zero discrepancies. Six cells still retain the expected later official
anchor-load failures after the correct capture rejection.

This result completes the finite manual matrix only. It keeps `fullA09Acceptance: false`
until separate whole-group resolver and other required evidence is considered. The original
failed summary and its reviewed `4e06694` receipt are unchanged. This acceptance copy was
updated after execution; the raw result retains the original execution-time document hash.

## Frozen scope

Use the reviewed unsigned 0.2.0 core and adapters with unmodified official Apache
ShardingSphere 5.5.2 and 5.5.3 JARs. Resolve each clean graph through the existing strict
standalone consumer, then manually replace only the executor, SPI and database-owner JARs.
The selected adapter follows the database-owner ABI. Keep all six non-uniform binary
version tuples, each with the complete three-anchor JAR sequence in forward and reversed
physical classpath order (12 negatives), plus one clean no-SQL capture per adapter
(2 controls). Every launch uses a new JVM on Java 17. There is no runtime JDK/workload
cross-product and no additional product build.

| Executor | SPI | Database owner | Adapter | Expected anchor feasibility |
| --- | --- | --- | --- | --- |
| 5.5.2 | 5.5.2 | 5.5.3 | 5.5.3 | Required ShardingSphereSPI absent |
| 5.5.2 | 5.5.3 | 5.5.2 | 5.5.2 | All three audited classes loadable |
| 5.5.2 | 5.5.3 | 5.5.3 | 5.5.3 | All three audited classes loadable |
| 5.5.3 | 5.5.2 | 5.5.2 | 5.5.2 | Executor's ShardingSphereSPI superinterface absent |
| 5.5.3 | 5.5.2 | 5.5.3 | 5.5.3 | Executor's ShardingSphereSPI superinterface absent |
| 5.5.3 | 5.5.3 | 5.5.2 | 5.5.2 | All three audited classes loadable |

These are nominal JAR-version tuples. A loadable anchor tuple is a stronger condition.
`ShardingSphereSPI` is absent from official `shardingsphere-infra-spi:5.5.2`.
The 5.5.2 adapter instead audits `ShardingSphereServiceLoader`, present in both SPI JARs.
The database owners and ConnectionProperties packages differ:

- 5.5.2: `shardingsphere-infra-database-core`,
  `org.apache.shardingsphere.infra.database.core.connector.ConnectionProperties`.
- 5.5.3: `shardingsphere-database-connector-core`,
  `org.apache.shardingsphere.database.connector.core.jdbcurl.parser.ConnectionProperties`.

The gate never fabricates an opposite-version copy of either class or relabels bytes.
It retains the expected FQCN's presence or absence and the actual JVM load failure.

## Required observations

The current public `api.RouteContract.capture` is the first product call. Its action only
increments a sentinel; mixed inputs must fail before this action, with the original
`RC_MIXED_SHARDINGSPHERE_RUNTIME:` prefix in the public capture exception's top-level message and a real
adapter guard frame. Raw linkage failures, another marker, empty successful capture,
missing output or changed classpath bytes fail. Anchor reflection occurs after the
capture attempt, so evidence collection cannot initialize the tested runtime first.
An unavailable anchor is retained as evidence. It does not itself fail a mixed cell when
a real guard has already produced the exact required diagnostic before action entry;
requiring an impossible official class to load would add an unrelated acceptance condition.

For both clean controls, the sentinel runs once and capture returns schema 2, INCOMPLETE,
zero physical attempts and `RC_NO_START_CALLBACK_OBSERVED` with all four runtime-identity
components exactly matching the expected identity, and the derived `supported` property
strictly equal to boolean `true`.
All input JAR paths, hashes, manifest versions, expected class resources and observed
loaded class origins are recorded. Reverse-order cells retain the same three selected
anchor payloads and reverse that complete sequence. No duplicate-version anchor remains
in the rest of the selected base graph.

The runner checks the externally provided receipt digest and production-source binding
before and after execution, and records fixture/class/JAR hashes, commands, logs and
observations. A partial run, preparation-only run, failed cell or repeated process ID
cannot establish the full 14-cell manual matrix. Even a passing manual matrix leaves
whole-group resolver and other release evidence separate.

```sh
python3 scripts/verify-mixed-anchor-consumer.py \
  --repository /path/to/reviewed/repository \
  --staged-receipt /path/to/reviewed-staged-receipt.json \
  --expected-staged-receipt-sha256 REVIEWED_SHA256 \
  --staged-source-revision REVIEWED_PRODUCTION_REVISION \
  --java-home /path/to/jdk17 \
  --gradle-distribution-zip /path/to/gradle-8.14.4-bin.zip \
  --evidence-directory /new/absolute/evidence-directory
```

`--prepare-only` stops after strict graph resolution, fixture compilation and launch-plan
recording. `--case` is diagnostic only; it never produces complete manual-matrix evidence.

## Observed failure and correction acceptance

The first full 14-cell execution against reviewed `4e06694` staging retains its original
status FAILED (6/14), bound by raw summary SHA-256
`8fa55131e2aba991cbfa37af0e02235cd1a189ec652b962f65c025c55ff5d25e`.
Six mixed cells satisfy the required marker. Three nominal mixed tuples in both orders
fail the diagnostic contract while still blocking action entry: E552/S552/D553 reports
UNSUPPORTED, and E553/S552 with either database owner includes a linkage cause beneath
CLASSLOADER_MISMATCH. Two clean observations additionally expose a harness-only schema
mismatch: direct Jackson serialization includes the derived `supported: true` property.
The strict classifier correction must require that boolean alongside all four identity
fields, not omit identity validation. The original execution is never rewritten.

The product correction must classify the actual mixed resource/JAR versions before core
links the hook ABI. An adapter-local passive phase must preserve legacy/dual descriptor
precedence, avoid service-loader recursion and collector access, and retain all later
loaded-origin/loader/module/ABI checks. Fresh source regression probes first reproduce
the three actual failing tuples in both orders. The final packaged run above uses newly
reviewed candidate bytes; its result is separate from the retained original staged failure.

The added passive phase currently reads three JAR manifests in each `verifyRuntime()`
call, including the registry verification performed for each capture. Constructors are
empty. This cost is unmeasured; no new cache or performance claim is included.

The public API correction must also preserve a direct top-level guard diagnosis. A
constructor-only passive phase nested the correct code beneath CLASSLOADER_MISMATCH;
that development observation is retained separately. Fresh source regressions require
`getMessage()` to start with MIXED for the six original failures and UNSUPPORTED for
both whole-runtime wrong pairs. Correct codes nested under a wrong public code fail.
