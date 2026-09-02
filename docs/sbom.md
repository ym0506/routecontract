# Software Bill of Materials

RouteContract uses the official CycloneDX Gradle plugin to generate SBOMs from
Gradle's **resolved** dependency graphs. The finalizer and policy checker then
bind those dependency profiles to the exact first-party project graph, generated
publication POMs, tracked dependency locks, license policy and vulnerability
scan evidence.

## Release-line boundary

This document describes the unreleased `0.2.x` source tree. It does not rewrite
the evidence or artifact layout of immutable `v0.1.2`. That release used the
legacy single `routecontract-shardingsphere-5.5` artifact and its tag-bound
evidence; the six-role split described below is not retroactive evidence for it.

The current `0.2.x` source has a complete six-role SBOM pipeline, but `0.2.x`
remains an explicit **NO-GO for release**. The release-evidence workflow
intentionally fails
for `0.2.*` until a clean-cache, unauthenticated public consumer proves the
complete `routecontract-core` + exact-5.5.3 adapter + exact-5.5.2 adapter group,
including whole-group and negative-exclusivity checks. Workflow-only SBOM evidence
does not satisfy that public-consumption gate.

## Unreleased 0.2 role set

`prepareVerifiedSbom` produces exactly six JSON/XML pairs, or 12 SBOM
documents:

| Official label | CycloneDX root | Verified output directory | Role |
| --- | --- | --- | --- |
| `aggregate` | `routecontract` | `aggregate/` | repository-wide resolved inventory |
| `core` | `routecontract-core` | `routecontract-core/` | version-neutral published core |
| `adapter553` | `routecontract-shardingsphere-5.5` | `routecontract-shardingsphere-5.5/` | exact ShardingSphere 5.5.3 published adapter |
| `adapter552` | `routecontract-shardingsphere-5.5.2` | `routecontract-shardingsphere-5.5.2/` | exact ShardingSphere 5.5.2 published adapter |
| `mysql553` | `mysql-example` | `mysql-example/` | MySQL test/example profile for 5.5.3 |
| `mysql552` | `mysql-5.5.2-example` | `mysql-5.5.2-example/` | MySQL test/example profile for 5.5.2 |

Every directory in the table is below
`build/reports/verified-sbom/` and contains exactly `bom.json` and `bom.xml`.
The aggregate root directly covers all five subprojects. Each adapter directly
owns `routecontract-core`; each MySQL example directly owns only its matching
adapter and reaches core transitively. The core role has no first-party child.

The three Central publication coordinates are `routecontract-core`,
`routecontract-shardingsphere-5.5` and
`routecontract-shardingsphere-5.5.2`, all at the same `0.2.x` version. The two
MySQL roles are test fixtures, not publication coordinates. Central staging is
a separate inventory: it expects five payloads per coordinate (main, sources
and Javadoc JARs, POM and Gradle module metadata), for 15 payloads plus 15
detached SHA-384 signatures. Those payload and signature counts are not SBOM
document counts.

All 12 SBOM documents are **Gradle dependency-profile BOMs**, not a shipped-file
inventory of every classifier. For example, Javadoc classifiers produced by the
pinned Temurin/OpenJDK standard doclet contain generated CSS, JavaScript and
image files, including jQuery 3.7.1 and jQuery UI 1.14.1. Those classifier-only
files and their embedded `legal/` texts are disclosed in `THIRD_PARTY.md` and
bound by classifier checksums. The SBOM-generation rules do not add them as
runtime or direct dependency components in these machine SBOMs.
The non-bundled distribution boundary remains a separate defense-in-depth
check. These profiles do not determine the semantic origin of renamed or copied
source/class bytes. The related provenance review reopens if those payload
invariants change or a JTS/Mahout published dependency enters the release.

## Generate and locate the SBOMs

Use the checked-in, checksum-pinned Gradle Wrapper:

```bash
./gradlew --no-daemon --no-build-cache validateOfficialCycloneDxSbom
```

The primary repository-level artifact is:

```text
build/reports/verified-sbom/aggregate/bom.json
```

The CycloneDX plugin's raw aggregate reports remain under
`build/reports/cyclonedx/`. Raw direct reports remain under each project's
`build/reports/cyclonedx-direct/`. `scripts/finalize-sbom.py` writes the six
verified pairs under `build/reports/verified-sbom/`. Build output is ignored by
Git. The release-evidence workflow stages and revalidates all 12 verified
documents as workflow evidence; only the aggregate and 5.5.3 adapter pair are
currently part of the legacy public Release-asset subset.

## Publication profiles

The generated core POM owns Alibaba TransmittableThreadLocal 2.14.2 and
`tools.jackson.core:jackson-core` 3.1.5 as direct runtime dependencies. Its
locked runtime closure also contains the Jackson 3.1.5 BOM.

