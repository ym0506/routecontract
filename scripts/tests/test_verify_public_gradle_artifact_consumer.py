"""Preparation and failure boundaries of the anonymous public Gradle consumer.

No build or network runs here. These tests do not establish public availability or MySQL
behavior; the unchanged real consumer fixture and its live evidence checks do that.
"""
from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import mock
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'public_gradle_consumer_test', ROOT / 'scripts/verify-public-gradle-artifact-consumer.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
FIXTURE = ROOT / 'examples/staged-split-artifact-consumer'
GROUP = 'io.github.ym0506.routecontract'
MODULES = ('routecontract-core', 'routecontract-shardingsphere-5.5',
           'routecontract-shardingsphere-5.5.2')
NAMESPACE = {'v': 'https://schema.gradle.org/dependency-verification'}


def receipt_for(version='0.2.1'):
    """Minimal validated-loader output; shared receipt schema tests live elsewhere."""
    return {'routeContractVersion': version, 'artifacts': [
        {'module': module, 'name': f'{module}-{version}.{suffix}',
         'sha256': hashlib.sha256(f'{module}-{version}.{suffix}'.encode()).hexdigest()}
        for module in MODULES for suffix in ('jar', 'pom', 'module')
    ]}


class PublicGradleConsumerPreparationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='public-gradle-wrapper-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_future_version_rewrites_only_first_party_versions_in_both_reviewed_locks(self):
        for runtime, adapter in MODULE.LANES.items():
            with self.subTest(runtime=runtime):
                original = (FIXTURE / 'gradle-locks' / f'{runtime}.lockfile').read_text()
                rewritten = MODULE.versioned_lock(original, '0.2.1', adapter)
                before, after = original.splitlines(keepends=True), rewritten.splitlines(keepends=True)
                self.assertEqual(len(before), len(after))
                changed = []
                for old, new in zip(before, after):
                    if old.startswith(GROUP + ':'):
                        coordinate, configurations = old.split('=', 1)
                        name = coordinate.split(':')[1]
                        self.assertEqual(f'{GROUP}:{name}:0.2.1={configurations}', new)
                        changed.append(name)
                    else:
                        self.assertEqual(old, new)
                self.assertCountEqual(['routecontract-core', adapter], changed)

    def test_unreviewed_first_party_lock_graphs_are_rejected(self):
        adapter = 'routecontract-shardingsphere-5.5'
        core = f'{GROUP}:routecontract-core:0.2.0=testCompileClasspath,testRuntimeClasspath\n'
        selected = f'{GROUP}:{adapter}:0.2.0=testCompileClasspath,testRuntimeClasspath\n'
        invalid = {
            'missing core': selected,
            'missing adapter': core,
            'duplicate core': core + selected + core,
            'duplicate adapter': core + selected + selected,
            'unknown first party': core + selected + f'{GROUP}:unreviewed:0.2.0=testRuntimeClasspath\n',
            'other adapter': core + selected + f'{GROUP}:routecontract-shardingsphere-5.5.2:0.2.0=testRuntimeClasspath\n',
            'unreviewed original version': core.replace(':0.2.0=', ':0.2.1=') + selected,
            'missing configuration separator': core + selected.rstrip().split('=')[0] + '\n',
        }
        for name, original in invalid.items():
            with self.subTest(name=name), self.assertRaises(MODULE.PublicConsumerError):
                MODULE.versioned_lock(original, '0.2.1', adapter)

    def test_public_copy_preserves_java_and_approved_baseline_bytes(self):
        sources = [path for path in (FIXTURE / 'src').rglob('*') if path.is_file()]
        self.assertEqual(1, sum(path.suffix == '.java' for path in sources))
        self.assertEqual(2, sum(path.name.endswith('.approved.json') for path in sources))
        for runtime in ('5.5.2', '5.5.3'):
            with self.subTest(runtime=runtime):
                consumer = self.root / runtime
                MODULE.copy_public_consumer(ROOT, consumer, runtime, receipt_for())
                copied = sorted(path.relative_to(consumer / 'src')
                                for path in (consumer / 'src').rglob('*') if path.is_file())
                self.assertEqual(sorted(path.relative_to(FIXTURE / 'src') for path in sources), copied)
                for source in sources:
                    self.assertEqual(source.read_bytes(), (consumer / source.relative_to(FIXTURE)).read_bytes())
                for filename in ('build.gradle', 'settings.gradle'):
                    self.assertEqual((FIXTURE / filename).read_bytes(), (consumer / filename).read_bytes())

    def test_future_metadata_contains_exact_nine_reviewed_hashes_and_preserves_third_party_trust(self):
        consumer = self.root / 'consumer'
        receipt = receipt_for()
        MODULE.copy_public_consumer(ROOT, consumer, '5.5.3', receipt)
        before = ET.parse(ROOT / 'gradle/verification-metadata.xml').getroot()
        after = ET.parse(consumer / 'gradle/verification-metadata.xml').getroot()
        self.assertEqual(ET.tostring(before.find('v:configuration', NAMESPACE)),
                         ET.tostring(after.find('v:configuration', NAMESPACE)))
        third_party = lambda root: [ET.tostring(component)
                                    for component in root.findall('v:components/v:component', NAMESPACE)
                                    if component.get('group') != GROUP]
        self.assertEqual(third_party(before), third_party(after))
        selected = [component for component in after.findall('v:components/v:component', NAMESPACE)
                    if component.get('group') == GROUP]
        self.assertCountEqual(MODULES, [component.get('name') for component in selected])
        actual = {}
        for component in selected:
            self.assertEqual('0.2.1', component.get('version'))
            for artifact in component.findall('v:artifact', NAMESPACE):
                digests = artifact.findall('v:sha256', NAMESPACE)
                self.assertEqual(1, len(digests))
                key = (component.get('name'), artifact.get('name'))
                self.assertNotIn(key, actual)
                actual[key] = digests[0].get('value')
        self.assertEqual(9, len(actual))
        self.assertEqual({(item['module'], item['name']): item['sha256'] for item in receipt['artifacts']}, actual)

    def test_staged_copy_keeps_its_existing_zero_two_zero_locks_and_metadata(self):
        for runtime in ('5.5.2', '5.5.3'):
            with self.subTest(runtime=runtime):
                consumer = self.root / runtime
                MODULE.STAGED.copy_consumer(ROOT, consumer, runtime, receipt_for('0.2.0'))
                self.assertEqual((FIXTURE / 'gradle-locks' / f'{runtime}.lockfile').read_bytes(),
                                 (consumer / 'gradle.lockfile').read_bytes())
                components = ET.parse(consumer / 'gradle/verification-metadata.xml').findall(
                    'v:components/v:component', NAMESPACE)
                first_party = [item for item in components if item.get('group') == GROUP]
                self.assertEqual(3, len(first_party))
                self.assertEqual({'0.2.0'}, {item.get('version') for item in first_party})

    def test_generated_arguments_select_public_mode_without_repository_credentials_or_direct_core(self):
        receipt = receipt_for()
        consumer = self.root / 'consumer with spaces'
        for runtime, adapter in MODULE.LANES.items():
            with self.subTest(runtime=runtime):
                args = MODULE.gradle_arguments(consumer, runtime, receipt)
                self.assertEqual(str(consumer / 'gradlew'), args[0])
                properties = dict(item[2:].split('=', 1) for item in args if item.startswith('-P'))
                expected = {'routecontractPublicConsumer': 'true', 'routecontractVersion': '0.2.1',
                            'routecontractRuntime': runtime}
                expected.update({f'routecontractSha256.{item["module"]}': item['sha256']
                                 for item in receipt['artifacts']
                                 if item['module'] in ('routecontract-core', adapter)
                                 and item['name'].endswith('.jar')})
                self.assertEqual(expected, properties)
                self.assertIn('--dependency-verification=strict', args)
                self.assertIn('--no-build-cache', args)
                self.assertIn('--no-configuration-cache', args)
                self.assertFalse(any('://' in item for item in args[1:]))
                self.assertFalse(any(str(self.root) in item for item in args[1:]))

    def test_public_environment_removes_shared_cache_and_java_gradle_injections(self):
        cache = self.root / 'fresh-gradle-home'
        retained = {'PATH': '/fixture/bin', 'JAVA_HOME': '/fixture/jdk-17',
                    'LANG': 'en_US.UTF-8', 'DOCKER_HOST': 'unix:///fixture/docker.sock'}
        inherited = dict(retained, GRADLE_USER_HOME='/fixture/warm-gradle-home',
                         GRADLE_RO_DEP_CACHE='/fixture/preloaded-readonly-cache',
                         GRADLE_OPTS='-Dfixture.gradle=injected',
                         JAVA_OPTS='-Dfixture.java=injected',
                         JAVA_TOOL_OPTIONS='-Dfixture.java.tool=injected',
                         JDK_JAVA_OPTIONS='-Dfixture.jdk.java=injected',
                         _JAVA_OPTIONS='-Dfixture.legacy.java=injected',
                         ORG_GRADLE_PROJECT_routecontractRepository='/fixture/local-repository',
                         ORG_GRADLE_PROJECT_routecontractPublicConsumer='false')
        with mock.patch.dict(os.environ, inherited, clear=True):
            environment = MODULE.public_environment(cache)
            self.assertEqual(inherited, dict(os.environ), 'Parent process environment must remain unchanged')
        self.assertEqual(dict(retained, GRADLE_USER_HOME=str(cache)), environment)
        self.assertFalse(cache.exists(), 'Environment preparation must not populate the new cache')

    def test_selected_jar_hash_must_be_unique_exact_name_and_lowercase_sha256(self):
        for mutation in ('missing', 'duplicate', 'wrong filename', 'invalid hash'):
            with self.subTest(mutation=mutation):
                receipt = receipt_for()
                item = next(item for item in receipt['artifacts'] if item['name'] == 'routecontract-core-0.2.1.jar')
                if mutation == 'missing':
                    receipt['artifacts'].remove(item)
                elif mutation == 'duplicate':
                    receipt['artifacts'].append(copy.deepcopy(item))
                elif mutation == 'wrong filename':
                    item['name'] = 'routecontract-core-0.2.0.jar'
                else:
                    item['sha256'] = 'A' * 64
                with self.assertRaises(MODULE.PublicConsumerError):
                    MODULE.gradle_arguments(self.root / 'consumer', '5.5.3', receipt)


