"""Preparation and failure boundaries; no claim of public artifact availability."""
import copy
import hashlib
import importlib.util
import json
import os
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('public_maven_release_consumer',
                                            ROOT / 'scripts/verify-public-maven-release-consumer.py')
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)
EARLIER = 'routecontract-shardingsphere-5.4.1-5.5.2'
POM = ROOT / 'examples/public-maven-release-consumer/pom.xml'


def receipt(version='0.1.3', module=consumer.ARTIFACT):
    return {'formatVersion': 1, 'routeContractVersion': version, 'artifacts': [
        {'module': module, 'name': f'{module}-{version}.{extension}',
         'relativePath': f'{consumer.GROUP_PATH}/{module}/{version}/{module}-{version}.{extension}',
         'sha256': hashlib.sha256(extension.encode()).hexdigest()}
        for extension in ('jar', 'pom', 'module')]}


def graph(artifact=consumer.ARTIFACT, version='0.1.3', runtime='5.5.3', anchors=None):
    anchors = consumer.REQUIRED_SS if anchors is None else anchors
    return {'groupId': 'example', 'artifactId': 'consumer', 'version': '1', 'children': [
        {'groupId': consumer.GROUP, 'artifactId': artifact, 'version': version,
         'type': 'jar', 'scope': 'test'},
        *[{'groupId': consumer.SS_GROUP, 'artifactId': anchor, 'version': runtime, 'type': 'jar'}
          for anchor in sorted(anchors)]]}


def earlier_graph(version='0.1.5'):
    return graph(EARLIER, version, '5.5.2', consumer.PROFILES[EARLIER].required_ss)


