#!/usr/bin/env python3
"""Run a bounded, privacy-safe ShardingSphere Agent 5.5.3 comparison.

The downloaded Agent distribution and received Zipkin payloads are treated as
ephemeral test inputs.  The fixed-schema JSON summary is the only comparison
artifact intended for publication; ordinary local Gradle build output may remain.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import secrets
import signal
import ssl
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unicodedata
import zlib
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


AGENT_VERSION = "5.5.3"
SHARDINGSPHERE_VERSION = "5.5.3"
AGENT_ARCHIVE_URL = (
    "https://archive.apache.org/dist/shardingsphere/5.5.3/"
    "apache-shardingsphere-5.5.3-shardingsphere-agent-bin.tar.gz"
)
EXPECTED_ARCHIVE_SHA512 = (
    "6538bf650cbdb1813814e1922b6c2072246c4595cb07322f793d5592c86be8759"
    "49529ab6a00553c15f72a0b17e2d23628f6e8b5da9fb189a72ce8c4cfb37839"
)
EXPECTED_ARCHIVE_BYTES = 46_741_869
EXPECTED_AGENT_FILES = {
    "agent/conf/agent.yaml",
    "agent/LICENSE",
    "agent/NOTICE",
    "agent/README.txt",
    "agent/plugins/lib/shardingsphere-agent-plugin-core-5.5.3.jar",
    "agent/plugins/lib/shardingsphere-agent-metrics-core-5.5.3.jar",
    "agent/plugins/logging/shardingsphere-agent-logging-file-5.5.3.jar",
    "agent/plugins/tracing/"
    "shardingsphere-agent-tracing-opentelemetry-5.5.3.jar",
    "agent/plugins/metrics/"
    "shardingsphere-agent-metrics-prometheus-5.5.3.jar",
    "agent/shardingsphere-agent-5.5.3.jar",
}
AGENT_JAR_RELATIVE = Path("agent/shardingsphere-agent-5.5.3.jar")
AGENT_CONFIG_RELATIVE = Path("agent/conf/agent.yaml")

ZIPKIN_PATH = "/api/v2/spans"
ROOT_SPAN_NAME = "/shardingsphere/rootinvoke/"
EXECUTE_SPAN_NAME = "/shardingsphere/executesql/"
REQUIRED_EXECUTE_TAGS = {
    "db.statement",
    "db.bind_vars",
    "db.instance",
    "peer.hostname",
    "peer.port",
    "otel.status_code",
}

EXPECTED_JUNIT_SUITE = (
    "io.github.ym0506.routecontract.example.AgentComparisonMySqlTest"
)
EXPECTED_JUNIT_METHOD = (
    "sequentialOperationsExposeExpectedPhysicalAttemptCounts()"
)
EXPECTED_ORACLE = {
    "schemaVersion": 1,
    "operations": 20,
    "logicalStatements": 40,
    "controlExpectedAttempts": 20,
    "fanOutExpectedAttempts": 40,
    "expectedPhysicalAttempts": 60,
    "proxyObservedAttempts": 60,
    "routeContractObservedAttempts": 60,
    "forcedFanOutPairs": 20,
    "uniqueRouteSignatures": 1,
}
EXPECTED_FIXTURE_VERSIONS = {
    "javaMajor": 17,
    "mysql": "8.4.11",
    "mysqlImageDigest": (
        "sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb"
    ),
    "testcontainers": "1.21.4",
    "connectorJ": "26.7.0",
}

MAX_ARCHIVE_MEMBERS = 64
MAX_ARCHIVE_MEMBER_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 96 * 1024 * 1024
MAX_HTTP_BODY_BYTES = 1024 * 1024
MAX_HTTP_TOTAL_BYTES = 16 * 1024 * 1024
MAX_HTTP_DECODED_BODY_BYTES = 1024 * 1024
MAX_HTTP_DECODED_TOTAL_BYTES = 16 * 1024 * 1024
MAX_HTTP_REQUESTS = 256
MAX_HTTP_WORKERS = 8
MAX_SPANS = 512
MAX_SPAN_FIELD_BYTES = 128 * 1024
MAX_ORACLE_BYTES = 16 * 1024
MAX_JUNIT_BYTES = 1024 * 1024
MAX_GRADLE_OUTPUT_BYTES = 8 * 1024 * 1024
GRADLE_TIMEOUT_SECONDS = 20 * 60

SUCCESS_MARKER = (
    "ROUTECONTRACT_AGENT_COMPARISON "
    "result=VERIFIED_SHARDINGSPHERE_AGENT_5_5_3"
)
SUMMARY_SUCCESS_MARKER = (
    "ROUTECONTRACT_AGENT_COMPARISON_SUMMARY result=VERIFIED_PRIVACY_SAFE_ARTIFACT"
)
FAILURE_MARKER = "ROUTECONTRACT_AGENT_COMPARISON result=FAILED"

RAW_PUBLIC_PATTERNS = (
    re.compile(r"\b(?:select|from|where|between|insert|update|delete|merge|values)\b", re.I),
    re.compile(r"\bpaid\b", re.I),
    re.compile(r"\bds_[01]\b", re.I),
    re.compile(r"\bjdbc\b", re.I),
    re.compile(r"\blocalhost\b", re.I),
    re.compile(r"127\.0\.0\.1"),
    re.compile(r"\b(?:traceid|spanid)\b", re.I),
    re.compile(r"/"),
    re.compile(r"\b[A-Za-z]:[\\/]"),
    re.compile(r"\\"),
)

CONTROL_STATEMENT = (
    "select order_id, user_id, status from t_order_1 "
    "where user_id = ? and status = ?"
)
_FANOUT_SELECT_0 = (
    "select order_id, user_id, status from t_order_0 "
    "where user_id between ? and ? and status = ?"
)
_FANOUT_SELECT_1 = (
    "select order_id, user_id, status from t_order_1 "
    "where user_id between ? and ? and status = ?"
)
FANOUT_STATEMENT = f"{_FANOUT_SELECT_0} union all {_FANOUT_SELECT_1}"


class ComparisonError(RuntimeError):
    """A privacy-safe validation failure identified only by a fixed code."""

    def __init__(self, code: str) -> None:
        safe_code = code if re.fullmatch(r"[A-Z][A-Z0-9_]*", code) else "INTERNAL"
        self.code = safe_code
        super().__init__(f"agent comparison validation failed ({safe_code})")


class SafeArgumentParser(argparse.ArgumentParser):
    """Avoid reflecting untrusted command-line values in parse errors."""

    def error(self, message: str) -> None:  # noqa: ARG002 - argparse API
        raise ComparisonError("ARGUMENTS")


@dataclass(frozen=True)
class AgentObservation:
    root_invoke_spans: int
    execute_spans: int
    control_execute_spans: int
    fanout_execute_spans: int
    fanout_surviving_data_source_count: int


@dataclass(frozen=True)
class JunitCounts:
    tests: int
    failures: int
    errors: int
    skipped: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = SafeArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--archive",
        type=Path,
        help="Use a local copy of the exact official Agent archive",
    )
    mode.add_argument(
        "--verify-summary-only",
        action="store_true",
        help="Verify the fixed repository summary without running the comparison",
    )
    return parser.parse_args(argv)


def _open_regular_no_follow(path: Path) -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ComparisonError("ARCHIVE_TYPE") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ComparisonError("ARCHIVE_TYPE")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _measure_sha512(path: Path) -> tuple[int, str]:
    digest = hashlib.sha512()
    descriptor = _open_regular_no_follow(path)
    size = 0
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
    except OSError as error:
        raise ComparisonError("ARCHIVE_READ") from error
    return size, digest.hexdigest()


def verify_archive_file(
    path: Path,
    *,
    expected_size: int = EXPECTED_ARCHIVE_BYTES,
    expected_sha512: str = EXPECTED_ARCHIVE_SHA512,
) -> None:
    actual_size, actual = _measure_sha512(path)
    if actual_size != expected_size:
        raise ComparisonError("ARCHIVE_SIZE")
    if not hmac.compare_digest(actual, expected_sha512):
        raise ComparisonError("ARCHIVE_CHECKSUM")


def stage_local_archive(
    source: Path,
    destination: Path,
    *,
    expected_size: int = EXPECTED_ARCHIVE_BYTES,
    expected_sha512: str = EXPECTED_ARCHIVE_SHA512,
) -> None:
    """Copy and hash one no-follow source descriptor into the private workspace."""
    source_descriptor = _open_regular_no_follow(source)
    digest = hashlib.sha512()
    size = 0
    try:
        with os.fdopen(source_descriptor, "rb", closefd=True) as input_stream:
            with destination.open("xb") as output_stream:
                while True:
                    chunk = input_stream.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > expected_size:
                        raise ComparisonError("ARCHIVE_SIZE")
                    digest.update(chunk)
                    output_stream.write(chunk)
                output_stream.flush()
                os.fsync(output_stream.fileno())
    except ComparisonError:
        raise
    except OSError as error:
        raise ComparisonError("ARCHIVE_READ") from error
    if size != expected_size:
        raise ComparisonError("ARCHIVE_SIZE")
    if not hmac.compare_digest(digest.hexdigest(), expected_sha512):
        raise ComparisonError("ARCHIVE_CHECKSUM")


def download_archive(destination: Path) -> None:
    request = Request(
        AGENT_ARCHIVE_URL,
        headers={"User-Agent": "RouteContract-Agent-Comparison/1"},
    )
    context = ssl.create_default_context()
    default_paths = ssl.get_default_verify_paths()
    if default_paths.cafile is None:
        for candidate in (
            Path("/etc/ssl/cert.pem"),
            Path("/etc/ssl/certs/ca-certificates.crt"),
            Path("/etc/pki/tls/certs/ca-bundle.crt"),
        ):
            try:
                if not candidate.is_symlink() and candidate.is_file():
                    context = ssl.create_default_context(cafile=str(candidate))
                    break
            except OSError:
                continue
    try:
        with urlopen(  # noqa: S310 - fixed HTTPS URL and verified context
            request,
            timeout=60,
            context=context,
        ) as response:
            final = urlparse(response.geturl())
            expected = urlparse(AGENT_ARCHIVE_URL)
            if (
                response.status != 200
                or final.scheme != "https"
                or final.hostname != expected.hostname
                or final.path != expected.path
            ):
                raise ComparisonError("DOWNLOAD_ORIGIN")
            raw_length = response.headers.get("Content-Length")
            if raw_length is None or not raw_length.isascii() or not raw_length.isdigit():
                raise ComparisonError("DOWNLOAD_LENGTH")
            if int(raw_length) != EXPECTED_ARCHIVE_BYTES:
                raise ComparisonError("DOWNLOAD_LENGTH")

            written = 0
            with destination.open("xb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > EXPECTED_ARCHIVE_BYTES:
                        raise ComparisonError("DOWNLOAD_LENGTH")
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if written != EXPECTED_ARCHIVE_BYTES:
                raise ComparisonError("DOWNLOAD_LENGTH")
    except ComparisonError:
        raise
    except (OSError, URLError, ValueError) as error:
        raise ComparisonError("DOWNLOAD_FAILED") from error


def _safe_tar_name(
    name: str, *, is_directory: bool = False
) -> tuple[PurePosixPath, str]:
    normalized = name
    if is_directory and normalized.endswith("/"):
        normalized = normalized[:-1]
    if (
        not normalized
        or "\\" in normalized
        or "\x00" in normalized
        or normalized.startswith("/")
        or normalized.endswith("/")
        or "//" in normalized
    ):
        raise ComparisonError("ARCHIVE_UNSAFE")
    parts = normalized.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ComparisonError("ARCHIVE_UNSAFE")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or str(pure) != normalized:
        raise ComparisonError("ARCHIVE_UNSAFE")
    collision_key = unicodedata.normalize("NFKC", normalized).casefold()
    return pure, collision_key


def extract_agent_archive(
    archive_path: Path,
    destination: Path,
    *,
    required_files: set[str] = EXPECTED_AGENT_FILES,
) -> None:
    if not required_files:
        raise ComparisonError("ARCHIVE_MANIFEST")
    if destination.exists() or destination.is_symlink():
        raise ComparisonError("EXTRACT_TARGET")

    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = archive.getmembers()
            if not members or len(members) > MAX_ARCHIVE_MEMBERS:
                raise ComparisonError("ARCHIVE_MEMBER_LIMIT")

            regular: dict[str, tarfile.TarInfo] = {}
            directories: set[str] = set()
            collision_keys: set[str] = set()
            total_size = 0
            for member in members:
                safe_name, collision_key = _safe_tar_name(
                    member.name, is_directory=member.isdir()
                )
                if collision_key in collision_keys:
                    raise ComparisonError("ARCHIVE_COLLISION")
                collision_keys.add(collision_key)
                if member.pax_headers or member.sparse is not None:
                    raise ComparisonError("ARCHIVE_UNSAFE")
                if member.isdir():
                    directories.add(str(safe_name))
                    continue
                if not member.isreg():
                    raise ComparisonError("ARCHIVE_UNSAFE")
                if member.size < 0 or member.size > MAX_ARCHIVE_MEMBER_BYTES:
                    raise ComparisonError("ARCHIVE_MEMBER_LIMIT")
                total_size += member.size
                if total_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise ComparisonError("ARCHIVE_MEMBER_LIMIT")
                regular[member.name] = member

            if set(regular) != set(required_files):
                raise ComparisonError("ARCHIVE_MANIFEST")
            allowed_directories = {
                str(parent)
                for name in required_files
                for parent in PurePosixPath(name).parents
                if str(parent) != "."
            }
            if not directories.issubset(allowed_directories):
                raise ComparisonError("ARCHIVE_MANIFEST")

            destination.mkdir(mode=0o700)
            for name in sorted(regular):
                target = destination.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                extracted = archive.extractfile(regular[name])
                if extracted is None:
                    raise ComparisonError("ARCHIVE_READ")
                remaining = regular[name].size
                with target.open("xb") as output:
                    while remaining:
                        chunk = extracted.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ComparisonError("ARCHIVE_READ")
                        output.write(chunk)
                        remaining -= len(chunk)
                    if extracted.read(1):
                        raise ComparisonError("ARCHIVE_READ")
                    output.flush()
                    os.fsync(output.fileno())
                target.chmod(0o600)
    except ComparisonError:
        raise
    except (OSError, tarfile.TarError, EOFError) as error:
        raise ComparisonError("ARCHIVE_READ") from error


def _atomic_write_text(path: Path, content: str) -> None:
    if path.is_symlink():
        raise ComparisonError("OUTPUT_SYMLINK")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        os.replace(temporary, path)
    except ComparisonError:
        raise
    except OSError as error:
        raise ComparisonError("OUTPUT_WRITE") from error


def write_agent_config(path: Path, port: int) -> None:
    if not 1 <= port <= 65_535:
        raise ComparisonError("HTTP_PORT")
    if path.is_symlink() or not path.is_file():
        raise ComparisonError("AGENT_CONFIG")
    content = f"""plugins:
  tracing:
    OpenTelemetry:
      props:
        otel.service.name: "routecontract-agent-comparison"
        otel.traces.exporter: "zipkin"
        otel.exporter.zipkin.endpoint: "http://127.0.0.1:{port}{ZIPKIN_PATH}"
        otel.traces.sampler: "always_on"
        otel.bsp.schedule.delay: "100"
        otel.bsp.max.export.batch.size: "1"
        otel.bsp.max.queue.size: "2048"
