"""Acceptance regressions for independent Maven staged-byte evidence."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

SCRIPT = Path(__file__).resolve().parents[1] / 'verify-staged-maven-artifact-consumer.py'
SPEC = importlib.util.spec_from_file_location('maven_consumer', SCRIPT)
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


def node(group, artifact, version, children=()):
    return {'groupId': group, 'artifactId': artifact, 'version': version, 'children': list(children)}


def graph(runtime='5.5.3'):
    core = node(consumer.GROUP, 'routecontract-core', '0.2.0')
    adapter = node(consumer.GROUP, consumer.LANES[runtime], '0.2.0', [core])
    runtime_node = node(consumer.SS_GROUP, 'shardingsphere-infra-executor', runtime)
    return node('example', 'consumer', '1', [adapter, runtime_node])


class StagedMavenConsumerTest(unittest.TestCase):
    def test_core_must_be_transitive_and_whole_shardingsphere_group_exact(self):
        self.assertTrue(consumer.verify_tree(graph(), '5.5.3', consumer.LANES['5.5.3'])['coreResolvedTransitively'])
        direct_core = graph()
        direct_core['children'].append(direct_core['children'][0]['children'].pop())
        wrong_non_anchor = graph()
        wrong_non_anchor['children'].append(node(consumer.SS_GROUP, 'shardingsphere-infra-common', '5.5.2'))
        both_adapters = graph()
        both_adapters['children'].append(node(consumer.GROUP, consumer.LANES['5.5.2'], '0.2.0'))
        for invalid in (direct_core, wrong_non_anchor, both_adapters):
            with self.subTest(invalid=invalid), self.assertRaises(consumer.VerificationError):
                consumer.verify_tree(invalid, '5.5.3', consumer.LANES['5.5.3'])

    def test_wrong_non_anchor_must_leave_all_three_anchors_correct(self):
        runtime = '5.5.3'
        tree = graph(runtime)
        tree['children'].extend(node(consumer.SS_GROUP, artifact, runtime) for artifact in
                                ('shardingsphere-infra-spi', 'shardingsphere-database-connector-core'))
        tree['children'].append(node(consumer.SS_GROUP, 'shardingsphere-infra-common', '5.5.2'))
        consumer.verify_negative_selection(tree, 'wrong-non-anchor', runtime, 'shardingsphere-infra-common', '5.5.2')
        tree['children'][2]['version'] = '5.5.2'
        with self.assertRaises(consumer.VerificationError):
            consumer.verify_negative_selection(tree, 'wrong-non-anchor', runtime, 'shardingsphere-infra-common', '5.5.2')

    def test_dual_order_cases_use_ordinary_dependencies(self):
        fixture = SCRIPT.parents[1] / 'examples/staged-maven-artifact-consumer/pom.xml'
        with tempfile.TemporaryDirectory() as directory:
            for case, expected_index in (('dual-opposite-first', 0), ('dual-selected-first', 1)):
                output = Path(directory) / f'{case}.xml'
                artifact, version = consumer.negative_pom(fixture, output, case, '5.5.3')
                dependencies = ET.parse(output).getroot().find(consumer.N + 'dependencies')
                first_party = [d for d in dependencies if d.findtext(consumer.N + 'groupId') == consumer.GROUP]
                self.assertEqual(2, len(first_party))
                self.assertEqual(artifact, first_party[expected_index].findtext(consumer.N + 'artifactId'))
                self.assertEqual('0.2.0', version)
                self.assertNotIn('capabilit', output.read_text().lower())

    def test_missing_download_does_not_count_as_policy_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def failed_run(command, **kwargs):
                kwargs['stdout'].write('Could not resolve artifact: network failed\n')
                return subprocess.CompletedProcess(command, 1)
            with mock.patch.object(consumer.subprocess, 'run', side_effect=failed_run):
                with self.assertRaisesRegex(consumer.VerificationError, 'BannedDependencies'):
                    consumer.run(['mvn'], root, {}, root / 'rejection.log', expect_failure=True)
            self.assertIn('network failed', (root / 'rejection.log').read_text())

    def test_timeout_retains_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def timed_out(command, **kwargs):
                kwargs['stdout'].write('retained before timeout\n')
                raise subprocess.TimeoutExpired(command, 1)
            with mock.patch.object(consumer.subprocess, 'run', side_effect=timed_out):
                with self.assertRaises(subprocess.TimeoutExpired):
                    consumer.run(['mvn'], root, {}, root / 'maven.log')
            self.assertEqual('retained before timeout\n', (root / 'maven.log').read_text())

    def test_failed_lane_keeps_junit_reports_inputs_and_download_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, cache, destination = root / 'consumer', root / 'm2', root / 'evidence'
            destination.mkdir()
            expected = {
                source / 'target/surefire-reports/TEST-case.xml': destination / 'junit/TEST-case.xml',
                source / 'build/routecontract-consumer-evidence/5.5.3/candidate.json': destination / 'reports/5.5.3/candidate.json',
                source / 'src/test/java/Fixture.java': destination / 'inputs/src/test/java/Fixture.java',
                source / 'pom.xml': destination / 'consumer-pom.xml',
                cache / consumer.shared.GROUP_PATH / '_remote.repositories': destination / 'resolved-first-party/_remote.repositories',
            }
            for path in expected:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(path.name)
            consumer.retain_lane_evidence(source, cache, destination)
            for source_path, preserved in expected.items():
                self.assertEqual(source_path.read_bytes(), preserved.read_bytes())

    def test_lane_timeout_reaches_failure_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            evidence = temporary / 'evidence'
            evidence.mkdir()
            fixture_root = SCRIPT.parents[1]
            receipt = {'artifacts': [{'module': name, 'name': name + '.jar', 'sha256': 'a' * 64}
                                     for name in ('routecontract-core', consumer.LANES['5.5.3'])]}
            def timed_out(command, cwd, environment, log, expect_failure=False):
                junit = cwd / 'target/surefire-reports/partial.xml'
                junit.parent.mkdir(parents=True)
                junit.write_text('<testsuite tests="1" errors="1"/>')
                report = cwd / 'build/routecontract-consumer-evidence/5.5.3/candidate.json'
                report.parent.mkdir(parents=True)
                report.write_text('{"partial":true}')
                log.write_text('partial real command output')
                raise subprocess.TimeoutExpired(command, 1)
            with mock.patch.object(consumer.shared, 'verify_receipt'), mock.patch.object(consumer, 'run', side_effect=timed_out):
                with self.assertRaises(subprocess.TimeoutExpired):
                    consumer.verify_lane(fixture_root, temporary, evidence, temporary / 'repository',
                                         temporary / 'settings.xml', 'mvn', {}, '5.5.3', consumer.LANES['5.5.3'], receipt)
            self.assertTrue((evidence / '5.5.3/junit/partial.xml').is_file())
            self.assertTrue((evidence / '5.5.3/reports/5.5.3/candidate.json').is_file())
            self.assertTrue((evidence / '5.5.3/consumer-pom.xml').is_file())
            self.assertEqual('partial real command output', (evidence / '5.5.3/maven.log').read_text())

    def test_matching_hashes_without_controlled_origin_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            file = cache / consumer.shared.GROUP_PATH / 'routecontract-core/0.2.0/routecontract-core-0.2.0.jar'
            file.parent.mkdir(parents=True)
            file.write_bytes(b'supplied staged bytes')
            receipt = {'artifacts': [{'module': 'routecontract-core', 'name': file.name,
                                     'relativePath': str(file.relative_to(cache)), 'sha256': consumer.shared.sha256(file)}]}
            marker = file.parent / '_remote.repositories'
            marker.write_text(f'{file.name}>central=\n')
            with self.assertRaisesRegex(consumer.VerificationError, 'controlled mirror'):
                consumer.verify_origins(cache, consumer.LANES['5.5.3'], receipt)
            marker.write_text(f'{file.name}>{consumer.MIRROR_ID}=\n')
            consumer.verify_origins(cache, consumer.LANES['5.5.3'], receipt)
            file.write_bytes(b'changed staged bytes')
            with self.assertRaisesRegex(consumer.VerificationError, 'receipt'):
                consumer.verify_origins(cache, consumer.LANES['5.5.3'], receipt)

    def test_settings_mirror_every_repository_and_environment_removes_build_injection(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / 'settings.xml'
            consumer.write_settings(settings, 'http://127.0.0.1:12345/')
            namespace = '{http://maven.apache.org/SETTINGS/1.2.0}'
            mirror = ET.parse(settings).getroot().find(namespace + 'mirrors/' + namespace + 'mirror')
            self.assertEqual('*', mirror.findtext(namespace + 'mirrorOf'))
            self.assertEqual('http://127.0.0.1:12345/', mirror.findtext(namespace + 'url'))
        with mock.patch.dict(consumer.os.environ, {'MAVEN_ARGS': '-Denforcer.skip', 'MAVEN_OPTS': '-javaagent:unwanted',
                                                  'JAVA_TOOL_OPTIONS': '-Dtest=other'}):
            cleaned = consumer.clean_environment(Path('/jdk17'))
        self.assertEqual('/jdk17', cleaned['JAVA_HOME'])
        self.assertEqual('true', cleaned['MAVEN_SKIP_RC'])
        self.assertFalse({'MAVEN_ARGS', 'MAVEN_OPTS', 'JAVA_TOOL_OPTIONS'} & cleaned.keys())

    def test_negative_consumer_poms_cannot_be_created_in_source_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'bin').mkdir()
            (root / 'bin/java').touch()
            evidence = SCRIPT.parents[1] / 'build/staged-maven-test-evidence-must-not-exist'
            self.assertFalse(evidence.exists())
            with mock.patch.object(consumer.shutil, 'which', return_value='/mvn'):
                with self.assertRaisesRegex(consumer.VerificationError, 'outside the checkout'):
                    consumer.main(['--repository', str(root), '--java-home', str(root),
                                   '--evidence-directory', str(evidence)])
            self.assertFalse(evidence.exists())


if __name__ == '__main__':
    unittest.main()
