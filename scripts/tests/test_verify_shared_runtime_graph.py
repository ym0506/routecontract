from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "verify-shared-runtime-graph.py"

POM_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>io.github.ym0506.routecontract</groupId>
  <artifactId>{artifact}</artifactId>
  <version>0.1.5</version>
  <dependencies>
    <dependency>
      <groupId>com.alibaba</groupId>
      <artifactId>transmittable-thread-local</artifactId>
      <version>2.14.2</version>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>tools.jackson.core</groupId>
      <artifactId>jackson-core</artifactId>
      <version>{jackson}</version>
      <scope>runtime</scope>
    </dependency>
  </dependencies>
</project>
"""
LOCK = """# This is a Gradle generated file for dependency locking.
com.alibaba:transmittable-thread-local:2.14.2=compileClasspath,runtimeClasspath
org.apache.shardingsphere:shardingsphere-infra-executor:{api}=compileClasspath
tools.jackson.core:jackson-core:{jackson}=compileClasspath,runtimeClasspath
empty=annotationProcessor
"""


def load_script():
    spec = importlib.util.spec_from_file_location("verify_shared_runtime_graph_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def module_json(jackson: str) -> str:
    return json.dumps({
        "formatVersion": "1.1",
        "variants": [
            {"name": "apiElements"},
            {
                "name": "runtimeElements",
                "dependencies": [
                    {"group": "com.alibaba", "module": "transmittable-thread-local",
                     "version": {"requires": "2.14.2"}},
                    {"group": "tools.jackson.core", "module": "jackson-core",
                     "version": {"requires": jackson}},
                ],
            },
        ],
    })


class SharedRuntimeGraphTest(unittest.TestCase):
    def setUp(self) -> None:
        self.script = load_script()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.addCleanup(self.temporary_directory.cleanup)

    def write_role(self, role: str, artifact: str, api: str, jackson: str = "3.1.6",
                   module_jackson: str | None = None, lock_jackson: str | None = None) -> list[str]:
        pom = self.root / f"{role}.pom"
        module = self.root / f"{role}.module"
        lock = self.root / f"{role}.lockfile"
        pom.write_text(POM_TEMPLATE.format(artifact=artifact, jackson=jackson), encoding="utf-8")
        module.write_text(module_json(module_jackson or jackson), encoding="utf-8")
        lock.write_text(LOCK.format(api=api, jackson=lock_jackson or jackson), encoding="utf-8")
        return [f"--{role}-pom", str(pom), f"--{role}-module", str(module), f"--{role}-lock", str(lock)]

    def run_check(self, **candidate) -> int:
        reference = self.write_role("reference", "routecontract-shardingsphere-5.5", "5.5.3")
        candidate_args = self.write_role("candidate", "routecontract-shardingsphere-5.4.1-5.5.2", "5.5.2",
                                         **candidate)
        return self.quiet_main(reference + candidate_args)

    def quiet_main(self, arguments: list[str]) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return self.script.main(arguments)

    def test_accepts_identical_runtime_graphs_with_different_compile_only_api(self) -> None:
        self.assertEqual(0, self.run_check())

    def test_rejects_a_different_pom_dependency(self) -> None:
        self.assertEqual(1, self.run_check(jackson="3.1.5", module_jackson="3.1.6", lock_jackson="3.1.6"))

    def test_rejects_a_different_module_metadata_dependency(self) -> None:
        self.assertEqual(1, self.run_check(module_jackson="3.1.5"))

    def test_rejects_a_different_locked_runtime_dependency(self) -> None:
        self.assertEqual(1, self.run_check(lock_jackson="3.1.5"))

    def test_rejects_a_symlinked_input(self) -> None:
        reference = self.write_role("reference", "routecontract-shardingsphere-5.5", "5.5.3")
        candidate = self.write_role("candidate", "routecontract-shardingsphere-5.4.1-5.5.2", "5.5.2")
        link = self.root / "linked.pom"
        link.symlink_to(self.root / "candidate.pom")
        candidate[1] = str(link)
        self.assertEqual(1, self.quiet_main(reference + candidate))


if __name__ == "__main__":
    unittest.main()
