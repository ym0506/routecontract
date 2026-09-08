#!/usr/bin/env python3
"""Acceptance for exact adapter-to-core project edges in published inventories."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

import test_verify_supply_chain_policy as fixtures


CHECKER = Path(__file__).resolve().parents[1] / "verify-supply-chain-policy.py"
SPEC = importlib.util.spec_from_file_location("published_core_inventory_checker", CHECKER)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)
GROUP = "io.github.ym0506.routecontract"
VERSION = "0.2.0"
CORE_NAME = "routecontract-core"
EXTERNAL_PURL = "pkg:maven/com.example/safe@1.0?type=jar"


class PublishedCoreProjectInventoryTest(unittest.TestCase):
    def setUp(self) -> None:
        # Composition reuses fixture data without inheriting its entire test suite.
        self.fixture = fixtures.SupplyChainPolicyTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.original_pom = self.fixture.published_pom.read_text(encoding="utf-8")

    def configure(
        self,
        root_name: str = checker.PUBLISHED_ROOT_NAME,
        *,
        core_version: str = VERSION,
        core_name: str = CORE_NAME,
        core_path: str = CORE_NAME,
        core_scope: str = "compile",
    ) -> None:
        self.document = copy.deepcopy(self.fixture.published_sbom_document)
        root = self.document["metadata"]["component"]
        root_purl = f"pkg:maven/{GROUP}/{root_name}@{VERSION}?project_path=%3A{root_name}"
        fixtures.replace_component_purl(self.document, root["purl"], root_purl)
        root.update({"name": root_name, "version": VERSION})
        self.root_purl = root_purl
        self.core_purl = (
            f"pkg:maven/{GROUP}/{core_name}@{core_version}?project_path=%3A{core_path}"
        )
        core = fixtures.apache_component(self.core_purl, GROUP, core_name, core_version)
        core["modified"] = False
        core["properties"] = [{"name": "cdx:maven:package:test", "value": "false"}]
        self.document["components"].append(core)
        self.document["dependencies"][0]["dependsOn"].append(self.core_purl)
        self.document["dependencies"].append({"ref": self.core_purl, "dependsOn": []})

        self.root_name = root_name
        is_552 = root_name == checker.ADAPTER_552_ROOT_NAME
        self.project_name = (
            checker.ADAPTER_552_PROJECT_NAME if is_552 else checker.PUBLISHED_PROJECT_NAME
        )
        self.project_description = (
            checker.ADAPTER_552_PROJECT_DESCRIPTION
            if is_552 else checker.PUBLISHED_PROJECT_DESCRIPTION
        )
        pom = self.original_pom.replace(
            f"<artifactId>{checker.PUBLISHED_ROOT_NAME}</artifactId>",
            f"<artifactId>{root_name}</artifactId>",
            1,
        ).replace("<version>0.1.0</version>", f"<version>{VERSION}</version>", 1)
        pom = pom.replace(checker.PUBLISHED_PROJECT_NAME, self.project_name).replace(
            checker.PUBLISHED_PROJECT_DESCRIPTION, self.project_description
        )
        core_dependency = (
            "    <dependency>\n"
            f"      <groupId>{GROUP}</groupId>\n"
            f"      <artifactId>{core_name}</artifactId>\n"
            f"      <version>{core_version}</version>\n"
            f"      <scope>{core_scope}</scope>\n"
            "    </dependency>\n"
        )
        pom = pom.replace("  <dependencies>\n", "  <dependencies>\n" + core_dependency, 1)
        self.fixture.published_pom.write_text(pom, encoding="utf-8")

    def inventory(self):
        return checker._published_inventory(
            self.document,
            self.fixture.published_pom,
            self.fixture.published_lock,
            expected_root_name=self.root_name,
            expected_project_name=self.project_name,
            expected_project_description=self.project_description,
            expected_dependency_management=(),
        )

    def test_accepts_exact_same_version_core_project_for_both_adapters(self) -> None:
        for root_name in (checker.PUBLISHED_ROOT_NAME, checker.ADAPTER_552_ROOT_NAME):
            with self.subTest(root=root_name):
                self.configure(root_name)
                before = copy.deepcopy(self.document)
                resolved, pom, closure = self.inventory()
                self.assertEqual({self.core_purl, EXTERNAL_PURL}, set(resolved))
                self.assertEqual(
                    {
                        f"pkg:maven/{GROUP}/{CORE_NAME}@{VERSION}": "compile",
                        "pkg:maven/com.example/safe@1.0": "runtime",
                    },
                    pom,
                )
                self.assertEqual({"pkg:maven/com.example/safe@1.0"}, closure)
                self.assertEqual(before, self.document)

    def test_rejects_core_version_different_from_root(self) -> None:
        self.configure(core_version="0.2.1")
        with self.assertRaises(checker.PolicyError):
            self.inventory()

    def test_rejects_wrong_core_project_path(self) -> None:
        self.configure(core_path="another-project")
        with self.assertRaises(checker.PolicyError):
            self.inventory()

    def test_rejects_another_first_party_project_name(self) -> None:
        self.configure(core_name="another-project", core_path="another-project")
        with self.assertRaises(checker.PolicyError):
            self.inventory()

    def test_rejects_core_project_edge_for_unsupported_root(self) -> None:
        self.configure(root_name="routecontract-unrelated")
        with self.assertRaises(checker.PolicyError):
            self.inventory()

    def test_rejects_external_pom_instead_of_default_jar(self) -> None:
        self.configure()
        fixtures.replace_component_purl(
            self.document, EXTERNAL_PURL, "pkg:maven/com.example/safe@1.0?type=pom"
        )
        with self.assertRaises(checker.PolicyError):
            self.inventory()

    def test_rejects_core_reachable_only_through_an_external_dependency(self) -> None:
        self.configure()
        self.document["dependencies"][0]["dependsOn"].remove(self.core_purl)
        external = next(
            record for record in self.document["dependencies"] if record["ref"] == EXTERNAL_PURL
        )
        external["dependsOn"].append(self.core_purl)
        with self.assertRaises(checker.PolicyError):
            self.inventory()

    def test_rejects_core_pom_runtime_scope_instead_of_compile(self) -> None:
        self.configure(core_scope="runtime")
        with self.assertRaises(checker.PolicyError):
            self.inventory()


if __name__ == "__main__":
    unittest.main()