Each adapter POM adds the same-version `routecontract-core` coordinate and its
exact ShardingSphere executor dependency. Its dependency-management section
also binds the exact SPI/connection-property anchors and the reviewed Jackson
2.x BOM used by that ShardingSphere line. The 5.5.3 and 5.5.2 adapter closures
are intentionally distinct and must not be merged into a generic `5.5.x`
profile. The MySQL fixtures have no publication POM.

For each of the three published coordinates, the policy checker proves that:

- the direct SBOM is non-test and root-reachable;
- the generated POM has the exact project identity, Apache-2.0 license, SCM and
  expected dependency/dependency-management structure;
- every literal POM runtime dependency is present in the direct SBOM and lock;
- the third-party POM-seeded runtime closure exactly equals the tracked
  `runtimeClasspath` lock set (Gradle project dependencies are not lockfile
  entries).

ShardingSphere, Connector/J, Jakarta Transaction API, JNA, JTS Core and the
MySQL image belong to adapter compatibility, test/example or container
profiles as appropriate. They are not all dependencies of `routecontract-core`.
JTS I/O Common is excluded from both ShardingSphere-JDBC fixture graphs and is
forbidden by the supply-chain gate.

## Finalization and license metadata

CycloneDX Gradle plugin 3.4.0 maps its `licenseChoice` setting to the BOM
document's `metadata.licenses`. CycloneDX distinguishes that from each
component's own `licenses`. `scripts/finalize-sbom.py` therefore:

- adds canonical Apache-2.0 metadata only to exact first-party components;
- normalizes MySQL Connector/J 26.7.0 to
  `GPL-2.0-only WITH Universal-FOSS-exception-1.0`;
- records Jakarta Transaction API 1.3.3 as
  `EPL-2.0 OR (GPL-2.0-only WITH Classpath-exception-2.0)`;
- records JNA 5.13.0 as `(Apache-2.0 OR LGPL-2.1-or-later) AND MIT`;
- records JTS Core 1.19.0 as `EPL-2.0 OR BSD-3-Clause`;
- rejects `org.locationtech.jts.io:jts-io-common` if it reappears;
- binds the digest-pinned MySQL 8.4.11 test container to the aggregate and the
  two MySQL example profiles that use it.

The MySQL container is an `excluded` CycloneDX component with
`routecontract:usage=test-only`. RouteContract does not assert an image-wide
license. The exact policy-bound review remains
`routecontract:license-review=manual-review-required`, with a documentation
reference to the MySQL 8.4 legal-notices index. The owner reviewed the bound
evidence on 2026-08-24; it expires on 2026-12-05. Re-review immediately if the
OCI digest, selected platform, embedded `LICENSE`/`INFO_SRC` evidence or
test-container boundary changes. Otherwise resolve, renew with new evidence or
remove the package-level review before expiry. The platform manifests, embedded
hashes, source revision and 167-package attestation boundary in
`THIRD_PARTY.md` do not establish an image-wide legal conclusion.

The exact example dependency anchors are profile-specific:

- `mysql553`: ShardingSphere-JDBC 5.5.3 and Calcite core/linq4j 1.42.0;
- `mysql552`: ShardingSphere-JDBC 5.5.2 and Calcite core/linq4j 1.38.0.

Both MySQL role roots must mark their dependency components as test-scoped and
must link to the single canonical MySQL container leaf. The aggregate contains
one canonical occurrence of that OCI identity, not one independently licensed
image per example.

## JSON/XML and official validation

The finalizer reads each output format back and requires complete JSON/XML
parity for every supported component field, metadata timestamp, pinned producer
and dependency edge. Across the six pairs it also requires one shared project
version, the exact first-party root/child graph, canonical first-party
Apache-2.0 metadata, complete graph records and root reachability. It rejects
non-UTF-8 declarations, comments, processing instructions, DTD/entities,
control characters, nested components and fields outside the supported flat
CycloneDX 1.6 release profile.

`validateOfficialCycloneDxSbom` independently runs CycloneDX CLI 0.33.1 against
all 12 documents with explicit JSON/XML format, `v1_6` and fail-on-error mode.
The six required labels are exactly `aggregate`, `core`, `adapter553`,
`adapter552`, `mysql553` and `mysql552`; missing, repeated or extra roles fail.
The executable version, source revision, platform asset size and SHA-256 are
pinned, and the binary is cached by content digest rather than redistributed.
CLI 0.33.1 embeds CycloneDX .NET 12.1.2's 1.6.1 schema snapshot, so this is not
described as exact specification patch 1.6.2 validation. Official schema
validation complements, rather than replaces, RouteContract's semantic role,
graph, license and policy checks.

## Exact-revision vulnerability and license audit

Run the gate from a clean checkout with the exact 40-character source revision:

```bash
./scripts/run-final-supply-chain-scan.sh --revision <40-hex>
```

The authoritative input accounting is:

