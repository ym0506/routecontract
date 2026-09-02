#!/usr/bin/env python3
"""Acceptance tests for reviewed CycloneDX license finalization."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FINALIZER = REPOSITORY_ROOT / "scripts" / "finalize-sbom.py"
GROUP = "io.github.ym0506.routecontract"
NAMESPACE = "http://cyclonedx.org/schema/bom/1.6"
JAKARTA_EXPRESSION = (
    "EPL-2.0 OR (GPL-2.0-only WITH Classpath-exception-2.0)"
)
JNA_EXPRESSION = "(Apache-2.0 OR LGPL-2.1-or-later) AND MIT"
JTS_EXPRESSIONS = {
    "jts-core": "EPL-2.0 OR BSD-3-Clause",
}
REQUIRED_EXAMPLE_COORDINATES = (
    ("org.apache.shardingsphere", "shardingsphere-jdbc", "5.5.3"),
    ("org.apache.calcite", "calcite-core", "1.42.0"),
    ("org.apache.calcite", "calcite-linq4j", "1.42.0"),
)
REQUIRED_552_EXAMPLE_COORDINATES = (
    ("org.apache.shardingsphere", "shardingsphere-jdbc", "5.5.2"),
    ("org.apache.calcite", "calcite-core", "1.38.0"),
    ("org.apache.calcite", "calcite-linq4j", "1.38.0"),
)
MYSQL_DOCUMENTATION_URL = "https://dev.mysql.com/doc/refman/8.4/en/preface.html"


def maven_component(
    group: str, name: str, version: str, licenses: list[dict[str, object]]
) -> dict[str, object]:
    purl = f"pkg:maven/{group}/{name}@{version}?type=jar"
    return {
        "type": "library",
        "bom-ref": purl,
        "group": group,
        "name": name,
        "version": version,
        "licenses": licenses,
        "purl": purl,
    }


def append_xml_component(parent: ET.Element, component: dict[str, object]) -> None:
    qname = lambda name: f"{{{NAMESPACE}}}{name}"
    element = ET.SubElement(
        parent,
        qname("component"),
        {"type": str(component["type"]), "bom-ref": str(component["bom-ref"])},
    )
    for field in ("group", "name", "version"):
        ET.SubElement(element, qname(field)).text = str(component[field])
    if "licenses" in component:
        licenses = ET.SubElement(element, qname("licenses"))
        for choice in component["licenses"]:
            if "expression" in choice:
                ET.SubElement(licenses, qname("expression")).text = str(
                    choice["expression"]
                )
            else:
                license_element = ET.SubElement(licenses, qname("license"))
                license_value = choice["license"]
                identifier = "id" if "id" in license_value else "name"
                ET.SubElement(license_element, qname(identifier)).text = str(
                    license_value[identifier]
                )
    ET.SubElement(element, qname("purl")).text = str(component["purl"])


class FinalizeSbomTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source_json = self.root / "source.json"
        self.source_xml = self.root / "source.xml"
        self.output_json = self.root / "output.json"
        self.output_xml = self.root / "output.xml"
        root_purl = (
            f"pkg:maven/{GROUP}/mysql-example@0.1.0?project_path=%3Amysql-example"
        )
        self.root_component = {
            "type": "library",
            "bom-ref": root_purl,
            "group": GROUP,
            "name": "mysql-example",
            "version": "0.1.0",
            "purl": root_purl,
        }
        library_purl = (
            f"pkg:maven/{GROUP}/routecontract-shardingsphere-5.5@0.1.0"
            "?project_path=%3Aroutecontract-shardingsphere-5.5"
        )
        self.library_component = {
            "type": "library",
            "bom-ref": library_purl,
            "group": GROUP,
            "name": "routecontract-shardingsphere-5.5",
            "version": "0.1.0",
            "purl": library_purl,
        }
        core_purl = (
            f"pkg:maven/{GROUP}/routecontract-core@0.1.0"
            "?project_path=%3Aroutecontract-core"
        )
        self.core_component = {
            "type": "library",
            "bom-ref": core_purl,
            "group": GROUP,
            "name": "routecontract-core",
            "version": "0.1.0",
            "purl": core_purl,
        }
        self.components = [
            self.library_component,
            maven_component(
                "jakarta.transaction",
                "jakarta.transaction-api",
                "1.3.3",
                [
                    {"license": {"id": "EPL-2.0"}},
                    {
                        "license": {
                            "id": "GPL-2.0-with-classpath-exception"
                        }
                    },
                ],
            ),
            maven_component(
                "net.java.dev.jna",
                "jna",
                "5.13.0",
                [
                    {"license": {"id": "LGPL-2.1-or-later"}},
                    {"license": {"id": "Apache-2.0"}},
                ],
            ),
            maven_component(
                "org.locationtech.jts",
                "jts-core",
                "1.19.0",
                [
                    {"license": {"id": "EPL-2.0"}},
                    {"license": {"id": "BSD-3-Clause"}},
                ],
            ),
            maven_component(
                "org.apache.shardingsphere",
                "shardingsphere-jdbc",
                "5.5.3",
                [{"license": {"id": "Apache-2.0"}}],
            ),
            maven_component(
                "com.mysql",
                "mysql-connector-j",
                "26.7.0",
                [{"license": {"id": "GPL-2.0-only"}}],
            ),
            maven_component(
                "com.example",
                "safe",
                "1.0.0",
                [{"license": {"id": "Apache-2.0"}}],
            ),
            maven_component(
                "org.apache.calcite",
                "calcite-core",
                "1.42.0",
                [{"license": {"id": "Apache-2.0"}}],
            ),
            maven_component(
                "org.apache.calcite",
                "calcite-linq4j",
                "1.42.0",
                [{"license": {"id": "Apache-2.0"}}],
            ),
            self.core_component,
        ]
        self.write_sources()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_sources(self) -> None:
        serial = "urn:uuid:00000000-0000-0000-0000-000000000001"
        document = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "serialNumber": serial,
            "version": 1,
            "metadata": {
                "timestamp": "2026-08-14T00:00:00Z",
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
                "component": self.root_component,
            },
            "components": self.components,
            "dependencies": [
                {
                    "ref": self.root_component["purl"],
                    "dependsOn": [
                        component["purl"]
                        for component in self.components
                        if component["purl"] != self.core_component["purl"]
                    ],
                },
                *[
                    {
                        "ref": component["purl"],
                        "dependsOn": (
                            [self.core_component["purl"]]
                            if component["purl"] == self.library_component["purl"]
                            and any(
                                candidate["purl"] == self.core_component["purl"]
                                for candidate in self.components
                            )
                            else []
                        ),
                    }
                    for component in self.components
                ],
            ],
        }
        self.source_json.write_text(json.dumps(document) + "\n", encoding="utf-8")

        ET.register_namespace("", NAMESPACE)
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        root = ET.Element(qname("bom"), {"serialNumber": serial, "version": "1"})
        metadata = ET.SubElement(root, qname("metadata"))
        ET.SubElement(metadata, qname("timestamp")).text = "2026-08-14T00:00:00Z"
        tools = ET.SubElement(metadata, qname("tools"))
        tool_components = ET.SubElement(tools, qname("components"))
        tool = ET.SubElement(tool_components, qname("component"), {"type": "application"})
        ET.SubElement(tool, qname("author")).text = "CycloneDX"
        ET.SubElement(tool, qname("name")).text = "cyclonedx-gradle-plugin"
        ET.SubElement(tool, qname("version")).text = "3.4.0"
        append_xml_component(metadata, self.root_component)
        document_licenses = ET.SubElement(metadata, qname("licenses"))
        document_license = ET.SubElement(document_licenses, qname("license"))
        ET.SubElement(document_license, qname("id")).text = "Apache-2.0"
        ET.SubElement(document_license, qname("url")).text = (
            "https://www.apache.org/licenses/LICENSE-2.0.txt"
        )
        components = ET.SubElement(root, qname("components"))
        for component in self.components:
            append_xml_component(components, component)
        dependencies = ET.SubElement(root, qname("dependencies"))
        root_dependency = ET.SubElement(
            dependencies, qname("dependency"), {"ref": str(self.root_component["purl"])}
        )
        for component in self.components:
            if component["purl"] != self.core_component["purl"]:
                ET.SubElement(
                    root_dependency,
                    qname("dependency"),
                    {"ref": str(component["purl"])},
                )
            dependency = ET.SubElement(
                dependencies, qname("dependency"), {"ref": str(component["purl"])}
            )
            if (
                component["purl"] == self.library_component["purl"]
                and any(
                    candidate["purl"] == self.core_component["purl"]
                    for candidate in self.components
                )
            ):
                ET.SubElement(
                    dependency,
                    qname("dependency"),
                    {"ref": str(self.core_component["purl"])},
                )
        ET.ElementTree(root).write(
            self.source_xml, encoding="utf-8", xml_declaration=True
        )

    def run_finalizer(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(FINALIZER), "--first-party-group", GROUP, *arguments],
            cwd=REPOSITORY_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def finalize(self) -> subprocess.CompletedProcess[str]:
        return self.run_finalizer(
            "--pair",
            str(self.source_json),
            str(self.source_xml),
            str(self.output_json),
            str(self.output_xml),
        )

    def test_normalizes_reviewed_test_artifact_licenses_in_both_formats(self) -> None:
        result = self.finalize()
        self.assertEqual(0, result.returncode, result.stderr)
        document = json.loads(self.output_json.read_text(encoding="utf-8"))
        by_name = {component["name"]: component for component in document["components"]}
        self.assertEqual(
            [{"expression": JAKARTA_EXPRESSION}],
            by_name["jakarta.transaction-api"]["licenses"],
        )
        self.assertEqual(
            [{"expression": JNA_EXPRESSION}], by_name["jna"]["licenses"]
        )
        for name, expression in JTS_EXPRESSIONS.items():
            self.assertEqual(
                [{"expression": expression}], by_name[name]["licenses"]
            )
        self.assertNotIn("licenses", by_name["mysql"])
        self.assertEqual(
            [{"type": "documentation", "url": MYSQL_DOCUMENTATION_URL}],
            by_name["mysql"]["externalReferences"],
        )
        self.assertIn(
            {
                "name": "routecontract:license-review",
                "value": "manual-review-required",
            },
            by_name["mysql"]["properties"],
        )
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        tree = ET.parse(self.output_xml)
        xml_by_name = {
            component.findtext(qname("name")): component
            for component in tree.getroot().findall(
                f"{qname('components')}/{qname('component')}"
            )
        }
        self.assertEqual(
            JAKARTA_EXPRESSION,
            xml_by_name["jakarta.transaction-api"].findtext(
                f"{qname('licenses')}/{qname('expression')}"
            ),
        )
        self.assertEqual(
            JNA_EXPRESSION,
            xml_by_name["jna"].findtext(
                f"{qname('licenses')}/{qname('expression')}"
            ),
        )
        for name, expression in JTS_EXPRESSIONS.items():
            self.assertEqual(
                expression,
                xml_by_name[name].findtext(
                    f"{qname('licenses')}/{qname('expression')}"
                ),
            )
        self.assertIsNone(xml_by_name["mysql"].find(qname("licenses")))
        self.assertEqual(
            MYSQL_DOCUMENTATION_URL,
            xml_by_name["mysql"].findtext(
                f"{qname('externalReferences')}/{qname('reference')}/{qname('url')}"
            ),
        )

    def role_pair(
        self, role: str, timestamp: str
    ) -> tuple[Path, Path, Path, Path]:
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        role_names = {
            "aggregate": "routecontract",
            "core": "routecontract-core",
            "adapter553": "routecontract-shardingsphere-5.5",
            "adapter552": "routecontract-shardingsphere-5.5.2",
            "mysql553": "mysql-example",
            "mysql552": "mysql-5.5.2-example",
        }
        if role not in role_names:
            self.fail(f"unexpected role fixture: {role}")

        root_name = role_names[role]

        def first_party_purl(name: str) -> str:
            project_path = "" if name == "routecontract" else name
            return (
                f"pkg:maven/{GROUP}/{name}@0.1.0"
                f"?project_path=%3A{project_path}"
            )

        first_party_components = {
            name: {
                "type": "library",
                "bom-ref": first_party_purl(name),
                "group": GROUP,
                "name": name,
                "version": "0.1.0",
                "purl": first_party_purl(name),
            }
            for name in role_names.values()
        }
        first_party_children = {
            "aggregate": (
                "routecontract-core",
                "routecontract-shardingsphere-5.5",
                "routecontract-shardingsphere-5.5.2",
                "mysql-example",
                "mysql-5.5.2-example",
            ),
            "core": (),
            "adapter553": ("routecontract-core",),
            "adapter552": ("routecontract-core",),
            "mysql553": (
                "routecontract-core",
                "routecontract-shardingsphere-5.5",
            ),
            "mysql552": (
                "routecontract-core",
                "routecontract-shardingsphere-5.5.2",
            ),
        }
        first_party_edges = {
            "aggregate": {
                "routecontract": set(first_party_children["aggregate"]),
                "routecontract-core": set(),
                "routecontract-shardingsphere-5.5": {"routecontract-core"},
                "routecontract-shardingsphere-5.5.2": {"routecontract-core"},
                "mysql-example": {"routecontract-shardingsphere-5.5"},
                "mysql-5.5.2-example": {
                    "routecontract-shardingsphere-5.5.2"
                },
            },
            "core": {"routecontract-core": set()},
            "adapter553": {
                "routecontract-shardingsphere-5.5": {"routecontract-core"},
                "routecontract-core": set(),
            },
            "adapter552": {
                "routecontract-shardingsphere-5.5.2": {"routecontract-core"},
                "routecontract-core": set(),
            },
            "mysql553": {
                "mysql-example": {"routecontract-shardingsphere-5.5"},
                "routecontract-shardingsphere-5.5": {"routecontract-core"},
                "routecontract-core": set(),
            },
            "mysql552": {
                "mysql-5.5.2-example": {
                    "routecontract-shardingsphere-5.5.2"
                },
                "routecontract-shardingsphere-5.5.2": {"routecontract-core"},
                "routecontract-core": set(),
            },
        }

        # Keep reviewed/common dependencies identical, then add only the pinned
        # ShardingSphere/Calcite versions implied by the MySQL profile(s).
        pinned_groups = {"org.apache.shardingsphere", "org.apache.calcite"}
        third_party_components = [
            copy.deepcopy(component)
            for component in self.components
            if component.get("group") != GROUP
            and component.get("group") not in pinned_groups
        ]
        coordinates: tuple[tuple[str, str, str], ...] = ()
        if role in {"aggregate", "mysql553"}:
            coordinates += REQUIRED_EXAMPLE_COORDINATES
        if role in {"aggregate", "mysql552"}:
            coordinates += REQUIRED_552_EXAMPLE_COORDINATES
        third_party_components.extend(
            maven_component(
                group,
                name,
                version,
                [{"license": {"id": "Apache-2.0"}}],
            )
            for group, name, version in coordinates
        )

        root_component = first_party_components[root_name]
        child_components = [
            first_party_components[name] for name in first_party_children[role]
        ]
        all_components = [*child_components, *third_party_components]
        dependency_records: list[dict[str, object]] = []
        for name in (root_name, *first_party_children[role]):
            targets = [
                first_party_purl(target)
                for target in sorted(first_party_edges[role][name])
            ]
            if name == root_name:
                targets.extend(str(component["purl"]) for component in third_party_components)
            dependency_records.append(
                {"ref": first_party_purl(name), "dependsOn": targets}
            )
        dependency_records.extend(
            {"ref": str(component["purl"]), "dependsOn": []}
            for component in third_party_components
        )

        serial = "urn:uuid:00000000-0000-0000-0000-000000000001"
        document = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "serialNumber": serial,
            "version": 1,
            "metadata": {
                "timestamp": timestamp,
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
                "component": root_component,
            },
            "components": all_components,
            "dependencies": dependency_records,
        }

        ET.register_namespace("", NAMESPACE)
        xml_root = ET.Element(
            qname("bom"), {"serialNumber": serial, "version": "1"}
        )
        metadata = ET.SubElement(xml_root, qname("metadata"))
        ET.SubElement(metadata, qname("timestamp")).text = timestamp
        tools = ET.SubElement(metadata, qname("tools"))
        tool_components = ET.SubElement(tools, qname("components"))
        tool = ET.SubElement(
            tool_components, qname("component"), {"type": "application"}
        )
        ET.SubElement(tool, qname("author")).text = "CycloneDX"
        ET.SubElement(tool, qname("name")).text = "cyclonedx-gradle-plugin"
        ET.SubElement(tool, qname("version")).text = "3.4.0"
        append_xml_component(metadata, root_component)
        document_licenses = ET.SubElement(metadata, qname("licenses"))
        document_license = ET.SubElement(document_licenses, qname("license"))
        ET.SubElement(document_license, qname("id")).text = "Apache-2.0"
        ET.SubElement(document_license, qname("url")).text = (
            "https://www.apache.org/licenses/LICENSE-2.0.txt"
        )
        components = ET.SubElement(xml_root, qname("components"))
        for component in all_components:
            append_xml_component(components, component)
        dependencies = ET.SubElement(xml_root, qname("dependencies"))
        for entry in dependency_records:
            dependency = ET.SubElement(
                dependencies, qname("dependency"), {"ref": str(entry["ref"])}
            )
            for target in entry["dependsOn"]:
                ET.SubElement(
                    dependency, qname("dependency"), {"ref": str(target)}
                )
        tree = ET.ElementTree(xml_root)

        source_json = self.root / f"{role}-source.json"
        source_xml = self.root / f"{role}-source.xml"
        output_json = self.root / f"{role}-output.json"
        output_xml = self.root / f"{role}-output.xml"
        source_json.write_text(json.dumps(document) + "\n", encoding="utf-8")
        tree.write(source_xml, encoding="utf-8", xml_declaration=True)
        return source_json, source_xml, output_json, output_xml

    def six_role_pairs(self) -> tuple[tuple[Path, Path, Path, Path], ...]:
        return (
            self.role_pair("aggregate", "2026-08-14T00:00:00Z"),
            self.role_pair("core", "2026-08-14T00:00:00.500Z"),
            self.role_pair("adapter553", "2026-08-14T00:00:01Z"),
            self.role_pair("adapter552", "2026-08-14T00:00:01.500Z"),
            self.role_pair("mysql553", "2026-08-14T00:00:02.123Z"),
            self.role_pair("mysql552", "2026-08-14T00:00:03.456Z"),
        )

    def run_role_pairs(
        self, pairs: tuple[tuple[Path, Path, Path, Path], ...]
    ) -> subprocess.CompletedProcess[str]:
        arguments: list[str] = []
        for pair in pairs:
            arguments.extend(("--pair", *(str(path) for path in pair)))
        return self.run_finalizer(*arguments)

    def test_accepts_distinct_valid_timestamps_across_six_roles(self) -> None:
        pairs = self.six_role_pairs()
        result = self.run_role_pairs(pairs)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(12, sum(path.exists() for pair in pairs for path in pair[2:]))

    def test_aggregate_links_both_mysql_profiles_to_one_container_leaf(self) -> None:
        pairs = self.six_role_pairs()
        result = self.run_role_pairs(pairs)
        self.assertEqual(0, result.returncode, result.stderr)

        document = json.loads(pairs[0][2].read_text(encoding="utf-8"))
        containers = [
            component
            for component in document["components"]
            if component.get("type") == "container"
            and component.get("name") == "mysql"
        ]
        self.assertEqual(1, len(containers))
        container_purl = containers[0]["purl"]
        graph = {
            entry["ref"]: entry["dependsOn"] for entry in document["dependencies"]
        }
        for example_name in ("mysql-example", "mysql-5.5.2-example"):
            self.assertIn(container_purl, graph[first_party_purl := (
                f"pkg:maven/{GROUP}/{example_name}@0.1.0"
                f"?project_path=%3A{example_name}"
            )], first_party_purl)
        self.assertEqual([], graph[container_purl])

    def test_mysql552_profile_requires_all_pinned_coordinates(self) -> None:
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        for group, name, version in REQUIRED_552_EXAMPLE_COORDINATES:
            with self.subTest(coordinate=f"{group}:{name}:{version}"):
                source_json, source_xml, output_json, output_xml = self.role_pair(
                    "mysql552", "2026-08-14T00:00:03.456Z"
                )
                target_purl = f"pkg:maven/{group}/{name}@{version}?type=jar"
                document = json.loads(source_json.read_text(encoding="utf-8"))
                document["components"] = [
                    component
                    for component in document["components"]
                    if component["purl"] != target_purl
                ]
                for entry in document["dependencies"]:
                    entry["dependsOn"] = [
                        ref for ref in entry["dependsOn"] if ref != target_purl
                    ]
                document["dependencies"] = [
                    entry
                    for entry in document["dependencies"]
                    if entry["ref"] != target_purl
                ]
                source_json.write_text(json.dumps(document) + "\n", encoding="utf-8")

                tree = ET.parse(source_xml)
                components = tree.getroot().find(qname("components"))
                dependencies = tree.getroot().find(qname("dependencies"))
                self.assertIsNotNone(components)
                self.assertIsNotNone(dependencies)
                for component in list(components):
                    if component.findtext(qname("purl")) == target_purl:
                        components.remove(component)
                for entry in list(dependencies):
                    if entry.get("ref") == target_purl:
                        dependencies.remove(entry)
                        continue
                    for target in list(entry):
                        if target.get("ref") == target_purl:
                            entry.remove(target)
                tree.write(source_xml, encoding="utf-8", xml_declaration=True)

                result = self.run_finalizer(
                    "--pair",
                    str(source_json),
                    str(source_xml),
                    str(output_json),
                    str(output_xml),
                )
                self.assertNotEqual(0, result.returncode)
                self.assertIn(
                    "Example SBOM must contain exactly the pinned Maven versions",
                    result.stderr,
                )

    def test_release_collection_rejects_cross_role_fingerprint_drift(self) -> None:
        pairs = self.six_role_pairs()
        aggregate_json, aggregate_xml, _, _ = pairs[0]
        document = json.loads(aggregate_json.read_text(encoding="utf-8"))
        core_json = next(
            component
            for component in document["components"]
            if component["name"] == "routecontract-core"
        )
        core_json["description"] = "context-specific drift"
        aggregate_json.write_text(json.dumps(document) + "\n", encoding="utf-8")

        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        tree = ET.parse(aggregate_xml)
        core_xml = next(
            component
            for component in tree.getroot().findall(
                f"{qname('components')}/{qname('component')}"
            )
            if component.findtext(qname("name")) == "routecontract-core"
        )
        purl_index = list(core_xml).index(core_xml.find(qname("purl")))
        description = ET.Element(qname("description"))
        description.text = "context-specific drift"
        core_xml.insert(purl_index, description)
        tree.write(aggregate_xml, encoding="utf-8", xml_declaration=True)

        result = self.run_role_pairs(pairs)

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "first-party module records differ across roles: routecontract-core",
            result.stderr,
        )

    def test_release_pair_rejects_wrong_first_party_dependency_ownership(self) -> None:
        pairs = self.six_role_pairs()
        example_json, example_xml, _, _ = pairs[-1]
        core_purl = str(self.core_component["purl"])
        document = json.loads(example_json.read_text(encoding="utf-8"))
        document["dependencies"][0]["dependsOn"].append(core_purl)
        example_json.write_text(json.dumps(document) + "\n", encoding="utf-8")

        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        tree = ET.parse(example_xml)
        dependencies = tree.getroot().find(qname("dependencies"))
        self.assertIsNotNone(dependencies)
        ET.SubElement(
            list(dependencies)[0], qname("dependency"), {"ref": core_purl}
        )
        tree.write(example_xml, encoding="utf-8", xml_declaration=True)

        result = self.run_role_pairs(pairs)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("first-party dependency ownership differs", result.stderr)

    def test_release_collection_requires_all_six_roles(self) -> None:
        pairs = self.six_role_pairs()

        result = self.run_role_pairs(pairs[:-1])

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "exactly aggregate, core, adapter553, adapter552, mysql553, and mysql552 pairs",
            result.stderr,
        )

    @unittest.skipUnless(
        os.environ.get("ROUTECONTRACT_CYCLONEDX_CLI"),
        "set ROUTECONTRACT_CYCLONEDX_CLI to run official CycloneDX validation",
    )
    def test_finalized_synthetic_pair_is_official_cyclonedx_valid(self) -> None:
        result = self.finalize()
        self.assertEqual(0, result.returncode, result.stderr)
        executable = os.environ["ROUTECONTRACT_CYCLONEDX_CLI"]
        for path, input_format in (
            (self.output_json, "json"),
            (self.output_xml, "xml"),
        ):
            with self.subTest(input_format=input_format):
                validation = subprocess.run(
                    [
                        executable,
                        "validate",
                        "--input-file",
                        str(path),
                        "--input-format",
                        input_format,
                        "--input-version",
                        "v1_6",
                        "--fail-on-errors",
                    ],
                    cwd=REPOSITORY_ROOT,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(
                    0,
                    validation.returncode,
                    validation.stdout + validation.stderr,
                )

    def test_verify_rejects_a_changed_container_documentation_url(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        document = json.loads(self.output_json.read_text(encoding="utf-8"))
        container = next(
            component for component in document["components"] if component["name"] == "mysql"
        )
        container["externalReferences"][0]["url"] = "https://example.invalid/"
        self.output_json.write_text(json.dumps(document) + "\n", encoding="utf-8")

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("JSON/XML component records differ", result.stderr)

    def test_rejects_unreviewed_jna_version(self) -> None:
        self.components[2]["version"] = "5.14.0"
        self.components[2]["purl"] = "pkg:maven/net.java.dev.jna/jna@5.14.0?type=jar"
        self.components[2]["bom-ref"] = self.components[2]["purl"]
        self.write_sources()

        result = self.finalize()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Reviewed Maven component identity differs", result.stderr)

    def test_rejects_reviewed_component_with_a_forged_purl(self) -> None:
        forged = "pkg:maven/evil/not-jna@99?type=jar"
        self.components[2]["purl"] = forged
        self.components[2]["bom-ref"] = forged
        self.write_sources()

        result = self.finalize()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Reviewed Maven component identity differs", result.stderr)

    def test_rejects_connector_with_a_forged_purl(self) -> None:
        forged = "pkg:maven/evil/not-connector@99?type=jar"
        self.components[5]["purl"] = forged
        self.components[5]["bom-ref"] = forged
        self.write_sources()

        result = self.finalize()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Reviewed Maven component identity differs", result.stderr)

    def test_rejects_each_missing_required_example_coordinate(self) -> None:
        original = copy.deepcopy(self.components)
        for group, name, version in REQUIRED_EXAMPLE_COORDINATES:
            with self.subTest(coordinate=f"{group}:{name}:{version}"):
                self.components = [
                    component
                    for component in copy.deepcopy(original)
                    if not (
                        component.get("group") == group
                        and component.get("name") == name
                    )
                ]
                self.write_sources()

                result = self.finalize()

                self.assertNotEqual(0, result.returncode)
                self.assertIn(
                    "Example SBOM must contain exactly the pinned Maven versions",
                    result.stderr,
                )
        self.components = original

    def test_rejects_each_wrong_required_example_version(self) -> None:
        original = copy.deepcopy(self.components)
        for group, name, version in REQUIRED_EXAMPLE_COORDINATES:
            with self.subTest(coordinate=f"{group}:{name}:{version}"):
                self.components = copy.deepcopy(original)
                component = next(
                    item
                    for item in self.components
                    if item.get("group") == group and item.get("name") == name
                )
                component["version"] = "0.0.0"
                component["purl"] = f"pkg:maven/{group}/{name}@0.0.0?type=jar"
                component["bom-ref"] = component["purl"]
                self.write_sources()

                result = self.finalize()

                self.assertNotEqual(0, result.returncode)
                self.assertIn("Unexpected Maven component version", result.stderr)
        self.components = original

    def test_rejects_percent_encoded_required_coordinate_alias_duplicates(self) -> None:
        original = copy.deepcopy(self.components)
        coordinates = (
            ("org.apache.shardingsphere", "shardingsphere-jdbc", "5.5.3"),
            ("org.apache.calcite", "calcite-core", "1.42.0"),
        )
        for group, name, version in coordinates:
            alias_group = group.replace(".", "%2E", 1)
            alias = maven_component(
                alias_group,
                name,
                version,
                [{"license": {"id": "Apache-2.0"}}],
            )
            for input_format in ("json", "xml"):
                with self.subTest(
                    coordinate=f"{group}:{name}:{version}",
                    input_format=input_format,
                ):
                    self.components = copy.deepcopy(original)
                    self.write_sources()
                    if input_format == "json":
                        document = json.loads(
                            self.source_json.read_text(encoding="utf-8")
                        )
                        document["components"].append(alias)
                        self.source_json.write_text(
                            json.dumps(document) + "\n", encoding="utf-8"
                        )
                    else:
                        qname = lambda field: f"{{{NAMESPACE}}}{field}"
                        tree = ET.parse(self.source_xml)
                        components = tree.getroot().find(qname("components"))
                        self.assertIsNotNone(components)
                        append_xml_component(components, alias)
                        tree.write(
                            self.source_xml,
                            encoding="utf-8",
                            xml_declaration=True,
                        )

                    result = self.finalize()

                    self.assertNotEqual(0, result.returncode)
                    self.assertIn(
                        "Maven purl differs from the pinned producer profile",
                        result.stderr,
                    )
        self.components = original

    def test_rejects_equivalent_noncanonical_maven_prefix_aliases(self) -> None:
        for prefix in ("pkg:Maven/", "PKG:maven/", "pkg://maven/"):
            alias = maven_component(
                "com.example",
                "safe-alias",
                "1.19.0",
                [{"license": {"id": "Apache-2.0"}}],
            )
            alias_purl = (
                f"{prefix}org.locationtech.jts.io/jts-io-common@1.19.0?type=jar"
            )
            alias["purl"] = alias_purl
            alias["bom-ref"] = alias_purl
            for input_format in ("json", "xml"):
                with self.subTest(prefix=prefix, input_format=input_format):
                    self.write_sources()
                    if input_format == "json":
                        document = json.loads(
                            self.source_json.read_text(encoding="utf-8")
                        )
                        document["components"].append(alias)
                        self.source_json.write_text(
                            json.dumps(document) + "\n", encoding="utf-8"
                        )
                    else:
                        qname = lambda field: f"{{{NAMESPACE}}}{field}"
                        tree = ET.parse(self.source_xml)
                        components = tree.getroot().find(qname("components"))
                        self.assertIsNotNone(components)
                        append_xml_component(components, alias)
                        tree.write(
                            self.source_xml,
                            encoding="utf-8",
                            xml_declaration=True,
                        )

                    result = self.finalize()

                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("invalid Maven purl", result.stderr)

    def test_rejects_noncanonical_maven_qualifier_keys_in_each_format(self) -> None:
        for qualifier_key in ("Type", "1type", "%74ype", "type!"):
            alias = maven_component(
                "com.example",
                "qualifier-alias",
                "1.0.0",
                [{"license": {"id": "Apache-2.0"}}],
            )
            alias_purl = (
                "pkg:maven/com.example/qualifier-alias@1.0.0?"
                f"{qualifier_key}=jar"
            )
            alias["purl"] = alias_purl
            alias["bom-ref"] = alias_purl
            for input_format in ("json", "xml"):
                with self.subTest(
                    qualifier_key=qualifier_key,
                    input_format=input_format,
                ):
                    self.write_sources()
                    if input_format == "json":
                        document = json.loads(
                            self.source_json.read_text(encoding="utf-8")
                        )
                        document["components"].append(alias)
                        self.source_json.write_text(
                            json.dumps(document) + "\n", encoding="utf-8"
                        )
                    else:
                        qname = lambda field: f"{{{NAMESPACE}}}{field}"
                        tree = ET.parse(self.source_xml)
                        components = tree.getroot().find(qname("components"))
                        self.assertIsNotNone(components)
                        append_xml_component(components, alias)
                        tree.write(
                            self.source_xml,
                            encoding="utf-8",
                            xml_declaration=True,
                        )

                    result = self.finalize()

                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("invalid Maven purl qualifier key", result.stderr)

    def test_verify_rejects_each_jts_license_list_instead_of_expression(self) -> None:
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        for component_name in JTS_EXPRESSIONS:
            with self.subTest(component=component_name):
                finalized = self.finalize()
                self.assertEqual(0, finalized.returncode, finalized.stderr)
                document = json.loads(self.output_json.read_text(encoding="utf-8"))
                jts_json = next(
                    component
                    for component in document["components"]
                    if component["name"] == component_name
                )
                jts_json["licenses"] = [
                    {"license": {"id": "EPL-2.0"}},
                    {"license": {"id": "BSD-3-Clause"}},
                ]
                self.output_json.write_text(
                    json.dumps(document) + "\n", encoding="utf-8"
                )

                tree = ET.parse(self.output_xml)
                jts_xml = next(
                    component
                    for component in tree.getroot().findall(
                        f"{qname('components')}/{qname('component')}"
                    )
                    if component.findtext(qname("name")) == component_name
                )
                licenses = jts_xml.find(qname("licenses"))
                self.assertIsNotNone(licenses)
                licenses.clear()
                for identifier in ("EPL-2.0", "BSD-3-Clause"):
                    choice = ET.SubElement(licenses, qname("license"))
                    ET.SubElement(choice, qname("id")).text = identifier
                tree.write(self.output_xml, encoding="utf-8", xml_declaration=True)

                result = self.run_finalizer(
                    "--verify-pair", str(self.output_json), str(self.output_xml)
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn("Reviewed license metadata is missing", result.stderr)

    def test_rejects_every_reintroduced_jts_io_version(self) -> None:
        original = copy.deepcopy(self.components)
        for version in ("1.18.2", "1.19.0", "1.20.0"):
            with self.subTest(version=version):
                self.components = copy.deepcopy(original)
                self.components.append(
                    maven_component(
                        "org.locationtech.jts.io",
                        "jts-io-common",
                        version,
                        [{"license": {"id": "Apache-2.0"}}],
                    )
                )
                self.write_sources()

                result = self.finalize()

                self.assertNotEqual(0, result.returncode)
                self.assertIn(
                    "JTS I/O Common is forbidden by the pinned dependency contract",
                    result.stderr,
                )
        self.components = original

    def test_rejects_jts_io_reintroduced_only_in_json(self) -> None:
        document = json.loads(self.source_json.read_text(encoding="utf-8"))
        document["components"].append(
            maven_component(
                "org.locationtech.jts.io",
                "jts-io-common",
                "99.0.0",
                [{"license": {"id": "Apache-2.0"}}],
            )
        )
        self.source_json.write_text(json.dumps(document) + "\n", encoding="utf-8")

        result = self.finalize()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("JTS I/O Common is forbidden", result.stderr)

    def test_rejects_jts_io_reintroduced_only_in_xml(self) -> None:
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        tree = ET.parse(self.source_xml)
        components = tree.getroot().find(qname("components"))
        self.assertIsNotNone(components)
        append_xml_component(
            components,
            maven_component(
                "org.locationtech.jts.io",
                "jts-io-common",
                "99.0.0",
                [{"license": {"id": "Apache-2.0"}}],
            ),
        )
        tree.write(self.source_xml, encoding="utf-8", xml_declaration=True)

        result = self.finalize()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("JTS I/O Common is forbidden", result.stderr)

    def test_rejects_percent_encoded_jts_io_alias_only_in_json(self) -> None:
        component = maven_component(
            "org.locationtech.jts%2Eio",
            "jts-io-common",
            "1.19.0",
            [{"license": {"id": "Apache-2.0"}}],
        )
        document = json.loads(self.source_json.read_text(encoding="utf-8"))
        document["components"].append(component)
        self.source_json.write_text(json.dumps(document) + "\n", encoding="utf-8")

        result = self.finalize()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("JTS I/O Common is forbidden", result.stderr)

    def test_rejects_percent_encoded_jts_io_alias_only_in_xml(self) -> None:
        component = maven_component(
            "org.locationtech.jts%2Eio",
            "jts-io-common",
            "1.19.0",
            [{"license": {"id": "Apache-2.0"}}],
        )
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        tree = ET.parse(self.source_xml)
        components = tree.getroot().find(qname("components"))
        self.assertIsNotNone(components)
        append_xml_component(components, component)
        tree.write(self.source_xml, encoding="utf-8", xml_declaration=True)

        result = self.finalize()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("JTS I/O Common is forbidden", result.stderr)

    def test_rejects_reviewed_component_missing_from_only_xml(self) -> None:
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        tree = ET.parse(self.source_xml)
        components = tree.getroot().find(qname("components"))
        self.assertIsNotNone(components)
        jna = next(
            component
            for component in components.findall(qname("component"))
            if component.findtext(qname("name")) == "jna"
        )
        components.remove(jna)
        tree.write(self.source_xml, encoding="utf-8", xml_declaration=True)

        result = self.finalize()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("JSON/XML reviewed Maven component mismatch", result.stderr)

    def test_verify_rejects_duplicate_json_keys_at_any_depth(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        content = self.output_json.read_text(encoding="utf-8")
        content = content.replace(
            '"bomFormat": "CycloneDX",',
            '"bomFormat": "bogus",\n  "bomFormat": "CycloneDX",',
            1,
        )
        self.output_json.write_text(content, encoding="utf-8")

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Duplicate JSON key: bomFormat", result.stderr)

    def test_verify_rejects_conflicting_json_first_party_license_name(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        document = json.loads(self.output_json.read_text(encoding="utf-8"))
        document["metadata"]["component"]["licenses"][0]["license"][
            "name"
        ] = "conflicting name"
        self.output_json.write_text(json.dumps(document) + "\n", encoding="utf-8")

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("ambiguous license object", result.stderr)

    def test_verify_rejects_conflicting_json_document_license(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        document = json.loads(self.output_json.read_text(encoding="utf-8"))
        document["metadata"]["licenses"][0]["license"]["id"] = "MIT"
        self.output_json.write_text(json.dumps(document) + "\n", encoding="utf-8")

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("JSON metadata differs", result.stderr)

    def test_verify_rejects_ordinary_third_party_license_drift(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        document = json.loads(self.output_json.read_text(encoding="utf-8"))
        safe = next(
            component
            for component in document["components"]
            if component["name"] == "safe"
        )
        safe["licenses"] = [{"license": {"id": "MIT"}}]
        self.output_json.write_text(json.dumps(document) + "\n", encoding="utf-8")

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("JSON/XML component records differ", result.stderr)

    def test_verify_rejects_unknown_component_field(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        document = json.loads(self.output_json.read_text(encoding="utf-8"))
        document["components"][-1]["notCycloneDx"] = True
        self.output_json.write_text(json.dumps(document) + "\n", encoding="utf-8")

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unsupported CycloneDX fields", result.stderr)

    def test_verify_rejects_unknown_document_field(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        document = json.loads(self.output_json.read_text(encoding="utf-8"))
        document["notCycloneDx"] = True
        self.output_json.write_text(json.dumps(document) + "\n", encoding="utf-8")

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("document fields differ", result.stderr)

    def test_verify_rejects_out_of_order_xml_component_field(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        tree = ET.parse(self.output_xml)
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
        tree.write(self.output_xml, encoding="utf-8", xml_declaration=True)

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("component child order", result.stderr)

    def test_verify_rejects_reversed_xml_first_party_license_children(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        tree = ET.parse(self.output_xml)
        license_element = tree.getroot().find(
            f"{qname('metadata')}/{qname('component')}/{qname('licenses')}/{qname('license')}"
        )
        self.assertIsNotNone(license_element)
        identifier, url = list(license_element)
        license_element.remove(identifier)
        license_element.remove(url)
        license_element.extend([url, identifier])
        tree.write(self.output_xml, encoding="utf-8", xml_declaration=True)

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("ambiguous license object", result.stderr)

    def test_verify_rejects_nested_xml_container_property_content(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        tree = ET.parse(self.output_xml)
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
        tree.write(self.output_xml, encoding="utf-8", xml_declaration=True)

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("unambiguous XML leaf", result.stderr)

    def test_rejects_utf16_xml_with_dtd_and_entity(self) -> None:
        content = self.source_xml.read_text(encoding="utf-8")
        declaration_end = content.index("?>") + 2
        content = (
            content[:declaration_end]
            + "\n<!DOCTYPE bom [<!ENTITY x 'mysql-example'>]>"
            + content[declaration_end:]
        )
        content = content.replace(">mysql-example<", ">&x;<", 1)
        content = content.replace("encoding='utf-8'", "encoding='utf-16'")
        content = content.replace('encoding="utf-8"', 'encoding="utf-16"')
        self.source_xml.write_bytes(content.encode("utf-16"))

        result = self.finalize()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("CycloneDX XML must be UTF-8", result.stderr)

    def test_rejects_nested_component_collection(self) -> None:
        self.components[0]["components"] = [self.components.pop(1)]
        self.write_sources()

        result = self.finalize()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Nested JSON components are not supported", result.stderr)

    def test_rejects_nested_metadata_component_collection(self) -> None:
        self.root_component["components"] = [self.components.pop(0)]
        self.write_sources()

        result = self.finalize()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Nested JSON components are not supported", result.stderr)

    def test_rejects_explicit_null_nested_component_collection(self) -> None:
        self.root_component["components"] = None
        self.write_sources()

        result = self.finalize()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Nested JSON components are not supported", result.stderr)

    def test_rejects_nested_xml_metadata_component_collection(self) -> None:
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        tree = ET.parse(self.source_xml)
        metadata_component = tree.getroot().find(
            f"{qname('metadata')}/{qname('component')}"
        )
        self.assertIsNotNone(metadata_component)
        ET.SubElement(metadata_component, qname("components"))
        tree.write(self.source_xml, encoding="utf-8", xml_declaration=True)

        result = self.finalize()

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Nested XML components are not supported", result.stderr)

    def test_verify_rejects_utf8_bom_in_each_format(self) -> None:
        for format_name in ("json", "xml"):
            with self.subTest(format=format_name):
                self.write_sources()
                self.assertEqual(0, self.finalize().returncode)
                path = self.output_json if format_name == "json" else self.output_xml
                path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
                result = self.run_finalizer(
                    "--verify-pair", str(self.output_json), str(self.output_xml)
                )
                self.assertNotEqual(0, result.returncode)
                self.assertIn("must not contain a UTF-8 BOM", result.stderr)

    def test_verify_rejects_non_utf8_xml_declaration_over_utf8_bytes(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        text = self.output_xml.read_text(encoding="utf-8")
        self.output_xml.write_text(
            text.replace("encoding='utf-8'", "encoding='ISO-8859-1'", 1),
            encoding="utf-8",
        )

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("must declare XML 1.0 with UTF-8", result.stderr)

    def test_verify_rejects_xml_comment_and_processing_instruction(self) -> None:
        for hidden in ("<!--hidden-->", "<?route hidden?>"):
            with self.subTest(hidden=hidden):
                self.write_sources()
                self.assertEqual(0, self.finalize().returncode)
                text = self.output_xml.read_text(encoding="utf-8")
                self.output_xml.write_text(
                    text.replace("<name>safe</name>", f"<name>sa{hidden}fe</name>", 1),
                    encoding="utf-8",
                )
                result = self.run_finalizer(
                    "--verify-pair", str(self.output_json), str(self.output_xml)
                )
                self.assertNotEqual(0, result.returncode)
                self.assertIn("comments or processing instructions", result.stderr)

    def test_verify_rejects_json_control_character(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        document = json.loads(self.output_json.read_text(encoding="utf-8"))
        document["metadata"]["timestamp"] = "2026-08-14T00:00:00Z\x00"
        self.output_json.write_text(json.dumps(document) + "\n", encoding="utf-8")

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("control character", result.stderr)

    def test_verify_rejects_timestamp_drift(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        tree = ET.parse(self.output_xml)
        timestamp = tree.getroot().find(f"{qname('metadata')}/{qname('timestamp')}")
        self.assertIsNotNone(timestamp)
        timestamp.text = "2026-08-14T00:00:01Z"
        tree.write(self.output_xml, encoding="utf-8", xml_declaration=True)

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("metadata timestamp or tools differ", result.stderr)

    def test_verify_rejects_invalid_timestamp_within_a_pair(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        document = json.loads(self.output_json.read_text(encoding="utf-8"))
        document["metadata"]["timestamp"] = "not-rfc3339"
        self.output_json.write_text(json.dumps(document) + "\n", encoding="utf-8")

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("RFC 3339 UTC timestamp", result.stderr)

    def test_verify_rejects_ordinary_component_name_drift(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        tree = ET.parse(self.output_xml)
        safe = next(
            component
            for component in tree.getroot().findall(
                f"{qname('components')}/{qname('component')}"
            )
            if component.findtext(qname("name")) == "safe"
        )
        safe.find(qname("name")).text = "not-safe"
        tree.write(self.output_xml, encoding="utf-8", xml_declaration=True)

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Maven purl does not match group/name/version", result.stderr)

    def test_verify_rejects_every_supported_component_field_drift(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        original = json.loads(self.output_json.read_text(encoding="utf-8"))
        mutations = {
            "type": lambda component: component.__setitem__("type", "framework"),
            "group": lambda component: component.__setitem__("group", "com.changed"),
            "name": lambda component: component.__setitem__("name", "changed-safe"),
            "version": lambda component: component.__setitem__("version", "2.0.0"),
            "publisher": lambda component: component.__setitem__("publisher", "Changed"),
            "description": lambda component: component.__setitem__(
                "description", "Changed description"
            ),
            "scope": lambda component: component.__setitem__("scope", "excluded"),
            "hashes": lambda component: component.__setitem__(
                "hashes", [{"alg": "SHA-256", "content": "a" * 64}]
            ),
            "licenses": lambda component: component.__setitem__(
                "licenses", [{"license": {"id": "MIT"}}]
            ),
            "purl": lambda component: component.__setitem__(
                "purl", "pkg:maven/com.example/safe@2.0.0?type=jar"
            ),
            "externalReferences": lambda component: component.__setitem__(
                "externalReferences",
                [{"type": "website", "url": "https://example.invalid/changed"}],
            ),
            "modified": lambda component: component.__setitem__("modified", True),
            "properties": lambda component: component.__setitem__(
                "properties", [{"name": "changed", "value": "true"}]
            ),
        }
        for field, mutate in mutations.items():
            with self.subTest(field=field):
                document = json.loads(json.dumps(original))
                component = next(
                    item for item in document["components"] if item["name"] == "safe"
                )
                mutate(component)
                self.output_json.write_text(
                    json.dumps(document) + "\n", encoding="utf-8"
                )
                result = self.run_finalizer(
                    "--verify-pair", str(self.output_json), str(self.output_xml)
                )
                self.assertNotEqual(0, result.returncode, field)

    def test_verify_rejects_pinned_metadata_tool_drift(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        document = json.loads(self.output_json.read_text(encoding="utf-8"))
        document["metadata"]["tools"]["components"][0]["version"] = "3.4.1"
        self.output_json.write_text(json.dumps(document) + "\n", encoding="utf-8")

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("pinned CycloneDX producer", result.stderr)

    def test_verify_rejects_asymmetric_dependency_edge(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        tree = ET.parse(self.output_xml)
        root_edge = tree.getroot().find(f"{qname('dependencies')}/{qname('dependency')}")
        self.assertIsNotNone(root_edge)
        root_edge.remove(list(root_edge)[0])
        tree.write(self.output_xml, encoding="utf-8", xml_declaration=True)

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("JSON/XML dependency graphs differ", result.stderr)

    def test_verify_rejects_paired_graph_missing_leaf_record(self) -> None:
        self.assertEqual(0, self.finalize().returncode)
        document = json.loads(self.output_json.read_text(encoding="utf-8"))
        safe_purl = next(
            component["purl"]
            for component in document["components"]
            if component["name"] == "safe"
        )
        document["dependencies"] = [
            record for record in document["dependencies"] if record["ref"] != safe_purl
        ]
        self.output_json.write_text(json.dumps(document) + "\n", encoding="utf-8")
        qname = lambda name: f"{{{NAMESPACE}}}{name}"
        tree = ET.parse(self.output_xml)
        dependencies = tree.getroot().find(qname("dependencies"))
        self.assertIsNotNone(dependencies)
        leaf = next(item for item in dependencies if item.get("ref") == safe_purl)
        dependencies.remove(leaf)
        tree.write(self.output_xml, encoding="utf-8", xml_declaration=True)

        result = self.run_finalizer(
            "--verify-pair", str(self.output_json), str(self.output_xml)
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("exactly one record per node", result.stderr)


if __name__ == "__main__":
    unittest.main()
