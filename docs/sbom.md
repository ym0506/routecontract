# Software Bill of Materials

RouteContract uses the official CycloneDX Gradle plugin to generate an
aggregate SBOM from Gradle's **resolved** dependency graphs. The aggregate is a
repository-level inventory that includes the library and MySQL example/test
configurations. The library module's direct SBOM is restricted to its compile
and runtime compatibility graph; it is still not a list of files embedded in
the thin JAR, which does not shade dependencies.

The generated published POM has two direct runtime dependencies: Alibaba
TransmittableThreadLocal 2.14.2 and `tools.jackson.core:jackson-core` 3.1.5.
Its locked runtime closure also contains the Jackson 3.1.5 BOM; all three are
Apache-2.0. ShardingSphere, Connector/J, Jakarta Transaction API, JNA, JTS and
the MySQL image belong to compile compatibility, test/example or container
profiles and are not bundled in the published RouteContract JAR.

## Generate

Use the checked-in, checksum-pinned Gradle Wrapper:

```bash
./gradlew --no-daemon --no-build-cache validateOfficialCycloneDxSbom
```

The primary submission artifact is:

```text
build/reports/verified-sbom/aggregate/bom.json
```

`prepareVerifiedSbom` preserves the plugin's raw reports under
`build/reports/cyclonedx/`
and each project's `build/reports/cyclonedx-direct/`, then writes verified
copies under `build/reports/verified-sbom/`. Build output is intentionally
ignored by Git; CI uploads the verified aggregate JSON and XML for each
successful run.

CycloneDX Gradle plugin 3.4.0 maps its `licenseChoice` setting to the BOM
document's `metadata.licenses`. The CycloneDX specification distinguishes that
from each component's own `licenses`. RouteContract therefore runs
`scripts/finalize-sbom.py` after dependency resolution to add Apache-2.0 only
to components whose group exactly matches the root project's release group, and
to normalize MySQL Connector/J 26.7.0 to its Maven-declared standardized SPDX
expression,
`GPL-2.0-only WITH Universal-FOSS-exception-1.0`. It also replaces two known
test-graph metadata shortcuts with reviewed expressions: Jakarta
Transaction API 1.3.3 becomes
`EPL-2.0 OR (GPL-2.0-only WITH Classpath-exception-2.0)`, and JNA 5.13.0 becomes
`(Apache-2.0 OR LGPL-2.1-or-later) AND MIT` to include its embedded libffi
license. JTS Core 1.19.0 becomes the explicit alternative expression
`EPL-2.0 OR BSD-3-Clause`. JTS I/O Common 1.19.0 becomes
`(EPL-2.0 OR BSD-3-Clause) AND Apache-2.0`: eight sources use the JTS project
choice while its packaged Mahout-derived `Varint.class` comes from an
Apache-2.0 source. For BOMs containing the MySQL example, the script
records the digest-pinned `mysql:8.4.11` test fixture as an `excluded` container component
without asserting an image-wide license. Instead, an exact custom property
records `manual-review-required` and a CycloneDX `documentation` external
reference points to the MySQL 8.4 legal-notices index. The policy binds that
unresolved review state to the exact MySQL name, version, OCI purl,
digest/hash, status, documentation URL, owner, review/action window and
test-only scope. The record expires 2026-08-27. The script then
links the image from the example's dependency entry and emits the container's
required empty dependency leaf record.

The JTS I/O Common expression is a concluded artifact-level license expression,
not a conclusion that its redistribution notices are complete. Its Central
binary and sources JARs contain no `LICENSE` or `NOTICE`; the inherited POM
names only the JTS dual licenses; the tagged `LICENSES.md` omits Mahout; and
`Varint.java` tells recipients to consult an ASF `NOTICE` that is absent from
the tag. Review of the official Mahout 0.8 source archive confirms its
top-level `NOTICE.txt` exists; policy pins that archive, notice, license and
original `Varint.java` by path and SHA-256. What remains unresolved is the
notice treatment for the copy shipped by JTS, whose artifact and release
metadata omit Mahout. The finalizer therefore also records
`manual-review-required` on this exact Maven component. Policy pins the
reviewed JTS binary/source/POM/source-file/class hashes, tag commit, upstream
URLs, action, owner and 2026-08-27 expiry.

The script independently reads both output formats back to assert complete
JSON/XML parity within each pair for every supported component field, the
metadata timestamp and pinned producer, and the exact dependency graph. Each
role may carry its own valid generation timestamp. It requires the aggregate,
published-module and example role roots and project children, complete graph
records, root reachability and canonical first-party Apache-2.0 ID/URL. It
rejects BOMs, non-UTF-8 declarations, comments, processing instructions,
DTD/entities, control characters, nested components and fields outside the
explicitly supported flat CycloneDX 1.6 release profile.

