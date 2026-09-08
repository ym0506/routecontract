import importlib.util
from contextlib import redirect_stdout
import hashlib
import io
import json
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

    def test_checksum_copy_can_corrupt_a_disposable_copy_of_readonly_reviewed_staging(self):
        h = self.helper
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            original, _, receipt = self.checksum_fixture(base)
            for path in original.rglob('*'):
                path.chmod(0o555 if path.is_dir() else 0o444)
            original.chmod(0o555)
            before = h.inventory(original)
            changed = base/'readonly-source-copy'
            control = h.prepare_checksum_copy(original, changed, receipt)
            self.assertEqual(1, control['changedBytes'])
            self.assertEqual(before, h.inventory(original))
            original_jar = original/receipt['artifacts'][0]['relativePath']
            self.assertEqual(0, original_jar.stat().st_mode & 0o222)

    def test_negative_graph_requires_exact_policy_rejection(self):
        h = self.helper
        coordinate = 'org.apache.shardingsphere:shardingsphere-infra-common:jar:5.5.2'
        output = ('[INFO] BUILD FAILURE\n'
                  '[ERROR] Rule 1: org.apache.maven.enforcer.rules.dependency.BannedDependencies failed with message:\n'
                  f'[ERROR]    {coordinate}:test <--- banned via the exclude/include list\n')
        h.verify_failure(1, output, 'graph', coordinate)
        for invalid in ['DependencyConvergence failed', output.replace(':jar:5.5.2', ':jar:5.5.20'),
                        output.replace(':jar:5.5.2', ':jar:5.5.2-SNAPSHOT'),
                        output.replace(coordinate, 'other:library:jar:1')+'\n'+coordinate,
                        output.replace('banned via the exclude/include list', 'mentioned separately'),
                        output+'\nCould not transfer artifact another:library:jar:1']:
            with self.subTest(output=invalid), self.assertRaises(h.VerificationError):
                h.verify_failure(1, invalid, 'graph', coordinate)

    def reviewed_fixture(self, root):
        h = self.helper
        repository = root/'staging'
        for module in h.shared.MODULES:
            for extension in ('jar', 'pom', 'module'):
                path = repository/h.shared.GROUP_PATH/module/'0.2.0'/f'{module}-0.2.0.{extension}'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f'synthetic receipt verifier:{module}:{extension}'.encode())
        receipt = root/'reviewed-receipt.json'
        receipt.write_text(json.dumps(h.shared.repository_receipt(repository)))
        return repository, receipt, h.shared.sha256(receipt)

    def test_reviewed_inputs_require_explicit_hash_full_source_and_exact_nine_payloads(self):
        h = self.helper
        with tempfile.TemporaryDirectory() as temporary:
            repository, receipt, reviewed = self.reviewed_fixture(Path(temporary))
            source = '1'*40
            binding = {'stagedSourceRevision': source, 'productionPublicationInputsIdentical': True}
            with patch.object(h.source_support, 'source_binding', return_value=binding) as source_binding:
                document, actual_binding = h.reviewed_inputs(repository, receipt, reviewed, source)
                self.assertEqual(9, len(document['artifacts']))
                self.assertEqual(binding, actual_binding)
                source_binding.assert_called_once_with(source)
                for expected, revision in [(None, source), ('', source), ('0'*64, source),
                                           (reviewed, 'HEAD'), (reviewed, source[:7])]:
                    with self.subTest(expected=expected, source=revision), self.assertRaises(h.VerificationError):
                        h.reviewed_inputs(repository, receipt, expected, revision)
                data = json.loads(receipt.read_text()); data['artifacts'].pop()
                receipt.write_text(json.dumps(data))
                with self.assertRaises(h.VerificationError):
                    h.reviewed_inputs(repository, receipt, h.shared.sha256(receipt), source)

    def test_reviewed_inputs_reject_changed_payload_source_or_receipt_symlink(self):
        h = self.helper
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, receipt, reviewed = self.reviewed_fixture(base)
            with patch.object(h.source_support, 'source_binding', side_effect=h.source_support.ResolverError('source drift')):
                with self.assertRaises(h.VerificationError):
                    h.reviewed_inputs(repository, receipt, reviewed, '1'*40)
            with patch.object(h.source_support, 'source_binding', return_value={}):
                alias = base/'alias.json'; alias.symlink_to(receipt)
                with self.assertRaises(h.VerificationError):
                    h.reviewed_inputs(repository, alias, reviewed, '1'*40)
                payload = next(repository.rglob('*.jar')); payload.write_bytes(b'changed')
                with self.assertRaises(h.VerificationError):
                    h.reviewed_inputs(repository, receipt, reviewed, '1'*40)

    def test_negative_graph_requires_real_first_party_selection_and_three_correct_nonanchors(self):
        h = self.helper
        for runtime, adapter in h.shared.LANES.items():
            wrong = '5.5.3' if runtime == '5.5.2' else '5.5.2'
            database = 'shardingsphere-infra-database-core' if runtime == '5.5.2' else 'shardingsphere-database-connector-core'
            for case, artifact in [('wrong-runtime', 'shardingsphere-infra-executor'),
                                   ('wrong-non-anchor', 'shardingsphere-infra-common')]:
                children = [{'groupId': h.shared.GROUP, 'artifactId': module, 'version': '0.2.0'}
                            for module in ('routecontract-core', adapter)]
                children += [{'groupId': h.maven_support.SS_GROUP, 'artifactId': anchor,
                              'version': wrong if anchor == artifact else runtime}
                             for anchor in ('shardingsphere-infra-executor', 'shardingsphere-infra-spi', database,
                                            'shardingsphere-infra-common')]
                tree = {'children': children}
                with self.subTest(runtime=runtime, case=case):
                    h.verify_negative_graph(tree, case, runtime, artifact, wrong, {'routeContractVersion': '0.2.0'})
                    for removed in (0, 1):
                        with self.assertRaises(h.VerificationError):
                            h.verify_negative_graph({'children': children[:removed]+children[removed+1:]}, case,
                                                    runtime, artifact, wrong, {'routeContractVersion': '0.2.0'})
                    if case == 'wrong-non-anchor':
                        children[2]['version'] = wrong
                        with self.assertRaises(h.VerificationError):
                            h.verify_negative_graph(tree, case, runtime, artifact, wrong, {'routeContractVersion': '0.2.0'})

    def test_wrong_origin_records_require_exact_pinned_files_and_finalized_gets(self):
        h = self.helper
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository, receipt_path, _ = self.reviewed_fixture(base)
            receipt = h.receipts.load_consumer_receipt(receipt_path)
            adapter = h.shared.LANES['5.5.2']
            selected = [item for item in receipt['artifacts'] if item['module'] in ('routecontract-core', adapter)
                        and item['name'].endswith(('.pom', '.jar'))]
            for item in selected:
                with ((repository/item['relativePath']).parent/'_remote.repositories').open('a') as stream:
                    stream.write(item['name']+'>unintended=\n')
            consumed = h.selected_files(repository, adapter, receipt, 'unintended')
            self.assertEqual(4, len(consumed))
            requests = [{'method':'GET', 'route':'staged', 'status':200, 'path':item['path']} for item in consumed]
            self.assertEqual(4, len(h.verify_origin_requests(requests, consumed)))
            for key, value in [('method', 'HEAD'), ('route', 'central'), ('status', 404), ('path', 'other.jar')]:
                changed = [{**requests[0], key:value}, *requests[1:]]
                with self.subTest(key=key), self.assertRaises(h.VerificationError):
                    h.verify_origin_requests(changed, consumed)
            with self.assertRaises(h.VerificationError):
                h.selected_files(repository, adapter, receipt, h.maven_support.MIRROR_ID)
            (repository/selected[0]['relativePath']).write_bytes(b'corrupted')
            with self.assertRaises(h.VerificationError):
                h.selected_files(repository, adapter, receipt, 'unintended')

    def test_negative_work_starts_with_absent_cache_for_each_java_boundary(self):
        h = self.helper
        with tempfile.TemporaryDirectory() as temporary:
            for java in (17, 21):
                consumer, home, cache = h.prepare_negative(SCRIPT.parents[1], Path(temporary)/str(java), java)
                self.assertTrue((consumer/'pom.xml').is_file())
                self.assertTrue(home.is_dir())
                self.assertFalse(cache.exists())
                tree = ET.parse(consumer/'pom.xml')
                self.assertEqual(str(java), tree.find(h.maven_support.N+'properties/'+h.maven_support.N+'maven.compiler.release').text)

    def test_wrong_origin_settings_cannot_point_to_expected_or_another_repository(self):
        h = self.helper
        with tempfile.TemporaryDirectory() as temporary:
            settings = Path(temporary)/'settings.xml'
            url = 'http://127.0.0.1:12345/'
            h.maven_support.write_settings(settings, url, 'unintended')
            h.verify_settings(settings, url, 'unintended')
            for endpoint, name in [(url, h.maven_support.MIRROR_ID), ('http://127.0.0.1:54321/', 'unintended'),
                                   ('https://example.com/', 'unintended')]:
                with self.assertRaises(h.VerificationError):
                    h.verify_settings(settings, endpoint, name)

    def test_main_completion_is_maven_only_and_rechecks_receipt_bytes_after_cells(self):
        h = self.helper
        # Stubbed cells test aggregation only; no Maven, Java, Docker or network
        # work is executed and none of these synthetic outputs is real evidence.
        for changed, positive_only in [(False, False), (True, False), (False, True)]:
            with tempfile.TemporaryDirectory() as temporary, self.subTest(changed=changed, diagnostic=positive_only):
                base = Path(temporary).resolve()
                repository, receipt, reviewed = self.reviewed_fixture(base)
                evidence = base/'evidence'
                java17, java21 = base/'java17', base/'java21'
                java17.mkdir(); java21.mkdir()
                argv = ['--repository', str(repository), '--reviewed-receipt', str(receipt),
                        '--reviewed-receipt-sha256', reviewed, '--staged-source-revision', '1'*40,
                        '--evidence-directory', str(evidence), '--java17-home', str(java17),
                        '--java21-home', str(java21), '--maven', '/usr/bin/true']
                if positive_only:
                    argv += ['--positive-only', '--java-feature', '17', '--runtime', '5.5.2']
                binding = {'stagedSourceRevision': '1'*40, 'productionPublicationInputsIdentical': True}
                def fake_cell(*args, **kwargs):
                    if changed:
                        receipt.write_bytes(receipt.read_bytes()+b' ')
                    return {'javaFeature': args[6], 'runtime': args[7], 'unitStub': True}
                with patch.object(h.source_support, 'source_binding', return_value=binding), \
                     patch.object(h.network, 'prepare_barrier', return_value={}), \
                     patch.object(h, 'cell', side_effect=fake_cell) as cell, redirect_stdout(io.StringIO()):
                    if changed:
                        with self.assertRaises(h.VerificationError):
                            h.main(argv)
                    else:
                        self.assertEqual(0, h.main(argv))
                summary = json.loads((evidence/'summary.json').read_text())
                self.assertFalse(summary['complete'])
                self.assertFalse(summary['fullA24Complete'])
                self.assertEqual(not changed and not positive_only, summary['completeMavenA24Matrix'])
                self.assertEqual(1 if positive_only else 4, cell.call_count)
                self.assertEqual(positive_only, summary['diagnosticOnly'])

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
