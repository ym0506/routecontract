"""Public Maven gate preparation and fail-closed evidence; no live-public success claim."""
import hashlib
import importlib.util
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

SCRIPT = Path(__file__).resolve().parents[1] / 'verify-public-maven-artifact-consumer.py'
SPEC = importlib.util.spec_from_file_location('public_maven_consumer', SCRIPT)
public = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(public)
support = public.maven_support


def receipt(version='0.2.1'):
    artifacts = []
    for module in support.shared.MODULES:
        for extension in ('jar', 'pom', 'module'):
            name = f'{module}-{version}.{extension}'
            artifacts.append({'module': module, 'name': name,
                              'relativePath': f'{support.shared.GROUP_PATH}/{module}/{version}/{name}',
                              'sha256': hashlib.sha256(name.encode()).hexdigest()})
    return {'formatVersion': 1, 'routeContractVersion': version, 'artifacts': artifacts}


def graph(version='0.2.1'):
    return {'children': [
        {'groupId': support.GROUP, 'artifactId': support.LANES['5.5.3'], 'version': version,
         'children': [{'groupId': support.GROUP, 'artifactId': 'routecontract-core', 'version': version}]},
        {'groupId': support.SS_GROUP, 'artifactId': 'shardingsphere-infra-spi', 'version': '5.5.3'}]}


