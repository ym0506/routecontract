"""Offline acceptance checks for the legacy resolver runner's evidence boundaries.

Synthetic staged bytes exercise copying and receipts, not Java loading. Source
binding uses a throwaway Git repository; no Gradle process or network runs.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT_ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    'gradle_legacy_consumer_under_test', SCRIPT_ROOT / 'verify-gradle-legacy-artifact-consumer.py'
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
LEGACY_VERSIONS = ('0.1.0', '0.1.2', '0.1.3', '0.1.0-rc2')
CURRENT = '0.2.0'
CORE = 'routecontract-core'
ADAPTER_552 = 'routecontract-shardingsphere-5.5.2'
ADAPTER_553 = 'routecontract-shardingsphere-5.5'


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


class LegacyResolverRunnerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def plan(self):
        registry = MODULE.load_registry(SCRIPT_ROOT / 'legacy-artifact-inputs.json')
        inventory = []
        for legacy in registry['distributed']:
            jar = next(pin for pin in legacy['payloads'] if pin['extension'] == 'jar')
            inventory.append(dict(jar, module=ADAPTER_553, version=legacy['version']))
        for module in (CORE, ADAPTER_552, ADAPTER_553):
            payload = ('synthetic-plan-only:' + module).encode()
            inventory.append({'module': module, 'version': CURRENT,
                              'name': f'{module}-{CURRENT}.jar',
                              'sha256': sha256(payload), 'byteCount': len(payload)})
        cases = MODULE.cases(registry, inventory, self.root / 'repository', CURRENT)
        return cases, inventory

    def test_case_grid_covers_every_distributed_version_and_both_orders(self):
        cases, _ = self.plan()
        suffixes = {
            'alone', 'core-legacy-first', 'core-legacy-last',
            '552-legacy-first', '552-legacy-last',
            'mediated-legacy-first', 'mediated-legacy-last',
            'strict-legacy-first', 'strict-legacy-last',
        }
        required = {f'{version}-{suffix}' for version in LEGACY_VERSIONS for suffix in suffixes}
        required.add('0.1.3-core-without-ownership-control')
        observed = [case['caseId'] for case in cases]
        self.assertEqual(required, set(observed))
        self.assertEqual(37, len(observed))
        self.assertEqual(len(observed), len(set(observed)), 'Duplicate cases cannot replace missing coverage')
        self.assertEqual(Counter({'RESOLVED': 13, 'CAPABILITY_CONFLICT': 16, 'STRICT_VERSION_CONFLICT': 8}),
                         Counter(case['expected'] for case in cases))
        self.assertEqual(set(LEGACY_VERSIONS), {case['legacyVersion'] for case in cases})

    def test_capability_cases_request_actual_legacy_plus_each_current_component(self):
        cases, _ = self.plan()
        by_id = {case['caseId']: case for case in cases}
        for version in LEGACY_VERSIONS:
            legacy = {'module': ADAPTER_553, 'version': version, 'strict': False}
            for suffix, module in (('core', CORE), ('552', ADAPTER_552)):
                current = {'module': module, 'version': CURRENT, 'strict': False}
                for order, requests in (('legacy-first', [legacy, current]), ('legacy-last', [current, legacy])):
                    with self.subTest(version=version, component=module, order=order):
                        case = by_id[f'{version}-{suffix}-{order}']
                        self.assertEqual(requests, case['requests'])
                        self.assertTrue(case['ownershipRule'])
                        self.assertEqual('CAPABILITY_CONFLICT', case['expected'])

    def test_mediation_requires_only_current_adapter_and_transitive_core_bytes(self):
        cases, inventory = self.plan()
        expected = {
            (pin['module'], pin['version']): (pin['name'], pin['sha256'], pin['byteCount'])
            for pin in inventory if pin['version'] == CURRENT and pin['module'] in (CORE, ADAPTER_553)
        }
        mediated = [case for case in cases if '-mediated-' in case['caseId']]
        self.assertEqual(8, len(mediated))
        for case in mediated:
            with self.subTest(case=case['caseId']):
                self.assertEqual('RESOLVED', case['expected'])
                self.assertEqual([ADAPTER_553, ADAPTER_553], [request['module'] for request in case['requests']])
                versions = [request['version'] for request in case['requests']]
                self.assertEqual([case['legacyVersion'], CURRENT] if case['caseId'].endswith('first')
                                 else [CURRENT, case['legacyVersion']], versions)
                self.assertFalse(any(request['strict'] for request in case['requests']))
                self.assertEqual(expected, {
                    (pin['module'], pin['version']): (pin['name'], pin['sha256'], pin['byteCount'])
                    for pin in case['expectedArtifacts']
                })
                self.assertTrue(case['ownershipRule'])

    def test_strict_cases_keep_both_incompatible_same_ga_requirements(self):
        cases, _ = self.plan()
        strict = [case for case in cases if '-strict-' in case['caseId']]
        self.assertEqual(8, len(strict))
        for case in strict:
            with self.subTest(case=case['caseId']):
                self.assertEqual('STRICT_VERSION_CONFLICT', case['expected'])
                self.assertEqual([ADAPTER_553, ADAPTER_553], [request['module'] for request in case['requests']])
                self.assertTrue(all(request['strict'] for request in case['requests']))
                self.assertEqual({case['legacyVersion'], CURRENT}, {request['version'] for request in case['requests']})
                self.assertEqual([], case['expectedArtifacts'])

    def test_rule_disabled_control_is_the_same_latest_legacy_core_combination(self):
        cases, _ = self.plan()
        controls = [case for case in cases if not case['ownershipRule']]
        self.assertEqual(1, len(controls))
        control = controls[0]
        protected = next(case for case in cases if case['caseId'] == '0.1.3-core-legacy-first')
        self.assertEqual(protected['requests'], control['requests'])
        self.assertEqual('RESOLVED', control['expected'])
        self.assertEqual('CAPABILITY_CONFLICT', protected['expected'])
        self.assertEqual({(ADAPTER_553, '0.1.3'), (CORE, CURRENT)},
                         {(pin['module'], pin['version']) for pin in control['expectedArtifacts']})

    def staging(self):
        repository = self.root / 'supplied'
        receipt = {'formatVersion': 1, 'routeContractVersion': CURRENT, 'artifacts': []}
        for module in (CORE, ADAPTER_553, ADAPTER_552):
            for extension in ('jar', 'pom', 'module'):
                name = f'{module}-{CURRENT}.{extension}'
                relative = f'{MODULE.GROUP.replace(".", "/")}/{module}/{CURRENT}/{name}'
                payload = ('synthetic-staged-receipt-only:' + name).encode()
                path = repository / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                receipt['artifacts'].append({'module': module, 'name': name,
                                             'relativePath': relative, 'sha256': sha256(payload)})
        return repository, receipt

    def test_matching_staged_receipt_copies_exactly_nine_reviewed_payloads(self):
        repository, receipt = self.staging()
        destination = self.root / 'isolated'
        inventory = MODULE.prepare_repository(repository, receipt, {'distributed': []}, destination, None)
        self.assertEqual(9, len(inventory))
        self.assertEqual({pin['relativePath'] for pin in receipt['artifacts']},
                         {str(path.relative_to(destination)) for path in destination.rglob('*') if path.is_file()})
        for pin in receipt['artifacts']:
            self.assertEqual((repository / pin['relativePath']).read_bytes(),
                             (destination / pin['relativePath']).read_bytes())

    def test_corrupt_staged_payload_is_rejected_before_copy_or_legacy_download(self):
        repository, receipt = self.staging()
        pin = receipt['artifacts'][0]
        source = repository / pin['relativePath']
        original = source.read_bytes()
        source.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        destination = self.root / 'isolated'
        registry = MODULE.load_registry(SCRIPT_ROOT / 'legacy-artifact-inputs.json')
        with mock.patch.object(MODULE, 'obtain_payload') as obtain:
            with self.assertRaisesRegex(MODULE.ResolverError, 'does not match reviewed receipt'):
                MODULE.prepare_repository(repository, receipt, registry, destination, None)
            obtain.assert_not_called()
        self.assertFalse(destination.exists())

    def git_repository(self):
        repository = self.root / 'source'
        repository.mkdir()
        for filename in ('LICENSE', 'NOTICE', 'README.md'):
            (repository / filename).write_text('original ' + filename + '\n')
        subprocess.run(['git', 'init', '--quiet', str(repository)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(repository), 'add', 'LICENSE', 'NOTICE', 'README.md'],
                       check=True, capture_output=True)
        subprocess.run(['git', '-C', str(repository), '-c', 'user.name=Fixture',
                        '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgSign=false',
                        '-c', 'core.hooksPath=/dev/null', 'commit', '--quiet', '-m', 'Synthetic source-binding fixture'],
                       check=True, capture_output=True)
        revision = subprocess.check_output(['git', '-C', str(repository), 'rev-parse', 'HEAD'], text=True).strip()
        return repository, revision

    def test_embedded_license_and_notice_changes_fail_real_git_source_binding(self):
        repository, revision = self.git_repository()
        with mock.patch.object(MODULE, 'ROOT', repository):
            original = MODULE.source_binding(revision)
            self.assertTrue(original['productionPublicationInputsIdentical'])
            for filename in ('LICENSE', 'NOTICE'):
                with self.subTest(filename=filename):
                    path = repository / filename
                    contents = path.read_bytes()
                    path.write_bytes(contents + b'changed embedded publication input\n')
                    with self.assertRaisesRegex(MODULE.ResolverError, filename):
                        MODULE.source_binding(revision)
                    path.write_bytes(contents)
            self.assertEqual(original, MODULE.source_binding(revision))

    def test_documentation_only_change_does_not_claim_production_drift(self):
        repository, revision = self.git_repository()
        (repository / 'README.md').write_text('Changed explanation; publication inputs unchanged\n')
        with mock.patch.object(MODULE, 'ROOT', repository):
            result = MODULE.source_binding(revision)
        self.assertEqual(revision, result['stagedSourceRevision'])
        self.assertTrue(result['productionPublicationInputsIdentical'])

    def test_incorrect_distribution_checksum_is_rejected_without_creating_seed(self):
        archive = self.root / 'gradle-8.14.4-bin.zip'
        archive.write_bytes(b'PK\x03\x04not the checksum-pinned Gradle distribution')
        seed = self.root / 'wrapper-seed'
        with self.assertRaisesRegex(MODULE.ResolverError, 'does not match the wrapper checksum'):
            MODULE.seed_distribution_zip(archive, seed)
        self.assertFalse(seed.exists())


if __name__ == '__main__':
    unittest.main()
