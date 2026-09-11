"""Preparation and failure boundaries; no claim of public artifact availability."""
import copy
import hashlib
import importlib.util
import json
import os
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


def receipt(version='0.1.3'):
    module = consumer.ARTIFACT
    return {'formatVersion': 1, 'routeContractVersion': version, 'artifacts': [
        {'module': module, 'name': f'{module}-{version}.{extension}',
         'relativePath': f'{consumer.GROUP_PATH}/{module}/{version}/{module}-{version}.{extension}',
         'sha256': hashlib.sha256(extension.encode()).hexdigest()}
        for extension in ('jar', 'pom', 'module')]}


def graph():
    return {'groupId': 'example', 'artifactId': 'consumer', 'version': '1', 'children': [
        {'groupId': consumer.GROUP, 'artifactId': consumer.ARTIFACT, 'version': '0.1.3',
         'type': 'jar', 'scope': 'test'},
        *[{'groupId': consumer.SS_GROUP, 'artifactId': artifact, 'version': '5.5.3', 'type': 'jar'}
          for artifact in sorted(consumer.REQUIRED_SS)]]}


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


if __name__ == '__main__':
    unittest.main()
