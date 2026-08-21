#!/usr/bin/env python3
"""Acceptance tests for the no-registry RouteContract release installer."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import stat
import time
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

try:
    import pwd
except ImportError:  # pragma: no cover - unavailable on Windows
    pwd = None  # type: ignore[assignment]


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPOSITORY_ROOT / "scripts" / "install-release-assets.py"
RELEASE_CONSUMER = REPOSITORY_ROOT / "scripts" / "verify-release-assets-consumer.sh"
ARTIFACT_ID = "routecontract-shardingsphere-5.5"
GROUP_ID = "io.github.ym0506.routecontract"
VERSION = "1.2.3"
SOURCE_PUBLIC_API_PATH = (
    "routecontract-shardingsphere-5.5/src/main/java/"
    "io/github/ym0506/routecontract/RouteContract.java"
)
SOURCE_HOOK_PATH = (
    "routecontract-shardingsphere-5.5/src/main/java/"
    "io/github/ym0506/routecontract/internal/RouteContractSqlExecutionHook.java"
)
SOURCE_SERVICE_DESCRIPTOR_PATH = (
    "routecontract-shardingsphere-5.5/src/main/resources/META-INF/services/"
    "org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook"
)
EXPECTED_PROVIDER = (
    "io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook"
)
SOURCE_REQUIRED_RELATIVE_PATHS = {
    "README.md",
    "LICENSE",
    "NOTICE",
    "build.gradle",
    "settings.gradle",
    "gradlew",
    "scripts/install-release-assets.py",
    SOURCE_PUBLIC_API_PATH,
    SOURCE_HOOK_PATH,
    SOURCE_SERVICE_DESCRIPTOR_PATH,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ReleaseFixture:
    def __init__(self, root: Path, version: str = VERSION) -> None:
        self.root = root
        self.version = version
        self.pom_name = f"{ARTIFACT_ID}.pom"
        self.main_jar_name = f"{ARTIFACT_ID}-{version}.jar"
        self.sources_jar_name = f"{ARTIFACT_ID}-{version}-sources.jar"
        self.javadoc_jar_name = f"{ARTIFACT_ID}-{version}-javadoc.jar"
        self.source_archive_name = f"routecontract-{version}-source.zip"

    def create(self) -> None:
        self.root.mkdir()
        (self.root / self.pom_name).write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>{GROUP_ID}</groupId>
  <artifactId>routecontract-shardingsphere-5.5</artifactId>
  <version>{self.version}</version>
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
        self.write_source_archive()
        for name, content in (
            (f"{ARTIFACT_ID}-cyclonedx.json", b"{}\n"),
            (f"{ARTIFACT_ID}-cyclonedx.xml", b"<bom/>\n"),
            ("routecontract-aggregate-cyclonedx.json", b"{}\n"),
            ("routecontract-aggregate-cyclonedx.xml", b"<bom/>\n"),
            ("test-summary.txt", b"tests=50 failures=0 errors=0 skipped=0\n"),
        ):
            (self.root / name).write_bytes(content)
        self.write_supply_chain_evidence()
        self.write_checksums()

    def write_supply_chain_evidence(self) -> None:
        aggregate_json = self.root / "routecontract-aggregate-cyclonedx.json"
        aggregate_xml = self.root / "routecontract-aggregate-cyclonedx.xml"
        published_json = self.root / f"{ARTIFACT_ID}-cyclonedx.json"
        published_xml = self.root / f"{ARTIFACT_ID}-cyclonedx.xml"
        license_reviews = [
            {
                "action": "resolve or renew the OCI license review before expiry",
                "componentName": "mysql",
                "componentVersion": "8.4.11",
                "expires": "2026-08-27",
                "owner": "RouteContract maintainers",
                "purl": "pkg:oci/mysql@sha256%3A" + "b" * 64,
                "rationaleCode": "MYSQL_OCI_PACKAGE_LICENSE_CONCLUSION_INCOMPLETE",
                "reviewedAt": "2026-08-13",
                "scope": "test-container",
                "status": "manual-review-required",
            },
            {
                "action": "resolve the redistribution NOTICE review before expiry",
                "componentName": "jts-io-common",
                "componentVersion": "1.19.0",
                "expires": "2026-08-27",
                "owner": "RouteContract maintainers",
                "purl": "pkg:maven/org.locationtech.jts.io/jts-io-common@1.19.0",
                "rationaleCode": "JTS_IO_COMMON_REDISTRIBUTION_NOTICE_TREATMENT_UNCONFIRMED",
                "reviewedAt": "2026-08-13",
                "scope": "test-runtime",
                "status": "manual-review-required",
            },
        ]
        vulnerability_exceptions = (
            ("OSV-001", "GHSA-j288-q9x7-2f5v", "pkg:maven/commons-lang/commons-lang@2.4", None, "MODERATE"),
            ("OSV-002", "GHSA-pq2g-wx69-c263", "pkg:maven/net.minidev/json-smart@2.5.0", "2.5.2", "HIGH"),
            ("OSV-003", "GHSA-c2rv-hwqm-wjpg", "pkg:maven/org.apache.calcite/calcite-core@1.40.0", "1.42.0", "MODERATE"),
        )
        findings = [
            {
                "action": "time-bounded reviewed exception; re-evaluate by expiry",
                "advisory": advisory,
                "exceptionExpires": "2026-08-27",
                "exceptionId": exception_id,
                "fixedVersion": fixed_version,
                "owner": "RouteContract maintainers",
                "purl": purl,
                "rationaleCode": "SHARDINGSPHERE_5_5_3_TEST_GRAPH",
                "reachabilityEvidence": {
                    "exampleProfile": True,
                    "publishedProfile": False,
                    "publishedRuntime": False,
                },
                "reviewedAt": "2026-08-12",
                "scope": "aggregate-test-only",
                "severity": severity,
            }
            for exception_id, advisory, purl, fixed_version, severity in vulnerability_exceptions
        ]
        evidence = {
            "exampleProfile": {
                "componentLicenseCount": 2,
                "mavenPackageCount": 2,
                "resolvedProfileSha256": "1" * 64,
                "sbomSha256": "2" * 64,
                "xmlComponentCount": 2,
                "xmlSha256": "3" * 64,
            },
            "publishedModule": {
                "componentLicenseCount": 2,
                "dependencyLockSha256": "4" * 64,
                "mavenPackageCount": 2,
                "pomDependencyCount": 1,
                "pomSha256": sha256(self.root / self.pom_name),
                "resolvedProfileSha256": "5" * 64,
                "runtimeClosureCount": 1,
                "runtimeClosureSha256": "6" * 64,
                "sbomSha256": sha256(published_json),
                "xmlComponentCount": 2,
                "xmlSha256": sha256(published_xml),
            },
            "revision": "a" * 40,
            "sbom": {
                "componentLicenseCount": 4,
                "inventorySha256": "7" * 64,
                "licensePolicy": "passed",
                "licenseReviews": license_reviews,
                "mavenPackageCount": 4,
                "policySha256": "8" * 64,
                "sha256": sha256(aggregate_json),
                "unresolvedLicenseReviewCount": 2,
                "xmlComponentCount": 4,
                "xmlSha256": sha256(aggregate_xml),
            },
            "scanner": {
                "binarySha256": "9" * 64,
                "binarySize": 10,
                "binaryUrl": "https://example.invalid/osv-scanner",
                "commit": "b" * 40,
                "database": {
                    "ecosystem": "Maven",
                    "generation": "1",
                    "lastModified": "2026-08-09T03:03:50.782Z",
                    "sha256": "c" * 64,
                    "size": 10,
                    "url": "https://example.invalid/Maven/all.zip?generation=1",
                },
                "name": "OSV-Scanner",
                "platform": "linux-x86_64",
                "scalibrVersion": "0.4.5",
                "scannerConfigSha256": hashlib.sha256(b"").hexdigest(),
                "scannerLockSha256": "d" * 64,
                "version": "2.5.0",
            },
            "schemaVersion": 1,
            "sourceTree": "e" * 40,
            "vulnerabilities": {
                "acceptedExceptionCount": 3,
                "findingCount": 3,
                "findings": findings,
                "unreviewedCount": 0,
            },
        }
        (self.root / "supply-chain-evidence.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def write_main_jar(
        self,
        module_name: str,
        *,
        extra_entries: tuple[str, ...] = (),
        provider_text: str = EXPECTED_PROVIDER + "\n",
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
                provider_text,
            )
            archive.writestr(
                "io/github/ym0506/routecontract/RouteContract.class", b"fixture"
            )
            for entry in extra_entries:
                archive.writestr(entry, b"unexpected fixture")
            archive.writestr("META-INF/LICENSE", "Apache-2.0 fixture")
            archive.writestr("META-INF/NOTICE", "RouteContract fixture")

    def write_source_archive(
        self,
        *,
        root_name: str | None = None,
        extra_relative_entries: tuple[str, ...] = (),
        omitted_relative_entries: tuple[str, ...] = (),
        content_overrides: dict[str, str] | None = None,
    ) -> None:
        if root_name is None:
            root_name = f"routecontract-{self.version}"
        omitted = set(omitted_relative_entries)
        source_content = {
            SOURCE_PUBLIC_API_PATH: (
                "package io.github.ym0506.routecontract;\n"
                "public final class RouteContract {}\n"
            ),
            SOURCE_HOOK_PATH: (
                "package io.github.ym0506.routecontract.internal;\n"
                "public final class RouteContractSqlExecutionHook "
                "implements SQLExecutionHook {}\n"
            ),
            SOURCE_SERVICE_DESCRIPTOR_PATH: (
                "io.github.ym0506.routecontract.internal."
                "RouteContractSqlExecutionHook\n"
            ),
        }
        if content_overrides:
            source_content.update(content_overrides)
        with ZipFile(
            self.root / self.source_archive_name, "w", ZIP_DEFLATED
        ) as archive:
            for relative in sorted(SOURCE_REQUIRED_RELATIVE_PATHS - omitted):
                archive.writestr(
                    f"{root_name}/{relative}",
                    source_content.get(relative, "fixture"),
                )
            for relative in extra_relative_entries:
                archive.writestr(
                    f"{root_name}/{relative}",
                    source_content.get(relative, "extra fixture"),
                )

    def public_payloads(self) -> list[Path]:
        return sorted(path for path in self.root.iterdir() if path.name != "SHA256SUMS")

    def append_source_entry(
        self,
        relative: str,
        content: bytes | str = b"extra fixture",
        *,
        unix_mode: int | None = None,
    ) -> None:
        info = ZipInfo(f"routecontract-{self.version}/{relative}")
        info.compress_type = ZIP_STORED if relative.endswith("/") else ZIP_DEFLATED
        info.create_system = 3
        if unix_mode is not None:
            info.external_attr = unix_mode << 16
        with ZipFile(self.root / self.source_archive_name, "a") as archive:
            archive.writestr(info, content)

    def append_jar_entry(
        self,
        jar_name: str,
        entry: str,
        content: bytes | str = b"extra fixture",
        *,
        unix_mode: int | None = None,
    ) -> None:
        info = ZipInfo(entry)
        info.compress_type = ZIP_STORED if entry.endswith("/") else ZIP_DEFLATED
        info.create_system = 3
        if unix_mode is not None:
            info.external_attr = unix_mode << 16
        with ZipFile(self.root / jar_name, "a") as archive:
            archive.writestr(info, content)

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

    def test_accepts_strict_release_candidate_coordinate(self) -> None:
        for version in ("1.2.3-rc1", "1.2.3-rc2"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets, version)
                fixture.create()
                repository = root / "consumer-maven"

                result = self.run_installer(assets, repository, home=root / "home")

                self.assertEqual(0, result.returncode, result.stderr)
                coordinate = (
                    repository
                    / Path(*GROUP_ID.split("."))
                    / ARTIFACT_ID
                    / version
                )
                self.assertTrue(coordinate.is_dir())
                self.assertIn(
                    f"{GROUP_ID}:{ARTIFACT_ID}:{version}", result.stdout
                )

    def test_rejects_supply_chain_evidence_bound_to_other_public_sbom(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            evidence_path = assets / "supply-chain-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["sbom"]["sha256"] = "f" * 64
            evidence_path.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            fixture.write_checksums()

            result = self.run_installer(
                assets, root / "consumer-maven", home=root / "home"
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("does not match the public asset", result.stderr)
            self.assertFalse((root / "consumer-maven").exists())

    def test_rejects_supply_chain_evidence_with_unreviewed_findings(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            evidence_path = assets / "supply-chain-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["vulnerabilities"]["unreviewedCount"] = 1
            evidence_path.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            fixture.write_checksums()

            result = self.run_installer(
                assets, root / "consumer-maven", home=root / "home"
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("unreviewed vulnerabilities", result.stderr)
            self.assertFalse((root / "consumer-maven").exists())

    def test_rejects_incomplete_unresolved_license_review_set(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            evidence_path = assets / "supply-chain-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["sbom"]["licenseReviews"].pop()
            evidence_path.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            fixture.write_checksums()

            result = self.run_installer(
                assets, root / "consumer-maven", home=root / "home"
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("exactly two license reviews", result.stderr)
            self.assertFalse((root / "consumer-maven").exists())

    def test_rejects_reversed_license_review_order(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            evidence_path = assets / "supply-chain-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["sbom"]["licenseReviews"].reverse()
            evidence_path.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            fixture.write_checksums()

            result = self.run_installer(
                assets, root / "consumer-maven", home=root / "home"
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("exact required order", result.stderr)
            self.assertFalse((root / "consumer-maven").exists())

    def test_rejects_boolean_supply_chain_vulnerability_count(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            evidence_path = assets / "supply-chain-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["vulnerabilities"]["unreviewedCount"] = False
            evidence_path.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            fixture.write_checksums()

            result = self.run_installer(
                assets, root / "consumer-maven", home=root / "home"
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("must be a non-negative integer", result.stderr)
            self.assertFalse((root / "consumer-maven").exists())

    def test_rejects_non_integer_supply_chain_schema_version(self) -> None:
        for invalid_version in (True, 1.0):
            with self.subTest(value=invalid_version), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                evidence_path = assets / "supply-chain-evidence.json"
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                evidence["schemaVersion"] = invalid_version
                evidence_path.write_text(
                    json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                fixture.write_checksums()

                result = self.run_installer(
                    assets, root / "consumer-maven", home=root / "home"
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn("unsupported supply-chain evidence schemaVersion", result.stderr)
                self.assertFalse((root / "consumer-maven").exists())

    def test_consumer_verification_trust_is_exact_and_rc_aware(self) -> None:
        metadata = ET.parse(
            REPOSITORY_ROOT
            / "examples/standalone-consumer/gradle/verification-metadata.xml"
        )
        rules = [
            element
            for element in metadata.getroot().iter()
            if element.tag.rsplit("}", 1)[-1] == "trust"
        ]
        self.assertEqual(1, len(rules))
        rule = rules[0]
        self.assertEqual("true", rule.attrib.get("regex"))
        self.assertEqual(
            "^io[.]github[.]ym0506[.]routecontract$", rule.attrib.get("group")
        )
        self.assertEqual(
            "^routecontract-shardingsphere-5[.]5$", rule.attrib.get("name")
        )
        version_pattern = rule.attrib["version"]
        self.assertIsNotNone(re.fullmatch(version_pattern, "1.2.3"))
        self.assertIsNotNone(re.fullmatch(version_pattern, "1.2.3-rc1"))
        for rejected in ("1.2.3-SNAPSHOT", "1.2.3-rc0", "1.2.3-beta1"):
            self.assertIsNone(re.fullmatch(version_pattern, rejected))

    def test_accepts_current_git_archive_source_shape(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            archive_result = subprocess.run(
                [
                    "git",
                    "archive",
                    "--format=zip",
                    f"--prefix=routecontract-{VERSION}/",
                    f"--output={assets / fixture.source_archive_name}",
                    "HEAD",
                ],
                cwd=REPOSITORY_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(0, archive_result.returncode, archive_result.stdout)
            fixture.write_checksums()
            repository = root / "consumer-maven"

            result = self.run_installer(assets, repository, home=root / "home")

            self.assertEqual(0, result.returncode, result.stderr)
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
            "io/github/developkim/nested/routecontract/Legacy.class",
            "IO/GITHUB/developkim/routecontract/Legacy.class",
            "IO/GITHUB/YM0506/routecontract/Legacy.class",
            "io/github/routecontract/Legacy.class",
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
                expected_error = (
                    "case or Unicode-normalization path collision"
                    if legacy_entry.startswith("IO/")
                    else "unexpected RouteContract package namespace"
                )
                self.assertIn(expected_error, result.stderr)
                self.assertFalse(repository.exists())

    def test_rejects_nonportable_ambiguous_or_special_jar_entries(self) -> None:
        cases = (
            (
                "main",
                (("pipe", stat.S_IFIFO | 0o600),),
                "special or mismatched Unix entry",
            ),
            (
                "sources",
                (("docs/data:secret", None),),
                "not portable across filesystems",
            ),
            (
                "javadoc",
                (("Docs/Guide.txt", None), ("docs/guide.txt", None)),
                "case or Unicode-normalization path collision",
            ),
        )
        for jar_kind, entries, expected_error in cases:
            with (
                self.subTest(jar=jar_kind),
                tempfile.TemporaryDirectory() as raw,
            ):
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                jar_name = {
                    "main": fixture.main_jar_name,
                    "sources": fixture.sources_jar_name,
                    "javadoc": fixture.javadoc_jar_name,
                }[jar_kind]
                for entry, unix_mode in entries:
                    fixture.append_jar_entry(
                        jar_name, entry, unix_mode=unix_mode
                    )
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(
                    assets, repository, home=root / "home"
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn(expected_error, result.stderr)
                self.assertFalse(repository.exists())

    def test_rejects_jar_entry_count_over_safety_limit(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            with ZipFile(
                assets / fixture.javadoc_jar_name, "a", ZIP_STORED
            ) as archive:
                for index in range(20_000):
                    archive.writestr(f"entries/{index:05d}", b"")
            fixture.write_checksums()
            repository = root / "consumer-maven"

            result = self.run_installer(
                assets, repository, home=root / "home"
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("20000-entry safety limit", result.stderr)
            self.assertFalse(repository.exists())

    def test_rejects_excessively_deep_archive_paths_in_bounded_time(self) -> None:
        deep_relative = "/".join(["d"] * 256 + ["payload"])
        for location in ("jar", "source"):
            with (
                self.subTest(location=location),
                tempfile.TemporaryDirectory() as raw,
            ):
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                if location == "jar":
                    fixture.append_jar_entry(
                        fixture.javadoc_jar_name,
                        deep_relative,
                    )
                else:
                    fixture.append_source_entry(deep_relative)
                fixture.write_checksums()
                repository = root / "consumer-maven"

                started = time.monotonic()
                result = self.run_installer(
                    assets, repository, home=root / "home"
                )
                elapsed = time.monotonic() - started

                self.assertNotEqual(0, result.returncode)
                self.assertIn("256-component safety limit", result.stderr)
                self.assertLess(elapsed, 5.0)
                self.assertFalse(repository.exists())

    def test_rejects_aggregate_archive_path_component_exhaustion(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            with ZipFile(
                assets / fixture.javadoc_jar_name, "a", ZIP_STORED
            ) as archive:
                for index in range(391):
                    components = [f"branch-{index:03d}", *(["d"] * 254), "payload"]
                    archive.writestr("/".join(components), b"")
            fixture.write_checksums()
            repository = root / "consumer-maven"

            started = time.monotonic()
            result = self.run_installer(
                assets, repository, home=root / "home"
            )
            elapsed = time.monotonic() - started

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "100000-total-path-component safety limit", result.stderr
            )
            self.assertLess(elapsed, 5.0)
            self.assertFalse(repository.exists())

    def test_rejects_service_descriptors_incompatible_with_java(self) -> None:
        cases = (
            ("main", "\u00a0" + EXPECTED_PROVIDER + "\n"),
            ("source", EXPECTED_PROVIDER + "\u2028# comment\n"),
        )
        for location, descriptor in cases:
            with (
                self.subTest(location=location),
                tempfile.TemporaryDirectory() as raw,
            ):
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                if location == "main":
                    fixture.write_main_jar(
                        "io.github.ym0506.routecontract.shardingsphere55",
                        provider_text=descriptor,
                    )
                else:
                    fixture.write_source_archive(
                        content_overrides={
                            SOURCE_SERVICE_DESCRIPTOR_PATH: descriptor
                        }
                    )
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(
                    assets, repository, home=root / "home"
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn("unexpected SQLExecutionHook provider", result.stderr)
                self.assertFalse(repository.exists())

    def test_rejects_source_archive_with_wrong_versioned_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            fixture.write_source_archive(root_name="routecontract-9.9.9")
            fixture.write_checksums()
            repository = root / "consumer-maven"

            result = self.run_installer(assets, repository, home=root / "home")

            self.assertNotEqual(0, result.returncode)
            self.assertIn("exactly one versioned root", result.stderr)
            self.assertFalse(repository.exists())

    def test_rejects_alternate_package_namespace_in_source_archive(self) -> None:
        unexpected_paths = (
            (
                "routecontract-shardingsphere-5.5/src/main/java/"
                "io/github/developkim/routecontract/Legacy.java",
                "unexpected RouteContract package namespace",
            ),
            (
                "routecontract-shardingsphere-5.5/src/main/java/"
                "io/github/example-owner/routecontract/Legacy.java",
                "unexpected RouteContract package namespace",
            ),
            (
                "routecontract-shardingsphere-5.5/src/main/java/"
                "io/github/example-owner/nested/routecontract/Legacy.java",
                "unexpected RouteContract package namespace",
            ),
            (
                "routecontract-shardingsphere-5.5/src/main/java/"
                "IO/GITHUB/example-owner/routecontract/Legacy.java",
                "case or Unicode-normalization path collision",
            ),
            (
                "routecontract-shardingsphere-5.5/src/main/java/"
                "IO/GITHUB/YM0506/routecontract/Legacy.java",
                "case or Unicode-normalization path collision",
            ),
            (
                "routecontract-shardingsphere-5.5/src/main/java/"
                "io/github/routecontract/Legacy.java",
                "unexpected RouteContract package namespace",
            ),
            (
                "routecontract-shardingsphere-5.5/src/main/java/"
                "io/github/ym0506/routecontract/generated/"
                "io/github/developkim/routecontract/Legacy.java",
                "unexpected RouteContract package namespace",
            ),
        )
        for unexpected_path, expected_error in unexpected_paths:
            with (
                self.subTest(path=unexpected_path),
                tempfile.TemporaryDirectory() as raw,
            ):
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                fixture.write_source_archive(
                    extra_relative_entries=(unexpected_path,)
                )
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(
                    assets, repository, home=root / "home"
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn(expected_error, result.stderr)
                self.assertFalse(repository.exists())

    def test_rejects_source_archive_missing_required_source_path(self) -> None:
        for missing in (
            "NOTICE",
            "routecontract-shardingsphere-5.5/src/main/java/"
            "io/github/ym0506/routecontract/internal/"
            "RouteContractSqlExecutionHook.java",
        ):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                fixture.write_source_archive(omitted_relative_entries=(missing,))
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(assets, repository, home=root / "home")

                self.assertNotEqual(0, result.returncode)
                self.assertIn("missing canonical source paths", result.stderr)
                self.assertFalse(repository.exists())

    def test_rejects_source_archive_with_mismatched_canonical_text(self) -> None:
        cases = (
            (
                SOURCE_PUBLIC_API_PATH,
                "package io.github.developkim.routecontract;\n",
                "public API has an unexpected package declaration",
            ),
            (
                SOURCE_HOOK_PATH,
                "package io.github.developkim.routecontract.internal;\n",
                "hook has an unexpected package declaration",
            ),
            (
                SOURCE_SERVICE_DESCRIPTOR_PATH,
                "io.github.developkim.routecontract.internal.LegacyHook\n",
                "unexpected SQLExecutionHook provider",
            ),
        )
        for relative, content, expected_error in cases:
            with (
                self.subTest(path=relative),
                tempfile.TemporaryDirectory() as raw,
            ):
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                fixture.write_source_archive(
                    content_overrides={relative: content}
                )
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(
                    assets, repository, home=root / "home"
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn(expected_error, result.stderr)
                self.assertFalse(repository.exists())

    def test_rejects_unsafe_source_names_and_special_unix_types(self) -> None:
        cases = (
            ("../escape.txt", None, "unsafe entry"),
            ("docs\\secret.txt", None, "unsafe entry"),
            ("README.md.", None, "not portable across filesystems"),
            ("docs/trailing. ", None, "not portable across filesystems"),
            ("keys/release.key.", None, "not portable across filesystems"),
            ("submission/private./identity.json", None, "not portable across filesystems"),
            ("docs/.. /escape.txt", None, "not portable across filesystems"),
            ("docs/. /inside.txt", None, "not portable across filesystems"),
            ("docs/data:secret", None, "not portable across filesystems"),
            ("CON.txt", None, "reserved Windows name"),
            ("docs/COM1.log", None, "reserved Windows name"),
            ("docs/LPT¹.log", None, "reserved Windows name"),
            ("link", stat.S_IFLNK | 0o777, "special or mismatched Unix entry"),
            ("pipe", stat.S_IFIFO | 0o600, "special or mismatched Unix entry"),
            ("typed-directory/", stat.S_IFREG | 0o644, "incompatible Unix type"),
        )
        for relative, unix_mode, expected_error in cases:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                fixture.append_source_entry(relative, unix_mode=unix_mode)
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(
                    assets, repository, home=root / "home"
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn(expected_error, result.stderr)
                self.assertFalse(repository.exists())

    def test_rejects_source_directory_with_a_payload(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            fixture.append_source_entry(
                "padding/", b"not empty", unix_mode=stat.S_IFDIR | 0o755
            )
            fixture.write_checksums()
            repository = root / "consumer-maven"

            result = self.run_installer(assets, repository, home=root / "home")

            self.assertNotEqual(0, result.returncode)
            self.assertIn("directory contains a payload", result.stderr)
            self.assertFalse(repository.exists())

    def test_rejects_ambiguous_source_path_graphs(self) -> None:
        cases = (
            (("README.md/",), "duplicate logical path"),
            (("docs", "docs/page.md"), "file/descendant path collision"),
            (("Docs", "docs/page.md"), "case or Unicode-normalization path"),
            (("Docs/", "docs/page.md"), "case or Unicode-normalization path"),
            (("Docs/Guide.md", "docs/guide.md"), "case or Unicode-normalization"),
            (
                (
                    "routecontract-shardingsphere-5.5/src/",
                    "routecontract-shardingsphere-5.5/SRC/main/java/Injected.java",
                ),
                "case or Unicode-normalization path",
            ),
        )
        for entries, expected_error in cases:
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                for relative in entries:
                    mode = stat.S_IFDIR | 0o755 if relative.endswith("/") else None
                    content = b"" if relative.endswith("/") else b"extra"
                    fixture.append_source_entry(relative, content, unix_mode=mode)
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(
                    assets, repository, home=root / "home"
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn(expected_error, result.stderr)
                self.assertFalse(repository.exists())

    def test_rejects_nul_truncated_source_entry_name(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            fixture.append_source_entry("nulXsuffix.txt")
            archive_path = assets / fixture.source_archive_name
            raw_archive = archive_path.read_bytes()
            encoded_name = (
                f"routecontract-{VERSION}/nulXsuffix.txt".encode("ascii")
            )
            self.assertEqual(2, raw_archive.count(encoded_name))
            archive_path.write_bytes(
                raw_archive.replace(encoded_name, encoded_name.replace(b"X", b"\x00"))
            )
            fixture.write_checksums()
            repository = root / "consumer-maven"

            result = self.run_installer(assets, repository, home=root / "home")

            self.assertNotEqual(0, result.returncode)
            self.assertIn("truncated or NUL-bearing entry name", result.stderr)
            self.assertFalse(repository.exists())

    def test_rejects_encrypted_source_archive_flag(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            archive_path = assets / fixture.source_archive_name
            raw_archive = bytearray(archive_path.read_bytes())
            patched_headers = 0
            for signature, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
                cursor = 0
                while True:
                    header = raw_archive.find(signature, cursor)
                    if header < 0:
                        break
                    flags = int.from_bytes(
                        raw_archive[header + flag_offset : header + flag_offset + 2],
                        "little",
                    )
                    raw_archive[header + flag_offset : header + flag_offset + 2] = (
                        flags | 0x1
                    ).to_bytes(2, "little")
                    patched_headers += 1
                    cursor = header + 4
            self.assertGreater(patched_headers, 1)
            archive_path.write_bytes(raw_archive)
            fixture.write_checksums()
            repository = root / "consumer-maven"

            result = self.run_installer(assets, repository, home=root / "home")

            self.assertNotEqual(0, result.returncode)
            self.assertIn("unsafe entry", result.stderr)
            self.assertFalse(repository.exists())

    def test_rejects_private_generated_and_credential_like_source_paths(self) -> None:
        forbidden_paths = (
            ".aws/credentials",
            ".netrc",
            ".npmrc",
            ".pypirc",
            ".ssh/id_ed25519",
            "private_codex/prompt.txt",
            "PRIVATE_CODEX/prompt.txt",
            "Private_Notes/prompt.txt",
            ".DS_Store",
            "cache/result.pyc",
            "out/generated.txt",
            "Build/generated.txt",
            "submission/private",
            "Submission/Private/identity.json",
            ".env.local",
            "keys/release.key",
            "credentials.json",
            "id_rsa",
        )
        for relative in forbidden_paths:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                fixture.append_source_entry(relative)
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(
                    assets, repository, home=root / "home"
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn("private or generated path", result.stderr)
                self.assertFalse(repository.exists())

    def test_rejects_commented_package_decoy_in_canonical_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            fixture.write_source_archive(
                content_overrides={
                    SOURCE_PUBLIC_API_PATH: (
                        "/* package io.github.ym0506.routecontract; */\n"
                        "package io.github.developkim.routecontract;\n"
                        "public final class RouteContract {}\n"
                    )
                }
            )
            fixture.write_checksums()
            repository = root / "consumer-maven"

            result = self.run_installer(assets, repository, home=root / "home")

            self.assertNotEqual(0, result.returncode)
            self.assertIn("public API has an unexpected package declaration", result.stderr)
            self.assertFalse(repository.exists())

    def test_applies_java_unicode_escapes_before_package_validation(self) -> None:
        escape_prefixes = (
            "\r",
            "\\u000a",
            "\\u005c\\u000a",
            "\\u005c\\\\u000a",
            "\\u000d",
            "\\u005c\\u000d",
            "\\u005c\\\\u000d",
        )
        for escape_prefix in escape_prefixes:
            with self.subTest(escape=escape_prefix), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                extra_java = (
                    "routecontract-shardingsphere-5.5/src/test/java/"
                    "io/github/ym0506/routecontract/Legacy.java"
                )
                fixture.write_source_archive(
                    extra_relative_entries=(extra_java,),
                    content_overrides={
                        extra_java: (
                            f"// {escape_prefix}package "
                            "io.github.developkim.routecontract; /*\n"
                            "package io.github.ym0506.routecontract; */\n"
                            "final class Legacy {}\n"
                        )
                    },
                )
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(
                    assets, repository, home=root / "home"
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn("Java package does not match its path", result.stderr)
                self.assertFalse(repository.exists())

    def test_rejects_malformed_eligible_unicode_escape_after_tandem_backslashes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            extra_java = (
                "routecontract-shardingsphere-5.5/src/test/java/"
                "io/github/ym0506/routecontract/Malformed.java"
            )
            fixture.write_source_archive(
                extra_relative_entries=(extra_java,),
                content_overrides={
                    extra_java: (
                        "// \\u005c\\\\u00G0\n"
                        "package io.github.ym0506.routecontract;\n"
                        "final class Malformed {}\n"
                    )
                },
            )
            fixture.write_checksums()
            repository = root / "consumer-maven"

            result = self.run_installer(assets, repository, home=root / "home")

            self.assertNotEqual(0, result.returncode)
            self.assertIn("malformed Unicode escape", result.stderr)
            self.assertFalse(repository.exists())

    def test_applies_tandem_unicode_escape_to_canonical_sources(self) -> None:
        cases = (
            (
                SOURCE_PUBLIC_API_PATH,
                (
                    "// \\u005c\\\\u000apackage "
                    "io.github.developkim.routecontract; /*\n"
                    "package io.github.ym0506.routecontract; */\n"
                    "public final class RouteContract {}\n"
                ),
                "public API has an unexpected package declaration",
            ),
            (
                SOURCE_HOOK_PATH,
                (
                    "// \\u005c\\\\u000apackage "
                    "io.github.developkim.routecontract.internal; /*\n"
                    "package io.github.ym0506.routecontract.internal; */\n"
                    "public final class RouteContractSqlExecutionHook "
                    "implements SQLExecutionHook {}\n"
                ),
                "hook has an unexpected package declaration",
            ),
        )
        for relative, content, expected_error in cases:
            with (
                self.subTest(path=relative),
                tempfile.TemporaryDirectory() as raw,
            ):
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                fixture.write_source_archive(content_overrides={relative: content})
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(
                    assets, repository, home=root / "home"
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn(expected_error, result.stderr)
                self.assertFalse(repository.exists())

    def test_release_evidence_workflow_is_tag_push_only_and_main_bound(self) -> None:
        workflow = (
            REPOSITORY_ROOT / ".github/workflows/release-evidence.yml"
        ).read_text(encoding="utf-8")

        self.assertNotIn("workflow_dispatch:", workflow)
        for required_contract in (
            "test \"${GITHUB_EVENT_NAME}\" = 'push'",
            "test \"${GITHUB_REF_TYPE}\" = 'tag'",
            "test \"${tagged_commit}\" = \"${GITHUB_SHA}\"",
            "git ls-remote --exit-code origin refs/heads/main",
            "test \"${tagged_commit}\" = \"${main_commit}\"",
            "release_version_pattern='^(0|[1-9][0-9]{0,8})",
            '[[ ! "${project_version}" =~ ${release_version_pattern} ]]',
            'test "v${project_version}" = "${GITHUB_REF_NAME}"',
            "./scripts/run-final-supply-chain-scan.sh --revision \"${GITHUB_SHA}\"",
            "'supply-chain-evidence.json'",
            'test ! -e "${evidence_dir}/osv-raw.json"',
            ")\" = '17'",
            "routecontract-mysql-example-cyclonedx.json",
            "scripts/validate-official-cyclonedx.py",
        ):
            self.assertIn(required_contract, workflow)
        self.assertNotIn("osv-raw.json\" \"${public_dir}", workflow)

    def test_rejects_wrong_active_package_in_any_java_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            extra_java = (
                "routecontract-shardingsphere-5.5/src/test/java/"
                "io/github/ym0506/routecontract/Legacy.java"
            )
            fixture.write_source_archive(
                extra_relative_entries=(extra_java,),
                content_overrides={
                    extra_java: (
                        "package io.github.developkim.routecontract;\n"
                        "final class Legacy {}\n"
                    )
                },
            )
            fixture.write_checksums()
            repository = root / "consumer-maven"

            result = self.run_installer(assets, repository, home=root / "home")

            self.assertNotEqual(0, result.returncode)
            self.assertIn("Java package does not match its path", result.stderr)
            self.assertFalse(repository.exists())

    def test_rejects_hook_without_expected_top_level_provider_class(self) -> None:
        invalid_declarations = (
            (
                "/* public final class RouteContractSqlExecutionHook "
                "implements SQLExecutionHook {} */\n"
                "final class DifferentHook {}\n"
            ),
            (
                "public final class RouteContractSqlExecutionHook "
                "implements SQLExecutionHook;\n"
            ),
        )
        for declaration in invalid_declarations:
            with self.subTest(declaration=declaration), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                fixture.write_source_archive(
                    content_overrides={
                        SOURCE_HOOK_PATH: (
                            "package io.github.ym0506.routecontract.internal;\n"
                            + declaration
                        )
                    }
                )
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(
                    assets, repository, home=root / "home"
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn("expected top-level SPI class", result.stderr)
                self.assertFalse(repository.exists())

    def test_rejects_non_zip_source_archive(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "release"
            fixture = ReleaseFixture(assets)
            fixture.create()
            (assets / fixture.source_archive_name).write_bytes(b"not a ZIP")
            fixture.write_checksums()
            repository = root / "consumer-maven"

            result = self.run_installer(assets, repository, home=root / "home")

            self.assertNotEqual(0, result.returncode)
            self.assertIn("source archive is not a valid ZIP", result.stderr)
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

    def test_rejects_non_utf8_pom_with_dtd_before_writing(self) -> None:
        xml = f"""<?xml version="1.0" encoding="ENCODING"?>
