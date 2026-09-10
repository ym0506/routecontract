"""Acceptance tests for evidence integrity in the independent staged consumer harness."""
import importlib.util
from pathlib import Path
import tempfile
import subprocess
from unittest import mock
import unittest
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location('staged_consumer', Path(__file__).parents[1] / 'verify-staged-split-artifact-consumer.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StagedConsumerEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def stage(self):
        for module in MODULE.MODULES:
            folder = self.root / MODULE.GROUP_PATH / module / MODULE.VERSION
            folder.mkdir(parents=True)
            for suffix in ('jar', 'pom', 'module'):
                (folder / f'{module}-{MODULE.VERSION}.{suffix}').write_bytes(f'{module}.{suffix}'.encode())
        return self.root

    def test_missing_split_coordinate_is_not_accepted(self):
        self.stage()
        (self.root / MODULE.GROUP_PATH / MODULE.MODULES[-1] / MODULE.VERSION / f'{MODULE.MODULES[-1]}-{MODULE.VERSION}.jar').unlink()
        with self.assertRaises(MODULE.VerificationError):
            MODULE.repository_receipt(self.root)

    def test_symlinked_artifact_is_not_accepted(self):
        self.stage()
        jar = self.root / MODULE.GROUP_PATH / MODULE.MODULES[0] / MODULE.VERSION / f'{MODULE.MODULES[0]}-{MODULE.VERSION}.jar'
        target = self.root / 'outside.jar'
        target.write_bytes(jar.read_bytes())
        jar.unlink()
        jar.symlink_to(target)
        with self.assertRaises(MODULE.VerificationError):
            MODULE.repository_receipt(self.root)

    def test_changed_artifact_is_detected_even_with_same_filename(self):
        self.stage()
        before = MODULE.repository_receipt(self.root)
        jar = self.root / MODULE.GROUP_PATH / MODULE.MODULES[0] / MODULE.VERSION / f'{MODULE.MODULES[0]}-{MODULE.VERSION}.jar'
        jar.write_bytes(b'changed')
        with self.assertRaises(MODULE.VerificationError):
            MODULE.verify_receipt(self.root, before)

    def test_metadata_keeps_third_party_hashes_and_adds_exact_staged_hashes(self):
        self.stage()
        metadata = self.root / 'original.xml'
        metadata.write_text(f'<verification-metadata xmlns="{MODULE.NAMESPACE}"><configuration><verify-metadata>true</verify-metadata><verify-signatures>false</verify-signatures></configuration><components><component group="third.party" name="library" version="1"><artifact name="library-1.jar"><sha256 value="' + 'a'*64 + '"/></artifact></component></components></verification-metadata>')
        destination = self.root / 'copied.xml'
        MODULE.prepare_metadata(metadata, destination, MODULE.repository_receipt(self.root))
        tree = ET.parse(destination)
        components = tree.findall(f'{{{MODULE.NAMESPACE}}}components/{{{MODULE.NAMESPACE}}}component')
        self.assertEqual(4, len(components))
        third_party = next(item for item in components if item.get('group') == 'third.party')
        self.assertEqual('a'*64, next(third_party.iter(f'{{{MODULE.NAMESPACE}}}sha256')).get('value'))
        for component in components:
            if component.get('group') == MODULE.GROUP:
                self.assertEqual(3, len(component))

    def test_skipped_empty_and_partial_junit_cannot_pass(self):
        xml = self.root / 'TEST.xml'
        for attributes in ('tests="3" failures="0" errors="0" skipped="1"', 'tests="0" failures="0" errors="0" skipped="0"', 'tests="2" failures="0" errors="0" skipped="0"'):
            xml.write_text(f'<testsuite {attributes}/>')
            with self.assertRaises(MODULE.VerificationError):
                MODULE.verify_junit(xml)

    def test_failure_artifacts_are_retained_before_validation(self):
        consumer = self.root / 'consumer'
        junit = consumer / 'build/test-results/test/TEST-failed.xml'
        junit.parent.mkdir(parents=True)
        junit.write_text('<testsuite tests="3" failures="1"/>')
        reports = consumer / 'build/routecontract-consumer-evidence'
        reports.mkdir(parents=True)
        (reports / 'review.json').write_text('{"status":"POLICY_VIOLATION"}')
        destination = self.root / 'evidence'
        destination.mkdir()
        MODULE.retain_lane_evidence(consumer, destination)
        self.assertEqual(junit.read_bytes(), (destination / 'junit/TEST-failed.xml').read_bytes())
        self.assertTrue((destination / 'reports/review.json').exists())

    def test_timeout_does_not_discard_output_already_written(self):
        log = self.root / 'gradle.log'
        def timeout(command, **arguments):
            arguments['stdout'].write('diagnostic before timeout\n')
            arguments['stdout'].flush()
            raise subprocess.TimeoutExpired(command, 1)
        with mock.patch.object(MODULE.subprocess, 'run', side_effect=timeout):
            with self.assertRaises(subprocess.TimeoutExpired):
                MODULE.run(['gradle'], self.root, {}, log)
        self.assertEqual('diagnostic before timeout\n', log.read_text())

    def test_junit_requires_all_three_tests_and_no_failures(self):
        xml = self.root / 'TEST.xml'
        xml.write_text('<testsuite tests="3" failures="0" errors="0" skipped="0"><testcase name="a"/><testcase name="b"/><testcase name="c"/></testsuite>')
        self.assertEqual(3, MODULE.verify_junit(xml)['tests'])
        xml.write_text('<testsuite tests="3" failures="1" errors="0" skipped="0"><testcase name="a"><failure/></testcase><testcase name="b"/><testcase name="c"/></testsuite>')
        with self.assertRaises(MODULE.VerificationError):
            MODULE.verify_junit(xml)


if __name__ == '__main__':
    unittest.main()
