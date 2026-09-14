# Runtime and installation checks for the integrated 0.2 candidate

A developer adding RouteContract needs both a working installation and a clear
failure when the installed adapter cannot observe the application's runtime.
These checks exercise the existing supported combinations and deliberate invalid
combinations against the same candidate artifacts.

Producer: `5800ed2960aefbf63c01d2ebaf2265278d662494`. Consumer checkout:
`efcfbb4ca30ad8dd1531f97c654068c36bb8410a`, with matching production/publication
inputs. Receipt SHA-256:
`9a4d745ff11508a8ab08dd8bced6a7893d8f6e6ff5baab34b3445aea652ba49c`.
The [minimized record](current-runtime-and-installation-5800ed2-2026-09-14.json)
contains case identities, outcomes and retained-evidence hashes. No first-party
artifact, business fixture or expected observation was rebuilt or changed by
these runs.

## Completed native executions

| Existing gate | Executed scope | Result |
| --- | --- | --- |
| A-01–A-08, A-10, A-18, A-19 | Runtime boundary: 28 cases | 4 controls and 24 specified rejections passed |
| A-09 manual matrix | Six mixed anchor tuples in both orders, plus two clean controls | 14/14 passed |
| A-11–A-13 | Provider discovery, cached provider after TCCL change, separate core loader | 6/6 passed |
| A-24 Gradle | Groovy/Kotlin × exact 5.5.2/5.5.3 × seven cases, Java 17 | 28/28 passed; 24 MySQL JUnit executions, 16 rejections and 4 origin controls |

Environment: local macOS 26.4.1 arm64, Temurin 17.0.20.1+1, Gradle 9.7.1,
exact ShardingSphere-JDBC 5.5.2 and 5.5.3, and MySQL 8.4.11 where the case
executes SQL. The MySQL image is pinned to
`sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb`.
Each finite runtime matrix ran once and exited 0. The qualifying Gradle matrix
is the fourth complete-plan invocation, with the original frozen input manifest
explicitly supplied; the preceding attempts are distinguished below.

### Runtime observations

The matching runtime boundary cases preserve the ordinary SQL → capture →
ordinary SQL → capture sequence. All four operations return the fixed business
row and each capture contains only its own operation. Core-only controls execute
ordinary SQL, then reject capture without an adapter. Wrong adapters, two adapters
and unsupported module-path combinations retain the required pre-action or
pre-business-SQL diagnosis.

All twelve manual mixed-anchor cases report the top-level
`RC_MIXED_SHARDINGSPHERE_RUNTIME` marker. Official anchor classes that cannot load
in a tuple remain recorded as unavailable; no synthetic class substitutes or
omitted tuples make the matrix pass. The two clean controls intentionally do not
execute SQL and return incomplete captures. This completes the finite manual
A-09 matrix only, not arbitrary manual classpath compatibility.

The two cached-provider/TCCL-change lifecycle controls execute real MySQL, return
the fixed row and observe one physical JDBC execution attempt. Hidden initial
provider discovery and separate-core-loader cases reject before action entry.
Full terminated lifecycle logs were checked for uncaught shutdown errors.
Boundary and mixed-anchor records expose 42 distinct JVM PIDs; the lifecycle
records establish six separate native invocations without exposing PIDs. These
are not a claim of 48 observed unique PIDs.

### Gradle installation observations

Each DSL/runtime pair executes online, offline, wrong checksum, protected wrong
origin, a separate disabled-origin control, wrong anchor and wrong non-anchor.
The eight online/offline phases run three MySQL tests each with zero failures,
errors or skips. They return the same order when observed execution grows from
one attempt to two; both in-process CLI report formats return regression code 1.

Offline execution uses a copy of its own frozen successful prime cache. The
prime HTTP endpoint is closed and connection refusal is verified. Actual Java
17 probes verify OS denial of external egress while allowing loopback and the
local Docker socket. Fixed MySQL/Ryuk images use the fixture's no-pull policy.
This boundary does not control Docker daemon/container networking or unrelated
loopback proxies.

Checksum failures name the actual core JAR, reviewed repository, deliberately
incorrect expected pin and correct actual hash in one native failure section.
Protected wrong-origin cases make no request to the unintended endpoint;
separate controls resolve the unchanged bytes there. Wrong-version diagnostics
record the actual policy rejection and complete their reports without compiling
or executing the MySQL fixture. Their diagnostic process exits 0 after validating
the expected rejection; it is not successful resolution of the invalid graph.

A post-run read-only audit rehashed 7,464 frozen-cache files, 88 command/log/request
records, 23 fixture inputs and all nine receipt artifacts, and checked 40
major-61 consumer classfiles, all eight JUnit XML files and minimized reports.
The runtime audit separately checked 138 case-file hashes. These audits did not
rerun the consumers and do not constitute human baseline approval.

