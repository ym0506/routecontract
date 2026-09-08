# Real legacy resolver acceptance for the 0.2 candidate

Status: the local Gradle 37-case and Maven 45-case runs passed on 2026-09-08
against reviewed source `86a0be5`; see the [execution evidence](evidence/legacy-resolver-86a0be5-2026-09-08.md).
The [earlier 4e06694 execution](evidence/legacy-resolver-4e06694-2026-09-08.md) remains preserved.
This file specifies the resolver work item, not the whole release requirement
in `versioned-shardingsphere-adapters.md`. It makes no public 0.2, MySQL,
manual-classpath or adoption claim. Original A-28 remains FAILED; the separate
[A-29 current-entry contract](current-entry-migration-acceptance.md) addresses
the changed application entry and preserves that historical failure.

The fixture must consume the actual published all-in-one JAR/POM bytes of
`0.1.0`, `0.1.2`, `0.1.3`, and distributed `0.1.0-rc2`. The public `0.1.3`
Gradle Module Metadata is also an input. A checked-in registry binds each
download to its public URL, exact size/SHA-256, tag commit, and inspected legacy
class/service entries. `0.1.1` and `0.1.0-rc1` are retained separately as tag-only layout
evidence; a tag is not evidence that a binary was distributed.

Current core and adapters are supplied as one reviewed nine-payload staged
receipt. The runner must compare every supplied byte with that receipt and
record its source revision. When reusing any retained staging, the
production/publication inputs must be identical to the checkout under test;
otherwise prepare and review a new staged input. The runner must not rebuild
first-party artifacts or substitute source projects.

Each resolver case runs in an independent copied Gradle build outside the
checkout, with an absent dependency cache and strict dependency-verification
metadata. Only the checksum-pinned Gradle distribution may be seeded. Exact
first-party bytes come from an isolated repository populated from the verified
inputs. Third-party metadata/artifacts use the existing reviewed trust metadata.

Required real Gradle cases for every distributed legacy input:

1. Resolve the legacy artifact alone and record its actual JAR hash and legacy
   layout. This is a resolver control, not SQL execution.
2. Combine legacy + core, in both declaration orders. Assign the synthetic
   `routecontract-core-owner:1` capability to each selected legacy metadata
   variant; resolution must fail through an actual capability conflict.
3. Combine legacy + adapter552, in both orders; resolution must fail through a
   core-owner or legacy-GAV capability conflict.
4. Request legacy and adapter553/current through the same GA in both orders.
   Ordinary version mediation must select exactly `0.2.0` and its transitive
   core, and the resolved first-party files must contain only the expected
   current JAR bytes.
5. Request both same-GA versions strictly, in both orders. Resolution must fail
   because the two version requirements are incompatible.

A separate latest-legacy + core control with the ownership rule disabled must
resolve both components. Enabling the rule must reject that same combination.
This records the actual missing protection before the fix. Request-time
exceptions, missing artifacts, checksum failures and unrelated dependency
conflicts do not count as the required resolver rejection.

Retain the registry/staged receipt digests, input-source binding, exact Java and
Gradle versions, per-case request order, applied metadata rules, selected
components, materialized first-party file hashes, and expected failure reasons.
Every case must have its own command/log and result. A partial run must not
produce a complete summary. Maven equivalents and the A-29 fresh-JVM ordinary
SQL/capture tests remain separate runners using the same legacy inputs. The
original A-28 failure must not be relabeled as passing.
