#!/usr/bin/env python3
"""Acceptance tests for the no-registry RouteContract release installer."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPOSITORY_ROOT / "scripts" / "install-release-assets.py"
RELEASE_CONSUMER = REPOSITORY_ROOT / "scripts" / "verify-release-assets-consumer.sh"
ARTIFACT_ID = "routecontract-shardingsphere-5.5"
GROUP_ID = "io.github.ym0506.routecontract"
VERSION = "1.2.3"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ReleaseFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.pom_name = f"{ARTIFACT_ID}.pom"
        self.main_jar_name = f"{ARTIFACT_ID}-{VERSION}.jar"
        self.sources_jar_name = f"{ARTIFACT_ID}-{VERSION}-sources.jar"
        self.javadoc_jar_name = f"{ARTIFACT_ID}-{VERSION}-javadoc.jar"

    def create(self) -> None:
        self.root.mkdir()
        (self.root / self.pom_name).write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>{GROUP_ID}</groupId>
  <artifactId>routecontract-shardingsphere-5.5</artifactId>
  <version>1.2.3</version>
</project>
""",
            encoding="utf-8",
        )
        self.write_main_jar(
            "io.github.ym0506.routecontract.shardingsphere55"
        )
        for name, member in (
            (self.sources_jar_name, "io/github/ym0506/routecontract/RouteContract.java"),
            (self.javadoc_jar_name, "io/github/ym0506/routecontract/RouteContract.html"),
        ):
            with ZipFile(self.root / name, "w", ZIP_DEFLATED) as archive:
                archive.writestr("META-INF/LICENSE", "Apache-2.0 fixture")
                archive.writestr("META-INF/NOTICE", "RouteContract fixture")
                archive.writestr(member, "fixture")
        for name, content in (
            (f"routecontract-{VERSION}-source.zip", b"source fixture"),
            (f"{ARTIFACT_ID}-cyclonedx.json", b"{}\n"),
            (f"{ARTIFACT_ID}-cyclonedx.xml", b"<bom/>\n"),
            ("routecontract-aggregate-cyclonedx.json", b"{}\n"),
            ("routecontract-aggregate-cyclonedx.xml", b"<bom/>\n"),
            ("test-summary.txt", b"tests=50 failures=0 errors=0 skipped=0\n"),
        ):
            (self.root / name).write_bytes(content)
        self.write_checksums()

    def write_main_jar(
        self, module_name: str, *, extra_entries: tuple[str, ...] = ()
    ) -> None:
        split_at = len("io.github.ym0506.routecontract.shardingsphere")
        manifest = (
            "Manifest-Version: 1.0\r\n"
            f"Automatic-Module-Name: {module_name[:split_at]}\r\n"
            f" {module_name[split_at:]}\r\n"
            "\r\n"
        )
        with ZipFile(self.root / self.main_jar_name, "w", ZIP_DEFLATED) as archive:
            archive.writestr(
                "META-INF/MANIFEST.MF",
                manifest,
            )
            archive.writestr(
                "META-INF/services/"
                "org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook",
                "io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook\n",
            )
            archive.writestr(
                "io/github/ym0506/routecontract/RouteContract.class", b"fixture"
            )
            for entry in extra_entries:
                archive.writestr(entry, b"unexpected fixture")
            archive.writestr("META-INF/LICENSE", "Apache-2.0 fixture")
            archive.writestr("META-INF/NOTICE", "RouteContract fixture")

    def public_payloads(self) -> list[Path]:
        return sorted(path for path in self.root.iterdir() if path.name != "SHA256SUMS")

    def write_checksums(self, *, extra_lines: tuple[str, ...] = ()) -> None:
        lines = [f"{sha256(path)}  {path.name}" for path in self.public_payloads()]
        lines.extend(extra_lines)
        (self.root / "SHA256SUMS").write_text(
            "\n".join(sorted(lines)) + "\n", encoding="utf-8"
        )


