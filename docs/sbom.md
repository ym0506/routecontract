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

An SBOM is an inventory, not a vulnerability scan or legal conclusion. The
project license remains `LICENSE`; third-party components remain governed by
their own licenses.