- 12 freshly generated SBOM documents (six JSON/XML pairs);
- three freshly generated publication POMs (core, adapter553 and adapter552);
- three tracked dependency locks for those same published coordinates;
- therefore 15 regenerated inputs and 18 mode-restricted audited private
  copies in total.

The derived scanner lockfile is created only after those 18 copies are bound;
it is a subsequent temporary output and is not included in the 18-input count.
The official CLI consumes exactly the 12 private SBOM copies. The policy checker
consumes all six pairs plus all three POM/lock pairs.

The audit flow is:

```text
exact clean revision
  -> 12 verified SBOM documents + 3 generated POMs
  -> add 3 tracked publication locks
  -> 18 mode-restricted audited private copies
  -> official validation of the 12 private SBOM copies
  -> derived Maven inventory from the validated aggregate and direct profiles
  -> checksum-pinned OSV-Scanner and generation-pinned Maven database
  -> offline scan and strict local policy
  -> sanitized schema-v3 evidence
```

The runner requires the requested revision to be checked-out `HEAD`, rejects
staged, tracked and untracked changes, records both commit and Git tree, and
rejects prior final-scan evidence before generation. It removes only the 15
enumerated generated inputs after non-symlink checks, regenerates them with no
build cache and rerun tasks, then copies them together with the three tracked
locks into a new mode-restricted directory. Source/copy byte parity and one
fingerprint covering all 18 sources and all 18 copies are rechecked around the
official validator, scanner and policy checker.

This is a cooperative single-user release process in a trusted checkout. Its
path, type, mode, parity and fingerprint checks do not create an operating-
system isolation boundary against a malicious same-UID process. Run it without
concurrent writers in a fresh, access-restricted checkout.

`security/osv-scanner.lock.json` pins the scanner release, supported platform
binaries and a generation-pinned Maven database snapshot. Downloads are checked
before offline execution. The runner passes the tracked, exactly empty
`security/osv-scanner.toml` by absolute path, so adjacent ignored configuration
cannot suppress findings.

`security/supply-chain-policy.json` and
`scripts/verify-supply-chain-policy.py` require the aggregate third-party Maven
set to equal the union of the five non-aggregate role profiles. They also prove
exact 5.5.3-only and 5.5.2-only ShardingSphere role boundaries, publication POM
and lock closure, allowed license metadata, the exact time-bounded MySQL OCI
review, and an empty vulnerability-exception policy. Any vulnerability finding
or policy vulnerability exception fails; this is not a severity threshold.

Successful six-role evidence uses schema version 3 and records
`sbom.roleCount=6` and `sbom.documentCount=12`. For compatibility,
`publishedModule` remains the adapter553 evidence key and `exampleProfile`
remains the mysql553 key. The other direct keys are `coreModule`,
`adapter552Module` and `mysql552Profile`. The aliases do not collapse 5.5.2
evidence into 5.5.3.

The raw scanner result at `build/reports/security/osv-raw.json` remains local
and is not staged, checksummed or uploaded. Only a successful, path-free
`build/reports/security/supply-chain-evidence.json` is eligible for workflow
evidence. It is point-in-time evidence, not a general vulnerability-free claim
or a completed legal review.

## Packaging and release verification boundary

The SBOM proves resolved dependency profiles; it does not prove the semantic
provenance of renamed, relocated, transformed or copied bytes. Archive path,
package, metadata, source-tree, POM and classifier checks are separate
defense-in-depth controls.

The current release-evidence workflow retains a legacy 5.5.3 single-artifact
public subset while adding all 12 split-role SBOM documents only to the
workflow artifact. That workflow artifact is useful internal evidence, but it
does not make `0.2.x` publicly consumable or released. Do not describe the
three-coordinate split, 5.5.2 support or its Central bundle as public until the
explicit public-consumer gate succeeds and the release process is updated.

Before a future `0.2.x` release:

1. Generate all six pairs from the exact candidate revision.
2. Confirm all six roots share the candidate project version and the exact
   first-party graph.
3. Inspect the three publication main/sources/Javadoc JAR sets, generated POMs,
   Gradle module metadata and tracked runtime locks.
4. Recheck `THIRD_PARTY.md`, every reviewed license expression, the absence of
   JTS I/O Common and the MySQL OCI review window.
5. Re-resolve the pinned MySQL OCI index and inspect legal notices in the
   selected platform image.
6. Refresh the pinned OSV database and require the same fail-closed policy.
7. Pass the clean-cache unauthenticated public split-artifact consumer and both
   version/exclusivity negative cases.
8. Save the exact revision/tree, Gradle/JDK versions, SBOM hashes and CI run URL
   with the candidate evidence.

Example checksum command:

```bash
shasum -a 256 build/reports/verified-sbom/aggregate/bom.json
```

An SBOM is an inventory, not a vulnerability scan or legal conclusion. The
offline gate is a point-in-time database and policy check, not a guarantee that
dependencies are vulnerability-free or legally suitable. The project license
remains `LICENSE`; third-party components remain governed by their own licenses.
