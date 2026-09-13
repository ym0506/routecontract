"""Bounded in-memory receiver; adapted from closed PR15 at 788b4684.

Only classified aggregates leave this module. Raw telemetry is never logged.
"""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import threading
import zlib

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


MAX_HTTP_BODY_BYTES = 1024 * 1024


MAX_HTTP_TOTAL_BYTES = 16 * 1024 * 1024


MAX_HTTP_DECODED_BODY_BYTES = 1024 * 1024


MAX_HTTP_DECODED_TOTAL_BYTES = 16 * 1024 * 1024


MAX_HTTP_REQUESTS = 256


MAX_HTTP_WORKERS = 8


MAX_SPANS = 512


MAX_SPAN_FIELD_BYTES = 128 * 1024


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


def analyze_spans(spans: list[dict[str, object]]) -> dict[str, object]:
    """Classify every root independently without assuming a fan-out outcome."""
    if not isinstance(spans, list) or len(spans) > MAX_SPANS:
        raise ComparisonError("SPAN_SET")
    roots = {}
    executes = []
    identities = set()
    for span in spans:
        if not isinstance(span, dict):
            raise ComparisonError("SPAN_SHAPE")
        name = _bounded_string(span.get("name")).casefold()
        trace = _bounded_string(span.get("traceId"))
        identity = (trace, _bounded_string(span.get("id")))
        if identity in identities:
            raise ComparisonError("SPAN_DUPLICATE")
        identities.add(identity)
        if name == ROOT_SPAN_NAME:
            if span.get("parentId") not in (None, ""):
                raise ComparisonError("ROOT_PARENT")
            roots[identity] = []
        elif name == EXECUTE_SPAN_NAME:
            executes.append(span)
    if len(roots) != 40:
        raise ComparisonError("ROOT_COUNT")

    aliases = {"ds_0": "left", "ds_1": "right"}
    for span in executes:
        parent = (span["traceId"], _bounded_string(span.get("parentId")))
        if parent not in roots:
            raise ComparisonError("EXECUTE_PARENT")
        tags = span.get("tags")
        if not isinstance(tags, dict):
            raise ComparisonError("EXECUTE_TAGS")
        values = {key: _bounded_string(tags.get(key)) for key in REQUIRED_EXECUTE_TAGS}
        if values["otel.status_code"].casefold() != "ok":
            raise ComparisonError("EXECUTE_STATUS")
        mode = _classify_statement(values["db.statement"])
        _validate_bind_shape(values["db.bind_vars"], 2 if mode == "control" else 6)
        alias = aliases.get(values["db.instance"])
        if alias is None:
            raise ComparisonError("UNREVIEWED_DATA_SOURCE")
        roots[parent].append((mode, alias))

    control_roots = 0
    histogram = {"oneChild": 0, "twoChildren": 0}
    observed_aliases = set()
    for children in roots.values():
        if not children:
            raise ComparisonError("ROOT_WITHOUT_EXECUTE")
        modes = {item[0] for item in children}
        if len(modes) != 1:
            raise ComparisonError("ROOT_MIXED_CLASSIFICATION")
        if modes == {"control"}:
            if children != [("control", "right")]:
                raise ComparisonError("CONTROL_CARDINALITY")
            control_roots += 1
        else:
            if len(children) not in (1, 2) or len(set(children)) != len(children):
                raise ComparisonError("FANOUT_CARDINALITY")
            histogram["oneChild" if len(children) == 1 else "twoChildren"] += 1
            observed_aliases.update(item[1] for item in children)
    if control_roots != 20 or sum(histogram.values()) != 20:
        raise ComparisonError("ROOT_CLASS_COUNTS")
    fanout_count = histogram["oneChild"] + 2 * histogram["twoChildren"]
    return {
        "rootSpans": len(roots),
        "executeSpans": len(executes),
        "controlRoots": control_roots,
        "controlExecuteSpans": control_roots,
        "fanoutRoots": 20,
        "fanoutExecuteSpans": fanout_count,
        "fanoutChildrenPerRoot": histogram,
        "fanoutObservedAliases": sorted(observed_aliases),
        "fanoutMatchesPhysicalOracle": histogram["twoChildren"] == 20,
        "classification": "ALL_FANOUT_CHILDREN_EXPORTED" if histogram["twoChildren"] == 20
                          else "FEWER_FANOUT_CHILDREN_EXPORTED",
    }