`validateOfficialCycloneDxSbom` then runs the CycloneDX project's CLI 0.33.1
against all three finalized JSON/XML pairs, with explicit JSON or XML format,
`v1_6` and fail-on-error mode. The executable version, source revision,
platform asset size and SHA-256 are pinned; the binary is cached by content
digest and is not redistributed. This is an independent structure-validation
layer, not a replacement for the semantic parity, role, graph, license and
vulnerability policy checks. CLI 0.33.1 embeds CycloneDX .NET 12.1.2's 1.6.1
schema snapshot, so it is not described as exact specification patch 1.6.2
validation.

## Verify before a release or contest submission

1. Generate the SBOM from the exact source revision being submitted.
2. Confirm `metadata.component.version` matches that revision's project
   version and that every expected subproject appears in the dependency graph.
3. Inspect the main, sources and Javadoc JARs plus generated POM and runtime
   lock; re-prove the distributed/runtime boundary rather than treating the
   aggregate test graph as shipped code.
4. Compare direct components and scopes with `THIRD_PARTY.md`.
5. Review all `licenses` entries against exact-version upstream POM, JAR,
   `LICENSE` and `NOTICE` files. Recheck Connector/J's FOSS exception, Jakarta
   Transaction's modern SPDX exception form, JNA's embedded libffi, and JTS's
   EPL/EDL dual choice.
6. Re-resolve the pinned MySQL OCI index and inspect legal notices in the
   selected platform image; a server license alone is not an image inventory.
7. Refresh the pinned OSV database and review all findings, fixed versions and
   exception expiries. `test-only` reachability is not a harmlessness claim.
8. Save the source revision, Gradle/JDK versions, command, SBOM SHA-256, and CI
   run URL alongside the submitted SBOM.

## Exact-revision vulnerability and license audit

The supply-chain audit starts from the exact clean source
revision and generates every inventory it checks itself:

```text
clean revision
  -> fresh aggregate, published-module and MySQL-example SBOMs
  -> fresh generated published POM
  -> mode-restricted audited copies bound to their generated sources
  -> checksum-pinned official CycloneDX validation of the six audited SBOM copies
  -> derived dependency inventory from those validated copies
  -> checksum-pinned OSV-Scanner and Maven database
  -> offline OSV scan
  -> strict local vulnerability/license policy
  -> sanitized audit summary
```

Run the gate from a clean checkout with the exact 40-character source
revision:

```bash
./scripts/run-final-supply-chain-scan.sh --revision <40-hex>
```

The runner requires that revision to be the checked-out `HEAD`, rejects staged,
tracked or untracked worktree changes, records both the commit and its exact Git
tree, rejects existing final-scan evidence before generation, deletes only the
three enumerated JSON/XML SBOM pairs and publication POM after non-symlink
checks, and then regenerates those inputs with no build cache and rerun tasks
before any scanner download. It copies the seven generated inputs into a new
mode-restricted directory and adds a read-only copy of the tracked
published-module dependency lock. It first fingerprints the generated sources
and private copies and verifies their byte parity, then runs the checksum-pinned
official CycloneDX CLI against the exact three JSON/XML copies that the policy
checker consumes.
The runner rechecks the bound source/copy fingerprint and parity immediately
after official validation and throughout the remaining pipeline. It generates
the scanner inventory from those copies and separately fingerprints it before
the scan. It checks both bindings before and after the scanner and again after
policy verification. It also repeats the clean-revision check after generation and
before publishing either result file. This makes ignored prior build output
ineligible for rebinding to a newer revision without using a broad clean that
could erase unrelated evidence. The final-tag Release evidence workflow invokes
this gate and stages only the sanitized summary after the policy succeeds.

This local runner assumes a cooperative, single-user release process in a
trusted checkout. It fails closed against stale inputs, adjacent ignored
scanner configuration, ordinary file mutation, symbolic-link redirection and
destination replacement, and it records hashes for the artifacts it checks.
Those checks are not an operating-system isolation boundary and do not claim
cryptographic immutability against a malicious same-UID process that can alter
files or process state while the scanner is running. Run it without concurrent
writers in a fresh, access-restricted checkout. The tag workflow and final
package verifier provide the immutable release binding; they do not expand this
trusted-runner boundary.

