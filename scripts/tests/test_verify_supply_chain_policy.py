#!/usr/bin/env python3
"""Acceptance tests for the final SBOM, license, and OSV policy gate."""

from __future__ import annotations

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


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def apache_component(purl: str, group: str, name: str, version: str) -> dict[str, object]:
    return {
        "type": "library",
        "bom-ref": purl,
        "group": group,
        "name": name,
        "version": version,
        "purl": purl,
        "licenses": [{"license": {"id": "Apache-2.0"}}],
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
                    ET.SubElement(license_element, qname("id")).text = choice["license"]["id"]
                    if "url" in choice["license"]:
                        ET.SubElement(license_element, qname("url")).text = choice["license"]["url"]
        ET.SubElement(element, qname("purl")).text = component["purl"]
        if component.get("properties"):
            properties = ET.SubElement(element, qname("properties"))
            for item in component["properties"]:
                ET.SubElement(
                    properties, qname("property"), {"name": item["name"]}
                ).text = item["value"]

    metadata = ET.SubElement(root, qname("metadata"))
    append_component(metadata, document["metadata"]["component"])
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
            "pkg:maven/net.minidev/json-smart@2.5.0?type=jar",
            "net.minidev",
            "json-smart",
            "2.5.0",
        )
        vulnerable["properties"] = [
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
            "licenses": [{"license": {"id": "GPL-2.0-only"}}],
            "properties": [{"name": "routecontract:usage", "value": "test-only"}],
        }
        self.sbom_document = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "component": {
                    "type": "library",
                    "bom-ref": "pkg:maven/io.github.ym0506.routecontract/routecontract@0.1.0?project_path=%3A",
                    "group": "io.github.ym0506.routecontract",
                    "name": "routecontract",
                    "version": "0.1.0",
                    "purl": "pkg:maven/io.github.ym0506.routecontract/routecontract@0.1.0?project_path=%3A",
                    "licenses": [{"license": {"id": "Apache-2.0"}}],
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
                safe,
            ],
            "dependencies": [],
        }
        self.published_sbom_document = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "component": {
                    "type": "library",
                    "bom-ref": "pkg:maven/io.github.ym0506.routecontract/routecontract-shardingsphere-5.5@0.1.0?project_path=%3Aroutecontract-shardingsphere-5.5",
                    "group": "io.github.ym0506.routecontract",
                    "name": "routecontract-shardingsphere-5.5",
                    "version": "0.1.0",
                    "purl": "pkg:maven/io.github.ym0506.routecontract/routecontract-shardingsphere-5.5@0.1.0?project_path=%3Aroutecontract-shardingsphere-5.5",
                    "licenses": [{"license": {"id": "Apache-2.0"}}],
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
                "component": {
                    "type": "library",
                    "bom-ref": "pkg:maven/io.github.ym0506.routecontract/mysql-example@0.1.0?project_path=%3Amysql-example",
                    "group": "io.github.ym0506.routecontract",
                    "name": "mysql-example",
                    "version": "0.1.0",
                    "purl": "pkg:maven/io.github.ym0506.routecontract/mysql-example@0.1.0?project_path=%3Amysql-example",
                    "licenses": [{"license": {"id": "Apache-2.0"}}],
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
            ],
            "dependencies": [],
        }
        self.example_sbom_document["components"][0]["properties"] = [
            {"name": "cdx:maven:package:test", "value": "true"}
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
            "schemaVersion": 1,
            "allowedLicenseIds": ["Apache-2.0"],
            "licenseExceptions": [
                {
                    "license": "GPL-2.0-only WITH Universal-FOSS-exception-1.0",
                    "purl": "pkg:maven/com.mysql/mysql-connector-j@26.7.0",
                    "scope": "test-runtime",
                },
                {
                    "license": "GPL-2.0-only",
                    "purl": container_purl,
                    "scope": "test-container",
                },
            ],
            "vulnerabilityExceptions": [
                {
                    "advisory": "GHSA-pq2g-wx69-c263",
                    "exceptionId": "OSV-TEST-001",
                    "expires": (
                        datetime.now(timezone.utc).date() + timedelta(days=15)
                    ).isoformat(),
                    "fixedVersion": "2.5.2",
                    "owner": "test maintainers",
                    "purl": "pkg:maven/net.minidev/json-smart@2.5.0",
                    "rationaleCode": "TEST_GRAPH",
                    "reviewedAt": datetime.now(timezone.utc).date().isoformat(),
                    "scope": "aggregate-test-only",
                    "severity": "HIGH",
                }
            ],
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
                                "version": "2.5.0",
                                "ecosystem": "Maven",
                            },
                            "groups": [
                                {"ids": ["GHSA-pq2g-wx69-c263"], "max_severity": "7.5"}
                            ],
                            "vulnerabilities": [
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
                                                        {"introduced": "2.5.0"},
                                                        {"fixed": "2.5.2"},
                                                    ],
                                                }
                                            ],
                                        }
                                    ],
                                }
                            ],
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
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>io.github.ym0506.routecontract</groupId>
  <artifactId>routecontract-shardingsphere-5.5</artifactId>
  <version>0.1.0</version>
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
net.minidev:json-smart:2.5.0=aggregateSbom
empty=
""",
            self.inventory.read_text(encoding="utf-8"),
        )

        verified = self.verify()
        self.assertEqual(0, verified.returncode, verified.stderr)
        evidence = json.loads(self.evidence.read_text(encoding="utf-8"))
        self.assertEqual(REVISION, evidence["revision"])
        self.assertEqual("b" * 40, evidence["sourceTree"])
        self.assertEqual(5, evidence["sbom"]["mavenPackageCount"])
        self.assertEqual(7, evidence["sbom"]["xmlComponentCount"])
        self.assertRegex(evidence["sbom"]["xmlSha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(1, evidence["vulnerabilities"]["findingCount"])
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
        finding = evidence["vulnerabilities"]["findings"][0]
        self.assertEqual("test maintainers", finding["owner"])
        self.assertEqual("TEST_GRAPH", finding["rationaleCode"])
        self.assertEqual(
            self.policy_document["vulnerabilityExceptions"][0]["reviewedAt"],
            finding["reviewedAt"],
        )
        self.assertEqual(
            {
                "exampleProfile": True,
                "publishedProfile": False,
                "publishedRuntime": False,
            },
            finding["reachabilityEvidence"],
        )
        self.assertIn("expiry", finding["action"])
        self.assertEqual(
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855",
            evidence["scanner"]["scannerConfigSha256"],
        )
        self.assertNotIn("path", self.evidence.read_text(encoding="utf-8"))
        self.assertNotIn("details", self.evidence.read_text(encoding="utf-8"))

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
        self.assertIn("JSON/XML metadata components differ", result.stderr)

    def test_rejects_json_xml_bom_version_drift(self) -> None:
        self.sbom_document["version"] = 2
        write_json(self.sbom, self.sbom_document)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("JSON SBOM version must be the integer 1", result.stderr)

    def test_rejects_json_xml_component_hash_drift(self) -> None:
        self.sbom_document["components"][-1]["hashes"] = [
            {"alg": "SHA-256", "content": "0" * 64}
        ]
        write_json(self.sbom, self.sbom_document)

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("JSON/XML component records differ", result.stderr)

    def test_rejects_unreviewed_vulnerability(self) -> None:
        self.policy_document["vulnerabilityExceptions"] = []
        self.write_fixture()
        self.assertEqual(0, self.prepare_inventory().returncode)

        result = self.verify()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unreviewed vulnerability", result.stderr)
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
        self.assertIn("third-party component set differs", result.stderr)

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
        self.sbom_document["components"][2]["properties"] = []
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("not proven test-container", result.stderr)

    def test_rejects_vulnerability_exception_on_non_library(self) -> None:
        self.sbom_document["components"][4]["type"] = "application"
        self.example_sbom_document["components"][3]["type"] = "application"
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("not proven test-runtime", result.stderr)

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
        self.write_fixture()
        self.assertEqual(0, self.prepare_inventory().returncode)

        result = self.verify()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("published-module vulnerability", result.stderr)
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
        tree = ET.parse(self.published_pom)
        root = tree.getroot()
        namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
        dependencies = root.find("m:dependencies", namespace)
        self.assertIsNotNone(dependencies)
        root.remove(dependencies)
        tree.write(self.published_pom, encoding="utf-8", xml_declaration=True)

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
        self.assertIn("must not contain a DTD", result.stderr)

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
        self.assertIn("component set differs", result.stderr)

    def test_rejects_profile_identity_drift_by_classifier(self) -> None:
        vulnerable = self.example_sbom_document["components"][3]
        original = vulnerable["purl"]
        drifted = original.replace("?type=jar", "?classifier=sources")
        vulnerable["purl"] = drifted
        vulnerable["bom-ref"] = drifted
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("classifier is not supported", result.stderr)

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
        self.assertIn("not canonically percent-encoded", result.stderr)

    def test_rejects_future_review_date(self) -> None:
        self.policy_document["vulnerabilityExceptions"][0]["reviewedAt"] = "2099-12-30"
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("reviewedAt must not be in the future", result.stderr)

    def test_rejects_excessive_exception_validity(self) -> None:
        exception = self.policy_document["vulnerabilityExceptions"][0]
        reviewed = datetime.now(timezone.utc).date()
        exception["reviewedAt"] = reviewed.isoformat()
        exception["expires"] = (reviewed + timedelta(days=31)).isoformat()
        self.write_fixture()

        result = self.prepare_inventory()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("validity must not exceed 30 days", result.stderr)

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

    def test_rejects_expired_vulnerability_exception(self) -> None:
        self.policy_document["vulnerabilityExceptions"][0]["expires"] = "2000-01-01"
        self.policy_document["vulnerabilityExceptions"][0]["reviewedAt"] = "1999-12-17"
        self.write_fixture()
        self.assertEqual(0, self.prepare_inventory().returncode)

        result = self.verify()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("expired vulnerability exception", result.stderr)


if __name__ == "__main__":
    unittest.main()
