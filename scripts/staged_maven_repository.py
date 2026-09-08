"""Loopback Maven mirror isolating staged RouteContract coordinates from Central.

This verifies consumption of supplied local bytes; it is not public release consumption.
"""
from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import stat
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

CENTRAL_ORIGIN = 'https://repo.maven.apache.org'
CENTRAL_PREFIX = CENTRAL_ORIGIN + '/maven2/'
GROUP_PATH = 'io/github/ym0506/routecontract'
MAX_BODY_BYTES = 100 * 1024 * 1024
UPSTREAM_TIMEOUT_SECONDS = 20
UPSTREAM_TOTAL_SECONDS = 120
CHUNK_BYTES = 64 * 1024


class RepositoryError(RuntimeError):
    """A request violates the local mirror's bounded repository policy."""


class BodyTooLarge(RepositoryError):
    """The requested artifact exceeds the configured body bound."""


def _maven_path(target: str) -> str:
    """Return an unambiguous relative Maven path, rejecting encoded traversal."""
    parsed = urlsplit(target)
    if (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment
            or not parsed.path.startswith('/') or parsed.path.startswith('//')):
        raise RepositoryError('Expected a repository-relative request path')
    if re.search(r'%(?![0-9A-Fa-f]{2})', parsed.path):
        raise RepositoryError('Malformed path encoding')
    # Encoded separators have no role in a Maven coordinate and obscure group routing.
    if re.search(r'%(?:2f|5c)', parsed.path, flags=re.IGNORECASE):
        raise RepositoryError('Encoded path separator')
    decoded = unquote(parsed.path, encoding='utf-8', errors='strict')[1:]
    parts = decoded.split('/')
    if any(not part or part in ('.', '..') for part in parts):
        raise RepositoryError('Empty or traversing repository segment')
    if any(not re.fullmatch(r'[A-Za-z0-9_~+.,@=()!-]+', part) for part in parts):
        raise RepositoryError('Unsupported repository path character')
    return decoded


def _is_staged(path: str) -> bool:
    return path == GROUP_PATH or path.startswith(GROUP_PATH + '/')


def _allowed_central_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname != 'repo.maven.apache.org'
                or parsed.port not in (None, 443) or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or not parsed.path.startswith('/maven2/')):
            return False
        relative = _maven_path('/' + parsed.path.removeprefix('/maven2/'))
        # A redirect must not evade group isolation by moving into our first-party namespace.
        return not _is_staged(relative)
    except (ValueError, UnicodeError, RepositoryError):
        return False


class CentralRedirectHandler(HTTPRedirectHandler):
    """Follow only HTTPS redirects within Central's third-party Maven path space."""

    def redirect_request(self, request, fp, code, message, headers, newurl):
        if not _allowed_central_url(newurl):
            raise RepositoryError('Central redirect left the permitted repository origin or namespace')
        redirected = super().redirect_request(request, fp, code, message, headers, newurl)
        if redirected is not None:
            # Do not carry any auth or cookie state even across an accepted redirect.
            # Older urllib versions rebuild a HEAD redirect as GET. Preserve the
            # caller's read method rather than inheriting that version-specific change.
            return Request(redirected.full_url, method=request.get_method(),
                           headers={'User-Agent': 'RouteContract-staged-consumer/1',
                                    'Accept-Encoding': 'identity'})
        return redirected


def _open_central(request: Request):
    if not _allowed_central_url(request.full_url):
        raise RepositoryError('Disallowed Central request')
    # No environment proxy, cookie jar, password manager, or caller headers are installed.
    opener = build_opener(ProxyHandler({}), CentralRedirectHandler())
    return opener.open(request, timeout=UPSTREAM_TIMEOUT_SECONDS)


def _staged_file(repository: Path, relative: str):
    """Open each directory and the final regular file without following symlinks."""
    descriptor = os.open(repository, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = relative.split('/')
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        file_descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                  dir_fd=descriptor)
        try:
            if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
                raise RepositoryError('The staged payload is not a regular file')
            return os.fdopen(file_descriptor, 'rb')
        except BaseException:
            os.close(file_descriptor)
            raise
    finally:
        os.close(descriptor)


def _content_length(headers) -> int | None:
    value = headers.get('Content-Length')
    if value is None:
        return None
    if not re.fullmatch(r'[0-9]+', value):
        raise RepositoryError('Invalid upstream content length')
    length = int(value)
    if length > MAX_BODY_BYTES:
        raise BodyTooLarge('Artifact exceeds mirror size bound')
    return length


