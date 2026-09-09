"""The required CI result inventory includes A-22 without accepting incomplete evidence."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
A22 = 'io.github.ym0506.routecontract.manifest.ManifestRuntimeCompatibilityMatrixTest'
REVISION = '1' * 40


def load_summary():
    spec = importlib.util.spec_from_file_location(
        'test_summary_tool', ROOT / 'scripts/summarize-test-results.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestResultSummaryAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.tool = load_summary()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.results = Path(self.directory.name)
        # Supply A-22 even when the registry is stale: this reproduces the actual CI failure.
        inventory = {**self.tool.EXPECTED_SUITES, A22: 606}
        for suite, count in inventory.items():
            self.write_suite(suite, count)

    def write_suite(self, suite, count, failed=False):
        root = ET.Element('testsuite', name=suite, tests=str(count),
                          failures=str(int(failed)), errors='0', skipped='0')
        for index in range(count):
            case = ET.SubElement(root, 'testcase', name=f'case-{index}', classname=suite)
            if failed and index == 0:
                ET.SubElement(case, 'failure')
        ET.ElementTree(root).write(self.path(suite), encoding='utf-8')

    def path(self, suite):
        return self.results / f'TEST-{suite}.xml'

    def summary(self):
        return self.tool.build_summary(REVISION, [self.results])

    def test_current_inventory_includes_the_606_case_matrix(self):
        summary = self.summary()
        self.assertIn('suite_count=25\n', summary)
        self.assertIn('test_count=780\n', summary)
        self.assertIn(f'suite={A22}|tests=606|failures=0|errors=0|skipped=0\n', summary)

    def test_prior_inventory_without_a22_is_no_longer_complete(self):
        self.path(A22).unlink()
        with self.assertRaisesRegex(self.tool.SummaryError, 'suite set mismatch'):
            self.summary()

    def test_dropping_one_matrix_case_cannot_pass_with_consistent_xml_counts(self):
        self.write_suite(A22, 605)
        with self.assertRaisesRegex(self.tool.SummaryError, 'expected 606, found 605'):
            self.summary()

    def test_failed_matrix_case_is_not_accepted_as_complete(self):
        self.write_suite(A22, 606, failed=True)
        with self.assertRaisesRegex(self.tool.SummaryError, 'not an all-passing'):
            self.summary()

    def test_unknown_suite_is_still_rejected(self):
        self.write_suite('unreviewed.UnexpectedTest', 1)
        with self.assertRaisesRegex(self.tool.SummaryError, 'unexpected JUnit suite.*UnexpectedTest'):
            self.summary()

    def test_duplicate_matrix_report_is_still_rejected(self):
        with self.assertRaisesRegex(self.tool.SummaryError, 'duplicate JUnit suite'):
            self.tool.build_summary(REVISION, [self.results, self.results])

    def test_existing_core_and_both_mysql_lanes_remain_required(self):
        for suite in ('io.github.ym0506.routecontract.api.CurrentRouteContractTest',
                      'io.github.ym0506.routecontract.example.OperationCorrelationMySqlTest',
                      'io.github.ym0506.routecontract.example552.Exact552OperationContractMySqlTest'):
            with self.subTest(suite=suite):
                path = self.path(suite)
                original = path.read_bytes()
                path.unlink()
                try:
                    with self.assertRaisesRegex(self.tool.SummaryError, 'suite set mismatch'):
                        self.summary()
                finally:
                    path.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
