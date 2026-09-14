#!/usr/bin/env python3
"""Acceptance for lock-backed runtime traversal of a merged published SBOM."""

from __future__ import annotations

import copy
import unittest

import test_published_core_project_inventory as core_fixture


checker = core_fixture.checker
DATABIND = "pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.18.9?type=jar"
COMPILE_ANNOTATIONS = "pkg:maven/com.fasterxml.jackson.core/jackson-annotations@2.18.9?type=jar"
RUNTIME_ANNOTATIONS = "pkg:maven/com.fasterxml.jackson.core/jackson-annotations@2.21?type=jar"
GUAVA = "pkg:maven/com.google.guava/guava@32.1.2-jre?type=jar"
J2OBJC = "pkg:maven/com.google.j2objc/j2objc-annotations@2.8?type=jar"
ADDITION = "pkg:maven/com.example/unexplained@1.0?type=jar"


class PublishedConfigurationInventoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.base = core_fixture.PublishedCoreProjectInventoryTest()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.configure()

    def configure(self) -> None:
        self.base.configure(checker.ADAPTER_552_ROOT_NAME)
        self.document = self.base.document
        self.memberships = {
            core_fixture.EXTERNAL_PURL: ("compileClasspath", "runtimeClasspath"),
            DATABIND: ("compileClasspath", "runtimeClasspath"),
            GUAVA: ("compileClasspath", "runtimeClasspath"),
            COMPILE_ANNOTATIONS: ("compileClasspath", "testCompileClasspath"),
            RUNTIME_ANNOTATIONS: ("runtimeClasspath", "testRuntimeClasspath"),
            J2OBJC: ("compileClasspath", "testCompileClasspath"),
        }
        self.add_component(DATABIND, core_fixture.EXTERNAL_PURL)
        self.add_component(GUAVA, core_fixture.EXTERNAL_PURL)
        self.add_component(COMPILE_ANNOTATIONS, DATABIND)
        self.add_component(RUNTIME_ANNOTATIONS, DATABIND)
        self.add_component(J2OBJC, GUAVA)
        self.write_lock()

    def edge(self, purl: str) -> dict[str, object]:
        return next(record for record in self.document["dependencies"] if record["ref"] == purl)

    def add_component(self, purl: str, parent: str) -> None:
        canonical, group, name, version, _ = checker._parse_maven_purl(purl)
        component = core_fixture.fixtures.apache_component(purl, group, name, version)
        component["properties"] = [{"name": "cdx:maven:package:test", "value": "false"}]
        self.document["components"].append(component)
        self.document["dependencies"].append({"ref": purl, "dependsOn": []})
        self.edge(parent)["dependsOn"].append(purl)

    def write_lock(self) -> None:
        lines = ["# Minimal exact compile/runtime membership fixture"]
        for purl, configurations in sorted(self.memberships.items()):
            _, group, name, version, _ = checker._parse_maven_purl(purl)
            lines.append(f"{group}:{name}:{version}={','.join(configurations)}")
        lines.append("empty=annotationProcessor,testAnnotationProcessor")
        self.base.fixture.published_lock.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_accepts_merged_versions_with_exact_compile_and_runtime_memberships(self) -> None:
        before = copy.deepcopy(self.document)
        resolved, pom, runtime = self.base.inventory()
        self.assertEqual(set(self.memberships) | {self.base.core_purl}, set(resolved))
        self.assertEqual(
            {
                "pkg:maven/com.example/safe@1.0",
                "pkg:maven/com.fasterxml.jackson.core/jackson-databind@2.18.9",
                "pkg:maven/com.fasterxml.jackson.core/jackson-annotations@2.21",
                "pkg:maven/com.google.guava/guava@32.1.2-jre",
            },
            runtime,
        )
        self.assertEqual(
            {
                f"pkg:maven/{core_fixture.GROUP}/routecontract-core@0.2.0": "compile",
                "pkg:maven/com.example/safe@1.0": "runtime",
            },
            pom,
        )
        self.assertEqual(before, self.document)

    def test_rejects_unlocked_nodes_including_below_compile_only_node(self) -> None:
        for parent in (DATABIND, J2OBJC):
            with self.subTest(parent=parent):
                self.configure()
                self.add_component(ADDITION, parent)
                with self.assertRaises(checker.PolicyError):
                    self.base.inventory()

    def test_rejects_addition_locked_only_for_tests(self) -> None:
        self.add_component(ADDITION, J2OBJC)
        self.memberships[ADDITION] = ("testCompileClasspath", "testRuntimeClasspath")
        self.write_lock()
        with self.assertRaises(checker.PolicyError):
            self.base.inventory()

    def test_rejects_missing_runtime_nodes_and_edges(self) -> None:
        for mode in ("missing-node", "missing-edge", "only-behind-compile-node"):
            with self.subTest(mode=mode):
                self.configure()
                self.edge(DATABIND)["dependsOn"].remove(RUNTIME_ANNOTATIONS)
                if mode == "missing-node":
                    self.document["components"] = [
                        item for item in self.document["components"]
                        if item["purl"] != RUNTIME_ANNOTATIONS
                    ]
                    self.document["dependencies"] = [
                        item for item in self.document["dependencies"]
                        if item["ref"] != RUNTIME_ANNOTATIONS
                    ]
                elif mode == "only-behind-compile-node":
                    self.edge(J2OBJC)["dependsOn"].append(RUNTIME_ANNOTATIONS)
                with self.assertRaises(checker.PolicyError):
                    self.base.inventory()

    def test_keeps_direct_core_pom_edge_requirement(self) -> None:
        self.edge(self.base.root_purl)["dependsOn"].remove(self.base.core_purl)
        self.edge(core_fixture.EXTERNAL_PURL)["dependsOn"].append(self.base.core_purl)
        with self.assertRaises(checker.PolicyError):
            self.base.inventory()

    def test_keeps_first_party_compile_and_third_party_runtime_pom_scopes(self) -> None:
        for old_scope, new_scope in (("compile", "runtime"), ("runtime", "compile")):
            with self.subTest(old_scope=old_scope):
                self.configure()
                path = self.base.fixture.published_pom
                pom = path.read_text(encoding="utf-8").replace(
                    f"<scope>{old_scope}</scope>", f"<scope>{new_scope}</scope>", 1
                )
                path.write_text(pom, encoding="utf-8")
                with self.assertRaises(checker.PolicyError):
                    self.base.inventory()


if __name__ == "__main__":
    unittest.main()
