#!/usr/bin/env python3
"""Acceptance tests for the privacy-safe ShardingSphere Agent comparison."""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "verify-agent-comparison.py"
SPEC = importlib.util.spec_from_file_location("verify_agent_comparison", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
comparison = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = comparison
SPEC.loader.exec_module(comparison)


RAW_SENTINELS = (
    "SELECT",
    "BETWEEN",
    "PAID",
    "ds_0",
    "ds_1",
    "jdbc",
    "localhost",
    "127.0.0.1",
    "/private/tmp/secret",
    "trace-control-00",
    "execute-control-00",
)


def root_span(index: int, kind: str) -> dict[str, object]:
    return {
        "traceId": f"trace-{kind}-{index:02d}",
        "id": f"root-{kind}-{index:02d}",
        "name": "/shardingsphere/rootinvoke/",
        "tags": {"fixture": "memory-only"},
    }


def execute_span(index: int, kind: str, data_source: str) -> dict[str, object]:
    if kind == "control":
        statement = (
            "SELECT order_id, user_id, status FROM t_order_1 "
            "WHERE user_id = ? AND status = ?"
        )
        bind_vars = "[1, PAID]"
    else:
        statement = (
            "SELECT order_id, user_id, status FROM t_order_0 "
            "WHERE user_id BETWEEN ? AND ? AND status = ?"
            " UNION ALL SELECT order_id, user_id, status FROM t_order_1 "
            "WHERE user_id BETWEEN ? AND ? AND status = ?"
        )
        bind_vars = "[0, 3, PAID, 0, 3, PAID]"
    return {
        "traceId": f"trace-{kind}-{index:02d}",
        "id": f"execute-{kind}-{index:02d}",
        "parentId": f"root-{kind}-{index:02d}",
        "name": "/shardingsphere/executesql/",
        "tags": {
            "db.statement": statement,
            "db.bind_vars": bind_vars,
            "db.instance": data_source,
            "peer.hostname": "localhost",
            "peer.port": "3306",
            "otel.status_code": "OK",
        },
    }


def valid_spans() -> list[dict[str, object]]:
    spans: list[dict[str, object]] = []
    for index in range(20):
        spans.extend(
            (
                root_span(index, "control"),
                execute_span(index, "control", "ds_0"),
                root_span(index, "fanout"),
                execute_span(index, "fanout", f"ds_{index % 2}"),
            )
        )
    return spans


def write_fixed_junit(path: Path, suite: str, method: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        f"<testsuite name='{suite}' tests='1' "
        "failures='0' errors='0' skipped='0' timestamp='2026-01-01T00:00:00Z' "
        "hostname='fixture.invalid' time='1.0'>\n"
        "  <properties/>\n"
        f"  <testcase classname='{suite}' name='{method}' time='1.0'/>\n"
        "</testsuite>\n",
        encoding="utf-8",
    )


def write_junit(path: Path) -> None:
    write_fixed_junit(
        path,
        comparison.EXPECTED_JUNIT_SUITE,
        comparison.EXPECTED_JUNIT_METHOD,
    )


def write_agent_only_junit(path: Path) -> None:
    write_fixed_junit(
        path,
        comparison.AGENT_ONLY_JUNIT_SUITE,
        comparison.AGENT_ONLY_JUNIT_METHOD,
    )


def tar_bytes(
    members: list[tuple[str, bytes | None, bytes]],
) -> bytes:
    """Build a gzip tar; member type is REGTYPE, DIRTYPE, SYMTYPE, etc."""
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, payload, member_type in members:
            info = tarfile.TarInfo(name)
            info.type = member_type
            if member_type == tarfile.SYMTYPE:
                info.linkname = "target"
            raw = payload or b""
            info.size = len(raw) if member_type == tarfile.REGTYPE else 0
            archive.addfile(info, io.BytesIO(raw) if raw else None)
    return stream.getvalue()


class VerifyAgentComparisonTest(unittest.TestCase):
    def assert_no_raw(self, text: str) -> None:
        lowered = text.casefold()
        for sentinel in RAW_SENTINELS:
            self.assertNotIn(sentinel.casefold(), lowered)

    def test_valid_result_is_exact_and_privacy_safe(self) -> None:
        observation = comparison.analyze_spans(valid_spans())
        summary = comparison.build_summary(
            comparison.EXPECTED_ORACLE,
            observation,
            comparison.JunitCounts(tests=1, failures=0, errors=0, skipped=0),
        )
        serialized = comparison.serialize_summary(summary)

        self.assertEqual(40, observation.root_invoke_spans)
        self.assertEqual(20, observation.control_execute_spans)
        self.assertEqual(20, observation.fanout_execute_spans)
        self.assertEqual(40, observation.execute_spans)
        self.assertEqual(2, observation.fanout_surviving_data_source_count)
        self.assertEqual(20, summary["agentCounts"]["executeGap"])
        self.assertTrue(serialized.endswith("\n"))
        self.assertEqual(
            json.dumps(summary, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
            + "\n",
            serialized,
        )
        comparison.scan_public_text(serialized)
        comparison.scan_public_text(comparison.SUCCESS_MARKER + "\n")
        self.assert_no_raw(serialized)

    def test_existing_summary_encoding_remains_byte_stable(self) -> None:
        summary = comparison.build_summary(
            comparison.EXPECTED_ORACLE,
            comparison.analyze_spans(valid_spans()),
            comparison.JunitCounts(tests=1, failures=0, errors=0, skipped=0),
        )
        self.assertEqual(
            "40061ab53689a011c341cf983256e417498380370684b6b5316a10527f767b06",
            hashlib.sha256(comparison.serialize_summary(summary).encode()).hexdigest(),
        )

    def test_agent_only_result_is_exact_isolated_and_privacy_safe(self) -> None:
        observation = comparison.analyze_spans(valid_spans())
        summary = comparison.build_agent_only_summary(
            comparison.EXPECTED_AGENT_ONLY_ORACLE,
            observation,
            comparison.JunitCounts(tests=1, failures=0, errors=0, skipped=0),
        )
        serialized = comparison.serialize_summary(summary)

        self.assertEqual(60, summary["workloadCounts"]["expectedBackingCallbacks"])
        self.assertEqual(60, summary["oracleCounts"]["proxyObservedBackingCallbacks"])
        self.assertEqual(40, summary["agentCounts"]["executeSpans"])
        self.assertEqual(20, summary["agentCounts"]["totalExecuteGap"])
        self.assertEqual(20, summary["agentCounts"]["fanOutExecuteGap"])
        self.assertEqual(
            2,
            summary["agentCounts"]["fanOutSurvivingDataSourceCount"],
        )
        self.assertEqual("1.11.0", summary["versions"]["datasourceProxy"])
        self.assertEqual(
            {
                "routeContractArtifactClasspathEntries": 0,
                "routeContractApiClassPresent": False,
                "routeContractHookClassPresent": False,
                "routeContractSpiProviderPresent": False,
            },
            summary["isolation"],
        )
        comparison.scan_public_text(serialized)
        comparison.scan_public_text(comparison.AGENT_ONLY_SUCCESS_MARKER + "\n")
        self.assert_no_raw(serialized)

    def test_agent_only_aggregate_preserves_surviving_source_cardinality(self) -> None:
        summaries = []
        for surviving_sources in (1, 2):
            summaries.append(
                comparison.build_agent_only_summary(
                    comparison.EXPECTED_AGENT_ONLY_ORACLE,
                    comparison.AgentObservation(
                        root_invoke_spans=40,
                        execute_spans=40,
                        control_execute_spans=20,
                        fanout_execute_spans=20,
                        fanout_surviving_data_source_count=surviving_sources,
                    ),
                    comparison.JunitCounts(
                        tests=1, failures=0, errors=0, skipped=0
                    ),
                )
            )
        self.assertEqual(1, summaries[0]["agentCounts"]["fanOutSurvivingDataSourceCount"])
        self.assertEqual(2, summaries[1]["agentCounts"]["fanOutSurvivingDataSourceCount"])
        self.assertNotEqual(
            comparison.serialize_summary(summaries[0]),
            comparison.serialize_summary(summaries[1]),
        )

    def test_rejects_missing_parent_root_and_required_attributes(self) -> None:
        mutations = []

        missing_parent = valid_spans()
        del missing_parent[1]["parentId"]
        mutations.append(missing_parent)

        missing_root = valid_spans()
        missing_root.pop(0)
        mutations.append(missing_root)

        missing_attribute = valid_spans()
        del missing_attribute[1]["tags"]["peer.port"]  # type: ignore[index]
        mutations.append(missing_attribute)

        parented_root = valid_spans()
        parented_root[0]["parentId"] = "application-parent"
        mutations.append(parented_root)

        failed_status = valid_spans()
        failed_status[1]["tags"]["otel.status_code"] = "ERROR"  # type: ignore[index]
        mutations.append(failed_status)

        for spans in mutations:
            with self.subTest(mutation=len(spans)):
                with self.assertRaises(comparison.ComparisonError) as caught:
                    comparison.analyze_spans(spans)
                self.assert_no_raw(str(caught.exception))

    def test_rejects_extra_and_unclassified_execute_spans(self) -> None:
        extra = valid_spans()
        extra.append(execute_span(99, "control", "ds_0"))

        unclassified = valid_spans()
        unclassified[1]["tags"]["db.statement"] = (  # type: ignore[index]
            "SELECT secret FROM t_order WHERE status = ?"
        )

        for spans in (extra, unclassified):
            with self.subTest(span_count=len(spans)):
                with self.assertRaises(comparison.ComparisonError) as caught:
                    comparison.analyze_spans(spans)
                self.assert_no_raw(str(caught.exception))

    def test_rejects_wrong_projection_table_predicate_and_bind_arity(self) -> None:
        wrong_shapes = (
            "SELECT secret FROM unrelated WHERE user_id = ? AND status = ?",
            "SELECT order_id, user_id, status FROM t_order_9 "
            "WHERE user_id = ? AND status = ?",
            "SELECT order_id, user_id, status FROM t_order_1 "
            "WHERE user_id = ? AND status = ? AND secret = ?",
        )
        mutations: list[list[dict[str, object]]] = []
        for statement in wrong_shapes:
            spans = valid_spans()
            spans[1]["tags"]["db.statement"] = statement  # type: ignore[index]
            mutations.append(spans)
        wrong_binds = valid_spans()
        wrong_binds[1]["tags"]["db.bind_vars"] = "[PAID]"  # type: ignore[index]
        mutations.append(wrong_binds)

        for spans in mutations:
            with self.assertRaises(comparison.ComparisonError) as caught:
                comparison.analyze_spans(spans)
            self.assert_no_raw(str(caught.exception))

    def test_rejects_duplicate_children_and_non_direct_parent(self) -> None:
        duplicate_child = valid_spans()
        duplicate_child[3]["parentId"] = duplicate_child[1]["parentId"]

        wrong_trace = valid_spans()
        wrong_trace[1]["traceId"] = "trace-fanout-00"

        for spans in (duplicate_child, wrong_trace):
            with self.assertRaises(comparison.ComparisonError) as caught:
                comparison.analyze_spans(spans)
            self.assert_no_raw(str(caught.exception))

    def test_oracle_requires_exact_privacy_safe_schema(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            oracle = root / "oracle.json"
            oracle.write_text(
                json.dumps(comparison.EXPECTED_ORACLE) + "\n", encoding="utf-8"
            )
            self.assertEqual(comparison.EXPECTED_ORACLE, comparison.read_oracle(oracle))

            unsafe = dict(comparison.EXPECTED_ORACLE)
            unsafe["raw"] = "SELECT PAID FROM ds_0"
            oracle.write_text(json.dumps(unsafe), encoding="utf-8")
            with self.assertRaises(comparison.ComparisonError) as caught:
                comparison.read_oracle(oracle)
            self.assert_no_raw(str(caught.exception))

    def test_agent_only_oracle_requires_exact_absence_proof(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            oracle = Path(raw) / "agent-only-oracle.json"
            oracle.write_text(
                json.dumps(comparison.EXPECTED_AGENT_ONLY_ORACLE) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                comparison.EXPECTED_AGENT_ONLY_ORACLE,
                comparison.read_agent_only_oracle(oracle),
            )

            mutations = (
                ("routeContractArtifactClasspathEntries", 1),
                ("routeContractApiClassPresent", True),
                ("routeContractHookClassPresent", True),
                ("routeContractSpiProviderPresent", True),
                ("raw", "SELECT PAID FROM ds_0"),
            )
            for key, value in mutations:
                with self.subTest(key=key):
                    unsafe = dict(comparison.EXPECTED_AGENT_ONLY_ORACLE)
                    unsafe[key] = value
                    oracle.write_text(json.dumps(unsafe), encoding="utf-8")
                    with self.assertRaises(comparison.ComparisonError) as caught:
                        comparison.read_agent_only_oracle(oracle)
                    self.assert_no_raw(str(caught.exception))

    def test_junit_parser_uses_only_the_fixed_result_shape(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            results = Path(raw)
            junit = results / f"TEST-{comparison.EXPECTED_JUNIT_SUITE}.xml"
            write_junit(junit)

            counts = comparison.read_junit_counts(results)

            self.assertEqual(
                comparison.JunitCounts(tests=1, failures=0, errors=0, skipped=0),
                counts,
            )
            self.assert_no_raw(repr(counts))

            unsafe = junit.read_text(encoding="utf-8").replace(
                "</testsuite>",
                "<system-out>SELECT PAID FROM ds_0 via jdbc://localhost</system-out>"
                "</testsuite>",
            )
            junit.write_text(unsafe, encoding="utf-8")
            with self.assertRaises(comparison.ComparisonError) as caught:
                comparison.read_junit_counts(results)
            self.assert_no_raw(str(caught.exception))

    def test_agent_only_junit_parser_uses_the_neutral_exact_suite(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            results = Path(raw)
            junit = results / f"TEST-{comparison.AGENT_ONLY_JUNIT_SUITE}.xml"
            write_agent_only_junit(junit)

            counts = comparison.read_junit_counts(
                results,
                expected_suite=comparison.AGENT_ONLY_JUNIT_SUITE,
                expected_method=comparison.AGENT_ONLY_JUNIT_METHOD,
            )
            self.assertEqual(
                comparison.JunitCounts(tests=1, failures=0, errors=0, skipped=0),
                counts,
            )
            with self.assertRaises(comparison.ComparisonError) as caught:
                comparison.read_junit_counts(results)
            self.assert_no_raw(str(caught.exception))

    def test_junit_parser_rejects_forged_suite_level_failure(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            results = Path(raw)
            junit = results / f"TEST-{comparison.EXPECTED_JUNIT_SUITE}.xml"
            write_junit(junit)
            forged = junit.read_text(encoding="utf-8").replace(
                "</testsuite>",
                "<failure>SELECT PAID FROM ds_0</failure></testsuite>",
            )
            junit.write_text(forged, encoding="utf-8")
            with self.assertRaises(comparison.ComparisonError) as caught:
                comparison.read_junit_counts(results)
            self.assert_no_raw(str(caught.exception))

    def test_junit_parser_rejects_non_schema_children_text_and_tail(self) -> None:
        mutations = (
            lambda text: text.replace(
                "hostname='fixture.invalid' time='1.0'>",
                "hostname='fixture.invalid' time='1.0'>forged",
            ),
            lambda text: text.replace(
                "time='1.0'/>",
                "time='1.0'><metadata/></testcase>",
            ),
            lambda text: text.replace(
                "time='1.0'/>",
                "time='1.0'>forged</testcase>",
            ),
            lambda text: text.replace(
                "time='1.0'/>",
                "time='1.0'/>forged",
            ),
        )
        with tempfile.TemporaryDirectory() as raw:
            results = Path(raw)
            junit = results / f"TEST-{comparison.EXPECTED_JUNIT_SUITE}.xml"
            for mutate in mutations:
                with self.subTest(mutation=mutate):
                    write_junit(junit)
                    junit.write_text(
                        mutate(junit.read_text(encoding="utf-8")),
                        encoding="utf-8",
                    )
                    with self.assertRaises(comparison.ComparisonError) as caught:
                        comparison.read_junit_counts(results)
                    self.assert_no_raw(str(caught.exception))

    def test_receiver_accepts_valid_batch_without_logging_raw_data(self) -> None:
        receiver = comparison.ZipkinReceiver(max_body_bytes=64 * 1024, max_requests=4)
        receiver.start()
        try:
            host, port = receiver.address
            connection = http.client.HTTPConnection(host, port, timeout=2)
            payload = json.dumps([execute_span(0, "control", "ds_0")]).encode()
            connection.request(
                "POST",
                comparison.ZIPKIN_PATH,
                body=payload,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            response.read()
            connection.close()
            self.assertEqual(202, response.status)
        finally:
            receiver.stop()

        receiver.raise_if_failed()
        self.assertEqual(1, len(receiver.snapshot()))

    def test_receiver_accepts_official_shaped_gzip_batch(self) -> None:
        receiver = comparison.ZipkinReceiver(max_body_bytes=64 * 1024, max_requests=4)
        receiver.start()
        try:
            host, port = receiver.address
            connection = http.client.HTTPConnection(host, port, timeout=2)
            raw_payload = json.dumps(
                [execute_span(0, "control", "ds_0")]
            ).encode()
            payload = gzip.compress(raw_payload)
            connection.request(
                "POST",
                comparison.ZIPKIN_PATH,
                body=payload,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
            )
            response = connection.getresponse()
            response.read()
            connection.close()
            self.assertEqual(202, response.status)
        finally:
            receiver.stop()

        receiver.raise_if_failed()
        self.assertEqual(1, len(receiver.snapshot()))

    def test_receiver_rejects_bad_trailing_and_oversized_gzip_generically(self) -> None:
        malformed_bodies = (
            gzip.compress(b"[]")[:-2],
            gzip.compress(b"[]") + gzip.compress(b"[]"),
            gzip.compress(b"[]") + b"PAID SELECT",
        )
        for body in malformed_bodies:
            with self.subTest(length=len(body)):
                receiver = comparison.ZipkinReceiver(max_body_bytes=1024)
                status = self._post_gzip(receiver, body)
                self.assertEqual(400, status)
                with self.assertRaises(comparison.ComparisonError) as caught:
                    receiver.raise_if_failed()
                self.assert_no_raw(str(caught.exception))

        receiver = comparison.ZipkinReceiver(
            max_body_bytes=1024,
            max_decoded_body_bytes=32,
            max_decoded_total_bytes=64,
        )
        status = self._post_gzip(receiver, gzip.compress(b"A" * 256))
        self.assertEqual(413, status)
        with self.assertRaises(comparison.ComparisonError) as caught:
            receiver.raise_if_failed()
        self.assert_no_raw(str(caught.exception))

    def _post_gzip(self, receiver: object, body: bytes) -> int:
        receiver.start()
        try:
            host, port = receiver.address
            connection = http.client.HTTPConnection(host, port, timeout=2)
            connection.request(
                "POST",
                comparison.ZIPKIN_PATH,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
            )
            response = connection.getresponse()
            response.read()
            connection.close()
            return response.status
        finally:
            receiver.stop()

    def test_receiver_rejects_malformed_and_oversized_requests_generically(self) -> None:
        cases = (
            (b"[{PAID SELECT", 1024, 400),
            (b"PAID SELECT FROM ds_0", 8, 413),
        )
        for body, limit, expected_status in cases:
            with self.subTest(status=expected_status):
                receiver = comparison.ZipkinReceiver(
                    max_body_bytes=limit, max_requests=2
                )
                receiver.start()
                try:
                    host, port = receiver.address
                    connection = http.client.HTTPConnection(host, port, timeout=2)
                    connection.request(
                        "POST",
                        comparison.ZIPKIN_PATH,
                        body=body,
                        headers={"Content-Type": "application/json"},
                    )
                    response = connection.getresponse()
                    response.read()
                    connection.close()
                    self.assertEqual(expected_status, response.status)
                finally:
                    receiver.stop()

                with self.assertRaises(comparison.ComparisonError) as caught:
                    receiver.raise_if_failed()
                self.assert_no_raw(str(caught.exception))
                self.assertEqual([], receiver.snapshot())

    def test_archive_checksum_and_size_are_both_required(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            archive = Path(raw) / "agent.tar.gz"
            archive.write_bytes(b"fixture archive")
            digest = hashlib.sha512(archive.read_bytes()).hexdigest()

            comparison.verify_archive_file(
                archive, expected_size=archive.stat().st_size, expected_sha512=digest
            )
            for expected_size, expected_digest in (
                (archive.stat().st_size + 1, digest),
                (archive.stat().st_size, "0" * 128),
            ):
                with self.assertRaises(comparison.ComparisonError) as caught:
                    comparison.verify_archive_file(
                        archive,
                        expected_size=expected_size,
                        expected_sha512=expected_digest,
                    )
                self.assert_no_raw(str(caught.exception))

    def test_local_archive_is_staged_from_one_no_follow_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source.tar.gz"
            source.write_bytes(b"verified fixture")
            digest = hashlib.sha512(source.read_bytes()).hexdigest()
            staged = root / "staged.tar.gz"

            comparison.stage_local_archive(
                source,
                staged,
                expected_size=source.stat().st_size,
                expected_sha512=digest,
            )
            source.write_bytes(b"replaced after staging")

            self.assertEqual(b"verified fixture", staged.read_bytes())

            link = root / "linked.tar.gz"
            link.symlink_to(source)
            with self.assertRaises(comparison.ComparisonError) as caught:
                comparison.stage_local_archive(
                    link,
                    root / "must-not-exist.tar.gz",
                    expected_size=source.stat().st_size,
                    expected_sha512=hashlib.sha512(source.read_bytes()).hexdigest(),
                )
            self.assert_no_raw(str(caught.exception))

    def test_safe_tar_extraction_requires_exact_regular_files(self) -> None:
        required = {"agent/conf/agent.yaml", "agent/agent.jar"}
        members = [
            ("agent/conf/", None, tarfile.DIRTYPE),
            ("agent/conf/agent.yaml", b"fixture", tarfile.REGTYPE),
            ("agent/agent.jar", b"jar", tarfile.REGTYPE),
        ]
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            archive = root / "agent.tar.gz"
            archive.write_bytes(tar_bytes(members))
            destination = root / "extract"

            comparison.extract_agent_archive(
                archive, destination, required_files=required
            )

            self.assertEqual(b"fixture", (destination / "agent/conf/agent.yaml").read_bytes())
            self.assertEqual(b"jar", (destination / "agent/agent.jar").read_bytes())

    def test_safe_tar_rejects_traversal_links_specials_duplicates_and_collisions(self) -> None:
        required = {"agent/conf/agent.yaml"}
        attacks = (
            [("../PAID", b"SELECT", tarfile.REGTYPE)],
            [("agent/conf/agent.yaml", None, tarfile.SYMTYPE)],
            [("agent/conf/agent.yaml", None, tarfile.FIFOTYPE)],
            [("agent/conf/agent.yaml/", b"wrong type", tarfile.REGTYPE)],
            [
                ("agent/conf/agent.yaml", b"first", tarfile.REGTYPE),
                ("agent/conf/agent.yaml", b"second", tarfile.REGTYPE),
            ],
            [
                ("agent/conf/agent.yaml", b"first", tarfile.REGTYPE),
                ("AGENT/conf/agent.yaml", b"second", tarfile.REGTYPE),
            ],
            [("agent/unexpected", b"extra", tarfile.REGTYPE)],
        )
        for index, members in enumerate(attacks):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                archive = root / "agent.tar.gz"
                archive.write_bytes(tar_bytes(members))
                with self.assertRaises(comparison.ComparisonError) as caught:
                    comparison.extract_agent_archive(
                        archive, root / "extract", required_files=required
                    )
                self.assert_no_raw(str(caught.exception))

    def test_fixture_versions_are_verified_from_build_and_test_sources(self) -> None:
        versions = comparison.validate_fixture_configuration(REPOSITORY_ROOT)
        self.assertEqual(comparison.EXPECTED_FIXTURE_VERSIONS, versions)
        summary = comparison.build_summary(
            comparison.EXPECTED_ORACLE,
            comparison.analyze_spans(valid_spans()),
            comparison.JunitCounts(tests=1, failures=0, errors=0, skipped=0),
            versions,
        )
        self.assertEqual(17, summary["versions"]["javaMajor"])
        self.assertFalse(summary["privacyClassification"]["rawTelemetryPersisted"])
        self.assertTrue(
            summary["privacyClassification"]["requiredAgentTagsValidated"]
        )

    def test_agent_only_fixture_is_independent_and_version_pinned(self) -> None:
        versions = comparison.validate_agent_only_fixture_configuration(
            REPOSITORY_ROOT
        )
        self.assertEqual(comparison.EXPECTED_AGENT_ONLY_FIXTURE_VERSIONS, versions)
        self.assertEqual("1.11.0", versions["datasourceProxy"])

    def test_failed_capped_process_never_exposes_captured_output(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            command = [
                sys.executable,
                "-c",
                "import sys; print('SELECT PAID ds_0 /private/tmp/secret'); sys.exit(7)",
            ]
            with self.assertRaises(comparison.ComparisonError) as caught:
                comparison.run_capped_process(
                    command,
                    cwd=Path(raw),
                    timeout_seconds=5,
                    max_output_bytes=1024,
                )
            self.assert_no_raw(str(caught.exception))

    def test_gradle_subprocess_environment_excludes_ambient_secret(self) -> None:
        sentinel = "ROUTECONTRACT_SENTINEL_SECRET_MUST_NOT_REACH_GRADLE"
        with tempfile.TemporaryDirectory() as raw, mock.patch.dict(
            os.environ,
            {
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "ROUTECONTRACT_SENTINEL_SECRET": sentinel,
                "GITHUB_TOKEN": sentinel,
                "ORG_GRADLE_PROJECT_password": sentinel,
                "JAVA_TOOL_OPTIONS": sentinel,
            },
            clear=True,
        ):
            environment = comparison._build_gradle_environment(Path(raw))

            self.assertEqual(
                {"PATH", "LANG", "HOME", "GRADLE_USER_HOME", "TMPDIR"},
                set(environment),
            )
            self.assertNotIn(sentinel, environment)
            self.assertNotIn(sentinel, environment.values())
            for key in ("HOME", "GRADLE_USER_HOME", "TMPDIR"):
                directory = Path(environment[key])
                self.assertTrue(directory.is_dir())
                self.assertTrue(directory.is_relative_to(Path(raw)))
                self.assertEqual(0o700, directory.stat().st_mode & 0o777)

    def test_summary_writer_refuses_symlinked_ancestors_and_exactly_verifies_output(self) -> None:
        observation = comparison.analyze_spans(valid_spans())
        summary = comparison.build_summary(
            comparison.EXPECTED_ORACLE,
            observation,
            comparison.JunitCounts(tests=1, failures=0, errors=0, skipped=0),
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            external = root / "external"
            external.mkdir()
            target = external / "summary.json"
            target.write_text("preserve\n", encoding="utf-8")
            repository = root / "repository"
            repository.mkdir()
            (repository / "build").symlink_to(external, target_is_directory=True)

            with self.assertRaises(comparison.ComparisonError) as caught:
                comparison._remove_stale_repository_summary(repository)

            self.assertEqual("preserve\n", target.read_text(encoding="utf-8"))
            self.assert_no_raw(str(caught.exception))

            (repository / "build").unlink()
            comparison._remove_stale_repository_summary(repository)
            comparison._write_repository_summary(repository, summary)
            comparison.verify_repository_summary(repository)
            written = repository / "build" / "agent-comparison" / "summary.json"
            self.assertEqual(
                comparison.serialize_summary(summary),
                written.read_text(encoding="utf-8"),
            )

            payload = json.loads(written.read_text(encoding="utf-8"))
            payload["rawExtra"] = "SELECT PAID FROM ds_0"
            written.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.assertRaises(comparison.ComparisonError) as caught:
                comparison.verify_repository_summary(repository)
            self.assert_no_raw(str(caught.exception))

    def test_summary_verifier_rejects_symlink_and_extra_file_upload_bypass(self) -> None:
        observation = comparison.analyze_spans(valid_spans())
        summary = comparison.build_summary(
            comparison.EXPECTED_ORACLE,
            observation,
            comparison.JunitCounts(tests=1, failures=0, errors=0, skipped=0),
        )
        with tempfile.TemporaryDirectory() as raw:
            repository = Path(raw) / "repository"
            repository.mkdir()
            comparison._write_repository_summary(repository, summary)
            output = repository / "build" / "agent-comparison"
            target = Path(raw) / "external.json"
            target.write_text(comparison.serialize_summary(summary), encoding="utf-8")
            (output / "summary.json").unlink()
            (output / "summary.json").symlink_to(target)
            (output / "dummy.json").write_text("{}\n", encoding="utf-8")

            with self.assertRaises(comparison.ComparisonError) as caught:
                comparison.verify_repository_summary(repository)
            self.assert_no_raw(str(caught.exception))

    def test_agent_only_summary_uses_a_distinct_exact_output_contract(self) -> None:
        summary = comparison.build_agent_only_summary(
            comparison.EXPECTED_AGENT_ONLY_ORACLE,
            comparison.analyze_spans(valid_spans()),
            comparison.JunitCounts(tests=1, failures=0, errors=0, skipped=0),
        )
        with tempfile.TemporaryDirectory() as raw:
            repository = Path(raw) / "repository"
            repository.mkdir()
            comparison._write_repository_summary(
                repository,
                summary,
                output_directory=comparison.AGENT_ONLY_OUTPUT_DIRECTORY,
            )
            comparison.verify_agent_only_repository_summary(repository)
            output = repository / "build" / comparison.AGENT_ONLY_OUTPUT_DIRECTORY
            self.assertEqual([output / "summary.json"], list(output.iterdir()))

            payload = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            payload["junitCounts"]["tests"] = True
            (output / "summary.json").write_text(
                comparison.serialize_summary(payload),
                encoding="utf-8",
            )
            with self.assertRaises(comparison.ComparisonError) as caught:
                comparison.verify_agent_only_repository_summary(repository)
            self.assert_no_raw(str(caught.exception))

            comparison._write_repository_summary(
                repository,
                summary,
                output_directory=comparison.AGENT_ONLY_OUTPUT_DIRECTORY,
            )
            payload = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            payload["rawExtra"] = "SELECT PAID FROM ds_0"
            (output / "summary.json").write_text(
                json.dumps(payload) + "\n", encoding="utf-8"
            )
            with self.assertRaises(comparison.ComparisonError) as caught:
                comparison.verify_agent_only_repository_summary(repository)
            self.assert_no_raw(str(caught.exception))

    def test_main_converts_unexpected_exceptions_to_one_fixed_marker(self) -> None:
        error_output = io.StringIO()
        with mock.patch.object(
            comparison,
            "run_comparison",
            side_effect=KeyError(
                "SELECT PAID FROM ds_0 via jdbc://localhost /private/tmp/secret"
            ),
        ), contextlib.redirect_stderr(error_output):
            result = comparison.main([])

        self.assertEqual(1, result)
        self.assertEqual(comparison.FAILURE_MARKER + "\n", error_output.getvalue())
        self.assert_no_raw(error_output.getvalue())

    def test_agent_only_main_uses_one_fixed_failure_marker(self) -> None:
        error_output = io.StringIO()
        with mock.patch.object(
            comparison,
            "run_agent_only_reproducer",
            side_effect=KeyError(
                "SELECT PAID FROM ds_0 via jdbc://localhost /private/tmp/secret"
            ),
        ), contextlib.redirect_stderr(error_output):
            result = comparison.main(["--agent-only"])

        self.assertEqual(1, result)
        self.assertEqual(
            comparison.AGENT_ONLY_FAILURE_MARKER + "\n",
            error_output.getvalue(),
        )
        self.assert_no_raw(error_output.getvalue())


if __name__ == "__main__":
    unittest.main()