class PublicMavenConsumerTest(unittest.TestCase):
    def arguments(self, temporary):
        source = temporary / 'receipt.json'
        source.write_text(json.dumps(receipt()))
        java = temporary / 'jdk/bin/java'
        java.parent.mkdir(parents=True)
        java.touch()
        return ['--receipt', str(source), '--java-home', str(java.parent.parent),
                '--evidence-directory', str(temporary / 'evidence')]

    def test_public_settings_and_two_lanes_use_only_fixed_central_and_receipt_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arguments = self.arguments(root)
            calls = []
            def lane(*args, **kwargs):
                calls.append((args, kwargs))
                self.assertIsNone(args[3])  # No local staging repository is accepted.
                self.assertEqual('0.2.1', kwargs['version'])
                self.assertEqual(public.MIRROR_ID, kwargs['mirror_id'])
                self.assertEqual(public.TRANSPORT_ARGUMENTS, kwargs['maven_arguments'])
                self.assertFalse(args[1].is_relative_to(SCRIPT.parents[1]))
                return {'runtime': args[7], 'distributionEvidence': 'public-maven-central'}
            with mock.patch.object(public.shutil, 'which', return_value='/mvn'), \
                    mock.patch.object(support, 'run', return_value='Apache Maven 3.9.14 (test)\nJava version: 17.0.15'), \
                    mock.patch.object(support, 'verify_lane', side_effect=lane), \
                    mock.patch.object(support.mirror, 'serve_repository', side_effect=AssertionError('staged mirror forbidden')):
                with redirect_stdout(StringIO()) as output:
                    self.assertEqual(0, public.main(arguments))
                self.assertIn('version=0.2.1', output.getvalue())
            settings = ET.parse(root / 'evidence/central-settings.xml').getroot()
            namespace = '{http://maven.apache.org/SETTINGS/1.2.0}'
            mirrors = settings.findall(namespace + 'mirrors/' + namespace + 'mirror')
            self.assertEqual(1, len(mirrors))
            self.assertEqual('*', mirrors[0].findtext(namespace + 'mirrorOf'))
            self.assertEqual(public.CENTRAL_URL, mirrors[0].findtext(namespace + 'url'))
            self.assertEqual(public.MIRROR_ID, mirrors[0].findtext(namespace + 'id'))
            self.assertIsNone(settings.find(namespace + 'servers'))
            self.assertEqual(['5.5.2', '5.5.3'], [args[7] for args, _ in calls])
            summary = json.loads((root / 'evidence/summary.json').read_text())
            self.assertTrue(summary['complete'])
            self.assertTrue(summary['publicRepositoryConsumptionVerified'])
            self.assertEqual('0.2.1', summary['routeContractVersion'])

    def test_missing_public_version_keeps_receipt_settings_and_incomplete_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arguments = self.arguments(root)
            with mock.patch.object(public.shutil, 'which', return_value='/mvn'), \
                    mock.patch.object(support, 'run', return_value='Apache Maven 3.9.14 (test)\nJava version: 17.0.15'), \
                    mock.patch.object(support, 'verify_lane', side_effect=[{'runtime': '5.5.2'}, support.VerificationError('unpublished')]):
                with self.assertRaisesRegex(support.VerificationError, 'unpublished'):
                    public.main(arguments)
            summary = json.loads((root / 'evidence/summary.json').read_text())
            self.assertFalse(summary['complete'])
            self.assertFalse(summary['publicRepositoryConsumptionVerified'])
            self.assertEqual(1, len(summary['lanes']))
            self.assertEqual(receipt(), json.loads((root / 'evidence/reviewed-receipt.json').read_text()))
            self.assertTrue((root / 'evidence/central-settings.xml').is_file())

    def test_invalid_receipt_fails_before_any_maven_or_evidence_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arguments = self.arguments(root)
            invalid = receipt()
            invalid['artifacts'] = []
            (root / 'receipt.json').write_text(json.dumps(invalid))
            with mock.patch.object(support, 'run', side_effect=AssertionError('Maven must not run')):
                with self.assertRaises(public.public_artifacts.ReceiptError):
                    public.main(arguments)
            self.assertFalse((root / 'evidence').exists())

    def test_version_binding_preserves_legacy_cutoff_and_unchanged_java(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            consumer = root / 'consumer'
            support.copy_consumer(SCRIPT.parents[1], consumer, '0.2.1')
            pom = ET.parse(consumer / 'pom.xml').getroot()
            self.assertEqual('0.2.1', pom.findtext(support.N + 'properties/' + support.N + 'routecontract.version'))
            self.assertEqual(r'0\.2\.1', pom.findtext('.//' + support.N + 'requireProperty/' + support.N + 'regex'))
            self.assertIn('routecontract-shardingsphere-5.5:(,0.2.0)', (consumer / 'pom.xml').read_text())
            source_root = SCRIPT.parents[1] / 'examples/staged-split-artifact-consumer/src'
            for source in source_root.rglob('*'):
                if source.is_file():
                    self.assertEqual(source.read_bytes(), (consumer / 'src' / source.relative_to(source_root)).read_bytes())
            support.verify_tree(graph(), '5.5.3', support.LANES['5.5.3'], '0.2.1')
            mixed = graph()
            mixed['children'][0]['children'][0]['version'] = '0.2.0'
            with self.assertRaises(support.VerificationError):
                support.verify_tree(mixed, '5.5.3', support.LANES['5.5.3'], '0.2.1')
            for case in ('dual-selected-first', 'dual-opposite-first'):
                artifact, version = support.negative_pom(consumer / 'pom.xml', root / f'{case}.xml', case, '5.5.3', '0.2.1')
                self.assertEqual('0.2.1', version)
                both = graph()
                both['children'].append({'groupId': support.GROUP, 'artifactId': artifact, 'version': version})
                support.verify_negative_selection(both, case, '5.5.3', artifact, version, '0.2.1')
                both['children'][0]['version'] = '0.2.0'
                with self.assertRaises(support.VerificationError):
                    support.verify_negative_selection(both, case, '5.5.3', artifact, version, '0.2.1')

    def test_public_command_has_fresh_cache_explicit_settings_and_retains_download_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            evidence = temporary / 'evidence'
            evidence.mkdir()
            settings = evidence / 'central-settings.xml'
            support.write_settings(settings, public.CENTRAL_URL, public.MIRROR_ID)
            def missing(command, cwd, environment, log, expect_failure=False):
                self.assertEqual(str(settings), command[command.index('--settings') + 1])
                self.assertEqual(str(settings), command[command.index('--global-settings') + 1])
                self.assertIn('--strict-checksums', command)
                self.assertIn('-Dmaven.resolver.transport=native', command)
                self.assertIn('-Daether.connector.http.followRedirects=false', command)
                cache = Path(next(c.removeprefix('-Dmaven.repo.local=') for c in command if c.startswith('-Dmaven.repo.local=')))
                self.assertFalse(cache.exists())
                self.assertFalse(cache.is_relative_to(SCRIPT.parents[1]))
                self.assertEqual(str(cwd / 'pom.xml'), command[command.index('--file') + 1])
                self.assertEqual(['clean', 'verify'], command[-2:])
                self.assertTrue(any(c.startswith('-Droutecontract.coreSha256=') for c in command))
                log.write_text('Could not find unpublished adapter in routecontract-public-central')
                raise support.VerificationError('missing public artifact')
            with mock.patch.object(support, 'run', side_effect=missing), \
                    mock.patch.object(support.shared, 'verify_receipt', side_effect=AssertionError('local staging forbidden')):
                with self.assertRaisesRegex(support.VerificationError, 'missing public artifact'):
                    support.verify_lane(SCRIPT.parents[1], temporary, evidence, None, settings, '/mvn', {},
                                        '5.5.3', support.LANES['5.5.3'], receipt(), version='0.2.1', mirror_id=public.MIRROR_ID,
                                        maven_arguments=public.TRANSPORT_ARGUMENTS)
            self.assertTrue((evidence / '5.5.3/consumer-pom.xml').is_file())
            self.assertIn('unpublished', (evidence / '5.5.3/maven.log').read_text())

    def test_central_origins_require_exact_entries_and_matching_jar_and_pom_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            expected = receipt()
            for item in expected['artifacts']:
                path = cache / item['relativePath']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(item['name'].encode())
                with (path.parent / '_remote.repositories').open('a') as marker:
                    marker.write(f'{path.name}>{public.MIRROR_ID}=\n')
            support.verify_origins(cache, support.LANES['5.5.3'], expected, public.MIRROR_ID)
            payload = next(i for i in expected['artifacts'] if i['module'] == 'routecontract-core' and i['name'].endswith('.pom'))
            pom = cache / payload['relativePath']
            marker = pom.parent / '_remote.repositories'
            original = marker.read_text()
            target = f'{pom.name}>{public.MIRROR_ID}='
            for bad in ('#' + target, 'longer-' + target, f'{pom.name}>routecontract-controlled=',
                        target + f'\n{pom.name}>another-repository='):
                marker.write_text(original.replace(target, bad))
                with self.subTest(bad=bad), self.assertRaises(support.VerificationError):
                    support.verify_origins(cache, support.LANES['5.5.3'], expected, public.MIRROR_ID)
            marker.write_text(original)
            other = cache / 'origin-marker'
            marker.rename(other)
            marker.symlink_to(other)
            with self.assertRaises(support.VerificationError):
                support.verify_origins(cache, support.LANES['5.5.3'], expected, public.MIRROR_ID)
            marker.unlink()
            other.rename(marker)
            pom.write_text('wrong public bytes')
            with self.assertRaises(support.VerificationError):
                support.verify_origins(cache, support.LANES['5.5.3'], expected, public.MIRROR_ID)

    def test_launcher_debug_injection_is_removed_and_base_directory_is_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.dict(support.os.environ, {'MAVEN_DEBUG_OPTS': '-javaagent:unexpected -Dinjected=true',
                                                      'MAVEN_BASEDIR': '/uncontrolled'}):
                cleaned = support.clean_environment(root)
            self.assertNotIn('MAVEN_DEBUG_OPTS', cleaned)
            self.assertNotIn('MAVEN_BASEDIR', cleaned)
            with mock.patch.object(support.subprocess, 'run', return_value=subprocess.CompletedProcess(['mvn'], 0)) as run:
                support.run(['mvn', '--version'], root, {**cleaned, 'MAVEN_BASEDIR': '/wrong'}, root / 'toolchain.log')
            self.assertEqual(str(root), run.call_args.kwargs['env']['MAVEN_BASEDIR'])


if __name__ == '__main__':
    unittest.main()