Two prior Gradle attempts remain failed: the first reached its checksum case
but could not resolve Maven Central DNS; the second stopped downloading Calcite
1.42.0. Neither is counted in the 28-case result or treated as an intended policy
rejection. Before the third attempt, the exact Calcite JAR was downloaded twice
using Java 17 and matched its pinned SHA-256. No verification policy, expected
observation or timeout was weakened. Recovery did not retroactively pass either
failed attempt.

The third invocation completed all 28 cases, but omitted the explicit
`--expected-input-manifest` option required for repeat acceptance. Its native
result remains PASS and its repeat protocol remains incomplete. All four
23-input manifests are identical, with SHA-256
`d67aabcbeea01a2dbcc2f270b5c97720c7db679dce7f42044a0db121affa11d2`.
The fourth invocation supplied that original manifest, completed all 28 cases
and exited 0. Only this invocation supplies the qualifying counts and audit
above; its summary SHA-256 is
`f83ac47cd0287e955eb1ccaafae2273cc0bf8192d84cd32d72edc9bb35c1d4a3`.

The [separate current Maven result](a24-maven-5800ed2-2026-09-14.md) covers
Java 17/21 × both exact runtimes. Together these records cover the existing local
A-24 build-tool profiles on the same nine-artifact receipt. Gradle Java 21 is not
part of this result.

## Artifact content and retained manifest unit evidence

A read-only JAR check found 44 core classes and nine classes in each adapter.
The adapter class-path intersections are empty. None of the three JARs contains
`module-info.class`; each adapter has exactly one hook provider and one core
adapter provider. Java 17 `jdeps -verbose:class` found no ShardingSphere class
dependency from core.

Every production class in those JARs equals the retained tested producer
checkout's compiled class bytes. That checkout's original JUnit XML records
606 manifest runtime compatibility cases and 22 observed-manifest cases passing
with no failures, errors or skips. This is retained unit execution plus compiled
byte equality, **not a new execution of 628 packaged tests**. Schema/API migration
has its [own current evidence](public-api-migration-5800ed2-2026-09-14.md).

## Reproduction and limits

Use consumer revision `efcfbb4ca30ad8dd1531f97c654068c36bb8410a`, the candidate
repository and receipt above, the retained expected-input manifest for Gradle
A-24, an absent output directory per command, and Java 17. Replace private
paths below with those verified inputs. The Gradle 9.7.1 distribution SHA-256 is
`acd53f1edaf02f1a8ff99879f8a34b302661a057d9b063ae9e35b552f804d20a`.

```sh
python3 scripts/verify-runtime-boundary-consumer.py \
  --repository "$CANDIDATE_REPOSITORY" --staged-receipt "$CANDIDATE_RECEIPT" \
  --expected-staged-receipt-sha256 "$RECEIPT_SHA256" \
  --staged-source-revision 5800ed2960aefbf63c01d2ebaf2265278d662494 \
  --java-home "$JAVA17_HOME" --gradle-distribution-zip "$GRADLE_9_7_1_ZIP" \
  --evidence-directory "$NEW_BOUNDARY_OUTPUT"
```

The mixed-anchor command has the same options with
`scripts/verify-mixed-anchor-consumer.py` and a separate output directory.
The lifecycle command uses `scripts/verify-runtime-lifecycle-consumer.py` and
`--staged-receipt-sha256` instead of `--expected-staged-receipt-sha256`.
Gradle A-24 uses `scripts/verify-a24-gradle-consumer.py`, the lifecycle spelling
of the receipt option, and `--expected-input-manifest "$FROZEN_GRADLE_INPUTS"`.
No `--case`, reduced profile, preparation-only or positive-only option was used.

Evidence labels: **verified - unit**, **verified - MySQL**,
**verified - ShardingSphere-JDBC 5.5.2**, **verified - ShardingSphere-JDBC 5.5.3**,
each limited to the corresponding checks above. Observed attempts are
SQLExecutionHook reports, not physical-table counts, transaction commits or
a complete route plan.

The [packaged 28-test corpus](packaged-corpus-5800ed2-2026-09-14.md), legacy
resolver/current-entry gates, signing/publication and human review remain
separate. The [specialized dual-resolver gate](dual-resolver-current-5800ed2-2026-09-14.md)
remains incomplete because one Gradle identity lacks the required native
intrinsic path evidence; the completed A-24 installation matrix does not replace it.
The 14 expected 5.5.2 corpus manifests are unchanged and their human
review remains unrecorded. Historical 86a0be5/4e06694 executions retain their
original identities and failures. Original A-28 remains FAILED. This document
does not establish a public 0.2 release, external adoption, wider execution
support or a performance improvement.
