"""Offline integrity checks for the registry and passive legacy artifact inspection.

The small synthetic ZIPs model entry identity only. They are not executable Java
fixtures and do not establish resolver, classpath, or MySQL acceptance.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile


SPEC = importlib.util.spec_from_file_location(
    'legacy_artifact_inputs_under_test', Path(__file__).parents[1] / 'legacy_artifact_inputs.py'
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
REGISTRY = Path(__file__).parents[1] / 'legacy-artifact-inputs.json'


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class LegacyArtifactInputsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def registry(self):
        return json.loads(REGISTRY.read_bytes())

    def write_registry(self, registry):
        path = self.root / 'registry.json'
        path.write_text(json.dumps(registry), encoding='utf-8')
        return path

    def fixture(self, version='0.1.3', *, service=None, duplicate_entry=None):
        item = copy.deepcopy(next(row for row in self.registry()['distributed'] if row['version'] == version))
        entries = {
            name: b'\xca\xfe\xba\xbe\x00\x00\x00\x3d-synthetic-layout-' + name.encode('ascii')
            for name in MODULE.ENTRIES if name != MODULE.SERVICE
        }
        entries[MODULE.SERVICE] = service if service is not None else (MODULE.PROVIDER + '\n').encode('ascii')
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name, payload in entries.items():
                archive.writestr(name, payload)
            if duplicate_entry is not None:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    archive.writestr(duplicate_entry, entries[duplicate_entry])
        jar = stream.getvalue()
        item['layout']['entries'] = {name: sha256(payload) for name, payload in entries.items()}
        pom = (
            '<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>'
            f'<groupId>{MODULE.GROUP}</groupId><artifactId>{MODULE.ARTIFACT}</artifactId>'
            f'<version>{version}</version></project>'
        ).encode('utf-8')
        payloads = {'jar': jar, 'pom': pom}
        if version == '0.1.3':
            filename = f'{MODULE.ARTIFACT}-{version}.jar'
            metadata = {
                'formatVersion': '1.1',
                'component': {
                    'group': MODULE.GROUP, 'module': MODULE.ARTIFACT, 'version': version,
                    'attributes': {'org.gradle.status': 'release'},
                },
                'variants': [
                    {'name': variant, 'files': [{
                        'name': filename, 'url': filename, 'sha256': sha256(jar), 'size': len(jar),
                    }]}
                    for variant in ('apiElements', 'runtimeElements')
                ],
            }
            payloads['module'] = json.dumps(metadata).encode('utf-8')
        for pin in item['payloads']:
            payload = payloads[pin['extension']]
            pin['sha256'] = sha256(payload)
            pin['byteCount'] = len(payload)
        return item, payloads

    def test_reviewed_registry_keeps_distributed_and_tag_only_inputs_separate(self):
        registry = MODULE.load_registry(REGISTRY)
        self.assertEqual(['0.1.0', '0.1.2', '0.1.3', '0.1.0-rc2'],
                         [row['version'] for row in registry['distributed']])
        self.assertEqual({'0.1.0-rc1', '0.1.1'}, {row['version'] for row in registry['tagOnly']})
        current = next(row for row in registry['distributed'] if row['version'] == '0.1.3')
        self.assertEqual(['jar', 'pom', 'module'], [pin['extension'] for pin in current['payloads']])

    def test_tag_only_version_cannot_be_promoted_to_runnable_input(self):
        for version in ('0.1.0-rc1', '0.1.1'):
            with self.subTest(version=version):
                registry = self.registry()
                promoted = copy.deepcopy(registry['distributed'][0])
                promoted['version'] = version
                promoted['tag'] = 'v' + version
                registry['distributed'].append(promoted)
                registry['tagOnly'] = [row for row in registry['tagOnly'] if row['version'] != version]
                with self.assertRaises(MODULE.LegacyInputError):
                    MODULE.load_registry(self.write_registry(registry))

    def test_distributed_rc_cannot_be_replaced_by_tag_only_evidence(self):
        registry = self.registry()
        rc = registry['distributed'].pop()
        registry['tagOnly'].append(rc)
        with self.assertRaises(MODULE.LegacyInputError):
            MODULE.load_registry(self.write_registry(registry))

    def test_public_module_pin_cannot_be_removed(self):
        registry = self.registry()
        current = next(row for row in registry['distributed'] if row['version'] == '0.1.3')
        current['payloads'].pop()
        with self.assertRaises(MODULE.LegacyInputError):
            MODULE.load_registry(self.write_registry(registry))

    def test_duplicate_registry_key_is_rejected(self):
        original = REGISTRY.read_bytes()
        path = self.root / 'duplicate.json'
        path.write_bytes(b'{"formatVersion":1,' + original.lstrip()[1:])
        with self.assertRaises(MODULE.LegacyInputError):
            MODULE.load_registry(path)

    def test_exact_payloads_and_layouts_pass_for_both_metadata_shapes(self):
        for version in ('0.1.0', '0.1.3'):
            with self.subTest(version=version):
                item, payloads = self.fixture(version)
                for pin in item['payloads']:
                    MODULE.verify_payload(pin, payloads[pin['extension']])
                MODULE.verify_layout(item, payloads)

    def test_altered_pinned_payload_is_rejected_even_when_size_is_unchanged(self):
        item, payloads = self.fixture()
        pin = next(pin for pin in item['payloads'] if pin['extension'] == 'jar')
        original = payloads['jar']
        changed = original[:-1] + bytes([original[-1] ^ 1])
        self.assertEqual(len(original), len(changed))
        with self.assertRaises(MODULE.LegacyInputError):
            MODULE.verify_payload(pin, changed)

    def test_truncated_payload_is_rejected(self):
        item, payloads = self.fixture()
        pin = next(pin for pin in item['payloads'] if pin['extension'] == 'pom')
        with self.assertRaises(MODULE.LegacyInputError):
            MODULE.verify_payload(pin, payloads['pom'][:-1])

    def test_duplicate_required_jar_entry_is_rejected_after_outer_hash_matches(self):
        for entry in (MODULE.ENTRIES[0], MODULE.SERVICE):
            with self.subTest(entry=entry):
                item, payloads = self.fixture(duplicate_entry=entry)
                MODULE.verify_payload(item['payloads'][0], payloads['jar'])
                with self.assertRaises(MODULE.LegacyInputError):
                    MODULE.verify_layout(item, payloads)

    def test_additional_service_provider_is_rejected_after_entry_hash_matches(self):
        service = (MODULE.PROVIDER + '\nexample.UnexpectedProvider\n').encode('ascii')
        item, payloads = self.fixture(service=service)
        MODULE.verify_payload(item['payloads'][0], payloads['jar'])
        with self.assertRaises(MODULE.LegacyInputError):
            MODULE.verify_layout(item, payloads)

    def test_changed_required_class_is_rejected_by_its_entry_pin(self):
        item, payloads = self.fixture()
        item['layout']['entries'][MODULE.ENTRIES[0]] = '0' * 64
        with self.assertRaises(MODULE.LegacyInputError):
            MODULE.verify_layout(item, payloads)

    def test_wrong_pom_coordinate_is_rejected(self):
        for field, expected, replacement in (
            ('groupId', MODULE.GROUP, 'example.other'),
            ('artifactId', MODULE.ARTIFACT, 'other-artifact'),
            ('version', '0.1.3', '0.1.2'),
        ):
            with self.subTest(field=field):
                item, payloads = self.fixture()
                payloads['pom'] = payloads['pom'].replace(
                    f'<{field}>{expected}</{field}>'.encode(),
                    f'<{field}>{replacement}</{field}>'.encode(),
                )
                with self.assertRaises(MODULE.LegacyInputError):
                    MODULE.verify_layout(item, payloads)

    def test_module_main_jar_binding_is_checked_in_each_variant(self):
        for variant in ('apiElements', 'runtimeElements'):
            for field, replacement in (
                ('sha256', '0' * 64), ('size', 1), ('name', 'other.jar'), ('url', 'other.jar'),
            ):
                with self.subTest(variant=variant, field=field):
                    item, payloads = self.fixture()
                    metadata = json.loads(payloads['module'])
                    selected = next(row for row in metadata['variants'] if row['name'] == variant)
                    selected['files'][0][field] = replacement
                    payloads['module'] = json.dumps(metadata).encode()
                    with self.assertRaises(MODULE.LegacyInputError):
                        MODULE.verify_layout(item, payloads)

    def test_duplicate_main_jar_variant_is_rejected(self):
        item, payloads = self.fixture()
        metadata = json.loads(payloads['module'])
        metadata['variants'].append(copy.deepcopy(metadata['variants'][0]))
        payloads['module'] = json.dumps(metadata).encode()
        with self.assertRaises(MODULE.LegacyInputError):
            MODULE.verify_layout(item, payloads)


if __name__ == '__main__':
    unittest.main()
