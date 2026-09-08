"""Offline preparation and failure boundaries for the public 0.1 Gradle consumer.

These tests prove wrapper behavior only, not public artifact availability or MySQL results.
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
from unittest import mock
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'public_gradle_release_consumer_test', ROOT / 'scripts/verify-public-gradle-release-consumer.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
GROUP = 'io.github.ym0506.routecontract'
ARTIFACT = 'routecontract-shardingsphere-5.5'
LEGACY = ROOT / 'examples/standalone-consumer'
FIXTURE = ROOT / 'examples/public-gradle-release-consumer'
NAMESPACE = {'v': 'https://schema.gradle.org/dependency-verification'}
TEST_NAMES = ('selectedRuntimeApiOriginsAndAutoDiscoveredHookAreTheExpectedJarBytes',
              'captureAndCaptureResultMatchTheReviewedSchemaOneBaseline',
              'sameBusinessRowWithTwoAttemptsFailsPolicyAndSeparateJvmCli')


def receipt_for(version='0.1.3'):
    artifacts = []
    for suffix in ('jar', 'pom', 'module'):
        name = f'{ARTIFACT}-{version}.{suffix}'
        artifacts.append({'module': ARTIFACT, 'name': name,
                          'relativePath': f'io/github/ym0506/routecontract/{ARTIFACT}/{version}/{name}',
                          'sha256': hashlib.sha256(name.encode()).hexdigest()})
    return {'formatVersion': 1, 'routeContractVersion': version, 'artifacts': artifacts}


def passing_junit(suffix='()'):
    suite = ET.Element('testsuite', {'name': MODULE.SUITE, 'tests': '3',
                                   'failures': '0', 'errors': '0', 'skipped': '0'})
    for name in TEST_NAMES:
        ET.SubElement(suite, 'testcase', {'name': name + suffix, 'classname': MODULE.SUITE})
    return suite


def evidence_markers(version='0.1.3'):
    return (f'ROUTECONTRACT_PUBLIC_RELEASE_GRAPH_VERIFIED version={version} runtime=5.5.3 payloads=3\n'
            f'ROUTECONTRACT_PUBLIC_SINGLE_MYSQL_VERIFIED version={version} runtime=5.5.3 '
            'baseline=MATCH regression=POLICY_VIOLATION attempts=1-to-2\n')


class PublicGradleReleasePreparationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='public-gradle-release-prep-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_public_lock_adds_only_exact_release_and_retains_all_reviewed_lines(self):
        original = (LEGACY / 'gradle.lockfile').read_text()
        for version in ('0.1.3', '0.1.13'):
            with self.subTest(version=version):
                result = MODULE.versioned_lock(original, version).splitlines(keepends=True)
                first_party = [line for line in result if line.startswith(GROUP + ':')]
                self.assertEqual([f'{GROUP}:{ARTIFACT}:{version}='
                                  'reviewedReleaseMetadata,testCompileClasspath,testRuntimeClasspath\n'],
                                 first_party)
                self.assertEqual(original.splitlines(keepends=True),
                                 [line for line in result if not line.startswith(GROUP + ':')])

    def test_lock_preparation_rejects_unsupported_line_prerelease_or_earlier_patch(self):
        original = (LEGACY / 'gradle.lockfile').read_text()
        for version in ('0.1.2', '0.2.3', '0.1.3-rc1', '0.1.03'):
            with self.subTest(version=version), self.assertRaises(
                    (MODULE.PublicConsumerError, MODULE.PUBLIC.ReceiptError)):
                MODULE.versioned_lock(original, version)

    def test_preexisting_first_party_lock_entry_cannot_be_silently_rewritten(self):
        original = (LEGACY / 'gradle.lockfile').read_text()
        for name, version in ((ARTIFACT, '0.1.3'), (ARTIFACT, '0.1.2'), ('unreviewed-module', '0.1.3')):
            with self.subTest(name=name, version=version), self.assertRaises(MODULE.PublicConsumerError):
                MODULE.versioned_lock(original + f'{GROUP}:{name}:{version}=testRuntimeClasspath\n', '0.1.3')

    def test_metadata_removes_legacy_trust_exemptions_and_pins_only_three_reviewed_payloads(self):
        source = self.root / 'original.xml'
        original = ET.parse(LEGACY / 'gradle/verification-metadata.xml')
        namespace = '{' + NAMESPACE['v'] + '}'
        component = ET.SubElement(original.getroot().find('v:components', NAMESPACE),
                                  namespace + 'component',
                                  {'group': GROUP, 'name': ARTIFACT, 'version': '0.1.2'})
        ET.SubElement(component, namespace + 'artifact', {'name': f'{ARTIFACT}-0.1.2.jar'})
        original.write(source, encoding='utf-8', xml_declaration=True)
        destination = self.root / 'prepared.xml'
        receipt = receipt_for('0.1.13')
        MODULE.prepare_metadata(source, destination, receipt)
        before, after = ET.parse(source).getroot(), ET.parse(destination).getroot()
        self.assertIsNotNone(before.find('v:configuration/v:trusted-artifacts', NAMESPACE))
        self.assertIsNone(after.find('v:configuration/v:trusted-artifacts', NAMESPACE))
        self.assertEqual('true', after.findtext('v:configuration/v:verify-metadata', namespaces=NAMESPACE))
        before_config = before.find('v:configuration', NAMESPACE)
        before_config.remove(before_config.find('v:trusted-artifacts', NAMESPACE))
        self.assertEqual(ET.tostring(before_config), ET.tostring(after.find('v:configuration', NAMESPACE)))
        third_party = lambda root: [ET.tostring(item)
                                    for item in root.findall('v:components/v:component', NAMESPACE)
                                    if item.get('group') != GROUP]
        self.assertEqual(third_party(before), third_party(after))
        components = [item for item in after.findall('v:components/v:component', NAMESPACE)
                      if item.get('group') == GROUP]
        self.assertEqual(1, len(components))
        self.assertEqual({'group': GROUP, 'name': ARTIFACT, 'version': '0.1.13'}, components[0].attrib)
        artifacts = components[0].findall('v:artifact', NAMESPACE)
        self.assertEqual(3, len(artifacts))
        pinned = {}
        for artifact in artifacts:
            hashes = artifact.findall('v:sha256', NAMESPACE)
            self.assertEqual(1, len(hashes))
            self.assertNotIn(artifact.get('name'), pinned)
            pinned[artifact.get('name')] = hashes[0].get('value')
        self.assertEqual({item['name']: item['sha256'] for item in receipt['artifacts']}, pinned)

    def test_copy_keeps_java_and_baseline_bytes_without_source_substitution(self):
        consumer = self.root / 'consumer'
        sources = [path for path in (FIXTURE / 'src').rglob('*') if path.is_file()]
        self.assertEqual(1, sum(path.suffix == '.java' for path in sources))
        self.assertEqual(1, sum(path.name.endswith('.approved.json') for path in sources))
        MODULE.copy_consumer(ROOT, consumer, receipt_for())
        copied = sorted(path.relative_to(consumer / 'src')
                        for path in (consumer / 'src').rglob('*') if path.is_file())
        self.assertEqual(sorted(path.relative_to(FIXTURE / 'src') for path in sources), copied)
        for source in sources:
            self.assertEqual(source.read_bytes(), (consumer / source.relative_to(FIXTURE)).read_bytes())
        for name in ('build.gradle', 'settings.gradle'):
            self.assertEqual((FIXTURE / name).read_bytes(), (consumer / name).read_bytes())
        self.assertEqual((ROOT / 'gradlew').read_bytes(), (consumer / 'gradlew').read_bytes())

    def test_public_environment_strips_shared_cache_and_java_gradle_injections(self):
        cache = self.root / 'new-home'
        retained = {'PATH': '/fixture/bin', 'JAVA_HOME': '/fixture/jdk17',
                    'LANG': 'en_US.UTF-8', 'DOCKER_HOST': 'unix:///fixture/docker.sock'}
        inherited = dict(retained, GRADLE_USER_HOME='/fixture/warm-home',
                         GRADLE_RO_DEP_CACHE='/fixture/shared-cache',
                         GRADLE_OPTS='-Dfixture.gradle=injected', JAVA_OPTS='-Dfixture.java=injected',
                         JAVA_TOOL_OPTIONS='-Dfixture.java.tool=injected',
                         JDK_JAVA_OPTIONS='-Dfixture.jdk.java=injected', _JAVA_OPTIONS='-Dfixture.old.java=injected',
                         ORG_GRADLE_PROJECT_routecontractRepository='/fixture/local-repository',
                         ORG_GRADLE_PROJECT_routecontractVersion='0.1.2',
                         ROUTECONTRACT_REPOSITORY='/fixture/private-repository')
        with mock.patch.dict(os.environ, inherited, clear=True):
            environment = MODULE.clean_environment(cache)
            self.assertEqual(inherited, dict(os.environ))
        self.assertEqual(dict(retained, GRADLE_USER_HOME=str(cache)), environment)
        self.assertFalse(cache.exists())

    def test_gradle_arguments_pin_version_and_all_three_hashes_without_repository_inputs(self):
        receipt = receipt_for('0.1.13')
        consumer = self.root / 'consumer with spaces'
        args = MODULE.gradle_arguments(consumer, receipt)
        self.assertEqual(str(consumer / 'gradlew'), args[0])
        properties = dict(item[2:].split('=', 1) for item in args if item.startswith('-P'))
        expected = {'routecontractVersion': '0.1.13'}
        expected.update({f'routecontractSha256.{item["name"].rsplit(".", 1)[1]}': item['sha256']
                         for item in receipt['artifacts']})
        self.assertEqual(expected, properties)
        self.assertIn('--dependency-verification=strict', args)
        self.assertIn('--no-build-cache', args)
        self.assertIn('--no-configuration-cache', args)
        self.assertFalse(any('://' in item or str(self.root) in item for item in args[1:]))


class PublicGradleReleaseFailureTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='public-gradle-release-failure-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.receipt = receipt_for()
        self.receipt_path = self.root / 'receipt.json'
        self.receipt_path.write_text(json.dumps(self.receipt))
        self.evidence = self.root / 'evidence'

    def test_malformed_receipt_fails_before_temporary_or_evidence_preparation_and_command(self):
        self.receipt_path.write_text('{invalid JSON')
        with mock.patch.object(MODULE.tempfile, 'TemporaryDirectory') as temporary, \
                mock.patch.object(MODULE, 'copy_consumer') as prepare, \
                mock.patch.object(MODULE, 'run') as run:
            with self.assertRaises(MODULE.PUBLIC.ReceiptError):
                MODULE.verify(ROOT, self.receipt_path, self.evidence)
        temporary.assert_not_called()
        prepare.assert_not_called()
        run.assert_not_called()
        self.assertFalse(self.evidence.exists())

    def test_evidence_under_resolved_checkout_or_symlink_alias_is_rejected(self):
        checkout = self.root / 'checkout'
        checkout.mkdir()
        alias = self.root / 'checkout-alias'
        alias.symlink_to(checkout, target_is_directory=True)
        for evidence in (checkout / 'evidence', alias / 'evidence'):
            with self.subTest(evidence=evidence), \
                    mock.patch.object(MODULE, 'copy_consumer') as prepare, \
                    mock.patch.object(MODULE, 'run') as run:
                with self.assertRaises(MODULE.PublicConsumerError):
                    MODULE.verify(checkout, self.receipt_path, evidence)
                prepare.assert_not_called()
                run.assert_not_called()
                self.assertFalse(evidence.exists())

    def test_temporary_checkout_directory_and_symlink_alias_are_rejected_before_preparation(self):
        checkout = self.root / 'checkout'
        checkout.mkdir()
        temporary = checkout / 'temporary'
        temporary.mkdir()
        alias = self.root / 'temporary-alias'
        alias.symlink_to(temporary, target_is_directory=True)
        for location in (temporary, alias):
            with self.subTest(location=location), \
                    mock.patch.object(MODULE.tempfile, 'TemporaryDirectory') as manager, \
                    mock.patch.object(MODULE, 'copy_consumer') as prepare, \
                    mock.patch.object(MODULE, 'run') as run:
                manager.return_value.__enter__.return_value = str(location)
                with self.assertRaises(MODULE.PublicConsumerError):
                    MODULE.verify(checkout, self.receipt_path, self.evidence)
                prepare.assert_not_called()
                run.assert_not_called()
                self.assertFalse(self.evidence.exists())
        self.assertEqual([], list(temporary.iterdir()))

    def test_existing_and_symlinked_evidence_are_preserved(self):
        self.evidence.mkdir()
        sentinel = self.evidence / 'keep.txt'
        sentinel.write_bytes(b'previous evidence')
        alias = self.root / 'evidence-alias'
        alias.symlink_to(self.evidence, target_is_directory=True)
        dangling = self.root / 'dangling'
        dangling.symlink_to(self.root / 'absent', target_is_directory=True)
        for evidence in (self.evidence, alias, dangling):
            with self.subTest(evidence=evidence), \
                    mock.patch.object(MODULE.tempfile, 'TemporaryDirectory') as temporary, \
                    mock.patch.object(MODULE, 'run') as run:
                with self.assertRaises(MODULE.PublicConsumerError):
                    MODULE.verify(ROOT, self.receipt_path, evidence)
                temporary.assert_not_called()
                run.assert_not_called()
        self.assertEqual(b'previous evidence', sentinel.read_bytes())
        self.assertTrue(dangling.is_symlink())

    def test_failed_command_retains_diagnostics_without_success_summary(self):
        raw_junit = b'<testsuite tests="3" failures="1" errors="0" skipped="0"/>'
        review = b'{"status":"POLICY_VIOLATION"}\n'

        def fail(command, cwd, environment, log):
            self.assertFalse(Path(environment['GRADLE_USER_HOME']).exists())
            junit = cwd / 'build/test-results/test' / MODULE.JUNIT_NAME
            junit.parent.mkdir(parents=True)
            junit.write_bytes(raw_junit)
            reports = cwd / 'build/routecontract-consumer-evidence'
            reports.mkdir(parents=True)
            (reports / 'review.json').write_bytes(review)
            log.write_text('diagnostic: unavailable public artifact\n')
            raise MODULE.PublicConsumerError('consumer exited 1')

        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(MODULE, 'run', side_effect=fail) as run, \
                redirect_stdout(output), redirect_stderr(errors):
            result = MODULE.main(['--receipt', str(self.receipt_path),
                                  '--evidence-directory', str(self.evidence)])
        self.assertEqual(1, result)
        self.assertEqual(1, run.call_count)
        self.assertEqual(raw_junit, (self.evidence / 'junit' / MODULE.JUNIT_NAME).read_bytes())
        self.assertEqual(review, (self.evidence / 'reports/review.json').read_bytes())
        self.assertIn('unavailable public artifact', (self.evidence / 'gradle.log').read_text())
        self.assertTrue((self.evidence / 'gradle.lockfile').is_file())
        self.assertTrue((self.evidence / 'verification-metadata.xml').is_file())
        self.assertFalse((self.evidence / 'summary.json').exists())
        self.assertNotIn('ROUTECONTRACT_PUBLIC_GRADLE_RELEASE_CONSUMER_VERIFIED', output.getvalue())
        self.assertIn('PUBLIC_GRADLE_RELEASE_CONSUMER_FAILED', errors.getvalue())

    def test_changed_expected_hash_after_successful_command_prevents_success_summary(self):
        def change_receipt(command, cwd, environment, log):
            junit = cwd / 'build/test-results/test' / MODULE.JUNIT_NAME
            junit.parent.mkdir(parents=True)
            ET.ElementTree(passing_junit()).write(junit, encoding='utf-8')
            changed = copy.deepcopy(self.receipt)
            changed['artifacts'][0]['sha256'] = '0' * 64
            self.receipt_path.write_text(json.dumps(changed))
            output = evidence_markers()
            log.write_text(output)
            return output

        output = io.StringIO()
        with mock.patch.object(MODULE, 'run', side_effect=change_receipt) as run, redirect_stdout(output):
            with self.assertRaisesRegex(MODULE.PublicConsumerError, 'receipt changed'):
                MODULE.verify(ROOT, self.receipt_path, self.evidence)
        self.assertEqual(1, run.call_count)
        self.assertTrue((self.evidence / 'junit' / MODULE.JUNIT_NAME).is_file())
        self.assertFalse((self.evidence / 'summary.json').exists())
        self.assertNotIn('ROUTECONTRACT_PUBLIC_GRADLE_RELEASE_CONSUMER_VERIFIED', output.getvalue())

    def test_only_exact_three_successful_named_junit_cases_are_accepted(self):
        path = self.root / 'TEST.xml'
        for suffix in ('', '()'):
            with self.subTest(suffix=suffix):
                ET.ElementTree(passing_junit(suffix)).write(path, encoding='utf-8')
                self.assertEqual({'tests': 3, 'failures': 0, 'errors': 0, 'skipped': 0}, MODULE.verify_junit(path))

    def test_junit_rejects_partial_skipped_duplicate_unrelated_or_failed_cases(self):
        path = self.root / 'TEST.xml'
        for mutation in ('wrong suite', 'partial', 'skipped', 'duplicate', 'unrelated', 'failure child'):
            with self.subTest(mutation=mutation):
                suite = passing_junit()
                if mutation == 'wrong suite':
                    suite.set('name', 'unrelated.Suite')
                elif mutation == 'partial':
                    suite.remove(suite[-1])
                elif mutation == 'skipped':
                    suite.set('skipped', '1')
                    ET.SubElement(suite[0], 'skipped')
                elif mutation == 'duplicate':
                    suite[1].set('name', suite[0].get('name'))
                elif mutation == 'unrelated':
                    suite[0].set('name', 'unrelatedPassingTest()')
                else:
                    ET.SubElement(suite[0], 'failure', {'message': 'failed despite optimistic suite counters'})
                ET.ElementTree(suite).write(path, encoding='utf-8')
                with self.assertRaises(MODULE.PublicConsumerError):
                    MODULE.verify_junit(path)

    def test_zero_exit_and_passing_junit_without_mysql_cli_marker_cannot_claim_success(self):
        def omit_mysql_marker(command, cwd, environment, log):
            junit = cwd / 'build/test-results/test' / MODULE.JUNIT_NAME
            junit.parent.mkdir(parents=True)
            ET.ElementTree(passing_junit()).write(junit, encoding='utf-8')
            output = evidence_markers().splitlines()[0] + '\n'
            log.write_text(output)
            return output

        output = io.StringIO()
        with mock.patch.object(MODULE, 'run', side_effect=omit_mysql_marker), redirect_stdout(output):
            with self.assertRaisesRegex(MODULE.PublicConsumerError, 'omitted required'):
                MODULE.verify(ROOT, self.receipt_path, self.evidence)
        self.assertFalse((self.evidence / 'summary.json').exists())
        self.assertTrue((self.evidence / 'junit' / MODULE.JUNIT_NAME).is_file())
        self.assertNotIn('ROUTECONTRACT_PUBLIC_GRADLE_RELEASE_CONSUMER_VERIFIED', output.getvalue())


if __name__ == '__main__':
    unittest.main()
