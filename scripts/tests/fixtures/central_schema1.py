#!/usr/bin/env python3
"""Isolated schema-1 signed-input fixture, derived from the 0.1.3 release tests.

Its disposable keys and synthetic payloads never use protected release material.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PREPARER = (REPOSITORY_ROOT / "scripts" / "legacy" / "central-v0_1_3"
            / "prepare-central-upload-bundle.py")
GROUP_ID = "io.github.ym0506.routecontract"
GROUP_PATH = Path("io/github/ym0506/routecontract")
ARTIFACT_ID = "routecontract-shardingsphere-5.5"
VERSION = "0.1.3"
CHECKSUMS = ("md5", "sha1", "sha256", "sha512")


def load_preparer():
    spec = importlib.util.spec_from_file_location("schema_one_signed_fixture_preparer", PREPARER)
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


class SchemaOneSignedFixture:
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
