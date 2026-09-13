from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import json

from test_summarize_test_results import CURRENT_RELEASE_SUITES


SCRIPT = Path(__file__).resolve().parents[1] / "summarize_java_runtime.py"
SPEC = importlib.util.spec_from_file_location("java_runtime_summary", SCRIPT)
runtime_summary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime_summary)

# These partitions are an independent acceptance fixture, not read from the
# helper's module declarations. The source inventory is checked separately.
MODULES = (
    ("core", "routecontract-core", 7),
    ("adapter553", "routecontract-shardingsphere-5.5", 7),
    ("adapter552", "routecontract-shardingsphere-5.5.2", 6),
    ("mysql553", "examples/mysql", 4),
    ("mysql552", "examples/mysql-5.5.2", 2),
)
ENTRIES = (
    "io/github/ym0506/routecontract/RouteContract.class",
    "io/github/ym0506/routecontract/shardingsphere553/internal/RouteContract553SqlExecutionHook.class",
    "io/github/ym0506/routecontract/shardingsphere552/internal/RouteContract552SqlExecutionHook.class",
)


class JavaRuntimeSummaryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.java_home = self.root / "java21"
        self.java = self.java_home / "bin/java"
        self.output = self.root / "build/runtime.json"
        self.output.parent.mkdir()
        self.log = self.root / "gradle.log"
        self.workers = []
        self.reports = []
        remaining = iter(CURRENT_RELEASE_SUITES.items())
        for number, (name, relative, count) in enumerate(MODULES, 1):
            directory = self.root / relative
            results = directory / "build/test-results/test"
            results.mkdir(parents=True)
            reports = []
            for _ in range(count):
                suite, tests = next(remaining)
                xml = ET.Element("testsuite", name=suite, tests=str(tests),
                                 failures="0", errors="0", skipped="0", hostname="private-host")
                for index in range(tests):
                    ET.SubElement(xml, "testcase", name=f"case-{index}", classname=suite, time="0.1")
                ET.SubElement(xml, "system-out").text = "password=private-fixture-secret"
                report = results / f"TEST-{suite}.xml"
                ET.ElementTree(xml).write(report)
                reports.append(report)
            self.reports.append(reports)
            self.workers.append(
                f"Starting process 'Gradle Test Executor {number}'. Working directory: {directory} "
                f"Command: {self.java} -ea worker.org.gradle.process.internal.worker.GradleWorkerMain "
                f"'Gradle Test Executor {number}'")
            if number <= 3:
                classes = directory / "build/classes/java/main"
                for entry in (ENTRIES[number - 1], "example/Other.class"):
                    target = classes / entry
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(struct.pack(">IHH", 0xCAFEBABE, 0, 61))
        self.log.write_text("\n".join(self.workers))

    def invoke(self, feature="21"):
        details = f"    java.specification.version = {feature}\n    java.version = {feature}.0.12\n"
        completed = subprocess.CompletedProcess([], 0, "", details)
        with patch.object(runtime_summary, "ROOT", self.root), \
             patch.object(runtime_summary.sys, "argv", [str(SCRIPT), str(self.log),
                                                        str(self.java_home), str(self.output)]), \
             patch.object(runtime_summary.subprocess, "run", return_value=completed), \
             contextlib.redirect_stdout(io.StringIO()):
            runtime_summary.main()

    def rejected(self):
        with self.assertRaises((ValueError, AssertionError, OSError, ET.ParseError)):
            self.invoke()
        self.assertFalse(self.output.exists())
        self.assertFalse((self.output.parent / "java21-runtime-junit").exists())

    def test_accepts_complete_split_corpus_and_minimizes_outputs(self):
        self.invoke()
        summary = json.loads(self.output.read_text())
        self.assertEqual(21, summary["javaFeature"])
        self.assertEqual(5, summary["workerLaunches"])
        self.assertEqual(782, sum(module["tests"] for module in summary["modules"]))
        self.assertEqual(26, sum(module["reportFiles"] for module in summary["modules"]))
        self.assertEqual({item[0] for item in MODULES}, {m["module"] for m in summary["modules"]})
        evidence = list((self.output.parent / "java21-runtime-junit").glob("*.xml"))
        self.assertEqual(5, len(evidence))
        for path in evidence:
            self.assertNotIn("private-fixture-secret", path.read_text())
            self.assertNotIn("private-host", path.read_text())

    def test_rejects_missing_core_results(self):
        for path in self.reports[0]:
            path.unlink()
        self.rejected()

    def test_rejects_missing_552_results(self):
        self.reports[4][0].unlink()
        self.rejected()

    def test_rejects_missing_core_worker_even_with_five_launches(self):
        self.log.write_text("\n".join([self.workers[1], *self.workers[1:]]))
        self.rejected()

    def test_rejects_worker_in_an_unrelated_directory(self):
        self.log.write_text("\n".join(self.workers).replace("Working directory: " + str(self.root / "examples/mysql-5.5.2"),
                                                       "Working directory: " + str(self.root / "other")))
        self.rejected()

    def test_rejects_a_worker_using_java17(self):
        self.workers[2] = self.workers[2].replace(str(self.java), str(self.root / "java17/bin/java"))
        self.log.write_text("\n".join(self.workers))
        self.rejected()

    def test_rejects_java17_even_if_worker_path_matches(self):
        with self.assertRaises((ValueError, AssertionError)):
            self.invoke(feature="17")
        self.assertFalse(self.output.exists())

    def test_rejects_malformed_xml(self):
        self.reports[4][0].write_text("<testsuite")
        self.rejected()

    def test_rejects_failed_and_skipped_tests(self):
        report = self.reports[4][0]
        original = report.read_bytes()
        for status, attribute in (("failure", "failures"), ("skipped", "skipped"), ("error", "errors")):
            with self.subTest(status=status):
                suite = ET.fromstring(original)
                suite.set(attribute, "1")
                ET.SubElement(suite.find("testcase"), status)
                ET.ElementTree(suite).write(report)
                self.rejected()

    def test_rejects_incomplete_testcase_inventory(self):
        report = self.reports[0][0]
        suite = ET.parse(report).getroot()
        suite.remove(suite.find("testcase"))
        ET.ElementTree(suite).write(report)
        self.rejected()

    def test_rejects_missing_adapter_entry_class(self):
        (self.root / MODULES[2][1] / "build/classes/java/main" / ENTRIES[2]).unlink()
        self.rejected()

    def test_rejects_java21_bytecode_outside_entry_class(self):
        target = self.root / MODULES[1][1] / "build/classes/java/main/example/Other.class"
        target.write_bytes(struct.pack(">IHH", 0xCAFEBABE, 0, 65))
        self.rejected()

    def test_rejects_malformed_class_header(self):
        target = self.root / MODULES[2][1] / "build/classes/java/main/example/Other.class"
        target.write_bytes(b"not-a-class")
        self.rejected()


if __name__ == "__main__":
    unittest.main()
