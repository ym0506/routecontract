#!/usr/bin/env python3
"""Acceptance tests for exact v0.1.0 Maven checksum sidecar preparation."""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PREPARER = REPOSITORY_ROOT / "scripts" / "prepare_maven_v0_1_0_checksums.py"
GROUP_PATH = Path("io/github/ym0506/routecontract")
ARTIFACT_ID = "routecontract-shardingsphere-5.5"
VERSION = "0.1.0"


def load_preparer():
    spec = importlib.util.spec_from_file_location("maven_checksum_preparer", PREPARER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {PREPARER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MavenChecksumPreparerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name) / "repository"
        self.coordinate = self.repository / GROUP_PATH / ARTIFACT_ID / VERSION
        self.coordinate.mkdir(parents=True)
        self.payloads = {
            f"{ARTIFACT_ID}-{VERSION}.pom": b"<project>fixture</project>\n",
            f"{ARTIFACT_ID}-{VERSION}.jar": b"fixture-main-jar\n",
            f"{ARTIFACT_ID}-{VERSION}-sources.jar": b"fixture-sources-jar\n",
            f"{ARTIFACT_ID}-{VERSION}-javadoc.jar": b"fixture-javadoc-jar\n",
        }
        for name, data in self.payloads.items():
            (self.coordinate / name).write_bytes(data)
        self.expected = {
            name: {
                "sha1": hashlib.sha1(data, usedforsecurity=False).hexdigest(),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            for name, data in self.payloads.items()
        }

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_preparer(self):
        module = load_preparer()
        with mock.patch.object(module, "EXPECTED_ARTIFACTS", self.expected):
            return module.prepare_repository(self.repository)

    def test_creates_exact_sha1_and_sha256_sidecars(self) -> None:
        result = self.run_preparer()

        self.assertEqual(self.coordinate, result)
        expected_names = set(self.payloads)
        expected_names.update(f"{name}.sha1" for name in self.payloads)
        expected_names.update(f"{name}.sha256" for name in self.payloads)
        self.assertEqual(expected_names, {path.name for path in self.coordinate.iterdir()})
        for name, digests in self.expected.items():
            self.assertEqual(
                (digests["sha1"] + "\n").encode("ascii"),
                (self.coordinate / f"{name}.sha1").read_bytes(),
            )
            self.assertEqual(
                (digests["sha256"] + "\n").encode("ascii"),
                (self.coordinate / f"{name}.sha256").read_bytes(),
            )

    def test_production_mapping_is_exact(self) -> None:
        module = load_preparer()
        self.assertEqual(
            {
                f"{ARTIFACT_ID}-{VERSION}.pom": {
                    "sha1": "a8b5aaf6912535f40191e329714c63e149d58334",
                    "sha256": "05570bfa238ef77db255a46efdd5bbb25e994ae0137db86491a46a25e28deac9",
                },
                f"{ARTIFACT_ID}-{VERSION}.jar": {
                    "sha1": "86856916485df62867cb832c105d30abb600060c",
                    "sha256": "d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc",
                },
                f"{ARTIFACT_ID}-{VERSION}-sources.jar": {
                    "sha1": "d9f4d35086022a0e1af9e5d36830c7df3768226e",
                    "sha256": "f1f7e0a10a165b713ee1483c219480786021135867275345b0b9ba1e5f51fea9",
                },
                f"{ARTIFACT_ID}-{VERSION}-javadoc.jar": {
                    "sha1": "a0d94c850d2112127687172bab5dd6cd79f7471c",
                    "sha256": "3f30ef3eb046afc36c95a7aed7848804be67aefc9b0cbbe24a72854e5e5c6f68",
                },
            },
            module.EXPECTED_ARTIFACTS,
        )

    def test_refuses_to_overwrite_existing_sidecar(self) -> None:
        first = next(iter(self.payloads))
        existing = self.coordinate / f"{first}.sha256"
        existing.write_text("do-not-overwrite\n", encoding="ascii")

        with self.assertRaisesRegex(RuntimeError, "exact four-file inventory"):
            self.run_preparer()

        self.assertEqual(b"do-not-overwrite\n", existing.read_bytes())

    def test_rejects_unexpected_file(self) -> None:
        (self.coordinate / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "exact four-file inventory"):
            self.run_preparer()

    def test_rejects_tampered_artifact_before_writing_sidecars(self) -> None:
        first = next(iter(self.payloads))
        (self.coordinate / first).write_bytes(b"tampered\n")

        with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
            self.run_preparer()

        self.assertEqual([], list(self.coordinate.glob("*.sha1")))
        self.assertEqual([], list(self.coordinate.glob("*.sha256")))

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links are unavailable")
    def test_rejects_symlink_artifact(self) -> None:
        first = next(iter(self.payloads))
        artifact = self.coordinate / first
        target = self.repository / "outside.bin"
        target.write_bytes(artifact.read_bytes())
        artifact.unlink()
        artifact.symlink_to(target)

        with self.assertRaisesRegex(OSError, "Too many levels of symbolic links"):
            self.run_preparer()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFOs are unavailable")
    def test_rejects_fifo_artifact_without_blocking(self) -> None:
        first = next(iter(self.payloads))
        artifact = self.coordinate / first
        artifact.unlink()
        os.mkfifo(artifact)

        with self.assertRaisesRegex(RuntimeError, "not a regular file"):
            self.run_preparer()

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links are unavailable")
    def test_rejects_intermediate_coordinate_symlink(self) -> None:
        outside = Path(self.temporary_directory.name) / "outside"
        outside_coordinate = outside / GROUP_PATH / ARTIFACT_ID / VERSION
        outside_coordinate.mkdir(parents=True)
        for name, data in self.payloads.items():
            (outside_coordinate / name).write_bytes(data)
        shutil.rmtree(self.repository / GROUP_PATH.parts[0])
        (self.repository / GROUP_PATH.parts[0]).symlink_to(
            outside / GROUP_PATH.parts[0], target_is_directory=True
        )

        module = load_preparer()
        with mock.patch.object(module, "EXPECTED_ARTIFACTS", self.expected):
            with self.assertRaisesRegex(RuntimeError, "missing or unsafe"):
                module.prepare_repository(self.repository)

        self.assertEqual([], list(outside_coordinate.glob("*.sha1")))
        self.assertEqual([], list(outside_coordinate.glob("*.sha256")))

    def test_atomic_publish_refuses_link_collision_and_cleans_staging(self) -> None:
        module = load_preparer()
        directory_fd = os.open(self.coordinate, os.O_RDONLY)
        try:
            with mock.patch.object(module.os, "link", side_effect=FileExistsError):
                with self.assertRaisesRegex(RuntimeError, "refusing to overwrite sidecar"):
                    module._write_new_sidecar(
                        directory_fd,
                        "collision.sha256",
                        b"0" * 64 + b"\n",
                    )
        finally:
            os.close(directory_fd)

        self.assertFalse((self.coordinate / "collision.sha256").exists())
        self.assertEqual(
            [],
            [
                path
                for path in self.coordinate.iterdir()
                if path.name.startswith(".routecontract-checksum.")
            ],
        )

    def test_cli_rejects_relative_repository(self) -> None:
        result = subprocess.run(
            [sys.executable, str(PREPARER), "--repository", "relative/repository"],
            cwd=REPOSITORY_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("absolute", result.stderr)


if __name__ == "__main__":
    unittest.main()
