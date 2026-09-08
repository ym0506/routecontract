"""Bounded A-24 verifier tests; no network, Gradle, Docker or MySQL execution.

Synthetic receipts and process outcomes test rejection/preparation boundaries only.
They are never accepted as staged-byte consumer or offline-execution evidence.
"""
import copy
from contextlib import ExitStack, contextmanager, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'a24_gradle_consumer_unit_tests', ROOT / 'scripts/verify-a24-gradle-consumer.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
GROUP = MODULE.staged.GROUP
MODULES = MODULE.staged.MODULES


def synthetic_receipt(version='0.2.0'):
    artifacts = []
    for name in MODULES:
        for extension in ('jar', 'pom', 'module'):
            filename = f'{name}-{version}.{extension}'
            artifacts.append({'module': name, 'name': filename,
                              'relativePath': f'{GROUP.replace(".", "/")}/{name}/{version}/{filename}',
                              'sha256': hashlib.sha256(filename.encode()).hexdigest()})
    return {'formatVersion': 1, 'routeContractVersion': version, 'artifacts': artifacts}


def artifact_records(receipt, runtime, kotlin=False):
    selected = [item for item in receipt['artifacts']
                if item['name'].endswith('.jar')
                and item['module'] in ('routecontract-core', MODULE.staged.LANES[runtime])]
    records = [{'coordinate': f'{GROUP}:{pin["module"]}:0.2.0',
                'name': pin['name'], 'sha256': pin['sha256']} for pin in selected]
    if kotlin:
        return [dict(item, configuration=configuration)
                for configuration in ('testCompileClasspath', 'testRuntimeClasspath')
                for item in records]
    return {'compile': copy.deepcopy(records), 'runtime': copy.deepcopy(records)}


