"""Fake-HTTP checks for the per-run Central response cache.

No Maven process, network, user repository cache, or real artifact is accessed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock
from urllib.request import Request


SCRIPT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))
SPEC = importlib.util.spec_from_file_location(
    'maven_legacy_central_cache_under_test', SCRIPT_ROOT / 'maven_legacy_central_cache.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
MIRROR = MODULE.mirror
RELATIVE = 'org/example/component/1/component-1.jar'
URL = MIRROR.CENTRAL_PREFIX + RELATIVE
BODY = b'central-response-verifier-bytes'


class FakeResponse(io.BytesIO):
    def __init__(self, body=BODY, *, url=URL, status=200, length='actual', before_read=None):
        super().__init__(body)
        self.url, self.status = url, status
        self.headers = {} if length is None else {'Content-Length': str(len(body) if length == 'actual' else length)}
        self.before_read = before_read

    def geturl(self):
        return self.url

    def read1(self, size):
        if self.before_read:
            self.before_read()
        return super().read1(size)


class CentralResponseCacheTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / 'central-responses'

    def cache(self, opener=None):
        opener = opener or mock.Mock(side_effect=lambda request: FakeResponse())
        return MODULE.CentralResponses(self.directory, opener), opener

    def read(self, cache, url=URL):
        with cache(Request(url)) as response:
            self.assertEqual(200, response.status)
            self.assertEqual(str(len(BODY)), response.headers['Content-Length'])
            return response.read1(100000)

    def assert_no_cached_payload(self, cache):
        self.assertEqual({}, cache.records)
        self.assertFalse((cache.directory / RELATIVE).exists())
        self.assertFalse(list(cache.directory.rglob('*.partial')))
        self.assertFalse((cache.directory / 'downloads.jsonl').exists())

    def test_second_get_reuses_verified_identical_bytes_and_records_download_provenance(self):
        cache, opener = self.cache()
        self.assertEqual(BODY, self.read(cache))
        self.assertEqual(BODY, self.read(cache))
        opener.assert_called_once()
        receipt = cache.receipt()
        self.assertTrue(receipt['initiallyAbsent'])
        self.assertEqual(1, len(receipt['responses']))
        entry = receipt['responses'][0]
        self.assertEqual((RELATIVE, URL, URL, 200, len(BODY), hashlib.sha256(BODY).hexdigest()),
                         tuple(entry[k] for k in ('relativePath', 'sourceUrl', 'finalUrl', 'status', 'byteCount', 'sha256')))
        self.assertEqual('downloaded-during-this-run', entry['source'])
        self.assertEqual(1, entry['cacheHits'], 'Only replayed responses count as cache hits')
        self.assertEqual(2, entry['responseDeliveries'])
        self.assertEqual(1, len((self.directory / 'downloads.jsonl').read_text().splitlines()))

    def test_same_url_concurrent_consumers_share_one_download(self):
        entered = threading.Event()
        second_started = threading.Event()
        release = threading.Event()
        def remote(request):
            entered.set()
            if not release.wait(2):
                raise AssertionError('Test did not release the fake download')
            return FakeResponse()
        opener = mock.Mock(side_effect=remote)
        cache, _ = self.cache(opener)
        def second():
            second_started.set()
            return self.read(cache)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.read, cache)
            try:
                self.assertTrue(entered.wait(2))
                other = pool.submit(second)
                self.assertTrue(second_started.wait(2))
            finally:
                release.set()
            self.assertEqual(BODY, first.result(timeout=2))
            self.assertEqual(BODY, other.result(timeout=2))
        opener.assert_called_once()
        self.assertEqual(1, len(cache.receipt()['responses']))

    def test_existing_directory_or_symlink_cannot_supply_a_seed(self):
        self.directory.mkdir()
        with self.assertRaises(MIRROR.RepositoryError):
            self.cache()
        self.directory.rmdir()
        outside = self.root / 'existing'; outside.mkdir()
        self.directory.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(MIRROR.RepositoryError):
            self.cache()

    def test_foreign_first_party_and_invalid_urls_never_reach_transport(self):
        cache, opener = self.cache()
        disallowed = [
            'https://foreign.invalid/maven2/' + RELATIVE,
            'http://repo.maven.apache.org/maven2/' + RELATIVE,
            'https://user:secret@repo.maven.apache.org/maven2/' + RELATIVE,
            'https://repo.maven.apache.org:444/maven2/' + RELATIVE,
            MIRROR.CENTRAL_PREFIX + 'io/github/ym0506/routecontract/core/1/core-1.jar',
            MIRROR.CENTRAL_PREFIX + '%69o/github/ym0506/routecontract/core/1/core-1.jar',
            MIRROR.CENTRAL_PREFIX + '../outside.jar',
            MIRROR.CENTRAL_PREFIX + 'org/%2e%2e/outside.jar',
            URL + '?token=not-a-real-secret',
        ]
        for url in disallowed:
            with self.subTest(url=url), self.assertRaises(MIRROR.RepositoryError):
                cache(Request(url))
        opener.assert_not_called()
        self.assert_no_cached_payload(cache)

    def test_write_methods_are_rejected_and_head_remains_uncached(self):
        cache, opener = self.cache()
        for method in ('POST', 'PUT', 'DELETE'):
            with self.subTest(method=method), self.assertRaises(MIRROR.RepositoryError):
                cache(Request(URL, method=method))
        opener.assert_not_called()
        request = Request(URL, method='HEAD')
        with cache(request) as response:
            self.assertEqual(URL, response.geturl())
        opener.assert_called_once_with(request)
        self.assert_no_cached_payload(cache)

    def test_non_200_and_disallowed_final_urls_cannot_seed_cache(self):
        cache, opener = self.cache()
        responses = [FakeResponse(status=404), FakeResponse(status=206),
                     FakeResponse(url='https://foreign.invalid/artifact.jar'),
                     FakeResponse(url=MIRROR.CENTRAL_PREFIX + 'io/github/ym0506/routecontract/core/1/core-1.jar')]
        for response in responses:
            opener.side_effect = None; opener.return_value = response
            with self.subTest(status=response.status, url=response.url), self.assertRaises(MIRROR.RepositoryError):
                cache(Request(URL))
            self.assert_no_cached_payload(cache)

    def test_permitted_central_redirect_retains_both_source_and_final_url(self):
        final_url = MIRROR.CENTRAL_PREFIX + 'org/example/moved/1/moved-1.jar'
        cache, _ = self.cache(mock.Mock(side_effect=lambda request: FakeResponse(url=final_url)))
        with cache(Request(URL)) as response:
            self.assertEqual(final_url, response.geturl())
            self.assertEqual(BODY, response.read1(100000))
        entry = cache.receipt()['responses'][0]
        self.assertEqual(URL, entry['sourceUrl'])
        self.assertEqual(final_url, entry['finalUrl'])

    def test_truncated_or_overlong_response_is_discarded_and_retry_can_succeed(self):
        cache, opener = self.cache()
        for length in (len(BODY) + 1, len(BODY) - 1):
            opener.side_effect = lambda request, length=length: FakeResponse(length=length)
            with self.subTest(length=length), self.assertRaisesRegex(MIRROR.RepositoryError, 'Truncated'):
                cache(Request(URL))
            self.assert_no_cached_payload(cache)
        opener.side_effect = lambda request: FakeResponse()
        self.assertEqual(BODY, self.read(cache))
        self.assertEqual(1, len(cache.receipt()['responses']))

    def test_invalid_or_oversized_content_length_is_rejected_before_caching(self):
        cache, opener = self.cache()
        with mock.patch.object(MIRROR, 'MAX_BODY_BYTES', 8):
            for length in ('-1', '1.5', 'unknown', 9):
                opener.side_effect = lambda request, length=length: FakeResponse(b'12345678', length=length)
                with self.subTest(length=length), self.assertRaises(MIRROR.RepositoryError):
                    cache(Request(URL))
                self.assert_no_cached_payload(cache)

    def test_chunked_response_cannot_exceed_the_size_bound(self):
        cache, _ = self.cache(mock.Mock(side_effect=lambda request: FakeResponse(b'123456789', length=None)))
        with mock.patch.object(MIRROR, 'MAX_BODY_BYTES', 8), self.assertRaises(MIRROR.BodyTooLarge):
            cache(Request(URL))
        self.assert_no_cached_payload(cache)

    def test_body_read_failure_discards_partial_payload(self):
        def fail():
            raise OSError('fake interrupted body')
        cache, _ = self.cache(mock.Mock(side_effect=lambda request: FakeResponse(before_read=fail)))
        with self.assertRaisesRegex(OSError, 'interrupted'):
            cache(Request(URL))
        self.assert_no_cached_payload(cache)

    def test_initial_download_deadline_discards_partial_payload(self):
        cache, _ = self.cache()
        with mock.patch.object(MODULE.time, 'monotonic', side_effect=[0, MODULE.DOWNLOAD_TIMEOUT_SECONDS + 1]):
            with self.assertRaises(TimeoutError):
                cache(Request(URL))
        self.assert_no_cached_payload(cache)

    def test_eof_after_deadline_cannot_be_committed(self):
        now = [0]
        def finish_after_deadline():
            now[0] = MODULE.DOWNLOAD_TIMEOUT_SECONDS + 1
        cache, _ = self.cache(mock.Mock(side_effect=lambda request: FakeResponse(b'', before_read=finish_after_deadline)))
        with mock.patch.object(MODULE.time, 'monotonic', side_effect=lambda: now[0]):
            with self.assertRaises(TimeoutError):
                cache(Request(URL))
        self.assert_no_cached_payload(cache)

    def test_final_body_read_after_deadline_cannot_be_committed(self):
        now = [0]
        def read_after_deadline():
            now[0] = MODULE.DOWNLOAD_TIMEOUT_SECONDS + 1
        cache, _ = self.cache(mock.Mock(side_effect=lambda request: FakeResponse(before_read=read_after_deadline)))
        with mock.patch.object(MODULE.time, 'monotonic', side_effect=lambda: now[0]):
            with self.assertRaises(TimeoutError):
                cache(Request(URL))
        self.assert_no_cached_payload(cache)

    def test_same_length_mutation_fails_on_hit_and_final_receipt(self):
        cache, opener = self.cache()
        self.read(cache)
        target = self.directory / RELATIVE
        target.write_bytes(bytes([BODY[0] ^ 1]) + BODY[1:])
        with self.assertRaisesRegex(MIRROR.RepositoryError, 'changed'):
            cache(Request(URL))
        with self.assertRaisesRegex(MIRROR.RepositoryError, 'final byte verification'):
            cache.receipt()
        opener.assert_called_once()

    def test_deleted_or_final_symlink_cache_entry_is_rejected(self):
        cache, _ = self.cache(); self.read(cache)
        target = self.directory / RELATIVE
        target.unlink()
        with self.assertRaises(MIRROR.RepositoryError):
            cache(Request(URL))
        outside = self.root / 'same-bytes.jar'; outside.write_bytes(BODY)
        target.symlink_to(outside)
        with self.assertRaises(MIRROR.RepositoryError):
            cache(Request(URL))
        with self.assertRaises(MIRROR.RepositoryError):
            cache.receipt()

    def test_parent_symlink_cannot_write_download_outside_cache(self):
        cache, _ = self.cache()
        outside = self.root / 'outside'; outside.mkdir()
        (self.directory / 'org').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(MIRROR.RepositoryError):
            cache(Request(URL))
        self.assertEqual([], list(outside.rglob('*')), 'Rejected input must not create outside payloads')
        self.assertEqual({}, cache.records)

    def test_parent_symlink_cannot_replay_previous_download_or_pass_receipt(self):
        cache, _ = self.cache(); self.read(cache)
        directory = self.directory / 'org'
        outside = self.root / 'moved-org'; directory.rename(outside)
        directory.symlink_to(outside, target_is_directory=True)
        with self.subTest(operation='replay'), self.assertRaises(MIRROR.RepositoryError):
            cache(Request(URL))
        with self.subTest(operation='receipt'), self.assertRaises(MIRROR.RepositoryError):
            cache.receipt()

    def test_replaced_cache_root_cannot_replay_or_write_outside(self):
        cache, _ = self.cache(); self.read(cache)
        outside = self.root / 'moved-cache'; self.directory.rename(outside)
        self.directory.symlink_to(outside, target_is_directory=True)
        for operation in (lambda: cache(Request(URL)), cache.receipt):
            with self.subTest(operation=operation), self.assertRaises(MIRROR.RepositoryError):
                operation()

    def test_metadata_symlinks_cannot_write_outside_cache(self):
        outside = self.root / 'outside.json'; outside.write_text('unchanged')
        cache, _ = self.cache()
        (self.directory / 'downloads.jsonl').symlink_to(outside)
        with self.assertRaises(MIRROR.RepositoryError):
            cache(Request(URL))
        self.assertEqual('unchanged', outside.read_text())
        (self.directory / 'receipt.json').symlink_to(outside)
        with self.assertRaises(MIRROR.RepositoryError):
            cache.write_receipt()
        self.assertEqual('unchanged', outside.read_text())

    def test_context_restores_transport_and_deadline_and_writes_verified_receipt(self):
        opener = mock.Mock(side_effect=lambda request: FakeResponse())
        deadline = MIRROR.UPSTREAM_TOTAL_SECONDS
        with mock.patch.object(MIRROR, '_open_central', opener):
            with MODULE.cached_central(self.directory) as cache:
                self.assertIs(cache, MIRROR._open_central)
                self.assertGreaterEqual(MIRROR.UPSTREAM_TOTAL_SECONDS, MODULE.DOWNLOAD_TIMEOUT_SECONDS)
                self.assertEqual(BODY, self.read(cache))
            self.assertIs(opener, MIRROR._open_central)
            self.assertEqual(deadline, MIRROR.UPSTREAM_TOTAL_SECONDS)
        receipt = json.loads((self.directory / 'receipt.json').read_text())
        self.assertEqual(hashlib.sha256(BODY).hexdigest(), receipt['responses'][0]['sha256'])

    def test_context_restores_global_transport_when_body_or_final_verification_fails(self):
        opener = mock.Mock(side_effect=lambda request: FakeResponse())
        deadline = MIRROR.UPSTREAM_TOTAL_SECONDS
        with mock.patch.object(MIRROR, '_open_central', opener):
            with self.assertRaisesRegex(ValueError, 'fake body error'):
                with MODULE.cached_central(self.directory):
                    raise ValueError('fake body error')
            self.assertIs(opener, MIRROR._open_central)
            self.assertEqual(deadline, MIRROR.UPSTREAM_TOTAL_SECONDS)
        other = self.root / 'mutated-cache'
        with mock.patch.object(MIRROR, '_open_central', opener):
            with self.assertRaises(MIRROR.RepositoryError):
                with MODULE.cached_central(other) as cache:
                    self.read(cache)
                    (other / RELATIVE).write_bytes(b'mutated')
            self.assertIs(opener, MIRROR._open_central)
            self.assertEqual(deadline, MIRROR.UPSTREAM_TOTAL_SECONDS)
        self.assertFalse((other / 'receipt.json').exists())


if __name__ == '__main__':
    unittest.main()
