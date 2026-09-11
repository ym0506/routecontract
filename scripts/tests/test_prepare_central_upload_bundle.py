#!/usr/bin/env python3
"""Acceptance tests for the credential-free Central upload-bundle gate."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
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
        first = self.build()
        verified = self.verify(first.bundle_path, first.receipt_path)
        second = self.build(self.root / "second-output")

        for result in (first, verified, second):
            self.assertEqual(VERSION, result.version)
            self.assertEqual(
                hashlib.sha256(result.bundle_path.read_bytes()).hexdigest(),
                result.bundle_sha256,
            )
            self.assertEqual(
                hashlib.sha256(result.receipt_path.read_bytes()).hexdigest(),
                result.receipt_sha256,
            )
        self.assertEqual(first.bundle_path.read_bytes(), second.bundle_path.read_bytes())
        self.assertEqual(first.receipt_path.read_bytes(), second.receipt_path.read_bytes())
        with zipfile.ZipFile(first.bundle_path) as archive:
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

        receipt = json.loads(first.receipt_path.read_text(encoding="utf-8"))
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
        receipt_text = first.receipt_path.read_text(encoding="utf-8")
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

    @unittest.skipUnless(hasattr(os, "link"), "hard links are unavailable")
    def test_rejects_hardlinked_inputs_and_creates_private_single_link_outputs(self) -> None:
        manifest_link = self.root / "manifest-hardlink.json"
        os.link(self.manifest, manifest_link)
        try:
            with self.assertRaisesRegex(RuntimeError, "exactly one hard link"):
                self.build()
        finally:
            manifest_link.unlink()

        payload = (
            self.repository
            / GROUP_PATH
            / ARTIFACT_ID
            / VERSION
            / next(iter(self.payloads))
        )
        payload_link = self.root / "payload-hardlink"
        os.link(payload, payload_link)
        try:
            with self.assertRaisesRegex(RuntimeError, "exactly one hard link"):
                self.build()
        finally:
            payload_link.unlink()

        tool_link = self.root / "tool-hardlink.py"
        os.link(PREPARER, tool_link)
        try:
            with self.assertRaisesRegex(RuntimeError, "exactly one hard link"):
                self.build()
        finally:
            tool_link.unlink()

        built = self.build()
        self.assertEqual(0o700, stat.S_IMODE(os.lstat(self.output).st_mode))
        for path in (built.bundle_path, built.receipt_path):
            metadata = os.lstat(path)
            self.assertTrue(stat.S_ISREG(metadata.st_mode))
            self.assertEqual(0o600, stat.S_IMODE(metadata.st_mode))
            self.assertEqual(1, metadata.st_nlink)

        bundle_link = self.root / "bundle-hardlink.zip"
        os.link(built.bundle_path, bundle_link)
        try:
            with self.assertRaisesRegex(RuntimeError, "exactly one hard link"):
                self.verify(built.bundle_path, built.receipt_path)
        finally:
            bundle_link.unlink()

        receipt_link = self.root / "receipt-hardlink.json"
        os.link(built.receipt_path, receipt_link)
        try:
            with self.assertRaisesRegex(RuntimeError, "exactly one hard link"):
                self.verify(built.bundle_path, built.receipt_path)
        finally:
            receipt_link.unlink()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFOs are unavailable")
    def test_rejects_static_special_file_in_staging(self) -> None:
        special = (
            self.repository
            / GROUP_PATH
            / ARTIFACT_ID
            / VERSION
            / "unexpected.pipe"
        )
        os.mkfifo(special, mode=0o600)
        with self.assertRaisesRegex(RuntimeError, "special file"):
            self.build()
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links are unavailable")
    def test_rejects_secret_material_name_aliases_and_dangling_links(self) -> None:
        alias_home = self.root / "alias-public-gnupg"
        shutil.copytree(
            self.public_home,
            alias_home,
            ignore=shutil.ignore_patterns("S.*"),
        )
        private_keys = alias_home / "private-keys-v1.d"
        if private_keys.exists():
            private_keys.rmdir()
        empty = self.root / "empty-private-keys"
        empty.mkdir()
        private_keys.symlink_to(empty, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "secret-key material"):
            self.module.build_bundle(
                repository=self.repository,
                reviewed_manifest_path=self.manifest,
                public_gpg_home=alias_home,
                expected_primary_fingerprint=self.fingerprint,
                output_directory=self.output,
            )

        dangling_home = self.root / "dangling-public-gnupg"
        shutil.copytree(
            self.public_home,
            dangling_home,
            ignore=shutil.ignore_patterns("S.*"),
        )
        (dangling_home / "secring.gpg").symlink_to(
            dangling_home / "does-not-exist"
        )
        with self.assertRaisesRegex(RuntimeError, "secret-key material"):
            self.module.build_bundle(
                repository=self.repository,
                reviewed_manifest_path=self.manifest,
                public_gpg_home=dangling_home,
                expected_primary_fingerprint=self.fingerprint,
                output_directory=self.output,
            )
        self.assertFalse(self.output.exists())

    def test_repository_directory_swap_fails_identity_snapshot(self) -> None:
        original_open = os.open
        swapped = False

        def open_then_swap(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal swapped
            descriptor = original_open(path, flags, mode, dir_fd=dir_fd)
            if path == "github" and dir_fd is not None and not swapped:
                swapped = True
                os.rename(
                    "github",
                    "github-displaced",
                    src_dir_fd=dir_fd,
                    dst_dir_fd=dir_fd,
                )
                os.mkdir("github", mode=0o755, dir_fd=dir_fd)
            return descriptor

        with mock.patch.object(self.module.os, "open", side_effect=open_then_swap):
            with self.assertRaisesRegex(RuntimeError, "directory identity changed"):
                self.build()
        self.assertTrue(swapped)
        self.assertFalse(self.output.exists())

    def test_output_close_failures_fail_and_preserve_the_transaction(self) -> None:
        original_close = os.close
        parent_identity = (
            os.lstat(self.root).st_dev,
            os.lstat(self.root).st_ino,
        )
        for target in ("file", "output", "parent"):
            with self.subTest(target=target):
                output = self.root / f"close-failure-{target}"
                failed = False

                def close_then_fail(descriptor):
                    nonlocal failed
                    metadata = os.fstat(descriptor)
                    identity = (metadata.st_dev, metadata.st_ino)
                    matches = (
                        target == "file" and stat.S_ISREG(metadata.st_mode)
                    ) or (
                        target == "output"
                        and stat.S_ISDIR(metadata.st_mode)
                        and output.exists()
                        and identity
                        == (
                            os.lstat(output).st_dev,
                            os.lstat(output).st_ino,
                        )
                    ) or (target == "parent" and identity == parent_identity)
                    original_close(descriptor)
                    if matches and not failed:
                        failed = True
                        raise OSError(f"injected {target} close failure")

                with mock.patch.object(
                    self.module.os, "close", side_effect=close_then_fail
                ), mock.patch.object(
                    self.module.os,
                    "unlink",
                    side_effect=AssertionError("failure handling must not unlink"),
                ), mock.patch.object(
                    self.module.os,
                    "rmdir",
                    side_effect=AssertionError("failure handling must not remove"),
                ), mock.patch.object(
                    self.module.os,
                    "rename",
                    side_effect=AssertionError("failure handling must not rename"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "could not close output"):
                        self.module._write_outputs(
                            output,
                            "bundle.zip",
                            b"bundle-bytes",
                            "receipt.json",
                            b"receipt-bytes",
                        )
                self.assertTrue(failed)
                self.assertTrue(output.is_dir())

    def test_initial_output_fstat_failure_closes_and_preserves_partial_output(self) -> None:
        original_fstat = os.fstat
        original_close = os.close
        failed_descriptor = None
        closed_failed_descriptor = False

        def fail_initial_regular_fstat(descriptor):
            nonlocal failed_descriptor
            metadata = original_fstat(descriptor)
            if failed_descriptor is None and stat.S_ISREG(metadata.st_mode):
                failed_descriptor = descriptor
                raise OSError("injected initial output fstat failure")
            return metadata

        def record_close(descriptor):
            nonlocal closed_failed_descriptor
            if descriptor == failed_descriptor:
                closed_failed_descriptor = True
            return original_close(descriptor)

        with mock.patch.object(
            self.module.os, "fstat", side_effect=fail_initial_regular_fstat
        ), mock.patch.object(
            self.module.os, "close", side_effect=record_close
        ):
            with self.assertRaisesRegex(RuntimeError, "output transaction failed"):
                self.module._write_outputs(
                    self.output,
                    "bundle.zip",
                    b"verified-bundle",
                    "receipt.json",
                    b"verified-receipt",
                )

        self.assertIsNotNone(failed_descriptor)
        self.assertTrue(closed_failed_descriptor)
        self.assertTrue(self.output.is_dir())
        self.assertTrue((self.output / "bundle.zip").is_file())

    def test_failure_preserves_replacement_file_and_directory_identities(self) -> None:
        original_write_file = self.module._write_file
        replacement_payload = b"replacement-must-survive"
        displaced_bundle = "bundle.zip.displaced"

        def replace_created_bundle_then_fail(directory_fd, name, payload):
            if name == "bundle.zip":
                return original_write_file(directory_fd, name, payload)
            os.rename(
                "bundle.zip",
                displaced_bundle,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
            replacement_fd = os.open(
                "bundle.zip",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory_fd,
            )
            try:
                os.write(replacement_fd, replacement_payload)
            finally:
                os.close(replacement_fd)
            raise self.module.BundleError("injected output failure")

        with mock.patch.object(
            self.module,
            "_write_file",
            side_effect=replace_created_bundle_then_fail,
        ), mock.patch.object(
            self.module.os,
            "unlink",
            side_effect=AssertionError("failure cleanup must not unlink"),
        ), mock.patch.object(
            self.module.os,
            "rmdir",
            side_effect=AssertionError("failure cleanup must not remove directories"),
        ):
            with self.assertRaisesRegex(RuntimeError, "injected output failure"):
                self.module._write_outputs(
                    self.output,
                    "bundle.zip",
                    b"verified-bundle",
                    "receipt.json",
                    b"verified-receipt",
                )
        self.assertEqual(
            replacement_payload, (self.output / "bundle.zip").read_bytes()
        )
        self.assertEqual(
            b"verified-bundle", (self.output / displaced_bundle).read_bytes()
        )

        directory_output = self.root / "directory-identity-output"
        displaced_directory = self.root / "directory-identity-displaced"
        replacement_directory = self.root / "directory-identity-replacement"
        replacement_directory.mkdir()
        replacement_identity = (
            os.lstat(replacement_directory).st_dev,
            os.lstat(replacement_directory).st_ino,
        )

        def replace_created_directory_then_fail(*_args, **_kwargs):
            os.rename(directory_output, displaced_directory)
            os.rename(replacement_directory, directory_output)
            raise self.module.BundleError("injected directory replacement")

        with mock.patch.object(
            self.module,
            "_write_file",
            side_effect=replace_created_directory_then_fail,
        ):
            with self.assertRaisesRegex(RuntimeError, "injected directory replacement"):
                self.module._write_outputs(
                    directory_output,
                    "bundle.zip",
                    b"verified-bundle",
                    "receipt.json",
                    b"verified-receipt",
                )
        current = os.lstat(directory_output)
        self.assertEqual(replacement_identity, (current.st_dev, current.st_ino))
        self.assertTrue(displaced_directory.is_dir())

    def test_failed_transaction_performs_no_cleanup_mutation(self) -> None:
        with mock.patch.object(
            self.module,
            "_write_file",
            side_effect=self.module.BundleError("injected pre-write failure"),
        ), mock.patch.object(
            self.module.os,
            "unlink",
            side_effect=AssertionError("failure handling must not unlink"),
        ), mock.patch.object(
            self.module.os,
            "rmdir",
            side_effect=AssertionError("failure handling must not remove"),
        ), mock.patch.object(
            self.module.os,
            "rename",
            side_effect=AssertionError("failure handling must not rename"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "failure handling performed no rename or deletion"
            ):
                self.module._write_outputs(
                    self.output,
                    "bundle.zip",
                    b"verified-bundle",
                    "receipt.json",
                    b"verified-receipt",
                )

        self.assertTrue(self.output.is_dir())
        self.assertEqual([], list(self.output.iterdir()))

    def test_rechecks_output_parent_privacy_at_write_time(self) -> None:
        original_write_outputs = self.module._write_outputs

        def widen_parent_then_write(*arguments, **keywords):
            self.root.chmod(0o777)
            return original_write_outputs(*arguments, **keywords)

        try:
            with mock.patch.object(
                self.module,
                "_write_outputs",
                side_effect=widen_parent_then_write,
            ):
                with self.assertRaisesRegex(RuntimeError, "output parent must be owned"):
                    self.build()
        finally:
            self.root.chmod(0o700)
        self.assertFalse(self.output.exists())

    def test_signatures_use_verified_public_only_snapshot_after_input_swap(self) -> None:
        input_home = self.root / "input-public-gnupg"
        secret_replacement = self.root / "same-fingerprint-secret-gnupg"
        displaced_input = self.root / "displaced-public-gnupg"
        shutil.copytree(
            self.public_home,
            input_home,
            ignore=shutil.ignore_patterns("S.*"),
        )
        shutil.copytree(
            self.secret_home,
            secret_replacement,
            ignore=shutil.ignore_patterns("S.*"),
        )
        original_verify_home = self.module._verify_public_gpg_home
        original_verify_signature = self.module._verify_signature
        swapped = False
        signature_homes: list[Path] = []

        def verify_home_then_swap(home, fingerprint):
            nonlocal swapped
            public_key = original_verify_home(home, fingerprint)
            if Path(home) == input_home and not swapped:
                swapped = True
                input_home.rename(displaced_input)
                secret_replacement.rename(input_home)
            return public_key

        def record_signature_home(
            signature,
            payload,
            public_gpg_home,
            expected_fingerprint,
            label,
        ):
            signature_home = Path(public_gpg_home)
            signature_homes.append(signature_home)
            self.assertNotEqual(input_home, signature_home)
            self.assertFalse((signature_home / "secring.gpg").exists())
            return original_verify_signature(
                signature,
                payload,
                public_gpg_home,
                expected_fingerprint,
                label,
            )

        with mock.patch.object(
            self.module,
            "_verify_public_gpg_home",
            side_effect=verify_home_then_swap,
        ), mock.patch.object(
            self.module,
            "_verify_signature",
            side_effect=record_signature_home,
        ):
            result = self.module.build_bundle(
                repository=self.repository,
                reviewed_manifest_path=self.manifest,
                public_gpg_home=input_home,
                expected_primary_fingerprint=self.fingerprint,
                output_directory=self.output,
            )

        self.assertTrue(swapped)
        self.assertEqual(VERSION, result.version)
        self.assertEqual(5, len(signature_homes))
        self.assertTrue((input_home / "private-keys-v1.d").is_dir())

    def test_verifier_rejects_tampered_bundle_or_receipt(self) -> None:
        built = self.build()
        bundle, receipt = built.bundle_path, built.receipt_path
        bundle_bytes = bytearray(bundle.read_bytes())
        bundle_bytes[-8] ^= 1
        bundle.write_bytes(bundle_bytes)
        with self.assertRaisesRegex(RuntimeError, "bundle SHA-256 mismatch"):
            self.verify(bundle, receipt)

        shutil.rmtree(self.output)
        built = self.build()
        bundle, receipt = built.bundle_path, built.receipt_path
        receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
        receipt_value["claims"]["portalUpload"] = True
        receipt.write_text(
            json.dumps(receipt_value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RuntimeError, "claims.portalUpload"):
            self.verify(bundle, receipt)

    def test_cli_markers_use_same_verified_result_after_path_swap(self) -> None:
        original_build = self.module.build_bundle
        build_result = None

        def build_then_swap(**arguments):
            nonlocal build_result
            build_result = original_build(**arguments)._replace(version="9.8.7")
            build_result.bundle_path.write_bytes(b"swapped-after-build\n")
            build_result.receipt_path.write_bytes(b"swapped-after-build\n")
            return build_result

        build_stdout = io.StringIO()
        with mock.patch.object(
            self.module, "build_bundle", side_effect=build_then_swap
        ), contextlib.redirect_stdout(build_stdout):
            build_status = self.module.main(
                [
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
                ]
            )
        self.assertEqual(0, build_status)
        self.assertIsNotNone(build_result)
        self.assertIn(
            f"coordinate={GROUP_ID}:{ARTIFACT_ID}:9.8.7",
            build_stdout.getvalue(),
        )
        self.assertIn(
            f"bundleSha256={build_result.bundle_sha256}",
            build_stdout.getvalue(),
        )
        self.assertIn(
            f"receiptSha256={build_result.receipt_sha256}",
            build_stdout.getvalue(),
        )

        shutil.rmtree(self.output)
        built = self.build()
        original_verify = self.module.verify_bundle
        verify_result = None

        def verify_then_swap(**arguments):
            nonlocal verify_result
            verify_result = original_verify(**arguments)._replace(version="9.8.7")
            built.bundle_path.write_bytes(b"swapped-after-verify\n")
            built.receipt_path.write_bytes(b"swapped-after-verify\n")
            return verify_result

        verify_stdout = io.StringIO()
        with mock.patch.object(
            self.module, "verify_bundle", side_effect=verify_then_swap
        ), contextlib.redirect_stdout(verify_stdout):
            verify_status = self.module.main(
                [
                    "verify",
                    "--repository",
                    str(self.repository),
                    "--bundle",
                    str(built.bundle_path),
                    "--receipt",
                    str(built.receipt_path),
                    "--reviewed-payload-manifest",
                    str(self.manifest),
                    "--public-gpg-home",
                    str(self.public_home),
                    "--expected-primary-fingerprint",
                    self.fingerprint,
                ]
            )
        self.assertEqual(0, verify_status)
        self.assertIsNotNone(verify_result)
        self.assertIn(
            f"coordinate={GROUP_ID}:{ARTIFACT_ID}:9.8.7",
            verify_stdout.getvalue(),
        )
        self.assertIn(
            f"bundleSha256={verify_result.bundle_sha256}",
            verify_stdout.getvalue(),
        )
        self.assertIn(
            f"receiptSha256={verify_result.receipt_sha256}",
            verify_stdout.getvalue(),
        )

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
