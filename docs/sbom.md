# Software Bill of Materials

RouteContract uses the official CycloneDX Gradle plugin to generate an
aggregate SBOM from Gradle's **resolved** dependency graphs. The aggregate is a
repository-level inventory that includes the library and MySQL example/test
configurations. The library module's direct SBOM is restricted to its compile
and runtime compatibility graph; it is still not a list of files embedded in
the thin JAR, which does not shade dependencies.

## Generate

Use the checked-in, checksum-pinned Gradle Wrapper:

```bash
./gradlew --no-daemon --no-build-cache prepareVerifiedSbom
```

The primary submission artifact is:

```text
build/reports/verified-sbom/aggregate/bom.json
```

The task preserves the plugin's raw reports under `build/reports/cyclonedx/`
and each project's `build/reports/cyclonedx-direct/`, then writes verified
copies under `build/reports/verified-sbom/`. Build output is intentionally
ignored by Git; CI uploads the verified aggregate JSON and XML for each
successful run.

CycloneDX Gradle plugin 3.4.0 maps its `licenseChoice` setting to the BOM
document's `metadata.licenses`. The CycloneDX specification distinguishes that
from each component's own `licenses`. RouteContract therefore runs
`scripts/finalize-sbom.py` after dependency resolution to add Apache-2.0 only
to components whose group exactly matches the root project's release group, and
to normalize MySQL Connector/J 26.7.0 to its complete SPDX expression,
`GPL-2.0-only WITH Universal-FOSS-exception-1.0`. For BOMs containing the
MySQL example, it also records the digest-pinned `mysql:8.4.11` test fixture as
an `excluded` container component with `GPL-2.0-only` and links it from the
example's dependency entry. The script then independently reads both output
formats back to assert these exact fields, first-party license URL and
coordinates, dependency relationship, and matching JSON/XML serial number.
Other third-party component metadata remains as emitted by the plugin.

## Verify before a release or contest submission

1. Generate the SBOM from the exact source revision being submitted.
2. Confirm `metadata.component.version` matches that revision's project
   version and that every expected subproject appears in the dependency graph.
3. Compare direct components and scopes with `THIRD_PARTY.md`.
4. Review all `licenses` entries and investigate missing or ambiguous values
   against upstream license and NOTICE files.
5. Save the source revision, Gradle/JDK versions, command, SBOM SHA-256, and CI
   run URL alongside the submitted SBOM.

## Experimental local vulnerability and license audit

The optional local supply-chain audit starts from the exact clean source
revision and generates every inventory it checks itself:

```text
clean revision
  -> fresh aggregate, published-module and MySQL-example SBOMs
  -> fresh generated published POM
  -> checksum-pinned OSV-Scanner and Maven database
  -> offline OSV scan
  -> strict local vulnerability/license policy
  -> local sanitized audit summary
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
checks, and
then regenerates those inputs with no build cache and rerun tasks before any
scanner download. It copies the seven generated inputs into a new
mode-restricted directory, adds a read-only copy of the tracked published-module
dependency lock, generates the scanner inventory from those copies, and
fingerprints the sources, copies, lock and inventory before the scan. It checks
that fingerprint before and after the scanner and again after policy
verification. It also repeats the clean-revision check after generation and
before publishing either result file. This makes ignored prior build output
ineligible for rebinding to a newer revision without using a broad clean that
could erase unrelated evidence. The v0.1 Release evidence workflow and
packaging verifier do not invoke or retain this audit, so its output is not
public immutable evidence.

This local runner assumes a cooperative, single-user release process in a
trusted checkout. It fails closed against stale inputs, adjacent ignored
scanner configuration, ordinary file mutation, symbolic-link redirection and
destination replacement, and it records hashes for the artifacts it checks.
Those checks are not an operating-system isolation boundary and do not claim
cryptographic immutability against a malicious same-UID process that can alter
files or process state while the scanner is running. Run it without concurrent
writers in a fresh, access-restricted checkout; final-tag CI integration must
provide the immutable release binding.

`security/osv-scanner.lock.json` pins the scanner release and platform binary
checksums plus one generation-pinned Maven database snapshot. Downloads are
verified before the scanner executes offline. The runner passes the tracked,
exactly empty `security/osv-scanner.toml` by absolute `--config` path, so an
ignored configuration beside the derived lockfile cannot suppress a finding.
`security/supply-chain-policy.json` and
`scripts/verify-supply-chain-policy.py` then fail closed unless scanned Maven
package identities exactly match canonical Maven purls in the aggregate BOM,
the aggregate third-party set exactly equals the union of the two direct
profiles, every component has explicit license metadata allowed by policy, and
every finding has an exact, unexpired exception. An unexpected, expired or
unused exception is also an error; the policy is not a severity-only threshold.

The direct published-module BOM must mark every dependency as non-test, its
dependency graph must be complete and root-reachable, and every literal
runtime dependency in the generated POM must be exactly the runtime-locked,
direct JAR subset. The POM-seeded transitive closure must exactly equal the
tracked `runtimeClasspath` lock set.
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
review evidence, or allowed to fail the gate.

The raw result at `build/reports/security/osv-raw.json` and generated sanitized
summary at `build/reports/security/supply-chain-evidence.json` are intentionally
local. Neither is uploaded by the current workflow or accepted by the final
package artifact allowlist. Do not cite them as release or contest evidence.
Workflow integration is deferred until one focused change can update the
workflow, artifact schema and package verifier together.

The verification fails closed if a first-party component already declares a
different license, if no first-party component exists, if Connector/J has an
unexpected version or incomplete license expression, if a MySQL example BOM
lacks the exact pinned container component or dependency edge, or if the
JSON/XML first-party component sets or serial numbers differ. Library-only
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
