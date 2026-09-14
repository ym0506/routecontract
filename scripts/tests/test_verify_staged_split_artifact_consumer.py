"""Acceptance tests for evidence integrity in the independent staged consumer harness."""
import importlib.util
from contextlib import redirect_stderr, redirect_stdout
import errno
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import subprocess
import sys
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
        diagnostic = json.loads(log.with_name('gradle-failure.json').read_text())
        self.assertEqual('TIMED_OUT', diagnostic['outcome'])
        self.assertTrue(diagnostic['timedOut'])
        self.assertIsNone(diagnostic['nativeExitCode'])
        self.assertEqual(['UNKNOWN'], diagnostic['observedSignals'])
        self.assertEqual(hashlib.sha256(log.read_bytes()).hexdigest(), diagnostic['logSha256'])
        self.assertEqual(len(log.read_bytes()), diagnostic['logByteCount'])

    def test_failed_child_retains_only_allowed_diagnostic_fields(self):
        log = self.root / 'gradle.log'
        private_values = "SELECT 'private-test-value'; jdbc:mysql://private-host/db?password=private-password"
        child = "import sys; print(sys.argv[1]); print('java.net.SocketTimeoutException: private-timeout-message'); sys.exit(7)"
        public_output = io.StringIO()
        with redirect_stdout(public_output), self.assertRaises(MODULE.VerificationError):
            MODULE.run([sys.executable, '-c', child, private_values], self.root, {}, log)
        diagnostic_text = log.with_name('gradle-failure.json').read_text()
        diagnostic = json.loads(diagnostic_text)
        self.assertEqual({
            'formatVersion': 1,
            'outcome': 'FAILED',
            'nativeExitCode': 7,
            'timedOut': False,
            'logByteCount': len(log.read_bytes()),
            'logSha256': hashlib.sha256(log.read_bytes()).hexdigest(),
            'observedSignals': ['SOCKET_TIMEOUT'],
        }, diagnostic)
        for forbidden in ('private-test-value', 'private-host', 'private-password',
                          'private-timeout-message', str(self.root), sys.executable):
            self.assertNotIn(forbidden, diagnostic_text + public_output.getvalue())
        self.assertIn(private_values, log.read_text())

    def test_unknown_failure_is_not_classified_from_arbitrary_text(self):
        log = self.root / 'gradle.log'
        with self.assertRaises(MODULE.VerificationError):
            MODULE.run([sys.executable, '-c', "raise SystemExit('arbitrary SQL or URL')"],
                       self.root, {}, log)
        diagnostic = json.loads(log.with_name('gradle-failure.json').read_text())
        self.assertEqual(['UNKNOWN'], diagnostic['observedSignals'])
        self.assertEqual(1, diagnostic['nativeExitCode'])

    def test_success_does_not_create_a_failure_diagnostic(self):
        log = self.root / 'gradle.log'
        self.assertEqual('completed\n', MODULE.run(
            [sys.executable, '-c', "print('completed')"], self.root, {}, log))
        self.assertFalse(log.with_name('gradle-failure.json').exists())

    def test_diagnostic_hashes_binary_output_and_finds_signals_across_chunks(self):
        log = self.root / 'gradle.log'
        content = b'\xff' * (64 * 1024 - 10) + b'java.net.UnknownHostException: private-host\n'
        content += b'Received status code 504 from private-url\norg.gradle.wrapper.Download\n'
        log.write_bytes(content)
        with redirect_stdout(io.StringIO()):
            MODULE.retain_failure_diagnostic(log, 1, timed_out=False)
        diagnostic = json.loads(log.with_name('gradle-failure.json').read_text())
        self.assertEqual(len(content), diagnostic['logByteCount'])
        self.assertEqual(hashlib.sha256(content).hexdigest(), diagnostic['logSha256'])
        self.assertEqual(['GRADLE_WRAPPER_FRAME', 'HTTP_504', 'UNKNOWN_HOST'], diagnostic['observedSignals'])

    def test_disk_full_diagnostic_write_preserves_native_failure_and_timeout(self):
        for timed_out in (False, True):
            with self.subTest(timed_out=timed_out):
                log = self.root / 'gradle.log'
                expired = subprocess.TimeoutExpired(['gradle', 'private-command'], 1)
                def fail(command, **arguments):
                    arguments['stdout'].write('No space left on device: private-path\n')
                    if timed_out:
                        raise expired
                    return subprocess.CompletedProcess(command, 7)
                stdout, stderr = io.StringIO(), io.StringIO()
                expected = subprocess.TimeoutExpired if timed_out else MODULE.VerificationError
                with mock.patch.object(MODULE.subprocess, 'run', side_effect=fail), \
                        mock.patch.object(Path, 'write_text', side_effect=OSError(errno.ENOSPC, 'private-message')), \
                        redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(expected) as raised:
                    MODULE.run(['gradle', 'private-command'], self.root, {}, log)
                if timed_out:
                    self.assertIs(expired, raised.exception)
                else:
                    self.assertIn('exit 7', str(raised.exception))
                diagnostic = json.loads(stdout.getvalue().split('STAGED_SPLIT_CONSUMER_FAILURE_DIAGNOSTIC ', 1)[1])
                self.assertEqual(['DISK_FULL'], diagnostic['observedSignals'])
                self.assertEqual(None if timed_out else 7, diagnostic['nativeExitCode'])
                self.assertEqual('STAGED_SPLIT_CONSUMER_DIAGNOSTIC_UNAVAILABLE\n', stderr.getvalue())
                for forbidden in ('private-path', 'private-command', 'private-message'):
                    self.assertNotIn(forbidden, stdout.getvalue() + stderr.getvalue())

    def test_both_lanes_receive_one_shared_deadline(self):
        repository = self.stage()
        evidence = self.root.parent / f'{self.root.name}-evidence'
        self.addCleanup(lambda: MODULE.shutil.rmtree(evidence, ignore_errors=True))
        with mock.patch.object(MODULE, 'verify_lane', return_value={}) as lane, \
                mock.patch.object(MODULE.time, 'monotonic', return_value=1000), redirect_stdout(io.StringIO()):
            self.assertEqual(0, MODULE.main(['--repository', str(repository), '--evidence-directory', str(evidence)]))
        self.assertEqual(2, lane.call_count)
        self.assertEqual([1000 + MODULE.STAGED_RUN_TIMEOUT_SECONDS] * 2,
                         [call.kwargs['deadline'] for call in lane.call_args_list])

    def test_lane_passes_only_remaining_deadline_to_child(self):
        receipt = MODULE.repository_receipt(self.stage())
        work, evidence = self.root / 'work', self.root / 'evidence'
        work.mkdir()
        evidence.mkdir()
        markers = ' '.join((
            'ROUTECONTRACT_STAGED_GRAPH_VERIFIED version=5.5.2 artifacts=2 ',
            'ROUTECONTRACT_STAGED_NEGATIVES_VERIFIED version=5.5.2 cases=5',
            'ROUTECONTRACT_STAGED_SPLIT_MYSQL_VERIFIED version=5.5.2 baseline=MATCH regression=POLICY_VIOLATION attempts=1-to-2'))
        with mock.patch.object(MODULE, 'copy_consumer', side_effect=lambda root, destination, runtime, receipt: destination.mkdir()), \
                mock.patch.object(MODULE, 'verify_junit', return_value={}), \
                mock.patch.object(MODULE, 'run', return_value=markers) as child, \
                mock.patch.object(MODULE.time, 'monotonic', return_value=910), redirect_stdout(io.StringIO()):
            MODULE.verify_lane(self.root, work, evidence, self.root, '5.5.2', MODULE.MODULES[2], receipt, deadline=1000)
        self.assertEqual(90, child.call_args.kwargs['timeout_seconds'])

    def test_ci_timeout_leaves_two_minutes_after_shared_native_deadline(self):
        workflow = (Path(__file__).parents[2] / '.github/workflows/ci.yml').read_text()
        step = workflow.split('      - name: Verify staged core and adapters with independent MySQL consumers\n', 1)[1]
        step = step.split('      - name:', 1)[0]
        outer_seconds = 60 * int(re.search(r'timeout-minutes: (\d+)', step).group(1))
        self.assertGreaterEqual(outer_seconds - MODULE.STAGED_RUN_TIMEOUT_SECONDS, 120)

    def test_workflow_retains_safe_diagnostic_without_raw_log(self):
        workflow = (Path(__file__).parents[2] / '.github/workflows/ci.yml').read_text()
        upload = workflow.split('      - name: Upload staged split-artifact consumer evidence\n', 1)[1]
        upload = upload.split('\n  maven-java21-pilot:', 1)[0]
        self.assertIn('if: always()', upload)
        paths = upload.split('          path: |\n', 1)[1].split('          if-no-files-found:', 1)[0]
        self.assertEqual({
            '${{ runner.temp }}/routecontract-staged-split-consumers/summary.json',
            '${{ runner.temp }}/routecontract-staged-split-consumers/staged-receipt.json',
            '${{ runner.temp }}/routecontract-staged-split-consumers/5.5.*/gradle-failure.json',
            '${{ runner.temp }}/routecontract-staged-split-consumers/5.5.*/junit/*.xml',
            '${{ runner.temp }}/routecontract-staged-split-consumers/5.5.*/reports/**',
        }, {line.strip() for line in paths.splitlines()})

    def test_junit_requires_all_three_tests_and_no_failures(self):
        xml = self.root / 'TEST.xml'
        xml.write_text('<testsuite tests="3" failures="0" errors="0" skipped="0"><testcase name="a"/><testcase name="b"/><testcase name="c"/></testsuite>')
        self.assertEqual(3, MODULE.verify_junit(xml)['tests'])
        xml.write_text('<testsuite tests="3" failures="1" errors="0" skipped="0"><testcase name="a"><failure/></testcase><testcase name="b"/><testcase name="c"/></testsuite>')
        with self.assertRaises(MODULE.VerificationError):
            MODULE.verify_junit(xml)


if __name__ == '__main__':
    unittest.main()