class InstallReleaseAssetsTest(unittest.TestCase):
    def run_installer(
        self, assets: Path, repository: Path, *, home: Path
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["HOME"] = str(home)
        return subprocess.run(
            [
                sys.executable,
                str(INSTALLER),
                "--release-assets-dir",
                str(assets),
                "--repository",
                str(repository),
            ],
            cwd=REPOSITORY_ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_installs_verified_coordinate_only_into_explicit_repository(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            repository = root / "consumer-maven"
            fake_home = root / "home"
            fake_home.mkdir()

            result = self.run_installer(assets, repository, home=fake_home)

            self.assertEqual(0, result.returncode, result.stderr)
            coordinate = (
                repository
                / Path(*GROUP_ID.split("."))
                / ARTIFACT_ID
                / VERSION
            )
            self.assertEqual(
                {
                    fixture.main_jar_name,
                    fixture.sources_jar_name,
                    fixture.javadoc_jar_name,
                    f"{ARTIFACT_ID}-{VERSION}.pom",
                },
                {path.name for path in coordinate.iterdir()},
            )
            self.assertEqual(
                (assets / fixture.main_jar_name).read_bytes(),
                (coordinate / fixture.main_jar_name).read_bytes(),
            )
            self.assertEqual(
                (assets / fixture.pom_name).read_bytes(),
                (coordinate / f"{ARTIFACT_ID}-{VERSION}.pom").read_bytes(),
            )
            self.assertFalse((fake_home / ".m2").exists())
            self.assertIn(f"{GROUP_ID}:{ARTIFACT_ID}:{VERSION}", result.stdout)

    def test_rejects_checksum_mismatch_without_creating_repository(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            (assets / fixture.main_jar_name).write_bytes(b"tampered")
            repository = root / "consumer-maven"

            result = self.run_installer(assets, repository, home=root / "home")

            self.assertNotEqual(0, result.returncode)
            self.assertIn("checksum mismatch", result.stderr)
            self.assertFalse(repository.exists())

    def test_rejects_unexpected_public_asset(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            (assets / "notes.txt").write_text("unexpected", encoding="utf-8")
            repository = root / "consumer-maven"

            result = self.run_installer(assets, repository, home=root / "home")

            self.assertNotEqual(0, result.returncode)
            self.assertIn("exact public release allowlist", result.stderr)
            self.assertFalse(repository.exists())

    def test_rejects_wrong_unfolded_automatic_module_name(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            fixture.write_main_jar(
                "io.github.ym0506.routecontract.shardingsphere54"
            )
            fixture.write_checksums()
            repository = root / "consumer-maven"

            result = self.run_installer(assets, repository, home=root / "home")

            self.assertNotEqual(0, result.returncode)
            self.assertIn("unexpected Automatic-Module-Name", result.stderr)
            self.assertFalse(repository.exists())

    def test_rejects_legacy_package_namespace_in_base_and_multirelease_paths(self) -> None:
        for legacy_entry in (
            "io/github/developkim/routecontract/Legacy.class",
            "META-INF/versions/17/io/github/developkim/routecontract/Legacy.class",
        ):
            with self.subTest(entry=legacy_entry), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                fixture.write_main_jar(
                    "io.github.ym0506.routecontract.shardingsphere55",
                    extra_entries=(legacy_entry,),
                )
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(assets, repository, home=root / "home")

                self.assertNotEqual(0, result.returncode)
                self.assertIn(
                    "unexpected RouteContract package namespace", result.stderr
                )
                self.assertFalse(repository.exists())

    def test_rejects_unexpected_checksum_entry(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            fixture.write_checksums(extra_lines=(f"{'0' * 64}  hidden.txt",))
            repository = root / "consumer-maven"

            result = self.run_installer(assets, repository, home=root / "home")

            self.assertNotEqual(0, result.returncode)
            self.assertIn("checksum allowlist", result.stderr)
            self.assertFalse(repository.exists())

    def test_rejects_snapshot_coordinate_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            pom = assets / fixture.pom_name
            pom.write_text(
                pom.read_text(encoding="utf-8").replace(
                    "<version>1.2.3</version>",
                    "<version>1.2.3-SNAPSHOT</version>",
                ),
                encoding="utf-8",
            )
            fixture.write_checksums()
            repository = root / "consumer-maven"

            result = self.run_installer(assets, repository, home=root / "home")

            self.assertNotEqual(0, result.returncode)
            self.assertIn("stable MAJOR.MINOR.PATCH", result.stderr)
            self.assertFalse(repository.exists())

    def test_rejects_noncanonical_owner_group_before_writing(self) -> None:
        for unexpected_group in (
            "io.github.example-owner.routecontract",
            "io.github.developkim.routecontract",
        ):
            with self.subTest(group=unexpected_group), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                pom = assets / fixture.pom_name
                pom.write_text(
                    pom.read_text(encoding="utf-8").replace(
                        f"<groupId>{GROUP_ID}</groupId>",
                        f"<groupId>{unexpected_group}</groupId>",
                    ),
                    encoding="utf-8",
                )
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(assets, repository, home=root / "home")

                self.assertNotEqual(0, result.returncode)
                self.assertIn(
                    f"groupId must be exactly {GROUP_ID}", result.stderr
                )
                self.assertFalse(repository.exists())

    def test_refuses_to_overwrite_an_existing_coordinate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            repository = root / "consumer-maven"
            coordinate = (
                repository
                / Path(*GROUP_ID.split("."))
                / ARTIFACT_ID
                / VERSION
            )
            coordinate.mkdir(parents=True)
            sentinel = coordinate / "sentinel.txt"
            sentinel.write_text("preserve", encoding="utf-8")

            result = self.run_installer(assets, repository, home=root / "home")

            self.assertNotEqual(0, result.returncode)
            self.assertIn("already exists", result.stderr)
            self.assertEqual("preserve", sentinel.read_text(encoding="utf-8"))

    def test_rejects_symlink_target_repository(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            actual_repository = root / "actual-repository"
            actual_repository.mkdir()
            repository_link = root / "repository-link"
            repository_link.symlink_to(actual_repository, target_is_directory=True)

            result = self.run_installer(assets, repository_link, home=root / "home")

            self.assertNotEqual(0, result.returncode)
            self.assertIn("must not be a symlink", result.stderr)
            self.assertEqual([], list(actual_repository.iterdir()))

    @unittest.skipUnless(
        os.environ.get("ROUTECONTRACT_RUN_RELEASE_ASSET_MYSQL_TEST") == "1",
        "set ROUTECONTRACT_RUN_RELEASE_ASSET_MYSQL_TEST=1 for the real-MySQL test",
    )
    def test_real_built_jars_install_and_run_isolated_mysql_consumer(self) -> None:
        build = subprocess.run(
            [
                str(REPOSITORY_ROOT / "gradlew"),
                "--no-daemon",
                "--no-build-cache",
                ":routecontract-shardingsphere-5.5:assemble",
                ":routecontract-shardingsphere-5.5:generatePomFileForMavenJavaPublication",
            ],
            cwd=REPOSITORY_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(0, build.returncode, build.stdout)

        module = REPOSITORY_ROOT / "routecontract-shardingsphere-5.5"
        generated_pom_path = module / "build/publications/mavenJava/pom-default.xml"
        generated_pom = generated_pom_path.read_text(encoding="utf-8")
        generated_pom_root = ET.fromstring(generated_pom)
        generated_coordinates = {
            child.tag.rsplit("}", 1)[-1]: (child.text or "").strip()
            for child in generated_pom_root
            if child.tag.rsplit("}", 1)[-1] in {"groupId", "artifactId", "version"}
        }
        self.assertEqual(ARTIFACT_ID, generated_coordinates.get("artifactId"))
        built_group = generated_coordinates["groupId"]
        built_version = generated_coordinates["version"]
        self.assertEqual(GROUP_ID, built_group)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            for suffix in ("", "-sources", "-javadoc"):
                shutil.copyfile(
                    module / "build/libs" / f"{ARTIFACT_ID}-{built_version}{suffix}.jar",
                    assets / f"{ARTIFACT_ID}-{VERSION}{suffix}.jar",
                )
            generated_pom = generated_pom.replace(
                f"<version>{built_version}</version>",
                f"<version>{VERSION}</version>",
                1,
            )
            (assets / fixture.pom_name).write_text(generated_pom, encoding="utf-8")
            fixture.write_checksums()

            result = subprocess.run(
                [str(RELEASE_CONSUMER), str(assets), str(root / "consumer-maven")],
                cwd=REPOSITORY_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stdout)
            self.assertIn(
                "ROUTECONTRACT_RELEASE_ASSET_CONSUMER "
                f"coordinate={GROUP_ID}:{ARTIFACT_ID}:{VERSION} "
                "result=VERIFIED_MYSQL",
                result.stdout,
            )


if __name__ == "__main__":
    unittest.main()
