"""Acceptance tests for group-isolated local staged Maven consumption."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

SPEC = importlib.util.spec_from_file_location(
    'staged_maven_repository', Path(__file__).parents[1] / 'staged_maven_repository.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RemoteResponse(io.BytesIO):
    def __init__(self, body=b'central-bytes', url=MODULE.CENTRAL_ORIGIN + '/maven2/org/example/a/1/a-1.jar',
                 length=None):
        super().__init__(body)
        self.url = url
        self.status = 200
        self.headers = {'Content-Length': str(len(body) if length is None else length)}

    def geturl(self):
        return self.url


class StagedMavenRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / 'repository'
        self.repository.mkdir()
        self.log = self.root / 'requests.jsonl'
        self.path = 'io/github/ym0506/routecontract/routecontract-core/0.2.0/routecontract-core-0.2.0.jar'
        self.artifact = self.repository / self.path
        self.artifact.parent.mkdir(parents=True)
        self.artifact.write_bytes(b'exact-staged-jar')

    def request(self, base, path, method='GET', headers=None):
        request = urllib.request.Request(base + path, method=method, headers=headers or {})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=5) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def records(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_staged_artifact_and_checksum_are_exact_for_get_and_head(self):
        checksum = self.artifact.with_name(self.artifact.name + '.sha256')
        checksum.write_bytes(b'fixture-checksum')
        with patch.object(MODULE, '_open_central') as remote:
            with MODULE.serve_repository(self.repository, self.log) as base:
                self.assertTrue(base.startswith('http://127.0.0.1:'))
                status, body, _ = self.request(base, self.path)
                self.assertEqual((200, b'exact-staged-jar'), (status, body))
                status, body, headers = self.request(base, self.path, 'HEAD')
                self.assertEqual((200, b''), (status, body))
                self.assertEqual(str(len(b'exact-staged-jar')), headers['Content-Length'])
                self.assertEqual((200, b'fixture-checksum'), self.request(base, self.path + '.sha256')[:2])
            remote.assert_not_called()
        self.assertEqual([{'method': 'GET', 'path': self.path, 'route': 'staged', 'status': 200},
                          {'method': 'HEAD', 'path': self.path, 'route': 'staged', 'status': 200},
                          {'method': 'GET', 'path': self.path + '.sha256', 'route': 'staged', 'status': 200}], self.records())

    def test_missing_first_party_never_falls_back_to_central(self):
        with patch.object(MODULE, '_open_central') as remote:
            with MODULE.serve_repository(self.repository, self.log) as base:
                self.assertEqual(404, self.request(base, self.path + '.missing')[0])
                self.assertEqual(404, self.request(base, self.path + '.missing', 'HEAD')[0])
            remote.assert_not_called()
        self.assertTrue(all(record['route'] == 'staged' and record['status'] == 404 for record in self.records()))

    def test_traversal_encoded_separators_queries_and_symlinks_are_rejected(self):
        linked = self.artifact.with_name('linked.jar')
        linked.symlink_to(self.artifact)
        directory_link = self.repository / 'io/github/ym0506/routecontract/linked'
        directory_link.symlink_to(self.artifact.parent, target_is_directory=True)
        invalid = [
            'io/github/ym0506/routecontract/../outside.jar',
            'io/github/ym0506/routecontract/%2e%2e/outside.jar',
            'io/github/ym0506/routecontract/%252e%252e/outside.jar',
            'io/github/ym0506/routecontract/%2f..%2foutside.jar',
            'io/github/ym0506/routecontract/a%5cb.jar',
            self.path + '?token=private-query-value',
        ]
        with patch.object(MODULE, '_open_central') as remote:
            with MODULE.serve_repository(self.repository, self.log) as base:
                for path in invalid:
                    self.assertEqual(400, self.request(base, path)[0], path)
                self.assertEqual(404, self.request(base, linked.relative_to(self.repository).as_posix())[0])
                self.assertEqual(404, self.request(base,
                    directory_link.relative_to(self.repository).as_posix() + '/' + self.artifact.name)[0])
            remote.assert_not_called()
        self.assertNotIn('private-query-value', self.log.read_text())

    def test_third_party_uses_only_fixed_central_and_forwards_no_credentials(self):
        target = 'org/example/a/1/a-1.jar'
        seen = []

        def remote(request):
            seen.append(request)
            return RemoteResponse(url=MODULE.CENTRAL_ORIGIN + '/maven2/' + target)

        with patch.object(MODULE, '_open_central', side_effect=remote):
            with MODULE.serve_repository(self.repository, self.log) as base:
                self.assertEqual((200, b'central-bytes'), self.request(base, target, headers={
                    'Authorization': 'Bearer private-credential', 'Cookie': 'private-cookie',
                    'Proxy-Authorization': 'Basic private-proxy'})[:2])
                self.assertEqual((200, b''), self.request(base, target, 'HEAD')[:2])
        self.assertEqual(['GET', 'HEAD'], [request.get_method() for request in seen])
        for request in seen:
            self.assertEqual(MODULE.CENTRAL_ORIGIN + '/maven2/' + target, request.full_url)
            self.assertFalse(any(name.lower() in ('authorization', 'cookie', 'proxy-authorization')
                                 for name, _ in request.header_items()))
        self.assertNotIn('private-', self.log.read_text())
        self.assertEqual([{'method': method, 'path': target, 'route': 'central', 'status': 200}
                          for method in ('GET', 'HEAD')], self.records())

    def test_off_origin_redirect_and_response_url_are_rejected(self):
        handler = MODULE.CentralRedirectHandler()
        original = urllib.request.Request(MODULE.CENTRAL_ORIGIN + '/maven2/org/example/a.jar')
        for destination in ['https://example.invalid/a.jar', 'http://repo.maven.apache.org/maven2/a.jar',
                            'https://user:password@repo.maven.apache.org/maven2/a.jar',
                            'https://repo.maven.apache.org:444/maven2/a.jar',
                            'https://repo.maven.apache.org/outside/a.jar',
                            MODULE.CENTRAL_PREFIX + self.path]:
            with self.assertRaises(MODULE.RepositoryError):
                handler.redirect_request(original, None, 302, 'Found', {}, destination)
        with patch.object(MODULE, '_open_central', return_value=RemoteResponse(url='https://example.invalid/a.jar')):
            with MODULE.serve_repository(self.repository, self.log) as base:
                self.assertEqual(502, self.request(base, 'org/example/a.jar')[0])
        self.assertEqual(502, self.records()[0]['status'])

    def test_allowed_redirect_removes_credentials_and_keeps_head_method(self):
        request = urllib.request.Request(MODULE.CENTRAL_PREFIX + 'org/example/old.jar', method='HEAD',
                                         headers={'Authorization': 'private', 'Cookie': 'private'})
        redirected = MODULE.CentralRedirectHandler().redirect_request(
            request, None, 302, 'Found', {}, MODULE.CENTRAL_PREFIX + 'org/example/new.jar')
        self.assertEqual('HEAD', redirected.get_method())
        self.assertFalse(any(key.lower() in ('authorization', 'cookie') for key, _ in redirected.header_items()))

    def test_transfer_deadline_is_bounded_and_logged(self):
        with patch.object(MODULE, 'UPSTREAM_TOTAL_SECONDS', 0):
            with patch.object(MODULE, '_open_central', return_value=RemoteResponse()):
                with MODULE.serve_repository(self.repository, self.log) as base:
                    self.assertEqual(504, self.request(base, 'org/example/a.jar')[0])
        self.assertEqual(504, self.records()[0]['status'])

    def test_slow_progress_uses_single_reads_and_cannot_extend_transfer_indefinitely(self):
        clock = [0]

        class SlowResponse(RemoteResponse):
            calls = 0

            def read(self, size=-1):
                raise AssertionError('Accumulating read(n) can defeat the transfer deadline')

            def read1(self, size=-1):
                self.calls += 1
                clock[0] += 60
                return b'x'

        response = SlowResponse(body=b'xxx')
        with patch.object(MODULE, 'time', SimpleNamespace(monotonic=lambda: clock[0])):
            with patch.object(MODULE, '_open_central', return_value=response):
                with MODULE.serve_repository(self.repository, self.log) as base:
                    self.assertEqual((504, b''), self.request(base, 'org/example/a.jar')[:2])
        self.assertEqual(2, response.calls)
        self.assertEqual(504, self.records()[0]['status'])

    def test_oversized_central_content_and_missing_content_length_cannot_bypass_limit(self):
        with patch.object(MODULE, 'MAX_BODY_BYTES', 4):
            with MODULE.serve_repository(self.repository, self.log) as base:
                with patch.object(MODULE, '_open_central', return_value=RemoteResponse(body=b'12345')):
                    self.assertEqual(413, self.request(base, 'org/example/a.jar')[0])
                response = RemoteResponse(body=b'12345')
                response.headers = {}
                with patch.object(MODULE, '_open_central', return_value=response):
                    self.assertEqual(413, self.request(base, 'org/example/a.jar')[0])

    def test_upstream_errors_preserve_status_and_log_without_response_body(self):
        failure = urllib.error.HTTPError(MODULE.CENTRAL_ORIGIN + '/maven2/org/example/missing.jar',
                                         404, 'private error detail', {}, io.BytesIO(b'private response'))
        with patch.object(MODULE, '_open_central', side_effect=failure):
            with MODULE.serve_repository(self.repository, self.log) as base:
                self.assertEqual((404, b''), self.request(base, 'org/example/missing.jar')[:2])
        self.assertEqual([{'method': 'GET', 'path': 'org/example/missing.jar', 'route': 'central', 'status': 404}], self.records())
        self.assertNotIn('private', self.log.read_text())

    def test_request_log_survives_caller_failure_and_server_stops(self):
        with self.assertRaisesRegex(RuntimeError, 'caller failed'):
            with MODULE.serve_repository(self.repository, self.log) as base:
                self.assertEqual(200, self.request(base, self.path)[0])
                raise RuntimeError('caller failed')
        self.assertEqual(1, len(self.records()))
        with self.assertRaises(urllib.error.URLError):
            self.request(base, self.path)


if __name__ == '__main__':
    unittest.main()
