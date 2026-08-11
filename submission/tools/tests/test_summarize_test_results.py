from __future__ import annotations

import importlib.util
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "summarize-test-results.py"
SPEC = importlib.util.spec_from_file_location("summarize_test_results", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
summarize_test_results = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(summarize_test_results)

PACKAGE_SCRIPT = Path(__file__).resolve().parents[1] / "package_submission.py"
PACKAGE_SPEC = importlib.util.spec_from_file_location(
    "package_submission_for_summary_test", PACKAGE_SCRIPT
)
assert PACKAGE_SPEC is not None and PACKAGE_SPEC.loader is not None
package_submission = importlib.util.module_from_spec(PACKAGE_SPEC)
PACKAGE_SPEC.loader.exec_module(package_submission)


class SummarizeTestResultsTest(unittest.TestCase):
    revision = "1" * 40

    def write_suite(
        self,
        directory: Path,
        suite: str,
        tests: int,
        *,
        failures: int = 0,
        errors: int = 0,
        skipped: int = 0,
        captured_output: str | None = None,
    ) -> None:
        root = ET.Element(
            "testsuite",
            {
                "name": suite,
                "tests": str(tests),
                "failures": str(failures),
                "errors": str(errors),
                "skipped": str(skipped),
                "timestamp": "2026-08-11T00:00:00Z",
                "hostname": "private-hostname",
                "time": "999.0",
            },
        )
        for index in range(tests):
            testcase = ET.SubElement(root, "testcase", {"name": f"case-{index}"})
            if index < failures:
                ET.SubElement(testcase, "failure")
            elif index < failures + errors:
                ET.SubElement(testcase, "error")
            elif index < failures + errors + skipped:
                ET.SubElement(testcase, "skipped")
        if captured_output is not None:
            ET.SubElement(root, "system-out").text = captured_output
        ET.ElementTree(root).write(
            directory / f"TEST-{suite}.xml",
            encoding="utf-8",
            xml_declaration=True,
        )

    def complete_results(self, root: Path, *, secret: str | None = None) -> list[Path]:
        core = root / "core"
        mysql = root / "mysql"
        core.mkdir()
        mysql.mkdir()
        for suite, tests in summarize_test_results.EXPECTED_SUITES.items():
            destination = mysql if ".example." in suite else core
            self.write_suite(
                destination,
                suite,
                tests,
                captured_output=secret if secret and ".example." in suite else None,
            )
        return [core, mysql]

    def test_builds_deterministic_privacy_minimized_summary(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            secret = "jdbc:mysql://127.0.0.1:3306/private?password=secret SELECT *"
            directories = self.complete_results(root, secret=secret)

            first = summarize_test_results.build_summary(self.revision, directories)
            second = summarize_test_results.build_summary(
                self.revision, list(reversed(directories))
            )

            self.assertEqual(first, second)
            self.assertEqual(
                package_submission.expected_release_test_summary(self.revision), first
            )
            self.assertTrue(first.endswith("\n"))
            self.assertIn("format=routecontract-test-summary-v1\n", first)
            self.assertIn(f"revision={self.revision}\n", first)
            self.assertIn("suite_count=7\n", first)
            self.assertIn("test_count=50\n", first)
            self.assertIn("failure_count=0\nerror_count=0\nskipped_count=0\n", first)
            self.assertNotIn(secret, first)
            self.assertNotIn("private-hostname", first)
            self.assertNotIn("timestamp", first)
            suite_lines = [line for line in first.splitlines() if line.startswith("suite=")]
            self.assertEqual(sorted(suite_lines), suite_lines)

    def test_writes_summary_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            directories = self.complete_results(root)
            output = root / "evidence" / "test-summary.txt"
            content = summarize_test_results.build_summary(self.revision, directories)

            summarize_test_results.write_summary(output, content)

            self.assertEqual(content, output.read_text(encoding="utf-8"))

    def test_rejects_missing_suite(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            directories = self.complete_results(root)
            missing = next(directories[0].glob("TEST-*.xml"))
            missing.unlink()

            with self.assertRaisesRegex(
                summarize_test_results.SummaryError, "suite set mismatch"
            ):
                summarize_test_results.build_summary(self.revision, directories)

    def test_rejects_changed_test_count(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            directories = self.complete_results(root)
            suite = "io.github.ym0506.routecontract.RouteContractTest"
            self.write_suite(directories[0], suite, 17)

            with self.assertRaisesRegex(
                summarize_test_results.SummaryError, "test count changed"
            ):
                summarize_test_results.build_summary(self.revision, directories)

    def test_rejects_failure_or_skip(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            directories = self.complete_results(root)
            suite = (
                "io.github.ym0506.routecontract.example."
                "DataSourceProxyComparisonMySqlTest"
            )
            self.write_suite(directories[1], suite, 1, failures=1)

            with self.assertRaisesRegex(
                summarize_test_results.SummaryError, "not an all-passing"
            ):
                summarize_test_results.build_summary(self.revision, directories)

    def test_rejects_invalid_revision(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            directories = self.complete_results(root)

            with self.assertRaisesRegex(
                summarize_test_results.SummaryError, "40-character"
            ):
                summarize_test_results.build_summary("main", directories)


if __name__ == "__main__":
    unittest.main()
