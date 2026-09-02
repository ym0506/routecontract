import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "atomic-central-staging.py"
WORK_NAME = ".repository.routecontract-work"
FINAL_NAME = "repository"


class AtomicCentralStagingTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="routecontract-atomic-central-"
        )
        self.parent = Path(self.temporary.name).resolve()
        self.parent.chmod(0o700)
        self.work = self.parent / WORK_NAME
        self.work.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def run_tool(self, *, parent_inode=None, work_inode=None):
        parent_stat = self.parent.stat()
        work_stat = os.stat(self.work, follow_symlinks=False)
        return subprocess.run(
            [
                sys.executable,
                "-I",
                os.fspath(TOOL),
                "--parent",
                os.fspath(self.parent),
                "--work-name",
                WORK_NAME,
                "--final-name",
                FINAL_NAME,
                "--expected-parent-device",
                str(parent_stat.st_dev),
                "--expected-parent-inode",
                str(parent_stat.st_ino if parent_inode is None else parent_inode),
                "--expected-work-device",
                str(work_stat.st_dev),
                "--expected-work-inode",
                str(work_stat.st_ino if work_inode is None else work_inode),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_atomically_renames_verified_work_directory(self):
        expected_identity = os.stat(self.work, follow_symlinks=False)

        result = self.run_tool()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("ROUTECONTRACT_ATOMIC_CENTRAL_STAGING_OK\n", result.stdout)
        self.assertEqual("", result.stderr)
        self.assertFalse(self.work.exists())
        final_identity = os.stat(self.parent / FINAL_NAME, follow_symlinks=False)
        self.assertEqual(expected_identity.st_dev, final_identity.st_dev)
        self.assertEqual(expected_identity.st_ino, final_identity.st_ino)

    def test_existing_final_path_is_never_replaced(self):
        final = self.parent / FINAL_NAME
        final.mkdir()
        work_identity = os.stat(self.work, follow_symlinks=False)
        final_identity = os.stat(final, follow_symlinks=False)

        result = self.run_tool()

        self.assertEqual(1, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("HOLD: final entry is not absent", result.stderr)
        self.assertEqual(work_identity.st_ino, self.work.stat().st_ino)
        self.assertEqual(final_identity.st_ino, final.stat().st_ino)

    def test_changed_parent_identity_fails_without_mutation(self):
        result = self.run_tool(parent_inode=self.parent.stat().st_ino + 1)

        self.assertEqual(1, result.returncode)
        self.assertIn("HOLD: parent inode changed", result.stderr)
        self.assertTrue(self.work.is_dir())
        self.assertFalse((self.parent / FINAL_NAME).exists())

    def test_changed_work_identity_fails_without_mutation(self):
        result = self.run_tool(work_inode=self.work.stat().st_ino + 1)

        self.assertEqual(1, result.returncode)
        self.assertIn("HOLD: work directory identity changed", result.stderr)
        self.assertTrue(self.work.is_dir())
        self.assertFalse((self.parent / FINAL_NAME).exists())


if __name__ == "__main__":
    unittest.main()
