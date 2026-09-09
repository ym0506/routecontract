import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "first_project_summary", Path(__file__).resolve().parents[1] / "summarize_first_project.py")
SUMMARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUMMARY)


class FirstProjectSummaryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.outcomes = dict.fromkeys(("capture", "match", "range", "restored"), "success")
        for key, _, status, count in SUMMARY.STAGES:
            directory = self.root / key
            directory.mkdir()
            report = {"status": status, "matched": key != "range",
                      "strictExitCode": 1 if key == "range" else 0,
                      "candidate": {"captureStatus": "COMPLETE",
                                    "observedPhysicalAttemptCount": count,
                                    "distinctObservedDataSourceNameCount": count},
                      "findings": [{"code": code} for code in
                                   (["RCM201", "RCM202"] if key == "range" else [])]}
            (directory / "review.json").write_text(json.dumps(report))

    def test_complete_rehearsal_explains_expected_rejection_and_recovery(self):
        text, complete = SUMMARY.render(self.root, self.outcomes)
        self.assertTrue(complete)
        self.assertIn("POLICY_VIOLATION | 2 | 2", text)
        self.assertIn("3. Normal query restored | Verified | MATCH | 1 | 1", text)
        self.assertIn("workflow is green because", text)

    def test_missing_restoration_keeps_prior_evidence_but_is_incomplete(self):
        (self.root / "restored" / "review.json").unlink()
        text, complete = SUMMARY.render(self.root, self.outcomes)
        self.assertFalse(complete)
        self.assertIn("Demonstration incomplete", text)
        self.assertIn("POLICY_VIOLATION | 2 | 2", text)
        self.assertIn("3. Normal query restored | Not verified", text)

    def test_failed_or_skipped_step_cannot_use_leftover_report(self):
        for outcome in ("failure", "skipped", "cancelled", ""):
            with self.subTest(outcome=outcome):
                self.outcomes["range"] = outcome
                text, complete = SUMMARY.render(self.root, self.outcomes)
                self.assertFalse(complete)
                self.assertNotIn("POLICY_VIOLATION | 2 | 2", text)

    def test_unverified_capture_prevents_completed_demo(self):
        self.outcomes["capture"] = "failure"
        self.assertFalse(SUMMARY.render(self.root, self.outcomes)[1])

    def test_malformed_or_unexpected_report_does_not_render_as_success(self):
        path = self.root / "range" / "review.json"
        original = json.loads(path.read_text())
        for value in ("{", "null", "[]", json.dumps({**original, "status": "MATCH"}),
                      json.dumps({**original, "findings": []}),
                      json.dumps({**original, "strictExitCode": True})):
            with self.subTest(value=value):
                path.write_text(value)
                text, complete = SUMMARY.render(self.root, self.outcomes)
                self.assertFalse(complete)
                self.assertNotIn("POLICY_VIOLATION | 2 | 2", text)

    def test_boolean_or_free_form_count_is_never_a_valid_observation(self):
        path = self.root / "match" / "review.json"
        report = json.loads(path.read_text())
        for value in (True, "1", "<img src=x>", -1):
            with self.subTest(value=value):
                report["candidate"]["observedPhysicalAttemptCount"] = value
                path.write_text(json.dumps(report))
                text, complete = SUMMARY.render(self.root, self.outcomes)
                self.assertFalse(complete)
                self.assertNotIn("<img", text)


if __name__ == "__main__":
    unittest.main()
