#!/usr/bin/env python3
"""Acceptance tests for the final SBOM, license, and OSV policy gate."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import copy
from datetime import datetime, timedelta, timezone
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPOSITORY_ROOT / "scripts" / "verify-supply-chain-policy.py"
SCANNER_LOCK = REPOSITORY_ROOT / "security" / "osv-scanner.lock.json"
REVISION = "a" * 40
CYCLONEDX_XML_NAMESPACE = "http://cyclonedx.org/schema/bom/1.6"
JTS_EXPRESSIONS = {
    "jts-core": "EPL-2.0 OR BSD-3-Clause",
}
REQUIRED_EXAMPLE_COORDINATES = (
    ("org.apache.shardingsphere", "shardingsphere-jdbc", "5.5.3"),
    ("org.apache.calcite", "calcite-core", "1.42.0"),
    ("org.apache.calcite", "calcite-linq4j", "1.42.0"),
)


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def replace_component_purl(
    document: dict[str, object], old_purl: str, new_purl: str
) -> None:
    candidates = [document["metadata"]["component"], *document["components"]]
    for component in candidates:
        if component.get("purl") == old_purl:
            component["purl"] = new_purl
            component["bom-ref"] = new_purl
    for record in document["dependencies"]:
        if record["ref"] == old_purl:
            record["ref"] = new_purl
        record["dependsOn"] = [
            new_purl if target == old_purl else target
            for target in record["dependsOn"]
        ]


def apache_component(purl: str, group: str, name: str, version: str) -> dict[str, object]:
    return {
        "type": "library",
        "bom-ref": purl,
        "group": group,
        "name": name,
        "version": version,
        "purl": purl,
        "licenses": [
            {
                "license": {
                    "id": "Apache-2.0",
                    "url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
                }
            }
        ],
    }


def write_xml_pair(path: Path, document: dict[str, object]) -> None:
    ET.register_namespace("", CYCLONEDX_XML_NAMESPACE)
    qname = lambda name: f"{{{CYCLONEDX_XML_NAMESPACE}}}{name}"
    root = ET.Element(
        qname("bom"),
        {
            "serialNumber": document["serialNumber"],
            "version": str(document["version"]),
        },
    )

    def append_component(parent: ET.Element, component: dict[str, object]) -> None:
        element = ET.SubElement(
            parent,
            qname("component"),
            {"type": component["type"], "bom-ref": component["bom-ref"]},
        )
        for field in ("group", "name", "version", "scope"):
            if field in component:
                ET.SubElement(element, qname(field)).text = component[field]
        if component.get("hashes"):
            hashes = ET.SubElement(element, qname("hashes"))
            for item in component["hashes"]:
                ET.SubElement(hashes, qname("hash"), {"alg": item["alg"]}).text = item[
                    "content"
                ]
        if "licenses" in component:
            licenses = ET.SubElement(element, qname("licenses"))
            for choice in component["licenses"]:
                if "expression" in choice:
                    ET.SubElement(licenses, qname("expression")).text = choice["expression"]
                else:
                    license_element = ET.SubElement(licenses, qname("license"))
                    license_value = choice["license"]
                    identifier = "id" if "id" in license_value else "name"
                    ET.SubElement(license_element, qname(identifier)).text = license_value[
                        identifier
                    ]
                    if "url" in choice["license"]:
                        ET.SubElement(license_element, qname("url")).text = choice["license"]["url"]
        ET.SubElement(element, qname("purl")).text = component["purl"]
        if component.get("externalReferences"):
            references = ET.SubElement(element, qname("externalReferences"))
            for item in component["externalReferences"]:
                reference = ET.SubElement(
                    references, qname("reference"), {"type": item["type"]}
                )
                ET.SubElement(reference, qname("url")).text = item["url"]
        if component.get("properties"):
            properties = ET.SubElement(element, qname("properties"))
            for item in component["properties"]:
                ET.SubElement(
                    properties, qname("property"), {"name": item["name"]}
                ).text = item["value"]

    metadata = ET.SubElement(root, qname("metadata"))
    ET.SubElement(metadata, qname("timestamp")).text = document["metadata"][
        "timestamp"
    ]
    tools = ET.SubElement(metadata, qname("tools"))
    tool_components = ET.SubElement(tools, qname("components"))
    tool = ET.SubElement(
        tool_components, qname("component"), {"type": "application"}
    )
    ET.SubElement(tool, qname("author")).text = "CycloneDX"
    ET.SubElement(tool, qname("name")).text = "cyclonedx-gradle-plugin"
    ET.SubElement(tool, qname("version")).text = "3.4.0"
    append_component(metadata, document["metadata"]["component"])
    if document["metadata"].get("licenses"):
        document_licenses = ET.SubElement(metadata, qname("licenses"))
        for choice in document["metadata"]["licenses"]:
            license_element = ET.SubElement(document_licenses, qname("license"))
            license_value = choice["license"]
            identifier = "id" if "id" in license_value else "name"
            ET.SubElement(license_element, qname(identifier)).text = license_value[
                identifier
            ]
            if "url" in license_value:
                ET.SubElement(license_element, qname("url")).text = license_value[
                    "url"
                ]
    components = ET.SubElement(root, qname("components"))
    for component in document["components"]:
        append_component(components, component)
    dependencies = ET.SubElement(root, qname("dependencies"))
    for record in document.get("dependencies", []):
        dependency = ET.SubElement(dependencies, qname("dependency"), {"ref": record["ref"]})
        for target in record["dependsOn"]:
            ET.SubElement(dependency, qname("dependency"), {"ref": target})
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


class SupplyChainPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        self.sbom = self.root / "bom.json"
        self.sbom_xml = self.root / "bom.xml"
        self.published_sbom = self.root / "published-bom.json"
        self.published_sbom_xml = self.root / "published-bom.xml"
        self.example_sbom = self.root / "example-bom.json"
        self.example_sbom_xml = self.root / "example-bom.xml"
        self.published_pom = self.root / "pom.xml"
        self.published_lock = self.root / "published-gradle.lockfile"
        self.policy = self.root / "policy.json"
        self.inventory = self.root / "gradle.lockfile"
        self.raw_scan = self.root / "osv-raw.json"
        self.scanner_config = self.root / "osv-scanner.toml"
        self.scanner_lock = self.root / "osv-scanner.lock.json"
        self.evidence = self.root / "evidence.json"

        safe = apache_component(
            "pkg:maven/com.example/safe@1.0?type=jar", "com.example", "safe", "1.0"
        )
        safe["properties"] = [
            {"name": "cdx:maven:package:test", "value": "false"}
        ]
        vulnerable = apache_component(
            "pkg:maven/net.minidev/json-smart@2.4.10?type=jar",
            "net.minidev",
            "json-smart",
            "2.4.10",
        )
        vulnerable["properties"] = [
            {"name": "cdx:maven:package:test", "value": "true"}
        ]
        jts = {
            "type": "library",
            "bom-ref": "pkg:maven/org.locationtech.jts/jts-core@1.19.0?type=jar",
            "group": "org.locationtech.jts",
            "name": "jts-core",
            "version": "1.19.0",
            "purl": "pkg:maven/org.locationtech.jts/jts-core@1.19.0?type=jar",
            "licenses": [{"expression": "EPL-2.0 OR BSD-3-Clause"}],
            "properties": [
                {"name": "cdx:maven:package:test", "value": "true"}
            ],
        }
        required_example_components = [
            apache_component(
                f"pkg:maven/{group}/{name}@{version}?type=jar",
                group,
                name,
                version,
            )
            for group, name, version in REQUIRED_EXAMPLE_COORDINATES
        ]
        for component in required_example_components:
            component["properties"] = [
                {"name": "cdx:maven:package:test", "value": "true"}
            ]
        connector = {
            "type": "library",
            "bom-ref": "pkg:maven/com.mysql/mysql-connector-j@26.7.0?type=jar",
            "group": "com.mysql",
            "name": "mysql-connector-j",
            "version": "26.7.0",
            "purl": "pkg:maven/com.mysql/mysql-connector-j@26.7.0?type=jar",
            "licenses": [
                {"expression": "GPL-2.0-only WITH Universal-FOSS-exception-1.0"}
            ],
            "properties": [
                {"name": "cdx:maven:package:test", "value": "true"}
            ],
        }
        container_purl = (
            "pkg:oci/mysql@sha256%3A"
            "b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb"
            "?repository_url=registry-1.docker.io&tag=8.4.11"
        )
        container = {
            "type": "container",
            "bom-ref": container_purl,
            "name": "mysql",
            "version": "8.4.11",
            "purl": container_purl,
            "scope": "excluded",
            "hashes": [
                {
                    "alg": "SHA-256",
                    "content": (
                        "b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37"
                        "fe8a23eb857fd3fb"
                    ),
                }
            ],
            "externalReferences": [
                {
                    "type": "documentation",
                    "url": "https://dev.mysql.com/doc/refman/8.4/en/preface.html",
                }
            ],
            "properties": [
                {
                    "name": "routecontract:license-review",
                    "value": "manual-review-required",
                },
                {"name": "routecontract:usage", "value": "test-only"},
            ],
        }
        self.sbom_document = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "timestamp": "2026-08-13T18:10:30Z",
                "tools": {
                    "components": [
                        {
                            "type": "application",
                            "author": "CycloneDX",
                            "name": "cyclonedx-gradle-plugin",
                            "version": "3.4.0",
                        }
                    ]
                },
                "licenses": [
                    {
                        "license": {
                            "id": "Apache-2.0",
                            "url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
                        }
                    }
                ],
                "component": {
                    "type": "library",
                    "bom-ref": "pkg:maven/io.github.ym0506.routecontract/routecontract@0.1.0?project_path=%3A",
                    "group": "io.github.ym0506.routecontract",
                    "name": "routecontract",
                    "version": "0.1.0",
                    "purl": "pkg:maven/io.github.ym0506.routecontract/routecontract@0.1.0?project_path=%3A",
                    "licenses": [
                        {
                            "license": {
                                "id": "Apache-2.0",
                                "url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
                            }
                        }
                    ],
                }
            },
            "components": [
                apache_component(
                    "pkg:maven/io.github.ym0506.routecontract/routecontract-shardingsphere-5.5@0.1.0?project_path=%3Aroutecontract-shardingsphere-5.5",
                    "io.github.ym0506.routecontract",
                    "routecontract-shardingsphere-5.5",
                    "0.1.0",
                ),
                apache_component(
                    "pkg:maven/io.github.ym0506.routecontract/mysql-example@0.1.0?project_path=%3Amysql-example",
                    "io.github.ym0506.routecontract",
                    "mysql-example",
                    "0.1.0",
                ),
                container,
                connector,
                vulnerable,
                jts,
                *required_example_components,
                safe,
            ],
            "dependencies": [],
        }
        self.published_sbom_document = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "timestamp": "2026-08-13T18:10:30Z",
                "tools": {
                    "components": [
                        {
                            "type": "application",
                            "author": "CycloneDX",
                            "name": "cyclonedx-gradle-plugin",
                            "version": "3.4.0",
                        }
                    ]
                },
                "licenses": [
                    {
                        "license": {
                            "id": "Apache-2.0",
                            "url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
                        }
                    }
                ],
                "component": {
                    "type": "library",
                    "bom-ref": "pkg:maven/io.github.ym0506.routecontract/routecontract-shardingsphere-5.5@0.1.0?project_path=%3Aroutecontract-shardingsphere-5.5",
                    "group": "io.github.ym0506.routecontract",
                    "name": "routecontract-shardingsphere-5.5",
                    "version": "0.1.0",
                    "purl": "pkg:maven/io.github.ym0506.routecontract/routecontract-shardingsphere-5.5@0.1.0?project_path=%3Aroutecontract-shardingsphere-5.5",
                    "licenses": [
                        {
                            "license": {
                                "id": "Apache-2.0",
                                "url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
                            }
                        }
                    ],
                }
            },
            "components": [copy.deepcopy(safe)],
            "dependencies": [
                {
                    "ref": "pkg:maven/io.github.ym0506.routecontract/routecontract-shardingsphere-5.5@0.1.0?project_path=%3Aroutecontract-shardingsphere-5.5",
                    "dependsOn": [
                        "pkg:maven/com.example/safe@1.0?type=jar"
                    ],
                },
                {
                    "ref": "pkg:maven/com.example/safe@1.0?type=jar",
                    "dependsOn": [],
                },
            ],
        }
        self.example_sbom_document = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "timestamp": "2026-08-13T18:10:30Z",
                "tools": {
                    "components": [
                        {
                            "type": "application",
                            "author": "CycloneDX",
                            "name": "cyclonedx-gradle-plugin",
                            "version": "3.4.0",
                        }
                    ]
                },
                "licenses": [
                    {
                        "license": {
                            "id": "Apache-2.0",
                            "url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
                        }
                    }
                ],
                "component": {
                    "type": "library",
                    "bom-ref": "pkg:maven/io.github.ym0506.routecontract/mysql-example@0.1.0?project_path=%3Amysql-example",
                    "group": "io.github.ym0506.routecontract",
                    "name": "mysql-example",
                    "version": "0.1.0",
                    "purl": "pkg:maven/io.github.ym0506.routecontract/mysql-example@0.1.0?project_path=%3Amysql-example",
                    "licenses": [
                        {
                            "license": {
                                "id": "Apache-2.0",
                                "url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
                            }
                        }
                    ],
                }
            },
            "components": [
                apache_component(
                    "pkg:maven/io.github.ym0506.routecontract/routecontract-shardingsphere-5.5@0.1.0?project_path=%3Aroutecontract-shardingsphere-5.5",
                    "io.github.ym0506.routecontract",
                    "routecontract-shardingsphere-5.5",
                    "0.1.0",
                ),
                copy.deepcopy(container),
                copy.deepcopy(connector),
                copy.deepcopy(vulnerable),
                copy.deepcopy(jts),
                *copy.deepcopy(required_example_components),
            ],
            "dependencies": [],
        }
        self.example_sbom_document["components"][0]["properties"] = [
            {"name": "cdx:maven:package:test", "value": "true"}
        ]
        for component in self.sbom_document["components"][:2]:
            component["properties"] = [
                {"name": "cdx:maven:package:test", "value": "false"}
            ]
        for document in (self.sbom_document, self.example_sbom_document):
            root_purl = document["metadata"]["component"]["purl"]
            component_purls = [component["purl"] for component in document["components"]]
            document["dependencies"] = [
                {"ref": root_purl, "dependsOn": component_purls},
                *[
                    {"ref": component_purl, "dependsOn": []}
                    for component_purl in component_purls
                ],
            ]
        self.policy_document = {
            "schemaVersion": 3,
            "allowedLicenseIds": ["Apache-2.0"],
            "licenseExceptions": [
                {
                    "kind": "expression",
                    "license": "GPL-2.0-only WITH Universal-FOSS-exception-1.0",
                    "purl": "pkg:maven/com.mysql/mysql-connector-j@26.7.0",
                    "scope": "test-runtime",
                    "url": None,
                },
                {
                    "kind": "expression",
                    "license": "EPL-2.0 OR BSD-3-Clause",
                    "purl": "pkg:maven/org.locationtech.jts/jts-core@1.19.0",
                    "scope": "test-runtime",
                    "url": None,
                },
            ],
            "licenseReviewExceptions": [
                {
                    "action": (
                        "re-review immediately if the MySQL OCI digest, selected "
                        "platform, embedded LICENSE/INFO_SRC evidence, or test-container "
                        "use boundary changes; otherwise resolve, renew with new "
                        "evidence, or remove the MySQL OCI package-level license review "
                        "before the 2026-12-05 expiry"
                    ),
                    "componentName": "mysql",
                    "componentVersion": "8.4.11",
                    "documentationUrl": (
                        "https://dev.mysql.com/doc/refman/8.4/en/preface.html"
                    ),
                    "expires": "2026-12-05",
                    "owner": "RouteContract maintainers",
                    "purl": container_purl,
                    "rationaleCode": "MYSQL_OCI_PACKAGE_LICENSE_CONCLUSION_INCOMPLETE",
                    "reviewedAt": "2026-08-24",
                    "scope": "test-container",
                    "sha256": (
                        "b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37"
                        "fe8a23eb857fd3fb"
                    ),
                    "status": "manual-review-required",
                },
            ],
            "vulnerabilityExceptions": [],
        }
        for index, document in enumerate(
            (self.sbom_document, self.published_sbom_document, self.example_sbom_document),
            start=1,
        ):
            document["serialNumber"] = f"urn:uuid:00000000-0000-0000-0000-{index:012d}"
        self.raw_scan_document = {
            "results": [
                {
                    "source": {"path": "/not-published/gradle.lockfile", "type": "lockfile"},
                    "packages": [
                        {
                            "package": {
                                "name": "net.minidev:json-smart",
                                "version": "2.4.10",
                                "ecosystem": "Maven",
                            },
                        },
                        {
                            "package": {
                                "name": "com.mysql:mysql-connector-j",
                                "version": "26.7.0",
                                "ecosystem": "Maven",
                            }
                        },
                        {
                            "package": {
                                "name": "com.example:safe",
                                "version": "1.0",
                                "ecosystem": "Maven",
                            }
                        },
                        {
                            "package": {
                                "name": "org.locationtech.jts:jts-core",
                                "version": "1.19.0",
                                "ecosystem": "Maven",
                            }
                        },
                        {
                            "package": {
                                "name": "org.apache.shardingsphere:shardingsphere-jdbc",
                                "version": "5.5.3",
                                "ecosystem": "Maven",
                            }
                        },
                        {
                            "package": {
                                "name": "org.apache.calcite:calcite-core",
                                "version": "1.42.0",
                                "ecosystem": "Maven",
                            }
                        },
                        {
                            "package": {
                                "name": "org.apache.calcite:calcite-linq4j",
                                "version": "1.42.0",
                                "ecosystem": "Maven",
                            }
                        },
                        {
                            "package": {
                                "name": "io.github.ym0506.routecontract:mysql-example",
                                "version": "0.1.0",
                                "ecosystem": "Maven",
                            }
                        },
                        {
                            "package": {
                                "name": "io.github.ym0506.routecontract:routecontract-shardingsphere-5.5",
                                "version": "0.1.0",
                                "ecosystem": "Maven",
                            }
                        },
                    ],
                }
            ],
            "experimental_config": {"licenses": {"summary": False, "allowlist": None}},
        }
        self.write_fixture()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_fixture(self) -> None:
        write_json(self.sbom, self.sbom_document)
        write_xml_pair(self.sbom_xml, self.sbom_document)
        write_json(self.published_sbom, self.published_sbom_document)
        write_xml_pair(self.published_sbom_xml, self.published_sbom_document)
        write_json(self.example_sbom, self.example_sbom_document)
        write_xml_pair(self.example_sbom_xml, self.example_sbom_document)
        write_json(self.policy, self.policy_document)
        write_json(self.raw_scan, self.raw_scan_document)
        self.scanner_config.write_bytes(b"")
        self.scanner_lock.write_bytes(SCANNER_LOCK.read_bytes())
        self.published_pom.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<project xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd" xmlns="http://maven.apache.org/POM/4.0.0"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <!-- This module was also published with a richer model, Gradle metadata,  -->
  <!-- which should be used instead. Do not delete the following line which  -->
  <!-- is to indicate to Gradle or any Gradle module metadata file consumer  -->
  <!-- that they should prefer consuming it instead. -->
  <!-- do_not_remove: published-with-gradle-metadata -->
  <modelVersion>4.0.0</modelVersion>
  <groupId>io.github.ym0506.routecontract</groupId>
  <artifactId>routecontract-shardingsphere-5.5</artifactId>
  <version>0.1.0</version>
  <name>RouteContract for Apache ShardingSphere-JDBC 5.5.3</name>
  <description>Operation-scoped contracts over physical JDBC execution attempts reported by Apache ShardingSphere-JDBC 5.5.3 SQLExecutionHook</description>
  <url>https://github.com/ym0506/routecontract</url>
  <licenses>
    <license>
      <name>The Apache License, Version 2.0</name>
      <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
      <distribution>repo</distribution>
    </license>
  </licenses>
  <developers>
    <developer>
      <id>ym0506</id>
      <name>ym0506</name>
      <email>atat9828@naver.com</email>
      <url>https://github.com/ym0506</url>
    </developer>
  </developers>
  <scm>
    <connection>scm:git:https://github.com/ym0506/routecontract.git</connection>
    <developerConnection>scm:git:ssh://git@github.com/ym0506/routecontract.git</developerConnection>
    <url>https://github.com/ym0506/routecontract</url>
  </scm>
  <dependencies>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>safe</artifactId>
      <version>1.0</version>
      <scope>runtime</scope>
    </dependency>
  </dependencies>
</project>
""",
            encoding="utf-8",
        )
        self.published_lock.write_text(
            "# This is a Gradle generated file for dependency locking.\n"
            "com.example:safe:1.0=compileClasspath,runtimeClasspath\n"
            "empty=annotationProcessor,testAnnotationProcessor\n",
            encoding="utf-8",
        )

    def inject_test_finding(self) -> None:
        package = self.raw_scan_document["results"][0]["packages"][0]
        package["groups"] = [
            {"ids": ["GHSA-pq2g-wx69-c263"], "max_severity": "7.5"}
        ]
        package["vulnerabilities"] = [
            {
                "id": "GHSA-pq2g-wx69-c263",
                "database_specific": {"severity": "HIGH"},
                "affected": [
                    {
                        "package": {
                            "ecosystem": "Maven",
                            "name": "net.minidev:json-smart",
                            "purl": "pkg:maven/net.minidev/json-smart",
                        },
                        "ranges": [
                            {
                                "type": "ECOSYSTEM",
                                "events": [
                                    {"introduced": "2.4.10"},
                                    {"fixed": "2.5.2"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]

    def run_checker(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CHECKER), *arguments],
            cwd=REPOSITORY_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def prepare_inventory(self) -> subprocess.CompletedProcess[str]:
        return self.run_checker(
            "inventory",
            "--sbom",
            str(self.sbom),
            "--sbom-xml",
            str(self.sbom_xml),
            "--published-sbom",
            str(self.published_sbom),
            "--published-sbom-xml",
            str(self.published_sbom_xml),
            "--example-sbom",
            str(self.example_sbom),
            "--example-sbom-xml",
            str(self.example_sbom_xml),
            "--published-pom",
            str(self.published_pom),
            "--published-lock",
            str(self.published_lock),
            "--policy",
            str(self.policy),
            "--output",
            str(self.inventory),
        )

    def verify(self) -> subprocess.CompletedProcess[str]:
        return self.run_checker(
            "verify",
            "--sbom",
            str(self.sbom),
            "--sbom-xml",
            str(self.sbom_xml),
            "--published-sbom",
            str(self.published_sbom),
            "--published-sbom-xml",
            str(self.published_sbom_xml),
            "--example-sbom",
            str(self.example_sbom),
            "--example-sbom-xml",
            str(self.example_sbom_xml),
            "--published-pom",
            str(self.published_pom),
            "--published-lock",
            str(self.published_lock),
            "--policy",
            str(self.policy),
            "--scanner-lock",
            str(self.scanner_lock),
            "--scanner-config",
            str(self.scanner_config),
            "--scanner-platform",
            "linux-x86_64",
            "--inventory",
            str(self.inventory),
            "--raw-scan",
            str(self.raw_scan),
            "--revision",
            REVISION,
            "--source-tree",
            "b" * 40,
            "--output",
            str(self.evidence),
        )

    def test_generates_sorted_inventory_and_sanitized_evidence(self) -> None:
        prepared = self.prepare_inventory()
        self.assertEqual(0, prepared.returncode, prepared.stderr)
        self.assertEqual(
            """# Generated from the verified aggregate CycloneDX SBOM; do not edit.
com.example:safe:1.0=aggregateSbom
com.mysql:mysql-connector-j:26.7.0=aggregateSbom
io.github.ym0506.routecontract:mysql-example:0.1.0=aggregateSbom
io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0=aggregateSbom
net.minidev:json-smart:2.4.10=aggregateSbom
org.apache.calcite:calcite-core:1.42.0=aggregateSbom
org.apache.calcite:calcite-linq4j:1.42.0=aggregateSbom
org.apache.shardingsphere:shardingsphere-jdbc:5.5.3=aggregateSbom
org.locationtech.jts:jts-core:1.19.0=aggregateSbom
empty=
""",
            self.inventory.read_text(encoding="utf-8"),
        )

        verified = self.verify()
        self.assertEqual(0, verified.returncode, verified.stderr)
        evidence = json.loads(self.evidence.read_text(encoding="utf-8"))
        self.assertEqual(1, evidence["schemaVersion"])
        self.assertEqual(REVISION, evidence["revision"])
        self.assertEqual("b" * 40, evidence["sourceTree"])
        self.assertEqual(9, evidence["sbom"]["mavenPackageCount"])
        self.assertEqual(11, evidence["sbom"]["xmlComponentCount"])
        self.assertEqual(1, evidence["sbom"]["unresolvedLicenseReviewCount"])
        license_review_keys = {
            "action",
            "componentName",
            "componentVersion",
            "expires",
            "owner",
            "purl",
            "rationaleCode",
            "reviewedAt",
            "scope",
            "status",
        }
        self.assertEqual(
            [license_review_keys],
            [set(review) for review in evidence["sbom"]["licenseReviews"]],
        )
        self.assertEqual(
            ["mysql"],
            [
                review["componentName"]
                for review in evidence["sbom"]["licenseReviews"]
            ],
        )
        self.assertEqual(
            [
                {
                    key: review[key]
                    for key in (
                        "action",
                        "componentName",
                        "componentVersion",
                        "expires",
                        "owner",
                        "purl",
                        "rationaleCode",
                        "reviewedAt",
                        "scope",
                        "status",
                    )
                }
                for review in self.policy_document["licenseReviewExceptions"]
            ],
            evidence["sbom"]["licenseReviews"],
        )
        self.assertEqual(
            evidence["sbom"]["unresolvedLicenseReviewCount"],
            len(evidence["sbom"]["licenseReviews"]),
        )
        self.assertEqual(
            hashlib.sha256(self.policy.read_bytes()).hexdigest(),
            evidence["sbom"]["policySha256"],
        )
        self.assertRegex(evidence["sbom"]["xmlSha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(0, evidence["vulnerabilities"]["findingCount"])
        self.assertEqual(0, evidence["vulnerabilities"]["acceptedExceptionCount"])
        self.assertEqual([], evidence["vulnerabilities"]["findings"])
        self.assertEqual(0, evidence["vulnerabilities"]["unreviewedCount"])
        self.assertEqual(1, evidence["publishedModule"]["mavenPackageCount"])
        self.assertEqual(1, evidence["publishedModule"]["pomDependencyCount"])
        self.assertRegex(
            evidence["publishedModule"]["xmlSha256"], r"^[0-9a-f]{64}$"
        )
        self.assertRegex(
            evidence["publishedModule"]["dependencyLockSha256"],
            r"^[0-9a-f]{64}$",
        )
        self.assertRegex(
            evidence["publishedModule"]["resolvedProfileSha256"], r"^[0-9a-f]{64}$"
        )
        self.assertRegex(
            evidence["exampleProfile"]["resolvedProfileSha256"], r"^[0-9a-f]{64}$"
        )
        self.assertGreater(evidence["scanner"]["binarySize"], 0)
        self.assertTrue(evidence["scanner"]["binaryUrl"].startswith("https://"))
        self.assertGreater(evidence["scanner"]["database"]["size"], 0)
        self.assertIn(
            "generation=", evidence["scanner"]["database"]["url"]
        )
        self.assertEqual(
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855",
            evidence["scanner"]["scannerConfigSha256"],
        )
        self.assertNotIn("path", self.evidence.read_text(encoding="utf-8"))
        self.assertNotIn("details", self.evidence.read_text(encoding="utf-8"))

    def test_rejects_finding_with_escaped_whitespace_in_advisory_prose(self) -> None:
        self.inject_test_finding()
        vulnerability = self.raw_scan_document["results"][0]["packages"][0][
            "vulnerabilities"
        ][0]
        vulnerability["details"] = "First paragraph.\n\nSecond\tparagraph.\r\n"
        self.write_fixture()
        prepared = self.prepare_inventory()
        self.assertEqual(0, prepared.returncode, prepared.stderr)

        verified = self.verify()

        self.assertNotEqual(0, verified.returncode)
        self.assertIn(
            "vulnerability findings are forbidden by the pinned policy",
            verified.stderr,
        )

    def test_rejects_nul_in_raw_osv_advisory_prose(self) -> None:
        self.inject_test_finding()
        vulnerability = self.raw_scan_document["results"][0]["packages"][0][
            "vulnerabilities"
        ][0]
        vulnerability["details"] = "unsafe\x00description"
        self.write_fixture()
        prepared = self.prepare_inventory()
        self.assertEqual(0, prepared.returncode, prepared.stderr)

        verified = self.verify()

        self.assertNotEqual(0, verified.returncode)
        self.assertIn("control character", verified.stderr)

    def test_rejects_stale_xml_pair(self) -> None:
        tree = ET.parse(self.example_sbom_xml)
        tree.getroot().set("serialNumber", "urn:uuid:stale")
        tree.write(self.example_sbom_xml, encoding="utf-8", xml_declaration=True)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("JSON/XML serial numbers differ", result.stderr)

    def test_rejects_json_xml_root_swap(self) -> None:
        qname = lambda name: f"{{{CYCLONEDX_XML_NAMESPACE}}}{name}"
        tree = ET.parse(self.sbom_xml)
        root = tree.getroot()
        metadata = root.find(qname("metadata"))
        components = root.find(qname("components"))
        self.assertIsNotNone(metadata)
        self.assertIsNotNone(components)
        metadata_component = metadata.find(qname("component"))
        first_component = components.find(qname("component"))
        self.assertIsNotNone(metadata_component)
        self.assertIsNotNone(first_component)
        metadata.remove(metadata_component)
        components.remove(first_component)
        metadata.append(first_component)
        components.insert(0, metadata_component)
        tree.write(self.sbom_xml, encoding="utf-8", xml_declaration=True)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("XML metadata has an unsupported shape", result.stderr)

    def test_rejects_json_xml_bom_version_drift(self) -> None:
        self.sbom_document["version"] = 2
        write_json(self.sbom, self.sbom_document)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("document identity must be CycloneDX version 1", result.stderr)

    def test_rejects_json_xml_component_hash_drift(self) -> None:
        self.sbom_document["components"][-1]["hashes"] = [
            {"alg": "SHA-256", "content": "0" * 64}
        ]
        write_json(self.sbom, self.sbom_document)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("JSON/XML component records differ", result.stderr)

    def test_rejects_unknown_json_component_field(self) -> None:
        self.sbom_document["components"][-1]["notCycloneDx"] = True
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unsupported CycloneDX fields", result.stderr)

    def test_rejects_unknown_json_document_field(self) -> None:
        self.sbom_document["notCycloneDx"] = True
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("document fields differ", result.stderr)

    def test_rejects_unknown_xml_component_element(self) -> None:
        self.write_fixture()
        qname = lambda name: f"{{{CYCLONEDX_XML_NAMESPACE}}}{name}"
        tree = ET.parse(self.sbom_xml)
        component = tree.getroot().find(
            f"{qname('components')}/{qname('component')}"
        )
        self.assertIsNotNone(component)
        ET.SubElement(component, qname("notCycloneDx")).text = "invalid"
        tree.write(self.sbom_xml, encoding="utf-8", xml_declaration=True)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unsupported CycloneDX fields", result.stderr)

    def test_rejects_out_of_order_xml_component_field(self) -> None:
        self.write_fixture()
        qname = lambda name: f"{{{CYCLONEDX_XML_NAMESPACE}}}{name}"
        tree = ET.parse(self.sbom_xml)
        component = tree.getroot().find(
            f"{qname('components')}/{qname('component')}"
        )
        self.assertIsNotNone(component)
        licenses = component.find(qname("licenses"))
        purl = component.find(qname("purl"))
        self.assertIsNotNone(licenses)
        self.assertIsNotNone(purl)
        component.remove(licenses)
        component.insert(list(component).index(purl) + 1, licenses)
        tree.write(self.sbom_xml, encoding="utf-8", xml_declaration=True)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("component child order", result.stderr)

    def test_rejects_conflicting_document_license(self) -> None:
        self.sbom_document["metadata"]["licenses"][0]["license"]["id"] = "MIT"
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("document license is not exact Apache-2.0", result.stderr)

    def test_rejects_unreviewed_vulnerability(self) -> None:
        self.inject_test_finding()
        self.write_fixture()
        self.assertEqual(0, self.prepare_inventory().returncode)

        result = self.verify()

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "vulnerability findings are forbidden by the pinned policy",
            result.stderr,
        )
        self.assertFalse(self.evidence.exists())

    def test_rejects_scanner_package_set_drift(self) -> None:
        self.assertEqual(0, self.prepare_inventory().returncode)
        self.raw_scan_document["results"][0]["packages"].pop()
        self.write_fixture()

        result = self.verify()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("package set does not exactly match", result.stderr)

    def test_rejects_non_maven_aggregate_only_union_drift(self) -> None:
        npm = {
            "type": "library",
            "bom-ref": "pkg:npm/example@1.0.0",
            "name": "example",
            "version": "1.0.0",
            "purl": "pkg:npm/example@1.0.0",
            "licenses": [{"license": {"id": "Apache-2.0"}}],
        }
        self.sbom_document["components"].append(npm)
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unsupported non-Maven component", result.stderr)

    def test_rejects_reachable_non_maven_component_in_both_profiles(self) -> None:
        npm = {
            "type": "library",
            "bom-ref": "pkg:npm/example@1.0.0",
            "name": "example",
            "version": "1.0.0",
            "purl": "pkg:npm/example@1.0.0",
            "licenses": [{"license": {"id": "Apache-2.0"}}],
            "properties": [
                {"name": "cdx:maven:package:test", "value": "true"}
            ],
        }
        for document in (self.sbom_document, self.example_sbom_document):
            document["components"].append(copy.deepcopy(npm))
            document["dependencies"][0]["dependsOn"].append(npm["purl"])
            document["dependencies"].append(
                {"ref": npm["purl"], "dependsOn": []}
            )
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unsupported non-Maven component", result.stderr)

    def test_rejects_cross_role_artifact_hash_drift(self) -> None:
        self.sbom_document["components"][-1]["hashes"] = [
            {"alg": "SHA-256", "content": "a" * 64}
        ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("cross-role component artifact metadata differs", result.stderr)

    def test_rejects_cross_role_license_drift(self) -> None:
        self.policy_document["allowedLicenseIds"].append("MIT")
        self.sbom_document["components"][-1]["licenses"] = [
            {"license": {"id": "MIT"}}
        ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("cross-role component artifact metadata differs", result.stderr)

    def test_rejects_example_component_unreachable_from_root(self) -> None:
        vulnerable_purl = self.example_sbom_document["components"][3]["purl"]
        self.example_sbom_document["dependencies"][0]["dependsOn"].remove(
            vulnerable_purl
        )
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unreachable from its root", result.stderr)

    def test_rejects_aggregate_dangling_dependency_edge(self) -> None:
        self.sbom_document["dependencies"][0]["dependsOn"].append(
            "pkg:maven/com.example/missing@1.0?type=jar"
        )
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("dangling edge", result.stderr)

    def test_rejects_unapproved_component_license(self) -> None:
        self.sbom_document["components"][-1]["licenses"] = [
            {"license": {"id": "GPL-3.0-only"}}
        ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unapproved license", result.stderr)

    def test_rejects_unreviewed_mixed_license_choice(self) -> None:
        self.sbom_document["components"][-1]["licenses"] = [
            {"license": {"id": "Apache-2.0"}},
            {"license": {"id": "GPL-3.0-only"}},
        ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unapproved license", result.stderr)

    def test_rejects_license_choice_with_both_id_and_name(self) -> None:
        self.sbom_document["components"][-1]["licenses"] = [
            {"license": {"id": "Apache-2.0", "name": "Apache License 2.0"}}
        ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("must contain exactly one id or name", result.stderr)

    def test_rejects_named_license_that_impersonates_an_allowed_spdx_id(self) -> None:
        self.sbom_document["components"][-1]["licenses"] = [
            {"license": {"name": "Apache-2.0"}}
        ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unapproved license", result.stderr)

    def test_rejects_review_record_when_exact_documentation_url_changes(self) -> None:
        for document, index in (
            (self.sbom_document, 2),
            (self.example_sbom_document, 1),
        ):
            document["components"][index]["externalReferences"][0]["url"] = (
                "https://example.invalid/not-reviewed"
            )
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("exact documentation reference", result.stderr)

    def test_rejects_review_policy_with_invalid_documentation_url(self) -> None:
        self.policy_document["licenseReviewExceptions"][0][
            "documentationUrl"
        ] = "https://example.com:bad"
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("invalid port", result.stderr)

    def test_rejects_review_policy_with_forbidden_url_delimiter(self) -> None:
        self.policy_document["licenseReviewExceptions"][0][
            "documentationUrl"
        ] = "https://exa|mple.com/path"
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("malformed URL syntax", result.stderr)

    def test_rejects_review_marker_on_a_component_with_real_licenses(self) -> None:
        self.sbom_document["components"][-1]["properties"] = [
            {
                "name": "routecontract:license-review",
                "value": "manual-review-required",
            }
        ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("must not carry reserved license review status", result.stderr)

    def test_rejects_missing_or_empty_review_record_licenses_only_when_exact(self) -> None:
        self.sbom_document["components"][2]["licenses"] = []
        self.example_sbom_document["components"][1]["licenses"] = []
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("has no license metadata", result.stderr)

    def test_rejects_explicit_null_review_record_licenses(self) -> None:
        self.write_fixture()
        self.sbom_document["components"][2]["licenses"] = None
        write_json(self.sbom, self.sbom_document)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("has no license metadata", result.stderr)

    def test_rejects_mixed_expression_and_license_object(self) -> None:
        self.sbom_document["components"][-1]["licenses"] = [
            {"license": {"id": "Apache-2.0"}},
            {"expression": "Apache-2.0"},
        ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("one expression or license objects", result.stderr)

    def test_rejects_nested_json_metadata_component_collection(self) -> None:
        self.sbom_document["metadata"]["component"]["components"] = [
            self.sbom_document["components"].pop()
        ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Nested JSON components are not supported", result.stderr)

    def test_rejects_explicit_null_nested_component_collection(self) -> None:
        self.sbom_document["metadata"]["component"]["components"] = None
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Nested JSON components are not supported", result.stderr)

    def test_rejects_nested_xml_metadata_component_collection(self) -> None:
        self.write_fixture()
        qname = lambda name: f"{{{CYCLONEDX_XML_NAMESPACE}}}{name}"
        tree = ET.parse(self.sbom_xml)
        metadata_component = tree.getroot().find(
            f"{qname('metadata')}/{qname('component')}"
        )
        self.assertIsNotNone(metadata_component)
        ET.SubElement(metadata_component, qname("components"))
        tree.write(self.sbom_xml, encoding="utf-8", xml_declaration=True)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("XML SBOM contains nested components", result.stderr)

    def test_rejects_nested_xml_container_property_content(self) -> None:
        self.write_fixture()
        qname = lambda name: f"{{{CYCLONEDX_XML_NAMESPACE}}}{name}"
        tree = ET.parse(self.sbom_xml)
        container = next(
            component
            for component in tree.getroot().findall(
                f"{qname('components')}/{qname('component')}"
            )
            if component.findtext(qname("name")) == "mysql"
        )
        property_element = container.find(
            f"{qname('properties')}/{qname('property')}"
        )
        self.assertIsNotNone(property_element)
        ET.SubElement(property_element, qname("bogus")).text = "hidden"
        tree.write(self.sbom_xml, encoding="utf-8", xml_declaration=True)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("property must be a leaf", result.stderr)

    def test_rejects_utf16_xml_with_dtd_and_entity(self) -> None:
        self.write_fixture()
        content = self.sbom_xml.read_text(encoding="utf-8")
        declaration_end = content.index("?>") + 2
        content = (
            content[:declaration_end]
            + "\n<!DOCTYPE bom [<!ENTITY x 'safe'>]>"
            + content[declaration_end:]
        )
        content = content.replace(">safe<", ">&x;<", 1)
        content = content.replace("encoding='utf-8'", "encoding='utf-16'")
        content = content.replace('encoding="utf-8"', 'encoding="utf-16"')
        self.sbom_xml.write_bytes(content.encode("utf-16"))

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("XML SBOM must be UTF-8", result.stderr)

    def test_rejects_nested_xml_content_in_license_scalar(self) -> None:
        self.write_fixture()
        qname = lambda name: f"{{{CYCLONEDX_XML_NAMESPACE}}}{name}"
        for path in (self.sbom_xml, self.example_sbom_xml):
            tree = ET.parse(path)
            expression = next(
                component.find(f"{qname('licenses')}/{qname('expression')}")
                for component in tree.getroot().findall(
                    f"{qname('components')}/{qname('component')}"
                )
                if component.findtext(qname("name")) == "mysql-connector-j"
            )
            ET.SubElement(expression, qname("bogus")).text = "MIT"
            tree.write(path, encoding="utf-8", xml_declaration=True)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("empty license expression", result.stderr)

    def test_rejects_xml_license_children_in_schema_invalid_order(self) -> None:
        self.write_fixture()
        qname = lambda name: f"{{{CYCLONEDX_XML_NAMESPACE}}}{name}"
        tree = ET.parse(self.sbom_xml)
        license_element = next(
            component.find(f"{qname('licenses')}/{qname('license')}")
            for component in tree.getroot().findall(
                f"{qname('components')}/{qname('component')}"
            )
            if component.findtext(qname("name")) == "safe"
        )
        identifier = license_element.find(qname("id"))
        self.assertIsNotNone(identifier)
        license_element.remove(identifier)
        url = ET.Element(qname("url"))
        url.text = "https://www.apache.org/licenses/LICENSE-2.0.txt"
        license_element.insert(0, url)
        license_element.append(identifier)
        tree.write(self.sbom_xml, encoding="utf-8", xml_declaration=True)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("ambiguous license", result.stderr)

    def test_rejects_non_ascii_spdx_whitespace(self) -> None:
        malformed = "GPL-2.0-only\u00a0WITH\u00a0Universal-FOSS-exception-1.0"
        self.policy_document["licenseExceptions"][0]["license"] = malformed
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("invalid SPDX syntax", result.stderr)

    def test_rejects_leading_or_trailing_spdx_space(self) -> None:
        self.policy_document["licenseExceptions"][0]["license"] = (
            " GPL-2.0-only WITH Universal-FOSS-exception-1.0 "
        )
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("invalid SPDX syntax", result.stderr)

    def test_rejects_malformed_spdx_expression_in_policy_and_sbom(self) -> None:
        malformed = "Apache-2.0 OR OR GPL-2.0-only"
        self.policy_document["licenseExceptions"][0]["license"] = malformed
        for document, index in (
            (self.sbom_document, 3),
            (self.example_sbom_document, 2),
        ):
            document["components"][index]["licenses"] = [
                {"expression": malformed}
            ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("invalid SPDX operator placement", result.stderr)

    def test_rejects_each_jts_license_list_instead_of_exact_expression(self) -> None:
        for component_name in JTS_EXPRESSIONS:
            with self.subTest(component=component_name):
                originals = []
                for document in (self.sbom_document, self.example_sbom_document):
                    jts = next(
                        component
                        for component in document["components"]
                        if component["name"] == component_name
                    )
                    originals.append(jts["licenses"])
                    jts["licenses"] = [
                        {"license": {"id": "EPL-2.0"}},
                        {"license": {"id": "BSD-3-Clause"}},
                    ]
                self.write_fixture()

                result = self.prepare_inventory()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("must use its exact reviewed SPDX expression", result.stderr)
                for document, original in zip(
                    (self.sbom_document, self.example_sbom_document), originals
                ):
                    next(
                        component
                        for component in document["components"]
                        if component["name"] == component_name
                    )["licenses"] = original

    def test_rejects_each_jts_component_mutated_to_a_pom_artifact(self) -> None:
        original_aggregate = copy.deepcopy(self.sbom_document)
        original_example = copy.deepcopy(self.example_sbom_document)
        for component_name in JTS_EXPRESSIONS:
            with self.subTest(component=component_name):
                for document in (self.sbom_document, self.example_sbom_document):
                    component = next(
                        item
                        for item in document["components"]
                        if item["name"] == component_name
                    )
                    old_purl = component["purl"]
                    new_purl = old_purl.removesuffix("?type=jar") + "?type=pom"
                    component["purl"] = new_purl
                    component["bom-ref"] = new_purl
                    for dependency in document["dependencies"]:
                        if dependency["ref"] == old_purl:
                            dependency["ref"] = new_purl
                        dependency["dependsOn"] = [
                            new_purl if target == old_purl else target
                            for target in dependency["dependsOn"]
                        ]
                self.write_fixture()

                result = self.prepare_inventory()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("must use its exact resolved JAR purl", result.stderr)
                self.sbom_document = copy.deepcopy(original_aggregate)
                self.example_sbom_document = copy.deepcopy(original_example)

    def test_rejects_missing_or_drifted_jts_policy_expression(self) -> None:
        originals = copy.deepcopy(self.policy_document["licenseExceptions"])
        for mode in ("missing", "drifted"):
            with self.subTest(mode=mode):
                mutated = copy.deepcopy(originals)
                if mode == "missing":
                    mutated.pop(1)
                else:
                    mutated[1]["license"] = "EPL-2.0 AND BSD-3-Clause"
                self.policy_document["licenseExceptions"] = mutated
                self.write_fixture()

                result = self.prepare_inventory()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("must bind JTS Core 1.19.0", result.stderr)
        self.policy_document["licenseExceptions"] = originals

    def test_rejects_reintroduced_jts_io_license_exception(self) -> None:
        self.policy_document["licenseExceptions"].append(
            {
                "kind": "expression",
                "license": "(EPL-2.0 OR BSD-3-Clause) AND Apache-2.0",
                "purl": "pkg:maven/org.locationtech.jts.io/jts-io-common@1.20.0",
                "scope": "test-runtime",
                "url": None,
            }
        )
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "JTS I/O Common license exceptions are forbidden",
            result.stderr,
        )

    def test_rejects_any_extra_license_review(self) -> None:
        self.policy_document["licenseReviewExceptions"].append(
            copy.deepcopy(self.policy_document["licenseReviewExceptions"][0])
        )
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "licenseReviewExceptions must contain exactly the pinned MySQL review",
            result.stderr,
        )

    def test_rejects_jts_io_in_every_role_format_and_version(self) -> None:
        original_aggregate = copy.deepcopy(self.sbom_document)
        original_published = copy.deepcopy(self.published_sbom_document)
        original_example = copy.deepcopy(self.example_sbom_document)
        for role, attribute, json_path, xml_path in (
            ("aggregate", "sbom_document", self.sbom, self.sbom_xml),
            (
                "published",
                "published_sbom_document",
                self.published_sbom,
                self.published_sbom_xml,
            ),
            ("example", "example_sbom_document", self.example_sbom, self.example_sbom_xml),
        ):
            for input_format in ("json", "xml"):
                for version in ("1.18.2", "1.19.0", "1.20.0"):
                    with self.subTest(
                        role=role, input_format=input_format, version=version
                    ):
                        self.sbom_document = copy.deepcopy(original_aggregate)
                        self.published_sbom_document = copy.deepcopy(original_published)
                        self.example_sbom_document = copy.deepcopy(original_example)
                        self.write_fixture()
                        document = copy.deepcopy(getattr(self, attribute))
                        purl = (
                            "pkg:maven/org.locationtech.jts.io/"
                            f"jts-io-common@{version}?type=jar"
                        )
                        component = apache_component(
                            purl,
                            "org.locationtech.jts.io",
                            "jts-io-common",
                            version,
                        )
                        component["properties"] = [
                            {"name": "cdx:maven:package:test", "value": "true"}
                        ]
                        document["components"].append(component)
                        document["dependencies"][0]["dependsOn"].append(purl)
                        document["dependencies"].append(
                            {"ref": purl, "dependsOn": []}
                        )
                        if input_format == "json":
                            write_json(json_path, document)
                        else:
                            write_xml_pair(xml_path, document)

                        result = self.prepare_inventory()

                        self.assertNotEqual(0, result.returncode)
                        self.assertIn(
                            "JTS I/O Common is forbidden by the pinned policy",
                            result.stderr,
                        )
        self.sbom_document = original_aggregate
        self.published_sbom_document = original_published
        self.example_sbom_document = original_example

    def test_rejects_missing_or_wrong_pinned_coordinate_in_both_roles(self) -> None:
        original_aggregate = copy.deepcopy(self.sbom_document)
        original_example = copy.deepcopy(self.example_sbom_document)
        for role, attribute in (
            ("aggregate", "sbom_document"),
            ("example", "example_sbom_document"),
        ):
            for group, name, version in REQUIRED_EXAMPLE_COORDINATES:
                for mode in ("missing", "wrong-version"):
                    with self.subTest(
                        role=role,
                        coordinate=f"{group}:{name}:{version}",
                        mode=mode,
                    ):
                        self.sbom_document = copy.deepcopy(original_aggregate)
                        self.example_sbom_document = copy.deepcopy(original_example)
                        document = getattr(self, attribute)
                        component = next(
                            item
                            for item in document["components"]
                            if item.get("group") == group and item.get("name") == name
                        )
                        old_purl = component["purl"]
                        if mode == "missing":
                            document["components"].remove(component)
                            document["dependencies"] = [
                                record
                                for record in document["dependencies"]
                                if record["ref"] != old_purl
                            ]
                            for record in document["dependencies"]:
                                record["dependsOn"] = [
                                    target
                                    for target in record["dependsOn"]
                                    if target != old_purl
                                ]
                        else:
                            new_purl = f"pkg:maven/{group}/{name}@0.0.0?type=jar"
                            replace_component_purl(document, old_purl, new_purl)
                            component["version"] = "0.0.0"
                        self.write_fixture()

                        result = self.prepare_inventory()

                        self.assertNotEqual(0, result.returncode)
                        self.assertIn(
                            f"must contain exactly {group}:{name}:{version}",
                            result.stderr,
                        )
        self.sbom_document = original_aggregate
        self.example_sbom_document = original_example

    def test_rejects_unknown_spdx_license_id(self) -> None:
        self.sbom_document["components"][-1]["licenses"] = [
            {"license": {"id": "LicenseRef-not-reviewed"}}
        ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("reviewed SPDX license-id set", result.stderr)

    def test_rejects_unknown_spdx_exception_id(self) -> None:
        unknown = "GPL-2.0-only WITH Unknown-exception-9.9"
        self.policy_document["licenseExceptions"][0]["license"] = unknown
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unreviewed SPDX exception id", result.stderr)

    def test_rejects_unknown_license_exception_scope(self) -> None:
        self.policy_document["licenseExceptions"][0]["scope"] = "declared-by-human"
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("license exception scope", result.stderr)

    def test_rejects_test_runtime_license_without_test_property(self) -> None:
        self.sbom_document["components"][3].pop("properties")
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("not proven test-runtime", result.stderr)

    def test_rejects_test_runtime_license_on_non_library(self) -> None:
        self.sbom_document["components"][3]["type"] = "application"
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("not proven test-runtime", result.stderr)

    def test_rejects_test_container_license_without_excluded_scope(self) -> None:
        self.sbom_document["components"][2]["scope"] = "required"
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("not proven test-container", result.stderr)

    def test_rejects_test_container_license_without_usage_property(self) -> None:
        self.sbom_document["components"][2]["properties"] = [
            {
                "name": "routecontract:license-review",
                "value": "manual-review-required",
            }
        ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("not proven test-container", result.stderr)

    def test_rejects_any_vulnerability_exception(self) -> None:
        self.policy_document["vulnerabilityExceptions"] = [
            {"advisory": "GHSA-pq2g-wx69-c263"}
        ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("vulnerabilityExceptions must be exactly empty", result.stderr)

    def test_rejects_test_only_exception_for_published_module_coordinate(self) -> None:
        published_vulnerable = copy.deepcopy(self.sbom_document["components"][4])
        published_vulnerable["properties"] = [
            {"name": "cdx:maven:package:test", "value": "false"}
        ]
        self.published_sbom_document["components"].append(published_vulnerable)
        self.published_sbom_document["dependencies"][0]["dependsOn"].append(
            published_vulnerable["purl"]
        )
        self.published_sbom_document["dependencies"].append(
            {"ref": published_vulnerable["purl"], "dependsOn": []}
        )
        self.inject_test_finding()
        self.write_fixture()
        self.assertEqual(0, self.prepare_inventory().returncode)

        result = self.verify()

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "vulnerability findings are forbidden by the pinned policy",
            result.stderr,
        )
        self.assertFalse(self.evidence.exists())

    def test_rejects_pom_dependency_missing_from_published_sbom(self) -> None:
        self.published_sbom_document["components"] = [
            apache_component(
                "pkg:maven/com.example/other@1.0?type=jar",
                "com.example",
                "other",
                "1.0",
            )
        ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("missing from published SBOM", result.stderr)

    def test_rejects_empty_published_pom_dependencies(self) -> None:
        self.write_fixture()
        content = self.published_pom.read_text(encoding="utf-8")
        start = content.index("  <dependencies>")
        end = content.index("  </dependencies>", start) + len("  </dependencies>\n")
        self.published_pom.write_text(
            content[:start] + content[end:], encoding="utf-8"
        )

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("locked runtime/direct contract", result.stderr)

    def test_rejects_published_pom_scope_drift(self) -> None:
        self.write_fixture()
        self.published_pom.write_text(
            self.published_pom.read_text(encoding="utf-8").replace(
                "<scope>runtime</scope>", "<scope>compile</scope>"
            ),
            encoding="utf-8",
        )

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("dependency scopes must exactly be runtime", result.stderr)

    def test_rejects_runtime_lock_coordinate_outside_pom_seeded_closure(self) -> None:
        self.write_fixture()
        self.published_lock.write_text(
            self.published_lock.read_text(encoding="utf-8").replace(
                "empty=annotationProcessor,testAnnotationProcessor",
                "com.example:extra:2.0=runtimeClasspath\n"
                "empty=annotationProcessor,testAnnotationProcessor",
            ),
            encoding="utf-8",
        )

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("runtime closure differs from the dependency lock", result.stderr)

    def test_rejects_pom_default_jar_mapped_to_pom_component(self) -> None:
        safe = self.published_sbom_document["components"][0]
        old = safe["purl"]
        new = old.replace("?type=jar", "?type=pom")
        safe["purl"] = new
        safe["bom-ref"] = new
        self.published_sbom_document["dependencies"][0]["dependsOn"] = [new]
        self.published_sbom_document["dependencies"][1]["ref"] = new
        for document in (self.sbom_document, self.example_sbom_document):
            for component in document["components"]:
                if component.get("purl") == old:
                    component["purl"] = new
                    component["bom-ref"] = new
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("default-jar dependency is not a resolved jar", result.stderr)

    def test_rejects_published_sbom_license_missing(self) -> None:
        self.published_sbom_document["components"][0].pop("licenses")
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("has no license metadata", result.stderr)

    def test_rejects_published_pom_with_doctype(self) -> None:
        self.write_fixture()
        self.published_pom.write_text(
            '<!DOCTYPE project SYSTEM "file:///etc/passwd"><project/>\n',
            encoding="utf-8",
        )

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("declare XML 1.0 with UTF-8 encoding", result.stderr)

    def test_rejects_published_pom_without_license(self) -> None:
        self.write_fixture()
        content = self.published_pom.read_text(encoding="utf-8")
        start = content.index("  <licenses>")
        end = content.index("  </licenses>\n", start) + len("  </licenses>\n")
        self.published_pom.write_text(
            content[:start] + content[end:], encoding="utf-8"
        )

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("must contain one licenses element", result.stderr)

    def test_rejects_duplicate_published_pom_license(self) -> None:
        self.write_fixture()
        content = self.published_pom.read_text(encoding="utf-8")
        license_record = (
            "    <license>\n"
            "      <name>The Apache License, Version 2.0</name>\n"
            "      <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>\n"
            "      <distribution>repo</distribution>\n"
            "    </license>\n"
        )
        self.published_pom.write_text(
            content.replace("  </licenses>\n", license_record + "  </licenses>\n"),
            encoding="utf-8",
        )

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("license declaration is ambiguous", result.stderr)

    def test_rejects_conflicting_published_pom_license(self) -> None:
        self.write_fixture()
        self.published_pom.write_text(
            self.published_pom.read_text(encoding="utf-8").replace(
                "The Apache License, Version 2.0", "GNU General Public License"
            ),
            encoding="utf-8",
        )

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("exact Apache-2.0 license", result.stderr)

    def test_accepts_exact_central_pom_metadata(self) -> None:
        self.write_fixture()
        result = self.prepare_inventory()
        self.assertEqual(0, result.returncode, result.stderr)

    def test_rejects_missing_duplicate_or_wrong_central_developer(self) -> None:
        developer = (
            "    <developer>\n"
            "      <id>ym0506</id>\n"
            "      <name>ym0506</name>\n"
            "      <email>atat9828@naver.com</email>\n"
            "      <url>https://github.com/ym0506</url>\n"
            "    </developer>\n"
        )
        developers = f"  <developers>\n{developer}  </developers>\n"
        cases = (
            ("missing", developers, "", "must contain one developers element"),
            ("duplicate", developer, developer * 2, "declaration is ambiguous"),
            (
                "wrong",
                "<email>atat9828@naver.com</email>",
                "<email>wrong@example.com</email>",
                "exact RouteContract developer",
            ),
        )
        for case, old, new, error in cases:
            with self.subTest(case=case):
                self.write_fixture()
                content = self.published_pom.read_text(encoding="utf-8")
                self.published_pom.write_text(
                    content.replace(old, new, 1), encoding="utf-8"
                )
                result = self.prepare_inventory()
                self.assertNotEqual(0, result.returncode)
                self.assertIn(error, result.stderr)

    def test_rejects_missing_or_wrong_central_project_metadata(self) -> None:
        project_name = (
            "<name>RouteContract for Apache ShardingSphere-JDBC 5.5.3</name>"
        )
        cases = (
            (project_name, "", "one project name"),
            (project_name, project_name * 2, "one project name"),
            (
                "Operation-scoped contracts over physical JDBC execution attempts",
                "Wrong contract",
                "project description",
            ),
            (
                "https://github.com/ym0506/routecontract</url>",
                "https://example.invalid/project</url>",
                "project url",
            ),
            (
                "scm:git:https://github.com/ym0506/routecontract.git",
                "scm:git:https://example.invalid/wrong.git",
                "exact RouteContract scm",
            ),
        )
        for old, new, error in cases:
            with self.subTest(old=old):
                self.write_fixture()
                content = self.published_pom.read_text(encoding="utf-8")
                self.published_pom.write_text(
                    content.replace(old, new, 1), encoding="utf-8"
                )
                result = self.prepare_inventory()
                self.assertNotEqual(0, result.returncode)
                self.assertIn(error, result.stderr)

    def test_rejects_utf16_published_pom_with_dtd_and_entity(self) -> None:
        self.write_fixture()
        content = self.published_pom.read_text(encoding="utf-8")
        declaration_end = content.index("?>") + 2
        content = (
            content[:declaration_end]
            + "\n<!DOCTYPE project [<!ENTITY x 'safe'>]>"
            + content[declaration_end:]
        )
        content = content.replace(">safe<", ">&x;<", 1)
        content = content.replace('encoding="UTF-8"', 'encoding="UTF-16"')
        self.published_pom.write_bytes(content.encode("utf-16"))

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("published POM must be UTF-8", result.stderr)

    def test_rejects_published_pom_with_false_encoding_declaration(self) -> None:
        self.write_fixture()
        self.published_pom.write_text(
            self.published_pom.read_text(encoding="utf-8").replace(
                'encoding="UTF-8"', 'encoding="ISO-8859-1"'
            ),
            encoding="utf-8",
        )

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("declare XML 1.0 with UTF-8 encoding", result.stderr)

    def test_rejects_nested_published_pom_dependency_scalar(self) -> None:
        self.write_fixture()
        self.published_pom.write_text(
            self.published_pom.read_text(encoding="utf-8").replace(
                "<artifactId>safe</artifactId>",
                "<artifactId>safe<bogus>hidden</bogus></artifactId>",
            ),
            encoding="utf-8",
        )

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("dependency artifactId must be a scalar leaf", result.stderr)

    def test_rejects_attributes_on_published_pom_dependency_scope(self) -> None:
        self.write_fixture()
        self.published_pom.write_text(
            self.published_pom.read_text(encoding="utf-8").replace(
                "<scope>runtime</scope>", '<scope spoof="true">runtime</scope>'
            ),
            encoding="utf-8",
        )

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("ambiguous scope", result.stderr)

    def test_rejects_spoofed_example_root(self) -> None:
        vulnerable = self.example_sbom_document["components"].pop(3)
        self.example_sbom_document["metadata"]["component"] = vulnerable
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unexpected first-party root identity", result.stderr)

    def test_rejects_wrong_first_party_project_path_duplicate(self) -> None:
        wrong = copy.deepcopy(self.example_sbom_document["components"][0])
        wrong_purl = wrong["purl"].replace(
            "project_path=%3Aroutecontract-shardingsphere-5.5",
            "project_path=%3Awrong-path",
        )
        wrong["purl"] = wrong_purl
        wrong["bom-ref"] = wrong_purl
        self.example_sbom_document["components"].append(wrong)
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("exactly the published first-party", result.stderr)

    def test_rejects_profile_identity_drift_by_classifier(self) -> None:
        vulnerable = self.example_sbom_document["components"][3]
        original = vulnerable["purl"]
        drifted = original.replace("?type=jar", "?classifier=sources")
        vulnerable["purl"] = drifted
        vulnerable["bom-ref"] = drifted
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unexpected qualifiers", result.stderr)

    def test_rejects_malformed_percent_encoded_maven_identity(self) -> None:
        safe = self.published_sbom_document["components"][0]
        original = safe["purl"]
        malformed = original.replace("com.example", "com.%FFexample")
        safe["purl"] = malformed
        safe["bom-ref"] = malformed
        self.published_sbom_document["dependencies"][0]["dependsOn"] = [malformed]
        self.published_sbom_document["dependencies"][1]["ref"] = malformed
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("invalid UTF-8 percent encoding", result.stderr)

    def test_rejects_published_pom_without_exact_model_version(self) -> None:
        self.write_fixture()
        self.published_pom.write_text(
            self.published_pom.read_text(encoding="utf-8").replace(
                "<modelVersion>4.0.0</modelVersion>",
                "<modelVersion>999</modelVersion>",
            ),
            encoding="utf-8",
        )

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("modelVersion must be exactly 4.0.0", result.stderr)

    def test_rejects_published_pom_parent(self) -> None:
        self.write_fixture()
        self.published_pom.write_text(
            self.published_pom.read_text(encoding="utf-8").replace(
                "  <modelVersion>4.0.0</modelVersion>",
                "  <modelVersion>4.0.0</modelVersion>\n"
                "  <parent><groupId>evil</groupId><artifactId>parent</artifactId>"
                "<version>1</version></parent>",
            ),
            encoding="utf-8",
        )

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("must not inherit from a parent", result.stderr)

    def test_rejects_non_jar_published_pom_packaging(self) -> None:
        for packaging in ("pom", "war"):
            with self.subTest(packaging=packaging):
                self.write_fixture()
                self.published_pom.write_text(
                    self.published_pom.read_text(encoding="utf-8").replace(
                        "  <dependencies>",
                        f"  <packaging>{packaging}</packaging>\n  <dependencies>",
                    ),
                    encoding="utf-8",
                )

                result = self.prepare_inventory()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("packaging must be jar", result.stderr)

    def test_rejects_published_pom_repository_or_build_injection(self) -> None:
        injections = (
            "<repositories><repository><id>evil</id><url>https://evil.invalid</url>"
            "</repository></repositories>",
            "<pluginRepositories><pluginRepository><id>evil</id>"
            "<url>https://evil.invalid</url></pluginRepository></pluginRepositories>",
            "<build><extensions><extension><groupId>evil</groupId>"
            "<artifactId>extension</artifactId><version>1</version>"
            "</extension></extensions></build>",
        )
        for injection in injections:
            with self.subTest(injection=injection.split(">", 1)[0]):
                self.write_fixture()
                self.published_pom.write_text(
                    self.published_pom.read_text(encoding="utf-8").replace(
                        "  <dependencies>", f"  {injection}\n  <dependencies>"
                    ),
                    encoding="utf-8",
                )

                result = self.prepare_inventory()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("unsupported project fields", result.stderr)

    def test_rejects_published_graph_back_edge_to_project_root(self) -> None:
        project_ref = self.published_sbom_document["metadata"]["component"]["purl"]
        self.published_sbom_document["dependencies"][1]["dependsOn"] = [project_ref]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("back-edge to its project root", result.stderr)

    def test_rejects_test_runtime_license_coordinate_in_published_profile(self) -> None:
        connector = copy.deepcopy(self.sbom_document["components"][3])
        connector["properties"] = [
            {"name": "cdx:maven:package:test", "value": "false"}
        ]
        connector["licenses"] = [{"license": {"id": "Apache-2.0"}}]
        self.published_sbom_document["components"].append(connector)
        self.published_sbom_document["dependencies"][0]["dependsOn"].append(
            connector["purl"]
        )
        self.published_sbom_document["dependencies"].append(
            {"ref": connector["purl"], "dependsOn": []}
        )
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("cross-role component artifact metadata differs", result.stderr)

    def test_rejects_test_container_missing_from_example_profile(self) -> None:
        self.example_sbom_document["components"].pop(1)
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("third-party component set differs", result.stderr)

    def test_rejects_profile_identity_drift_by_type(self) -> None:
        vulnerable = self.example_sbom_document["components"][3]
        original = vulnerable["purl"]
        drifted = original.replace("?type=jar", "?type=pom")
        vulnerable["purl"] = drifted
        vulnerable["bom-ref"] = drifted
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("component set differs", result.stderr)

    def test_rejects_noncanonical_percent_encoding(self) -> None:
        safe = self.published_sbom_document["components"][0]
        original = safe["purl"]
        drifted = original.replace("com.example", "com%2Eexample")
        safe["purl"] = drifted
        safe["bom-ref"] = drifted
        self.published_sbom_document["dependencies"][0]["dependsOn"] = [drifted]
        self.published_sbom_document["dependencies"][1]["ref"] = drifted
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("differs from the pinned producer encoding profile", result.stderr)

    def test_rejects_wrong_first_party_apache_url_in_all_pairs(self) -> None:
        for document in (
            self.sbom_document,
            self.published_sbom_document,
            self.example_sbom_document,
        ):
            candidates = [document["metadata"]["component"], *document["components"]]
            for component in candidates:
                if component.get("group") == "io.github.ym0506.routecontract":
                    component["licenses"] = [
                        {
                            "license": {
                                "id": "Apache-2.0",
                                "url": "https://wrong.example/license",
                            }
                        }
                    ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("must use exact Apache-2.0 metadata", result.stderr)

    def test_rejects_paired_mysql_oci_name_or_version_drift(self) -> None:
        for field, value in (("name", "not-mysql"), ("version", "0.0.0")):
            with self.subTest(field=field):
                originals = []
                for document in (self.sbom_document, self.example_sbom_document):
                    component = document["components"][
                        2 if document is self.sbom_document else 1
                    ]
                    originals.append(component[field])
                    component[field] = value
                self.write_fixture()

                result = self.prepare_inventory()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("exactly identify the pinned MySQL OCI image", result.stderr)
                for document, original in zip(
                    (self.sbom_document, self.example_sbom_document), originals
                ):
                    document["components"][
                        2 if document is self.sbom_document else 1
                    ][field] = original

    def test_rejects_policy_and_component_oci_purl_co_mutation(self) -> None:
        original = self.policy_document["licenseReviewExceptions"][0]["purl"]
        drifted = "pkg:oci/notmysql@latest"
        self.policy_document["licenseReviewExceptions"][0]["purl"] = drifted
        for document in (self.sbom_document, self.example_sbom_document):
            replace_component_purl(document, original, drifted)
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("exactly identify the pinned MySQL OCI image", result.stderr)

    def test_rejects_mysql_oci_digest_drift_in_both_profiles(self) -> None:
        for document, index in (
            (self.sbom_document, 2),
            (self.example_sbom_document, 1),
        ):
            document["components"][index]["hashes"][0]["content"] = "0" * 64
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("exactly identify the pinned MySQL OCI image", result.stderr)

    def test_rejects_drift_in_pinned_mysql_review_policy_fields(self) -> None:
        cases = (
            ("action", "defer this review indefinitely"),
            ("componentName", "not-mysql"),
            ("componentVersion", "0.0.0"),
            ("expires", "9999-12-31"),
            ("owner", "nobody"),
            ("rationaleCode", "UNBOUNDED"),
            ("reviewedAt", "2026-08-12"),
            ("sha256", "0" * 64),
        )
        for field, value in cases:
            with self.subTest(field=field):
                original = self.policy_document["licenseReviewExceptions"][0][field]
                self.policy_document["licenseReviewExceptions"][0][field] = value
                self.write_fixture()

                result = self.prepare_inventory()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("exactly identify the pinned MySQL OCI image", result.stderr)
                self.policy_document["licenseReviewExceptions"][0][field] = original

    def test_rejects_stale_pre_owner_decision_mysql_review_contract(self) -> None:
        stale_values = (
            (
                "action",
                "resolve, renew with new evidence, or remove the MySQL OCI "
                "package-level license review before the 2026-08-27 expiry",
            ),
            ("reviewedAt", "2026-08-13"),
        )
        for field, value in stale_values:
            with self.subTest(field=field):
                original = self.policy_document["licenseReviewExceptions"][0][field]
                self.policy_document["licenseReviewExceptions"][0][field] = value
                self.write_fixture()

                result = self.prepare_inventory()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("exactly identify the pinned MySQL OCI image", result.stderr)
                self.policy_document["licenseReviewExceptions"][0][field] = original

    def test_rejects_expired_mysql_license_review_window(self) -> None:
        today = datetime.now(timezone.utc).date()
        reviewed = (today - timedelta(days=2)).isoformat()
        expired = (today - timedelta(days=1)).isoformat()
        original_policy = copy.deepcopy(self.policy_document)
        for index in (0,):
            with self.subTest(review=index):
                self.policy_document["licenseReviewExceptions"][index][
                    "reviewedAt"
                ] = reviewed
                self.policy_document["licenseReviewExceptions"][index][
                    "expires"
                ] = expired
                self.write_fixture()

                result = self.prepare_inventory()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("has expired", result.stderr)
                self.policy_document = copy.deepcopy(original_policy)

    def test_rejects_future_or_noncanonical_license_review_dates(self) -> None:
        tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
        original_policy = copy.deepcopy(self.policy_document)
        cases = (
            ("reviewedAt", tomorrow, "must not be in the future"),
            ("reviewedAt", "2026-08-13T00:00:00Z", "must use YYYY-MM-DD"),
            ("expires", "2026-8-27", "must use YYYY-MM-DD"),
            ("expires", "20260827", "must use canonical YYYY-MM-DD"),
        )
        for index in (0,):
            for field, value, diagnostic in cases:
                with self.subTest(review=index, field=field, value=value):
                    self.policy_document = copy.deepcopy(original_policy)
                    self.policy_document["licenseReviewExceptions"][index][field] = value
                    self.write_fixture()

                    result = self.prepare_inventory()

                    self.assertNotEqual(0, result.returncode)
                    self.assertIn(diagnostic, result.stderr)
        self.policy_document = original_policy

    def test_rejects_mysql_license_review_date_after_expiry(self) -> None:
        today = datetime.now(timezone.utc).date()
        reviewed = (today - timedelta(days=1)).isoformat()
        expires = (today - timedelta(days=2)).isoformat()
        original_policy = copy.deepcopy(self.policy_document)
        for index in (0,):
            with self.subTest(review=index):
                self.policy_document = copy.deepcopy(original_policy)
                self.policy_document["licenseReviewExceptions"][index][
                    "reviewedAt"
                ] = reviewed
                self.policy_document["licenseReviewExceptions"][index][
                    "expires"
                ] = expires
                self.write_fixture()

                result = self.prepare_inventory()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("reviewedAt must not be later than expires", result.stderr)
        self.policy_document = original_policy

    def test_rejects_published_role_containing_example_project(self) -> None:
        example_project = copy.deepcopy(self.sbom_document["components"][1])
        self.published_sbom_document["components"].append(example_project)
        self.published_sbom_document["dependencies"][0]["dependsOn"].append(
            example_project["purl"]
        )
        self.published_sbom_document["dependencies"].append(
            {"ref": example_project["purl"], "dependsOn": []}
        )
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("must not contain another first-party project", result.stderr)

    def test_rejects_example_role_missing_published_project(self) -> None:
        published_project = self.example_sbom_document["components"].pop(0)
        self.example_sbom_document["dependencies"][0]["dependsOn"].remove(
            published_project["purl"]
        )
        self.example_sbom_document["dependencies"] = [
            record
            for record in self.example_sbom_document["dependencies"]
            if record["ref"] != published_project["purl"]
        ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("exactly the published first-party project", result.stderr)

    def test_rejects_paired_aggregate_project_type_or_license_drift(self) -> None:
        for field in ("type", "licenses"):
            with self.subTest(field=field):
                component = self.sbom_document["components"][0]
                original = copy.deepcopy(component[field])
                if field == "type":
                    component[field] = "container"
                else:
                    component[field] = [{"license": {"id": "MIT"}}]
                self.write_fixture()

                result = self.prepare_inventory()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("component identities differ", result.stderr)
                component[field] = original

    def test_rejects_paired_graph_missing_reachable_leaf_record(self) -> None:
        for document, index in (
            (self.sbom_document, 4),
            (self.example_sbom_document, 3),
        ):
            leaf = document["components"][index]["purl"]
            document["dependencies"] = [
                record for record in document["dependencies"] if record["ref"] != leaf
            ]
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("does not cover every node", result.stderr)

    def test_rejects_paired_published_root_self_loop(self) -> None:
        root = self.published_sbom_document["metadata"]["component"]["purl"]
        self.published_sbom_document["dependencies"][0]["dependsOn"].append(root)
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("repeats a node or edge", result.stderr)

    def test_accepts_distinct_valid_role_timestamps(self) -> None:
        self.published_sbom_document["metadata"][
            "timestamp"
        ] = "2026-08-13T18:10:31Z"
        self.example_sbom_document["metadata"][
            "timestamp"
        ] = "2026-08-13T18:10:32.123Z"
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertEqual(0, result.returncode, result.stderr)

    def test_rejects_malformed_timestamp(self) -> None:
        self.example_sbom_document["metadata"][
            "timestamp"
        ] = "definitely-not-rfc3339"
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("RFC 3339 UTC timestamp", result.stderr)

    def test_rejects_json_xml_timestamp_drift_within_a_role(self) -> None:
        self.write_fixture()
        document = json.loads(self.example_sbom.read_text(encoding="utf-8"))
        document["metadata"]["timestamp"] = "2026-08-13T18:10:31Z"
        write_json(self.example_sbom, document)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("JSON/XML metadata timestamps differ", result.stderr)

    def test_rejects_utf8_bom_in_json_and_xml(self) -> None:
        for path in (self.sbom, self.sbom_xml):
            with self.subTest(path=path.suffix):
                self.write_fixture()
                path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())

                result = self.prepare_inventory()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("must not contain a UTF-8 BOM", result.stderr)

    def test_rejects_non_utf8_xml_declaration_over_utf8_bytes(self) -> None:
        content = self.sbom_xml.read_text(encoding="utf-8")
        self.assertIn("encoding='utf-8'", content)
        self.sbom_xml.write_text(
            content.replace("encoding='utf-8'", "encoding='UTF-16'", 1),
            encoding="utf-8",
        )

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("declare XML 1.0 with UTF-8 encoding", result.stderr)

    def test_rejects_xml_comments_and_processing_instructions(self) -> None:
        for markup in (b"<!-- hidden -->", b"<?hidden value?>"):
            with self.subTest(markup=markup):
                self.write_fixture()
                content = self.sbom_xml.read_bytes()
                declaration_end = content.index(b"?>") + 2
                self.sbom_xml.write_bytes(
                    content[:declaration_end]
                    + b"\n"
                    + markup
                    + content[declaration_end:]
                )

                result = self.prepare_inventory()

                self.assertNotEqual(0, result.returncode)
                self.assertIn(
                    "must not contain comments or processing instructions",
                    result.stderr,
                )

    def test_rejects_published_pom_comments_and_processing_instructions(self) -> None:
        for markup in ("<!-- hidden -->", "<?hidden value?>"):
            with self.subTest(markup=markup):
                self.write_fixture()
                content = self.published_pom.read_text(encoding="utf-8")
                declaration_end = content.index("?>") + 2
                self.published_pom.write_text(
                    content[:declaration_end]
                    + "\n"
                    + markup
                    + content[declaration_end:],
                    encoding="utf-8",
                )

                result = self.prepare_inventory()

                self.assertNotEqual(0, result.returncode)
                self.assertIn(
                    "must not contain comments or processing instructions",
                    result.stderr,
                )

    def test_rejects_nonempty_explicit_scanner_config(self) -> None:
        self.assertEqual(0, self.prepare_inventory().returncode)
        self.scanner_config.write_text(
            "[IgnoreVulns]\nid = [\"GHSA-pq2g-wx69-c263\"]\n",
            encoding="utf-8",
        )

        result = self.verify()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("must be exactly empty", result.stderr)
        self.assertFalse(self.evidence.exists())

    def test_rejects_database_timestamp_unrelated_to_pinned_generation(self) -> None:
        self.assertEqual(0, self.prepare_inventory().returncode)
        scanner_lock = json.loads(self.scanner_lock.read_text(encoding="utf-8"))
        scanner_lock["database"]["lastModified"] = "2099-01-01T00:00:00.000Z"
        write_json(self.scanner_lock, scanner_lock)

        result = self.verify()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("does not match the pinned generation object", result.stderr)
        self.assertFalse(self.evidence.exists())

    def test_rejects_symlink_json_input(self) -> None:
        actual_sbom = self.root / "actual-bom.json"
        self.sbom.replace(actual_sbom)
        os.symlink(actual_sbom.name, self.sbom)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("symbolic link", result.stderr)

    def test_rejects_symlink_inventory_output(self) -> None:
        victim = self.root / "victim.txt"
        victim.write_text("do not replace\n", encoding="utf-8")
        os.symlink(victim.name, self.inventory)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("symbolic link", result.stderr)
        self.assertEqual("do not replace\n", victim.read_text(encoding="utf-8"))

    def test_rejects_symlink_output_parent(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        linked_parent = self.root / "linked-parent"
        os.symlink(outside.name, linked_parent)
        self.inventory = linked_parent / "gradle.lockfile"

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("symbolic link", result.stderr)
        self.assertFalse((outside / "gradle.lockfile").exists())

if __name__ == "__main__":
    unittest.main()
