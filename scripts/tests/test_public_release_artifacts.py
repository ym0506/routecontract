import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('public_release_artifacts', Path(__file__).parents[1] / 'public_release_artifacts.py')
receipt = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(receipt)


def valid_receipt(version='0.1.3'):
    artifacts = []
    for module in receipt.MODULES:
        for extension in receipt.EXTENSIONS:
            name = f'{module}-{version}.{extension}'
            artifacts.append({'module': module, 'name': name,
                              'relativePath': f'{receipt.GROUP_PATH}/{module}/{version}/{name}',
                              'sha256': 'a' * 64})
    return {'formatVersion': 1, 'routeContractVersion': version, 'artifacts': artifacts}


class PublicReceiptTest(unittest.TestCase):
    def test_stable_patch_and_canonical_order(self):
        value = valid_receipt('0.1.13')
        shuffled = copy.deepcopy(value)
        shuffled['artifacts'].reverse()
        self.assertEqual(value, receipt.validate_consumer_receipt(shuffled))

    def test_rejects_versions_outside_reviewed_line(self):
        for version in ('0.1.0', '0.1.1', '0.1.2', '0.2.0', '1.0.0', '0.1.03', '0.1.3-rc1', '0.1.3-SNAPSHOT', '../0.1.3', True, None, '0.1.' + '1'*100):
            with self.subTest(version=version), self.assertRaises(receipt.ReceiptError):
                receipt.validate_consumer_receipt(valid_receipt(version))

    def test_rejects_nonexact_header(self):
        for field, value in (('formatVersion', True), ('formatVersion', 1.0), ('formatVersion', 2), ('unknown', 'ignored')):
            document = valid_receipt()
            document[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(receipt.ReceiptError):
                receipt.validate_consumer_receipt(document)

    def test_rejects_duplicate_missing_and_extra_payloads(self):
        original = valid_receipt()
        for entries in (original['artifacts'][:-1], original['artifacts'] + [original['artifacts'][0]],
                        original['artifacts'][:-1] + [original['artifacts'][0]]):
            document = {**original, 'artifacts': entries}
            with self.assertRaises(receipt.ReceiptError):
                receipt.validate_consumer_receipt(document)

    def test_rejects_path_coordinate_and_digest_substitution(self):
        for field, value in (('relativePath', '../escape'), ('relativePath', 'https://repo.maven.apache.org/x'),
                             ('module', 'routecontract-other'), ('name', 'x.jar'), ('name', None),
                             ('sha256', 'A'*64), ('sha256', 'a'*63), ('unknown', 'extra')):
            document = valid_receipt()
            document['artifacts'][0][field] = value
            with self.subTest(field=field), self.assertRaises(receipt.ReceiptError):
                receipt.validate_consumer_receipt(document)

    def test_loads_regular_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            path.write_text(json.dumps(valid_receipt()), encoding='utf-8')
            self.assertEqual(valid_receipt(), receipt.load_consumer_receipt(path))

    def test_rejects_ambiguous_invalid_and_oversized_json(self):
        for payload in (b'{"formatVersion":1,"formatVersion":1}', b'{"a":NaN}', b'\xff', b'{', b' ',
                        b' '*(receipt.MAX_RECEIPT_BYTES+1), b'['*2000, b'{"n":' + b'1'*5000 + b'}'):
            with self.subTest(payload=payload[:30]), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'receipt.json'
                path.write_bytes(payload)
                with self.assertRaises(receipt.ReceiptError):
                    receipt.load_consumer_receipt(path)

    def test_rejects_symlink_and_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            path.write_text(json.dumps(valid_receipt()), encoding='utf-8')
            linked = Path(directory) / 'linked.json'
            linked.symlink_to(path)
            for candidate in (linked, Path(directory), path.with_name('absent')):
                with self.subTest(path=candidate), self.assertRaises(receipt.ReceiptError):
                    receipt.load_consumer_receipt(candidate)


if __name__ == '__main__':
    unittest.main()
