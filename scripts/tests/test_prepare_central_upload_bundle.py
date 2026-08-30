#!/usr/bin/env python3
"""Acceptance tests for the credential-free Central upload-bundle gate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zipfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PREPARER = REPOSITORY_ROOT / "scripts" / "prepare-central-upload-bundle.py"
GROUP_ID = "io.github.ym0506.routecontract"
GROUP_PATH = Path("io/github/ym0506/routecontract")
ARTIFACT_ID = "routecontract-shardingsphere-5.5"
VERSION = "0.1.3"
CHECKSUMS = ("md5", "sha1", "sha256", "sha512")


def load_preparer():
    spec = importlib.util.spec_from_file_location("central_upload_preparer", PREPARER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {PREPARER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def digest(data: bytes, algorithm: str) -> str:
    if algorithm == "md5":
        value = hashlib.md5(usedforsecurity=False)
    elif algorithm == "sha1":
        value = hashlib.sha1(usedforsecurity=False)
    else:
        value = hashlib.new(algorithm)
    value.update(data)
    return value.hexdigest()


def run_checked(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **kwargs,
    )


@unittest.skipUnless(shutil.which("gpg"), "GnuPG is required")
class CentralUploadBundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.class_temporary = tempfile.TemporaryDirectory()
        cls.class_root = Path(cls.class_temporary.name).resolve()
        cls.secret_home = cls.class_root / "secret-gnupg"
        cls.public_home = cls.class_root / "public-gnupg"
        cls.secret_home.mkdir(mode=0o700)
        cls.public_home.mkdir(mode=0o700)
        options = cls.class_root / "gpg-options"
        options.write_text("no-auto-key-retrieve\ndigest-algo SHA384\n", encoding="ascii")
        options.chmod(0o600)

        run_checked(
            [
                "gpg",
                "--no-options",
                "--homedir",
                str(cls.secret_home),
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                "",
                "--quick-generate-key",
                "RouteContract bundle test <central-bundle@example.invalid>",
                "rsa2048",
                "sign",
                "0",
            ]
        )
        listing = run_checked(
            [
                "gpg",
                "--no-options",
                "--homedir",
                str(cls.secret_home),
                "--batch",
                "--with-colons",
                "--fixed-list-mode",
                "--fingerprint",
                "--list-secret-keys",
            ],
            text=True,
        ).stdout
        cls.fingerprint = next(
            line.split(":")[9]
            for line in listing.splitlines()
            if line.startswith("fpr:")
        )
        public_key = run_checked(
            [
                "gpg",
                "--no-options",
                "--homedir",
                str(cls.secret_home),
                "--batch",
                "--armor",
                "--export",
                cls.fingerprint,
            ]
        ).stdout
        run_checked(
            [
                "gpg",
                "--no-options",
                "--homedir",
                str(cls.public_home),
                "--batch",
                "--import",
            ],
            input=public_key,
        )

        cls.fixture_repository = cls.class_root / "fixture-repository"
        cls.fixture_version = (
            cls.fixture_repository / GROUP_PATH / ARTIFACT_ID / VERSION
        )
        cls.fixture_version.mkdir(parents=True)
        base = f"{ARTIFACT_ID}-{VERSION}"
        cls.payloads = {
            f"{base}-javadoc.jar": b"fixture-javadoc-jar\n",
            f"{base}-sources.jar": b"fixture-sources-jar\n",
            f"{base}.jar": b"fixture-main-jar\n",
            f"{base}.module": (
                json.dumps(
                    {
                        "formatVersion": "1.1",
                        "component": {
                            "group": GROUP_ID,
                            "module": ARTIFACT_ID,
                            "version": VERSION,
                        },
                        "createdBy": {"gradle": {"version": "8.14.4"}},
                        "variants": [],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8"),
            f"{base}.pom": (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
                "  <modelVersion>4.0.0</modelVersion>\n"
                f"  <groupId>{GROUP_ID}</groupId>\n"
                f"  <artifactId>{ARTIFACT_ID}</artifactId>\n"
                f"  <version>{VERSION}</version>\n"
                "</project>\n"
            ).encode("utf-8"),
        }
        for name, data in cls.payloads.items():
            payload = cls.fixture_version / name
            payload.write_bytes(data)
            signature = cls.fixture_version / f"{name}.asc"
            run_checked(
                [
                    "gpg",
                    "--no-options",
                    "--homedir",
                    str(cls.secret_home),
                    "--batch",
                    "--pinentry-mode",
                    "loopback",
                    "--passphrase",
                    "",
                    "--digest-algo",
                    "SHA384",
                    "--local-user",
                    f"{cls.fingerprint}!",
                    "--armor",
                    "--detach-sign",
                    "--output",
                    str(signature),
                    str(payload),
                ]
            )
            for source in (payload, signature):
                source_bytes = source.read_bytes()
                for algorithm in CHECKSUMS:
                    (source.parent / f"{source.name}.{algorithm}").write_text(
                        digest(source_bytes, algorithm), encoding="ascii"
                    )

        metadata = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<metadata>\n"
            f"  <groupId>{GROUP_ID}</groupId>\n"
            f"  <artifactId>{ARTIFACT_ID}</artifactId>\n"
            "  <versioning>\n"
            f"    <latest>{VERSION}</latest>\n"
            f"    <release>{VERSION}</release>\n"
            f"    <versions><version>{VERSION}</version></versions>\n"
            "    <lastUpdated>20260101000000</lastUpdated>\n"
            "  </versioning>\n"
            "</metadata>\n"
        ).encode("utf-8")
        metadata_path = cls.fixture_version.parent / "maven-metadata.xml"
        metadata_path.write_bytes(metadata)
        for algorithm in CHECKSUMS:
            (metadata_path.parent / f"{metadata_path.name}.{algorithm}").write_text(
                digest(metadata, algorithm), encoding="ascii"
            )

        cls.manifest_value = {
            "schemaVersion": 1,
            "coordinate": {
                "groupId": GROUP_ID,
                "artifactId": ARTIFACT_ID,
                "version": VERSION,
            },
            "payloads": [
                {
                    "name": name,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
                for name, data in sorted(cls.payloads.items())
            ],
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.class_temporary.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.repository = self.root / "repository"
        shutil.copytree(self.fixture_repository, self.repository)
        self.manifest = self.root / "reviewed-payloads.json"
        self.write_manifest(self.manifest_value)
        self.output = self.root / "bundle-output"
        self.module = load_preparer()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_manifest(self, value: dict) -> None:
        self.manifest.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def build(self, output: Path | None = None):
        return self.module.build_bundle(
            repository=self.repository,
            reviewed_manifest_path=self.manifest,
            public_gpg_home=self.public_home,
            expected_primary_fingerprint=self.fingerprint,
            output_directory=output or self.output,
        )

    def verify(self, bundle: Path, receipt: Path):
        return self.module.verify_bundle(
            repository=self.repository,
            bundle_path=bundle,
            receipt_path=receipt,
            reviewed_manifest_path=self.manifest,
            public_gpg_home=self.public_home,
            expected_primary_fingerprint=self.fingerprint,
        )

    def test_builds_and_verifies_exact_deterministic_thirty_entry_bundle(self) -> None:
        first_bundle, first_receipt = self.build()
        self.verify(first_bundle, first_receipt)
        second_bundle, second_receipt = self.build(self.root / "second-output")

        self.assertEqual(first_bundle.read_bytes(), second_bundle.read_bytes())
        self.assertEqual(first_receipt.read_bytes(), second_receipt.read_bytes())
        with zipfile.ZipFile(first_bundle) as archive:
            self.assertEqual(30, len(archive.infolist()))
            self.assertEqual(
                sorted(info.filename for info in archive.infolist()),
                [info.filename for info in archive.infolist()],
            )
            for info in archive.infolist():
                self.assertEqual(zipfile.ZIP_STORED, info.compress_type)
                self.assertEqual((1980, 1, 1, 0, 0, 0), info.date_time)
                self.assertEqual(0o100644, info.external_attr >> 16)
                self.assertEqual(b"", info.extra)
                self.assertEqual(b"", info.comment)

        receipt = json.loads(first_receipt.read_text(encoding="utf-8"))
        self.assertEqual(30, receipt["bundle"]["entryCount"])
        self.assertEqual(25, len(receipt["excludedStagingEntries"]))
        self.assertEqual(
            {
                "availabilityClaim": False,
                "credentialInput": False,
                "networkPublication": False,
                "portalUpload": False,
                "portalValidation": False,
                "publicReadback": False,
                "publishAction": False,
            },
            receipt["claims"],
        )
        receipt_text = first_receipt.read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), receipt_text)
        self.assertNotIn(str(self.public_home), receipt_text)

    def test_rejects_versions_that_are_not_later_than_v012(self) -> None:
        value = json.loads(json.dumps(self.manifest_value))
        value["coordinate"]["version"] = "0.1.2"
        self.write_manifest(value)

        with self.assertRaisesRegex(RuntimeError, "greater than 0.1.2"):
            self.build()

        self.assertFalse(self.output.exists())

    def test_rejects_payload_that_differs_from_reviewed_manifest(self) -> None:
        payload = self.repository / GROUP_PATH / ARTIFACT_ID / VERSION / next(
            iter(self.payloads)
        )
        payload.write_bytes(b"tampered\n")

        with self.assertRaisesRegex(RuntimeError, "reviewed payload mismatch"):
            self.build()

        self.assertFalse(self.output.exists())

    def test_rejects_checksum_or_unexpected_staging_file(self) -> None:
        payload_name = next(iter(self.payloads))
        version_path = self.repository / GROUP_PATH / ARTIFACT_ID / VERSION
        (version_path / f"{payload_name}.sha256").write_text("0" * 64, encoding="ascii")
        with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
            self.build()
        self.assertFalse(self.output.exists())

        shutil.rmtree(self.repository)
        shutil.copytree(self.fixture_repository, self.repository)
        (version_path / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "staging inventory mismatch"):
            self.build()
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links are unavailable")
    def test_rejects_symlink_and_public_home_with_secret_key(self) -> None:
        payload_name = next(iter(self.payloads))
        version_path = self.repository / GROUP_PATH / ARTIFACT_ID / VERSION
        payload = version_path / payload_name
        outside = self.root / "outside"
        outside.write_bytes(payload.read_bytes())
        payload.unlink()
        payload.symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, "symbolic link"):
            self.build()
        self.assertFalse(self.output.exists())

        shutil.rmtree(self.repository)
        shutil.copytree(self.fixture_repository, self.repository)
        with self.assertRaisesRegex(RuntimeError, "secret-key material"):
            self.module.build_bundle(
                repository=self.repository,
                reviewed_manifest_path=self.manifest,
                public_gpg_home=self.secret_home,
                expected_primary_fingerprint=self.fingerprint,
                output_directory=self.output,
            )
        self.assertFalse(self.output.exists())

    def test_rejects_noncanonical_manifest_and_existing_output(self) -> None:
        self.manifest.write_text(json.dumps(self.manifest_value), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "canonical sorted JSON"):
            self.build()
        self.assertFalse(self.output.exists())

        self.write_manifest(self.manifest_value)
        self.output.mkdir()
        with self.assertRaisesRegex(RuntimeError, "new absent path"):
            self.build()

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links are unavailable")
    def test_rejects_ancestor_aliases_in_inputs_and_output(self) -> None:
        ancestor_alias = self.root / "ancestor-alias"
        ancestor_alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "canonical non-symlink path"):
            self.module.build_bundle(
                repository=ancestor_alias / "repository",
                reviewed_manifest_path=self.manifest,
                public_gpg_home=self.public_home,
                expected_primary_fingerprint=self.fingerprint,
                output_directory=self.output,
            )
        self.assertFalse(self.output.exists())

        staging_alias = self.root / "staging-alias"
        staging_alias.symlink_to(self.repository, target_is_directory=True)
        dangerous_output = (
            staging_alias / GROUP_PATH / ARTIFACT_ID / VERSION / "bundle-output"
        )
        with self.assertRaisesRegex(RuntimeError, "canonical non-symlink path"):
            self.module.build_bundle(
                repository=self.repository,
                reviewed_manifest_path=self.manifest,
                public_gpg_home=self.public_home,
                expected_primary_fingerprint=self.fingerprint,
                output_directory=dangerous_output,
            )
        direct_output = (
            self.repository
            / GROUP_PATH
            / ARTIFACT_ID
            / VERSION
            / "direct-bundle-output"
        )
        with self.assertRaisesRegex(RuntimeError, "outside protected input"):
            self.module.build_bundle(
                repository=self.repository,
                reviewed_manifest_path=self.manifest,
                public_gpg_home=self.public_home,
                expected_primary_fingerprint=self.fingerprint,
                output_directory=direct_output,
            )
        self.assertFalse(
            (
                self.repository
                / GROUP_PATH
                / ARTIFACT_ID
                / VERSION
                / "bundle-output"
            ).exists()
        )

    def test_output_creation_swap_cannot_redirect_writes(self) -> None:
        attacker = self.root / "attacker"
        attacker.mkdir()
        displaced = self.root / "displaced-output"
        original_mkdir = os.mkdir

        def mkdir_then_swap(path, mode=0o777, *, dir_fd=None):
            original_mkdir(path, mode=mode, dir_fd=dir_fd)
            if path == self.output.name and dir_fd is not None:
                os.rename(
                    path,
                    displaced.name,
                    src_dir_fd=dir_fd,
                    dst_dir_fd=dir_fd,
                )
                os.symlink(
                    attacker,
                    path,
                    target_is_directory=True,
                    dir_fd=dir_fd,
                )

        with mock.patch.object(self.module.os, "mkdir", side_effect=mkdir_then_swap):
            with self.assertRaisesRegex(
                RuntimeError, "output directory identity changed during creation"
            ):
                self.build()

        self.assertEqual([], list(attacker.iterdir()))
        self.assertFalse((attacker / f"{ARTIFACT_ID}-{VERSION}-central-upload.zip").exists())

    def test_verifier_rejects_tampered_bundle_or_receipt(self) -> None:
        bundle, receipt = self.build()
        bundle_bytes = bytearray(bundle.read_bytes())
        bundle_bytes[-8] ^= 1
        bundle.write_bytes(bundle_bytes)
        with self.assertRaisesRegex(RuntimeError, "bundle SHA-256 mismatch"):
            self.verify(bundle, receipt)

        shutil.rmtree(self.output)
        bundle, receipt = self.build()
        receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
        receipt_value["claims"]["portalUpload"] = True
        receipt.write_text(
            json.dumps(receipt_value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RuntimeError, "claims.portalUpload"):
            self.verify(bundle, receipt)

    def test_cli_build_and_verify_use_stable_value_free_markers(self) -> None:
        build = subprocess.run(
            [
                sys.executable,
                "-I",
                str(PREPARER),
                "build",
                "--repository",
                str(self.repository),
                "--reviewed-payload-manifest",
                str(self.manifest),
                "--public-gpg-home",
                str(self.public_home),
                "--expected-primary-fingerprint",
                self.fingerprint,
                "--output-directory",
                str(self.output),
            ],
            cwd=REPOSITORY_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, build.returncode, build.stderr)
        self.assertRegex(
            build.stdout,
            r"^ROUTECONTRACT_CENTRAL_BUNDLE_BUILT "
            r"coordinate=io\.github\.ym0506\.routecontract:"
            r"routecontract-shardingsphere-5\.5:0\.1\.3 entries=30 "
            r"bundleSha256=[0-9a-f]{64} receiptSha256=[0-9a-f]{64} VERIFIED\n$",
        )
        self.assertEqual("", build.stderr)

        bundle = self.output / f"{ARTIFACT_ID}-{VERSION}-central-upload.zip"
        receipt = self.output / f"{ARTIFACT_ID}-{VERSION}-central-upload-receipt.json"
        verify = subprocess.run(
            [
                sys.executable,
                "-I",
                str(PREPARER),
                "verify",
                "--repository",
                str(self.repository),
                "--bundle",
                str(bundle),
                "--receipt",
                str(receipt),
                "--reviewed-payload-manifest",
                str(self.manifest),
                "--public-gpg-home",
                str(self.public_home),
                "--expected-primary-fingerprint",
                self.fingerprint,
            ],
            cwd=REPOSITORY_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, verify.returncode, verify.stderr)
        self.assertRegex(
            verify.stdout,
            r"^ROUTECONTRACT_CENTRAL_BUNDLE_VERIFIED .* VERIFIED\n$",
        )
        self.assertEqual("", verify.stderr)


if __name__ == "__main__":
    unittest.main()
