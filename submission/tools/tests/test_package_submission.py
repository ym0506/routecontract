from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile


SCRIPT = Path(__file__).resolve().parents[1] / "package_submission.py"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
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
        "submission_identity": {
            "receipt_number": "123",
            "team_name": "홍길동전",
            "registered_project_name": "RouteContract",
            "team_size": "1명",
            "division": "학생",
            "task_type": "자유과제",
        },
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


def valid_ffprobe_video() -> dict:
    return {
        "format": {
            "duration": "179.500000",
            "tags": {
                "encoder": "Lavf test fixture",
            },
        },
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "disposition": {
                    "default": 1,
                    "attached_pic": 0,
                    "still_image": 0,
                },
                "tags": {
                    "language": "und",
                    "handler_name": "VideoHandler",
                },
            },
            {
                "index": 1,
                "codec_type": "audio",
                "tags": {
                    "language": "kor",
                    "handler_name": "SoundHandler",
                },
            },
        ],
    }


def valid_youtube_probe() -> dict:
    return {
        "id": "abcdefghijk",
        "duration": 179,
        "availability": "public",
        "live_status": "not_live",
        "age_limit": 0,
        "formats": [
            {
                "format_id": "140",
                "height": None,
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "url": "https://example.invalid/audio",
            },
            {
                "format_id": "137",
                "height": 1080,
                "vcodec": "avc1.640028",
                "acodec": "none",
                "url": "https://example.invalid/video",
                "has_drm": False,
            },
        ],
    }


class SubmissionClaimTextTest(unittest.TestCase):
    def test_video_delivery_docs_separate_machine_and_owner_qc(self) -> None:
        readme = (REPOSITORY_ROOT / "submission" / "README.md").read_text(
            encoding="utf-8"
        )
        storyboard = (
            REPOSITORY_ROOT / "submission" / "video-storyboard.md"
        ).read_text(encoding="utf-8")

        for required in (
            "at least 1920x1080",
            "at least one audio stream",
            "public, non-live, age-unrestricted",
            "downloadable 1080p",
            "checks all reported formats",
            "does not grade narration",
            "loudness, clipping, or visual readability",
            "owner must still watch and listen",
            "download the entire public video",
        ):
            self.assertIn(required, readme)
        for required in (
            "1920×1080 이상",
            "audio stream이 1개 이상",
            "공개·non-live·연령 제한 없음",
            "1080p 이상 format",
            "음량·clipping·내레이션 진실성·화면 가독성",
        ):
            self.assertIn(required, storyboard)

    def test_storyboard_supports_qualified_and_zero_external_result_branches(
        self,
    ) -> None:
        storyboard = (
            REPOSITORY_ROOT / "submission" / "video-storyboard.md"
        ).read_text(encoding="utf-8")

        for required in (
            "**qualified-result 분기:**",
            "Issue #9의 모든 acceptance criteria",
            "사람 비작성자·비협업자",
            "정확히 활성화된 immutable RC",
            "first outcomes 전 비공개 설정 도움 없음",
            "원본 first-outcome dedicated independent-install Issue",
            "adoption·실사용 증거로 부르지 않는다.",
            "**0-result 분기:**",
            "Issue #9의 activation/protocol",
            "qualified non-author first outcomes: 0",
            "independent external validation not obtained before cutoff",
            "게시하지 않았다면 카드와 내레이션에서 제외",
            "0건이어서 외부 검증 미확보를 그대로 표시했습니다.",
        ):
            self.assertIn(required, storyboard)

        for unconditional_claim in (
            "비작성자가 직접 남긴 첫 quick-start 결과 Issue",
            "최종 revision의 CI와 checksummed Release, 비작성자의 첫 설치 "
            "결과, upstream 질문을 모두 공개 링크로 남겼습니다.",
            "- [ ] 실제 비작성자의 첫 quick-start 결과가 본인 계정으로 "
            "공개되어 있다.",
        ):
            self.assertNotIn(unconditional_claim, storyboard)

    def test_report_roadmap_does_not_promise_external_result(self) -> None:
        report = json.loads(
            (REPOSITORY_ROOT / "submission" / "report-content.ko.json").read_text(
                encoding="utf-8"
            )
        )
        roadmap = next(
            item["text"] for item in report["other"] if item["lead"] == "로드맵"
        )

        self.assertIn("Issue #9 기준을 충족한 비작성자 독립 설치 결과", roadmap)
        self.assertIn("확보된 경우만 기록", roadmap)
        self.assertIn("qualified 결과가 0건이면 외부 검증 미확보", roadmap)
        self.assertNotIn("외부 설치 기록·license/security 재검토를 완료", roadmap)


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

    def test_accepts_standard_venv_final_python_symlink(self) -> None:
        with tempfile.TemporaryDirectory(dir=SCRIPT.parents[2]) as raw:
            root = Path(raw)
            target = root / "python-target"
            target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            target.chmod(0o755)
            venv = root / "venv"
            (venv / "bin").mkdir(parents=True)
            interpreter = venv / "bin" / "python"
            interpreter.symlink_to(target)

            self.assertEqual(
                interpreter,
                package_submission.require_python_interpreter(
                    interpreter, "report builder Python"
                ),
            )

    def test_rejects_symlink_in_builder_python_parent_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=SCRIPT.parents[2]) as raw:
            root = Path(raw)
            real = root / "real"
            real.mkdir()
            interpreter = real / "python"
            interpreter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            interpreter.chmod(0o755)
            linked_parent = root / "linked"
            linked_parent.symlink_to(real, target_is_directory=True)

            with self.assertRaisesRegex(package_submission.GateError, "symlink component"):
                package_submission.require_python_interpreter(
                    linked_parent / "python", "report builder Python"
                )

    def test_accepts_complete_manifest(self) -> None:
        checked = package_submission.validate_manifest(valid_manifest())
        self.assertEqual("example-owner", checked["github_owner"])
        basename = "2026 오픈소스 개발자대회 결과보고서_123(홍길동전)"
        self.assertEqual(
            {
                "basename": basename,
                "docx": f"{basename}.docx",
                "pdf": f"{basename}.pdf",
                "zip": f"{basename}.zip",
            },
            checked["official_submission_filenames"],
        )

    def test_rejects_non_nfc_submission_identity(self) -> None:
        manifest = valid_manifest()
        manifest["submission_identity"]["team_name"] = unicodedata.normalize(
            "NFD", "홍길동전"
        )
        with self.assertRaisesRegex(package_submission.GateError, "NFC"):
            package_submission.validate_manifest(manifest)

    def test_rejects_unsafe_submission_identity_components(self) -> None:
        for unsafe in ("../123", "123/456", "123\\456", "123\n456", " 123"):
            with self.subTest(unsafe=repr(unsafe)):
                manifest = valid_manifest()
                manifest["submission_identity"]["receipt_number"] = unsafe
                with self.assertRaises(package_submission.GateError):
                    package_submission.validate_manifest(manifest)

    def test_rejects_official_filename_over_portable_byte_limit(self) -> None:
        manifest = valid_manifest()
        manifest["submission_identity"]["team_name"] = "가" * 80
        with self.assertRaisesRegex(package_submission.GateError, "255 UTF-8 bytes"):
            package_submission.validate_manifest(manifest)

    def test_requires_exact_report_registration_identity_match(self) -> None:
        manifest = package_submission.validate_manifest(valid_manifest())
        metadata = {
            "team_name": "홍길동전",
            "project_name": "RouteContract",
            "team_size": "1명",
            "division": "학생",
            "task_type": "자유과제",
        }
        package_submission.validate_submission_identity_matches_content(
            {"metadata": metadata}, manifest
        )
        for key in metadata:
            with self.subTest(key=key), self.assertRaisesRegex(
                package_submission.GateError, "exactly match"
            ):
                changed = dict(metadata)
                changed[key] += "-mismatch"
                package_submission.validate_submission_identity_matches_content(
                    {"metadata": changed}, manifest
                )

    def test_rejects_control_character_in_registration_identity(self) -> None:
        manifest = valid_manifest()
        manifest["submission_identity"]["registered_project_name"] = "Route\u200bContract"
        with self.assertRaisesRegex(package_submission.GateError, "control or formatting"):
            package_submission.validate_manifest(manifest)

    def test_rejects_required_duplicate_form_until_official_source_is_validated(self) -> None:
        manifest = valid_manifest()
        manifest["duplicate_benefit_confirmation"] = {
            "status": "required",
            "sha256": digest("8"),
        }
        with self.assertRaisesRegex(package_submission.GateError, "exact source form"):
            package_submission.validate_manifest(manifest)
        with self.assertRaisesRegex(package_submission.GateError, "exact source form"):
            package_submission.validate_duplicate_confirmation(Path("arbitrary.pdf"), manifest)

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


