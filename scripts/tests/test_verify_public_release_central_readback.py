import hashlib
import importlib.util
import io
import json
from email.message import Message
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

SPEC = importlib.util.spec_from_file_location('public_release_central_readback', Path(__file__).parents[1] / 'verify-public-release-central-readback.py')
readback = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = readback
SPEC.loader.exec_module(readback)


def synthetic_snapshot():
    entries = []
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        for module in readback.artifacts.MODULES:
            for extension in ('jar', 'pom', 'module', 'sources.jar', 'javadoc.jar'):
                suffix = '-' + extension if extension in ('sources.jar', 'javadoc.jar') else '.' + extension
                name = f'{module}-0.1.3{suffix}'
                path = f'{readback.artifacts.GROUP_PATH}/{module}/0.1.3/{name}'
                for sidecar in ('', '.asc', '.md5', '.sha1', '.sha256', '.sha512'):
                    content = ('synthetic unit fixture: ' + path + sidecar).encode()
                    record = {'path': path + sidecar, 'size': len(content),
                              'sha256': hashlib.sha256(content).hexdigest(),
                              'kind': 'payload' if not sidecar else 'signature' if sidecar == '.asc' else 'payloadChecksum'}
                    entries.append(record)
                    archive.writestr(record['path'], content)
    archive_bytes = data.getvalue()
    return readback.VerifiedSnapshot('0.1.3', hashlib.sha256(archive_bytes).hexdigest(),
                                    'b'*64, 'c'*64, 'D'*40, archive_bytes, tuple(entries))


class Response(io.BytesIO):
    status = 200

    def __init__(self, content, url, headers=None):
        super().__init__(content)
        self.url = url
        self.headers = {'Content-Length': str(len(content))} if headers is None else headers

    def geturl(self):
        return self.url


class FakeCentral:
    def __init__(self, snapshot, failure=None):
        self.archive = zipfile.ZipFile(io.BytesIO(snapshot.bundle_bytes))
        self.requests = []
        self.failure = failure

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        path = request.full_url.removeprefix(readback.artifacts.CENTRAL_ROOT)
        content = self.archive.read(path)
        if self.failure and len(self.requests) == 2:
            return self.failure(content, request.full_url)
        return Response(content, request.full_url)


