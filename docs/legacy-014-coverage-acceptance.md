# Upgrade coverage after the public 0.1.4 release

A user upgrading to 0.2 may accidentally retain the previously installed 0.1.4
JAR. The current migration fixtures still enumerate four older artifacts and
omit that newest public release. A passing old matrix cannot establish what
happens for this user's installed version.

Status: acceptance before implementation; current 0.1.4 coverage is unverified.

## Required change

Keep the historical format-1 four-version registry and the original A-28 failed
evidence unchanged. Add a separate current format-2 registry containing exactly
those four audited records, unchanged, plus the published 0.1.4 JAR, POM and
Gradle metadata. Bind the new entry to the retained public release receipt,
source revision, actual public payload bytes and inspected class/service layout.
Tag-only versions remain non-executable. No wildcard or unreviewed version is
admitted by either format.

Current A-27 Gradle/Maven and A-29 runners must select the current registry.
Historical A-28 and focused regression tools keep their original four-version
input. Preserve historical results and counts as dated records.

For 0.1.4, A-29 must exercise both exact ShardingSphere versions, both physical
JAR orders, both current capture methods, and ordinary SQL before any bootstrap.
The complete current matrix contains 76 distinct fresh JVM cases: 40 capture
collisions, 20 ordinary-SQL collisions, 12 clean controls and four startup
rejections. A 64-case subset, missing version, duplicate process or altered
expected diagnostic must not qualify that matrix. Current A-27 plans must include
the same ordinary per-version scenarios for 0.1.4 as the older distributed
versions, retaining their existing policy-disabled diagnostic controls: 46
Gradle cases and 56 Maven cases. Current runners must reject a format-1 registry
instead of silently reducing the current coverage to its historical subset.

## Evidence

First reproduce missing 0.1.4 coverage in the actual three current plans. Add
focused integrity tests for the separate registry, exact supported version sets,
mandatory 0.1.4 metadata, payload source and layout checks, and complete A-29
counts. Then run the current A-29 matrix against the already verified unsigned
CI candidate from `5800ed2960aefbf63c01d2ebaf2265278d662494` without rebuilding
production artifacts. Retain exact graph/JAR origins, fresh process identities,
commands, exits and real-MySQL clean controls.

An A-29 result does not qualify A-27 resolver executions. The two full current
resolver plans require their own executions and must remain unverified until
those finish. No original A-28 failure, authentic human baseline review, release
hold, signing decision or public 0.2 availability changes through this work.