class PublicGradleConsumerFailureTest(unittest.TestCase):
    class ReceiptError(ValueError):
        pass

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='public-gradle-failure-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.receipt = receipt_for()
        self.receipt_path = self.root / 'receipt.json'
        self.receipt_path.write_text(json.dumps(self.receipt))
        self.evidence = self.root / 'evidence'
        self.helper = SimpleNamespace(ReceiptError=self.ReceiptError,
                                      load_consumer_receipt=mock.Mock(return_value=self.receipt))

    def test_invalid_receipt_is_rejected_before_temporary_cache_network_or_evidence_creation(self):
        self.helper.load_consumer_receipt.side_effect = self.ReceiptError('receipt rejected')
        with mock.patch.object(MODULE, 'load_tool', return_value=self.helper), \
                mock.patch.object(MODULE.tempfile, 'TemporaryDirectory') as temporary, \
                mock.patch.object(MODULE.STAGED, 'run') as run:
            with self.assertRaisesRegex(self.ReceiptError, 'receipt rejected'):
                MODULE.verify(ROOT, self.receipt_path, self.evidence)
        self.helper.load_consumer_receipt.assert_called_once_with(self.receipt_path)
        temporary.assert_not_called()
        run.assert_not_called()
        self.assertFalse(self.evidence.exists())

    def test_cli_catches_real_shared_receipt_failure_before_any_consumer_preparation(self):
        self.receipt_path.write_text('{malformed JSON')
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(MODULE.tempfile, 'TemporaryDirectory') as temporary, \
                mock.patch.object(MODULE.STAGED, 'run') as run, \
                redirect_stdout(output), redirect_stderr(errors):
            result = MODULE.main(['--receipt', str(self.receipt_path),
                                  '--evidence-directory', str(self.evidence)])
        self.assertEqual(1, result)
        temporary.assert_not_called()
        run.assert_not_called()
        self.assertFalse(self.evidence.exists())
        self.assertIn('PUBLIC_GRADLE_CONSUMER_FAILED', errors.getvalue())
        self.assertNotIn('ROUTECONTRACT_PUBLIC_GRADLE_CONSUMER_VERIFIED', output.getvalue())

    def test_existing_or_symlinked_evidence_is_not_overwritten(self):
        existing = self.root / 'existing'
        existing.mkdir()
        marker = existing / 'keep.txt'
        marker.write_bytes(b'previous evidence')
        linked = self.root / 'linked'
        linked.symlink_to(existing, target_is_directory=True)
        dangling = self.root / 'dangling'
        dangling.symlink_to(self.root / 'absent', target_is_directory=True)
        for evidence in (existing, linked, dangling):
            with self.subTest(evidence=evidence.name), \
                    mock.patch.object(MODULE, 'load_tool', return_value=self.helper), \
                    mock.patch.object(MODULE.tempfile, 'TemporaryDirectory') as temporary:
                with self.assertRaisesRegex(MODULE.PublicConsumerError, 'new public-consumer evidence'):
                    MODULE.verify(ROOT, self.receipt_path, evidence)
                temporary.assert_not_called()
        self.assertEqual(b'previous evidence', marker.read_bytes())
        self.assertTrue(dangling.is_symlink())

    def test_reused_lane_cache_is_rejected_before_preparation_or_command(self):
        temporary = self.root / 'temporary'
        temporary.mkdir()
        (temporary / 'gradle-home-5.5.2').mkdir()
        self.evidence.mkdir()
        with mock.patch.object(MODULE, 'copy_public_consumer') as prepare, \
                mock.patch.object(MODULE.STAGED, 'run') as run:
            with self.assertRaisesRegex(MODULE.PublicConsumerError, 'absent dependency cache'):
                MODULE.verify_lane(ROOT, temporary, self.evidence, '5.5.2', self.receipt)
        prepare.assert_not_called()
        run.assert_not_called()
        self.assertEqual([], list(self.evidence.iterdir()))

    def test_checkout_evidence_including_symlinked_parent_is_rejected_before_preparation(self):
        checkout = self.root / 'checkout'
        checkout.mkdir()
        alias = self.root / 'checkout-alias'
        alias.symlink_to(checkout, target_is_directory=True)
        for evidence in (checkout / 'evidence-direct', alias / 'evidence-linked'):
            with self.subTest(evidence=evidence), \
                    mock.patch.object(MODULE, 'load_tool', return_value=self.helper), \
                    mock.patch.object(MODULE.tempfile, 'TemporaryDirectory') as temporary, \
                    mock.patch.object(MODULE, 'verify_lane', return_value={}) as lane:
                temporary.return_value.__enter__.return_value = str(self.root / 'outside-checkout')
                with self.assertRaisesRegex(MODULE.PublicConsumerError, 'evidence.*outside the checkout'):
                    MODULE.verify(checkout, self.receipt_path, evidence)
                temporary.assert_not_called()
                lane.assert_not_called()
                self.assertFalse(evidence.exists())

    def test_actual_checkout_temporary_directory_is_rejected_before_evidence_or_consumer(self):
        checkout = self.root / 'checkout'
        checkout.mkdir()
        alias = self.root / 'checkout-alias'
        alias.symlink_to(checkout, target_is_directory=True)
        # Model an actual tempfile result after TMPDIR was redirected into the checkout.
        with tempfile.TemporaryDirectory(dir=checkout) as inside:
            for source_root in (checkout, alias):
                evidence = self.root / f'evidence-{source_root.name}'
                with self.subTest(source_root=source_root), \
                        mock.patch.object(MODULE, 'load_tool', return_value=self.helper), \
                        mock.patch.object(MODULE.tempfile, 'TemporaryDirectory') as temporary, \
                        mock.patch.object(MODULE, 'verify_lane', return_value={}) as lane:
                    temporary.return_value.__enter__.return_value = inside
                    with self.assertRaisesRegex(MODULE.PublicConsumerError, 'temporary.*outside the checkout'):
                        MODULE.verify(source_root, self.receipt_path, evidence)
                    temporary.assert_called_once()
                    lane.assert_not_called()
                    self.assertEqual([], list(Path(inside).iterdir()))
                    self.assertFalse(evidence.exists())

    def test_command_failure_retains_diagnostics_and_does_not_write_success_summary(self):
        raw_junit = b'<testsuite tests="3" failures="1" errors="0" skipped="0"/>'
        minimized_report = b'{"status":"POLICY_VIOLATION"}\n'

        def fail(command, cwd, environment, log):
            self.assertFalse(Path(environment['GRADLE_USER_HOME']).exists())
            junit = cwd / 'build/test-results/test' / MODULE.STAGED.JUNIT_NAME
            junit.parent.mkdir(parents=True)
            junit.write_bytes(raw_junit)
            reports = cwd / 'build/routecontract-consumer-evidence'
            reports.mkdir(parents=True)
            (reports / 'review.json').write_bytes(minimized_report)
            log.write_text('diagnostic: public artifact unavailable\n')
            raise MODULE.STAGED.VerificationError('consumer command failed')

        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(MODULE, 'load_tool', return_value=self.helper), \
                mock.patch.object(MODULE.STAGED, 'run', side_effect=fail) as run, \
                redirect_stdout(output), redirect_stderr(errors):
            result = MODULE.main(['--receipt', str(self.receipt_path),
                                  '--evidence-directory', str(self.evidence)])
        self.assertEqual(1, result)
        self.assertEqual(1, run.call_count)
        lane = self.evidence / '5.5.2'
        self.assertEqual(raw_junit, (lane / 'junit' / MODULE.STAGED.JUNIT_NAME).read_bytes())
        self.assertEqual(minimized_report, (lane / 'reports/review.json').read_bytes())
        self.assertIn('public artifact unavailable', (lane / 'gradle.log').read_text())
        self.assertTrue((lane / 'gradle.lockfile').is_file())
        self.assertTrue((lane / 'verification-metadata.xml').is_file())
        self.assertFalse((self.evidence / 'summary.json').exists())
        self.assertFalse((self.evidence / '5.5.3').exists())
        self.assertNotIn('ROUTECONTRACT_PUBLIC_GRADLE_CONSUMER_VERIFIED', output.getvalue())
        self.assertIn('PUBLIC_GRADLE_CONSUMER_FAILED', errors.getvalue())

    def test_receipt_change_between_lanes_stops_consumption_without_success(self):
        def change_receipt(*arguments):
            changed = copy.deepcopy(self.receipt)
            changed['artifacts'][0]['sha256'] = '0' * 64
            self.receipt_path.write_text(json.dumps(changed))
            return {'runtime': '5.5.2'}

        self.helper.load_consumer_receipt.side_effect = lambda path: json.loads(path.read_text())
        with mock.patch.object(MODULE, 'load_tool', return_value=self.helper), \
                mock.patch.object(MODULE, 'verify_lane', side_effect=change_receipt) as lane:
            with self.assertRaisesRegex(MODULE.PublicConsumerError, 'receipt changed'):
                MODULE.verify(ROOT, self.receipt_path, self.evidence)
        self.assertEqual(1, lane.call_count)
        self.assertFalse((self.evidence / 'summary.json').exists())


if __name__ == '__main__':
    unittest.main()
