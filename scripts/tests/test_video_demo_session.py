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

    def run_wrapper(self, mode: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["LC_ALL"] = "C"
        return subprocess.run(
            [str(self.wrapper), mode],
            cwd=self.fake_repository,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

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


if __name__ == "__main__":
    unittest.main()
