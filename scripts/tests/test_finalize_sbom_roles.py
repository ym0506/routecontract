from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FINALIZER = REPOSITORY_ROOT / "scripts" / "finalize-sbom.py"
GROUP = "io.github.ym0506.routecontract"
VERSION = "0.1.0"


def load_finalizer():
    spec = importlib.util.spec_from_file_location("finalize_sbom_roles_under_test", FINALIZER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.FIRST_PARTY_GROUP = GROUP
    return module


class AggregateRoleCoverageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.finalizer = load_finalizer()

    def purl(self, name: str) -> str:
        project_path = "" if name == "routecontract" else name
        return f"pkg:maven/{GROUP}/{name}@{VERSION}?project_path=%3A{project_path}"

    def record(self, name: str) -> dict[str, object]:
        return {
            "type": "library",
            "group": GROUP,
            "name": name,
            "version": VERSION,
            "licenses": (("id", self.finalizer.LICENSE_ID, self.finalizer.LICENSE_URL),),
        }

    def validate(self, root: str, children: list[str]) -> str:
        root_ref = self.purl(root)
        records = {root_ref: self.record(root)}
        for name in children:
            records[self.purl(name)] = self.record(name)
        graph = {ref: frozenset() for ref in records}
        graph[root_ref] = frozenset(ref for ref in records if ref != root_ref)
        return self.finalizer._validate_role_and_graph(root_ref, records, graph, "test")

    def test_accepts_released_children_only(self) -> None:
        self.assertEqual(
            "routecontract",
            self.validate("routecontract", ["routecontract-shardingsphere-5.5", "mysql-example"]),
        )

    def test_accepts_unreleased_projects_in_the_aggregate(self) -> None:
        self.assertEqual(
            "routecontract",
            self.validate(
                "routecontract",
                [
                    "routecontract-shardingsphere-5.5",
                    "mysql-example",
                    "routecontract-shardingsphere-5.4.1-5.5.2",
                    "mysql-5.4.1-5.5.2-example",
                ],
            ),
        )

    def test_rejects_an_unknown_first_party_child(self) -> None:
        with self.assertRaisesRegex(self.finalizer.SbomError, "first-party role coverage differs"):
            self.validate(
                "routecontract",
                ["routecontract-shardingsphere-5.5", "mysql-example", "other-module"],
            )

    def test_rejects_a_missing_released_child(self) -> None:
        with self.assertRaisesRegex(self.finalizer.SbomError, "first-party role coverage differs"):
            self.validate(
                "routecontract",
                ["mysql-example", "routecontract-shardingsphere-5.4.1-5.5.2"],
            )

    def test_unreleased_projects_are_not_allowed_outside_the_aggregate(self) -> None:
        with self.assertRaisesRegex(self.finalizer.SbomError, "first-party role coverage differs"):
            self.validate("mysql-example", ["routecontract-shardingsphere-5.5", "mysql-5.4.1-5.5.2-example"])


if __name__ == "__main__":
    unittest.main()
