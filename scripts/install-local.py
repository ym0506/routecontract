#!/usr/bin/env python3
"""Install the checked v0.1.2 release and print normal test dependency configuration."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
from xml.sax.saxutils import escape


if sys.version_info < (3, 10):
    raise SystemExit("RouteContract installation requires Python 3.10 or newer.")

_spec = importlib.util.spec_from_file_location(
    "routecontract_public_installer", Path(__file__).with_name("install-public-v0_1_2.py"))
INSTALLER = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(INSTALLER)

GROUP = "io.github.ym0506.routecontract"
ARTIFACT = "routecontract-shardingsphere-5.5"
VERSION = INSTALLER.VERSION


def gradle_configuration(repository: Path) -> str:
    """Return one configuration valid in both Gradle Groovy and Kotlin DSL."""
    return f'''repositories {{
    exclusiveContent {{
        forRepository {{
            maven {{
                url = uri("{repository.as_uri()}")
                metadataSources {{
                    mavenPom()
                    artifact()
                    ignoreGradleMetadataRedirection()
                }}
            }}
        }}
        filter {{
            includeModule("{GROUP}", "{ARTIFACT}")
        }}
    }}
    mavenCentral()
}}

dependencies {{
    testImplementation("{GROUP}:{ARTIFACT}:{VERSION}")
}}'''


def maven_configuration(repository: Path) -> str:
    """Return project fragments using a file repository and a test-scoped dependency."""
    return f'''<repositories>
  <repository>
    <id>routecontract-local</id>
    <url>{escape(repository.as_uri())}</url>
    <releases><checksumPolicy>fail</checksumPolicy></releases>
    <snapshots><enabled>false</enabled></snapshots>
  </repository>
</repositories>

<dependencies>
  <dependency>
    <groupId>{GROUP}</groupId>
    <artifactId>{ARTIFACT}</artifactId>
    <version>{VERSION}</version>
    <scope>test</scope>
  </dependency>
</dependencies>'''


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Install released v0.1.2 with existing integrity checks, then print test build configuration.")
    parser.add_argument("--repository", type=Path,
                        default=Path.cwd() / ".routecontract-v0.1.2",
                        help="new destination (absolute or relative); its parent must already exist")
    parser.add_argument("--format", choices=("gradle", "gradle-kotlin", "maven"), default="gradle",
                        help="build configuration to print after installation (default: gradle)")
    arguments = parser.parse_args(argv)
    # Do not resolve away a symlink at the requested target. The original
    # installer checks absence and canonicalizes ancestors before reservation.
    repository = arguments.repository.absolute()
    try:
        INSTALLER.install_public_release(repository)
    except (INSTALLER.PublicInstallError, OSError) as error:
        print(f"Installation failed: {error}", file=sys.stderr)
        print("Keep any failed target for inspection and retry with a new --repository.",
              file=sys.stderr)
        return 2
    print("\nAdd this configuration to your test build; retain your existing ShardingSphere dependency.")
    if arguments.format == "maven":
        print("Merge the repository and dependency entries into existing <repositories> and <dependencies> elements.")
        print("Do not duplicate those elements in pom.xml.")
    print("The local directory must remain available to that build. See docs/install-local.md.\n")
    renderer = maven_configuration if arguments.format == "maven" else gradle_configuration
    print(renderer(repository.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
