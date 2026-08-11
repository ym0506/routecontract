from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile


SCRIPT = Path(__file__).resolve().parents[1] / "package_submission.py"
SPEC = importlib.util.spec_from_file_location("package_submission", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
package_submission = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_submission)


def digest(character: str = "a") -> str:
    return character * 64


def valid_test_summary(revision: str) -> str:
    suites = {
        "io.github.ym0506.routecontract.RouteContractTest": 18,
        "io.github.ym0506.routecontract.example.DataSourceProxyComparisonMySqlTest": 1,
        "io.github.ym0506.routecontract.example.FailureBoundaryMySqlTest": 1,
        "io.github.ym0506.routecontract.example.ObservedExecutionRegressionCorpusMySqlTest": 7,
        "io.github.ym0506.routecontract.example.OperationCorrelationMySqlTest": 5,
        "io.github.ym0506.routecontract.internal.ShardingSphere553PreflightTest": 3,
        "io.github.ym0506.routecontract.manifest.ObservedExecutionManifestTest": 15,
    }
    lines = [
        "format=routecontract-test-summary-v1",
        f"revision={revision}",
        "suite_count=7",
        "test_count=50",
        "failure_count=0",
        "error_count=0",
        "skipped_count=0",
    ]
    lines.extend(
        f"suite={suite}|tests={suites[suite]}|failures=0|errors=0|skipped=0"
        for suite in sorted(suites)
    )
    return "\n".join(lines) + "\n"


def valid_manifest() -> dict:
    return {
        "schema_version": 1,
        "official_notice_url": "https://osscontest.kr/notice/39",
        "project": {
            "slug": "routecontract",
            "repository_url": "https://github.com/example-owner/routecontract",
            "commit": "1" * 40,
            "tag": "v0.1.0",
            "ci_run_url": (
                "https://github.com/example-owner/routecontract/actions/runs/123456"
            ),
            "release_url": (
                "https://github.com/example-owner/routecontract/releases/tag/v0.1.0"
            ),
        },
        "report": {
            "docx_sha256": digest("2"),
            "pdf_sha256": digest("3"),
            "runtime_ai_attachment": "not_applicable",
        },
        "video": {
            "youtube_url": "https://www.youtube.com/watch?v=abcdefghijk",
            "title": "RouteContract demo",
            "duration_seconds": 179.5,
            "local_file_sha256": digest("4"),
        },
        "release_evidence": {
            "workflow_artifact_id": 987654,
            "workflow_artifact_sha256": digest("a"),
            "source_archive_filename": "routecontract-0.1.0-source.zip",
            "source_archive_sha256": digest("5"),
            "aggregate_sbom_json_sha256": digest("6"),
            "aggregate_sbom_xml_sha256": digest("7"),
            "signature_filenames": [],
        },
        "participant_attestations": {
            "registration_matches_report": True,
            "single_entry_per_participant_confirmed": True,
            "duplicate_benefit_status_reviewed": True,
            "ai_assistance_scope_confirmed": True,
            "all_submitted_code_reviewed_and_explainable": True,
            "source_and_dependency_licenses_reviewed": True,
            "final_pdf_visual_qa_completed": True,
            "final_video_watchthrough_completed": True,
            "public_repository_maintenance_obligation_accepted": True,
        },
        "duplicate_benefit_confirmation": {
            "status": "not_applicable",
            "sha256": None,
        },
    }