class PublicMavenReleaseConsumerTest(unittest.TestCase):
    def test_exact_graph_and_receipt_are_accepted(self):
        self.assertEqual(1, consumer.verify_tree(graph(), '0.1.3')['firstPartyArtifacts'])
        self.assertEqual('0.1.3', consumer.public_artifacts().validate_consumer_receipt(receipt())['routeContractVersion'])

    def test_unsupported_versions_and_extra_payloads_are_rejected(self):
        for version in ('0.1.2', '0.1.03', '0.2.0', '0.1.3-SNAPSHOT', 'LATEST'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                consumer.public_artifacts().validate_consumer_receipt(receipt(version))
        bad = receipt()
        bad['artifacts'].append(copy.deepcopy(bad['artifacts'][0]))
        with self.assertRaises(ValueError):
            consumer.public_artifacts().validate_consumer_receipt(bad)

    def test_non_anchor_wrong_version_is_rejected(self):
        bad = graph()
        bad['children'].append({'groupId': consumer.SS_GROUP, 'artifactId': 'shardingsphere-infra-common', 'version': '5.5.2'})
        with self.assertRaises(consumer.VerificationError):
            consumer.verify_tree(bad, '0.1.3')

    def test_missing_anchor_extra_firstparty_and_transitive_only_are_rejected(self):
        candidates = []
        bad = graph()
        bad['children'] = bad['children'][:-1]
        candidates.append(bad)
        bad = graph()
        bad['children'].append({'groupId': consumer.GROUP, 'artifactId': 'routecontract-core', 'version': '0.2.0'})
        candidates.append(bad)
        bad = graph()
        first = bad['children'].pop(0)
        bad['children'][0]['children'] = [first]
        candidates.append(bad)
        for bad in candidates:
            with self.assertRaises(consumer.VerificationError):
                consumer.verify_tree(bad, '0.1.3')

    def make_resolved(self, directory):
        for item in receipt()['artifacts'][:2]:
            path = directory / item['relativePath']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(path.suffix[1:].encode())
        parent = (directory / receipt()['artifacts'][0]['relativePath']).parent
        marker = parent / '_remote.repositories'
        marker.write_text('\n'.join(f'{item["name"]}>{consumer.MIRROR_ID}=' for item in receipt()['artifacts'][:2]))
        return parent, marker

    def test_only_jar_and_pom_consumption_is_verified(self):
        with tempfile.TemporaryDirectory() as name:
            cache = Path(name)
            self.make_resolved(cache)
            self.assertEqual(2, len(consumer.verify_origins(cache, receipt())))

    def test_tampered_bytes_and_wrong_or_ambiguous_origin_are_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            cache = Path(name)
            parent, marker = self.make_resolved(cache)
            original = marker.read_text()
            for invalid in (original.replace(consumer.MIRROR_ID, 'local'),
                            original + '\n' + receipt()['artifacts'][0]['name'] + '>other='):
                marker.write_text(invalid)
                with self.assertRaises(consumer.VerificationError):
                    consumer.verify_origins(cache, receipt())
            marker.write_text(original)
            (parent / receipt()['artifacts'][1]['name']).write_text('changed')
            with self.assertRaises(consumer.VerificationError):
                consumer.verify_origins(cache, receipt())

    def test_symlinked_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            cache = Path(name)
            parent, _ = self.make_resolved(cache)
            path = parent / receipt()['artifacts'][0]['name']
            target = cache / 'alias.jar'
            path.rename(target)
            path.symlink_to(target)
            with self.assertRaises(consumer.VerificationError):
                consumer.verify_origins(cache, receipt())

    def test_environment_and_command_pin_isolation_and_transport(self):
        with patch.dict(os.environ, {name: 'untrusted' for name in consumer.STRIPPED_ENV}):
            environment = consumer.clean_environment(Path('/jdk17'), Path('/isolated-home'))
        for name in consumer.STRIPPED_ENV:
            if name != 'MAVEN_OPTS':
                self.assertNotIn(name, environment)
        self.assertEqual('-Duser.home=../home', environment['MAVEN_OPTS'])
        self.assertEqual('/isolated-home', environment['HOME'])
        self.assertEqual('true', environment['MAVEN_SKIP_RC'])
        args = consumer.maven_arguments('/mvn', Path('/settings'), Path('/cache'), Path('/isolated-home'))
        self.assertIn('-Duser.home=/isolated-home', args)
        self.assertIn('-Dmaven.resolver.transport=native', args)
        self.assertIn('-Daether.connector.http.followRedirects=false', args)
        self.assertIn('--strict-checksums', args)
        self.assertEqual('/settings', args[args.index('--settings') + 1])
        self.assertEqual('/settings', args[args.index('--global-settings') + 1])

    def test_settings_are_anonymous_fixed_all_repository_mirror(self):
        root = ET.parse(ROOT / 'examples/public-maven-release-consumer/settings.xml').getroot()
        namespace = '{http://maven.apache.org/SETTINGS/1.2.0}'
        mirrors = root.findall(namespace + 'mirrors/' + namespace + 'mirror')
        self.assertEqual(1, len(mirrors))
        self.assertEqual('*', mirrors[0].findtext(namespace + 'mirrorOf'))
        self.assertEqual(consumer.CENTRAL_URL, mirrors[0].findtext(namespace + 'url'))
        self.assertEqual([], root.findall(namespace + 'servers'))
        self.assertEqual([], root.findall(namespace + 'proxies'))

    def test_copy_pins_reviewed_version_without_checkout_dependencies(self):
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / 'consumer'
            consumer.copy_consumer(ROOT, destination, '0.1.4')
            pom = ET.parse(destination / 'pom.xml').getroot()
            namespace = consumer.N
            self.assertEqual('0.1.4', pom.findtext(namespace + 'properties/' + namespace + 'routecontract.version'))
            self.assertEqual('0[.]1[.]4', pom.findtext('.//' + namespace + 'requireProperty/' + namespace + 'regex'))
            self.assertFalse((destination / '.mvn').exists())
            self.assertEqual([], pom.findall(namespace + 'repositories'))
            self.assertEqual([], pom.findall(namespace + 'parent'))

    def test_checkout_and_symlink_alias_evidence_are_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            checkout = directory / 'checkout'
            checkout.mkdir()
            alias = directory / 'alias'
            alias.symlink_to(checkout, target_is_directory=True)
            for destination in (checkout / 'evidence', alias / 'evidence'):
                with self.assertRaises(consumer.VerificationError):
                    consumer.validate_evidence_path(checkout, directory / 'receipt.json', destination)

    def test_junit_requires_exact_suite_three_passes_zero_skips(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / consumer.JUNIT_NAME
            cases = ''.join(f'<testcase name="{name}"/>' for name in consumer.TEST_NAMES)
            path.write_text(f'<testsuite name="{consumer.SUITE}" tests="3" failures="0" errors="0" skipped="0">{cases}</testsuite>')
            self.assertEqual(3, consumer.verify_junit(path)['tests'])
            path.write_text(path.read_text().replace('skipped="0"', 'skipped="1"'))
            with self.assertRaises(consumer.VerificationError):
                consumer.verify_junit(path)

    def test_receipt_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'receipt.json'
            path.write_text(json.dumps(receipt()))
            consumer.check_receipt(path, receipt())
            changed = receipt()
            changed['artifacts'][0]['sha256'] = 'a' * 64
            path.write_text(json.dumps(changed))
            with self.assertRaises(consumer.VerificationError):
                consumer.check_receipt(path, receipt())

    def test_hash_failure_prevents_compilation_and_tests(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            temporary, evidence = directory / 'temporary', directory / 'evidence'
            temporary.mkdir()
            evidence.mkdir()
            receipt_path = directory / 'receipt.json'
            receipt_path.write_text(json.dumps(receipt()))
            def fake_run(command, cwd, environment, log):
                if '--version' in command:
                    return 'Apache Maven 3.9.14 (test)\nJava version: 17.0.15'
                self.assertIn(consumer.DEPENDENCY_PLUGIN + ':resolve', command)
                self.assertNotIn('verify', command)
                (evidence / 'resolved-graph.json').write_text(json.dumps(graph()))
                return ''
            with patch.object(consumer, 'run', side_effect=fake_run) as run, \
                    patch.object(consumer, 'verify_origins', side_effect=consumer.VerificationError('hash mismatch')):
                with self.assertRaisesRegex(consumer.VerificationError, 'hash mismatch'):
                    consumer.verify_consumer(ROOT, temporary, evidence, receipt_path, receipt(), '/mvn', Path('/jdk17'))
            self.assertEqual(2, run.call_count)
            self.assertFalse((evidence / 'summary.json').exists())
            self.assertTrue((evidence / 'consumer-pom.xml').is_file())

    def test_failure_never_writes_a_success_summary(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            receipt_path = directory / 'receipt.json'
            receipt_path.write_text(json.dumps(receipt()))
            java_home = directory / 'jdk17'
            (java_home / 'bin').mkdir(parents=True)
            (java_home / 'bin/java').touch()
            evidence = directory / 'evidence'
            with patch.object(consumer.shutil, 'which', return_value='/mvn'), \
                    patch.object(consumer, 'verify_consumer', side_effect=consumer.VerificationError('missing public artifact')):
                with self.assertRaisesRegex(consumer.VerificationError, 'missing public artifact'):
                    consumer.main(['--receipt', str(receipt_path), '--evidence-directory', str(evidence),
                                   '--java-home', str(java_home)])
            self.assertFalse((evidence / 'summary.json').exists())
            self.assertFalse(json.loads((evidence / 'failure.json').read_text())['complete'])



class PublicMavenRuntimeProfileTest(unittest.TestCase):
    """Each receipt selects its artifact's runtime profile; the 5.5 profile stays the original contract."""

    def test_profiles_cover_exactly_the_published_artifacts(self):
        helper = consumer.public_artifacts()
        self.assertEqual(helper.MODULES, tuple(consumer.PROFILES))
        self.assertEqual({consumer.ARTIFACT: ('5.5.3', None), EARLIER: ('5.5.2', 'runtime-5.5.2')},
                         {name: (profile.runtime, profile.maven_profile) for name, profile in consumer.PROFILES.items()})
        self.assertEqual(frozenset(consumer.REQUIRED_SS), consumer.DEFAULT_PROFILE.required_ss)
        self.assertEqual({'shardingsphere-jdbc', 'shardingsphere-infra-executor', 'shardingsphere-infra-spi',
                          'shardingsphere-infra-database-core'}, consumer.PROFILES[EARLIER].required_ss)

    def test_receipt_selects_its_artifact_profile(self):
        self.assertEqual((receipt(), consumer.DEFAULT_PROFILE), consumer.select_profile(receipt()))
        selected, profile = consumer.select_profile(receipt('0.1.5', EARLIER))
        self.assertEqual(receipt('0.1.5', EARLIER), selected)
        self.assertEqual((EARLIER, '5.5.2'), (profile.artifact, profile.runtime))
        self.assertEqual(profile, consumer.select_profile(receipt('0.1.5', EARLIER), EARLIER)[1])

    def test_receipt_for_one_artifact_cannot_use_the_other_profile(self):
        helper = consumer.public_artifacts()
        for named, other in ((consumer.ARTIFACT, EARLIER), (EARLIER, consumer.ARTIFACT)):
            with self.subTest(named=named), tempfile.TemporaryDirectory() as name:
                directory = Path(name)
                path = directory / 'receipt.json'
                path.write_text(json.dumps(receipt('0.1.5', named)))
                with self.assertRaisesRegex(helper.ReceiptError, f'not a reviewed receipt for {other}'):
                    consumer.select_profile(receipt('0.1.5', named), other)
                with self.assertRaisesRegex(helper.ReceiptError, f'not a reviewed receipt for {other}'):
                    consumer.load_receipt(path, other)
                evidence = directory / 'evidence'
                with patch.object(consumer, 'verify_consumer') as verify, \
                        patch.object(consumer.tempfile, 'TemporaryDirectory') as temporary:
                    with self.assertRaises(helper.ReceiptError):
                        consumer.main(['--receipt', str(path), '--evidence-directory', str(evidence),
                                       '--java-home', str(directory), '--artifact', other])
                verify.assert_not_called()
                temporary.assert_not_called()
                self.assertFalse(evidence.exists())

    def test_unpublished_artifact_option_is_rejected_by_the_parser(self):
        with tempfile.TemporaryDirectory() as name:
            for artifact in ('routecontract-shardingsphere-5.5.2', 'routecontract-core'):
                with self.subTest(artifact=artifact), self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                    consumer.main(['--receipt', str(Path(name) / 'receipt.json'), '--evidence-directory',
                                   str(Path(name) / 'evidence'), '--java-home', name, '--artifact', artifact])
            self.assertFalse((Path(name) / 'evidence').exists())

    def test_graph_must_match_the_selected_profile(self):
        profile = consumer.PROFILES[EARLIER]
        verified = consumer.verify_tree(earlier_graph(), '0.1.5', profile)
        self.assertEqual(f'{consumer.GROUP}:{EARLIER}:0.1.5', verified['soleDirectFirstPartyCoordinate'])
        self.assertEqual('5.5.2', verified['shardingSphereVersion'])
        rejected = {
            'earlier graph with default profile': (earlier_graph(), consumer.DEFAULT_PROFILE),
            'default graph with earlier profile': (graph(version='0.1.5'), profile),
            'earlier artifact on 5.5.3': (graph(EARLIER, '0.1.5', '5.5.3', profile.required_ss), profile),
            'default artifact on 5.5.2': (graph(consumer.ARTIFACT, '0.1.5', '5.5.2', profile.required_ss), profile),
            '5.5.3 database anchor': (graph(EARLIER, '0.1.5', '5.5.2', consumer.REQUIRED_SS), profile)}
        mixed = earlier_graph()
        mixed['children'].append({'groupId': consumer.SS_GROUP, 'artifactId': 'shardingsphere-infra-common',
                                  'version': '5.5.3'})
        rejected['one 5.5.3 component'] = (mixed, profile)
        both = earlier_graph()
        both['children'].append({'groupId': consumer.GROUP, 'artifactId': consumer.ARTIFACT, 'version': '0.1.5'})
        rejected['both artifacts'] = (both, profile)
        for label, (tree, selected) in rejected.items():
            with self.subTest(label), self.assertRaises(consumer.VerificationError):
                consumer.verify_tree(tree, '0.1.5', selected)

    def test_only_the_earlier_profile_adds_its_maven_profile_flag(self):
        base = consumer.maven_arguments('/mvn', Path('/settings'), Path('/cache'), Path('/home'))
        self.assertEqual(base, consumer.maven_arguments('/mvn', Path('/settings'), Path('/cache'), Path('/home'),
                                                        consumer.DEFAULT_PROFILE))
        self.assertFalse(any(item.startswith(('-P', '--activate-profiles')) for item in base))
        earlier = consumer.maven_arguments('/mvn', Path('/settings'), Path('/cache'), Path('/home'),
                                           consumer.PROFILES[EARLIER])
        self.assertEqual([*base, '-Pruntime-5.5.2'], earlier)

    def test_pom_profile_switches_only_runtime_inputs_and_adds_no_repository(self):
        namespace = consumer.N
        pom = ET.parse(POM).getroot()
        base = pom.find(namespace + 'properties')
        self.assertEqual(('5.5.3', consumer.ARTIFACT, EARLIER), tuple(base.findtext(namespace + key) for key in (
            'shardingsphere.version', 'routecontract.adapterArtifactId', 'routecontract.otherAdapterArtifactId')))
        profiles = pom.findall(namespace + 'profiles/' + namespace + 'profile')
        self.assertEqual(['runtime-5.5.2'], [item.findtext(namespace + 'id') for item in profiles])
        profile = profiles[0]
        self.assertIsNone(profile.find(namespace + 'activation'))
        for forbidden in ('repositories', 'pluginRepositories', 'distributionManagement', 'modules', 'dependencies'):
            self.assertIsNone(profile.find(namespace + forbidden), forbidden)
        properties = {item.tag[len(namespace):]: item.text or '' for item in profile.find(namespace + 'properties')}
        self.assertEqual({'shardingsphere.version': '5.5.2', 'routecontract.adapterArtifactId': EARLIER,
                          'routecontract.otherAdapterArtifactId': consumer.ARTIFACT,
                          'routecontract.databaseAnchor': 'shardingsphere-infra-database-core',
                          'routecontract.modeRepository': 'jdbc', 'routecontract.parserPrefix': ''}, properties)
        managed = {(item.findtext(namespace + 'groupId'), item.findtext(namespace + 'artifactId'),
                    item.findtext(namespace + 'version')) for item in profile.iter(namespace + 'dependency')}
        self.assertEqual({('org.apache.calcite', 'calcite-core', '1.38.0'),
                          ('org.apache.calcite', 'calcite-linq4j', '1.38.0'),
                          ('net.hydromatic', 'aggdesigner-algorithm', '6.0')}, managed)
        plugins = profile.findall(namespace + 'build/' + namespace + 'plugins/' + namespace + 'plugin')
        self.assertEqual(['maven-surefire-plugin'], [item.findtext(namespace + 'artifactId') for item in plugins])
        variables = plugins[0].find(namespace + 'configuration/' + namespace + 'systemPropertyVariables')
        self.assertEqual([f'routecontract.sha256.{EARLIER}'], [item.tag[len(namespace):] for item in variables])
        surefire = next(item for item in pom.findall(namespace + 'build/' + namespace + 'plugins/' + namespace + 'plugin')
                        if item.findtext(namespace + 'artifactId') == 'maven-surefire-plugin')
        passed = surefire.find(namespace + 'configuration/' + namespace + 'systemPropertyVariables')
        self.assertEqual('${routecontract.adapterArtifactId}', passed.findtext(namespace + 'routecontract.artifact'))
        self.assertEqual('${shardingsphere.version}', passed.findtext(namespace + 'routecontract.expectedRuntime'))
        bans = [item.text for item in pom.iter(namespace + 'exclude')]
        self.assertIn('io.github.ym0506.routecontract:${routecontract.otherAdapterArtifactId}', bans)

    def test_copy_keeps_the_profile_and_pins_only_the_base_version(self):
        with tempfile.TemporaryDirectory() as name:
            destination = Path(name) / 'consumer'
            consumer.copy_consumer(ROOT, destination, '0.1.5')
            namespace = consumer.N
            copied = ET.parse(destination / 'pom.xml').getroot()
            self.assertEqual('0.1.5', copied.findtext(namespace + 'properties/' + namespace + 'routecontract.version'))
            self.assertEqual(['runtime-5.5.2'], [item.findtext(namespace + 'id') for item in
                                                 copied.findall(namespace + 'profiles/' + namespace + 'profile')])
            self.assertEqual([], list(copied.iter(namespace + 'repository')))
            self.assertEqual([], list(copied.iter(namespace + 'pluginRepository')))
            self.assertIsNone(copied.find(namespace + 'profiles/' + namespace + 'profile/' + namespace + 'properties/'
                                          + namespace + 'routecontract.version'))

    @staticmethod
    def fake_consumer_run(selected_receipt, runtime, commands):
        version = selected_receipt['routeContractVersion']
        earlier = selected_receipt['artifacts'][0]['module'] == EARLIER
        tree = earlier_graph(version) if earlier else graph(version=version)

        def fake_run(command, cwd, environment, log):
            commands.append(command)
            if '--version' in command:
                return 'Apache Maven 3.9.14 (test)\nJava version: 17.0.15'
            outputs = [item.split('=', 1)[1] for item in command if item.startswith('-DoutputFile=')]
            if outputs:
                Path(outputs[0]).write_text(json.dumps(tree))
                return ''
            reports = cwd / 'target/surefire-reports'
            reports.mkdir(parents=True)
            cases = ''.join(f'<testcase name="{name}"/>' for name in consumer.TEST_NAMES)
            (reports / consumer.JUNIT_NAME).write_text(
                f'<testsuite name="{consumer.SUITE}" tests="3" failures="0" errors="0" skipped="0">{cases}</testsuite>')
            return (f'ROUTECONTRACT_PUBLIC_SINGLE_MYSQL_VERIFIED version={version} '
                    f'runtime={runtime} baseline=MATCH regression=POLICY_VIOLATION attempts=1-to-2\n')
        return fake_run

    def run_consumer(self, selected_receipt, runtime):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        directory = Path(temporary_directory.name)
        temporary, evidence = directory / 'temporary', directory / 'evidence'
        temporary.mkdir()
        evidence.mkdir()
        receipt_path = directory / 'receipt.json'
        receipt_path.write_text(json.dumps(selected_receipt))
        commands = []
        consumed = [item for item in selected_receipt['artifacts'] if not item['name'].endswith('.module')]
        with patch.object(consumer, 'run', side_effect=self.fake_consumer_run(selected_receipt, runtime, commands)), \
                patch.object(consumer, 'verify_origins', return_value=consumed), \
                redirect_stdout(io.StringIO()):
            result = consumer.verify_consumer(ROOT, temporary, evidence, receipt_path, selected_receipt,
                                              '/mvn', Path('/jdk17'))
        return result, commands

    def test_earlier_receipt_runs_every_maven_command_with_its_profile_and_digest(self):
        selected = receipt('0.1.5', EARLIER)
        result, commands = self.run_consumer(selected, '5.5.2')
        self.assertEqual(4, len(commands))
        self.assertTrue(all(command.count('-Pruntime-5.5.2') == 1 for command in commands))
        verify = next(command for command in commands if 'verify' in command)
        self.assertIn(f'-Droutecontract.sha256.{EARLIER}={selected["artifacts"][0]["sha256"]}', verify)
        self.assertFalse(any(item.startswith(f'-Droutecontract.sha256.{consumer.ARTIFACT}=') for item in verify))
        self.assertEqual(['verified - MySQL', 'verified - ShardingSphere-JDBC 5.5.2'], result['evidenceLabels'])
        self.assertEqual(f'{consumer.GROUP}:{EARLIER}:0.1.5', result['soleDirectFirstPartyCoordinate'])

    def test_default_receipt_runs_maven_without_a_profile_flag(self):
        result, commands = self.run_consumer(receipt('0.1.5'), '5.5.3')
        self.assertFalse(any(item.startswith('-P') for command in commands for item in command))
        verify = next(command for command in commands if 'verify' in command)
        self.assertIn(f'-Droutecontract.sha256.{consumer.ARTIFACT}={receipt()["artifacts"][0]["sha256"]}', verify)
        self.assertEqual(['verified - MySQL', 'verified - ShardingSphere-JDBC 5.5.3'], result['evidenceLabels'])

    def test_earlier_receipt_rejects_the_553_acceptance_marker(self):
        with self.assertRaisesRegex(consumer.VerificationError, 'omitted the real-MySQL acceptance marker'):
            self.run_consumer(receipt('0.1.5', EARLIER), '5.5.3')

    def test_summary_names_only_a_non_default_artifact(self):
        for selected, expected in ((consumer.ARTIFACT, None), (EARLIER, EARLIER)):
            with self.subTest(artifact=selected), tempfile.TemporaryDirectory() as name:
                directory = Path(name)
                path = directory / 'receipt.json'
                path.write_text(json.dumps(receipt('0.1.5', selected)))
                java_home = directory / 'jdk17'
                (java_home / 'bin').mkdir(parents=True)
                (java_home / 'bin/java').touch()
                output = io.StringIO()
                with patch.object(consumer.shutil, 'which', return_value='/mvn'), \
                        patch.object(consumer, 'verify_consumer', return_value={'junit': {}}), redirect_stdout(output):
                    self.assertEqual(0, consumer.main(['--receipt', str(path), '--evidence-directory',
                                                       str(directory / 'evidence'), '--java-home', str(java_home)]))
                summary = json.loads((directory / 'evidence/summary.json').read_text())
                self.assertEqual(expected, summary.get('artifact'))
                suffix = '' if expected is None else f' artifact={EARLIER} runtime=5.5.2'
                self.assertTrue(output.getvalue().endswith(
                    f'version=0.1.5 mysqlTests=3 publicConsumption=true{suffix}\n'))
                with patch.object(consumer.shutil, 'which', return_value='/mvn'), \
                        patch.object(consumer, 'verify_consumer', side_effect=consumer.VerificationError('failed')):
                    with self.assertRaises(consumer.VerificationError):
                        consumer.main(['--receipt', str(path), '--evidence-directory',
                                       str(directory / 'failed'), '--java-home', str(java_home)])
                self.assertEqual(expected, json.loads((directory / 'failed/failure.json').read_text()).get('artifact'))

    def test_receipt_replaced_by_the_other_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'receipt.json'
            path.write_text(json.dumps(receipt('0.1.5', EARLIER)))
            consumer.check_receipt(path, receipt('0.1.5', EARLIER))
            path.write_text(json.dumps(receipt('0.1.5')))
            with self.assertRaises(ValueError):
                consumer.check_receipt(path, receipt('0.1.5', EARLIER))


if __name__ == '__main__':
    unittest.main()