<!DOCTYPE project [<!ENTITY group "{GROUP_ID}">]>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>&group;</groupId>
  <artifactId>{ARTIFACT_ID}</artifactId>
  <version>{VERSION}</version>
</project>
"""
        for encoding in ("utf-16", "utf-32"):
            with (
                self.subTest(encoding=encoding),
                tempfile.TemporaryDirectory() as raw,
            ):
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                pom = assets / fixture.pom_name
                pom.write_bytes(
                    xml.replace("ENCODING", encoding.upper()).encode(encoding)
                )
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(
                    assets, repository, home=root / "home"
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn("valid UTF-8 XML", result.stderr)
                self.assertFalse(repository.exists())

    def test_rejects_utf8_pom_declaring_a_different_encoding(self) -> None:
        for declared_encoding in ("UTF-16", "ISO-8859-1", "x-bogus"):
            with (
                self.subTest(encoding=declared_encoding),
                tempfile.TemporaryDirectory() as raw,
            ):
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                pom = assets / fixture.pom_name
                text = pom.read_text(encoding="utf-8")
                pom.write_bytes(
                    text.replace(
                        '<?xml version="1.0" encoding="UTF-8"?>',
                        f'<?xml version="1.0" encoding="{declared_encoding}"?>',
                    )
                    .replace(
                        "<modelVersion>4.0.0</modelVersion>",
                        "<modelVersion>4.0.0</modelVersion>"
                        "<name>R\u00e9sum\u00e9 \ud55c\uae00</name>",
                    )
                    .encode("utf-8")
                )
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(
                    assets, repository, home=root / "home"
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn("XML declaration must specify", result.stderr)
                self.assertFalse(repository.exists())

    def test_rejects_non_scalar_or_unicode_padded_pom_values(self) -> None:
        replacements = (
            (
                f"<groupId>{GROUP_ID}</groupId>",
                f"<groupId>{GROUP_ID}<nested/></groupId>",
                "must not contain nested XML elements",
            ),
            (
                f"<groupId>{GROUP_ID}</groupId>",
                f"<groupId>\u00a0{GROUP_ID}\u00a0</groupId>",
                f"groupId must be exactly {GROUP_ID}",
            ),
        )
        for old, new, expected_error in replacements:
            with (
                self.subTest(replacement=new),
                tempfile.TemporaryDirectory() as raw,
            ):
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                pom = assets / fixture.pom_name
                pom.write_text(
                    pom.read_text(encoding="utf-8").replace(old, new),
                    encoding="utf-8",
                )
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(
                    assets, repository, home=root / "home"
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn(expected_error, result.stderr)
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
            self.assertIn("MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-rcN", result.stderr)
            self.assertFalse(repository.exists())

    def test_rejects_noncanonical_release_candidate_versions(self) -> None:
        for version in ("1.2.3-rc0", "1.2.3-rc01", "1.2.3-beta1", "1.2.3-rc1-SNAPSHOT"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                pom = assets / fixture.pom_name
                pom.write_text(
                    pom.read_text(encoding="utf-8").replace(
                        f"<version>{VERSION}</version>",
                        f"<version>{version}</version>",
                    ),
                    encoding="utf-8",
                )
                fixture.write_checksums()
                repository = root / "consumer-maven"

                result = self.run_installer(
                    assets, repository, home=root / "home"
                )

                self.assertNotEqual(0, result.returncode)
                self.assertIn(
                    "MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-rcN",
                    result.stderr,
                )
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

    def test_rejects_conventional_default_maven_repository(self) -> None:
        for relative in (
            Path(".m2/repository"),
            Path(".m2/repository/isolated"),
            Path(".M2/Repository"),
            Path(".M2/Repository/isolated"),
        ):
            with (
                self.subTest(relative=relative),
                tempfile.TemporaryDirectory() as raw,
            ):
                root = Path(raw)
                assets = root / "release"
                fixture = ReleaseFixture(assets)
                fixture.create()
                home = root / "home"
                home.mkdir()
                repository = home / relative

                result = self.run_installer(assets, repository, home=home)

                self.assertNotEqual(0, result.returncode)
                self.assertIn(
                    "must not be the conventional ~/.m2/repository", result.stderr
                )
                self.assertFalse(repository.exists())

    @unittest.skipIf(pwd is None, "POSIX account home is unavailable")
    def test_rejects_account_home_maven_repository_when_home_is_overridden(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            assets = root / "empty-release"
            assets.mkdir()
            fake_home = root / "fake-home"
            fake_home.mkdir()
            account_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
            repository = (
                account_home
                / ".m2"
                / "repository"
                / "routecontract-default-guard-probe"
            )

            result = self.run_installer(
                assets, repository, home=fake_home
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "must not be the conventional ~/.m2/repository", result.stderr
            )

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
            release_version = "1.2.3-rc1"
            fixture = ReleaseFixture(assets, release_version)
            fixture.create()
            for suffix in ("", "-sources", "-javadoc"):
                shutil.copyfile(
                    module / "build/libs" / f"{ARTIFACT_ID}-{built_version}{suffix}.jar",
                    assets / f"{ARTIFACT_ID}-{release_version}{suffix}.jar",
                )
            generated_pom = generated_pom.replace(
                f"<version>{built_version}</version>",
                f"<version>{release_version}</version>",
                1,
            )
            (assets / fixture.pom_name).write_text(generated_pom, encoding="utf-8")
            fixture.write_supply_chain_evidence()
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
                f"coordinate={GROUP_ID}:{ARTIFACT_ID}:{release_version} "
                "result=VERIFIED_MYSQL",
                result.stdout,
            )


if __name__ == "__main__":
    unittest.main()
