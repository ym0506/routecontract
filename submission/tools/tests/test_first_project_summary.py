import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
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
        self.outcomes = dict.fromkeys(("capture", "match", "range", "restored", "direct"), "success")
        for key, _, status, count in SUMMARY.STAGES:
            directory = self.root / key
            directory.mkdir()
            report = {"status": status, "matched": key != "range",
                      "strictExitCode": 1 if key == "range" else 0,
                      "candidate": {"captureStatus": "COMPLETE",
                                    "observedPhysicalAttemptCount": count,
                                    "distinctObservedDataSourceNameCount": count},
                      "findings": [{"code": code} for code in
                                   (["RCM201", "RCM202"] if key == "range" else ["RCM000"])]}
            (directory / "review.json").write_text(json.dumps(report))
        self.direct_path = self.root / "direct-assertions/maven/summary.json"
        self.direct_path.parent.mkdir(parents=True)
        self.direct = {
            "buildTool": "Maven", "libraryVersion": "0.1.3", "javaFeature": 17,
            "exampleClassMajor": 61, "libraryClassMajor": 61,
            "publicJarSha256": "9e883e618eb09d9ecf30814151bb4b0a43eba02c78d288cc582fa7e57e6edba2",
            "stages": [
                {"stage": stage, "query": query, "exitCode": exit_code,
                 "businessAssertionPassed": True, "observedAttempts": count,
                 "observedDataSources": count, "manifestFilesUnchanged": True}
                for stage, query, exit_code, count in (
                    ("match", "equality", 0, 1), ("range", "range", 1, 2),
                    ("restored", "equality", 0, 1))]}
        self.direct_path.write_text(json.dumps(self.direct))

    def run_cli(self, java="17", build="Maven"):
        env = {**os.environ, "BUILD_TOOL": build, "ROUTECONTRACT_EXAMPLE_JAVA_VERSION": java,
               **{f"{key.upper()}_OUTCOME": value for key, value in self.outcomes.items()}}
        return subprocess.run([sys.executable, str(SPEC.origin), str(self.root)],
                              env=env, text=True, capture_output=True, check=False)

    def test_java21_summary_identifies_verified_runtime_and_artifact(self):
        self.direct.update(javaFeature=21, exampleClassMajor=65)
        self.direct_path.write_text(json.dumps(self.direct))
        result = self.run_cli(java="21")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Verified test runtime: **Java 21**", result.stdout)
        self.assertIn("first-project-Maven-java21", result.stdout)
        self.assertNotIn("· Java **17**", result.stdout)

    def test_failed_direct_step_cannot_claim_completion_using_leftover_summary(self):
        for outcome in ("failure", "skipped", "cancelled", ""):
            with self.subTest(outcome=outcome):
                self.outcomes["direct"] = outcome
                result = self.run_cli()
                self.assertEqual(1, result.returncode)
                self.assertIn("Demonstration incomplete", result.stdout)
                self.assertNotIn("Demonstration complete.", result.stdout)

    def test_selected_java21_cannot_verify_java17_evidence(self):
        result = self.run_cli(java="21")
        self.assertEqual(1, result.returncode)
        self.assertIn("Test runtime: **Not verified**", result.stdout)

    def test_missing_direct_evidence_cannot_claim_completion(self):
        self.direct_path.unlink()
        result = self.run_cli()
        self.assertEqual(1, result.returncode)
        self.assertIn("Demonstration incomplete", result.stdout)

    def test_both_build_tools_and_jdks_report_only_the_selected_artifact(self):
        for build in ("Maven", "Gradle"):
            for java in (17, 21):
                with self.subTest(build=build, java=java):
                    report = {**self.direct, "buildTool": build, "javaFeature": java,
                              "exampleClassMajor": java + 44}
                    path = self.root / "direct-assertions" / build.lower() / "summary.json"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(report))
                    result = self.run_cli(str(java), build)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertIn(f"Verified test runtime: **Java {java}**", result.stdout)
                    artifact = f"first-project-{build}" + ("-java21" if java == 21 else "")
                    self.assertIn(f"Download **{artifact}**", result.stdout)

    def test_invalid_direct_identity_and_stage_evidence_is_not_verified(self):
        mutations = [
            {"libraryVersion": "0.2.0"}, {"buildTool": "Gradle"},
            {"javaFeature": True}, {"exampleClassMajor": 61.0},
            {"libraryClassMajor": 65}, {"publicJarSha256": "0" * 64},
            {"stages": []}, {"stages": self.direct["stages"][:2]},
            {"stages": [self.direct["stages"][0]] * 3},
        ]
        for field, value in (("exitCode", 0), ("exitCode", -9), ("observedAttempts", True),
                             ("observedDataSources", "2"), ("businessAssertionPassed", False),
                             ("manifestFilesUnchanged", False), ("query", "equality")):
            stages = [dict(stage) for stage in self.direct["stages"]]
            stages[1][field] = value
            mutations.append({"stages": stages})
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.direct_path.write_text(json.dumps({**self.direct, **mutation}))
                result = self.run_cli()
                self.assertEqual(1, result.returncode)
                self.assertIn("Test runtime: **Not verified**", result.stdout)
                self.assertNotIn("Demonstration complete.", result.stdout)

    def test_malformed_evidence_and_untrusted_context_are_not_echoed(self):
        for value in ("{", "null", "[]", '{"secret":"private-value"}'):
            with self.subTest(value=value):
                self.direct_path.write_text(value)
                result = self.run_cli()
                self.assertEqual(1, result.returncode)
                self.assertNotIn("private-value", result.stdout + result.stderr)
        result = self.run_cli(java="21\n::error::private-value", build="<script>private-value</script>")
        self.assertEqual(1, result.returncode)
        self.assertNotIn("private-value", result.stdout + result.stderr)

    def test_complete_rehearsal_explains_expected_rejection_and_recovery(self):
        text, complete = SUMMARY.render(self.root, self.outcomes)
        self.assertTrue(complete)
        self.assertIn("POLICY_VIOLATION | 2 | 2", text)
        self.assertIn("3. Normal query restored | Verified | MATCH | 1 | 1", text)
        self.assertIn("All required demonstration stages verified", text)
        self.assertNotIn("workflow is green", text)

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