class LocalVideoEvidenceTest(unittest.TestCase):
    VIDEO = Path("/private/final-video.mp4")

    def probe(self, payload: object) -> dict:
        with patch.object(
            package_submission.shutil,
            "which",
            side_effect=lambda name: "/usr/local/bin/ffprobe"
            if name == "ffprobe"
            else None,
        ), patch.object(
            package_submission,
            "run",
            return_value=json.dumps(payload),
        ) as run:
            result = package_submission.local_video_metadata(self.VIDEO)

        run.assert_called_once_with(
            [
                "/usr/local/bin/ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:format_tags:stream=index,codec_type,width,height:stream_tags:stream_disposition=default,attached_pic,still_image:chapter=id:chapter_tags:program=id:program_tags",
                "-of",
                "json",
                str(self.VIDEO),
            ]
        )
        return result

    def test_accepts_1080p_audio_and_normal_container_tags(self) -> None:
        result = self.probe(valid_ffprobe_video())

        self.assertEqual(179.5, result["duration_seconds"])
        self.assertEqual(1920, result["width"])
        self.assertEqual(1080, result["height"])
        self.assertEqual(1, result["video_stream_count"])
        self.assertEqual(1, result["audio_stream_count"])
        self.assertEqual("ffprobe", result["probe"])

    def test_accepts_larger_video_and_multiple_audio_streams(self) -> None:
        payload = valid_ffprobe_video()
        payload["streams"][0]["width"] = 3840
        payload["streams"][0]["height"] = 2160
        payload["streams"].append(
            {
                "index": 2,
                "codec_type": "audio",
                "tags": {"language": "eng", "handler_name": "SoundHandler"},
            }
        )

        result = self.probe(payload)

        self.assertEqual(3840, result["width"])
        self.assertEqual(2160, result["height"])
        self.assertEqual(2, result["audio_stream_count"])

    def test_uses_default_motion_video_instead_of_larger_alternate(self) -> None:
        payload = valid_ffprobe_video()
        alternate = dict(payload["streams"][0])
        alternate["index"] = 2
        alternate["width"] = 3840
        alternate["height"] = 2160
        alternate["disposition"] = dict(
            payload["streams"][0]["disposition"], default=0
        )
        payload["streams"].append(alternate)

        result = self.probe(payload)

        self.assertEqual(1920, result["width"])
        self.assertEqual(1080, result["height"])
        self.assertEqual(0, result["selected_video_stream_index"])
        self.assertTrue(result["selected_video_is_default"])

    def test_rejects_720p_default_even_with_4k_nondefault_alternate(self) -> None:
        payload = valid_ffprobe_video()
        payload["streams"][0]["width"] = 1280
        payload["streams"][0]["height"] = 720
        alternate = dict(payload["streams"][0])
        alternate["index"] = 2
        alternate["width"] = 3840
        alternate["height"] = 2160
        alternate["disposition"] = dict(
            payload["streams"][0]["disposition"], default=0
        )
        payload["streams"].append(alternate)

        with self.assertRaisesRegex(package_submission.GateError, "got 1280x720"):
            self.probe(payload)

    def test_rejects_cover_art_or_still_image_as_resolution_evidence(self) -> None:
        for excluded_disposition in ("attached_pic", "still_image"):
            payload = valid_ffprobe_video()
            payload["streams"][0]["width"] = 1280
            payload["streams"][0]["height"] = 720
            cover = dict(payload["streams"][0])
            cover["index"] = 2
            cover["width"] = 1920
            cover["height"] = 1080
            cover["disposition"] = {
                "default": 0,
                "attached_pic": 0,
                "still_image": 0,
                excluded_disposition: 1,
            }
            payload["streams"].append(cover)

            with self.subTest(disposition=excluded_disposition), self.assertRaisesRegex(
                package_submission.GateError, "got 1280x720"
            ):
                self.probe(payload)

    def test_without_default_uses_first_motion_stream_not_larger_secondary(self) -> None:
        payload = valid_ffprobe_video()
        payload["streams"][0]["width"] = 1280
        payload["streams"][0]["height"] = 720
        payload["streams"][0]["disposition"]["default"] = 0
        secondary = dict(payload["streams"][0])
        secondary["index"] = 2
        secondary["width"] = 3840
        secondary["height"] = 2160
        secondary["disposition"] = dict(
            payload["streams"][0]["disposition"]
        )
        payload["streams"].append(secondary)

        with self.assertRaisesRegex(package_submission.GateError, "got 1280x720"):
            self.probe(payload)

    def test_rejects_multiple_default_motion_video_streams(self) -> None:
        payload = valid_ffprobe_video()
        secondary = dict(payload["streams"][0])
        secondary["index"] = 2
        secondary["disposition"] = dict(
            payload["streams"][0]["disposition"], default=1
        )
        payload["streams"].append(secondary)

        with self.assertRaisesRegex(package_submission.GateError, "multiple default"):
            self.probe(payload)

    def test_rejects_missing_or_duplicate_motion_video_stream_index(self) -> None:
        payload = valid_ffprobe_video()
        del payload["streams"][0]["index"]
        with self.assertRaisesRegex(package_submission.GateError, "stream indexes"):
            self.probe(payload)

        payload = valid_ffprobe_video()
        secondary = dict(payload["streams"][0])
        secondary["disposition"] = dict(
            payload["streams"][0]["disposition"], default=0
        )
        payload["streams"].append(secondary)
        with self.assertRaisesRegex(package_submission.GateError, "stream indexes"):
            self.probe(payload)

    def test_rejects_only_cover_art_or_still_image_video(self) -> None:
        for excluded_disposition in ("attached_pic", "still_image"):
            payload = valid_ffprobe_video()
            payload["streams"][0]["disposition"][excluded_disposition] = 1
            with self.subTest(disposition=excluded_disposition), self.assertRaisesRegex(
                package_submission.GateError, "no playable motion video stream"
            ):
                self.probe(payload)

    def test_rejects_missing_or_malformed_video_disposition(self) -> None:
        for disposition in (None, {}, {"default": False, "attached_pic": 0, "still_image": 0}):
            payload = valid_ffprobe_video()
            if disposition is None:
                del payload["streams"][0]["disposition"]
            else:
                payload["streams"][0]["disposition"] = disposition
            with self.subTest(disposition=disposition), self.assertRaisesRegex(
                package_submission.GateError, "video stream disposition"
            ):
                self.probe(payload)

    def test_requires_ffprobe_instead_of_incomplete_mdls_fallback(self) -> None:
        with patch.object(package_submission.shutil, "which", return_value=None):
            with self.assertRaisesRegex(package_submission.GateError, "ffprobe is required"):
                package_submission.local_video_metadata(self.VIDEO)

    def test_rejects_invalid_or_incomplete_ffprobe_output(self) -> None:
        invalid_payloads = (
            "not-an-object",
            {},
            {"format": {}, "streams": []},
            {"format": {"duration": "NaN"}, "streams": []},
            {"format": {"duration": "179"}, "streams": "not-a-list"},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaisesRegex(
                package_submission.GateError, "ffprobe returned incomplete video metadata"
            ):
                self.probe(payload)

    def test_rejects_missing_audio_stream(self) -> None:
        payload = valid_ffprobe_video()
        payload["streams"] = [payload["streams"][0]]

        with self.assertRaisesRegex(package_submission.GateError, "audio stream"):
            self.probe(payload)

    def test_rejects_missing_video_stream(self) -> None:
        payload = valid_ffprobe_video()
        payload["streams"] = [payload["streams"][1]]

        with self.assertRaisesRegex(package_submission.GateError, "no video stream"):
            self.probe(payload)

    def test_rejects_video_below_1920_by_1080(self) -> None:
        for width, height in ((1919, 1080), (1920, 1079), (1280, 720)):
            payload = valid_ffprobe_video()
            payload["streams"][0]["width"] = width
            payload["streams"][0]["height"] = height
            with self.subTest(width=width, height=height), self.assertRaisesRegex(
                package_submission.GateError, "at least 1920x1080"
            ):
                self.probe(payload)

    def test_rejects_malformed_video_dimensions(self) -> None:
        for width, height in (("1920", 1080), (1920, None), (True, 1080)):
            payload = valid_ffprobe_video()
            payload["streams"][0]["width"] = width
            payload["streams"][0]["height"] = height
            with self.subTest(width=width, height=height), self.assertRaisesRegex(
                package_submission.GateError, "dimensions"
            ):
                self.probe(payload)

    def test_rejects_every_explicit_sensitive_tag_at_format_and_stream_scope(
        self,
    ) -> None:
        for tag in package_submission.SENSITIVE_VIDEO_METADATA_TAGS:
            for scope in ("format", "stream"):
                payload = valid_ffprobe_video()
                target = (
                    payload["format"]["tags"]
                    if scope == "format"
                    else payload["streams"][0]["tags"]
                )
                target[f" {tag.swapcase()} "] = "private fixture value"
                with self.subTest(tag=tag, scope=scope), self.assertRaisesRegex(
                    package_submission.GateError, "sensitive metadata tag"
                ):
                    self.probe(payload)

    def test_rejects_sensitive_chapter_and_program_metadata_tags(self) -> None:
        for scope in ("chapters", "programs"):
            payload = valid_ffprobe_video()
            payload[scope] = [{"id": 1, "tags": {"author": "private fixture"}}]
            with self.subTest(scope=scope), self.assertRaisesRegex(
                package_submission.GateError, "sensitive metadata tag"
            ):
                self.probe(payload)

    def test_rejects_malformed_tag_objects(self) -> None:
        for scope in ("format", "stream"):
            payload = valid_ffprobe_video()
            if scope == "format":
                payload["format"]["tags"] = ["encoder"]
            else:
                payload["streams"][0]["tags"] = ["language"]
            with self.subTest(scope=scope), self.assertRaisesRegex(
                package_submission.GateError, "metadata tags"
            ):
                self.probe(payload)

    def test_rejects_private_path_or_email_in_otherwise_allowed_tag(self) -> None:
        for leaked_value in (
            "/Users/person/private/final.mov",
            "owner@example.com",
        ):
            payload = valid_ffprobe_video()
            payload["format"]["tags"]["encoder"] = leaked_value
            with self.subTest(value=leaked_value), self.assertRaisesRegex(
                package_submission.GateError, "private path/identity metadata"
            ):
                self.probe(payload)

    def test_validate_local_video_preserves_hash_and_duration_gates(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            video = Path(raw) / "final.mp4"
            video.write_bytes(b"final video fixture")
            manifest = valid_manifest()
            manifest["video"]["local_file_sha256"] = hashlib.sha256(
                video.read_bytes()
            ).hexdigest()

            with patch.object(
                package_submission,
                "local_video_metadata",
                return_value={
                    "duration_seconds": 179.5,
                    "width": 1920,
                    "height": 1080,
                    "video_stream_count": 1,
                    "audio_stream_count": 1,
                    "probe": "ffprobe",
                },
            ):
                accepted = package_submission.validate_local_video(video, manifest)
            self.assertEqual(manifest["video"]["local_file_sha256"], accepted["sha256"])

            changed = valid_manifest()
            with self.assertRaisesRegex(package_submission.GateError, "SHA-256 mismatch"):
                package_submission.validate_local_video(video, changed)

            with patch.object(
                package_submission,
                "local_video_metadata",
                return_value={"duration_seconds": 180.001},
            ), self.assertRaisesRegex(package_submission.GateError, "official maximum"):
                package_submission.validate_local_video(video, manifest)

            with patch.object(
                package_submission,
                "local_video_metadata",
                return_value={"duration_seconds": 179.0},
            ), self.assertRaisesRegex(package_submission.GateError, "differs from manifest"):
                package_submission.validate_local_video(video, manifest)


class GitStateTest(unittest.TestCase):
    COMMIT = "1" * 40
    LOCAL_TAG_OBJECT = "a" * 40

    def validate_with_remote_refs(self, root: Path, remote_refs: str) -> None:
        manifest = package_submission.validate_manifest(valid_manifest())
        (root / "build.gradle").write_text(
            "group = 'io.github.example-owner.routecontract'\n"
            "version = '0.1.0'\n",
            encoding="utf-8",
        )

        def git_run(
            command: list[str],
            *,
            cwd: Path | None = None,
            env: dict[str, str] | None = None,
        ) -> str:
            self.assertEqual(root, cwd)
            if command == ["git", "rev-parse", "--show-toplevel"]:
                return f"{root}\n"
            if command == ["git", "rev-parse", "HEAD"]:
                return f"{self.COMMIT}\n"
            if command == [
                "git",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ]:
                return ""
            if command == ["git", "remote", "get-url", "origin"]:
                return "https://github.com/example-owner/routecontract.git\n"
            if command == ["git", "cat-file", "-t", "refs/tags/v0.1.0"]:
                return "tag\n"
            if command == ["git", "rev-parse", "refs/tags/v0.1.0^{commit}"]:
                return f"{self.COMMIT}\n"
            if command == ["git", "rev-parse", "refs/tags/v0.1.0"]:
                return f"{self.LOCAL_TAG_OBJECT}\n"
            if command == [
                "git",
                "ls-remote",
                "--tags",
                "origin",
                "refs/tags/v0.1.0",
                "refs/tags/v0.1.0^{}",
            ]:
                self.assertEqual("0", env.get("GIT_TERMINAL_PROMPT") if env else None)
                return remote_refs
            self.fail(f"unexpected command: {command}")

        with patch.object(package_submission, "run", side_effect=git_run):
            package_submission.validate_git_state(root, manifest)

    def test_accepts_exact_remote_annotated_tag_object_and_peel(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            self.validate_with_remote_refs(
                root,
                f"{self.LOCAL_TAG_OBJECT}\trefs/tags/v0.1.0\n"
                f"{self.COMMIT}\trefs/tags/v0.1.0^{{}}\n",
            )

    def test_rejects_remote_lightweight_tag_at_same_commit(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            with self.assertRaisesRegex(package_submission.GateError, "exact annotated"):
                self.validate_with_remote_refs(
                    root,
                    f"{self.COMMIT}\trefs/tags/v0.1.0\n",
                )

    def test_rejects_different_remote_tag_object_with_same_peel(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            with self.assertRaisesRegex(package_submission.GateError, "tag object"):
                self.validate_with_remote_refs(
                    root,
                    f"{'b' * 40}\trefs/tags/v0.1.0\n"
                    f"{self.COMMIT}\trefs/tags/v0.1.0^{{}}\n",
                )


class ReportContractTest(unittest.TestCase):
    BASE = (
        "2026년 오픈소스 개발자대회 결과보고서 "
        "개발 보조 AI OpenAI ChatGPT 및 Codex "
        "제품에는 AI 모델·학습/추론 코드·외부 AI API 호출이 없다 "
        "붙임1 SBOM(소프트웨어 자재명세서)"
    )
    PORTRAIT = (595.0, 842.0)
    LANDSCAPE = (842.0, 595.0)
    SBOM_ROWS = [
        {"name": "Alpha", "version": "1.0"},
        {"name": "Omega", "version": "2.0"},
    ]

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
        pages = ["body"] * 6 + ["붙임1 SBOM(소프트웨어 자재명세서) Omega 2.0"]
        sizes = [self.PORTRAIT] * 6 + [self.LANDSCAPE]
        with self.assertRaisesRegex(package_submission.GateError, "maximum is 5"):
            package_submission.report_page_contract(pages, sizes, self.SBOM_ROWS)

    def test_accepts_two_trailing_attachment_1_pages(self) -> None:
        pages = [
            "body page 1",
            "body page 2",
            "붙임1 SBOM(소프트웨어 자재명세서) Alpha 1.0",
            "SBOM continued rows Omega 2.0",
        ]
        sizes = [self.PORTRAIT, self.PORTRAIT, self.LANDSCAPE, self.LANDSCAPE]
        self.assertEqual(
            {"body_pages": 2, "attachment_1_pages": 2, "total_pages": 4},
            package_submission.report_page_contract(pages, sizes, self.SBOM_ROWS),
        )

    def test_rejects_wrong_body_or_attachment_orientation(self) -> None:
        pages = ["body", "붙임1 SBOM(소프트웨어 자재명세서) Omega 2.0"]
        for sizes, message in (
            ([self.LANDSCAPE, self.LANDSCAPE], "body page 1 must be A4 portrait"),
            ([self.PORTRAIT, self.PORTRAIT], "Attachment 1 page 2 must be A4 landscape"),
        ):
            with self.subTest(sizes=sizes), self.assertRaisesRegex(
                package_submission.GateError, message
            ):
                package_submission.report_page_contract(pages, sizes, self.SBOM_ROWS)

    def test_rejects_letter_or_legal_page_sizes(self) -> None:
        pages = ["body", "붙임1 SBOM(소프트웨어 자재명세서) Omega 2.0"]
        for sizes, message in (
            ([(612.0, 792.0), self.LANDSCAPE], "A4 portrait"),
            ([self.PORTRAIT, (1008.0, 612.0)], "A4 landscape"),
        ):
            with self.subTest(sizes=sizes), self.assertRaisesRegex(
                package_submission.GateError, message
            ):
                package_submission.report_page_contract(pages, sizes, self.SBOM_ROWS)

    def test_parses_real_poppler_a4_page_size_format(self) -> None:
        info = (
            "Pages:           2\n"
            "Page    1 size:  595.304 x 841.89 pts (A4)\n"
            "Page    2 size:  841.89 x 595.304 pts (A4)\n"
            "File size:       12345 bytes\n"
        )
        self.assertEqual(
            [(595.304, 841.89), (841.89, 595.304)],
            package_submission.parse_pdf_page_sizes(info, 2),
        )

    def test_rejects_blank_or_unanchored_attachment_page(self) -> None:
        sizes = [self.PORTRAIT, self.LANDSCAPE, self.LANDSCAPE]
        for trailing, message in (
            ("", "blank pages"),
            ("continued without a declared component", "no declared SBOM row anchor"),
        ):
            pages = [
                "body",
                "붙임1 SBOM(소프트웨어 자재명세서) Alpha 1.0",
                trailing,
            ]
            with self.subTest(trailing=trailing), self.assertRaisesRegex(
                package_submission.GateError, message
            ):
                package_submission.report_page_contract(pages, sizes, self.SBOM_ROWS)

    def test_requires_last_declared_row_on_final_attachment_page(self) -> None:
        pages = [
            "body",
            "붙임1 SBOM(소프트웨어 자재명세서) Omega 2.0",
            "continued Alpha 1.0",
        ]
        sizes = [self.PORTRAIT, self.LANDSCAPE, self.LANDSCAPE]
        with self.assertRaisesRegex(package_submission.GateError, "last declared SBOM row"):
            package_submission.report_page_contract(pages, sizes, self.SBOM_ROWS)

    def test_recognizes_multiword_row_split_by_pdf_column_order(self) -> None:
        row = {"name": "CycloneDX Gradle Plugin", "version": "3.4.0"}
        page = "CycloneDX https://example.invalid 10 3.4.0 Gradle purpose Plugin"
        self.assertTrue(package_submission.page_contains_sbom_row(page, row))


class ReportContentSbomTest(unittest.TestCase):
    def test_report_comparison_figure_excludes_fixture_identifiers(self) -> None:
        submission_root = SCRIPT.parents[1]
        svg = (submission_root / "assets" / "baseline-candidate.svg").read_text(
            encoding="utf-8"
        )
        content = (submission_root / "report-content.ko.json").read_text(
            encoding="utf-8"
        )
        combined = svg + "\n" + content

        for forbidden in ("user_id", "row 201", "= 3", "BETWEEN 3"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)
        self.assertIn("one synthetic fixture row", svg)
        self.assertIn("동일한 단일 fixture 행", content)

        png = (submission_root / "assets" / "baseline-candidate.png").read_bytes()
        self.assertEqual(
            "f4e94a5d64c7fde85aae58c36435a4a49ba5929fe67d6ccaf06ac64d2913b537",
            hashlib.sha256(png).hexdigest(),
        )

    def test_current_content_declares_exactly_ten_prioritized_rows(self) -> None:
        content_path = SCRIPT.parents[1] / "report-content.ko.json"
        with content_path.open(encoding="utf-8") as stream:
            content = json.load(stream)

        self.assertEqual(
            [
                "MySQL Connector/J",
                "MySQL Server 컨테이너",
                "Apache ShardingSphere",
                "Alibaba TransmittableThreadLocal",
                "Jackson Core",
                "Testcontainers (JUnit·MySQL)",
                "datasource-proxy",
                "JUnit Jupiter/Launcher",
                "Gradle Wrapper",
                "CycloneDX Gradle Plugin",
            ],
            [row["name"] for row in content["sbom"]],
        )

    def test_report_builder_requirements_pin_the_complete_python_closure(self) -> None:
        requirements_path = SCRIPT.parents[1] / "report-builder-requirements.txt"
        requirements = {
            line.strip()
            for line in requirements_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
        self.assertEqual(
            {
                "certifi==2026.7.22",
                "Pillow==12.3.0",
                "lxml==6.1.1",
                "python-docx==1.2.0",
                "typing_extensions==4.16.0",
            },
            requirements,
        )


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
            filenames = package_submission.validate_manifest(valid_manifest())[
                "official_submission_filenames"
            ]
            names = [filenames["docx"], filenames["pdf"]]
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

    def test_rejects_legacy_submission_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            upload = root / "upload"
            upload.mkdir()
            names = sorted(package_submission.LEGACY_SUBMISSION_FILENAMES)
            for name in names:
                (upload / name).write_bytes(b"legacy")
            with self.assertRaisesRegex(package_submission.GateError, "legacy"):
                package_submission.validate_upload_directory(upload, names)
            with self.assertRaisesRegex(package_submission.GateError, "legacy"):
                package_submission.build_upload_zip(upload, root / "legacy.zip", names)


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
    def test_public_youtube_contract_preserves_title_and_duration_gates(self) -> None:
        manifest = package_submission.validate_manifest(valid_manifest())
        local_video = {"duration_seconds": 179.5}
        youtube = {
            "title": "RouteContract demo",
            "duration_seconds": 179.0,
        }
        package_submission.validate_public_youtube_contract(
            manifest, local_video, youtube
        )

        changed_title = dict(youtube, title="Different title")
        with self.assertRaisesRegex(package_submission.GateError, "title mismatch"):
            package_submission.validate_public_youtube_contract(
                manifest, local_video, changed_title
            )

        over_limit = dict(youtube, duration_seconds=180.001)
        with self.assertRaisesRegex(package_submission.GateError, "180-second maximum"):
            package_submission.validate_public_youtube_contract(
                manifest, local_video, over_limit
            )

        different_upload = dict(youtube, duration_seconds=178.499)
        with self.assertRaisesRegex(
            package_submission.GateError, "checksummed local video"
        ):
            package_submission.validate_public_youtube_contract(
                manifest, local_video, different_upload
            )

    def test_public_youtube_contract_accepts_exact_one_second_rounding(self) -> None:
        manifest = package_submission.validate_manifest(valid_manifest())
        package_submission.validate_public_youtube_contract(
            manifest,
            {"duration_seconds": 179.5},
            {"title": "RouteContract demo", "duration_seconds": 178.5},
        )

    def test_tls_context_uses_the_pinned_certifi_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            ca_bundle = Path(raw) / "cacert.pem"
            ca_bundle.write_text("test CA bundle", encoding="utf-8")
            fake_certifi = type(
                "FakeCertifi",
                (),
                {"where": staticmethod(lambda: str(ca_bundle))},
            )
            sentinel = object()
            with patch.object(
                package_submission.importlib,
                "import_module",
                return_value=fake_certifi,
            ) as import_module, patch.object(
                package_submission.ssl,
                "create_default_context",
                return_value=sentinel,
            ) as create_context:
                context = package_submission.verified_tls_context()

            self.assertIs(sentinel, context)
            import_module.assert_called_once_with("certifi")
            create_context.assert_called_once_with(cafile=str(ca_bundle))

    def test_tls_context_fails_without_certifi(self) -> None:
        with patch.object(
            package_submission.importlib,
            "import_module",
            side_effect=ModuleNotFoundError("certifi"),
        ):
            with self.assertRaisesRegex(
                package_submission.GateError, "pinned certifi CA bundle"
            ):
                package_submission.verified_tls_context()

    def test_youtube_probe_ignores_local_config_and_playlists(self) -> None:
        url = "https://www.youtube.com/watch?v=abcdefghijk"
        commands: list[list[str]] = []

        def fake_run(command: list[str]) -> str:
            commands.append(command)
            return json.dumps(valid_youtube_probe())

        with patch.object(
            package_submission,
            "request_json",
            return_value={"title": "RouteContract demo"},
        ), patch.object(
            package_submission.shutil, "which", return_value="/usr/local/bin/yt-dlp"
        ), patch.object(package_submission, "run", side_effect=fake_run):
            result = package_submission.public_youtube_metadata(url)

        self.assertEqual(179.0, result["duration_seconds"])
        self.assertEqual("public", result["availability"])
        self.assertEqual("not_live", result["live_status"])
        self.assertEqual(0, result["age_limit"])
        self.assertEqual(1080, result["max_video_height"])
        self.assertEqual(
            [
                "/usr/local/bin/yt-dlp",
                "--ignore-config",
                "--no-playlist",
                "--check-all-formats",
                "--dump-single-json",
                "--skip-download",
                "--",
                url,
            ],
            commands[0],
        )

    def youtube_probe(self, metadata: object) -> dict:
        url = "https://www.youtube.com/watch?v=abcdefghijk"
        with patch.object(
            package_submission,
            "request_json",
            return_value={"title": "RouteContract demo"},
        ), patch.object(
            package_submission.shutil, "which", return_value="/usr/local/bin/yt-dlp"
        ), patch.object(
            package_submission, "run", return_value=json.dumps(metadata)
        ):
            return package_submission.public_youtube_metadata(url)

    def test_youtube_probe_accepts_none_age_limit_and_4k_video(self) -> None:
        metadata = valid_youtube_probe()
        metadata["age_limit"] = None
        metadata["formats"][1]["height"] = 2160

        result = self.youtube_probe(metadata)

        self.assertIsNone(result["age_limit"])
        self.assertEqual(2160, result["max_video_height"])

        metadata["age_limit"] = 0.0
        result = self.youtube_probe(metadata)
        self.assertEqual(0.0, result["age_limit"])

    def test_youtube_probe_requires_yt_dlp_for_public_format_evidence(self) -> None:
        with patch.object(
            package_submission,
            "request_json",
            return_value={"title": "RouteContract demo"},
        ), patch.object(package_submission.shutil, "which", return_value=None):
            with self.assertRaisesRegex(package_submission.GateError, "yt-dlp is required"):
                package_submission.public_youtube_metadata(
                    "https://www.youtube.com/watch?v=abcdefghijk"
                )

    def test_youtube_probe_rejects_non_public_or_missing_availability(self) -> None:
        for availability in (None, "unlisted", "private", "needs_auth"):
            metadata = valid_youtube_probe()
            if availability is None:
                del metadata["availability"]
            else:
                metadata["availability"] = availability
            with self.subTest(availability=availability), self.assertRaisesRegex(
                package_submission.GateError, "availability must be public"
            ):
                self.youtube_probe(metadata)

    def test_youtube_probe_rejects_live_upcoming_or_unknown_status(self) -> None:
        for live_status in (
            None,
            "is_live",
            "is_upcoming",
            "post_live",
            "was_live",
        ):
            metadata = valid_youtube_probe()
            if live_status is None:
                del metadata["live_status"]
            else:
                metadata["live_status"] = live_status
            with self.subTest(live_status=live_status), self.assertRaisesRegex(
                package_submission.GateError, "must be a non-live upload"
            ):
                self.youtube_probe(metadata)

    def test_youtube_probe_rejects_restricted_or_malformed_age_limit(self) -> None:
        for age_limit in (18, 1, -1, "0", False):
            metadata = valid_youtube_probe()
            metadata["age_limit"] = age_limit
            with self.subTest(age_limit=age_limit), self.assertRaisesRegex(
                package_submission.GateError, "age_limit must be 0 or null"
            ):
                self.youtube_probe(metadata)

        missing = valid_youtube_probe()
        del missing["age_limit"]
        with self.assertRaisesRegex(
            package_submission.GateError, "age_limit must be 0 or null"
        ):
            self.youtube_probe(missing)

    def test_youtube_probe_rejects_missing_or_low_resolution_video_formats(
        self,
    ) -> None:
        invalid_formats = (
            [],
            [
                {
                    "format_id": "136",
                    "height": 720,
                    "vcodec": "avc1.4d401f",
                    "url": "https://example.invalid/720p",
                }
            ],
            [
                {
                    "format_id": "140",
                    "height": 1080,
                    "vcodec": "none",
                    "url": "https://example.invalid/audio",
                }
            ],
            [
                {
                    "format_id": "137",
                    "height": 1080,
                    "vcodec": "avc1.640028",
                    "url": "",
                    "has_drm": False,
                }
            ],
            [
                {
                    "format_id": "137",
                    "height": 1080,
                    "vcodec": "avc1.640028",
                    "url": "https://example.invalid/drm",
                    "has_drm": True,
                }
            ],
            [
                {
                    "format_id": "137",
                    "height": 1080,
                    "vcodec": "avc1.640028",
                    "url": "https://example.invalid/missing-drm-status",
                }
            ],
            [
                {
                    "format_id": "137",
                    "height": 1080,
                    "vcodec": "avc1.640028",
                    "url": "https://example.invalid/unknown-drm-status",
                    "has_drm": None,
                }
            ],
        )
        for formats in invalid_formats:
            metadata = valid_youtube_probe()
            metadata["formats"] = formats
            with self.subTest(formats=formats), self.assertRaisesRegex(
                package_submission.GateError, "downloadable video format at 1080p"
            ):
                self.youtube_probe(metadata)

    def test_youtube_probe_rejects_malformed_format_evidence(self) -> None:
        malformed_formats = (
            None,
            {},
            ["not-an-object"],
            [{"height": True}],
            [{"has_drm": "false"}],
        )
        for formats in malformed_formats:
            metadata = valid_youtube_probe()
            metadata["formats"] = formats
            with self.subTest(formats=formats), self.assertRaisesRegex(
                package_submission.GateError, "format metadata"
            ):
                self.youtube_probe(metadata)

    def test_youtube_probe_rejects_empty_or_none_like_video_codec(self) -> None:
        for vcodec in ("", "   ", "none", "NONE", " None "):
            metadata = valid_youtube_probe()
            metadata["formats"][1]["vcodec"] = vcodec
            with self.subTest(vcodec=vcodec), self.assertRaisesRegex(
                package_submission.GateError, "downloadable video format at 1080p"
            ):
                self.youtube_probe(metadata)

    def test_youtube_probe_preserves_exact_id_and_finite_duration(self) -> None:
        wrong_id = valid_youtube_probe()
        wrong_id["id"] = "zyxwvutsrqp"
        with self.assertRaisesRegex(package_submission.GateError, "different YouTube video ID"):
            self.youtube_probe(wrong_id)

        for duration in (None, True, 0, -1, float("nan"), float("inf")):
            metadata = valid_youtube_probe()
            if duration is None:
                del metadata["duration"]
            else:
                metadata["duration"] = duration
            with self.subTest(duration=duration), self.assertRaisesRegex(
                package_submission.GateError, "duration"
            ):
                self.youtube_probe(metadata)

        with self.assertRaisesRegex(
            package_submission.GateError, "incomplete public video duration metadata"
        ):
            self.youtube_probe("not-an-object")

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
                    "head_branch": project["tag"],
                    "event": "push",
                    "path": ".github/workflows/release-evidence.yml",
                    "name": "Release evidence",
                    "repository": {"full_name": "example-owner/routecontract"},
                }
            if "/actions/artifacts/" in url:
                return {
                    "id": 987654,
                    "name": f"routecontract-release-evidence-{project['commit']}",
                    "expired": False,
                    "digest": f"sha256:{digest('a')}",
                    "workflow_run": {
                        "id": 123456,
                        "head_sha": project["commit"],
                        "head_branch": project["tag"],
                    },
                }
            if "/releases/tags/" in url:
                return {
                    "id": 7,
                    "draft": False,
                    "prerelease": False,
                    "immutable": True,
                    "tag_name": project["tag"],
                    "html_url": project["release_url"],
                    "assets": [
                        {
                            "name": evidence["source_archive_filename"],
                            "state": "uploaded",
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
            "availability": "public",
            "live_status": "not_live",
            "age_limit": 0,
            "max_video_height": 1080,
        }
        public_identity_events: list[str] = []
        with patch.object(
            package_submission, "request_json", side_effect=fake_json
        ), patch.object(
            package_submission, "public_youtube_metadata", return_value=youtube
        ), patch.object(
            package_submission,
            "verify_release_attestations",
            side_effect=lambda *_: public_identity_events.append("attestations"),
        ) as verify_attestations, patch.object(
            package_submission,
            "validate_remote_tag_identity",
            side_effect=lambda *_: public_identity_events.append("remote-tag-recheck"),
        ) as verify_remote_tag:
            result = package_submission.validate_public_evidence(
                manifest,
                {"duration_seconds": 179.5},
                evidence,
                Path("/evidence"),
                Path("/repository"),
            )
        self.assertEqual("success", result["ci_conclusion"])
        self.assertEqual("v0.1.0", result["release_tag"])
        self.assertIs(True, result["release_immutable"])
        self.assertEqual("abcdefghijk", result["youtube_video_id"])
        self.assertEqual("RouteContract demo", result["youtube_title"])
        self.assertEqual(179.0, result["youtube_duration_seconds"])
        self.assertEqual("public", result["youtube_availability"])
        self.assertEqual("not_live", result["youtube_live_status"])
        self.assertEqual(0, result["youtube_age_limit"])
        self.assertEqual(1080, result["youtube_max_video_height"])
        verify_attestations.assert_called_once_with(
            manifest, evidence, Path("/evidence")
        )
        verify_remote_tag.assert_called_once_with(Path("/repository"), manifest)
        self.assertEqual(
            ["attestations", "remote-tag-recheck"], public_identity_events
        )

    def test_release_attestation_verifier_checks_release_and_every_asset(self) -> None:
        manifest = package_submission.validate_manifest(valid_manifest())
        evidence = {
            "public_release_assets": {
                "SHA256SUMS": {"sha256": digest("1"), "size": 1},
                "routecontract-0.1.0-source.zip": {
                    "sha256": digest("2"),
                    "size": 1,
                },
            }
        }
        with tempfile.TemporaryDirectory() as raw:
            evidence_dir = Path(raw)
            for asset_name in evidence["public_release_assets"]:
                (evidence_dir / asset_name).write_bytes(b"x")
            repository = "example-owner/routecontract"
            tag = manifest["project"]["tag"]
            expected_commands = [
                ["/usr/local/bin/gh", "version"],
                [
                    "/usr/local/bin/gh",
                    "release",
                    "verify",
                    tag,
                    "--repo",
                    repository,
                ],
                [
                    "/usr/local/bin/gh",
                    "release",
                    "verify-asset",
                    tag,
                    str(evidence_dir / "SHA256SUMS"),
                    "--repo",
                    repository,
                ],
                [
                    "/usr/local/bin/gh",
                    "release",
                    "verify-asset",
                    tag,
                    str(evidence_dir / "routecontract-0.1.0-source.zip"),
                    "--repo",
                    repository,
                ],
            ]
            for version_output in (
                (
                    "gh version 2.93.0 (2026-05-27)\n"
                    "https://github.com/cli/cli/releases/tag/v2.93.0\n"
                ),
                (
                    "gh version 2.97.0 (2026-07-31)\n"
                    "https://github.com/cli/cli/releases/tag/v2.97.0\n"
                ),
            ):
                with self.subTest(version_output=version_output):
                    commands: list[list[str]] = []

                    def fake_subprocess_run(
                        command: list[str], **_: object
                    ) -> subprocess.CompletedProcess[str]:
                        commands.append(command)
                        return subprocess.CompletedProcess(
                            command,
                            0,
                            stdout=version_output,
                            stderr="",
                        )

                    def fake_run(command: list[str]) -> str:
                        commands.append(command)
                        return ""

                    with patch.object(
                        package_submission.shutil,
                        "which",
                        return_value="/usr/local/bin/gh",
                    ), patch.object(
                        package_submission.subprocess,
                        "run",
                        side_effect=fake_subprocess_run,
                    ), patch.object(
                        package_submission, "run", side_effect=fake_run
                    ):
                        package_submission.verify_release_attestations(
                            manifest, evidence, evidence_dir
                        )

                    self.assertEqual(expected_commands, commands)

    def test_release_attestation_verifier_rejects_affected_github_cli_before_verify(self) -> None:
        manifest = package_submission.validate_manifest(valid_manifest())

        for rendered_version in ("0.0.0", "2.87.3", "2.92.0"):
            with self.subTest(version=rendered_version):
                commands: list[list[str]] = []

                def fake_subprocess_run(
                    command: list[str], **_: object
                ) -> subprocess.CompletedProcess[str]:
                    commands.append(command)
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        stdout=f"gh version {rendered_version}\n",
                        stderr="",
                    )

                with patch.object(
                    package_submission.shutil,
                    "which",
                    return_value="/usr/local/bin/gh",
                ), patch.object(
                    package_submission.subprocess,
                    "run",
                    side_effect=fake_subprocess_run,
                ), patch.object(package_submission, "run") as verify_command:
                    with self.assertRaises(package_submission.GateError) as caught:
                        package_submission.verify_release_attestations(
                            manifest,
                            {"public_release_assets": {}},
                            Path("/evidence"),
                        )

                message = str(caught.exception)
                self.assertIn("2.93.0 or newer", message)
                self.assertIn("GHSA-8xvp-7hj6-mcj9", message)
                self.assertIn(rendered_version, message)
                self.assertEqual([["/usr/local/bin/gh", "version"]], commands)
                verify_command.assert_not_called()

    def test_release_attestation_verifier_rejects_malformed_github_cli_version(self) -> None:
        manifest = package_submission.validate_manifest(valid_manifest())
        malformed_outputs = (
            "",
            "GitHub CLI current\n",
            "gh version 02.093.000 (2026-05-27)\n",
            " gh version 2.93.0 (2026-05-27)\n",
            "gh version 2.93.0 (2026-05-27) \n",
            "gh version 2.93.0-rc.1 (2026-05-27)\n",
            "gh version 2.93.0\ngh version 2.97.0\n",
            (
                "gh version 2.93.0 (2026-05-27)\n"
                "https://github.com/cli/cli/releases/tag/v2.97.0\n"
            ),
            "gh version 2.93.0\nunexpected extra line\n",
        )

        for malformed_output in malformed_outputs:
            with self.subTest(output=malformed_output):
                commands: list[list[str]] = []

                def fake_subprocess_run(
                    command: list[str], **_: object
                ) -> subprocess.CompletedProcess[str]:
                    commands.append(command)
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        stdout=malformed_output,
                        stderr="",
                    )

                with patch.object(
                    package_submission.shutil,
                    "which",
                    return_value="/usr/local/bin/gh",
                ), patch.object(
                    package_submission.subprocess,
                    "run",
                    side_effect=fake_subprocess_run,
                ), patch.object(package_submission, "run") as verify_command:
                    with self.assertRaisesRegex(
                        package_submission.GateError,
                        "not an unambiguous stable version",
                    ):
                        package_submission.verify_release_attestations(
                            manifest,
                            {"public_release_assets": {}},
                            Path("/evidence"),
                        )

                self.assertEqual([["/usr/local/bin/gh", "version"]], commands)
                verify_command.assert_not_called()

    def test_release_attestation_verifier_fails_without_or_with_failed_github_cli(self) -> None:
        manifest = package_submission.validate_manifest(valid_manifest())
        with patch.object(
            package_submission.shutil, "which", return_value=None
        ), patch.object(package_submission.subprocess, "run") as version_command, patch.object(
            package_submission, "run"
        ) as verify_command:
            with self.assertRaisesRegex(package_submission.GateError, "GitHub CLI"):
                package_submission.verify_release_attestations(
                    manifest, {"public_release_assets": {}}, Path("/evidence")
                )
        version_command.assert_not_called()
        verify_command.assert_not_called()

        failed = subprocess.CompletedProcess(
            ["/usr/local/bin/gh", "version"],
            1,
            stdout="synthetic-sensitive-stdout",
            stderr="synthetic-sensitive-stderr",
        )
        with patch.object(
            package_submission.shutil,
            "which",
            return_value="/usr/local/bin/gh",
        ), patch.object(
            package_submission.subprocess, "run", return_value=failed
        ) as version_command, patch.object(
            package_submission, "run"
        ) as verify_command:
            with self.assertRaisesRegex(
                package_submission.GateError,
                "GitHub CLI version check failed",
            ) as caught:
                package_submission.verify_release_attestations(
                    manifest, {"public_release_assets": {}}, Path("/evidence")
                )
        self.assertNotIn("synthetic-sensitive", str(caught.exception))
        version_command.assert_called_once()
        verify_command.assert_not_called()

    def test_rejects_non_tag_push_release_evidence_run(self) -> None:
        manifest = package_submission.validate_manifest(valid_manifest())
        project = manifest["project"]
        evidence = {"public_release_assets": {}}
        base_run = {
            "status": "completed",
            "conclusion": "success",
            "head_sha": project["commit"],
            "head_branch": project["tag"],
            "event": "push",
            "path": ".github/workflows/release-evidence.yml",
            "name": "Release evidence",
            "repository": {"full_name": "example-owner/routecontract"},
        }
        cases = (
            {"event": "workflow_dispatch"},
            {"head_branch": "main"},
            {"path": ".github/workflows/ci.yml"},
            {"path": ".github/workflows/release-evidence.yml@evil.yaml"},
        )
        for override in cases:
            with self.subTest(override=override):

                def fake_json(url: str) -> dict:
                    if "/actions/runs/" in url:
                        return base_run | override
                    if "/commits/" in url:
                        return {"sha": project["commit"]}
                    return {
                        "private": False,
                        "archived": False,
                        "full_name": "example-owner/routecontract",
                    }

                with patch.object(
                    package_submission, "request_json", side_effect=fake_json
                ):
                    with self.assertRaisesRegex(
                        package_submission.GateError, "expected tag-push workflow"
                    ):
                        package_submission.validate_public_evidence(
                            manifest,
                            {"duration_seconds": 179.5},
                            evidence,
                            Path("/evidence"),
                            Path("/repository"),
                        )

    def test_rejects_artifact_for_non_tag_branch(self) -> None:
        manifest = package_submission.validate_manifest(valid_manifest())
        project = manifest["project"]
        evidence = {"public_release_assets": {}}

        def fake_json(url: str) -> dict:
            if "/actions/runs/" in url:
                return {
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": project["commit"],
                    "head_branch": project["tag"],
                    "event": "push",
                    "path": ".github/workflows/release-evidence.yml",
                    "name": "Release evidence",
                    "repository": {"full_name": "example-owner/routecontract"},
                }
            if "/actions/artifacts/" in url:
                return {
                    "id": 987654,
                    "name": f"routecontract-release-evidence-{project['commit']}",
                    "expired": False,
                    "digest": f"sha256:{digest('a')}",
                    "workflow_run": {
                        "id": 123456,
                        "head_sha": project["commit"],
                        "head_branch": "main",
                    },
                }
            if "/commits/" in url:
                return {"sha": project["commit"]}
            return {
                "private": False,
                "archived": False,
                "full_name": "example-owner/routecontract",
            }

        with patch.object(package_submission, "request_json", side_effect=fake_json):
            with self.assertRaisesRegex(package_submission.GateError, "artifact ID/digest"):
                package_submission.validate_public_evidence(
                    manifest,
                    {"duration_seconds": 179.5},
                    evidence,
                    Path("/evidence"),
                    Path("/repository"),
                )

    def test_rejects_mutable_or_unreported_release_immutability(self) -> None:
        manifest = package_submission.validate_manifest(valid_manifest())
        project = manifest["project"]
        evidence = {"public_release_assets": {}}
        for immutable in (False, None):
            with self.subTest(immutable=immutable):

                def fake_json(url: str) -> dict:
                    if "/actions/runs/" in url:
                        return {
                            "status": "completed",
                            "conclusion": "success",
                            "head_sha": project["commit"],
                            "head_branch": project["tag"],
                            "event": "push",
                            "path": ".github/workflows/release-evidence.yml",
                            "name": "Release evidence",
                            "repository": {
                                "full_name": "example-owner/routecontract"
                            },
                        }
                    if "/actions/artifacts/" in url:
                        return {
                            "id": 987654,
                            "name": (
                                "routecontract-release-evidence-"
                                f"{project['commit']}"
                            ),
                            "expired": False,
                            "digest": f"sha256:{digest('a')}",
                            "workflow_run": {
                                "id": 123456,
                                "head_sha": project["commit"],
                                "head_branch": project["tag"],
                            },
                        }
                    if "/releases/tags/" in url:
                        return {
                            "id": 7,
                            "draft": False,
                            "prerelease": False,
                            "immutable": immutable,
                            "tag_name": project["tag"],
                            "html_url": project["release_url"],
                            "assets": [],
                        }
                    if "/commits/" in url:
                        return {"sha": project["commit"]}
                    return {
                        "private": False,
                        "archived": False,
                        "full_name": "example-owner/routecontract",
                    }

                with patch.object(
                    package_submission, "request_json", side_effect=fake_json
                ):
                    with self.assertRaisesRegex(
                        package_submission.GateError, "not immutable"
                    ):
                        package_submission.validate_public_evidence(
                            manifest,
                            {"duration_seconds": 179.5},
                            evidence,
                            Path("/evidence"),
                            Path("/repository"),
                        )

    def test_rejects_release_run_for_different_commit(self) -> None:
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
                    "head_sha": "0" * 40,
                    "head_branch": project["tag"],
                    "event": "push",
                    "path": ".github/workflows/release-evidence.yml",
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
                    manifest,
                    {"duration_seconds": 179.5},
                    evidence,
                    Path("/evidence"),
                    Path("/repository"),
                )


if __name__ == "__main__":
    unittest.main()