"""
    _atomic_write_text(path, content)


class _BoundedZipkinServer(ThreadingHTTPServer):
    daemon_threads = False

    def __init__(self, address: tuple[str, int], receiver: "ZipkinReceiver") -> None:
        self.receiver = receiver
        self._worker_slots = threading.BoundedSemaphore(MAX_HTTP_WORKERS)
        super().__init__(address, _ZipkinHandler)

    def process_request(self, request: object, client_address: object) -> None:
        if not self._worker_slots.acquire(blocking=False):
            self.receiver._record_error("HTTP_WORKER_LIMIT")
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._worker_slots.release()
            raise

    def process_request_thread(self, request: object, client_address: object) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._worker_slots.release()

    def handle_error(self, request: object, client_address: object) -> None:  # noqa: ARG002
        self.receiver._record_error("HTTP_HANDLER")


class _ZipkinHandler(BaseHTTPRequestHandler):
    server: _BoundedZipkinServer
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002, ARG002
        return

    def _respond(self, status: int) -> None:
        self.close_connection = True
        self.send_response(status)
        self.send_header("Connection", "close")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        try:
            lengths = self.headers.get_all("Content-Length", failobj=[])
            transfer_encoding = self.headers.get("Transfer-Encoding")
            content_type = self.headers.get("Content-Type", "").partition(";")[0].strip()
            content_encodings = self.headers.get_all("Content-Encoding", failobj=[])
            content_encoding = (
                "identity" if not content_encodings else content_encodings[0].casefold()
            )
            if (
                self.path != ZIPKIN_PATH
                or transfer_encoding is not None
                or len(lengths) != 1
                or len(content_encodings) > 1
                or not lengths[0].isascii()
                or not lengths[0].isdigit()
                or content_type != "application/json"
                or content_encoding not in ("identity", "gzip")
            ):
                self.server.receiver._record_error("HTTP_REQUEST")
                self.close_connection = True
                self._respond(400)
                return
            length = int(lengths[0])
            status = self.server.receiver._reserve_request(length)
            if status is not None:
                self.close_connection = True
                self._respond(status)
                return
            body = self.rfile.read(length)
            if len(body) != length:
                self.server.receiver._record_error("HTTP_BODY")
                self.close_connection = True
                self._respond(400)
                return
            try:
                decoded_body = self.server.receiver._decode_body(
                    body, content_encoding
                )
                decoded = decoded_body.decode("utf-8", errors="strict")
                batch = json.loads(decoded)
            except ComparisonError as error:
                self.server.receiver._record_error("HTTP_ENCODING")
                self._respond(
                    413
                    if error.code
                    in {"HTTP_DECODED_LIMIT", "HTTP_DECODED_TOTAL_LIMIT"}
                    else 400
                )
                return
            except (UnicodeDecodeError, json.JSONDecodeError):
                self.server.receiver._record_error("HTTP_JSON")
                self._respond(400)
                return
            if (
                not isinstance(batch, list)
                or len(batch) != 1
                or not isinstance(batch[0], dict)
            ):
                self.server.receiver._record_error("HTTP_JSON")
                self._respond(400)
                return
            self.server.receiver._append_span(batch[0])
            self._respond(202)
        except (OSError, ValueError):
            self.server.receiver._record_error("HTTP_HANDLER")
            self.close_connection = True

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.server.receiver._record_error("HTTP_METHOD")
        self._respond(405)


class ZipkinReceiver:
    """A loopback-only receiver with fixed request and memory limits."""

    def __init__(
        self,
        *,
        max_body_bytes: int = MAX_HTTP_BODY_BYTES,
        max_requests: int = MAX_HTTP_REQUESTS,
        max_total_bytes: int = MAX_HTTP_TOTAL_BYTES,
        max_decoded_body_bytes: int = MAX_HTTP_DECODED_BODY_BYTES,
        max_decoded_total_bytes: int = MAX_HTTP_DECODED_TOTAL_BYTES,
    ) -> None:
        if min(
            max_body_bytes,
            max_requests,
            max_total_bytes,
            max_decoded_body_bytes,
            max_decoded_total_bytes,
        ) <= 0:
            raise ComparisonError("HTTP_LIMIT")
        self._max_body_bytes = max_body_bytes
        self._max_requests = max_requests
        self._max_total_bytes = max_total_bytes
        self._max_decoded_body_bytes = max_decoded_body_bytes
        self._max_decoded_total_bytes = max_decoded_total_bytes
        self._lock = threading.Lock()
        self._requests = 0
        self._bytes = 0
        self._decoded_bytes = 0
        self._errors: set[str] = set()
        self._spans: list[dict[str, object]] = []
        try:
            self._server = _BoundedZipkinServer(("127.0.0.1", 0), self)
        except OSError as error:
            raise ComparisonError("HTTP_BIND") from error
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    def start(self) -> None:
        if self._thread is not None:
            raise ComparisonError("HTTP_STATE")
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="routecontract-agent-zipkin",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._server.shutdown()
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                self._record_error("HTTP_SHUTDOWN")
            self._thread = None
        self._server.server_close()

    def _record_error(self, code: str) -> None:
        with self._lock:
            self._errors.add(code)

    def _reserve_request(self, length: int) -> int | None:
        with self._lock:
            self._requests += 1
            if self._requests > self._max_requests:
                self._errors.add("HTTP_REQUEST_LIMIT")
                return 429
            if length <= 0 or length > self._max_body_bytes:
                self._errors.add("HTTP_BODY_LIMIT")
                return 413
            if self._bytes + length > self._max_total_bytes:
                self._errors.add("HTTP_TOTAL_LIMIT")
                return 413
            self._bytes += length
        return None

    def _append_span(self, span: dict[str, object]) -> None:
        with self._lock:
            if len(self._spans) >= MAX_SPANS:
                self._errors.add("HTTP_SPAN_LIMIT")
                return
            self._spans.append(span)

    def _decode_body(self, body: bytes, encoding: str) -> bytes:
        if encoding == "identity":
            decoded = body
        elif encoding == "gzip":
            try:
                decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
                decoded = decompressor.decompress(
                    body, self._max_decoded_body_bytes + 1
                )
                if (
                    len(decoded) > self._max_decoded_body_bytes
                    or decompressor.unconsumed_tail
                ):
                    raise ComparisonError("HTTP_DECODED_LIMIT")
                decoded += decompressor.flush(
                    self._max_decoded_body_bytes + 1 - len(decoded)
                )
                if (
                    len(decoded) > self._max_decoded_body_bytes
                    or not decompressor.eof
                    or decompressor.unused_data
                ):
                    raise ComparisonError("HTTP_ENCODING")
            except zlib.error as error:
                raise ComparisonError("HTTP_ENCODING") from error
        else:
            raise ComparisonError("HTTP_ENCODING")

        with self._lock:
            if len(decoded) > self._max_decoded_body_bytes:
                self._errors.add("HTTP_DECODED_LIMIT")
                raise ComparisonError("HTTP_DECODED_LIMIT")
            if self._decoded_bytes + len(decoded) > self._max_decoded_total_bytes:
                self._errors.add("HTTP_DECODED_TOTAL_LIMIT")
                raise ComparisonError("HTTP_DECODED_TOTAL_LIMIT")
            self._decoded_bytes += len(decoded)
        return decoded

    def snapshot(self) -> list[dict[str, object]]:
        with self._lock:
            return list(self._spans)

    def raise_if_failed(self) -> None:
        with self._lock:
            failed = bool(self._errors)
        if failed:
            raise ComparisonError("HTTP_CAPTURE_INVALID")


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def run_capped_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
    timeout_seconds: int = GRADLE_TIMEOUT_SECONDS,
    max_output_bytes: int = MAX_GRADLE_OUTPUT_BYTES,
) -> None:
    if not command or timeout_seconds <= 0 or max_output_bytes <= 0:
        raise ComparisonError("GRADLE_ARGUMENTS")
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=(os.name == "posix"),
            env=environment,
        )
    except OSError as error:
        raise ComparisonError("GRADLE_START") from error
    assert process.stdout is not None

    captured = bytearray()
    selector = selectors.DefaultSelector()
    deadline = time.monotonic() + timeout_seconds
    try:
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _stop_process(process)
                raise ComparisonError("GRADLE_TIMEOUT")
            events = selector.select(timeout=min(0.25, remaining))
            for key, _ in events:
                try:
                    chunk = os.read(key.fileobj.fileno(), 64 * 1024)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if len(captured) + len(chunk) > max_output_bytes:
                    _stop_process(process)
                    raise ComparisonError("GRADLE_OUTPUT_LIMIT")
                captured.extend(chunk)
        remaining = max(0.01, deadline - time.monotonic())
        try:
            return_code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            _stop_process(process)
            raise ComparisonError("GRADLE_TIMEOUT") from error
        if return_code != 0:
            raise ComparisonError("GRADLE_FAILED")
    finally:
        selector.close()
        process.stdout.close()
        if process.poll() is None:
            _stop_process(process)
        captured.clear()


def _bounded_string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ComparisonError("SPAN_FIELD")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ComparisonError("SPAN_FIELD") from error
    if len(encoded) > MAX_SPAN_FIELD_BYTES:
        raise ComparisonError("SPAN_FIELD")
    return value


def _classify_statement(statement: str) -> str:
    normalized = " ".join(statement.casefold().replace("`", "").split())
    if normalized == CONTROL_STATEMENT:
        return "control"
    if normalized == FANOUT_STATEMENT:
        return "fanout"
    raise ComparisonError("EXECUTE_UNCLASSIFIED")


def _validate_bind_shape(bind_vars: str, expected_values: int) -> None:
    if not bind_vars.startswith("[") or not bind_vars.endswith("]"):
        raise ComparisonError("EXECUTE_BIND_SHAPE")
    body = bind_vars[1:-1]
    values = [value.strip() for value in body.split(",")]
    if len(values) != expected_values or any(not value for value in values):
        raise ComparisonError("EXECUTE_BIND_SHAPE")


def analyze_spans(spans: list[dict[str, object]]) -> AgentObservation:
    if not isinstance(spans, list) or len(spans) > MAX_SPANS:
        raise ComparisonError("SPAN_SET")

    roots: dict[tuple[str, str], dict[str, object]] = {}
    executes: list[dict[str, object]] = []
    recognized_ids: set[tuple[str, str]] = set()
    for span in spans:
        if not isinstance(span, dict):
            raise ComparisonError("SPAN_SHAPE")
        name = _bounded_string(span.get("name")).casefold()
        if name not in (ROOT_SPAN_NAME, EXECUTE_SPAN_NAME):
            continue
        trace_id = _bounded_string(span.get("traceId"))
        span_id = _bounded_string(span.get("id"))
        identity = (trace_id, span_id)
        if identity in recognized_ids:
            raise ComparisonError("SPAN_DUPLICATE")
        recognized_ids.add(identity)
        if name == ROOT_SPAN_NAME:
            if span.get("parentId") not in (None, ""):
                raise ComparisonError("ROOT_PARENT")
            roots[identity] = span
        else:
            executes.append(span)

    if len(roots) != 40 or len(executes) != 40:
        raise ComparisonError("SPAN_COUNTS")

    children_per_root = {identity: 0 for identity in roots}
    control = 0
    fanout = 0
    control_data_sources: set[str] = set()
    fanout_data_sources: set[str] = set()
    for span in executes:
        trace_id = _bounded_string(span.get("traceId"))
        parent_id = _bounded_string(span.get("parentId"))
        parent = (trace_id, parent_id)
        if parent not in roots:
            raise ComparisonError("EXECUTE_PARENT")
        children_per_root[parent] += 1

        tags = span.get("tags")
        if not isinstance(tags, dict):
            raise ComparisonError("EXECUTE_TAGS")
        values: dict[str, str] = {}
        for tag in REQUIRED_EXECUTE_TAGS:
            values[tag] = _bounded_string(tags.get(tag))
        if values["otel.status_code"].casefold() != "ok":
            raise ComparisonError("EXECUTE_STATUS")
        classification = _classify_statement(values["db.statement"])
        if classification == "control":
            _validate_bind_shape(values["db.bind_vars"], 2)
            control += 1
            control_data_sources.add(values["db.instance"])
        else:
            _validate_bind_shape(values["db.bind_vars"], 6)
            fanout += 1
            fanout_data_sources.add(values["db.instance"])

    if any(count != 1 for count in children_per_root.values()):
        raise ComparisonError("EXECUTE_PARENT_CARDINALITY")
    if control != 20 or fanout != 20:
        raise ComparisonError("EXECUTE_CLASS_COUNTS")
    if len(control_data_sources) != 1:
        raise ComparisonError("CONTROL_DATA_SOURCE_COUNT")
    fanout_data_source_count = len(fanout_data_sources)
    if fanout_data_source_count not in (1, 2):
        raise ComparisonError("FANOUT_DATA_SOURCE_COUNT")

    return AgentObservation(
        root_invoke_spans=len(roots),
        execute_spans=len(executes),
        control_execute_spans=control,
        fanout_execute_spans=fanout,
        fanout_surviving_data_source_count=fanout_data_source_count,
    )


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ComparisonError("JSON_DUPLICATE")
        result[key] = value
    return result


def read_oracle(path: Path) -> dict[str, int]:
    try:
        if path.is_symlink() or not path.is_file():
            raise ComparisonError("ORACLE_TYPE")
        if path.stat().st_size > MAX_ORACLE_BYTES:
            raise ComparisonError("ORACLE_SIZE")
        raw = path.read_bytes()
        decoded = raw.decode("utf-8", errors="strict")
        parsed = json.loads(decoded, object_pairs_hook=_object_without_duplicates)
    except ComparisonError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ComparisonError("ORACLE_JSON") from error
    if not isinstance(parsed, dict) or set(parsed) != set(EXPECTED_ORACLE):
        raise ComparisonError("ORACLE_SCHEMA")
    if any(type(parsed[key]) is not int for key in EXPECTED_ORACLE):
        raise ComparisonError("ORACLE_SCHEMA")
    if parsed != EXPECTED_ORACLE:
        raise ComparisonError("ORACLE_VALUES")
    return {key: int(parsed[key]) for key in EXPECTED_ORACLE}


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def read_junit_counts(results_directory: Path) -> JunitCounts:
    expected_path = results_directory / f"TEST-{EXPECTED_JUNIT_SUITE}.xml"
    try:
        if results_directory.is_symlink() or not results_directory.is_dir():
            raise ComparisonError("JUNIT_DIRECTORY")
        xml_files = sorted(results_directory.glob("TEST-*.xml"))
        if xml_files != [expected_path]:
            raise ComparisonError("JUNIT_SET")
        if expected_path.is_symlink() or not expected_path.is_file():
            raise ComparisonError("JUNIT_TYPE")
        if expected_path.stat().st_size > MAX_JUNIT_BYTES:
            raise ComparisonError("JUNIT_SIZE")
        raw = expected_path.read_bytes()
    except ComparisonError:
        raise
    except OSError as error:
        raise ComparisonError("JUNIT_READ") from error
    uppercase = raw.upper()
    if b"<!DOCTYPE" in uppercase or b"<!ENTITY" in uppercase:
        raise ComparisonError("JUNIT_XML")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ComparisonError("JUNIT_XML") from error
    if _xml_local_name(root.tag) != "testsuite":
        raise ComparisonError("JUNIT_SCHEMA")
    expected_attributes = {
        "name": EXPECTED_JUNIT_SUITE,
        "tests": "1",
        "failures": "0",
        "errors": "0",
        "skipped": "0",
    }
    if any(root.get(key) != value for key, value in expected_attributes.items()):
        raise ComparisonError("JUNIT_COUNTS")
    if set(root.attrib) != {
        "name",
        "tests",
        "skipped",
        "failures",
        "errors",
        "timestamp",
        "hostname",
        "time",
    }:
        raise ComparisonError("JUNIT_SCHEMA")
    if any(not root.get(key) for key in ("timestamp", "hostname", "time")):
        raise ComparisonError("JUNIT_SCHEMA")
    children = list(root)
    if [_xml_local_name(child.tag) for child in children] != [
        "properties",
        "testcase",
    ]:
        raise ComparisonError("JUNIT_SCHEMA")
    properties = children[0]
    if properties.attrib or list(properties) or (properties.text or "").strip():
        raise ComparisonError("JUNIT_SCHEMA")
    testcases = [child for child in root if _xml_local_name(child.tag) == "testcase"]
    if len(testcases) != 1:
        raise ComparisonError("JUNIT_COUNTS")
    testcase = testcases[0]
    if (
        set(testcase.attrib) != {"name", "classname", "time"}
        or testcase.get("classname") != EXPECTED_JUNIT_SUITE
        or testcase.get("name") != EXPECTED_JUNIT_METHOD
        or not testcase.get("time")
        or (testcase.text or "").strip()
        or any(
            _xml_local_name(child.tag) in {"failure", "error", "skipped"}
            for child in testcase
        )
    ):
        raise ComparisonError("JUNIT_RESULT")
    return JunitCounts(tests=1, failures=0, errors=0, skipped=0)


def _read_bounded_source(path: Path) -> str:
    try:
        if path.is_symlink() or not path.is_file():
            raise ComparisonError("FIXTURE_SOURCE")
        if path.stat().st_size > 1024 * 1024:
            raise ComparisonError("FIXTURE_SOURCE")
        return path.read_text(encoding="utf-8", errors="strict")
    except ComparisonError:
        raise
    except (OSError, UnicodeDecodeError) as error:
        raise ComparisonError("FIXTURE_SOURCE") from error


def validate_fixture_configuration(repository_root: Path) -> dict[str, object]:
    properties_text = _read_bounded_source(repository_root / "gradle.properties")
    properties: dict[str, str] = {}
    for raw_line in properties_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ComparisonError("FIXTURE_PROPERTIES")
        key, value = (part.strip() for part in line.split("=", 1))
        if not key or not value or key in properties:
            raise ComparisonError("FIXTURE_PROPERTIES")
        properties[key] = value
    expected_properties = {
        "shardingSphereVersion": SHARDINGSPHERE_VERSION,
        "testcontainersVersion": str(EXPECTED_FIXTURE_VERSIONS["testcontainers"]),
        "mysqlConnectorVersion": str(EXPECTED_FIXTURE_VERSIONS["connectorJ"]),
    }
    if any(properties.get(key) != value for key, value in expected_properties.items()):
        raise ComparisonError("FIXTURE_VERSIONS")

    root_build = _read_bounded_source(repository_root / "build.gradle")
    mysql_build = _read_bounded_source(
        repository_root / "examples" / "mysql" / "build.gradle"
    )
    fixture_source = _read_bounded_source(
        repository_root
        / "examples"
        / "mysql"
        / "src"
        / "test"
        / "java"
        / "io"
        / "github"
        / "ym0506"
        / "routecontract"
        / "example"
        / "AgentComparisonMySqlTest.java"
    )
    lockfile = _read_bounded_source(
        repository_root / "examples" / "mysql" / "gradle.lockfile"
    )
    required_fragments = (
        (root_build, "languageVersion = JavaLanguageVersion.of(17)"),
        (root_build, "options.release = 17"),
        (
            mysql_build,
            'testRuntimeOnly("com.mysql:mysql-connector-j:${mysqlConnectorVersion}")',
        ),
        (
            mysql_build,
            'testImplementation "org.testcontainers:mysql:${testcontainersVersion}"',
        ),
        (
            fixture_source,
            '"mysql:8.4.11@sha256:'
            'b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb"',
        ),
        (fixture_source, "new MySQLContainer<>(MYSQL_IMAGE)"),
        (lockfile, "com.mysql:mysql-connector-j:26.7.0=testRuntimeClasspath"),
        (lockfile, "org.testcontainers:mysql:1.21.4="),
        (lockfile, "org.testcontainers:junit-jupiter:1.21.4="),
    )
    if any(text.count(fragment) != 1 for text, fragment in required_fragments):
        raise ComparisonError("FIXTURE_CONFIGURATION")
    return dict(EXPECTED_FIXTURE_VERSIONS)


def build_summary(
    oracle: dict[str, int],
    observation: AgentObservation,
    junit: JunitCounts,
    fixture_versions: dict[str, object] = EXPECTED_FIXTURE_VERSIONS,
) -> dict[str, object]:
    if oracle != EXPECTED_ORACLE:
        raise ComparisonError("SUMMARY_ORACLE")
    if fixture_versions != EXPECTED_FIXTURE_VERSIONS:
        raise ComparisonError("SUMMARY_VERSIONS")
    gap = oracle["expectedPhysicalAttempts"] - observation.execute_spans
    if (
        observation.root_invoke_spans != 40
        or observation.control_execute_spans != 20
        or observation.fanout_execute_spans != 20
        or observation.execute_spans != 40
        or gap != 20
        or observation.fanout_surviving_data_source_count not in (1, 2)
        or junit != JunitCounts(tests=1, failures=0, errors=0, skipped=0)
    ):
        raise ComparisonError("SUMMARY_COUNTS")
    return {
        "schemaVersion": 1,
        "classification": "verified-mysql-shardingsphere-5.5.3-agent-comparison",
        "versions": {
            "agent": AGENT_VERSION,
            "shardingSphere": SHARDINGSPHERE_VERSION,
            "javaMajor": fixture_versions["javaMajor"],
            "mysql": fixture_versions["mysql"],
            "mysqlImageDigest": fixture_versions["mysqlImageDigest"],
            "testcontainers": fixture_versions["testcontainers"],
            "connectorJ": fixture_versions["connectorJ"],
        },
        "archive": {
            "bytes": EXPECTED_ARCHIVE_BYTES,
            "sha512": EXPECTED_ARCHIVE_SHA512,
        },
        "workloadCounts": {
            "operations": oracle["operations"],
            "logicalStatements": oracle["logicalStatements"],
            "controlExpectedAttempts": oracle["controlExpectedAttempts"],
            "fanOutExpectedAttempts": oracle["fanOutExpectedAttempts"],
            "expectedPhysicalAttempts": oracle["expectedPhysicalAttempts"],
            "forcedFanOutPairs": oracle["forcedFanOutPairs"],
            "uniqueRouteSignatures": oracle["uniqueRouteSignatures"],
        },
        "oracleCounts": {
            "proxyObservedAttempts": oracle["proxyObservedAttempts"],
            "routeContractObservedAttempts": oracle[
                "routeContractObservedAttempts"
            ],
        },
        "agentCounts": {
            "rootInvokeSpans": observation.root_invoke_spans,
            "executeSpans": observation.execute_spans,
            "controlExecuteSpans": observation.control_execute_spans,
            "fanOutExecuteSpans": observation.fanout_execute_spans,
            "executeGap": gap,
            "fanOutSurvivingDataSourceCount": (
                observation.fanout_surviving_data_source_count
            ),
        },
        "junitCounts": {
            "tests": junit.tests,
            "failures": junit.failures,
            "errors": junit.errors,
            "skipped": junit.skipped,
        },
        "privacyClassification": {
            "requiredAgentTagsValidated": True,
            "rawTelemetryPersisted": False,
        },
    }


def serialize_summary(summary: dict[str, object]) -> str:
    try:
        serialized = json.dumps(
            summary,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ) + "\n"
    except (TypeError, ValueError) as error:
        raise ComparisonError("SUMMARY_JSON") from error
    scan_public_text(serialized)
    return serialized


def scan_public_text(text: str) -> None:
    if not isinstance(text, str):
        raise ComparisonError("PRIVACY_SCAN")
    if any(pattern.search(text) for pattern in RAW_PUBLIC_PATTERNS):
        raise ComparisonError("PRIVACY_SCAN")


def _directory_open_flags() -> int:
    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required):
        raise ComparisonError("OUTPUT_PLATFORM")
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )


def _open_output_directory(repository_root: Path, *, create: bool) -> int:
    """Open build/agent-comparison without following repository-relative links."""
    try:
        current = os.open(repository_root, _directory_open_flags())
        try:
            for component in ("build", "agent-comparison"):
                if create:
                    try:
                        os.mkdir(component, mode=0o700, dir_fd=current)
                    except FileExistsError:
                        pass
                next_directory = os.open(
                    component,
                    _directory_open_flags(),
                    dir_fd=current,
                )
                os.close(current)
                current = next_directory
            return current
        except BaseException:
            os.close(current)
            raise
    except ComparisonError:
        raise
    except OSError as error:
        raise ComparisonError("OUTPUT_DIRECTORY") from error


def _remove_stale_repository_summary(repository_root: Path) -> None:
    directory = _open_output_directory(repository_root, create=True)
    try:
        try:
            metadata = os.stat(
                "summary.json",
                dir_fd=directory,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return
        if not stat.S_ISREG(metadata.st_mode):
            raise ComparisonError("OUTPUT_TYPE")
        os.unlink("summary.json", dir_fd=directory)
        os.fsync(directory)
    except ComparisonError:
        raise
    except OSError as error:
        raise ComparisonError("OUTPUT_WRITE") from error
    finally:
        os.close(directory)


def _write_repository_summary(
    repository_root: Path,
    summary: dict[str, object],
) -> None:
    serialized = serialize_summary(summary).encode("utf-8")
    directory = _open_output_directory(repository_root, create=True)
    temporary_name = f".summary.json.{secrets.token_hex(12)}"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=directory,
        )
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(
            temporary_name,
            "summary.json",
            src_dir_fd=directory,
            dst_dir_fd=directory,
        )
        os.fsync(directory)
    except OSError as error:
        raise ComparisonError("OUTPUT_WRITE") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=directory)
        except FileNotFoundError:
            pass
        finally:
            os.close(directory)


def _read_repository_summary(repository_root: Path) -> str:
    directory = _open_output_directory(repository_root, create=False)
    descriptor: int | None = None
    try:
        if os.listdir(directory) != ["summary.json"]:
            raise ComparisonError("SUMMARY_FILE_SET")
        descriptor = os.open(
            "summary.json",
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory,
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 4096:
            raise ComparisonError("SUMMARY_FILE_TYPE")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                raise ComparisonError("SUMMARY_FILE_READ")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ComparisonError("SUMMARY_FILE_READ")
        return b"".join(chunks).decode("utf-8", errors="strict")
    except ComparisonError:
        raise
    except (OSError, UnicodeDecodeError) as error:
        raise ComparisonError("SUMMARY_FILE_READ") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)


def verify_repository_summary(repository_root: Path) -> None:
    serialized = _read_repository_summary(repository_root)
    try:
        payload = json.loads(
            serialized,
            object_pairs_hook=_object_without_duplicates,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ComparisonError("SUMMARY_FILE_JSON") from error
    if not isinstance(payload, dict):
        raise ComparisonError("SUMMARY_FILE_SCHEMA")
    agent_counts = payload.get("agentCounts")
    if not isinstance(agent_counts, dict):
        raise ComparisonError("SUMMARY_FILE_SCHEMA")
    surviving = agent_counts.get("fanOutSurvivingDataSourceCount")
    if type(surviving) is not int or surviving not in (1, 2):
        raise ComparisonError("SUMMARY_FILE_SCHEMA")
    expected = build_summary(
        EXPECTED_ORACLE,
        AgentObservation(
            root_invoke_spans=40,
            execute_spans=40,
            control_execute_spans=20,
            fanout_execute_spans=20,
            fanout_surviving_data_source_count=surviving,
        ),
        JunitCounts(tests=1, failures=0, errors=0, skipped=0),
        dict(EXPECTED_FIXTURE_VERSIONS),
    )
    if payload != expected or serialize_summary(payload) != serialized:
        raise ComparisonError("SUMMARY_FILE_SCHEMA")


def run_comparison(local_archive: Path | None) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    _remove_stale_repository_summary(repository_root)

    with tempfile.TemporaryDirectory(prefix="routecontract-agent-comparison.") as raw:
        temporary_root = Path(raw)
        archive = temporary_root / "agent.tar.gz"
        if local_archive is None:
            download_archive(archive)
            verify_archive_file(archive)
        else:
            stage_local_archive(local_archive.expanduser(), archive)

        extracted = temporary_root / "extracted"
        extract_agent_archive(archive, extracted)
        agent_jar = (extracted / AGENT_JAR_RELATIVE).resolve(strict=True)
        agent_config = extracted / AGENT_CONFIG_RELATIVE
        oracle_path = (temporary_root / "oracle.json").resolve()

        receiver = ZipkinReceiver()
        receiver.start()
        try:
            _, port = receiver.address
            write_agent_config(agent_config, port)
            command = [
                str(repository_root / "gradlew"),
                "--no-daemon",
                "--no-build-cache",
                "--rerun-tasks",
                ":mysql-example:agentComparisonMySql",
                f"-ProutecontractAgentJar={agent_jar}",
                f"-ProutecontractAgentEvidence={oracle_path}",
            ]
            environment = os.environ.copy()
            for key in tuple(environment):
                if key.startswith("ORG_GRADLE_PROJECT_"):
                    environment.pop(key, None)
            for key in (
                "CLASSPATH",
                "GRADLE_OPTS",
                "GRADLE_USER_HOME",
                "JAVA_OPTS",
                "JAVA_TOOL_OPTIONS",
                "JDK_JAVA_OPTIONS",
                "_JAVA_OPTIONS",
            ):
                environment.pop(key, None)
            environment["GRADLE_USER_HOME"] = str(
                temporary_root / "gradle-user-home"
            )
            run_capped_process(
                command,
                cwd=repository_root,
                environment=environment,
            )
        finally:
            receiver.stop()

        receiver.raise_if_failed()
        oracle = read_oracle(oracle_path)
        observation = analyze_spans(receiver.snapshot())
        junit = read_junit_counts(
            repository_root
            / "examples"
            / "mysql"
            / "build"
            / "test-results"
            / "agentComparisonMySql"
        )
        fixture_versions = validate_fixture_configuration(repository_root)
        summary = build_summary(
            oracle,
            observation,
            junit,
            fixture_versions,
        )
        _write_repository_summary(repository_root, summary)
        verify_repository_summary(repository_root)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if args.verify_summary_only:
            repository_root = Path(__file__).resolve().parents[1]
            verify_repository_summary(repository_root)
            scan_public_text(SUMMARY_SUCCESS_MARKER + "\n")
            print(SUMMARY_SUCCESS_MARKER)
            return 0
        run_comparison(args.archive)
        scan_public_text(SUCCESS_MARKER + "\n")
    except Exception:
        print(FAILURE_MARKER, file=sys.stderr)
        return 1
    print(SUCCESS_MARKER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
