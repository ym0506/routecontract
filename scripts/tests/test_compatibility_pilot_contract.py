#!/usr/bin/env python3
"""Contract tests for the sealed Quarkiverse compatibility pilot packet."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PILOT = (
    REPOSITORY_ROOT
    / "docs"
    / "compatibility-pilots"
    / "quarkiverse-quarkus-shardingsphere-jdbc"
)
README = PILOT / "README.md"
PATCH = PILOT / "routecontract-pilot.patch"
REPRODUCER = PILOT / "reproduce.sh"
EXPECTED_CANDIDATE = PILOT / "expected-candidate.sha256"
RECEIPT = PILOT / "receipt.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CompatibilityPilotContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = README.read_text(encoding="utf-8")
        cls.reproducer = REPRODUCER.read_text(encoding="utf-8")
        cls.patch = PATCH.read_text(encoding="utf-8")
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))

    def test_packet_files_are_regular_and_receipt_hashes_current_bytes(self) -> None:
        for path in (README, PATCH, REPRODUCER, EXPECTED_CANDIDATE, RECEIPT):
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)

        patch_record = self.receipt["patch"]
        self.assertEqual(PATCH.stat().st_size, patch_record["bytes"])
        self.assertEqual(sha256(PATCH), patch_record["sha256"])
        reproducer_record = self.receipt["reproducer"]
        self.assertEqual(REPRODUCER.stat().st_size, reproducer_record["bytes"])
        self.assertEqual(sha256(REPRODUCER), reproducer_record["sha256"])
        self.assertIn(reproducer_record["sha256"], self.readme)
        self.assertEqual(
            sha256(EXPECTED_CANDIDATE),
            reproducer_record["expectedCandidateFileSha256"],
        )

    def test_patch_scope_is_exact_and_contains_no_baseline(self) -> None:
        changed_paths = [
            line.removeprefix("+++ b/")
            for line in self.patch.splitlines()
            if line.startswith("+++ b/")
        ]
        self.assertEqual(self.receipt["patch"]["changedPaths"], changed_paths)
        self.assertEqual(2, len(changed_paths))
        self.assertFalse(
            any(
                path.endswith("resources/route-contracts/accounts.insert.json")
                for path in changed_paths
            )
        )
        self.assertFalse(self.receipt["patch"]["approvedBaselineIncluded"])

    def test_reproducer_is_syntax_valid_and_seed_cleanup_is_symlink_safe(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(REPRODUCER)],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)

        source_guard = self.reproducer.index(
            'find "$SEED_DIR" -type l -print -quit'
        )
        copy = self.reproducer.index('cp -R "$SEED_DIR"/. "$MAVEN_LOCAL_REPO"/')
        copied_guard = self.reproducer.index(
            'find "$MAVEN_LOCAL_REPO" -type l -print -quit', copy
        )
        coordinate_removal = self.reproducer.index(
            'rm -rf -- "$MAVEN_LOCAL_REPO/io/github/ym0506/routecontract"',
            copied_guard,
        )
        self.assertLess(source_guard, copy)
        self.assertLess(copy, copied_guard)
        self.assertLess(copied_guard, coordinate_removal)

    def test_profile_off_and_profile_on_tests_cannot_be_skipped(self) -> None:
        for option in (
            "-DskipTests=false",
            "-Dmaven.test.skip=false",
            "-Dmaven.test.failure.ignore=false",
        ):
            self.assertEqual(2, self.reproducer.count(option))

        for identity in (
            "ShardingsphereJdbcTest.xml",
            "ShardingsphereJdbcTest'",
            "writeYourOwnUnitTest",
            "ShardingsphereJdbcDevModeTest.xml",
            "ShardingsphereJdbcDevModeTest'",
            "writeYourOwnDevModeTest",
            "ShardingTablesTest.xml",
            "ShardingTablesTest'",
            "expected three exact profile-off report triples",
            "profile-off Surefire report inventory is not the exact reviewed set",
            'expected_totals = {"tests": "1", "failures": "0", "errors": "0", "skipped": "0"}',
        ):
            self.assertIn(identity, self.reproducer)

    def test_receipt_keeps_claim_boundary_explicit(self) -> None:
        boundary = self.receipt["claimBoundary"]
        for key in (
            "completeRoutePlanClaimed",
            "mysqlVerified",
            "productionSupportClaimed",
            "externalMaintainerParticipated",
            "externalUserEvidence",
            "adoptionEvidence",
            "endorsementClaimed",
        ):
            self.assertIs(boundary[key], False, key)
        self.assertFalse(
            self.receipt["verification"]["profileOn"]["approvedBaselineCreated"]
        )
        normalized_readme = " ".join(self.readme.replace("**", "").split())
        for phrase in (
            "not MySQL evidence",
            "a user result, adoption, production support or endorsement",
            "No human-approved baseline is included or created",
            "does not satisfy the project's strict definition of an actual external user integration",
        ):
            self.assertIn(phrase, normalized_readme)

    def test_packet_does_not_embed_private_paths_or_secrets(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (README, PATCH, REPRODUCER, EXPECTED_CANDIDATE, RECEIPT)
        )
        for forbidden in (
            "/Users/",
            "/private/tmp/",
            "atat9828@naver.com",
            "ghp_",
            "github_pat_",
        ):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