class ManifestTest(unittest.TestCase):
    def test_default_builder_python_uses_canonical_current_interpreter(self) -> None:
        argv = [
            "package_submission.py",
            "--manifest",
            "m",
            "--template",
            "t",
            "--content",
            "c",
            "--report-pdf",
            "p",
            "--video-file",
            "v",
            "--release-evidence-dir",
            "e",
            "--release-evidence-artifact",
            "a",
            "--output",
            "o",
        ]
        with patch.object(sys, "argv", argv):
            args = package_submission.parse_args()

        self.assertEqual(Path(sys.executable).resolve(), args.builder_python)

    def test_accepts_complete_manifest(self) -> None:
        checked = package_submission.validate_manifest(valid_manifest())
        self.assertEqual("example-owner", checked["github_owner"])

    def test_rejects_placeholder_before_packaging(self) -> None:
        manifest = valid_manifest()
        manifest["project"]["repository_url"] = "[[PUBLIC_REPOSITORY_URL]]"
        with self.assertRaisesRegex(package_submission.GateError, "unresolved"):
            package_submission.validate_manifest(manifest)

    def test_rejects_packaging_at_or_after_official_deadline(self) -> None:
        at_deadline = datetime(2026, 8, 27, 9, 0, 0, tzinfo=timezone.utc)
        with self.assertRaisesRegex(package_submission.GateError, "deadline has passed"):
            package_submission.validate_submission_deadline(at_deadline)

    def test_rejects_video_over_three_minutes(self) -> None:
        manifest = valid_manifest()
        manifest["video"]["duration_seconds"] = 180.001
        with self.assertRaisesRegex(package_submission.GateError, "at most 180"):
            package_submission.validate_manifest(manifest)

    def test_rejects_release_candidate_tag_for_final_package(self) -> None:
        manifest = valid_manifest()
        manifest["project"]["tag"] = "v0.1.0-rc1"
        manifest["project"]["release_url"] += "-rc1"
        manifest["release_evidence"]["source_archive_filename"] = (
            "routecontract-0.1.0-rc1-source.zip"
        )
        with self.assertRaisesRegex(package_submission.GateError, "stable"):
            package_submission.validate_manifest(manifest)

    def test_rejects_inapplicable_duplicate_form_checksum(self) -> None:
        manifest = valid_manifest()
        manifest["duplicate_benefit_confirmation"]["sha256"] = digest("8")
        with self.assertRaisesRegex(package_submission.GateError, "must be null"):
            package_submission.validate_manifest(manifest)

    def test_rejects_unreviewed_participant_attestation(self) -> None:
        manifest = valid_manifest()
        manifest["participant_attestations"]["single_entry_per_participant_confirmed"] = False
        with self.assertRaisesRegex(package_submission.GateError, "attestations"):
            package_submission.validate_manifest(manifest)

    def test_rejects_unimplemented_release_signature_claim(self) -> None:
        manifest = valid_manifest()
        manifest["release_evidence"]["signature_filenames"] = [
            "routecontract-shardingsphere-5.5-0.1.0.jar.asc"
        ]
        with self.assertRaisesRegex(package_submission.GateError, "must be empty"):
            package_submission.validate_manifest(manifest)


class ReportContractTest(unittest.TestCase):
    BASE = (
        "2026년 오픈소스 개발자대회 결과보고서 "
        "개발 보조 AI OpenAI ChatGPT 및 Codex "
        "제품에는 AI 모델·학습/추론 코드·외부 AI API 호출이 없다 "
        "붙임1 SBOM(소프트웨어 자재명세서)"
    )

    def test_accepts_sbom_and_development_ai_without_attachment_2(self) -> None:
        package_submission.validate_report_text_contract(self.BASE, self.BASE)

    def test_rejects_runtime_ai_attachment(self) -> None:
        text = self.BASE + " AI 모델 활용 및 라이선스 기술 명세서"
        with self.assertRaisesRegex(package_submission.GateError, "Attachment 2"):
            package_submission.validate_report_text_contract(text, text)

    def test_rejects_missing_sbom(self) -> None:
        text = self.BASE.replace("SBOM(소프트웨어 자재명세서)", "")
        with self.assertRaisesRegex(package_submission.GateError, "SBOM"):
            package_submission.validate_report_text_contract(text, text)

    def test_rejects_body_over_five_pages(self) -> None:
        pages = ["body"] * 6 + ["붙임1 SBOM(소프트웨어 자재명세서)"]
        with self.assertRaisesRegex(package_submission.GateError, "maximum is 5"):
            package_submission.report_page_contract(pages)