class PublicReadbackTest(unittest.TestCase):
    def execute(self, failure=None):
        snapshot = synthetic_snapshot()
        transport = FakeCentral(snapshot, failure)
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory).resolve() / 'evidence'
            code = readback.readback(snapshot, evidence, opener=transport)
            summary = json.loads((evidence / 'public-readback.json').read_text())
            consumer = evidence / 'consumer-receipt.json'
            value = readback.artifacts.load_consumer_receipt(consumer) if consumer.exists() else None
        return code, summary, value, transport.requests

    def test_synthetic_exact_30_files_create_three_payload_receipt(self):
        code, summary, consumer, requests = self.execute()
        self.assertEqual(0, code)
        self.assertEqual(30, summary['verifiedEntryCount'])
        self.assertTrue(summary['publicReadbackVerified'])
        self.assertFalse(summary['availabilityClaim'])
        self.assertFalse(summary['consumerExecutionVerified'])
        self.assertEqual(3, len(consumer['artifacts']))
        self.assertEqual(30, len(requests))
        for request, timeout in requests:
            self.assertTrue(request.full_url.startswith(readback.artifacts.CENTRAL_ROOT))
            self.assertEqual('GET', request.get_method())
            self.assertIsNone(request.data)
            self.assertEqual({'Accept-encoding': 'identity', 'User-agent': 'RouteContract-public-readback/1'}, dict(request.header_items()))
            self.assertLessEqual(timeout, readback.REQUEST_TIMEOUT_SECONDS)

    def test_missing_file_retains_partial_failure_without_consumer_receipt(self):
        def missing(content, url):
            raise urllib.error.HTTPError(url, 404, 'do not copy server text', {}, None)
        code, summary, consumer, requests = self.execute(missing)
        self.assertEqual(2, code)
        self.assertEqual('HTTP_404', summary['failureCode'])
        self.assertEqual(1, summary['verifiedEntryCount'])
        self.assertFalse(summary['publicReadbackVerified'])
        self.assertIsNone(consumer)
        self.assertEqual(2, len(requests))
        self.assertNotIn('do not copy', json.dumps(summary))

    def test_rejects_changed_truncated_oversized_encoded_and_redirected_bytes(self):
        failures = [
            ('BYTE_MISMATCH', lambda data, url: Response(b'X' + data[1:], url)),
            ('SIZE_MISMATCH', lambda data, url: Response(data[:-1], url)),
            ('SIZE_MISMATCH', lambda data, url: Response(data + b'X', url)),
            ('SIZE_MISMATCH', lambda data, url: Response(data + b'X', url, {})),
            ('CONTENT_ENCODING', lambda data, url: Response(data, url, {'Content-Encoding': 'gzip'})),
            ('UNEXPECTED_ORIGIN', lambda data, url: Response(data, 'https://example.invalid/private')),
            ('CONTENT_LENGTH', lambda data, url: Response(data, url, {'Content-Length': 'invalid'})),
        ]
        for expected, failure in failures:
            with self.subTest(expected=expected):
                code, summary, consumer, requests = self.execute(failure)
                self.assertEqual(2, code)
                self.assertEqual(expected, summary['failureCode'])
                self.assertIsNone(consumer)
                self.assertEqual(2, len(requests))

    def test_rejects_transport_error_without_echoing_private_message(self):
        def timeout(content, url):
            raise urllib.error.URLError('potential private connection detail')
        code, summary, consumer, _ = self.execute(timeout)
        self.assertEqual('TRANSPORT_ERROR', summary['failureCode'])
        self.assertNotIn('private connection', json.dumps(summary))
        self.assertIsNone(consumer)

    def test_rejects_duplicate_body_headers_in_real_http_message(self):
        for name, first, second in (
                ('Content-Encoding', 'identity', 'gzip'),
                ('Content-Encoding', 'identity', 'identity'),
                ('Content-Length', '3', '999'),
                ('Content-Length', '3', '3')):
            def duplicate_headers(data, url):
                headers = Message()
                headers[name] = first if name != 'Content-Length' else str(len(data))
                headers[name] = second
                return Response(data, url, headers)
            with self.subTest(name=name, second=second):
                code, summary, consumer, _ = self.execute(duplicate_headers)
                self.assertEqual(2, code)
                self.assertEqual('AMBIGUOUS_BODY_HEADERS', summary['failureCode'])
                self.assertIsNone(consumer)

    def test_no_redirect_and_no_environment_proxy_handlers(self):
        with patch.dict('os.environ', {'HTTPS_PROXY': 'http://user:secret@example.invalid:80'}):
            opener = readback.central_opener()
        proxies = [handler for handler in opener.handlers if isinstance(handler, readback.urllib.request.ProxyHandler)]
        self.assertTrue(all(handler.proxies == {} for handler in proxies))
        redirect = next(handler for handler in opener.handlers if isinstance(handler, readback.NoRedirect))
        with self.assertRaises(readback.ReadbackError) as caught:
            redirect.redirect_request(None, None, 302, 'ignored', {}, 'https://example.invalid')
        self.assertEqual('REDIRECT_REJECTED', caught.exception.code)

    def test_expired_deadline_stops_before_network(self):
        snapshot = synthetic_snapshot()
        transport = FakeCentral(snapshot)
        with tempfile.TemporaryDirectory() as directory, patch.object(readback, 'TOTAL_TIMEOUT_SECONDS', 0):
            evidence = Path(directory).resolve() / 'evidence'
            self.assertEqual(2, readback.readback(snapshot, evidence, opener=transport))
            summary = json.loads((evidence / 'public-readback.json').read_text())
            self.assertEqual('DEADLINE_EXCEEDED', summary['failureCode'])
            self.assertEqual([], transport.requests)

    def test_existing_evidence_is_not_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory).resolve()
            with self.assertRaises(readback.ReadbackError):
                readback.readback(synthetic_snapshot(), evidence, opener=FakeCentral(synthetic_snapshot()))
            self.assertEqual([], list(evidence.iterdir()))

    def test_slow_body_rechecks_budget_between_single_reads(self):
        class SlowResponse(Response):
            def read(self, count):
                raise AssertionError('A filling read would bypass the checked deadline')

            def read1(self, count):
                return io.BytesIO.read(self, 1)

        class SlowTransport:
            def open(self, request, timeout):
                return SlowResponse(b'a'*20, request.full_url)

        with patch.object(readback.time, 'monotonic', side_effect=[0, 1, 2, 3, 4, 5]):
            with self.assertRaises(readback.ReadbackError) as caught:
                readback._verify_response(SlowTransport(), 'synthetic-unit-only', b'a'*20, 4)
        self.assertEqual('DEADLINE_EXCEEDED', caught.exception.code)


