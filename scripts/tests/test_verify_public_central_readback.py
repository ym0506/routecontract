import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

SPEC = importlib.util.spec_from_file_location('public_central_readback', Path(__file__).parents[1] / 'verify-public-central-readback.py')
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
                name = f'{module}-0.2.0{suffix}'
                path = f'{readback.artifacts.GROUP_PATH}/{module}/0.2.0/{name}'
                for sidecar in ('', '.asc', '.md5', '.sha1', '.sha256', '.sha512'):
                    content = ('synthetic unit fixture: ' + path + sidecar).encode()
                    record = {'path': path + sidecar, 'size': len(content),
                              'sha256': hashlib.sha256(content).hexdigest(),
                              'kind': 'payload' if not sidecar else 'signature' if sidecar == '.asc' else 'payloadChecksum'}
                    entries.append(record)
                    archive.writestr(record['path'], content)
    archive_bytes = data.getvalue()
    return readback.VerifiedSnapshot('0.2.0', hashlib.sha256(archive_bytes).hexdigest(),
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

    def test_synthetic_exact_90_files_create_nine_payload_receipt(self):
        code, summary, consumer, requests = self.execute()
        self.assertEqual(0, code)
        self.assertEqual(90, summary['verifiedEntryCount'])
        self.assertTrue(summary['publicReadbackVerified'])
        self.assertFalse(summary['availabilityClaim'])
        self.assertFalse(summary['consumerExecutionVerified'])
        self.assertEqual(9, len(consumer['artifacts']))
        self.assertEqual(90, len(requests))
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


if __name__ == '__main__':
    unittest.main()
