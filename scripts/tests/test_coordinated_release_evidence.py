"""Acceptance for split preparation without changing historical release meaning."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import hashlib
import json
import stat
import zipfile
from unittest import mock
import unittest

ROOT = Path(__file__).resolve().parents[2]

def module():
    path = ROOT / 'scripts/prepare-coordinated-release-evidence.py'
    spec = importlib.util.spec_from_file_location('coordinated_release_evidence', path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value

class CoordinatedReleaseAcceptanceTest(unittest.TestCase):
    def test_stable_split_dispatch_and_historical_separation(self):
        tool = module()
        self.assertEqual('split', tool.release_family('0.2.0'))
        self.assertEqual('legacy', tool.release_family('0.1.3'))
        self.assertEqual('legacy', tool.release_family('0.1.0-rc2'))
        for value in ('0.2.0-rc1', '0.2.00', '0.3.0', '2.0.0', '../0.2.0'):
            with self.subTest(value=value), self.assertRaises(tool.PreparationError):
                tool.release_family(value)

    def test_closed_fifteen_payloads_never_accept_historical_five(self):
        tool = module()
        paths = tool.payload_paths('0.2.0')
        self.assertEqual(15, len(paths))
        self.assertEqual(3, len({p.split('/')[-3] for p in paths}))
        self.assertTrue(all(name.startswith('io/github/ym0506/routecontract/') for name in paths))

    def test_incomplete_repository_cannot_emit_complete_receipt(self):
        tool = module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(tool.PreparationError):
                tool.inspect_payloads(root, ROOT, '0.2.0', release_javadoc=False)
            self.assertEqual([], list(root.iterdir()))

    def test_workflow_keeps_hold_and_dispatches_split_preparation(self):
        text = (ROOT / '.github/workflows/release-evidence.yml').read_text()
        self.assertIn('prepare-coordinated-release-evidence.py collect', text)
        self.assertIn('prepare-coordinated-release-evidence.py verify', text)
        self.assertIn("steps.release_family.outputs.family == 'legacy'", text)
        self.assertIn('0.2 publication is blocked:', text)
        self.assertIn('exit 1', text[text.index('0.2 publication is blocked:'):])
        self.assertIn('verify-release-assets-consumer.sh', text)


    def test_legacy_cli_cannot_enter_split_collector(self):
        tool = module()
        with mock.patch('sys.stderr'):
            self.assertEqual(1, tool.main(['inspect-payloads', '--source-root', str(ROOT), '--version', '0.1.3', '--repository', str(ROOT)]))

    def test_missing_release_jdk_rejects_without_output(self):
        tool=module()
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve(); output=root/'output'
            with mock.patch.object(tool,'source_identity',return_value={'revision':'1'*40,'tree':'2'*40}):
                with self.assertRaises(tool.PreparationError):
                    tool.collect(root/'repository',ROOT,'0.2.0','1'*40,root/'missing-jdk',output)
            self.assertFalse(output.exists())

    def test_other_java17_vendor_does_not_satisfy_release_toolchain(self):
        tool=module()
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve()
            (root/'release').write_text('IMPLEMENTOR_VERSION="Homebrew"\nJAVA_RUNTIME_VERSION="17.0.15"\n')
            with self.assertRaisesRegex(tool.PreparationError,'exact Temurin'):
                tool.verify_toolchain(root)

    def test_duplicate_java_release_identity_is_rejected(self):
        tool=module()
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve()
            (root/'release').write_text('IMPLEMENTOR_VERSION="Temurin-17.0.20.1+1"\n'*2+'JAVA_RUNTIME_VERSION="17.0.20.1+1"\n')
            with self.assertRaises(tool.PreparationError):tool.verify_toolchain(root)

    def test_invalid_release_javadoc_module_is_rejected(self):
        tool=module()
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve(); (root/'jmods').mkdir()
            (root/'release').write_text('IMPLEMENTOR_VERSION="Temurin-17.0.20.1+1"\nJAVA_RUNTIME_VERSION="17.0.20.1+1"\n')
            (root/'jmods/jdk.javadoc.jmod').write_bytes(b'unreviewed module')
            result=type('Result',(),{'stdout':b'openjdk full version "17.0.20.1+1"\n'})()
            with mock.patch.object(tool.subprocess,'run',return_value=result):
                with self.assertRaisesRegex(tool.PreparationError,'Javadoc module'):tool.verify_toolchain(root)

    def test_read_rejects_symlink_and_hardlink_inputs(self):
        tool=module()
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve(); original=root/'original'; original.write_bytes(b'payload')
            link=root/'link';link.symlink_to(original)
            with self.assertRaises(tool.PreparationError):tool.read(link)
            link.unlink();link.hardlink_to(original)
            with self.assertRaises(tool.PreparationError):tool.read(link)

    def test_archive_rejects_traversal_duplicate_and_special_entries(self):
        tool=module()
        for mode in ('traversal','duplicate','symlink'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as raw:
                path=Path(raw).resolve()/'input.jar'
                with zipfile.ZipFile(path,'w') as z:
                    z.writestr('META-INF/LICENSE','license');z.writestr('META-INF/NOTICE','notice')
                    if mode=='traversal':z.writestr('../escape','payload')
                    elif mode=='duplicate':
                        z.writestr('same','one')
                        with __import__('warnings').catch_warnings():
                            __import__('warnings').simplefilter('ignore');z.writestr('same','two')
                    else:
                        info=zipfile.ZipInfo('linked');info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'target')
                with self.assertRaises((tool.PreparationError,tool.ARCHIVE.InstallError)):tool.jar_contents(path)

    def test_unsigned_inventory_rejects_extra_file_before_metadata_validation(self):
        tool=module()
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve();(root/'unrelated').write_bytes(b'payload')
            with self.assertRaisesRegex(tool.PreparationError,'exactly 15'):
                tool.inspect_payloads(root,ROOT,'0.2.0',release_javadoc=False)

    def validated_writer_inputs(self,tool):
        # This tests the output/receipt boundary only; semantic payload validation
        # is deliberately replaced with a prevalidated input object in these cells.
        contents={p:('fixture '+p).encode() for p in tool.payload_paths('0.2.0')}
        payloads=[{'artifactId':p.split('/')[-3],'name':p.split('/')[-1],'size':len(b),'sha256':tool.sha(b)} for p,b in contents.items()]
        inspected={'payloads':payloads,'contents':contents,'consumerReceipt':{'fixture':'prevalidated for writer unit only'}}
        return ({'revision':'1'*40,'tree':'2'*40},{'runtime':'unit-only'},inspected,{'test-summary.txt':b'unit-only'})

    def test_output_receipt_remains_unsigned_unreviewed_and_held(self):
        tool=module()
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve();output=root/'output'
            with mock.patch.object(tool,'evidence_inputs',return_value=self.validated_writer_inputs(tool)):
                tool.collect(root/'repository',ROOT,'0.2.0','1'*40,root,output)
                receipt=json.loads((output/'candidate-payloads.json').read_text())
                self.assertEqual(2,receipt['formatVersion']);self.assertEqual(15,len(receipt['payloads']))
                self.assertIs(False,receipt['reviewed']);self.assertIs(False,receipt['signed']);self.assertIs(False,receipt['published']);self.assertIs(True,receipt['publicationHeld'])
                with self.assertRaises(tool.PreparationError):tool.collect(root/'repository',ROOT,'0.2.0','1'*40,root,output)

    def test_final_inspection_rejects_changed_missing_extra_and_relabelled_output(self):
        tool=module()
        for mode in ('changed','missing','extra','historical-format','approval'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as raw:
                root=Path(raw).resolve();output=root/'output'
                with mock.patch.object(tool,'evidence_inputs',return_value=self.validated_writer_inputs(tool)):
                    tool.collect(root/'repository',ROOT,'0.2.0','1'*40,root,output)
                    path=output/'evidence/test-summary.txt'
                    if mode=='changed':path.write_bytes(b'changed')
                    elif mode=='missing':path.unlink()
                    elif mode=='extra':(output/'extra').write_bytes(b'unexpected')
                    else:
                        receipt=json.loads((output/'candidate-payloads.json').read_text())
                        receipt['formatVersion' if mode=='historical-format' else 'reviewed']=1 if mode=='historical-format' else True
                        (output/'candidate-payloads.json').write_bytes(tool.canonical(receipt))
                    with self.assertRaises(tool.PreparationError):tool.verify(output,ROOT,'0.2.0','1'*40,root)

    def test_reinspection_detects_changed_underlying_evidence(self):
        tool=module()
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve();output=root/'output';inputs=self.validated_writer_inputs(tool)
            with mock.patch.object(tool,'evidence_inputs',return_value=inputs):tool.collect(root/'repository',ROOT,'0.2.0','1'*40,root,output)
            changed=(*inputs[:3],{'test-summary.txt':b'new evidence'})
            with mock.patch.object(tool,'evidence_inputs',return_value=changed):
                with self.assertRaises(tool.PreparationError):tool.verify(output,ROOT,'0.2.0','1'*40,root)

    def test_workflow_split_consumers_use_retained_repository_and_recheck(self):
        text=(ROOT/'.github/workflows/release-evidence.yml').read_text()
        block=text.split('      - name: Verify retained split preparation through independent MySQL consumers\n',1)[1].split('\n      - name:',1)[0]
        self.assertIn('build/central-candidate-evidence/repository',block)
        self.assertIn('verify-staged-split-artifact-consumer.py',block)
        self.assertIn('verify-staged-maven-artifact-consumer.py',block)
        self.assertIn('prepare-coordinated-release-evidence.py verify',block)
        self.assertNotIn('install-release-assets.py',block)
        self.assertNotIn('continue-on-error',block)

    def test_class_identity_is_read_from_constant_pool(self):
        tool=module();name='io/github/ym0506/routecontract/api/RouteContract'
        def utf8(value):
            encoded=value.encode();return b'\x01'+len(encoded).to_bytes(2,'big')+encoded
        payload=(b'\xca\xfe\xba\xbe\x00\x00\x00\x3d\x00\x05'+utf8(name)+b'\x07\x00\x01'+
                 utf8('java/lang/Object')+b'\x07\x00\x03'+b'\x00\x21\x00\x02\x00\x04'+b'\x00\x00'*4)
        self.assertEqual(name,tool.class_binary_name(payload))
        for bad in (payload[:-1],payload+b'extra',payload[:7]+b'\x34'+payload[8:]):
            with self.assertRaises(tool.PreparationError):tool.class_binary_name(bad)

    def test_output_cannot_mutate_input_repository(self):
        tool=module()
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve()
            with mock.patch.object(tool,'evidence_inputs') as inputs:
                with self.assertRaisesRegex(tool.PreparationError,'overlap'):
                    tool.collect(root,ROOT,'0.2.0','1'*40,root,root/'nested')
                inputs.assert_not_called()
            self.assertFalse((root/'nested').exists())

if __name__ == '__main__':
    unittest.main()
