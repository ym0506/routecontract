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
EARLIER = 'routecontract-shardingsphere-5.4.1-5.5.2'
LEGACY = ROOT / 'examples/standalone-consumer'
FIXTURE = ROOT / 'examples/public-gradle-release-consumer'
EARLIER_FIXTURE = FIXTURE / 'runtime-5.5.2'
NAMESPACE = {'v': 'https://schema.gradle.org/dependency-verification'}
TEST_NAMES = ('selectedRuntimeApiOriginsAndAutoDiscoveredHookAreTheExpectedJarBytes',
              'captureAndCaptureResultMatchTheReviewedSchemaOneBaseline',
              'sameBusinessRowWithTwoAttemptsFailsPolicyAndSeparateJvmCli')


def receipt_for(version='0.1.3', artifact=ARTIFACT):
    artifacts = []
    for suffix in ('jar', 'pom', 'module'):
        name = f'{artifact}-{version}.{suffix}'
        artifacts.append({'module': artifact, 'name': name,
                          'relativePath': f'io/github/ym0506/routecontract/{artifact}/{version}/{name}',
                          'sha256': hashlib.sha256(name.encode()).hexdigest()})
    return {'formatVersion': 1, 'routeContractVersion': version, 'artifacts': artifacts}


def passing_junit(suffix='()'):
    suite = ET.Element('testsuite', {'name': MODULE.SUITE, 'tests': '3',
                                   'failures': '0', 'errors': '0', 'skipped': '0'})
    for name in TEST_NAMES:
        ET.SubElement(suite, 'testcase', {'name': name + suffix, 'classname': MODULE.SUITE})
    return suite


def evidence_markers(version='0.1.3', runtime='5.5.3'):
    return (f'ROUTECONTRACT_PUBLIC_RELEASE_GRAPH_VERIFIED version={version} runtime={runtime} payloads=3\n'
            f'ROUTECONTRACT_PUBLIC_SINGLE_MYSQL_VERIFIED version={version} runtime={runtime} '
            'baseline=MATCH regression=POLICY_VIOLATION attempts=1-to-2\n')


def lock_coordinates(text):
    coordinates = set()
    for line in text.splitlines():
        if line and not line.startswith(('#', 'empty=')):
            coordinates.add(tuple(line.split('=', 1)[0].split(':')))
    return coordinates


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



