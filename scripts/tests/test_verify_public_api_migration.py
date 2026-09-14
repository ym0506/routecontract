"""Fail-closed checks for the independently executed A-26 consumer harness."""
from pathlib import Path
import importlib.util
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('public_api_migration', ROOT / 'scripts/verify-public-api-migration.py')
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


class PublicApiMigrationHarnessTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def payloads(self, version):
        modules = (HARNESS.ADAPTER,) if version == '0.1.2' else (HARNESS.ADAPTER, HARNESS.CORE)
        result = {}
        for module in modules:
            parent = self.root / HARNESS.GROUP_PATH / module / version
            parent.mkdir(parents=True)
            for extension in ('jar', 'pom'):
                path = parent / f'{module}-{version}.{extension}'
                path.write_bytes(f'{module}:{version}:{extension}'.encode())
                result[path.name] = HARNESS.digest(path)
        return {'artifacts': result}

    def test_authenticated_old_payload_is_rejected_after_one_byte_changes(self):
        pins = self.payloads('0.1.2')
        HARNESS.receipt(self.root, '0.1.2', pins)
        path = self.root / HARNESS.GROUP_PATH / HARNESS.ADAPTER / '0.1.2' / f'{HARNESS.ADAPTER}-0.1.2.jar'
        path.write_bytes(path.read_bytes() + b'changed')
        with self.assertRaisesRegex(HARNESS.VerificationError, 'Immutable public'):
            HARNESS.receipt(self.root, '0.1.2', pins)

    def test_missing_staged_core_pom_cannot_use_a_jar_only_graph(self):
        self.payloads('0.2.0')
        path = self.root / HARNESS.GROUP_PATH / HARNESS.CORE / '0.2.0' / f'{HARNESS.CORE}-0.2.0.pom'
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            HARNESS.receipt(self.root, '0.2.0', {})

    def test_symlinked_staged_payload_is_not_accepted_as_supplied_bytes(self):
        self.payloads('0.2.0')
        path = self.root / HARNESS.GROUP_PATH / HARNESS.CORE / '0.2.0' / f'{HARNESS.CORE}-0.2.0.jar'
        real = self.root / 'substituted.jar'
        real.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(real)
        with self.assertRaisesRegex(HARNESS.VerificationError, 'symlinks'):
            HARNESS.receipt(self.root, '0.2.0', {})

    def test_descriptor_comparison_detects_a_removed_old_constructor(self):
        frozen = (ROOT / 'examples/public-api-migration-consumer/public-api-0.1.2.txt').read_text()
        original = '    descriptor: (Ljava/lang/String;)V'
        # Remove only the exception's constructor descriptor; every other signature stays present.
        current = frozen.replace(original, '    descriptor: (Ljava/lang/Object;)V', 1)
        with self.assertRaisesRegex(HARNESS.VerificationError, 'descriptors removed/changed'):
            HARNESS.verify_api_inventory(frozen, current, frozen)

    def test_inventory_authentication_is_separate_from_current_additions(self):
        frozen = (ROOT / 'examples/public-api-migration-consumer/public-api-0.1.2.txt').read_text()
        changed = frozen.replace('CURRENT_SCHEMA_VERSION = 1', 'CURRENT_SCHEMA_VERSION = 2')
        verified = HARNESS.verify_api_inventory(frozen, changed, frozen)
        self.assertEqual({'publicTypes': 26, 'preservedMemberDescriptors': 167}, verified)
        with self.assertRaisesRegex(HARNESS.VerificationError, 'Pinned old API inventory'):
            HARNESS.verify_api_inventory(changed, changed, frozen)

    def junit(self):
        suite = ET.Element('testsuite', {'name': HARNESS.SUITE, 'tests': '3', 'failures': '0', 'errors': '0', 'skipped': '0'})
        for name in sorted(HARNESS.EXPECTED_MYSQL_CASES):
            ET.SubElement(suite, 'testcase', {'name': name + '()'})
        path = self.root / 'junit.xml'
        ET.ElementTree(suite).write(path)
        return suite, path

    def test_skipped_or_replaced_mysql_case_does_not_pass_with_green_totals(self):
        suite, path = self.junit()
        self.assertEqual(3, HARNESS.verify_junit(path)['tests'])
        case = suite.find('testcase')
        ET.SubElement(case, 'skipped')
        ET.ElementTree(suite).write(path)
        with self.assertRaisesRegex(HARNESS.VerificationError, 'did not pass'):
            HARNESS.verify_junit(path)
        case.remove(case.find('skipped'))
        case.set('name', 'unrelatedGreenTest()')
        ET.ElementTree(suite).write(path)
        with self.assertRaisesRegex(HARNESS.VerificationError, 'incomplete or failed'):
            HARNESS.verify_junit(path)

    def test_metadata_preparation_rejects_trust_bypass(self):
        metadata = self.root / 'metadata.xml'
        metadata.write_text(f'<verification-metadata xmlns="{HARNESS.NS}"><configuration><verify-metadata>true</verify-metadata><trusted-artifacts/></configuration><components/></verification-metadata>')
        with self.assertRaisesRegex(HARNESS.VerificationError, 'trust bypasses'):
            HARNESS.prepare_metadata(metadata, self.root / 'out.xml', [])
        self.assertFalse((self.root / 'out.xml').exists())

    def test_missing_exact_business_rows_cannot_be_replaced_by_a_green_summary(self):
        baseline = ROOT / 'examples/public-api-migration-consumer/src/test/resources/manifests/find-paid-orders-by-user.approved.json'
        (self.root / 'approved.json').write_bytes(baseline.read_bytes())
        one = json.loads(baseline.read_text())
        for name in ('equality-capture.json', 'equality-capture-result.json'):
            (self.root / name).write_text(json.dumps(one))
        two = json.loads(baseline.read_text())
        two['counts']['observedPhysicalAttemptCount'] = 2
        (self.root / 'candidate.json').write_text(json.dumps(two))
        (self.root / 'business-rows.json').write_text(json.dumps({
            'syntheticFixtureData': True, 'equality': [], 'range': [],
        }))
        with self.assertRaisesRegex(HARNESS.VerificationError, 'exact expected result'):
            HARNESS.verify_mysql_evidence(self.root, '0.1.2', HARNESS.digest(baseline))

    def test_runtime_only_core_cannot_prove_normal_source_compilation(self):
        self.payloads('0.2.0')
        expected = HARNESS.receipt(self.root, '0.2.0', {})
        consumer = self.root / 'consumer'
        (consumer / 'build').mkdir(parents=True)
        artifacts = []
        for item in expected['artifacts']:
            if item['name'].endswith('.jar'):
                artifacts.append({'coordinate': f'{HARNESS.GROUP}:{item["module"]}:0.2.0',
                                  'file': str(self.root / item['relativePath']), 'sha256': item['sha256']})
        value = {'version': '0.2.0', 'directRouteContractDependencies': [HARNESS.ADAPTER],
                 'transitiveCore': True, 'artifacts': artifacts,
                 'classpath': [item['file'] for item in artifacts],
                 'compileClasspath': [item['file'] for item in artifacts if HARNESS.CORE not in item['coordinate']]}
        graph = consumer / 'build/migration-graph.json'
        graph.write_text(json.dumps(value))
        with self.assertRaisesRegex(HARNESS.VerificationError, 'resolved compile classpath'):
            HARNESS.graph_data(consumer, self.root, expected)
        value['compileClasspath'] = value['classpath']
        graph.write_text(json.dumps(value))
        HARNESS.graph_data(consumer, self.root, expected)

    def test_direct_core_is_rejected_even_when_its_payload_is_valid(self):
        self.payloads('0.2.0')
        expected = HARNESS.receipt(self.root, '0.2.0', {})
        consumer = self.root / 'consumer'
        (consumer / 'build').mkdir(parents=True)
        (consumer / 'build/migration-graph.json').write_text(json.dumps({
            'version': '0.2.0', 'directRouteContractDependencies': [HARNESS.ADAPTER, HARNESS.CORE],
            'transitiveCore': True,
        }))
        with self.assertRaisesRegex(HARNESS.VerificationError, 'exactly the existing adapter'):
            HARNESS.graph_data(consumer, self.root, expected)


if __name__ == '__main__':
    unittest.main()