class PrivacyAndPathTest(unittest.TestCase):
    PDF_INFO = """Author: RouteContract project
Creator: Writer
Producer: LibreOffice 26.2
Custom Metadata: no
UserProperties: no
Suspects: no
Form: none
JavaScript: no
Encrypted: no
Pages: 5
"""
    XMP = """<?xml version="1.0"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:RDF><rdf:Description><dc:creator><rdf:Seq><rdf:li>RouteContract project</rdf:li></rdf:Seq></dc:creator></rdf:Description></rdf:RDF>
</x:xmpmeta>"""

    def pdf_run(self, command: list[str]) -> str:
        if command[0].endswith("pdfdetach"):
            return "0 embedded files\n"
        if "-meta" in command:
            return self.XMP
        if "-js" in command:
            return ""
        return self.PDF_INFO

    def test_accepts_sanitized_pdf_without_attachments_or_javascript(self) -> None:
        with patch.object(package_submission.shutil, "which", side_effect=lambda name: f"/bin/{name}"), patch.object(
            package_submission, "run", side_effect=self.pdf_run
        ):
            package_submission.validate_pdf_privacy(Path("/tmp/report.pdf"))

    def test_rejects_private_path_in_pdf_metadata(self) -> None:
        def leaked_run(command: list[str]) -> str:
            value = self.pdf_run(command)
            if len(command) == 2 and command[0].endswith("pdfinfo"):
                return value + "Subject: /Users/person/private/report.docx\n"
            return value

        with patch.object(package_submission.shutil, "which", side_effect=lambda name: f"/bin/{name}"), patch.object(
            package_submission, "run", side_effect=leaked_run
        ):
            with self.assertRaisesRegex(package_submission.GateError, "private path"):
                package_submission.validate_pdf_privacy(Path("/tmp/report.pdf"))

    def test_rejects_symlink_in_input_path(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "target.txt"
            target.write_text("value", encoding="utf-8")
            link = root / "link.txt"
            link.symlink_to(target)
            with self.assertRaisesRegex(package_submission.GateError, "symlink"):
                package_submission.require_file(link, "fixture")

    def test_rejects_corrupt_docx_as_gate_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "corrupt.docx"
            path.write_bytes(b"not-a-zip")
            for validator in (
                package_submission.extract_docx_text,
                package_submission.validate_docx_privacy,
            ):
                with self.subTest(validator=validator.__name__), self.assertRaises(
                    package_submission.GateError
                ):
                    validator(path)

    def test_requires_repository_output_to_be_gitignored(self) -> None:
        repository = SCRIPT.parents[2]
        package_submission.assert_ignored_if_inside_repository(
            repository / "submission" / "package" / "final",
            repository,
            "ignored output",
        )
        with self.assertRaisesRegex(package_submission.GateError, "not gitignored"):
            package_submission.assert_ignored_if_inside_repository(
                repository / "unexpected-final-output",
                repository,
                "public output",
            )

    def test_invalid_manifest_does_not_create_output_parent(self) -> None:
        repository = SCRIPT.parents[2]
        manifest = repository / "submission" / "package-manifest.example.json"
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            missing_parent = root / "not-created"
            argv = [
                "package_submission.py",
                "--manifest",
                str(manifest),
                "--template",
                str(SCRIPT),
                "--content",
                str(SCRIPT),
                "--report-pdf",
                str(SCRIPT),
                "--video-file",
                str(SCRIPT),
                "--release-evidence-dir",
                str(root),
                "--release-evidence-artifact",
                str(SCRIPT),
                "--output",
                str(missing_parent / "final"),
                "--repository-root",
                str(repository),
            ]
            with patch.object(sys, "argv", argv), self.assertRaisesRegex(
                package_submission.GateError, "unresolved"
            ):
                package_submission.main()

            self.assertFalse(missing_parent.exists())


class ZipAllowlistTest(unittest.TestCase):
    def test_default_zip_has_exactly_two_deterministic_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            upload = root / "upload"
            upload.mkdir()
            names = [
                package_submission.REPORT_DOCX_NAME,
                package_submission.REPORT_PDF_NAME,
            ]
            (upload / names[0]).write_bytes(b"docx")
            (upload / names[1]).write_bytes(b"pdf")
            first = root / "first.zip"
            second = root / "second.zip"
            package_submission.build_upload_zip(upload, first, names)
            package_submission.build_upload_zip(upload, second, names)
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())
            with ZipFile(first) as archive:
                self.assertEqual(names, archive.namelist())
                self.assertFalse(any(name.endswith((".json", ".xml", ".mp4", ".jar")) for name in archive.namelist()))