class PublicGradleRuntimeProfileTest(unittest.TestCase):
    """Each receipt selects its artifact's runtime profile; the 5.5 profile stays the original contract."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='public-gradle-release-profile-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write_receipt(self, document, name='receipt.json'):
        path = self.root / name
        path.write_text(json.dumps(document))
        return path

    def test_profiles_cover_exactly_the_published_artifacts_in_order(self):
        self.assertEqual(MODULE.PUBLIC.MODULES, tuple(MODULE.PROFILES))
        self.assertEqual({ARTIFACT: '5.5.3', EARLIER: '5.5.2'},
                         {name: profile.runtime for name, profile in MODULE.PROFILES.items()})
        self.assertIs(MODULE.PROFILES[ARTIFACT], MODULE.DEFAULT_PROFILE)

    def test_default_receipt_keeps_the_original_fixture_lock_and_metadata(self):
        receipt, profile = MODULE.select_profile(receipt_for())
        self.assertEqual(receipt_for(), receipt)
        self.assertEqual(MODULE.DEFAULT_PROFILE, profile)
        self.assertEqual(('examples/public-gradle-release-consumer', 'examples/standalone-consumer'),
                         (profile.build, profile.reviewed))

    def test_earlier_artifact_receipt_selects_the_552_profile_without_an_option(self):
        receipt, profile = MODULE.select_profile(receipt_for('0.1.5', EARLIER))
        self.assertEqual(receipt_for('0.1.5', EARLIER), receipt)
        self.assertEqual((EARLIER, '5.5.2'), (profile.artifact, profile.runtime))
        self.assertEqual((EARLIER_FIXTURE, EARLIER_FIXTURE), (ROOT / profile.build, ROOT / profile.reviewed))
        path = self.write_receipt(receipt_for('0.1.5', EARLIER))
        self.assertEqual((receipt, profile), MODULE.load_receipt(path))
        self.assertEqual((receipt, profile), MODULE.load_receipt(path, EARLIER))

    def test_receipt_for_one_artifact_cannot_use_the_other_artifact_profile(self):
        for named, other in ((ARTIFACT, EARLIER), (EARLIER, ARTIFACT)):
            with self.subTest(named=named, other=other):
                path = self.write_receipt(receipt_for('0.1.5', named), f'{named}.json')
                with self.assertRaisesRegex(MODULE.PUBLIC.ReceiptError, f'not a reviewed receipt for {other}'):
                    MODULE.select_profile(receipt_for('0.1.5', named), other)
                with self.assertRaisesRegex(MODULE.PUBLIC.ReceiptError, f'not a reviewed receipt for {other}'):
                    MODULE.load_receipt(path, other)
                evidence = self.root / f'evidence-{named}'
                with mock.patch.object(MODULE.tempfile, 'TemporaryDirectory') as temporary, \
                        mock.patch.object(MODULE, 'copy_consumer') as prepare, \
                        mock.patch.object(MODULE, 'run') as run:
                    with self.assertRaises(MODULE.PUBLIC.ReceiptError):
                        MODULE.verify(ROOT, path, evidence, other)
                    errors = io.StringIO()
                    with redirect_stderr(errors):
                        self.assertEqual(1, MODULE.main(['--receipt', str(path), '--evidence-directory',
                                                         str(evidence), '--artifact', other]))
                temporary.assert_not_called()
                prepare.assert_not_called()
                run.assert_not_called()
                self.assertFalse(evidence.exists())
                self.assertIn('PUBLIC_GRADLE_RELEASE_CONSUMER_FAILED', errors.getvalue())

    def test_unpublished_artifact_option_and_mixed_receipts_are_rejected(self):
        path = self.write_receipt(receipt_for())
        for name in ('routecontract-shardingsphere-5.5.2', 'routecontract-core', ''):
            with self.subTest(name=name):
                with self.assertRaises(MODULE.PUBLIC.ReceiptError):
                    MODULE.select_profile(receipt_for(), name)
                with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                    MODULE.main(['--receipt', str(path), '--evidence-directory', str(self.root / 'evidence'),
                                 '--artifact', name])
        mixed = receipt_for('0.1.5')
        mixed['artifacts'][2] = receipt_for('0.1.5', EARLIER)['artifacts'][2]
        for artifact in (None, ARTIFACT, EARLIER):
            with self.subTest(artifact=artifact):
                with self.assertRaisesRegex(MODULE.PUBLIC.ReceiptError, 'outside the exact coordinate set'):
                    MODULE.select_profile(mixed, artifact)
                with self.assertRaisesRegex(MODULE.PUBLIC.ReceiptError, 'outside the exact coordinate set'):
                    MODULE.load_receipt(self.write_receipt(mixed, 'mixed.json'), artifact)
        self.assertFalse((self.root / 'evidence').exists())

    def test_receipt_errors_name_each_artifact_when_their_reasons_differ(self):
        uppercase = receipt_for('0.1.5', EARLIER)
        uppercase['artifacts'][0]['sha256'] = uppercase['artifacts'][0]['sha256'].upper()
        with self.assertRaisesRegex(MODULE.PUBLIC.ReceiptError, 'does not match any published artifact') as raised:
            MODULE.select_profile(uppercase)
        self.assertIn(f'{EARLIER}: Consumer receipt requires lowercase SHA-256 digests', str(raised.exception))
        self.assertIn(f'{ARTIFACT}: Consumer receipt payload is outside the exact coordinate set', str(raised.exception))
        self.write_receipt({'formatVersion': 1}, 'header.json')
        with self.assertRaisesRegex(MODULE.PUBLIC.ReceiptError, '^Consumer receipt header does not match format 1$'):
            MODULE.load_receipt(self.root / 'header.json')

    def test_lock_line_names_the_selected_artifact_only(self):
        original = (EARLIER_FIXTURE / 'gradle.lockfile').read_text()
        result = MODULE.versioned_lock(original, '0.1.5', EARLIER)
        self.assertEqual(original + f'{GROUP}:{EARLIER}:0.1.5='
                         'reviewedReleaseMetadata,testCompileClasspath,testRuntimeClasspath\n', result)
        with self.assertRaises(MODULE.PUBLIC.ReceiptError):
            MODULE.versioned_lock(original, '0.1.5', 'routecontract-shardingsphere-5.5.2')

    def test_552_lock_and_metadata_pin_only_the_third_party_552_graph(self):
        lock = (EARLIER_FIXTURE / 'gradle.lockfile').read_text()
        lines = lock.splitlines()
        self.assertTrue(lock.endswith('\n'))
        self.assertEqual(1, sum(line.startswith('empty=') for line in lines))
        self.assertFalse(any(line.startswith(GROUP + ':') or 'routecontract' in line for line in lines))
        coordinates = lock_coordinates(lock)
        sharding = {(name, version) for group, name, version in coordinates if group == 'org.apache.shardingsphere'}
        self.assertIn(('shardingsphere-jdbc', '5.5.2'), sharding)
        self.assertEqual({'5.5.2'}, {version for _, version in sharding})
        for anchor in ('shardingsphere-infra-executor', 'shardingsphere-infra-spi', 'shardingsphere-infra-database-core',
                       'shardingsphere-standalone-mode-repository-jdbc', 'shardingsphere-parser-sql-mysql'):
            self.assertIn((anchor, '5.5.2'), sharding)
        self.assertNotIn('shardingsphere-jdbc-core', {name for name, _ in sharding})
        self.assertIn(('org.apache.calcite', 'calcite-core', '1.38.0'), coordinates)
        self.assertNotIn('org.locationtech.jts.io', {group for group, _, _ in coordinates})
        root = ET.parse(EARLIER_FIXTURE / 'gradle/verification-metadata.xml').getroot()
        self.assertEqual('true', root.findtext('v:configuration/v:verify-metadata', namespaces=NAMESPACE))
        self.assertIsNone(root.find('v:configuration/v:trusted-artifacts', NAMESPACE))
        components = root.findall('v:components/v:component', NAMESPACE)
        verified = {(item.get('group'), item.get('name'), item.get('version')) for item in components}
        self.assertFalse(any(group == GROUP for group, _, _ in verified))
        self.assertTrue(coordinates.issubset(verified), sorted(coordinates - verified))
        for component in components:
            artifacts = component.findall('v:artifact', NAMESPACE)
            self.assertTrue(artifacts)
            for artifact in artifacts:
                hashes = artifact.findall('v:sha256', NAMESPACE)
                self.assertEqual(1, len(hashes), artifact.get('name'))
                self.assertRegex(hashes[0].get('value'), '^[0-9a-f]{64}$')
            if component.get('group') == 'org.apache.shardingsphere':
                self.assertEqual('5.5.2', component.get('version'))

    def test_552_copy_uses_its_build_lock_and_metadata_with_the_shared_test(self):
        consumer = self.root / 'consumer'
        receipt = receipt_for('0.1.5', EARLIER)
        MODULE.copy_consumer(ROOT, consumer, receipt)
        self.assertEqual((EARLIER_FIXTURE / 'build.gradle').read_bytes(), (consumer / 'build.gradle').read_bytes())
        self.assertEqual((FIXTURE / 'settings.gradle').read_bytes(), (consumer / 'settings.gradle').read_bytes())
        sources = sorted(path.relative_to(FIXTURE / 'src') for path in (FIXTURE / 'src').rglob('*') if path.is_file())
        self.assertEqual(sources, sorted(path.relative_to(consumer / 'src')
                                         for path in (consumer / 'src').rglob('*') if path.is_file()))
        for relative in sources:
            self.assertEqual((FIXTURE / 'src' / relative).read_bytes(), (consumer / 'src' / relative).read_bytes())
        self.assertFalse((consumer / 'runtime-5.5.2').exists())
        self.assertEqual(MODULE.versioned_lock((EARLIER_FIXTURE / 'gradle.lockfile').read_text(), '0.1.5', EARLIER),
                         (consumer / 'gradle.lockfile').read_text())
        prepared = ET.parse(consumer / 'gradle/verification-metadata.xml').getroot()
        first_party = [item for item in prepared.findall('v:components/v:component', NAMESPACE)
                       if item.get('group') == GROUP]
        self.assertEqual([{'group': GROUP, 'name': EARLIER, 'version': '0.1.5'}], [item.attrib for item in first_party])
        self.assertEqual({item['name']: item['sha256'] for item in receipt['artifacts']},
                         {artifact.get('name'): artifact.find('v:sha256', NAMESPACE).get('value')
                          for artifact in first_party[0].findall('v:artifact', NAMESPACE)})
        third_party = lambda root: [ET.tostring(item) for item in root.findall('v:components/v:component', NAMESPACE)
                                    if item.get('group') != GROUP]
        self.assertEqual(third_party(ET.parse(EARLIER_FIXTURE / 'gradle/verification-metadata.xml').getroot()),
                         third_party(prepared))
        self.assertEqual(MODULE.gradle_arguments(consumer, receipt_for('0.1.5', ARTIFACT))[:-3],
                         MODULE.gradle_arguments(consumer, receipt)[:-3])

    def test_both_builds_resolve_only_from_anonymous_central_without_local_or_project_inputs(self):
        for build in (FIXTURE / 'build.gradle', EARLIER_FIXTURE / 'build.gradle'):
            with self.subTest(build=build):
                text = build.read_text()
                for forbidden in ('mavenLocal', 'flatDir', 'files(', 'fileTree', 'project(', 'includeBuild',
                                  'credentials', 'file:', 'exclusiveContent', 'gradlePluginPortal', 'google()'):
                    self.assertNotIn(forbidden, text)
                self.assertEqual(["url = uri('https://repo.maven.apache.org/maven2')"],
                                 [line.strip() for line in text.splitlines() if 'url' in line and 'uri(' in line])
                self.assertIn('lockMode = LockMode.STRICT', text)
                self.assertIn("throw new GradleException('Public release consumer rejects supplied repository paths and URLs')",
                              text)
        self.assertNotIn('include', (FIXTURE / 'settings.gradle').read_text())

    def test_552_build_pins_its_artifact_runtime_and_test_properties(self):
        text = (EARLIER_FIXTURE / 'build.gradle').read_text()
        self.assertIn(f"def moduleName = '{EARLIER}'", text)
        self.assertIn("def shardingSphereVersion = '5.5.2'", text)
        self.assertIn("systemProperty 'routecontract.artifact', moduleName", text)
        self.assertIn("systemProperty 'routecontract.expectedRuntime', shardingSphereVersion", text)
        self.assertIn('systemProperty "routecontract.sha256.${moduleName}", expectedHashes.jar', text)
        self.assertIn('runtime=${shardingSphereVersion} payloads=3', text)
        code = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('//'))
        self.assertNotRegex(code, r'shardingsphere[-a-z]*:5[.]5[.]3')
        self.assertNotRegex(code, r"version != '5[.]5[.]3'")
        # Workarounds for 5.5.0 (shardingsphere-test-util) and 5.4.1 (snakeyaml 1.33) do not apply to 5.5.2.
        self.assertNotIn('shardingsphere-test-util', code)
        self.assertNotIn('snakeyaml', code)

    def test_shared_java_test_pairs_each_artifact_with_its_profile_runtime(self):
        java = next((FIXTURE / 'src').rglob('PublicReleaseMySqlTest.java')).read_text()
        self.assertIn(f'DEFAULT_ARTIFACT = "{ARTIFACT}"', java)
        self.assertIn('DEFAULT_ARTIFACT, "5.5.3"', java)
        self.assertIn(f'"{EARLIER}", "5.5.2"', java)
        self.assertIn('System.getProperty("routecontract.artifact", DEFAULT_ARTIFACT)', java)
        self.assertIn('"shardingsphere-jdbc-" + EXPECTED_RUNTIME + ".jar"', java)
        self.assertNotIn('"5.5.3";', java)

    def run_successfully(self, receipt, runtime):
        path = self.write_receipt(receipt)
        evidence = self.root / f'evidence-{runtime}'
        commands = []

        def succeed(command, cwd, environment, log):
            commands.append((command, (cwd / 'build.gradle').read_bytes()))
            junit = cwd / 'build/test-results/test' / MODULE.JUNIT_NAME
            junit.parent.mkdir(parents=True)
            ET.ElementTree(passing_junit()).write(junit, encoding='utf-8')
            output = evidence_markers(receipt['routeContractVersion'], runtime)
            log.write_text(output)
            return output

        output = io.StringIO()
        with mock.patch.object(MODULE, 'run', side_effect=succeed), redirect_stdout(output):
            summary = MODULE.verify(ROOT, path, evidence)
        self.assertEqual(1, len(commands))
        self.assertEqual(summary, json.loads((evidence / 'summary.json').read_text()))
        return summary, output.getvalue(), commands[0], evidence

    def test_default_summary_and_console_keep_the_original_shape(self):
        summary, output, (_, build), evidence = self.run_successfully(receipt_for('0.1.5'), '5.5.3')
        self.assertEqual(['formatVersion', 'routeContractVersion', 'normalizedReviewedReceiptSha256', 'buildTool',
                          'runtime', 'junit', 'configuredRepository', 'publicRepositoryConsumptionVerified',
                          'evidenceLabel', 'transportBoundary', 'boundary'], list(summary))
        self.assertEqual('5.5.3', summary['runtime'])
        self.assertEqual((FIXTURE / 'build.gradle').read_bytes(), build)
        self.assertIn('Checking public Gradle release 0.1.5 with a fresh cache...\n', output)
        self.assertTrue(output.endswith('ROUTECONTRACT_PUBLIC_GRADLE_RELEASE_CONSUMER_VERIFIED mysqlTests=3 '
                                        'publicConsumption=true\n'))
        self.assertEqual((FIXTURE / 'build.gradle').read_bytes(), (evidence / 'consumer-build.gradle').read_bytes())

    def test_552_summary_names_the_artifact_and_runtime(self):
        summary, output, (_, build), evidence = self.run_successfully(receipt_for('0.1.5', EARLIER), '5.5.2')
        self.assertEqual(EARLIER, summary['artifact'])
        self.assertEqual('5.5.2', summary['runtime'])
        self.assertEqual((EARLIER_FIXTURE / 'build.gradle').read_bytes(), build)
        self.assertEqual(receipt_for('0.1.5', EARLIER),
                         json.loads((evidence / 'reviewed-receipt.json').read_text()))
        self.assertTrue(output.endswith('ROUTECONTRACT_PUBLIC_GRADLE_RELEASE_CONSUMER_VERIFIED mysqlTests=3 '
                                        f'publicConsumption=true artifact={EARLIER} runtime=5.5.2\n'))

    def test_552_receipt_rejects_the_553_runtime_markers(self):
        receipt = receipt_for('0.1.5', EARLIER)
        path = self.write_receipt(receipt)

        def wrong_runtime(command, cwd, environment, log):
            junit = cwd / 'build/test-results/test' / MODULE.JUNIT_NAME
            junit.parent.mkdir(parents=True)
            ET.ElementTree(passing_junit()).write(junit, encoding='utf-8')
            output = evidence_markers('0.1.5', '5.5.3')
            log.write_text(output)
            return output

        with mock.patch.object(MODULE, 'run', side_effect=wrong_runtime), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(MODULE.PublicConsumerError, 'omitted required'):
                MODULE.verify(ROOT, path, self.root / 'evidence')
        self.assertFalse((self.root / 'evidence/summary.json').exists())

    def test_receipt_replaced_by_the_other_artifact_during_the_run_prevents_success(self):
        path = self.write_receipt(receipt_for('0.1.5', EARLIER))

        def swap(command, cwd, environment, log):
            junit = cwd / 'build/test-results/test' / MODULE.JUNIT_NAME
            junit.parent.mkdir(parents=True)
            ET.ElementTree(passing_junit()).write(junit, encoding='utf-8')
            path.write_text(json.dumps(receipt_for('0.1.5', ARTIFACT)))
            output = evidence_markers('0.1.5', '5.5.2')
            log.write_text(output)
            return output

        with mock.patch.object(MODULE, 'run', side_effect=swap), redirect_stdout(io.StringIO()) as output:
            with self.assertRaises((MODULE.PublicConsumerError, MODULE.PUBLIC.ReceiptError)):
                MODULE.verify(ROOT, path, self.root / 'evidence')
        self.assertFalse((self.root / 'evidence/summary.json').exists())
        self.assertNotIn('ROUTECONTRACT_PUBLIC_GRADLE_RELEASE_CONSUMER_VERIFIED', output.getvalue())


if __name__ == '__main__':
    unittest.main()
