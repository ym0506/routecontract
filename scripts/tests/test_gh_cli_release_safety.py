from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts/gh_cli_release_safety.py"
SPEC = importlib.util.spec_from_file_location("gh_cli_release_safety", SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import precondition
    raise RuntimeError(f"could not import {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class GithubCliReleaseSafetyTest(unittest.TestCase):
    def test_accepts_patched_stable_versions(self) -> None:
        for output, expected in (
            (
                "gh version 2.93.0 (2026-05-27)\n"
                "https://github.com/cli/cli/releases/tag/v2.93.0\n",
                (2, 93, 0),
            ),
            (
                "gh version 2.97.0 (2026-07-31)\n"
                "https://github.com/cli/cli/releases/tag/v2.97.0\n",
                (2, 97, 0),
            ),
            ("gh version 3.0.0 (future)\n", (3, 0, 0)),
        ):
            with self.subTest(output=output):
                self.assertEqual(expected, MODULE.parse_version(output))

    def test_rejects_malformed_or_prerelease_versions(self) -> None:
        for output in (
            "",
            "gh version 2.93\n",
            "gh version 2.93.0-rc1\n",
            "gh version 02.93.0\n",
            "gh version 2.93.0 (nested (value))\n",
            "unexpected 2.93.0\n",
            "gh version 2.93.0\ngh version 2.97.0\n",
            (
                "gh version 2.93.0\n"
                "https://github.com/cli/cli/releases/tag/v2.97.0\n"
            ),
            "gh version 2.93.0\nunexpected extra line\n",
        ):
            with self.subTest(output=output):
                with self.assertRaises(MODULE.GithubCliSafetyError):
                    MODULE.parse_version(output)

    def test_rejects_representative_affected_versions(self) -> None:
        for version in ((0, 0, 0), (2, 87, 3), (2, 92, 0)):
            completed = subprocess.CompletedProcess(
                ["/safe/path/gh", "version"],
                0,
                stdout="gh version " + ".".join(map(str, version)) + "\n",
                stderr="",
            )
            with (
                self.subTest(version=version),
                mock.patch.object(MODULE.shutil, "which", return_value="/safe/path/gh"),
                mock.patch.object(MODULE.subprocess, "run", return_value=completed),
            ):
                with self.assertRaisesRegex(
                    MODULE.GithubCliSafetyError,
                    r"2\.93\.0 or newer.*GHSA-8xvp-7hj6-mcj9",
                ):
                    MODULE.require_safe_github_cli()

    def test_returns_exact_executable_at_minimum_patched_version(self) -> None:
        completed = subprocess.CompletedProcess(
            ["/safe/path/gh", "version"],
            0,
            stdout="gh version 2.93.0\n",
            stderr="",
        )
        with (
            mock.patch.object(MODULE.shutil, "which", return_value="/safe/path/gh"),
            mock.patch.object(MODULE.subprocess, "run", return_value=completed),
        ):
            self.assertEqual(
                ("/safe/path/gh", (2, 93, 0)), MODULE.require_safe_github_cli()
            )

    def test_fails_closed_without_echoing_command_output(self) -> None:
        failed = subprocess.CompletedProcess(
            ["/safe/path/gh", "version"],
            1,
            stdout="synthetic-sensitive-stdout",
            stderr="synthetic-sensitive-stderr",
        )
        with (
            mock.patch.object(MODULE.shutil, "which", return_value="/safe/path/gh"),
            mock.patch.object(MODULE.subprocess, "run", return_value=failed),
        ):
            with self.assertRaises(MODULE.GithubCliSafetyError) as caught:
                MODULE.require_safe_github_cli()
        self.assertNotIn("synthetic-sensitive", str(caught.exception))

    def test_fails_closed_when_cli_is_missing_or_probe_cannot_complete(self) -> None:
        with mock.patch.object(MODULE.shutil, "which", return_value=None):
            with self.assertRaisesRegex(
                MODULE.GithubCliSafetyError, "not installed or is not on PATH"
            ):
                MODULE.require_safe_github_cli()

        for error in (
            OSError("synthetic-sensitive-os-error"),
            subprocess.TimeoutExpired(["/safe/path/gh", "version"], 10),
        ):
            with (
                self.subTest(error=type(error).__name__),
                mock.patch.object(MODULE.shutil, "which", return_value="/safe/path/gh"),
                mock.patch.object(MODULE.subprocess, "run", side_effect=error),
            ):
                with self.assertRaises(MODULE.GithubCliSafetyError) as caught:
                    MODULE.require_safe_github_cli()
            self.assertNotIn("synthetic-sensitive", str(caught.exception))

    def test_release_procedure_requires_gate_before_verification(self) -> None:
        releasing = (REPOSITORY_ROOT / "RELEASING.md").read_text(encoding="utf-8")
        gate = "python3 scripts/gh_cli_release_safety.py"
        verify = "`gh release verify`"
        self.assertEqual(1, releasing.count(gate))
        self.assertLess(releasing.index(gate), releasing.index(verify))
        for required in (
            "GHSA-8xvp-7hj6-mcj9",
            "2.93.0",
            "revoke",
            "security log",
            "audit logs",
            "enforced_by_owner",
            "do not advance `main`",
            "immediately before publication",
            "#21",
        ):
            self.assertIn(required, releasing)


if __name__ == "__main__":
    unittest.main()
