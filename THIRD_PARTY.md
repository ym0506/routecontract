# Third-party software

RouteContract is licensed under Apache-2.0. The dependencies below keep their
own licenses. This file is a human-readable inventory of the dependencies
declared directly by this repository, selected reviewed transitive metadata,
and the pinned report-builder runtime closure, as of 2026-08-23; it is not a
substitute for the machine-readable SBOM or the license text shipped by each
dependency.

RouteContract does not shade or copy these dependencies into its library JAR.
The MySQL example's dependencies and container image are test-only and are not
part of the published library artifact.

## Published library

| Component | Version | Gradle scope | License |
|---|---:|---|---|
| Jackson 2 compatibility BOM (`com.fasterxml.jackson`) | 2.18.9 | `compileOnly` (also `testImplementation`) | Apache-2.0 |
| Apache ShardingSphere `shardingsphere-infra-executor` | 5.5.3 | `compileOnly` (also `testImplementation`) | Apache-2.0 |
| Alibaba TransmittableThreadLocal | 2.14.2 | `implementation` | Apache-2.0 |
| Jackson Core (`tools.jackson.core`) | 3.1.5 | `implementation` | Apache-2.0 |

In the verified Gradle compatibility/test graph, the `compileOnly` Jackson 2 BOM
resolves core, databind, datatype-jdk8, and datatype-jsr310 to 2.18.9; it is not
published as a consumer version constraint. In the verified combined test
runtime, the annotations artifact shared with Jackson 3 resolves to 2.21.
Consumers using ShardingSphere 5.5.3
must supply, or already have, an equivalent Jackson 2 alignment to reproduce
the verified 2.18.9 graph; RouteContract's POM does not provide it. It does not
replace the separate `tools.jackson` 3.1.5 runtime dependency.

## Javadoc classifier shipped assets

The published Javadoc classifier is generated with **Eclipse Temurin/OpenJDK
standard-doclet 17.0.20.1+1**. In addition to RouteContract API pages, that
classifier ships the standard doclet's JavaScript, CSS and two PNG resources.
The OpenJDK-authored files are distributed under
`GPL-2.0-only WITH Classpath-exception-2.0`; the classifier also contains
jQuery 3.7.1 and jQuery UI 1.14.1 under MIT. This does not relicense
RouteContract or the Apache-2.0 main JAR. The five upstream texts are kept
inside the classifier under the `legal/` directory as `legal/LICENSE`, `legal/ADDITIONAL_LICENSE_INFO`,
`legal/ASSEMBLY_EXCEPTION`, `legal/jquery.md` and `legal/jqueryUI.md`.

