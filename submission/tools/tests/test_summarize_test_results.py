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

# Keep the acceptance fixture independent of the summarizer's allowlist so a
# newly added release suite cannot disappear from both the input and expectation.
CURRENT_RELEASE_SUITES = {
    "io.github.ym0506.routecontract.api.CurrentRouteContractTest": 15,
    "io.github.ym0506.routecontract.internal.CurrentRuntimeGuardTest": 9,
    "io.github.ym0506.routecontract.internal.RuntimeAdapterRegistryTest": 7,
    "io.github.ym0506.routecontract.manifest.ManifestReviewReportTest": 13,
    "io.github.ym0506.routecontract.structure.CorePublicationStructureTest": 3,
    "io.github.ym0506.routecontract.CurrentRouteContractCompatibilityTest": 4,
    "io.github.ym0506.routecontract.RouteContractTest": 19,
    "io.github.ym0506.routecontract.ShardingSphereRuntimeIdentityTest": 3,
    "io.github.ym0506.routecontract.manifest.ObservedExecutionManifestTest": 22,
    "io.github.ym0506.routecontract.shardingsphere553.internal.FreshJvmGuardFailureTest": 2,
    "io.github.ym0506.routecontract.shardingsphere553.internal.ShardingSphere553PreflightTest": 8,
    "io.github.ym0506.routecontract.structure.ArtifactIsolationTest": 6,
    "io.github.ym0506.routecontract.shardingsphere552.internal.FreshJvmCompatibilityFailureTest": 3,
    "io.github.ym0506.routecontract.shardingsphere552.internal.FreshJvmGuardFailureTest": 2,
    "io.github.ym0506.routecontract.shardingsphere552.internal.RouteContract552HookContainmentTest": 3,
    "io.github.ym0506.routecontract.shardingsphere552.internal.ShardingSphere552PreflightTest": 8,
    "io.github.ym0506.routecontract.structure.ArtifactIsolation552Test": 8,
    "io.github.ym0506.routecontract.example.DataSourceProxyComparisonMySqlTest": 1,
    "io.github.ym0506.routecontract.example.FailureBoundaryMySqlTest": 1,
    "io.github.ym0506.routecontract.example.ObservedExecutionRegressionCorpusMySqlTest": 7,
    "io.github.ym0506.routecontract.example.OperationCorrelationMySqlTest": 5,
    "io.github.ym0506.routecontract.example552.Exact552OperationContractMySqlTest": 7,
    "io.github.ym0506.routecontract.example552.Exact552ObservedExecutionRegressionCorpusMySqlTest": 7,
}


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
        for suite, tests in CURRENT_RELEASE_SUITES.items():
            destination = mysql if ".example" in suite else core
            self.write_suite(
                destination,
                suite,
                tests,
                captured_output=secret if secret and ".example" in suite else None,
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
            self.assertTrue(first.endswith("\n"))
            self.assertIn("format=routecontract-test-summary-v1\n", first)
            self.assertIn(f"revision={self.revision}\n", first)
            self.assertIn("suite_count=23\n", first)
            self.assertIn("test_count=163\n", first)
            self.assertIn(
                "suite=io.github.ym0506.routecontract.manifest.ManifestReviewReportTest"
                "|tests=13|failures=0|errors=0|skipped=0\n",
                first,
            )
            self.assertIn("failure_count=0\nerror_count=0\nskipped_count=0\n", first)
            self.assertNotIn(secret, first)
            self.assertNotIn("private-hostname", first)
            self.assertNotIn("timestamp", first)
            suite_lines = [line for line in first.splitlines() if line.startswith("suite=")]
            self.assertEqual(sorted(suite_lines), suite_lines)

    def test_keeps_historical_contest_summary_unchanged(self) -> None:
        historical = package_submission.expected_release_test_summary(self.revision)

        self.assertIn("suite_count=7\n", historical)
        self.assertIn("test_count=52\n", historical)
        self.assertNotIn("ManifestReviewReportTest", historical)

    def test_rejects_unexpected_suites_including_standalone_consumer(self) -> None:
        for suite in (
            "io.github.ym0506.routecontract.UnexpectedTest",
            "io.github.ym0506.routecontract.consumer.PublishedArtifactMySqlTest",
        ):
            with self.subTest(suite=suite), tempfile.TemporaryDirectory() as raw:
                directories = self.complete_results(Path(raw))
                self.write_suite(directories[0], suite, 1)

                with self.assertRaisesRegex(
                    summarize_test_results.SummaryError, "unexpected JUnit suite"
                ):
                    summarize_test_results.build_summary(self.revision, directories)

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
