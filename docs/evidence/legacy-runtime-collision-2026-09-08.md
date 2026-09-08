# Actual legacy JAR runtime matrix, 2026-09-08

**A-28 failed.** All 32 required collision cells and four clean controls ran in
separate fresh JVMs. Collision cells passed **28/32**; controls passed **4/4**.
The four failures remain release blockers. The
[minimized receipt](legacy-runtime-collision-2026-09-08.json) has `status: FAILED`
and preserves each outcome without rewriting the diagnostic.

| Exact runtime | Legacy position | Ordinary SQL | Direct capture sentinel |
| --- | --- | --- | --- |
| 5.5.2 | First | 4/4 passed | 0/4 passed: old version diagnostic |
| 5.5.2 | Last | 4/4 passed | 4/4 passed |
| 5.5.3 | First | 4/4 passed | 4/4 passed |
| 5.5.3 | Last | 4/4 passed | 4/4 passed |

Every row includes the actual distributed 0.1.0, 0.1.2, 0.1.3 and 0.1.0-rc2
JARs. Both clean SQL controls returned the exact fixed synthetic business row and
recorded one physical driver execution. Both clean capture controls entered the
action and returned an INCOMPLETE snapshot with zero attempts and
`RC_NO_START_CALLBACK_OBSERVED`, as expected for a no-SQL action.

All 32 collision cells left the action unentered, returned no business rows and
performed no delegated physical business execution. No linkage failure,
`AbstractMethodError`, or silent return was observed. This safety observation
is separate from the **four failing diagnostic assertions**. In those four
cases, actual code-source evidence selects the old `RouteContract` and
`CaptureRegistry`; the legacy 5.5.3 version check rejects exact 5.5.2 before
any new adapter is discovered. It cannot emit the new collision code.

The [feasibility note](../legacy-runtime-collision-feasibility.md) traces that
old-method path and evaluates an explicitly selected, non-colliding current API
or bootstrap. Such an addition would not repair direct calls into an unchanged
old class and does not close the original A-28 gate. No production change was
made for this investigation.

## Reproduction and input binding

Read the [acceptance specification](../legacy-runtime-collision-acceptance.md).
Use a new, absent evidence directory outside the checkout:

```sh
python3 scripts/verify-legacy-runtime-collision.py \
  --repository /path/to/reviewed-staging/repository \
  --staged-receipt /path/to/reviewed-staged-receipt.json \
  --staged-source-revision 008e125a0648ed615842a572d60fd453698bb5aa \
  --evidence-directory /path/to/new-a28-evidence \
  --java-home /path/to/jdk-17 \
  --gradle-distribution-zip /path/to/gradle-8.14.4-bin.zip \
  --legacy-payload-directory /path/to/pinned-public-legacy-cache
```

Omit the last argument to obtain the registered public URLs, verifying all pins.
The legacy cache layout is `<version>/<registered-payload-name>`. The command
currently exits **1** after retaining the complete failing matrix. A requested
`--case` subset can never be reported as full A-28 verification.

Observed environment: CPython 3.12.14, Homebrew OpenJDK 17.0.15+0, Gradle 8.14.4,
macOS arm64 and pinned MySQL 8.4.11 image
`sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb`.
The Gradle archive was verified against
`f1771298a70f6db5a29daf62378c4e18a17fc33c9ba6b14362e0cdf40610380d`.
Each exact runtime graph began with an absent dependency cache, strict checksum
verification and the existing staged consumer lock. Every selected
`org.apache.shardingsphere` component had the lane's exact version.

Checkout `3a136a6f006c8040b0facadafc18606d2a63600a` has identical production and
publication inputs to the separately supplied staging source revision above.
All nine staged payloads and all nine registered legacy payloads were verified.
Every launched JAR and compiled consumer class was checked before and after
execution. The fixture never builds first-party JARs or substitutes source
classes, mocked services, synthetic old classes or test-invoked guards.

Evidence labels: `verified - MySQL`, `verified - ShardingSphere-JDBC 5.5.2`, and
`verified - ShardingSphere-JDBC 5.5.3` apply to the **observations and controls**;
they do not turn the failed A-28 contract into a pass. Ten focused harness unit
tests passed, including altered input bytes, exact row checks and failure/timeout
retention.

## Retained evidence and limits

Local raw evidence is under
`/private/tmp/routecontract-a28-final-20260908`. It includes:

- `source-binding.json`, reviewed receipts, public registry and input inventory;
- independent `lanes/<version>` resolution logs, classpaths and compiled probes;
- 36 `cases/<id>` commands, observations, JVM logs and results;
- `TEST-a28-subprocess-assertions.xml`: **36 assertions, four failures**, generated
  by Python from subprocess results, not raw product JUnit;
- `bytecode/legacy-0.1.0-entry.txt`: read-only `javap` of the pinned actual old JAR;
- `summary.json`, `verified-receipt.json` and `harness-unit-tests.log`.

The minimized receipt SHA-256 is
`58e96ff9cf16260679aeb026326fc815a25d948fffb2393e0dcf2f9a274fefcb`.
The raw summary SHA-256 is
`83ffad4b77bd025b8daf953a9d2275447e7e0d0068f82e8850e99a1e42a885c5`.
Public receipt entries contain counts, code-source JAR hashes and diagnostic
codes; raw logs, raw observations and generated JUnit can contain connection
information or SQL in unexpected failures and remain local.

The first diagnostic run was intentionally stopped after its SQL controls
exposed an invalid constant INLINE expression. That fixture error was corrected
before this final run; none of its SQL cells contributes to the final receipt.
Its independent direct-capture failure is preserved separately. No production
bytes changed between runs.

The physical-execution counter covers the fixed synchronous business
PreparedStatement immediately before its actual MySQL delegation. Direct fixture
schema setup and datasource metadata queries are outside that counter.

This is reviewed local 0.2 staging combined with actual public legacy bytes.
It is not evidence of anonymous public 0.2 consumption. Each process had a fixed,
complete classpath and a cold default loader; warmed caches, TCCL mutation,
hidden providers and same-process retry remain outside this matrix. No signing,
publication, protected-key access, commit or push was performed.