This is a classifier-only shipped-file boundary. These assets are not present
in the main library JAR or its runtime dependency graph, and the project does
not add them as runtime dependencies merely to make a dependency-profile SBOM
look like a file inventory. The exact release workflow instead pins the JDK,
records `java -fullversion`, and makes the offline Release installer require
the legal files, static resources, versions and license markers. The
authoritative upstream references are the [Eclipse Temurin
17.0.20.1+1 release](https://github.com/adoptium/temurin17-binaries/releases/tag/jdk-17.0.20.1%2B1),
the [OpenJDK 17.0.20.1 jdk.javadoc
source](https://github.com/openjdk/jdk17u/tree/jdk-17.0.20.1%2B1/src/jdk.javadoc),
[jQuery 3.7.1](https://github.com/jquery/jquery/tree/3.7.1), and [jQuery UI
1.14.1](https://github.com/jquery/jquery-ui/tree/1.14.1). No whole-file hash is
predeclared here: the final classifier and `SHA256SUMS` bind the bytes actually
produced by the pinned release workflow.

## Tests and MySQL example

| Component | Version | Gradle scope | License |
|---|---:|---|---|
| Apache ShardingSphere JDBC and explicitly declared runtime modules | 5.5.3 | `testImplementation` / `testRuntimeOnly` | Apache-2.0 |
| JUnit Jupiter and JUnit Platform Launcher (managed by JUnit BOM) | 5.14.3 / 1.14.3 | `testImplementation` / `testRuntimeOnly` | EPL-2.0 |
| Testcontainers JUnit Jupiter and MySQL modules | 1.21.4 | `testImplementation` | MIT |
| Apache Commons Compress | 1.26.0 | `testImplementation` constraint | Apache-2.0 |
| datasource-proxy | 1.11.0 | `testImplementation` (empirical comparison only) | MIT |
| HikariCP | 6.2.1 | `testRuntimeOnly` | Apache-2.0 |
| MySQL Connector/J | 26.7.0 | `testRuntimeOnly` | `GPL-2.0-only WITH Universal-FOSS-exception-1.0` |
| SLF4J Simple | 2.0.17 | `testRuntimeOnly` | MIT |
| MySQL Community Server container image (`mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb`) | 8.4.11 | Testcontainers runtime | Image-wide conclusion not asserted; manual package-level review required |

Connector/J's upstream 26.7.0 license includes GPLv2 plus the Universal FOSS
Exception 1.0 and third-party notices; the expression above records the Maven
project’s stated license choice. The digest-pinned OCI image is not described
as wholly GPL: the digest-selected platform image is built from an Oracle Linux
base and installs MySQL server, MySQL Shell and other packages. The SBOM
therefore omits `licenses` for this one OCI component, records an exact custom
unresolved-review property, and links the [MySQL 8.4 legal-notices
index](https://dev.mysql.com/doc/refman/8.4/en/preface.html) as a documentation
external reference rather than an unsupported image-wide SPDX conclusion.
The reviewed official image recipe source is the
[`docker-library/mysql` 8.4 Oracle Dockerfile at commit
`01f90d87012e46cd174073bba02d64e9fc693ed3`](https://github.com/docker-library/mysql/blob/01f90d87012e46cd174073bba02d64e9fc693ed3/8.4/Dockerfile.oracle).
The image layers and installed programs are test-only and are not bundled in
RouteContract's Release JARs.
That exact review is owned by the RouteContract maintainers and expires
2026-08-27; it must be resolved, renewed with new evidence or removed before
then.

The example also resolves transitive dependencies of the components above.
Generate the aggregate CycloneDX SBOM to obtain the exact resolved graph for a
specific build:

```bash
./gradlew --no-daemon --no-build-cache validateOfficialCycloneDxSbom
```

## Reviewed test-only transitive metadata

These components are reached only through the MySQL example/test graph in the
verified profiles; they are not dependencies in the generated published POM
and are not bundled in the thin JAR.

| Component | Version | Reviewed license metadata | Upstream basis |
|---|---:|---|---|
| Jakarta Transaction API | 1.3.3 | `EPL-2.0 OR (GPL-2.0-only WITH Classpath-exception-2.0)` | [tagged NOTICE](https://github.com/eclipse-ee4j/jta-api/blob/1.3.3/NOTICE.md) |
| JNA | 5.13.0 | `(Apache-2.0 OR LGPL-2.1-or-later) AND MIT` | [tagged JNA license](https://github.com/java-native-access/jna/blob/5.13.0/LICENSE) and [embedded libffi license](https://github.com/java-native-access/jna/blob/5.13.0/native/libffi/LICENSE) |
| JTS Core | 1.19.0 | `EPL-2.0 OR BSD-3-Clause` | [tagged JTS license choices](https://github.com/locationtech/jts/blob/1.19.0/LICENSES.md) |
| JTS I/O Common | 1.19.0 | `(EPL-2.0 OR BSD-3-Clause) AND Apache-2.0` | [tagged JTS license choices](https://github.com/locationtech/jts/blob/1.19.0/LICENSES.md) and [Apache-licensed Mahout-derived `Varint.java`](https://github.com/locationtech/jts/blob/1.19.0/modules/io/common/src/main/java/org/locationtech/jts/io/twkb/Varint.java) |

The exact JTS I/O Common 1.19.0 sources artifact contains nine Java source
files. Eight carry the JTS project dual-license header; `Varint.java`, whose
class is present in the resolved binary JAR, carries an Apache-2.0 header and
identifies Apache Mahout 0.8 as its origin. The reviewed binary and sources JAR
SHA-256 values are respectively
`e0f0c62024d4282f5f905de1abd2cc96f975a51d9e8d98254234fa14b16bbe9b`
and `c367d87dc525a5d9b85e2751e3b0e14ea018165b45aef3d2642c857d49f53804`.
Those artifacts contain no `LICENSE` or `NOTICE`; the inherited POM lists only
the JTS dual licenses; tagged `LICENSES.md` omits Mahout; and the Apache header
refers to an ASF `NOTICE` absent from the JTS tag. The review pins the official
[Mahout 0.8 source archive](https://archive.apache.org/dist/mahout/0.8/mahout-distribution-0.8-src.tar.gz)
at SHA-256
`0ff823d5c898880f0a00df52f72f0a9af1d2fc502700780eef20e91b4161504b`;
its top-level `NOTICE.txt` has SHA-256
`5e81cc7357b3c9a710860c4b66ac09c3322b2ac5ae914f4e07bfc36896e13c47`.
That proves the originating ASF notice exists, but it does not resolve how the
copied source's notice should be carried by the JTS artifact, whose release
metadata omits it. The expression is therefore concluded while the JTS
redistribution notice remains an exact manual-review item expiring 2026-08-27.

That upstream metadata gap remains disclosed and is not treated as upstream
license clearance. RouteContract's v0.1 distribution boundary is narrower:
the main JAR accepts only `.class` entry paths under the exact RouteContract
package namespace plus an exact metadata allowlist. The sources JAR applies the
same path policy to `.java` entries and requires every declared package to match
its path; the Javadoc JAR has its own exact inventory. The source ZIP rejects
JTS/Mahout-named files and package paths, every compiled `.class`, and every
Java file outside conventional source roots, outside the first-party declared
namespace, or with a path/declaration mismatch. The published POM declares no
direct JTS or Mahout dependency and cannot contain a Maven parent or relocation.
These are name, path, declared-package and dependency gates; they do not determine the
semantic origin of renamed or copied source/class bytes. The final Release gate
must recheck those invariants,
prove the source archive matches the final tagged tracked tree, and retain the
owner's source/provenance review before the non-bundled test/example review is
complete. This does not remove JTS from the test/example dependency graph or
its aggregate SBOM record. The distribution-boundary review reopens if those
payload invariants change or a JTS/Mahout published dependency enters the
release; it is not legal advice or a conclusion about the upstream artifact's
compliance.

The MySQL and standalone fixtures strictly align the following transitive
versions to the dependency-management values published in the Apache
ShardingSphere 5.5.3 parent POM:

- `net.hydromatic:aggdesigner-algorithm:6.1`;
- `net.minidev:json-smart:2.4.10`;
- `net.minidev:accessors-smart:2.4.9`.

That alignment replaces Calcite's requested `aggdesigner-algorithm:6.0` and
JSONPath's requested `json-smart:2.5.0` / `accessors-smart:2.5.0` in the exact
resolved fixture graph. `aggdesigner-algorithm:6.1` also replaces the legacy
`commons-lang:commons-lang:2.4` edge with Commons Lang 3 and Commons Logging
1.3.5. The pinned offline audit currently observes one reviewed advisory in
the remaining test/example-only ShardingSphere SQL Federation graph:

| Coordinate | Advisory | Reviewed upstream status | Policy expiry |
|---|---|---|---:|
| `org.apache.calcite:calcite-core:1.40.0` | [GHSA-c2rv-hwqm-wjpg](https://github.com/advisories/GHSA-c2rv-hwqm-wjpg) | Patched in 1.42.0 | 2026-08-27 |

`test/example-only` describes RouteContract's resolved reachability; it is not
a statement that the findings are harmless or inapplicable. The exceptions
must be removed, replaced by an upgrade/exclusion, or renewed from fresh review
evidence before they expire.

## Build tooling

| Component | Version | Purpose | License |
|---|---:|---|---|
| Gradle Wrapper | 8.14.4 | Reproducible build entry point | Apache-2.0 |
| CycloneDX Gradle plugin | 3.4.0 | CycloneDX 1.6 JSON/XML SBOM generation | Apache-2.0 |
| CycloneDX CLI | 0.33.1 (`b3cfa4b0edc356dad07e0b6e7ab6da0a94af0246`) | Checksum-pinned official JSON/XML structure validation after finalization | Apache-2.0 |
| OSV-Scanner | 2.5.0 | Pinned offline vulnerability scan of the verified aggregate SBOM | Apache-2.0 |

The CycloneDX CLI binary is downloaded only as build tooling, verified against
the platform size and SHA-256 in `security/cyclonedx-cli.lock.json`, and is not
redistributed in the repository, JARs, workflow evidence or public Release.
Version 0.33.1 uses CycloneDX .NET 12.1.2's 1.6.1 schema snapshot. The project
therefore describes this as official CLI structure validation for its bounded
CycloneDX 1.6 profile, not an exact validation claim for specification patch
1.6.2.

OSV-Scanner and its pinned vulnerability database are release-audit inputs.
They are not embedded in the library JAR or copied into the public GitHub
Release. The exact-tag workflow retains only the sanitized, checksummed
`supply-chain-evidence.json`; raw scanner output and the database archive are
not uploaded.

## Contest report builder tooling

These packages generate and validate the organizer DOCX report. They are not
part of RouteContract's published JAR or product runtime. The exact install
closure is pinned in `submission/report-builder-requirements.txt`.

| Component | Version | Purpose | License |
|---|---:|---|---|
| python-docx | 1.2.0 | Retained DOCX template, table and image editing | MIT |
| Pillow | 12.3.0 | PNG format and 1200×675 evidence-asset validation | MIT-CMU |
| lxml | 6.1.1 | OOXML core-property parsing and deterministic sanitization | BSD-3-Clause |
| typing_extensions | 4.16.0 | Runtime compatibility dependency required by python-docx | PSF-2.0 |
| certifi | 2026.7.22 | Pinned Mozilla CA bundle for final public-evidence HTTPS verification | MPL-2.0 |

License identifiers and names above were checked against the projects' Maven
metadata or upstream license files. For the final tag, repeat all of these
manual checks from the tagged clean tree:

1. Inspect the main, sources and Javadoc JARs plus generated POM and runtime
   lock to re-prove which files and dependencies are actually distributed.
2. Regenerate all three JSON/XML SBOM pairs; confirm coordinates, artifact
   hashes, review properties/external references, JSON/XML equivalence and
   dependency reachability.
3. Re-fetch exact-version upstream POM, JAR, `LICENSE` and `NOTICE` files for
   Connector/J, Jakarta Transaction API, JNA (including libffi) and JTS.
4. Re-resolve the OCI index for the pinned MySQL digest and inspect the selected
   platform image/package legal notices; do not infer one image-wide license
   from the MySQL server license alone.
5. Refresh the pinned OSV database, re-run the exact-revision gate, and review
   every advisory and every exception's expiry/fixed-version data.

Dependency metadata can be incomplete. This inventory and any required copied
notices must be updated when the resolved graph, distributed payload or
upstream legal files change. This factual inventory is not legal advice.
