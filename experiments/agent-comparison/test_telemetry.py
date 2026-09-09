"""Synthetic verifier controls. These are not native Agent executions."""
import copy
import gzip
import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from telemetry import (ComparisonError, CONTROL_STATEMENT, EXECUTE_SPAN_NAME,
                       FANOUT_STATEMENT, ROOT_SPAN_NAME, ZipkinReceiver, analyze_spans)


def fixture(children=2):
    spans = []
    for index in range(40):
        trace = f"{index + 1:032x}"
        root = {"traceId": trace, "id": "0000000000000001", "name": ROOT_SPAN_NAME}
        spans.append(root)
        control = index % 2 == 0
        for child in range(1 if control else children):
            spans.append({
                "traceId": trace, "id": f"{child + 2:016x}",
                "parentId": root["id"], "name": EXECUTE_SPAN_NAME,
                "tags": {"db.statement": CONTROL_STATEMENT if control else FANOUT_STATEMENT,
                         "db.bind_vars": "[3, PAID]" if control else "[3, 3, PAID, 3, 3, PAID]",
                         "db.instance": "ds_1" if control or child == 0 else "ds_0",
                         "peer.hostname": "fixture-host", "peer.port": "1234",
                         "otel.status_code": "OK"},
            })
    return spans


class ClassificationTest(unittest.TestCase):
    def test_all_physical_children_are_a_valid_outcome(self):
        result = analyze_spans(fixture(2))
        self.assertEqual(60, result["executeSpans"])
        self.assertEqual({"oneChild": 0, "twoChildren": 20}, result["fanoutChildrenPerRoot"])
        self.assertTrue(result["fanoutMatchesPhysicalOracle"])

    def test_fewer_fanout_children_are_reported_without_assuming_a_cause(self):
        result = analyze_spans(fixture(1))
        self.assertEqual(40, result["executeSpans"])
        self.assertEqual({"oneChild": 20, "twoChildren": 0}, result["fanoutChildrenPerRoot"])
        self.assertFalse(result["fanoutMatchesPhysicalOracle"])

    def test_mixed_fanout_results_are_not_hidden_in_a_total(self):
        spans = fixture(2)
        del spans[4]
        self.assertEqual({"oneChild": 1, "twoChildren": 19},
                         analyze_spans(spans)["fanoutChildrenPerRoot"])

    def test_invalid_evidence_is_rejected(self):
        cases = []
        spans = fixture(); del spans[0]; cases.append((spans, "ROOT_COUNT"))
        spans = fixture(); spans.append(copy.deepcopy(spans[1])); cases.append((spans, "SPAN_DUPLICATE"))
        spans = fixture(); spans[1]["parentId"] = "missing"; cases.append((spans, "EXECUTE_PARENT"))
        spans = fixture(); del spans[1]; cases.append((spans, "ROOT_WITHOUT_EXECUTE"))
        spans = fixture(); spans[1]["tags"]["otel.status_code"] = "ERROR"; cases.append((spans, "EXECUTE_STATUS"))
        spans = fixture(); spans[1]["tags"]["db.instance"] = "unknown"; cases.append((spans, "UNREVIEWED_DATA_SOURCE"))
        spans = fixture(); spans[1]["tags"]["db.statement"] = "unexpected"; cases.append((spans, "EXECUTE_UNCLASSIFIED"))
        spans = fixture(); extra = copy.deepcopy(spans[1]); extra["id"] = "00000000000000ff"
        spans.append(extra); cases.append((spans, "CONTROL_CARDINALITY"))
        for spans, code in cases:
            with self.subTest(code=code), self.assertRaises(ComparisonError) as caught:
                analyze_spans(spans)
            self.assertEqual(code, caught.exception.code)


class ReceiverTest(unittest.TestCase):
    def test_loopback_receiver_accepts_json_and_rejects_oversized_input(self):
        receiver = ZipkinReceiver(max_body_bytes=128)
        receiver.start()
        try:
            host, port = receiver.address
            self.assertEqual("127.0.0.1", host)
            url = f"http://{host}:{port}/api/v2/spans"
            request = Request(url, data=json.dumps([{"name": "synthetic"}]).encode(),
                              headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=5) as response:
                self.assertEqual(202, response.status)
            self.assertEqual(1, len(receiver.snapshot()))
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(url, data=b"x" * 129,
                                headers={"Content-Type": "application/json"}), timeout=5)
            self.assertEqual(413, caught.exception.code)
            with self.assertRaises(ComparisonError):
                receiver.raise_if_failed()
        finally:
            receiver.stop()

    def test_compressed_decoded_limit_is_enforced(self):
        receiver = ZipkinReceiver(max_decoded_body_bytes=128)
        try:
            with self.assertRaises(ComparisonError):
                receiver._decode_body(gzip.compress(b"x" * 129), "gzip")
        finally:
            receiver.stop()


if __name__ == "__main__":
    unittest.main()