`security/osv-scanner.lock.json` pins the scanner release and platform binary
checksums plus one generation-pinned Maven database snapshot. Downloads are
verified before the scanner executes offline. The runner passes the tracked,
exactly empty `security/osv-scanner.toml` by absolute `--config` path, so an
ignored configuration beside the derived lockfile cannot suppress a finding.
`security/supply-chain-policy.json` and
`scripts/verify-supply-chain-policy.py` then fail closed unless scanned Maven
package identities exactly match canonical Maven purls in the aggregate BOM,
the aggregate third-party set exactly equals the union of the two direct
profiles, every component has real license metadata allowed by policy except
the exact OCI component carrying a bound unresolved-review record, and
every finding has an exact, unexpired exception. An unexpected, expired or
unused exception is also an error; the policy is not a severity-only threshold.
Policy schema v3 binds each real-license exception to its CycloneDX choice kind
(`id`, `expression` or `name`). It separately binds exactly two unresolved
reviews: the MySQL OCI record to its exact name, version, purl, digest/hash,
status, documentation URL, owner, dates, action and test-only scope; and JTS
I/O Common to its exact expression, artifact hash, review provenance, status,
owner, dates, action and test-only scope. The
checker parses expressions against the reviewed SPDX license/exception
identifiers used by this release, so malformed expressions or unknown
identifiers do not degrade into arbitrary strings.

A policy pass may retain exactly those two time-bounded unresolved reviews:
both components are confined to the example/test graph and absent from the
published module and its runtime closure. This is not a claim of completed
legal review. The owner must resolve, renew with new evidence or remove each
record before its expiry; the stable release and submission must not describe
the unresolved count as legal completion.

The direct published-module BOM must mark every dependency as non-test, its
dependency graph must be complete and root-reachable, and every literal
runtime dependency in the generated POM must be exactly the runtime-locked,
direct JAR subset. The POM-seeded transitive closure must exactly equal the
tracked `runtimeClasspath` lock set. That POM must contain exactly one
Apache-2.0 license declaration with the canonical project name, URL and `repo`
distribution value. Non-Maven SBOM components are rejected except for the
exact policy-bound OCI review record. The licensed JTS I/O Common Maven
component is the only licensed component permitted to carry the reserved
review marker.
The MySQL example BOM must mark every dependency as test. A test-only
vulnerability exception is rejected if its canonical purl appears anywhere in
the published-module profile, even if the aggregate BOM's collapsed property
says `test=true`. A license exception marked `test-runtime` is likewise
checked against all three SBOM roles. The MySQL `test-container` exception
additionally requires a `container` component with `scope=excluded` and the
checked-in `routecontract:usage=test-only` property. A human-written scope
string alone is never accepted.

The only allowed vulnerability findings are:

- `commons-lang:commons-lang:2.4` / `GHSA-j288-q9x7-2f5v`;
- `net.minidev:json-smart:2.5.0` / `GHSA-pq2g-wx69-c263`;
- `org.apache.calcite:calcite-core:1.40.0` / `GHSA-c2rv-hwqm-wjpg`.

They are test/example-only transitive dependencies reached through
ShardingSphere 5.5.3's SQL Federation modules, not dependencies declared by the
published RouteContract POM. SQL Federation coverage is outside v0.1 scope.
Each exception expires on 2026-08-27 and must then be removed, renewed with new
review evidence, or allowed to fail the gate. This reachability statement does
not establish that a vulnerability is harmless or inapplicable.

The raw result at `build/reports/security/osv-raw.json` remains local and is
never staged, checksummed or uploaded. The generated path-free summary at
`build/reports/security/supply-chain-evidence.json` is a public payload only
for a successful exact-tag Release evidence run. The package verifier binds
its commit/tree, scanner/database lock, policy, aggregate/direct SBOMs,
example-profile SBOM pair, publication POM and published dependency lock to the
final source and exact workflow artifact. The summary records the exact two
unresolved review identities, owners, actions and windows while the policy hash
binds their full review contracts and provenance.
That retained summary is point-in-time evidence, not the raw scanner record or
a claim of zero vulnerabilities.

The verification fails closed if a first-party component already declares a
different license, if no first-party component exists, if Connector/J has an
unexpected version or incomplete license expression, if a MySQL example BOM
lacks the exact pinned container component, unresolved-review property,
documentation external reference or dependency edge, if reviewed Jakarta
Transaction, JNA or JTS expressions drift, or if the JSON/XML component records,
metadata or graphs differ, a graph omits a node record or a role has the wrong
project-root coverage. Library-only
direct BOMs are required not to contain the test container.

Example checksum command:

```bash
shasum -a 256 build/reports/verified-sbom/aggregate/bom.json
```

An SBOM by itself is an inventory, not a vulnerability scan or legal
conclusion. The offline gate is a point-in-time database and policy check, not
a guarantee that dependencies are vulnerability-free or legally suitable.
The project license remains `LICENSE`; third-party components remain governed
by their own licenses.