class ChecksumManifestTest(unittest.TestCase):
    def test_accepts_flat_sha256sum_output(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "SHA256SUMS"
            path.write_text(f"{digest('8')}  artifact.jar\n", encoding="utf-8")
            self.assertEqual(
                {"artifact.jar": digest("8")},
                package_submission.parse_checksum_manifest(path),
            )

    def test_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "SHA256SUMS"
            path.write_text(f"{digest('9')}  ../secret\n", encoding="utf-8")
            with self.assertRaisesRegex(package_submission.GateError, "invalid"):
                package_submission.parse_checksum_manifest(path)


class SourceArchiveTest(unittest.TestCase):
    REQUIRED = ("README.md", "LICENSE", "NOTICE", "build.gradle", "gradlew")

    def write_archive(self, path: Path, extra: tuple[str, ...] = ()) -> None:
        with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
            for name in (*self.REQUIRED, *extra):
                archive.writestr(f"routecontract-0.1.0/{name}", name)

    def test_accepts_single_root_release_archive(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "source.zip"
            self.write_archive(path)
            self.assertEqual(
                "routecontract-0.1.0",
                package_submission.validate_source_archive(path, "routecontract-0.1.0"),
            )

    def test_rejects_corrupt_source_archive_as_gate_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "corrupt-source.zip"
            path.write_bytes(b"not-a-zip")
            with self.assertRaises(package_submission.GateError):
                package_submission.source_archive_members(path, "routecontract-0.1.0")

    def test_rejects_private_submission_material(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "source.zip"
            self.write_archive(path, ("submission/private/final.json",))
            with self.assertRaisesRegex(package_submission.GateError, "leaked"):
                package_submission.validate_source_archive(path, "routecontract-0.1.0")

    def test_matches_final_git_tree_and_rejects_changed_content(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repository = Path(raw) / "repository"
            repository.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            for name in self.REQUIRED:
                path = repository / name
                path.write_text(name, encoding="utf-8")
            os.chmod(repository / "gradlew", 0o755)
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=RouteContract test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-q",
                    "-m",
                    "fixture",
                ],
                cwd=repository,
                check=True,
            )
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            source = Path(raw) / "source.zip"
            subprocess.run(
                [
                    "git",
                    "archive",
                    "--format=zip",
                    "--prefix=routecontract-0.1.0/",
                    f"--output={source}",
                    commit,
                ],
                cwd=repository,
                check=True,
            )
            package_submission.validate_source_archive_identity(
                source, repository, commit, "routecontract-0.1.0"
            )

            changed = Path(raw) / "changed.zip"
            with ZipFile(source) as original, ZipFile(changed, "w") as rewritten:
                for info in original.infolist():
                    data = original.read(info.filename)
                    if info.filename.endswith("README.md"):
                        data = b"changed"
                    rewritten.writestr(info, data)
            with self.assertRaisesRegex(package_submission.GateError, "not content-identical"):
                package_submission.validate_source_archive_identity(
                    changed, repository, commit, "routecontract-0.1.0"
                )


class ReleaseEvidenceTest(unittest.TestCase):
    PRIVATE_EVIDENCE_NAMES = {
        "environment.txt",
        "mysql-image.txt",
        "standalone-consumer.txt",
    }

    def write_public_checksums(self, root: Path) -> None:
        checksum_lines = [
            f"{package_submission.sha256(path)}  {path.name}"
            for path in sorted(root.iterdir())
            if path.name != "SHA256SUMS"
            and path.name not in self.PRIVATE_EVIDENCE_NAMES
        ]
        (root / "SHA256SUMS").write_text(
            "\n".join(checksum_lines) + "\n", encoding="utf-8"
        )

    def rebuild_artifact(self, root: Path, artifact: Path, manifest: dict) -> None:
        with ZipFile(artifact, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(root.iterdir()):
                archive.write(path, path.name)
        manifest["release_evidence"]["workflow_artifact_sha256"] = (
            package_submission.sha256(artifact)
        )

    def build_evidence(self, root: Path, manifest: dict) -> Path:
        source_name = "routecontract-0.1.0-source.zip"
        with ZipFile(root / source_name, "w", compression=ZIP_DEFLATED) as archive:
            for name in ("README.md", "LICENSE", "NOTICE", "build.gradle", "gradlew"):
                archive.writestr(f"routecontract-0.1.0/{name}", name)
        files = {
            "environment.txt": f"revision={manifest['project']['commit']}\n",
            "mysql-image.txt": "image_id=sha256:test\n",
            "standalone-consumer.txt": (
                "ROUTECONTRACT_RELEASE_ASSET_CONSUMER "
                "coordinate=io.github.example-owner.routecontract:"
                "routecontract-shardingsphere-5.5:0.1.0 result=VERIFIED_MYSQL\n"
            ),
            "test-summary.txt": valid_test_summary(manifest["project"]["commit"]),
            "routecontract-shardingsphere-5.5.pom": (
                "<project><groupId>io.github.example-owner.routecontract</groupId>"
                "<artifactId>routecontract-shardingsphere-5.5</artifactId>"
                "<version>0.1.0</version></project>\n"
            ),
            "routecontract-shardingsphere-5.5-cyclonedx.json": "{}\n",
            "routecontract-shardingsphere-5.5-cyclonedx.xml": "<bom/>\n",
            "routecontract-aggregate-cyclonedx.json": "{}\n",
            "routecontract-aggregate-cyclonedx.xml": "<bom/>\n",
            "routecontract-shardingsphere-5.5-0.1.0.jar": "main\n",
            "routecontract-shardingsphere-5.5-0.1.0-sources.jar": "sources\n",
            "routecontract-shardingsphere-5.5-0.1.0-javadoc.jar": "javadoc\n",
        }
        for name, content in files.items():
            (root / name).write_text(content, encoding="utf-8")
        source_hash = package_submission.sha256(root / source_name)
        json_hash = package_submission.sha256(root / "routecontract-aggregate-cyclonedx.json")
        xml_hash = package_submission.sha256(root / "routecontract-aggregate-cyclonedx.xml")
        manifest["release_evidence"].update(
            {
                "source_archive_sha256": source_hash,
                "aggregate_sbom_json_sha256": json_hash,
                "aggregate_sbom_xml_sha256": xml_hash,
            }
        )
        self.write_public_checksums(root)
        artifact = root.parent / "release-evidence.zip"
        self.rebuild_artifact(root, artifact, manifest)
        return artifact

    def test_rejects_corrupt_workflow_artifact_as_gate_error(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "corrupt-artifact.zip"
            path.write_bytes(b"not-a-zip")
            with self.assertRaises(package_submission.GateError):
                package_submission.zip_flat_file_metadata(path, "workflow artifact ZIP")

    def test_accepts_complete_checksummed_release_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            checked = package_submission.validate_manifest(manifest)
            with patch.object(package_submission, "run", return_value=""), patch.object(
                package_submission, "validate_source_archive_identity", return_value=None
            ):
                result = package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )
            self.assertEqual(13, result["release_evidence_file_count"])
            self.assertEqual(50, result["test_summary"]["test_count"])
            self.assertIn("SHA256SUMS", result["public_release_assets"])
            self.assertIn("test-summary.txt", result["public_release_assets"])
            self.assertNotIn("environment.txt", result["public_release_assets"])

    def test_rejects_test_summary_for_another_revision(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            (root / "test-summary.txt").write_text(
                valid_test_summary("2" * 40), encoding="utf-8"
            )
            self.write_public_checksums(root)
            self.rebuild_artifact(root, artifact, manifest)
            checked = package_submission.validate_manifest(manifest)
            with self.assertRaisesRegex(package_submission.GateError, "7-suite/50-test"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_file_not_covered_by_sha256sums(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            (root / "unexpected.txt").write_text("not checksummed", encoding="utf-8")
            checked = package_submission.validate_manifest(manifest)
            with self.assertRaisesRegex(package_submission.GateError, "byte-identical|unlisted"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_unexpected_file_even_when_artifact_and_checksums_match(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            (root / "private.log").write_text("unexpected", encoding="utf-8")
            self.rebuild_artifact(root, artifact, manifest)
            checked = package_submission.validate_manifest(manifest)
            with self.assertRaisesRegex(package_submission.GateError, "exact allowlist"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_workflow_only_log_in_public_sha256sums(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            checksum_path = root / "SHA256SUMS"
            checksum_path.write_text(
                checksum_path.read_text(encoding="utf-8")
                + f"{package_submission.sha256(root / 'environment.txt')}  environment.txt\n",
                encoding="utf-8",
            )
            self.rebuild_artifact(root, artifact, manifest)
            checked = package_submission.validate_manifest(manifest)
            with self.assertRaisesRegex(package_submission.GateError, "public SHA256SUMS"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_missing_public_checksum_entry(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            checksum_path = root / "SHA256SUMS"
            lines = checksum_path.read_text(encoding="utf-8").splitlines()
            checksum_path.write_text(
                "\n".join(
                    line for line in lines if not line.endswith("  test-summary.txt")
                )
                + "\n",
                encoding="utf-8",
            )
            self.rebuild_artifact(root, artifact, manifest)
            checked = package_submission.validate_manifest(manifest)
            with self.assertRaisesRegex(package_submission.GateError, "public SHA256SUMS"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_tampered_public_payload(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            (root / "routecontract-shardingsphere-5.5-0.1.0.jar").write_text(
                "tampered\n", encoding="utf-8"
            )
            self.rebuild_artifact(root, artifact, manifest)
            checked = package_submission.validate_manifest(manifest)
            with self.assertRaisesRegex(package_submission.GateError, "checksum mismatch"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_legacy_source_published_consumer_marker(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            (root / "standalone-consumer.txt").write_text(
                "ROUTECONTRACT_STANDALONE artifact=published-jar\n",
                encoding="utf-8",
            )
            self.rebuild_artifact(root, artifact, manifest)
            checked = package_submission.validate_manifest(manifest)
            with self.assertRaisesRegex(package_submission.GateError, "final-asset"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_duplicate_final_asset_consumer_marker(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            standalone = root / "standalone-consumer.txt"
            marker = standalone.read_text(encoding="utf-8")
            standalone.write_text(marker + marker, encoding="utf-8")
            self.rebuild_artifact(root, artifact, manifest)
            checked = package_submission.validate_manifest(manifest)
            with self.assertRaisesRegex(package_submission.GateError, "marker once"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )


class PublicEvidenceTest(unittest.TestCase):
    def test_youtube_probe_ignores_local_config_and_playlists(self) -> None:
        url = "https://www.youtube.com/watch?v=abcdefghijk"
        commands: list[list[str]] = []

        def fake_run(command: list[str]) -> str:
            commands.append(command)
            return json.dumps({"id": "abcdefghijk", "duration": 179})

        with patch.object(
            package_submission,
            "request_json",
            return_value={"title": "RouteContract demo"},
        ), patch.object(
            package_submission.shutil, "which", return_value="/usr/local/bin/yt-dlp"
        ), patch.object(package_submission, "run", side_effect=fake_run):
            result = package_submission.public_youtube_metadata(url)

        self.assertEqual(179.0, result["duration_seconds"])
        self.assertEqual(
            [
                "/usr/local/bin/yt-dlp",
                "--ignore-config",
                "--no-playlist",
                "--dump-single-json",
                "--skip-download",
                "--",
                url,
            ],
            commands[0],
        )

    def test_accepts_matching_public_revision_release_and_video(self) -> None:
        manifest = package_submission.validate_manifest(valid_manifest())
        project = manifest["project"]
        evidence = {
            "source_archive_filename": "routecontract-0.1.0-source.zip",
            "source_archive_sha256": digest("5"),
            "source_archive_size": 123,
            "public_release_assets": {
                "routecontract-0.1.0-source.zip": {"sha256": digest("5"), "size": 123}
            },
        }

        def fake_json(url: str) -> dict:
            if "/actions/runs/" in url:
                return {
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": project["commit"],
                    "name": "Release evidence",
                    "repository": {"full_name": "example-owner/routecontract"},
                }
            if "/actions/artifacts/" in url:
                return {
                    "id": 987654,
                    "name": f"routecontract-release-evidence-{project['commit']}",
                    "expired": False,
                    "digest": f"sha256:{digest('a')}",
                    "workflow_run": {"id": 123456, "head_sha": project["commit"]},
                }
            if "/releases/tags/" in url:
                return {
                    "id": 7,
                    "draft": False,
                    "prerelease": False,
                    "tag_name": project["tag"],
                    "html_url": project["release_url"],
                    "assets": [
                        {
                            "name": evidence["source_archive_filename"],
                            "size": 123,
                            "digest": f"sha256:{digest('5')}",
                        }
                    ],
                }
            if "/commits/" in url:
                return {"sha": project["commit"]}
            return {
                "private": False,
                "archived": False,
                "full_name": "example-owner/routecontract",
            }

        youtube = {
            "id": "abcdefghijk",
            "title": "RouteContract demo",
            "duration_seconds": 179.0,
        }
        with patch.object(package_submission, "request_json", side_effect=fake_json), patch.object(
            package_submission, "public_youtube_metadata", return_value=youtube
        ):
            result = package_submission.validate_public_evidence(
                manifest, {"duration_seconds": 179.5}, evidence
            )
        self.assertEqual("success", result["ci_conclusion"])
        self.assertEqual("v0.1.0", result["release_tag"])

    def test_rejects_release_run_for_different_commit(self) -> None:
        manifest = package_submission.validate_manifest(valid_manifest())
        evidence = {
            "source_archive_filename": "routecontract-0.1.0-source.zip",
            "source_archive_sha256": digest("5"),
            "source_archive_size": 123,
            "public_release_assets": {
                "routecontract-0.1.0-source.zip": {"sha256": digest("5"), "size": 123}
            },
        }

        def fake_json(url: str) -> dict:
            if "/actions/runs/" in url:
                return {
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": "0" * 40,
                    "name": "Release evidence",
                    "repository": {"full_name": "example-owner/routecontract"},
                }
            if "/commits/" in url:
                return {"sha": manifest["project"]["commit"]}
            return {
                "private": False,
                "archived": False,
                "full_name": "example-owner/routecontract",
            }

        with patch.object(package_submission, "request_json", side_effect=fake_json):
            with self.assertRaisesRegex(package_submission.GateError, "not green"):
                package_submission.validate_public_evidence(
                    manifest, {"duration_seconds": 179.5}, evidence
                )


if __name__ == "__main__":
    unittest.main()