@unittest.skipUnless(shutil.which('gpg'), 'GnuPG is required for the genuine signed fixture')
class SignedLocalInputReadbackTest(unittest.TestCase):
    """Real schema-1 verification; only HTTP responses are synthetic."""

    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name('fixtures') / 'central_schema1.py'
        spec = importlib.util.spec_from_file_location('release_readback_signed_fixture', path)
        cls.fixtures = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.fixtures
        spec.loader.exec_module(cls.fixtures)
        cls.fixtures.SchemaOneSignedFixture.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.fixtures.SchemaOneSignedFixture.tearDownClass()

    def setUp(self):
        self.fixture = self.fixtures.SchemaOneSignedFixture()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.built = self.fixture.build()

    def inputs(self):
        return dict(repository=self.fixture.repository, bundle=self.built.bundle_path,
                    receipt=self.built.receipt_path, reviewed_payload_manifest=self.fixture.manifest,
                    public_gpg_home=self.fixture.public_home,
                    expected_primary_fingerprint=self.fixture.fingerprint)

    def test_genuine_signed_bundle_verifies_before_synthetic_thirty_file_readback(self):
        with patch.object(readback.bundle_tool, 'verify_bundle', wraps=readback.bundle_tool.verify_bundle) as verifier:
            snapshot = readback.verified_snapshot(**self.inputs())
        verifier.assert_called_once()
        self.assertEqual('0.1.3', snapshot.version)
        self.assertEqual(30, len(snapshot.entries))
        self.assertEqual(5, sum(record['kind'] == 'signature' for record in snapshot.entries))
        self.assertEqual(self.fixture.fingerprint, snapshot.fingerprint)
        self.assertEqual(hashlib.sha256(self.fixture.manifest.read_bytes()).hexdigest(), snapshot.manifest_sha256)
        evidence = self.fixture.root / 'synthetic-http-evidence'
        transport = FakeCentral(snapshot)
        self.assertEqual(0, readback.readback(snapshot, evidence, opener=transport))
        consumer = readback.artifacts.load_consumer_receipt(evidence / 'consumer-receipt.json')
        self.assertEqual(3, len(consumer['artifacts']))
        for record in consumer['artifacts']:
            local_bytes = (self.fixture.repository / record['relativePath']).read_bytes()
            self.assertEqual(hashlib.sha256(local_bytes).hexdigest(), record['sha256'])
        summary = json.loads((evidence / 'public-readback.json').read_text())
        self.assertEqual(30, summary['verifiedEntryCount'])
        self.assertFalse(summary['availabilityClaim'])
        self.assertFalse(summary['consumerExecutionVerified'])
        self.assertFalse(summary['networkPublication'])

    def test_signed_schema_one_receipt_preserves_published_tool_binding(self):
        receipt = json.loads(self.built.receipt_path.read_text())
        self.assertEqual(1, receipt['schemaVersion'])
        self.assertEqual({
            'name': 'prepare-central-upload-bundle.py',
            'sha256': '87f60774cbcdbf2eb75884621875487b4673c073de933f73670d405c8cbf4df3',
        }, receipt['tool'])
        snapshot = readback.verified_snapshot(**self.inputs())
        self.assertEqual(hashlib.sha256(self.built.receipt_path.read_bytes()).hexdigest(),
                         snapshot.receipt_sha256)

    def test_schema_two_manifest_cannot_enter_the_schema_one_readback(self):
        manifest = json.loads(self.fixture.manifest.read_text())
        manifest['schemaVersion'] = 2
        self.fixture.write_manifest(manifest)
        with self.assertRaises(readback.bundle_tool.BundleError):
            readback.verified_snapshot(**self.inputs())

    def test_corrupt_signature_is_rejected_by_real_signature_verifier(self):
        signature = next(self.fixture.repository.rglob('*.jar.asc'))
        original = signature.read_bytes()
        lines = original.splitlines(keepends=True)
        body = next(index for index, line in enumerate(lines)
                    if line and line[:1] not in (b'-', b'\n', b'\r') and b':' not in line)
        lines[body] = (b'B' if lines[body][:1] == b'A' else b'A') + lines[body][1:]
        changed = b''.join(lines)
        self.assertNotEqual(original, changed)
        signature.write_bytes(changed)
        for algorithm in self.fixtures.CHECKSUMS:
            signature.with_name(signature.name + '.' + algorithm).write_text(
                self.fixtures.digest(changed, algorithm), encoding='ascii')
        with patch.object(readback.bundle_tool, '_verify_signature', wraps=readback.bundle_tool._verify_signature) as verifier:
            with self.assertRaises(readback.bundle_tool.BundleError):
                readback.verified_snapshot(**self.inputs())
        self.assertGreaterEqual(verifier.call_count, 1)

    def test_mutation_after_real_verification_cannot_change_snapshot(self):
        real_verify = readback.bundle_tool.verify_bundle
        for field in ('bundle', 'receipt'):
            target = self.inputs()[field]
            original = target.read_bytes()
            def mutate_after_verification(**kwargs):
                result = real_verify(**kwargs)
                target.write_bytes(original + b'\n')
                return result
            with self.subTest(field=field), patch.object(readback.bundle_tool, 'verify_bundle', side_effect=mutate_after_verification):
                with self.assertRaises(readback.ReadbackError) as caught:
                    readback.verified_snapshot(**self.inputs())
                self.assertEqual('LOCAL_INPUT_CHANGED', caught.exception.code)
            target.write_bytes(original)

    def test_invalid_local_bundle_stops_cli_before_transport_or_evidence(self):
        self.built.bundle_path.write_bytes(self.built.bundle_path.read_bytes() + b'changed')
        evidence = self.fixture.root / 'must-not-be-created'
        args = []
        for name, value in self.inputs().items():
            args.extend(['--' + name.replace('_', '-'), str(value)])
        args.extend(['--evidence-directory', str(evidence)])
        with patch.object(readback, 'central_opener') as opener, patch('sys.stderr', new=io.StringIO()):
            self.assertEqual(2, readback.main(args))
        opener.assert_not_called()
        self.assertFalse(evidence.exists())


if __name__ == '__main__':
    unittest.main()