class A24GradleConsumerPreparationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='routecontract-a24-unit-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.receipt = synthetic_receipt()

    def write_artifacts(self, data):
        consumer = self.root / 'consumer'
        destination = consumer / 'build/routecontract-consumer-evidence/resolved-first-party.json'
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(data))
        return consumer

    def test_both_dsl_shapes_normalize_to_the_same_two_exact_artifacts_per_classpath(self):
        for runtime in MODULE.staged.LANES:
            with self.subTest(runtime=runtime):
                expected = artifact_records(self.receipt, runtime)
                groovy = MODULE.verified_first_party(self.write_artifacts(expected), runtime, self.receipt)
                kotlin = MODULE.verified_first_party(
                    self.write_artifacts(artifact_records(self.receipt, runtime, kotlin=True)),
                    runtime, self.receipt)
                self.assertEqual(expected, groovy)
                self.assertEqual(expected, kotlin)

    def test_duplicate_or_missing_classpath_artifacts_never_count_as_two_verified_jars(self):
        for runtime in MODULE.staged.LANES:
            valid = artifact_records(self.receipt, runtime)
            invalid = []
            duplicate = copy.deepcopy(valid)
            duplicate['compile'][1] = copy.deepcopy(duplicate['compile'][0])
            invalid.append(duplicate)
            missing = copy.deepcopy(valid)
            missing['runtime'].pop()
            invalid.append(missing)
            flattened = artifact_records(self.receipt, runtime, kotlin=True)
            flattened[-1]['configuration'] = 'testCompileClasspath'
            invalid.append(flattened)
            unknown = artifact_records(self.receipt, runtime, kotlin=True)
            unknown[0]['configuration'] = 'runtimeClasspath'
            invalid.append(unknown)
            for records in invalid:
                with self.subTest(runtime=runtime, records=records), self.assertRaises(MODULE.AcceptanceError):
                    MODULE.verified_first_party(self.write_artifacts(records), runtime, self.receipt)

    def test_first_party_evidence_preserves_additional_measured_byte_counts(self):
        records = artifact_records(self.receipt, '5.5.2', kotlin=True)
        for item in records:
            item['byteCount'] = len(item['name'].encode())
        result = MODULE.verified_first_party(self.write_artifacts(records), '5.5.2', self.receipt)
        for scope in ('compile', 'runtime'):
            self.assertEqual(2, len(result[scope]))
            self.assertTrue(all(item['byteCount'] == len(item['name'].encode()) for item in result[scope]))

    def test_wrong_hash_filename_or_release_cannot_satisfy_receipt_identity(self):
        for runtime in MODULE.staged.LANES:
            for field, value in (('sha256', '0' * 64), ('name', 'renamed.jar'),
                                 ('coordinate', f'{GROUP}:routecontract-core:0.1.2')):
                with self.subTest(runtime=runtime, field=field):
                    records = artifact_records(self.receipt, runtime)
                    records['runtime'][0][field] = value
                    with self.assertRaises(MODULE.AcceptanceError):
                        MODULE.verified_first_party(self.write_artifacts(records), runtime, self.receipt)

    def test_receipt_pinned_copy_rejects_tampered_or_symlinked_payload(self):
        repository = self.root / 'repository'
        for pin in self.receipt['artifacts']:
            path = repository / pin['relativePath']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(pin['name'].encode())
        pin = self.receipt['artifacts'][0]
        target = repository / pin['relativePath']
        target.write_bytes(b'tampered fixture bytes')
        with self.assertRaisesRegex(MODULE.AcceptanceError, 'reviewed receipt'):
            MODULE.copy_repository(repository, self.receipt, self.root / 'bad-copy')
        target.unlink()
        original = self.root / 'correct-synthetic-payload'
        original.write_bytes(pin['name'].encode())
        target.symlink_to(original)
        with self.assertRaisesRegex(MODULE.AcceptanceError, 'reviewed receipt'):
            MODULE.copy_repository(repository, self.receipt, self.root / 'symlink-copy')

    def test_origin_control_changes_one_exclusive_group_and_preserves_other_policy_text(self):
        for dsl, expression in (('groovy', 'includeGroup routeGroup'), ('kotlin', 'includeGroup(routeGroup)')):
            consumer = self.root / dsl
            consumer.mkdir()
            build = consumer / ('build.gradle.kts' if dsl == 'kotlin' else 'build.gradle')
            original = 'before\n' + expression + '\nafter checksum and lock policy\n'
            build.write_text(original)
            result = MODULE.disable_exclusive_group(consumer, dsl)
            self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), result['originalBuildSha256'])
            self.assertNotEqual(result['originalBuildSha256'], result['controlBuildSha256'])
            self.assertEqual(MODULE.sha(build), result['controlBuildSha256'])
            self.assertTrue(build.read_text().startswith('before\n'))
            self.assertTrue(build.read_text().endswith('\nafter checksum and lock policy\n'))
            self.assertEqual(1, build.read_text().count('io.github.ym0506.routecontract.disabled-origin-control'))
            with self.assertRaises(MODULE.AcceptanceError):
                MODULE.disable_exclusive_group(consumer, dsl)
            build.write_text(expression + '\n' + expression + '\n')
            with self.assertRaises(MODULE.AcceptanceError):
                MODULE.disable_exclusive_group(consumer, dsl)

    def test_checksum_control_changes_only_the_single_core_jar_trust_pin(self):
        consumer = self.root / 'checksum'
        metadata = consumer / 'gradle/verification-metadata.xml'
        MODULE.staged.prepare_metadata(ROOT / 'gradle/verification-metadata.xml', metadata, self.receipt)
        namespace = {'v': MODULE.staged.NAMESPACE}
        def pins():
            result = {}
            for component in ET.parse(metadata).findall('v:components/v:component', namespace):
                for artifact in component.findall('v:artifact', namespace):
                    result[(component.get('group'), component.get('name'), component.get('version'), artifact.get('name'))] = ET.tostring(artifact)
            return result
        before = pins()
        MODULE.corrupt_core_checksum(consumer)
        after = pins()
        changed = [key for key in before if before[key] != after[key]]
        self.assertEqual([(GROUP, 'routecontract-core', '0.2.0', 'routecontract-core-0.2.0.jar')], changed)
        self.assertIn(('value="' + '0' * 64 + '"').encode(), after[changed[0]])
        self.assertEqual(set(before), set(after))

    def test_inventory_detects_frozen_cache_changes_and_rejects_symlink_entries(self):
        cache = self.root / 'cache'
        cache.mkdir()
        artifact = cache / 'dependency.jar'
        artifact.write_bytes(b'primed bytes')
        before = MODULE.tree_inventory(cache)
        artifact.write_bytes(b'changed after prime')
        self.assertNotEqual(before, MODULE.tree_inventory(cache))
        (cache / 'alias.jar').symlink_to(artifact)
        with self.assertRaisesRegex(MODULE.AcceptanceError, 'symlinks'):
            MODULE.tree_inventory(cache)

    def test_changed_network_profile_is_rejected_before_starting_a_process(self):
        profile = self.root / 'profile.sb'
        profile.write_text('(version 1)\n(deny network-outbound)\n')
        barrier = {'profilePath': str(profile), 'profileSha256': MODULE.sha(profile)}
        profile.write_text('(version 1)\n(allow default)\n')
        fake_sandbox = self.root / 'sandbox-exec'
        fake_sandbox.write_text('not executed')
        with mock.patch.object(MODULE.network.sys, 'platform', 'darwin'), \
                mock.patch.object(MODULE.network, 'SANDBOX', fake_sandbox), \
                self.assertRaises(MODULE.network.NetworkBarrierError):
            MODULE.network.sandboxed(['never-executed'], barrier)

    def test_invalid_or_wrong_candidate_receipt_fails_before_wrapper_or_consumer_preparation(self):
        invalid = ['{"formatVersion":1,"formatVersion":1}', json.dumps(synthetic_receipt('0.2.1'))]
        for index, contents in enumerate(invalid):
            receipt_path = self.root / f'receipt-{index}.json'
            receipt_path.write_text(contents)
            argv = ['verify-a24-gradle-consumer.py', '--repository', str(self.root / 'unused-staging'),
                    '--staged-receipt', str(receipt_path), '--staged-source-revision', 'fixture-source',
                    '--staged-receipt-sha256', hashlib.sha256(contents.encode()).hexdigest(),
                    '--evidence-directory', str(self.root / f'evidence-{index}'),
                    '--java-home', str(self.root / 'unused-java'),
                    '--gradle-distribution-zip', str(self.root / 'unused-archive')]
            with self.subTest(index=index), mock.patch.object(MODULE.sys, 'argv', argv), \
                    mock.patch.object(MODULE, 'source_snapshot', return_value={}), \
                    mock.patch.object(MODULE.legacy, 'source_binding', return_value={}), \
                    mock.patch.object(MODULE, 'copy_repository') as copy_repository, \
                    mock.patch.object(MODULE.wrapper, 'verify_toolchain') as verify_toolchain, \
                    mock.patch.object(MODULE.network, 'prepare_barrier') as prepare_barrier:
                with self.assertRaises((MODULE.AcceptanceError, ValueError)):
                    MODULE.main()
                copy_repository.assert_not_called()
                verify_toolchain.assert_not_called()
                prepare_barrier.assert_not_called()

    def checksum_inputs(self):
        """Synthetic bytes and native-shaped text, never a real Gradle result."""
        consumer = self.root / 'checksum' / 'consumer'
        metadata = consumer / 'gradle/verification-metadata.xml'
        MODULE.staged.prepare_metadata(ROOT / 'gradle/verification-metadata.xml', metadata, self.receipt)
        mutation = MODULE.corrupt_core_checksum(consumer, self.receipt)
        pin = MODULE.core_pin(self.receipt)
        cached = (consumer.parent / 'gradle-home/caches/modules-2/files-2.1' / GROUP /
                  'routecontract-core/0.2.0/synthetic-content-address' / pin['name'])
        cached.parent.mkdir(parents=True)
        cached.write_bytes(pin['name'].encode())
        message = (f"On artifact {pin['name']} ({GROUP}:routecontract-core:0.2.0) "
                   "in repository 'reviewedStaging': expected a 'sha256' checksum of '" + '0' * 64 +
                   f"' but was '{pin['sha256']}'")
        output = "Dependency verification failed for configuration ':testRuntimeClasspath'\n" + message + '\nBUILD FAILED\n'
        requests = [self.http_row(pin['relativePath'])]
        return consumer, cached, mutation, output, requests

    @staticmethod
    def http_row(path, method='GET', status=200, route='staged'):
        return {'method': method, 'path': path, 'status': status, 'route': route}

    def checksum_result(self, consumer, mutation, output, requests, code=1):
        return MODULE.verify_checksum_negative(code, output, requests, 'http://127.0.0.1:49151/',
                                               self.receipt, mutation, consumer)

    def test_native_checksum_binding_accepts_one_exact_section_and_whitespace_wrapping(self):
        consumer, _cached, mutation, output, requests = self.checksum_inputs()
        for contents in (output, output.replace("in repository", "\n    in repository")):
            with self.subTest(contents=contents):
                result = self.checksum_result(consumer, mutation, contents, requests)
                self.assertEqual('NATIVE_CHECKSUM_REJECTED', result['result'])
                self.assertEqual(MODULE.core_pin(self.receipt)['sha256'], result['cachedCoreSha256'])
                self.assertEqual(requests, result['successfulJarGets'])

    def test_checksum_rejects_unrelated_artifact_repository_algorithm_or_digest(self):
        consumer, _cached, mutation, output, requests = self.checksum_inputs()
        invalid = [
            output.replace('On artifact routecontract-core-', 'On artifact unrelated-core-'),
            output.replace("in repository 'reviewedStaging'", "in repository 'unintendedDecoy'"),
            output.replace("a 'sha256'", "a 'sha1'"),
            output.replace('0' * 64, '1' * 64),
            output.replace(MODULE.core_pin(self.receipt)['sha256'], '2' * 64),
            output.replace('Dependency verification failed for', 'Unrelated failure for'),
            output.replace('BUILD FAILED', 'BUILD SUCCESSFUL'),
            output.replace("in repository", "\nOn artifact unrelated.jar (other:module:1) in repository"),
        ]
        for contents in invalid:
            with self.subTest(contents=contents), self.assertRaises(MODULE.AcceptanceError):
                self.checksum_result(consumer, mutation, contents, requests)
        with self.assertRaises(MODULE.AcceptanceError):
            self.checksum_result(consumer, mutation, output, requests, code=0)

    def test_checksum_requires_finalized_exact_get_and_reviewed_cached_bytes(self):
        consumer, cached, mutation, output, requests = self.checksum_inputs()
        path = requests[0]['path']
        invalid = [[], [self.http_row(path, method='HEAD')], [self.http_row(path, status=502)],
                   [self.http_row(path, route='central')], [self.http_row(path + '.sha256')]]
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(MODULE.AcceptanceError):
                self.checksum_result(consumer, mutation, output, rows)
        cached.write_bytes(b'unreviewed synthetic payload')
        with self.assertRaisesRegex(MODULE.AcceptanceError, 'reviewed core JAR bytes'):
            self.checksum_result(consumer, mutation, output, requests)
        cached.unlink()
        with self.assertRaisesRegex(MODULE.AcceptanceError, 'reviewed core JAR bytes'):
            self.checksum_result(consumer, mutation, output, requests)

    def test_checksum_rejects_later_metadata_change_or_inconsistent_mutation_receipt(self):
        consumer, _cached, mutation, output, requests = self.checksum_inputs()
        for field, value in (('reviewedActualSha256', '1' * 64), ('incorrectExpectedSha256', '1' * 64)):
            changed = dict(mutation, **{field: value})
            with self.subTest(field=field), self.assertRaises(MODULE.AcceptanceError):
                self.checksum_result(consumer, changed, output, requests)
        metadata = consumer / 'gradle/verification-metadata.xml'
        metadata.write_bytes(metadata.read_bytes() + b'\n')
        with self.assertRaises(MODULE.AcceptanceError):
            self.checksum_result(consumer, mutation, output, requests)

    def test_core_pin_mutation_rejects_preexisting_unreviewed_trust_and_preserves_original(self):
        consumer, _cached, mutation, _output, _requests = self.checksum_inputs()
        original = consumer.parent / 'verification-metadata.original.xml'
        self.assertEqual(mutation['originalMetadataSha256'], MODULE.sha(original))
        before = (consumer / 'gradle/verification-metadata.xml').read_bytes()
        with self.assertRaisesRegex(MODULE.AcceptanceError, 'original trust pin'):
            MODULE.corrupt_core_checksum(consumer, self.receipt)
        self.assertEqual(before, (consumer / 'gradle/verification-metadata.xml').read_bytes())

    def test_repository_requests_are_consumed_only_after_server_finalizes_log(self):
        log = self.root / 'synthetic-requests.jsonl'
        row = self.http_row('io/example/synthetic.jar')

        @contextmanager
        def fake_server(_repository, supplied_log):
            self.assertEqual(log, supplied_log)
            try:
                yield 'http://127.0.0.1:49151/'
            finally:
                log.write_text(json.dumps(row) + '\n')

        with mock.patch.object(MODULE.mirror, 'serve_repository', fake_server):
            with MODULE.repository_server(self.root / 'unused-repository', log) as (_url, requests):
                self.assertEqual([], requests)
            self.assertEqual([row], requests)

    def origin_inputs(self, runtime):
        selected = [pin for pin in self.receipt['artifacts'] if pin['module'] in
                    ('routecontract-core', MODULE.staged.LANES[runtime]) and pin['name'].endswith('.jar')]
        consumer = self.write_artifacts(artifact_records(self.receipt, runtime))
        missing = '\n'.join(f"Could not find {GROUP}:{pin['module']}:0.2.0." for pin in selected)
        approved = [self.http_row(pin['relativePath'].removesuffix('.jar') + '.pom', status=404) for pin in selected]
        decoy = [self.http_row(pin['relativePath']) for pin in selected]
        marker = f'ROUTECONTRACT_STAGED_GRAPH_VERIFIED version={runtime} artifacts=2 shardingsphereComponents=synthetic\n'
        return consumer, missing, approved, decoy, marker

    def origin_result(self, case, code, output, approved, decoy, consumer, runtime):
        return MODULE.verify_origin_negative(case, code, output, approved, decoy,
                                              'http://127.0.0.1:49151/', 'http://127.0.0.1:49152/',
                                              consumer, runtime, self.receipt)

    def test_origin_protection_and_disabled_control_require_distinct_exact_outcomes(self):
        for runtime in MODULE.staged.LANES:
            consumer, missing, approved, decoy, marker = self.origin_inputs(runtime)
            with self.subTest(runtime=runtime):
                protected = self.origin_result('wrong-origin', 1, missing, approved, [], consumer, runtime)
                control = self.origin_result('origin-control', 0, marker, approved, decoy, consumer, runtime)
                self.assertEqual('WRONG_ORIGIN_REJECTED', protected['result'])
                self.assertEqual('UNPROTECTED_ORIGIN_CONTROL_RESOLVED', control['result'])
                self.assertEqual(artifact_records(self.receipt, runtime), control['firstParty'])

    def test_protected_origin_rejects_missing_coordinate_lookups_or_any_decoy_access(self):
        consumer, missing, approved, decoy, _marker = self.origin_inputs('5.5.2')
        invalid = [(missing.splitlines()[0], approved, []), (missing, approved[:1], []),
                   (missing, [dict(row, status=200) for row in approved], []),
                   (missing, [dict(row, path='unrelated.pom') for row in approved], []),
                   (missing, approved, [dict(decoy[0], method='HEAD', status=404)])]
        for output, rows, decoy_rows in invalid:
            with self.subTest(output=output, rows=rows, decoy=decoy_rows), self.assertRaises(MODULE.AcceptanceError):
                self.origin_result('wrong-origin', 1, output, rows, decoy_rows, consumer, '5.5.2')
        with self.assertRaises(MODULE.AcceptanceError):
            self.origin_result('wrong-origin', 0, missing, approved, [], consumer, '5.5.2')

    def test_protected_origin_cannot_count_unrelated_transport_or_checksum_failures(self):
        consumer, missing, approved, _decoy, _marker = self.origin_inputs('5.5.2')
        for unrelated in ('Could not GET https://example.invalid/third-party.jar',
                          "Dependency verification failed for configuration ':unrelated'",
                          'Received status code 503 from server',
                          'Could not find unrelated:module:1.'):
            with self.subTest(unrelated=unrelated), self.assertRaises(MODULE.AcceptanceError):
                self.origin_result('wrong-origin', 1, missing + '\n' + unrelated,
                                   approved, [], consumer, '5.5.2')

    def test_origin_control_requires_both_successful_jars_graph_and_reviewed_bytes(self):
        consumer, _missing, approved, decoy, marker = self.origin_inputs('5.5.3')
        invalid = [[], decoy[:1], [dict(row, method='HEAD') for row in decoy],
                   [dict(row, status=502) for row in decoy],
                   [dict(row, path=row['path'] + '.sha256') for row in decoy]]
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(MODULE.AcceptanceError):
                self.origin_result('origin-control', 0, marker, approved, rows, consumer, '5.5.3')
        for code, output in ((1, marker), (0, ''), (0, marker + marker)):
            with self.subTest(code=code, output=output), self.assertRaises(MODULE.AcceptanceError):
                self.origin_result('origin-control', code, output, approved, decoy, consumer, '5.5.3')
        data = artifact_records(self.receipt, '5.5.3')
        data['runtime'][0]['sha256'] = 'f' * 64
        self.write_artifacts(data)
        with self.assertRaises(MODULE.AcceptanceError):
            self.origin_result('origin-control', 0, marker, approved, decoy, consumer, '5.5.3')

    def version_inputs(self, case, runtime):
        other = '5.5.3' if runtime == '5.5.2' else '5.5.2'
        module = 'shardingsphere-infra-executor' if case == 'wrong-anchor' else 'shardingsphere-infra-common'
        wrong = f'org.apache.shardingsphere:{module}:{other}'
        marker = 'WRONG_ANCHOR_REJECTED' if case == 'wrong-anchor' else 'WRONG_NON_ANCHOR_REJECTED'
        output = f'ROUTECONTRACT_STAGED_{marker} version={runtime} module={module}'
        report = {'runtime': runtime, 'requestedWrongCoordinate': wrong, 'actualUnresolvedSelector': wrong,
                  'selectedAdapter': f'{GROUP}:{MODULE.staged.LANES[runtime]}:0.2.0',
                  'correctAnchors': [],
                  'failureMessages': [f'Could not resolve {wrong}.\n'
                                      f'RC_STAGED_RUNTIME_REJECTED: expected {runtime}; requested {wrong}']}
        if case == 'wrong-non-anchor':
            output += ' correctAnchors=3'
            anchors = ['shardingsphere-infra-executor', 'shardingsphere-infra-spi',
                       'shardingsphere-infra-database-core' if runtime == '5.5.2' else 'shardingsphere-database-connector-core']
            report['correctAnchors'] = sorted('org.apache.shardingsphere:' + name + ':' + runtime for name in anchors)
        consumer = self.root / 'version' / 'consumer'
        path = consumer / 'build/routecontract-consumer-evidence' / (case + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report))
        return consumer, path, report, output + '\n'

    def test_version_rejection_binds_each_runtime_and_module_to_actual_policy_cause(self):
        for case in ('wrong-anchor', 'wrong-non-anchor'):
            for runtime in MODULE.staged.LANES:
                consumer, _path, report, output = self.version_inputs(case, runtime)
                with self.subTest(case=case, runtime=runtime):
                    result = MODULE.verify_version_negative(case, 0, output, consumer, runtime)
                    self.assertEqual(report, result['observedPolicyRejection'])

    def test_version_rejection_cannot_be_satisfied_by_claimed_wrong_selector_or_other_failure(self):
        consumer, path, report, output = self.version_inputs('wrong-anchor', '5.5.2')
        invalid = []
        for field, value in (('runtime', '5.5.3'), ('requestedWrongCoordinate', 'org.apache.shardingsphere:other:5.5.3'),
                             ('actualUnresolvedSelector', 'org.apache.shardingsphere:other:5.5.3'),
                             ('selectedAdapter', f'{GROUP}:routecontract-shardingsphere-5.5:0.2.0')):
            invalid.append(dict(report, **{field: value}))
        chain = report['failureMessages'][0].splitlines()
        invalid += [dict(report, failureMessages=[chain[0]]),
                    dict(report, failureMessages=[chain[1]]),
                    dict(report, failureMessages=[message.replace('5.5.3', '5.5.2') for message in report['failureMessages']])]
        for unrelated in ('Could not GET external.invalid/x', 'Could not HEAD external.invalid/x',
                          'Received status code 503', 'Dependency verification failed for unrelated',
                          'No cached version of unrelated:module:1 available for offline mode'):
            invalid.append(dict(report, failureMessages=report['failureMessages'] + [unrelated]))
        for changed in invalid:
            path.write_text(json.dumps(changed))
            with self.subTest(report=changed), self.assertRaises(MODULE.AcceptanceError):
                MODULE.verify_version_negative('wrong-anchor', 0, output, consumer, '5.5.2')

    def test_version_rejection_requires_three_distinct_correct_anchors_and_single_task_result(self):
        consumer, path, report, output = self.version_inputs('wrong-non-anchor', '5.5.3')
        anchors = report['correctAnchors']
        for changed in ([], anchors[:2], anchors + anchors[:1],
                        [anchors[0], anchors[0], anchors[2]],
                        [value.replace(':5.5.3', ':5.5.2') for value in anchors]):
            path.write_text(json.dumps(dict(report, correctAnchors=changed)))
            with self.subTest(anchors=changed), self.assertRaises(MODULE.AcceptanceError):
                MODULE.verify_version_negative('wrong-non-anchor', 0, output, consumer, '5.5.3')
        path.write_text(json.dumps(report))
        for code, text in ((1, output), (0, ''), (0, output + output)):
            with self.subTest(code=code, output=text), self.assertRaises(MODULE.AcceptanceError):
                MODULE.verify_version_negative('wrong-non-anchor', code, text, consumer, '5.5.3')

    def test_version_rejection_cannot_mix_another_resolution_or_policy_cause_into_valid_chain(self):
        consumer, path, report, output = self.version_inputs('wrong-anchor', '5.5.2')
        for unrelated in ('Could not resolve unrelated:module:1.',
                          'Could not find unrelated:module:1.',
                          'RC_STAGED_RUNTIME_REJECTED: expected 5.5.2; requested '
                          'org.apache.shardingsphere:shardingsphere-infra-common:5.5.3'):
            changed = dict(report, failureMessages=[report['failureMessages'][0] + '\n' + unrelated])
            path.write_text(json.dumps(changed))
            with self.subTest(unrelated=unrelated), self.assertRaises(MODULE.AcceptanceError):
                MODULE.verify_version_negative('wrong-anchor', 0, output, consumer, '5.5.2')

    def test_plan_is_28_distinct_identities_and_closes_required_controls_without_full_claim(self):
        full = MODULE.selected_plan(list(MODULE.FIXTURES), list(MODULE.staged.LANES), list(MODULE.CASES))
        self.assertEqual(28, len(full))
        self.assertEqual(28, len({tuple(sorted(row.items())) for row in full}))
        self.assertEqual([{'profile': 'kotlin', 'runtime': '5.5.2', 'case': case}
                          for case in ('online', 'offline', 'wrong-origin', 'origin-control')],
                         MODULE.selected_plan(['kotlin'], ['5.5.2'], ['offline', 'wrong-origin']))
        self.assertEqual([{'profile': 'groovy', 'runtime': '5.5.3', 'case': 'origin-control'}],
                         MODULE.selected_plan(['groovy'], ['5.5.3'], ['origin-control']))
        for dsls, runtimes, cases in ((['groovy', 'groovy'], ['5.5.2'], ['online']),
                                      (['groovy'], ['5.5.2', '5.5.2'], ['online']),
                                      (['groovy'], ['5.5.2'], ['online', 'online'])):
            with self.subTest(dsls=dsls, runtimes=runtimes, cases=cases), self.assertRaises(MODULE.AcceptanceError):
                MODULE.selected_plan(dsls, runtimes, cases)

    def main_arguments(self, suffix, extra=()):
        receipt = self.root / (suffix + '-receipt.json')
        receipt.write_text(json.dumps(self.receipt))
        evidence = self.root / (suffix + '-evidence')
        return [
            'verify-a24-gradle-consumer.py', '--repository', str(self.root / 'unused-staging'),
            '--staged-receipt', str(receipt), '--staged-receipt-sha256', MODULE.sha(receipt),
            '--staged-source-revision', 'synthetic-source-revision', '--evidence-directory', str(evidence),
            '--java-home', str(self.root / 'unused-java'), '--gradle-distribution-zip', str(self.root / 'unused-wrapper'),
            *extra,
        ], evidence

    @contextmanager
    def synthetic_main(self, argv, results):
        """Mock every build/toolchain integration boundary; outputs stay in TemporaryDirectory."""
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(mock.patch.object(MODULE.sys, 'argv', argv))
            for target, name, value in (
                (MODULE, 'source_snapshot', {}), (MODULE.legacy, 'source_binding', {}),
                (MODULE, 'load_consumer_receipt', self.receipt), (MODULE, 'copy_repository', None),
                (MODULE.wrapper, 'verify_toolchain', None), (MODULE.legacy, 'seed_distribution_zip', None),
                (MODULE.wrapper, 'prepare_wrapper_seed', None),
                (MODULE.subprocess, 'check_output', 'Synthetic test fixture\nGradle 8.14.4\nLauncher JVM: 17.0.0 (synthetic)\n'),
                (MODULE.network, 'prepare_barrier', {}), (MODULE.staged, 'verify_receipt', None),
            ):
                stack.enter_context(mock.patch.object(target, name, return_value=value))
            runner = stack.enter_context(mock.patch.object(MODULE, 'run_profile', return_value=results))
            yield runner

    def test_summary_remains_partial_and_requires_exact_completed_case_identities(self):
        selectors = ['--dsl', 'groovy', '--runtime', '5.5.2', '--case', 'wrong-anchor']
        row = {'profile': 'groovy', 'runtime': '5.5.2', 'case': 'wrong-anchor'}
        argv, evidence = self.main_arguments('partial', selectors)
        with self.synthetic_main(argv, [row]):
            MODULE.main()
        summary = json.loads((evidence / 'summary.json').read_text())
        self.assertEqual('PARTIAL_VERIFIED', summary['status'])
        self.assertFalse(summary['completeGradleA24Matrix'])
        self.assertFalse(summary['mavenA24Verified'])
        self.assertEqual(1, summary['caseCount'])
        for index, invalid in enumerate(([], [row, row], [dict(row, runtime='5.5.3')])):
            argv, evidence = self.main_arguments('invalid-results-' + str(index), selectors)
            with self.subTest(results=invalid), self.synthetic_main(argv, invalid), \
                    self.assertRaisesRegex(MODULE.AcceptanceError, 'finite requested plan'):
                MODULE.main()
            self.assertFalse((evidence / 'summary.json').exists())
            self.assertFalse(json.loads((evidence / 'failure.json').read_text())['completeGradleA24Matrix'])

    def test_prepare_only_can_never_become_execution_or_matrix_evidence(self):
        argv, evidence = self.main_arguments('prepared', ['--prepare-only'])
        with self.synthetic_main(argv, []) as runner, \
                mock.patch.object(MODULE, 'prepare_case', return_value=(self.root / 'synthetic-consumer', None)) as prepare, \
                mock.patch.object(MODULE, 'corrupt_core_checksum'), mock.patch.object(MODULE, 'disable_exclusive_group'):
            MODULE.main()
            runner.assert_not_called()
            self.assertEqual(28, prepare.call_count)
        summary = json.loads((evidence / 'summary.json').read_text())
        self.assertEqual('PREPARED_ONLY', summary['status'])
        self.assertFalse(summary['completeGradleA24Matrix'])
        self.assertEqual(0, summary['executedCaseCount'])
        self.assertEqual(28, summary['preparedCaseCount'])

    def test_separately_reviewed_receipt_hash_is_checked_before_payload_or_tool_execution(self):
        for index, supplied in enumerate(('a' * 64, 'A' * 64, 'too-short')):
            argv, evidence = self.main_arguments('receipt-hash-' + str(index))
            argv[argv.index('--staged-receipt-sha256') + 1] = supplied
            with self.subTest(hash=supplied), self.synthetic_main(argv, []) as runner, \
                    mock.patch.object(MODULE, 'copy_repository') as copied, \
                    mock.patch.object(MODULE.wrapper, 'verify_toolchain') as toolchain:
                with self.assertRaisesRegex(MODULE.AcceptanceError, 'separately reviewed SHA-256'):
                    MODULE.main()
                copied.assert_not_called()
                toolchain.assert_not_called()
                runner.assert_not_called()
            self.assertFalse((evidence / 'summary.json').exists())

    def test_reviewed_fixture_manifest_drift_is_rejected_before_source_or_artifact_access(self):
        manifest = self.root / 'reviewed-inputs.json'
        manifest.write_text(json.dumps({'synthetic-fixture': 'a' * 64}))
        argv, _evidence = self.main_arguments('fixture-drift', ['--expected-input-manifest', str(manifest)])
        with self.synthetic_main(argv, []), mock.patch.object(MODULE.legacy, 'source_binding') as binding, \
                mock.patch.object(MODULE, 'copy_repository') as copied:
            with self.assertRaisesRegex(MODULE.AcceptanceError, 'reviewed input manifest'):
                MODULE.main()
            binding.assert_not_called()
            copied.assert_not_called()

    def test_consumer_command_uses_http_endpoint_strict_verification_and_explicit_runtime(self):
        consumer, cache, java = self.root / 'consumer', self.root / 'gradle-home', self.root / 'jdk17'
        command = MODULE.command_for(consumer, cache, 'http://127.0.0.1:49151/', '5.5.2',
                                     self.receipt, java, ['--offline', 'clean', 'test', 'verifySelectedGraph'])
        self.assertIn('-ProutecontractRepositoryUrl=http://127.0.0.1:49151/', command)
        self.assertIn('-Porg.gradle.dependency.verification.console=verbose', command)
        self.assertIn('--dependency-verification=strict', command)
        self.assertIn('-ProutecontractRuntime=5.5.2', command)
        self.assertIn('-Dorg.gradle.java.installations.auto-download=false', command)
        self.assertEqual(['--offline', 'clean', 'test', 'verifySelectedGraph'], command[-4:])
        self.assertFalse(any(value.startswith('-ProutecontractRepository=') for value in command))
        for invalid in ('file:///tmp/staging', '/tmp/staging', 'https://repo.maven.apache.org/maven2/',
                        'http://external.invalid:49151/', 'http://user:secret@127.0.0.1:49151/'):
            with self.subTest(url=invalid), self.assertRaises(MODULE.AcceptanceError):
                MODULE.command_for(consumer, cache, invalid, '5.5.2', self.receipt, java, ['verifySelectedGraph'])

    def test_execute_uses_private_home_and_replaces_ambient_jvm_proxy_and_docker_settings(self):
        directory = self.root / 'execution'
        (directory / 'consumer').mkdir(parents=True)
        cache, java = directory / 'gradle-home', self.root / 'jdk17'
        ambient = {'PATH': '/synthetic-bin', 'HOME': '/ambient-user', 'CLASSPATH': 'ambient.jar',
                   'GRADLE_RO_DEP_CACHE': '/ambient-cache', 'GRADLE_OPTS': '-I /ambient/init.gradle',
                   'ORG_GRADLE_PROJECT_secret': 'ambient-project-property',
                   'JAVA_TOOL_OPTIONS': '-Djava.net.preferIPv4Stack=false', 'HTTP_PROXY': 'http://ambient.invalid',
                   'DOCKER_HOST': 'tcp://ambient.invalid:2375', 'DOCKER_CONFIG': '/ambient-docker',
                   'TESTCONTAINERS_PULL_POLICY': 'ambient.PullEverything'}
        images = {'mysql': {'reference': 'mysql@sha256:' + '1' * 64},
                  'ryuk': {'reference': 'testcontainers/ryuk@sha256:' + '2' * 64}}
        with mock.patch.dict(os.environ, ambient, clear=True), \
                mock.patch.object(MODULE.network, 'local_docker_socket', return_value=self.root / 'synthetic-docker.sock'), \
                mock.patch.object(MODULE.subprocess, 'run', return_value=mock.Mock(returncode=0)) as process:
            MODULE.execute(directory, ['synthetic-gradlew', 'test'], cache, java, 'synthetic absent cache', images=images)
        args, kwargs = process.call_args
        env = kwargs['env']
        self.assertEqual(str(directory / 'home'), env['HOME'])
        self.assertEqual(str(directory / 'home/.docker'), env['DOCKER_CONFIG'])
        self.assertEqual(env['HOME'], env['ROUTECONTRACT_A24_PRIVATE_HOME'])
        self.assertEqual(str(java), env['JAVA_HOME'])
        self.assertEqual(str(cache), env['GRADLE_USER_HOME'])
        self.assertEqual('-Djava.net.preferIPv4Stack=true', env['JAVA_TOOL_OPTIONS'])
        self.assertEqual(MODULE.network.PULL_POLICY_CLASS, env['TESTCONTAINERS_PULL_POLICY'])
        self.assertEqual('unix://' + str(self.root / 'synthetic-docker.sock'), env['DOCKER_HOST'])
        for key in ('CLASSPATH', 'GRADLE_RO_DEP_CACHE', 'GRADLE_OPTS', 'ORG_GRADLE_PROJECT_secret', 'HTTP_PROXY'):
            self.assertNotIn(key, env)
        self.assertEqual('-Duser.home=' + env['HOME'], args[0][1])
        self.assertEqual({'exitCode': 0}, json.loads((directory / 'exit.json').read_text()))

    def test_offline_execute_requires_proof_for_the_selected_jdk_before_process_launch(self):
        directory = self.root / 'unproved-offline'
        (directory / 'consumer').mkdir(parents=True)
        with mock.patch.object(MODULE.network, 'local_docker_socket', return_value=self.root / 'unused.sock'), \
                mock.patch.object(MODULE.subprocess, 'run') as process, \
                self.assertRaisesRegex(MODULE.AcceptanceError, 'exact selected JDK'):
            MODULE.execute(directory, ['never-executed'], directory / 'cache', self.root / 'jdk17',
                           'synthetic frozen prime', barrier={'javaRuntimes': {str(self.root / 'other-jdk'): {}}})
        process.assert_not_called()


if __name__ == '__main__':
    unittest.main()
