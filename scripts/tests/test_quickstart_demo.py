import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


MYSQL_MARKER = (
    "ROUTECONTRACT_MANIFEST_DEMO businessResult=UNCHANGED "
    "observedPhysicalAttempts=1->2 verificationStatus=POLICY_VIOLATION "
    "blockingCodes=[RCM201,RCM202] privacy=MINIMIZED"
)
CI_MARKER = (
    "ROUTECONTRACT_FILE_CI_DEMO approvedAttempts=1 candidateAttempts=2 "
    "status=POLICY_VIOLATION blockingCodes=[RCM201,RCM202]"
)


class QuickstartDemoContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.scripts = self.root / "scripts"
        self.bin = self.root / "bin"
        self.scripts.mkdir()
        self.bin.mkdir()

        source = Path(__file__).resolve().parents[1] / "quickstart-demo.sh"
        quickstart = self.scripts / "quickstart-demo.sh"
        shutil.copyfile(source, quickstart)
        self.make_executable(quickstart)

        self.write_executable(
            self.root / "gradlew",
            "#!/usr/bin/env bash\nexit 0\n",
        )
        self.write_executable(
            self.bin / "java",
            "#!/usr/bin/env bash\nprintf '%s\\n' 'openjdk version \"17.0.20\"' >&2\n",
        )
        self.write_executable(
            self.bin / "docker",
            "#!/usr/bin/env bash\n[[ \"${1:-}\" == info ]]\n",
        )
        self.write_executable(
            self.scripts / "video-demo-session.sh",
            f"""#!/usr/bin/env bash
case "${{QUICKSTART_TEST_SCENARIO:-current}}:${{1:-}}" in
    current:mysql)
        printf '%s\\n' '{MYSQL_MARKER}' 'verified_child_exit     0'
        exit 0
        ;;
    current:ci)
        printf '%s\\n' \\
            '{CI_MARKER}' \\
            '- RCM201 BLOCKING ATTEMPT_BUDGET_EXCEEDED: maximum=1, observed=2' \\
            '- RCM202 BLOCKING DATA_SOURCE_BUDGET_EXCEEDED: maximum=1, observed=2' \\
            'BUILD FAILED in 1s' \\
            'verified_child_exit     1'
        exit 1
        ;;
    legacy:mysql)
        printf '%s\\n' \\
            'businessResult          UNCHANGED (one row in both captures)' \\
            'observedAttempts        1 -> 2' \\
            'observedDataSources     1 -> 2' \\
            'RCM201                  ATTEMPT_BUDGET_EXCEEDED: maximum=1, observed=2' \\
            'RCM202                  DATA_SOURCE_BUDGET_EXCEEDED: maximum=1, observed=2' \\
            'demo_exit               0'
        exit 0
        ;;
    *)
        exit 2
        ;;
esac
""",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @staticmethod
    def make_executable(path: Path) -> None:
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def write_executable(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        self.make_executable(path)

    def run_quickstart(self, scenario: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PATH"] = f"{self.bin}{os.pathsep}{environment['PATH']}"
        environment["QUICKSTART_TEST_SCENARIO"] = scenario
        return subprocess.run(
            [str(self.scripts / "quickstart-demo.sh")],
            cwd=self.root,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_accepts_current_privacy_reviewed_video_contract(self) -> None:
        result = self.run_quickstart("current")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("[ROUTECONTRACT QUICKSTART VERIFIED]", result.stdout)
        self.assertIn("quickstartExit         0", result.stdout)
        self.assertNotIn("ROUTECONTRACT_MANIFEST_DEMO", result.stdout)

    def test_rejects_legacy_reformatted_contract(self) -> None:
        result = self.run_quickstart("legacy")

        self.assertEqual(2, result.returncode)
        self.assertIn("QUICKSTART_ERROR phase=mysql", result.stderr)
        self.assertIn("child_output=WITHHELD_FOR_PRIVACY", result.stderr)
        self.assertNotIn("businessResult", result.stderr)


if __name__ == "__main__":
    unittest.main()
