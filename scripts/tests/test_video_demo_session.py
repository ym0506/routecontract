import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VIDEO_DEMO_SCRIPT = REPOSITORY_ROOT / "scripts" / "video-demo-session.sh"

MYSQL_MARKER = (
    "ROUTECONTRACT_MANIFEST_DEMO businessResult=UNCHANGED "
    "observedPhysicalAttempts=1->2 verificationStatus=POLICY_VIOLATION "
    "blockingCodes=[RCM201,RCM202] privacy=MINIMIZED"
)
FINGERPRINT_MARKER = (
    "ROUTECONTRACT_FINGERPRINT_DRIFT_DEMO businessResult=UNCHANGED "
    "observedPhysicalAttempts=1->1 observedDataSourceAliases="
    "[orders-odd]->[orders-odd] fingerprintMultiset=CHANGED "
    "parameterTypeShape=[Long]->[Long,Long] verificationStatus=DRIFT "
    "blockingCodes=[RCM301,RCM302] privacy=MINIMIZED"
)
CI_MARKER = (
    "ROUTECONTRACT_FILE_CI_DEMO approvedAttempts=1 candidateAttempts=2 "
    "status=POLICY_VIOLATION blockingCodes=[RCM201,RCM202]"
)
RCM201 = "RCM201 BLOCKING ATTEMPT_BUDGET_EXCEEDED: maximum=1, observed=2"
RCM202 = "RCM202 BLOCKING DATA_SOURCE_BUDGET_EXCEEDED: maximum=1, observed=2"


class VideoDemoSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.fake_repository = Path(self.temporary_directory.name)
        self.fake_scripts = self.fake_repository / "scripts"
        self.fake_scripts.mkdir()
        self.wrapper = self.fake_scripts / "video-demo-session.sh"
        shutil.copy2(VIDEO_DEMO_SCRIPT, self.wrapper)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_executable(self, path: Path, body: str) -> None:
        path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body, encoding="utf-8")
        path.chmod(0o755)

    def run_wrapper(
        self,
        *arguments: str,
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["LC_ALL"] = "C"
        if extra_environment:
            environment.update(extra_environment)
        return subprocess.run(
            [str(self.wrapper), *arguments],
            cwd=self.fake_repository,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def git(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.fake_repository,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout.strip()

    def initialize_recording_repository(self) -> dict[str, str]:
        self.git("init")
        self.git("config", "user.name", "RouteContract test")
        self.git("config", "user.email", "routecontract-test@example.invalid")
        self.git("remote", "add", "origin", "https://github.com/ym0506/routecontract.git")
        self.git("add", ".")
        self.git("commit", "-m", "recording fixture")
        self.git("tag", "-a", "v0.1.0", "-m", "recording fixture tag")
        return {
            "ROUTECONTRACT_FINAL_COMMIT": self.git("rev-parse", "HEAD^{commit}"),
            "ROUTECONTRACT_FINAL_TREE": self.git("rev-parse", "HEAD^{tree}"),
            "ROUTECONTRACT_FINAL_ORIGIN": "https://github.com/ym0506/routecontract",
            "ROUTECONTRACT_FINAL_TAG": "v0.1.0",
        }

    def test_mysql_and_fingerprint_emit_only_extracted_markers_and_verified_exits(self) -> None:
        self.write_executable(
            self.fake_scripts / "run-demo.sh",
            "printf '%s\\n' 'private_path=/Users/redacted/work' "
            f"'    {MYSQL_MARKER}' '{MYSQL_MARKER}'\n",
        )
        mysql = self.run_wrapper("mysql")

        self.assertEqual(0, mysql.returncode, mysql.stderr)
        self.assertEqual(
            [
                "video_phase=mysql status=RUNNING child_output=WITHHELD_UNTIL_VERIFIED",
                MYSQL_MARKER,
                "verified_child_exit     0",
            ],
            mysql.stdout.splitlines(),
        )
        self.assertNotIn("/Users/", mysql.stdout)

        self.write_executable(
            self.fake_repository / "gradlew",
            "printf '%s\\n' 'jdbc:private' "
            f"'    {FINGERPRINT_MARKER}'\n",
        )
        fingerprint = self.run_wrapper("fingerprint")

        self.assertEqual(0, fingerprint.returncode, fingerprint.stderr)
        self.assertEqual(
            [
                "video_phase=fingerprint status=RUNNING child_output=WITHHELD_UNTIL_VERIFIED",
                f"    {FINGERPRINT_MARKER}",
                "verified_child_exit     0",
            ],
            fingerprint.stdout.splitlines(),
        )
        self.assertNotIn("jdbc:private", fingerprint.stdout)

    def test_ci_emits_actual_matched_lines_including_dynamic_build_failure(self) -> None:
        self.write_executable(
            self.fake_scripts / "demo-manifest-ci-failure.sh",
            "printf '%s\\n' 'container_id=private' "
            f"'    {CI_MARKER}' '    - {RCM201}' '    - {RCM202}' "
            "'BUILD FAILED in 7s'\nexit 1\n",
        )
        result = self.run_wrapper("ci")

        self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual(
            [
                "video_phase=ci status=RUNNING child_output=WITHHELD_UNTIL_VERIFIED",
                f"    {CI_MARKER}",
                f"    - {RCM201}",
                f"    - {RCM202}",
                "BUILD FAILED in 7s",
                "verified_child_exit     1",
            ],
            result.stdout.splitlines(),
        )
        self.assertNotIn("container_id=private", result.stdout)
        self.assertNotIn("BUILD FAILED (intentional)", result.stdout)

    def test_ambiguous_marker_is_withheld_and_returns_wrapper_error(self) -> None:
        self.write_executable(
            self.fake_scripts / "run-demo.sh",
            f"printf '%s\\n' '{MYSQL_MARKER}' '{MYSQL_MARKER}'\n",
        )
        result = self.run_wrapper("mysql")

        self.assertEqual(2, result.returncode)
        self.assertNotIn(MYSQL_MARKER, result.stdout)
        self.assertIn("VIDEO_DEMO_ERROR", result.stderr)
        self.assertIn("raw_output=WITHHELD_FOR_PRIVACY", result.stderr)

    def test_ci_rejects_evidence_lines_with_extra_private_text(self) -> None:
        cases = (
            (
                "rcm-prefix",
                f"'/Users/private - {RCM201}' '    - {RCM202}' "
                "'BUILD FAILED in 7s'",
            ),
            (
                "build-suffix",
                f"'    - {RCM201}' '    - {RCM202}' "
                "'BUILD FAILED in 7s private_path=/Users/private'",
            ),
        )
        for label, evidence_lines in cases:
            with self.subTest(label=label):
                self.write_executable(
                    self.fake_scripts / "demo-manifest-ci-failure.sh",
                    f"printf '%s\\n' '    {CI_MARKER}' {evidence_lines}\nexit 1\n",
                )
                result = self.run_wrapper("ci")

                self.assertEqual(2, result.returncode)
                self.assertNotIn("/Users/private", result.stdout)
                self.assertNotIn(RCM201, result.stdout)
                self.assertNotIn("BUILD FAILED", result.stdout)
                self.assertIn("VIDEO_DEMO_ERROR", result.stderr)

    def test_final_recording_mode_requires_exact_clean_annotated_revision(self) -> None:
        self.write_executable(
            self.fake_scripts / "run-demo.sh",
            f"printf '%s\\n' '{MYSQL_MARKER}'\n",
        )
        expected = self.initialize_recording_repository()

        verified = self.run_wrapper(
            "--final-recording",
            "mysql",
            extra_environment=expected,
        )
        self.assertEqual(0, verified.returncode, verified.stderr)
        self.assertEqual(
            "video_recording_preflight status=VERIFIED",
            verified.stdout.splitlines()[0],
        )
        self.assertIn(MYSQL_MARKER, verified.stdout)

        local_origin = str(self.fake_repository)
        self.git("remote", "set-url", "origin", local_origin)
        rewritten_origin = self.run_wrapper(
            "--final-recording",
            "mysql",
            extra_environment={
                **expected,
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": (
                    "url.https://github.com/ym0506/routecontract.insteadOf"
                ),
                "GIT_CONFIG_VALUE_0": local_origin,
            },
        )
        self.assertEqual(2, rewritten_origin.returncode)
        self.assertNotIn(MYSQL_MARKER, rewritten_origin.stdout)
        self.assertIn("check=origin", rewritten_origin.stderr)
        self.git(
            "remote",
            "set-url",
            "origin",
            "https://github.com/ym0506/routecontract.git",
        )

        self.git(
            "config",
            "--add",
            "remote.origin.url",
            "https://github.com/other/routecontract.git",
        )
        ambiguous_origin = self.run_wrapper(
            "--final-recording",
            "mysql",
            extra_environment=expected,
        )
        self.assertEqual(2, ambiguous_origin.returncode)
        self.assertNotIn(MYSQL_MARKER, ambiguous_origin.stdout)
        self.assertIn("check=origin", ambiguous_origin.stderr)
        self.git("config", "--unset-all", "remote.origin.url")
        self.git(
            "config",
            "remote.origin.url",
            "https://github.com/ym0506/routecontract.git",
        )

        cases = (
            ("commit", {"ROUTECONTRACT_FINAL_COMMIT": "f" * 40}),
            ("tree", {"ROUTECONTRACT_FINAL_TREE": "e" * 40}),
            (
                "origin",
                {"ROUTECONTRACT_FINAL_ORIGIN": "https://github.com/other/repository"},
            ),
            ("tag", {"ROUTECONTRACT_FINAL_TAG": "v0.1.1"}),
        )
        for label, override in cases:
            with self.subTest(label=label):
                result = self.run_wrapper(
                    "--final-recording",
                    "mysql",
                    extra_environment={**expected, **override},
                )
                self.assertEqual(2, result.returncode)
                self.assertNotIn(MYSQL_MARKER, result.stdout)
                self.assertIn("VIDEO_DEMO_ERROR phase=recording_preflight", result.stderr)

        (self.fake_repository / "untracked.txt").write_text("dirty", encoding="utf-8")
        dirty = self.run_wrapper(
            "--final-recording",
            "mysql",
            extra_environment=expected,
        )
        self.assertEqual(2, dirty.returncode)
        self.assertNotIn(MYSQL_MARKER, dirty.stdout)
        self.assertIn("check=clean_worktree", dirty.stderr)

    def test_final_recording_mode_rejects_missing_contract_and_lightweight_tag(self) -> None:
        self.write_executable(
            self.fake_scripts / "run-demo.sh",
            f"printf '%s\\n' '{MYSQL_MARKER}'\n",
        )
        expected = self.initialize_recording_repository()

        missing = self.run_wrapper("--final-recording", "mysql")
        self.assertEqual(2, missing.returncode)
        self.assertNotIn(MYSQL_MARKER, missing.stdout)
        self.assertIn("check=expected_commit", missing.stderr)

        self.git("tag", "v0.1.1")
        lightweight = self.run_wrapper(
            "--final-recording",
            "mysql",
            extra_environment={**expected, "ROUTECONTRACT_FINAL_TAG": "v0.1.1"},
        )
        self.assertEqual(2, lightweight.returncode)
        self.assertNotIn(MYSQL_MARKER, lightweight.stdout)
        self.assertIn("check=annotated_tag", lightweight.stderr)


if __name__ == "__main__":
    unittest.main()
