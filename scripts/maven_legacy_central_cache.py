"""Per-run read-through Central response cache for independent Maven consumers.

Maven dependency caches remain empty at each case's start. This repository-side
cache downloads only through the existing anonymous, certificate-validating
Central transport; it accepts no user .m2 cache or foreign repository seed.
"""
from __future__ import annotations

from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import threading
import time
from urllib.parse import urlsplit

import staged_maven_repository as mirror

DOWNLOAD_TIMEOUT_SECONDS = 600


class CachedResponse:
    def __init__(self, stream, url: str, size: int):
        self.stream = stream
        self.url = url
        self.status = 200
        self.headers = {'Content-Length': str(size)}

    def geturl(self):
        return self.url

    def read1(self, size):
        return self.stream.read1(size)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stream.close()


class CentralResponses:
    def __init__(self, directory: Path, opener):
        if directory.exists() or directory.is_symlink():
            raise mirror.RepositoryError('Central response cache must start absent')
        directory.mkdir(mode=0o700)
        self.directory = directory
        self.opener = opener
        self.records = {}
        self.locks = {}
        self.lock = threading.Lock()

    @contextmanager
    def parent_descriptor(self, relative: str, *, create=False):
        """Anchor every cache operation at no-follow directory descriptors."""
        descriptor = None
        try:
            descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            for part in relative.split('/')[:-1]:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            yield descriptor
        except OSError as error:
            if error.errno in (errno.ELOOP, errno.ENOTDIR, errno.ENOENT, errno.EEXIST):
                raise mirror.RepositoryError('Response cache must contain regular files with no symlink ancestors') from error
            raise
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def verified_stream(self, relative: str, record: dict):
        with self.parent_descriptor(relative) as parent:
            descriptor = os.open(relative.split('/')[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_size != record['byteCount']:
                    raise mirror.RepositoryError('Repository response-cache bytes changed after the Central download')
                stream = os.fdopen(descriptor, 'rb')
            except BaseException:
                os.close(descriptor)
                raise
        try:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
            if checksum != record['sha256']:
                raise mirror.RepositoryError('Repository response-cache bytes changed after the Central download')
            stream.seek(0)
            return stream
        except BaseException:
            stream.close()
            raise

    def write_metadata(self, filename: str, payload: str, *, append=False):
        with self.parent_descriptor(filename) as parent:
            flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK
            descriptor = os.open(filename, flags | (os.O_APPEND if append else os.O_EXCL), mode=0o600, dir_fd=parent)
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise mirror.RepositoryError('Response-cache metadata must be regular files')
                stream = os.fdopen(descriptor, 'w', encoding='utf-8')
            except BaseException:
                os.close(descriptor)
                raise
            with stream:
                stream.write(payload)

    def __call__(self, request):
        if not mirror._allowed_central_url(request.full_url):
            raise mirror.RepositoryError('Response cache accepts only the isolated Central transport')
        if request.get_method() == 'HEAD':
            return self.opener(request)
        if request.get_method() != 'GET':
            raise mirror.RepositoryError('Response cache is read-only')
        relative = mirror._maven_path('/' + urlsplit(request.full_url).path.removeprefix('/maven2/'))
        with self.lock:
            path_lock = self.locks.setdefault(relative, threading.Lock())
        with path_lock:
            cache_hit = relative in self.records
            if not cache_hit:
                started = time.monotonic()
                with self.opener(request) as response:
                    if response.status != 200 or not mirror._allowed_central_url(response.geturl()):
                        raise mirror.RepositoryError('Cache response left the permitted Central origin')
                    expected_size = mirror._content_length(response.headers)
                    filename = relative.split('/')[-1]
                    partial = filename + '.partial'
                    size = 0
                    checksum = hashlib.sha256()
                    with self.parent_descriptor(relative, create=True) as parent:
                        created = False
                        try:
                            descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                                 mode=0o600, dir_fd=parent)
                            created = True
                            with os.fdopen(descriptor, 'wb') as destination:
                                while True:
                                    if time.monotonic() - started > DOWNLOAD_TIMEOUT_SECONDS:
                                        raise TimeoutError('Central response exceeded the bounded initial download time')
                                    chunk = response.read1(min(mirror.CHUNK_BYTES, mirror.MAX_BODY_BYTES - size + 1))
                                    if time.monotonic() - started > DOWNLOAD_TIMEOUT_SECONDS:
                                        raise TimeoutError('Central response exceeded the bounded initial download time')
                                    if not chunk:
                                        break
                                    size += len(chunk)
                                    if size > mirror.MAX_BODY_BYTES:
                                        raise mirror.BodyTooLarge('Central response exceeded the existing mirror size bound')
                                    checksum.update(chunk)
                                    destination.write(chunk)
                            if expected_size is not None and size != expected_size:
                                raise mirror.RepositoryError('Truncated Central response cannot seed the cache')
                            os.rename(partial, filename, src_dir_fd=parent, dst_dir_fd=parent)
                            created = False
                        finally:
                            if created:
                                os.unlink(partial, dir_fd=parent)
                    record = {'relativePath': relative, 'sourceUrl': request.full_url,
                              'finalUrl': response.geturl(), 'status': 200, 'sha256': checksum.hexdigest(),
                              'byteCount': size, 'transport': 'Anonymous HTTPS Central-only redirects; normal certificate validation',
                              'source': 'downloaded-during-this-run', 'cacheHits': 0, 'responseDeliveries': 0}
                with self.lock:
                    self.records[relative] = record
                    self.write_metadata('downloads.jsonl', json.dumps(record, sort_keys=True) + '\n', append=True)
            record = self.records[relative]
            stream = self.verified_stream(relative, record)
            with self.lock:
                record['cacheHits'] += int(cache_hit)
                record['responseDeliveries'] += 1
            return CachedResponse(stream, record['finalUrl'], record['byteCount'])

    def receipt(self) -> dict:
        records = []
        for relative, record in sorted(self.records.items()):
            try:
                with self.verified_stream(relative, record):
                    pass
            except mirror.RepositoryError as error:
                raise mirror.RepositoryError('Central response-cache final byte verification failed') from error
            records.append(dict(record))
        return {'formatVersion': 1, 'initiallyAbsent': True, 'source': 'This run only; no local Maven cache imported',
                'maxBodyBytes': mirror.MAX_BODY_BYTES, 'initialDownloadTimeoutSeconds': DOWNLOAD_TIMEOUT_SECONDS,
                'responses': records}

    def write_receipt(self):
        self.write_metadata('receipt.json', json.dumps(self.receipt(), indent=2, sort_keys=True) + '\n')


@contextmanager
def cached_central(directory: Path):
    original = mirror._open_central
    original_deadline = mirror.UPSTREAM_TOTAL_SECONDS
    cache = CentralResponses(directory, original)
    # The source module remains unchanged. Its per-request deadline includes an
    # initial cache fill; subsequent fresh consumers still fetch through HTTP.
    mirror._open_central = cache
    mirror.UPSTREAM_TOTAL_SECONDS = DOWNLOAD_TIMEOUT_SECONDS + 60
    try:
        yield cache
    finally:
        mirror._open_central = original
        mirror.UPSTREAM_TOTAL_SECONDS = original_deadline
        cache.write_receipt()
