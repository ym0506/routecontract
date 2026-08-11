# Third-party software

RouteContract is licensed under Apache-2.0. The dependencies below keep their
own licenses. This file is a human-readable inventory of the dependencies
declared directly by this repository as of 2026-08-11; it is not a substitute
for the machine-readable SBOM or the license text shipped by each dependency.

RouteContract does not shade or copy these dependencies into its library JAR.
The MySQL example's dependencies and container image are test-only and are not
part of the published library artifact.

## Published library

| Component | Version | Gradle scope | License |
|---|---:|---|---|
| Apache ShardingSphere `shardingsphere-infra-executor` | 5.5.3 | `compileOnly` (also `testImplementation`) | Apache-2.0 |
| Alibaba TransmittableThreadLocal | 2.14.2 | `implementation` | Apache-2.0 |
| Jackson Core (`tools.jackson.core`) | 3.1.5 | `implementation` | Apache-2.0 |

## Tests and MySQL example

| Component | Version | Gradle scope | License |
|---|---:|---|---|
| Apache ShardingSphere JDBC and explicitly declared runtime modules | 5.5.3 | `testImplementation` / `testRuntimeOnly` | Apache-2.0 |
| JUnit Jupiter and JUnit Platform Launcher (managed by JUnit BOM) | 5.14.3 / 1.14.3 | `testImplementation` / `testRuntimeOnly` | EPL-2.0 |
| Testcontainers JUnit Jupiter and MySQL modules | 1.21.4 | `testImplementation` | MIT |
| datasource-proxy | 1.11.0 | `testImplementation` (empirical comparison only) | MIT |
| HikariCP | 6.2.1 | `testRuntimeOnly` | Apache-2.0 |
| MySQL Connector/J | 26.7.0 | `testRuntimeOnly` | `GPL-2.0-only WITH Universal-FOSS-exception-1.0` |
| SLF4J Simple | 2.0.17 | `testRuntimeOnly` | MIT |
| MySQL Community Server container image (`mysql:8.4.11@sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb`) | 8.4.11 | Testcontainers runtime | `GPL-2.0-only`; see the image and MySQL distribution notices for bundled components |

The example also resolves transitive dependencies of the components above.
Generate the aggregate CycloneDX SBOM to obtain the exact resolved graph for a
specific build:

```bash
./gradlew --no-daemon --no-build-cache prepareVerifiedSbom
```

## Build tooling

| Component | Version | Purpose | License |
|---|---:|---|---|
| Gradle Wrapper | 8.14.4 | Reproducible build entry point | Apache-2.0 |
| CycloneDX Gradle plugin | 3.4.0 | CycloneDX 1.6 JSON/XML SBOM generation | Apache-2.0 |

License identifiers and names above were checked against the projects' Maven
metadata or upstream license files. Before a release, review the generated
SBOM and the license/NOTICE files from the resolved artifacts; dependency
metadata can be incomplete and this inventory must be updated when declared
versions or scopes change.