@contextmanager
def serve_repository(repository: Path, log: Path):
    """Yield an ephemeral ``http://127.0.0.1:PORT/`` mirror and retain request JSONL.

    The supplied log must not exist. Records contain only normalized path, selected route,
    and response status; malformed paths are represented by ``<invalid>``. Request bodies,
    headers, remote error bodies, timestamps, and credentials are never logged.
    """
    repository = Path(repository).expanduser().absolute()
    log = Path(log).expanduser().absolute()
    if repository.is_symlink() or not repository.is_dir():
        raise RepositoryError('Supply a regular staged repository directory')
    repository = repository.resolve(strict=True)
    if log.resolve().is_relative_to(repository):
        raise RepositoryError('The request log must be outside the staged repository')
    log.parent.mkdir(parents=True, exist_ok=True)
    log_stream = log.open('x', encoding='utf-8')
    log_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        # HTTP/1.0 closes each connection so cleanup cannot wait on idle keep-alive clients.
        protocol_version = 'HTTP/1.0'

        def setup(self):
            super().setup()
            self.connection.settimeout(UPSTREAM_TIMEOUT_SECONDS)

        def log_message(self, format, *args):
            pass

        def do_GET(self):
            self._serve(head=False)

        def do_HEAD(self):
            self._serve(head=True)

        def _headers(self, status: int, length: int | None = 0):
            self.send_response(status)
            self.send_header('Content-Type', 'application/octet-stream')
            if length is not None:
                self.send_header('Content-Length', str(length))
            self.send_header('Connection', 'close')
            self.end_headers()

        def _copy_body(self, source, length: int):
            deadline = time.monotonic() + UPSTREAM_TOTAL_SECONDS
            remaining = length
            while remaining:
                available = deadline - time.monotonic()
                if available <= 0:
                    raise TimeoutError('Local response exceeded total transfer time bound')
                self.connection.settimeout(min(UPSTREAM_TIMEOUT_SECONDS, available))
                chunk = source.read(min(CHUNK_BYTES, remaining))
                if not chunk:
                    raise RepositoryError('Staged file changed while being served')
                self.wfile.write(chunk)
                remaining -= len(chunk)

        def _serve(self, head: bool):
            route = 'staged' if self.path.startswith('/' + GROUP_PATH) else 'central'
            path = '<invalid>'
            status = 500
            sent = False
            try:
                try:
                    path = _maven_path(self.path)
                except (RepositoryError, ValueError, UnicodeError):
                    status = 400
                    self._headers(status)
                    sent = True
                    return
                route = 'staged' if _is_staged(path) else 'central'
                if route == 'staged':
                    try:
                        source = _staged_file(repository, path)
                    except (RepositoryError, OSError):
                        status = 404
                        self._headers(status)
                        sent = True
                        return
                    with source:
                        length = os.fstat(source.fileno()).st_size
                        if length > MAX_BODY_BYTES:
                            raise BodyTooLarge('Artifact exceeds mirror size bound')
                        status = 200
                        self._headers(status, length)
                        sent = True
                        if not head:
                            self._copy_body(source, length)
                    return

                url = CENTRAL_PREFIX + quote(path, safe='/._~+-(),@=!')
                request = Request(url, method='HEAD' if head else 'GET',
                                  headers={'User-Agent': 'RouteContract-staged-consumer/1',
                                           'Accept-Encoding': 'identity'})
                deadline = time.monotonic() + UPSTREAM_TOTAL_SECONDS
                with _open_central(request) as response:
                    if not _allowed_central_url(response.geturl()) or response.status != 200:
                        raise RepositoryError('Unexpected Central response')
                    expected_length = _content_length(response.headers)
                    if head:
                        status = 200
                        self._headers(status, expected_length)
                        sent = True
                        return
                    # Buffer bounded content before declaring success, including chunked responses.
                    with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as body:
                        length = 0
                        while True:
                            if time.monotonic() >= deadline:
                                raise TimeoutError('Central request exceeded total transfer time bound')
                            # read1 performs at most one underlying read; read(n) could keep
                            # accumulating slow trickles indefinitely despite a socket timeout.
                            chunk = response.read1(min(CHUNK_BYTES, MAX_BODY_BYTES - length + 1))
                            if not chunk:
                                break
                            length += len(chunk)
                            if length > MAX_BODY_BYTES:
                                raise BodyTooLarge('Artifact exceeds mirror size bound')
                            body.write(chunk)
                        if expected_length is not None and expected_length != length:
                            raise RepositoryError('Truncated or inconsistent Central response')
                        body.seek(0)
                        status = 200
                        self._headers(status, length)
                        sent = True
                        self._copy_body(body, length)
            except HTTPError as error:
                status = error.code if error.code in (400, 403, 404, 410, 429, 500, 502, 503, 504) else 502
                error.close()
            except BodyTooLarge:
                status = 413
            except (socket.timeout, TimeoutError):
                status = 504
            except (RepositoryError, URLError, OSError, ValueError):
                status = 502
            finally:
                if not sent:
                    try:
                        self._headers(status)
                    except OSError:
                        pass
                with log_lock:
                    log_stream.write(json.dumps({'method': self.command, 'route': route, 'status': status, 'path': path},
                                                sort_keys=True, separators=(',', ':')) + '\n')
                    log_stream.flush()

    class Server(ThreadingHTTPServer):
        daemon_threads = False
        block_on_close = True

        def handle_error(self, request, client_address):
            # Do not emit exception traces containing request or upstream details.
            pass

    server = None
    thread = None
    try:
        server = Server(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05},
                                  name='routecontract-staged-maven-mirror')
        thread.start()
        yield f'http://127.0.0.1:{server.server_address[1]}/'
    finally:
        if server is not None:
            if thread is not None:
                server.shutdown()
                thread.join()
            server.server_close()
        log_stream.close()
