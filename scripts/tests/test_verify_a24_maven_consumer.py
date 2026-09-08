import importlib.util
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

SCRIPT = Path(__file__).resolve().parents[1] / 'verify-a24-maven-consumer.py'


class A24MavenControlsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('a24_maven_tested', SCRIPT)
        cls.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.helper)

    def checksum_fixture(self, root):
        h = self.helper
        relative = str(h.shared.GROUP_PATH)+'/routecontract-core/0.2.0/routecontract-core-0.2.0.jar'
        original, corrupted = root/'original', root/'corrupted'
        payload = b'PK\x03\x04controlled-original-jar-bytes'
        changed = bytearray(payload)
        changed[len(changed)//2] ^= 1
        for directory, content in ((original, payload), (corrupted, changed)):
            path = directory/relative
            path.parent.mkdir(parents=True)
            path.write_bytes(content)
            for algorithm in ('sha1', 'sha256', 'sha512', 'md5'):
                path.with_name(path.name+'.'+algorithm).write_text(hashlib.new(algorithm, payload).hexdigest()+'\n')
        receipt = {'routeContractVersion': '0.2.0', 'artifacts': [{
            'module': 'routecontract-core', 'name': 'routecontract-core-0.2.0.jar',
            'relativePath': relative, 'sha256': hashlib.sha256(payload).hexdigest()}]}
        return original, corrupted, receipt

    def checksum_evidence(self, root):
        h = self.helper
        original, corrupted, receipt = self.checksum_fixture(root)
        control = h.checksum_control(original, corrupted, receipt)
        url = 'http://127.0.0.1:12345/'
        digest = control['digests']['sha1']
        output = ("[INFO] BUILD FAILURE\n[ERROR] \tCould not transfer artifact "+control['coordinate']+
                  f" from/to {h.maven_support.MIRROR_ID} ({url}): Checksum validation failed, "
                  f"expected '{digest['expected']}' (REMOTE_EXTERNAL) but is actually '{digest['actual']}'\n")
        requests = [{'method':'GET', 'route':'staged', 'status':200, 'path':path}
                    for path in (control['path'], digest['sidecarPath'])]
        command = ['mvn', '--strict-checksums', h.DEPENDENCY_RESOLVE]
        return control, url, output, requests, command

    def test_generic_checksum_classifier_can_no_longer_claim_acceptance(self):
        h = self.helper
        with self.assertRaises(h.VerificationError):
            h.verify_failure(1, 'Checksum validation failed for routecontract-core', 'checksum', 'routecontract-core')

    def test_native_checksum_binds_exact_jar_url_get_and_actual_digests_with_retries(self):
        h = self.helper
        with tempfile.TemporaryDirectory() as temporary:
            control, url, output, requests, command = self.checksum_evidence(Path(temporary))
            result = h.verify_checksum_failure(1, output, requests+requests, command, url, control)
            self.assertEqual(url+control['path'], result['requestedJarUrl'])
            self.assertEqual('sha1', result['algorithm'])
            self.assertEqual(2, len(result['successfulRequests']['jar']))
            self.assertEqual(control['corruptedSha256'], result['corruptedSha256'])

    def test_unrelated_native_failures_do_not_count_as_modified_jar_rejection(self):
        h = self.helper
        with tempfile.TemporaryDirectory() as temporary:
            control, url, output, requests, command = self.checksum_evidence(Path(temporary))
            bad_outputs = [output.replace(':jar:0.2.0', ':pom:0.2.0'),
                           output.replace('routecontract-core:jar', 'unrelated:jar')+'\nroutecontract-core\n',
                           output.replace(':12345/', ':54321/'),
                           output.replace(h.maven_support.MIRROR_ID, 'unintended'),
                           output.replace('[ERROR]', '[WARNING]')+'\n[ERROR] unrelated compile failure',
                           output.replace(control['digests']['sha1']['actual'], control['digests']['sha1']['expected']),
                           output.replace('REMOTE_EXTERNAL', 'LOCAL'),
                           output.replace('Checksum validation', '\n[ERROR] Checksum validation'),
                           '[INFO] BUILD FAILURE\n[ERROR] Checksum validation failed for unrelated.pom\nroutecontract-core']
            for value in bad_outputs:
                with self.subTest(output=value), self.assertRaises(h.VerificationError):
                    h.verify_checksum_failure(1, value, requests, command, url, control)
            for code, args in [(0, command), (1, ['mvn', h.DEPENDENCY_RESOLVE]),
                               (1, command+['--lax-checksums'])]:
                with self.assertRaises(h.VerificationError):
                    h.verify_checksum_failure(code, output, requests, args, url, control)

    def test_checksum_needs_successful_jar_and_matching_sidecar_gets(self):
        h = self.helper
        with tempfile.TemporaryDirectory() as temporary:
            control, url, output, requests, command = self.checksum_evidence(Path(temporary))
            bad = [requests[:1], requests[1:]]
            for key, value in [('method', 'HEAD'), ('route', 'central'), ('status', 404),
                               ('status', 502), ('path', control['path']+'.pom')]:
                bad.append([{**requests[0], key:value}, requests[1]])
            for value in bad:
                with self.subTest(requests=value), self.assertRaises(h.VerificationError):
                    h.verify_checksum_failure(1, output, value, command, url, control)

    def test_corruption_must_preserve_other_bytes_and_original_sidecars(self):
        h = self.helper
        for mutation in ('receipt', 'sidecar', 'two-bytes', 'size', 'extra-file'):
            with tempfile.TemporaryDirectory() as temporary:
                original, corrupted, receipt = self.checksum_fixture(Path(temporary))
                path = corrupted/receipt['artifacts'][0]['relativePath']
                if mutation == 'receipt':
                    receipt['artifacts'][0]['sha256'] = '0'*64
                elif mutation == 'sidecar':
                    path.with_name(path.name+'.sha1').write_text(hashlib.sha1(path.read_bytes()).hexdigest())
                elif mutation == 'two-bytes':
                    content = bytearray(path.read_bytes()); content[0] ^= 1; path.write_bytes(content)
                elif mutation == 'size':
                    path.write_bytes(path.read_bytes()+b'changed')
                else:
                    (corrupted/'unexpected').write_text('extra')
                with self.subTest(mutation=mutation), self.assertRaises(h.VerificationError):
                    h.checksum_control(original, corrupted, receipt)

    def test_negative_graph_requires_exact_policy_rejection(self):
        h = self.helper
        h.verify_failure(1, 'BannedDependencies failed shardingsphere-infra-common:jar:5.5.2',
                         'graph', 'shardingsphere-infra-common:jar:5.5.2')
        with self.assertRaises(h.VerificationError):
            h.verify_failure(1, 'DependencyConvergence failed', 'graph', 'shardingsphere-infra-common')

    def test_snapshot_clone_is_disposable_and_snapshot_detects_change(self):
        h = self.helper
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            (source / 'payload').write_bytes(b'reviewed')
            snapshot = root / 'snapshot'
            expected = h.freeze_cache(source, snapshot)
            clone = root / 'clone'
            h.clone_cache(snapshot, clone)
            (clone / 'payload').write_bytes(b'changed')
            self.assertEqual(expected, h.inventory(snapshot))
            self.assertNotEqual(expected, h.inventory(clone))
            for path in [snapshot / 'payload', snapshot]:
                path.chmod(0o700)

    def test_java21_compiler_and_enforcer_boundaries_both_change(self):
        h = self.helper
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'consumer'
            h.configure_consumer(SCRIPT.parents[1], destination, 21)
            pom = ET.parse(destination / 'pom.xml').getroot()
            n = h.maven_support.N
            self.assertEqual('21', pom.find(n+'properties/'+n+'maven.compiler.release').text)
            self.assertEqual('[21,22)', pom.find('.//'+n+'requireJavaVersion/'+n+'version').text)
            self.assertEqual('21', pom.find('.//'+n+'configuration/'+n+'release').text)
            fixture = destination/'src/test/java/io/github/ym0506/routecontract/consumer/StagedArtifactMySqlTest.java'
            self.assertIn(h.network.MYSQL_IMAGE, fixture.read_text())
            self.assertNotIn(h.network.MYSQL_SOURCE_IMAGE, fixture.read_text())
            self.assertEqual(h.network.MYSQL_SOURCE_IMAGE.split('@')[1], h.network.MYSQL_IMAGE.split('@')[1])

    def test_environment_replaces_hostile_jvm_proxy_and_testcontainers_options(self):
        h = self.helper
        hostile = {'HTTPS_PROXY': 'http://unexpected.invalid', 'http_proxy': 'http://unexpected.invalid',
                   'ALL_PROXY': 'http://unexpected.invalid', 'NO_PROXY': '*',
                   'JAVA_TOOL_OPTIONS': '-javaagent:unexpected.jar', '_JAVA_OPTIONS': '-Xmx1m',
                   'JDK_JAVA_OPTIONS': '-Djava.net.preferIPv4Stack=false',
                   'TESTCONTAINERS_PULL_POLICY': 'unexpected.AllowPull',
                   'TESTCONTAINERS_RYUK_DISABLED': 'true', 'DOCKER_HOST': 'tcp://unexpected.invalid:2375',
                   'DOCKER_CONFIG': '/unexpected', 'CLASSPATH': '/unexpected', 'PATH': '/usr/bin'}
        images = {'mysql': {'reference': h.network.MYSQL_IMAGE},
                  'ryuk': {'reference': 'testcontainers/ryuk@sha256:' + 'a'*64}}
        with patch.dict(h.os.environ, hostile, clear=True):
            actual = h.environment(Path('/jdk'), Path('/private/home'),
                                   docker_socket=Path('/private/docker.sock'), images=images)
        self.assertFalse(any(key.lower().endswith('_proxy') for key in actual))
        self.assertEqual(h.network.JAVA_IPV4_OPTION, actual['JAVA_TOOL_OPTIONS'])
        self.assertNotIn('_JAVA_OPTIONS', actual)
        self.assertNotIn('JDK_JAVA_OPTIONS', actual)
        self.assertNotIn('CLASSPATH', actual)
        self.assertEqual('unix:///private/docker.sock', actual['DOCKER_HOST'])
        self.assertEqual('/private/home/.docker', actual['DOCKER_CONFIG'])
        self.assertEqual(h.network.PULL_POLICY_CLASS, actual['TESTCONTAINERS_PULL_POLICY'])
        self.assertEqual('false', actual['TESTCONTAINERS_RYUK_DISABLED'])

    def test_policy_evidence_requires_actual_both_images_and_no_unexpected_image(self):
        h = self.helper
        images = {'mysql': {'reference': 'mysql@sha256:reviewed'},
                  'ryuk': {'reference': 'testcontainers/ryuk@sha256:reviewed'}}
        output = '\n'.join('A24_IMAGE_PULL_BLOCKED image='+entry['reference'] for entry in images.values())
        self.assertEqual(2, len(h.network.verify_pull_policy(output, images)['actualInvocations']))
        for bad in ['', output.splitlines()[0], output+'\nA24_IMAGE_PULL_BLOCKED image=unexpected']:
            with self.assertRaises(h.network.NetworkBarrierError):
                h.network.verify_pull_policy(bad, images)

    def test_closed_endpoint_requires_actual_connection_refused(self):
        h = self.helper
        with patch.object(h.network.socket, 'create_connection', side_effect=ConnectionRefusedError):
            self.assertEqual('REFUSED', h.network.require_closed_endpoint('http://127.0.0.1:12345/')['connectionAfterShutdown'])
        with patch.object(h.network.socket, 'create_connection'):
            with self.assertRaises(h.network.NetworkBarrierError):
                h.network.require_closed_endpoint('http://127.0.0.1:12345/')
        for value in ['file:///tmp/repository', 'http://example.com:12345/', 'https://127.0.0.1:12345/']:
            with self.assertRaises(h.network.NetworkBarrierError):
                h.network.require_closed_endpoint(value)

    def test_offline_execution_rejects_jdk_without_actual_barrier_proof(self):
        h = self.helper
        with self.assertRaises(h.VerificationError):
            h.execute(['mvn'], Path('/work'), {'JAVA_HOME': '/jdk', 'JAVA_TOOL_OPTIONS': h.network.JAVA_IPV4_OPTION},
                      Path('/absent/evidence'), 'must-not-run', barrier={'javaRuntimes': {}})

    def test_missing_local_image_never_triggers_download(self):
        h = self.helper
        missing = h.subprocess.CompletedProcess(['docker'], 1, '', 'No such image')
        with patch.object(h.network.subprocess, 'run', return_value=missing) as run:
            with self.assertRaises(h.network.NetworkBarrierError):
                h.network.inspect_local_images(Path('/docker.sock'))
            command = run.call_args.args[0]
            self.assertIn('inspect', command)
            self.assertNotIn('pull', command)

    def test_different_ryuk_digest_between_online_and_offline_is_rejected(self):
        h = self.helper
        expected = {'mysql': {'reference': 'mysql@reviewed'}, 'ryuk': {'reference': 'ryuk@first'}}
        h.network.require_same_images(expected, dict(expected))
        with self.assertRaises(h.network.NetworkBarrierError):
            h.network.require_same_images(expected, {**expected, 'ryuk': {'reference': 'ryuk@different'}})
        with self.assertRaises(h.network.NetworkBarrierError):
            h.network.require_same_images({}, {})

    def test_evidence_path_rejects_parent_traversal_and_symlink_alias(self):
        h = self.helper
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root, repository = base/'source', base/'staging'
            root.mkdir()
            repository.mkdir()
            alias = base/'alias'
            alias.symlink_to(root, target_is_directory=True)
            for path in [alias/'evidence', base/'uncreated/../source/evidence', root/'evidence']:
                with self.assertRaises(h.VerificationError):
                    h.evidence_path(path, root, repository)
            self.assertEqual(base/'evidence', h.evidence_path(base/'evidence', root, repository))

    def test_junit_requires_three_distinct_actual_fixture_tests(self):
        h = self.helper
        name = 'io.github.ym0506.routecontract.consumer.StagedArtifactMySqlTest'
        suite = ET.Element('testsuite', {'name': name})
        for test in sorted(h.TEST_NAMES):
            ET.SubElement(suite, 'testcase', {'name': test, 'classname': name})
        h.verify_junit_identity(suite)
        suite.findall('testcase')[1].set('name', suite.findall('testcase')[0].get('name'))
        with self.assertRaises(h.VerificationError):
            h.verify_junit_identity(suite)


if __name__ == '__main__':
    unittest.main()
