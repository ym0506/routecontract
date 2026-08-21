from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import unittest
import urllib.parse
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import call, patch
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


SCRIPT = Path(__file__).resolve().parents[1] / "package_submission.py"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("package_submission", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
package_submission = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_submission)
TEST_CURRENT_UTC = datetime(2026, 8, 14, 0, 0, 0, tzinfo=timezone.utc)


def digest(character: str = "a") -> str:
    return character * 64


def valid_license_reviews() -> list[dict[str, object]]:
    return [
        {
            "action": "resolve or renew the OCI license review before expiry",
            "componentName": "mysql",
            "componentVersion": "8.4.11",
            "expires": "2099-01-01",
            "owner": "test maintainers",
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
            "expires": "2099-01-01",
            "owner": "test maintainers",
            "purl": "pkg:maven/org.locationtech.jts.io/jts-io-common@1.19.0",
            "rationaleCode": "JTS_IO_COMMON_REDISTRIBUTION_NOTICE_TREATMENT_UNCONFIRMED",
            "reviewedAt": "2026-08-13",
            "scope": "test-runtime",
            "status": "manual-review-required",
        },
    ]


def valid_vulnerability_exceptions() -> list[dict[str, object]]:
    coordinates = (
        ("OSV-001", "GHSA-j288-q9x7-2f5v", "pkg:maven/commons-lang/commons-lang@2.4", None, "MODERATE"),
        ("OSV-002", "GHSA-pq2g-wx69-c263", "pkg:maven/net.minidev/json-smart@2.5.0", "2.5.2", "HIGH"),
        ("OSV-003", "GHSA-c2rv-hwqm-wjpg", "pkg:maven/org.apache.calcite/calcite-core@1.40.0", "1.42.0", "MODERATE"),
    )
    return [
        {
            "advisory": advisory,
            "exceptionId": exception_id,
            "expires": "2099-01-01",
            "fixedVersion": fixed_version,
            "owner": "test maintainers",
            "purl": purl,
            "rationaleCode": "SHARDINGSPHERE_5_5_3_TEST_GRAPH",
            "reviewedAt": "2026-08-12",
            "scope": "aggregate-test-only",
            "severity": severity,
        }
        for exception_id, advisory, purl, fixed_version, severity in coordinates
    ]


def findings_for(exceptions: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "action": "time-bounded reviewed exception; re-evaluate by expiry",
            "advisory": item["advisory"],
            "exceptionExpires": item["expires"],
            "exceptionId": item["exceptionId"],
            "fixedVersion": item["fixedVersion"],
            "owner": item["owner"],
            "purl": item["purl"],
            "rationaleCode": item["rationaleCode"],
            "reachabilityEvidence": {
                "exampleProfile": True,
                "publishedProfile": False,
                "publishedRuntime": False,
            },
            "reviewedAt": item["reviewedAt"],
            "scope": item["scope"],
            "severity": item["severity"],
        }
        for item in exceptions
    ]


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
            "report_free_text_contains_no_external_evidence_claims": True,
            "public_external_evidence_history_and_maintainer_edits_reviewed": True,
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


def valid_report_content(branch: str = "rc_only") -> dict:
    content_path = REPOSITORY_ROOT / "submission" / "report-content.ko.json"
    content = json.loads(content_path.read_text(encoding="utf-8"))
    manifest = valid_manifest()
    content["metadata"].update(
        {
            "team_name": manifest["submission_identity"]["team_name"],
            "team_size": manifest["submission_identity"]["team_size"],
            "division": manifest["submission_identity"]["division"],
            "task_type": manifest["submission_identity"]["task_type"],
            "project_name": manifest["submission_identity"]["registered_project_name"],
            "repository_url": manifest["project"]["repository_url"],
            "video_url": manifest["video"]["youtube_url"],
        }
    )

    def resolve_placeholders(value: object) -> object:
        if isinstance(value, str):
            if value == package_submission.REPORT_CONTENT_CONTRACT.EXTERNAL_EVIDENCE_SUMMARY_MARKER:
                return value
            return package_submission.PLACEHOLDER_RE.sub("resolved evidence", value)
        if isinstance(value, list):
            return [resolve_placeholders(child) for child in value]
        if isinstance(value, dict):
            return {key: resolve_placeholders(child) for key, child in value.items()}
        return value

    content = resolve_placeholders(content)
    assert isinstance(content, dict)
    external = {
        "branch": branch,
        "final_stable_tag": manifest["project"]["tag"],
        "tested_tag": manifest["project"]["tag"],
        "qualified_result_count": 1,
        "result_issue_url": f"{manifest['project']['repository_url']}/issues/42",
        "activation_record_url": None,
        "recruitment_record_url": None,
        "protocol_issue_url": f"{manifest['project']['repository_url']}/issues/9",
        "cutoff_utc": "2026-08-01T06:00:00Z",
    }
    if branch in {"rc_only", "zero"}:
        external["tested_tag"] = "v0.1.0-rc1"
        external["activation_record_url"] = (
            f"{manifest['project']['repository_url']}/blob/{'b' * 40}/docs/evidence/"
            "independent-rc-activation-v0.1.0-rc1.json"
        )
        external["recruitment_record_url"] = (
            f"{manifest['project']['repository_url']}/issues/9#issuecomment-777"
        )
    if branch == "zero":
        external["qualified_result_count"] = 0
        external["result_issue_url"] = None
    content["external_evidence"] = external
    return content


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

    def test_independent_rc_protocol_uses_twelve_asset_supply_chain_contract(self) -> None:
        protocol = (REPOSITORY_ROOT / "docs/independent-install-study.md").read_text(
            encoding="utf-8"
        )
        issue_form = (
            REPOSITORY_ROOT / ".github/ISSUE_TEMPLATE/independent-rc1-install.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("exactly eleven project payloads", protocol)
        self.assertIn("supply-chain-evidence.json", protocol)
        self.assertIn("exactly twelve uploaded assets", protocol)
        self.assertIn("Never mix different RC filenames", protocol)
        self.assertIn("cannot authenticate an earlier RC's JAR bytes", protocol)
        self.assertIn("workflow artifact identity/digest", protocol)
        self.assertIn("exact 17-file flat allowlist", protocol)
        self.assertIn("the 11 payload names", issue_form)
        self.assertIn("12/12 verify-asset=pass", issue_form)
        self.assertIn("flat files=17", issue_form)
        self.assertIn(
            "Direct project assets: 12 files (the tagged 11-payload allowlist + SHA256SUMS)",
            issue_form,
        )
        for stale in (
            "exactly ten project payloads",
            "11/11 verify-asset=pass",
            "tagged 10-payload allowlist",
        ):
            self.assertNotIn(stale, protocol + issue_form)

    def test_storyboard_requires_two_exclusive_external_result_branches(
        self,
    ) -> None:
        storyboard = (
            REPOSITORY_ROOT / "submission" / "video-storyboard.md"
        ).read_text(encoding="utf-8")

        for required in (
            "currently API-visible at both packaging observations",
            "**rc-only-result 분기:**",
            "Issue #9 form의 14개 필수 self-attestation",
            "나머지 자유서술 답변 의미",
            "REST/GraphQL은 현재 editor·last edit·retained body edit·title rename이 보이지 않는 상태",
            "비공개 독립성을 판정한다고 말하지 않는다",
            "정확히 활성화된 immutable RC",
            "schema-v2 activation-record permalink",
            "superseding 공개 모집 comment",
            "`RC-only`",
            "not final-stable validation or adoption",
            "최종 안정 Release 화면과 나란히 보여도 RC 결과를 최종 안정 검증으로 승격하지 않는다.",
            "**0-result 분기:**",
            "Issue #9의 activation/protocol",
            "currently API-visible at both packaging observations: 0",
            "final-stable external validation not obtained before cutoff",
            "구조화 `external_evidence.branch`와 영상 카드는 같은 분기",
            "게시하지 않았다면 카드와 내레이션에서 제외",
            "maintainer 수정·삭제·은폐·이전·누락 이력은 API로 복원하지 못해 "
            "owner 수동 진술에 의존",
            "final-stable-result 분기는 fail-closed",
            "저장소 owner와 다른 GitHub User 계정이 비작성자라고 self-attest",
        ):
            self.assertIn(required, storyboard)

        for unconditional_claim in (
            "**qualified-result 분기:**",
            "비작성자가 직접 남긴 첫 quick-start 결과 Issue",
            "최종 revision의 CI와 checksummed Release, 비작성자의 첫 설치 "
            "결과, upstream 질문을 모두 공개 링크로 남겼습니다.",
            "- [ ] 실제 비작성자의 첫 quick-start 결과가 본인 계정으로 "
            "공개되어 있다.",
            "비작성자 독립 clean-install 첫 결과 1건을 adoption과 구분해 링크했습니다.",
            "모든 acceptance criteria",
            "qualified Issue",
        ):
            self.assertNotIn(unconditional_claim, storyboard)

    def test_report_uses_generated_external_evidence_slot(self) -> None:
        report = json.loads(
            (REPOSITORY_ROOT / "submission" / "report-content.ko.json").read_text(
                encoding="utf-8"
            )
        )
        external = report["external_evidence"]
        self.assertEqual(
            set(package_submission.REPORT_CONTENT_CONTRACT.EXTERNAL_EVIDENCE_KEYS),
            set(external),
        )
        self.assertEqual(
            "https://github.com/ym0506/routecontract/issues/9",
            external["protocol_issue_url"],
        )
        slot = [item for item in report["other"] if item["lead"] == "외부 검증"]
        self.assertEqual(
            [package_submission.REPORT_CONTENT_CONTRACT.EXTERNAL_EVIDENCE_SUMMARY_MARKER],
            [item["text"] for item in slot],
        )
        roadmap = next(
            item["text"] for item in report["other"] if item["lead"] == "로드맵"
        )

        self.assertNotIn("비작성자 독립 설치 결과", roadmap)
        self.assertNotIn("qualified 결과", roadmap)
        self.assertNotIn("외부 검증 미확보", roadmap)
        self.assertNotIn("외부 설치 기록·license/security 재검토를 완료", roadmap)


class TaggedIssueFormAllowlistTest(unittest.TestCase):
    FORM_ROOT = REPOSITORY_ROOT / ".github/ISSUE_TEMPLATE"
    APPROVED = {
        "independent-rc1-install.yml": (
            "0f4afc4ac098e0ee425704168f045352b3e2a77f856a0ae7438a9f93d955e583"
        ),
        "independent-rc2-install.yml": (
            "518c4102b9a0f7725b46b825ad5952263b3418bdb07b0164c54a037d902e7f8a"
        ),
    }

    def test_accepts_reviewed_rc1_and_rc2_bytes(self) -> None:
        self.assertEqual(
            self.APPROVED,
            package_submission.APPROVED_ISSUE_FORM_SHA256_BY_FILENAME,
        )
        for filename, expected_sha256 in self.APPROVED.items():
            with self.subTest(filename=filename):
                data = (self.FORM_ROOT / filename).read_bytes()
                self.assertEqual(expected_sha256, hashlib.sha256(data).hexdigest())
                package_submission._validate_tagged_issue_form_bytes(data, filename)

    def test_rejects_tampering_cross_version_bytes_and_unreviewed_rc3(self) -> None:
        rc1 = (self.FORM_ROOT / "independent-rc1-install.yml").read_bytes()
        rc2 = (self.FORM_ROOT / "independent-rc2-install.yml").read_bytes()
        for data, filename in (
            (rc2 + b"\n", "independent-rc2-install.yml"),
            (rc1, "independent-rc2-install.yml"),
            (rc2, "independent-rc1-install.yml"),
        ):
            with self.subTest(filename=filename, data_sha256=hashlib.sha256(data).hexdigest()), (
                self.assertRaisesRegex(
                    package_submission.GateError,
                    "reviewed version-specific form",
                )
            ):
                package_submission._validate_tagged_issue_form_bytes(data, filename)

        with self.assertRaisesRegex(
            package_submission.GateError,
            "outside the contest package allowlist",
        ):
            package_submission._validate_tagged_issue_form_bytes(
                rc2.replace(b"0.1.0-rc2", b"0.1.0-rc3"),
                "independent-rc3-install.yml",
            )


class ReportExternalEvidenceContractTest(unittest.TestCase):
    def materialize(self, branch: str) -> dict:
        return package_submission.validate_and_materialize_report_content(
            valid_report_content(branch),
            valid_manifest(),
            current_utc=TEST_CURRENT_UTC,
        )

    @staticmethod
    def summary(content: dict) -> str:
        return next(
            item["text"] for item in content["other"] if item["lead"] == "외부 검증"
        )

    def test_final_stable_branch_is_fail_closed_without_distinct_protocol(self) -> None:
        with self.assertRaisesRegex(
            package_submission.GateError, "distinct reviewed stable form and protocol"
        ):
            self.materialize("final_stable")

    def test_rc_only_branch_names_rc_and_denies_stable_validation_and_adoption(
        self,
    ) -> None:
        summary = self.summary(self.materialize("rc_only"))

        for required in (
            "exact RC v0.1.0-rc1",
            "저장소 owner와 다른 GitHub User의 비작성자 self-attestation",
            "현재 GraphQL 편집 신호 없음(editor·last edit·body edit·title rename)",
            "14개 [x]·Task A enum",
            "[활성화 기록]·[모집 기록]·[검증 프로토콜]을 확인",
            "자동 gate는 실제 사람·작성자·비공개 독립성",
            "adoption, stable 검증을 증명하지 않는다",
            "stable 외부 검증 미확보",
            "maintainer 수정·삭제·은폐·이전·누락은 API 이력 복원·자동 검증 불가로 "
            "owner 수동 진술에 의존",
            "[결과 Issue]",
        ):
            self.assertIn(required, summary)

    def test_zero_branch_requires_honest_zero_and_no_result_issue(self) -> None:
        summary = self.summary(self.materialize("zero"))

        for required in (
            "exact RC v0.1.0-rc1",
            "[모집 기록]",
            "owner와 다른 GitHub User의 비작성자 self-attestation",
            "현재 GraphQL 편집 신호 없음(editor·last edit·body edit·title rename)",
            "14개 [x]·Task A enum",
            "갖춘 결과는 0건",
            "실제 사람·작성자·비공개 독립성은 자동 증명되지 않는다",
            "stable 외부 검증 미확보",
            "maintainer 수정·삭제·은폐·이전·누락은 API 이력 복원·자동 검증 불가로 "
            "owner 수동 진술에 의존",
        ):
            self.assertIn(required, summary)
        for overclaim in ("eligible", "qualified", "전 기준", "모든 acceptance"):
            self.assertNotIn(overclaim, summary)
        self.assertNotIn("issues/42", summary)

    def test_report_sentence_keeps_only_the_branch_necessary_public_url(self) -> None:
        rc_summary = self.summary(self.materialize("rc_only"))
        zero_summary = self.summary(self.materialize("zero"))

        self.assertIn("[결과 Issue]", rc_summary)
        self.assertIn("[모집 기록]", rc_summary)
        self.assertIn("[모집 기록]", zero_summary)
        for summary in (rc_summary, zero_summary):
            self.assertIn("[활성화 기록]", summary)
            self.assertIn("[검증 프로토콜]", summary)
            self.assertNotIn(
                "/docs/evidence/independent-rc-activation-v0.1.0-rc1.json",
                summary,
            )
            self.assertIn("활성화", summary)

    def test_rejects_branch_specific_permalink_omissions_or_leaks(self) -> None:
        mutations = (
            ("rc_only", {"activation_record_url": None}, "activation-record permalink"),
            ("rc_only", {"recruitment_record_url": None}, "Issue #9 comment"),
            ("zero", {"recruitment_record_url": None}, "Issue #9 comment"),
        )
        for branch, mutation, message in mutations:
            content = valid_report_content(branch)
            content["external_evidence"].update(mutation)
            with self.subTest(branch=branch, mutation=mutation), self.assertRaisesRegex(
                package_submission.GateError, message
            ):
                package_submission.validate_and_materialize_report_content(
                    content, valid_manifest(), current_utc=TEST_CURRENT_UTC
                )

    def test_rejects_future_cutoff_against_explicit_validation_utc(self) -> None:
        content = valid_report_content("zero")
        content["external_evidence"]["cutoff_utc"] = "2026-08-15T00:00:00Z"

        with self.assertRaisesRegex(package_submission.GateError, "later than current UTC"):
            package_submission.validate_and_materialize_report_content(
                content, valid_manifest(), current_utc=TEST_CURRENT_UTC
            )

    def test_rejects_unicode_issue_number(self) -> None:
        unicode_issue = valid_report_content("rc_only")
        unicode_issue["external_evidence"]["result_issue_url"] = (
            "https://github.com/example-owner/routecontract/issues/²"
        )
        with self.assertRaisesRegex(
            package_submission.GateError, "canonical public Issue URL"
        ):
            package_submission.validate_and_materialize_report_content(
                unicode_issue, valid_manifest(), current_utc=TEST_CURRENT_UTC
            )

    def test_rejects_change_outside_documented_private_overlay(self) -> None:
        mutations = (
            lambda content: content["features"][0].__setitem__(
                "text", content["features"][0]["text"] + " 변경"
            ),
            lambda content: content["other"].append(
                {
                    "lead": "추가",
                    "text": "최종 안정판이 외부에서 정상 동작함을 확인했다.",
                }
            ),
            lambda content: content["sbom"][0].__setitem__("version", "99.0"),
        )
        for mutate in mutations:
            content = valid_report_content("rc_only")
            mutate(content)
            with self.subTest(mutate=mutate), self.assertRaisesRegex(
                package_submission.GateError,
                "canonical closed source outside documented private-overlay fields",
            ):
                package_submission.validate_and_materialize_report_content(
                    content, valid_manifest(), current_utc=TEST_CURRENT_UTC
                )

    def test_accepts_each_documented_private_overlay_path(self) -> None:
        paths = package_submission.REPORT_CONTENT_CONTRACT.PRIVATE_OVERLAY_STRING_PATHS
        for path in paths:
            content = valid_report_content("zero")
            parent = content
            for component in path[:-1]:
                parent = parent[component]
            parent[path[-1]] = f"resolved private overlay {path!r}"
            with self.subTest(path=path):
                package_submission.validate_and_materialize_report_content(
                    content, valid_manifest(), current_utc=TEST_CURRENT_UTC
                )

    def test_rejects_rc_result_collapsed_into_final_stable_branch(self) -> None:
        content = valid_report_content("final_stable")
        content["external_evidence"]["tested_tag"] = "v0.1.0-rc1"

        with self.assertRaisesRegex(
            package_submission.GateError, "distinct reviewed stable form and protocol"
        ):
            package_submission.validate_and_materialize_report_content(
                content, valid_manifest(), current_utc=TEST_CURRENT_UTC
            )

    def test_rejects_rc_only_branch_without_an_exact_rc(self) -> None:
        content = valid_report_content("rc_only")
        content["external_evidence"]["tested_tag"] = "v0.1.0"

        with self.assertRaisesRegex(package_submission.GateError, "exact vMAJOR"):
            package_submission.validate_and_materialize_report_content(
                content, valid_manifest(), current_utc=TEST_CURRENT_UTC
            )

    def test_rejects_rc_from_a_different_stable_version(self) -> None:
        content = valid_report_content("rc_only")
        content["external_evidence"]["tested_tag"] = "v0.2.0-rc1"

        with self.assertRaisesRegex(package_submission.GateError, "RC of the exact final"):
            package_submission.validate_and_materialize_report_content(
                content, valid_manifest(), current_utc=TEST_CURRENT_UTC
            )

    def test_rejects_unanchored_positive_result_count(self) -> None:
        for branch in ("rc_only",):
            content = valid_report_content(branch)
            content["external_evidence"]["qualified_result_count"] = 2
            with self.subTest(branch=branch), self.assertRaisesRegex(
                package_submission.GateError, "exactly one qualified"
            ):
                package_submission.validate_and_materialize_report_content(
                    content, valid_manifest(), current_utc=TEST_CURRENT_UTC
                )

    def test_rejects_zero_branch_with_a_result_or_positive_count(self) -> None:
        for mutation in (
            {"qualified_result_count": 1},
            {"result_issue_url": "https://github.com/example-owner/routecontract/issues/42"},
        ):
            content = valid_report_content("zero")
            content["external_evidence"].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaisesRegex(
                package_submission.GateError, "count=0 and result_issue_url=null"
            ):
                package_submission.validate_and_materialize_report_content(
                    content, valid_manifest(), current_utc=TEST_CURRENT_UTC
                )

    def test_rejects_protocol_issue_substituted_for_participant_result(self) -> None:
        content = valid_report_content("rc_only")
        content["external_evidence"]["result_issue_url"] = content[
            "external_evidence"
        ]["protocol_issue_url"]

        with self.assertRaisesRegex(package_submission.GateError, "cannot substitute"):
            package_submission.validate_and_materialize_report_content(
                content, valid_manifest(), current_utc=TEST_CURRENT_UTC
            )

    def test_rejects_mismatched_final_tag_and_manual_summary_text(self) -> None:
        mismatched = valid_report_content("rc_only")
        mismatched["external_evidence"]["final_stable_tag"] = "v0.1.1"
        manual = valid_report_content("rc_only")
        self.summary(manual)
        next(item for item in manual["other"] if item["lead"] == "외부 검증")[
            "text"
        ] = "RC 결과를 최종 결과로 직접 입력"

        for content, message in (
            (mismatched, "does not match the final package tag"),
            (manual, "must remain the generated structured-evidence marker"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(
                package_submission.GateError, message
            ):
                package_submission.validate_and_materialize_report_content(
                    content, valid_manifest(), current_utc=TEST_CURRENT_UTC
                )

    def test_rejects_unresolved_or_partial_structured_branch(self) -> None:
        source = json.loads(
            (REPOSITORY_ROOT / "submission" / "report-content.ko.json").read_text(
                encoding="utf-8"
            )
        )
        partial = deepcopy(source)
        partial["external_evidence"]["branch"] = "rc_only"

        for content in (source, partial):
            with self.subTest(branch=content["external_evidence"]["branch"]), self.assertRaisesRegex(
                package_submission.GateError, "unresolved structured fields"
            ):
                package_submission.validate_and_materialize_report_content(
                    content, valid_manifest(), current_utc=TEST_CURRENT_UTC
                )

class PublicExternalEvidenceTest(unittest.TestCase):
    RECORD_COMMIT = "b" * 40
    TAG_COMMIT = "c" * 40
    RECORD_BLOB = "d" * 40
    RECORD_TREE = "e" * 40
    FORM_BLOB = "f" * 40
    PROTOCOL_BLOB = "7" * 40
    README_BLOB = "6" * 40
    TAG_TREE = "a" * 40
    TAG_OBJECT = "9" * 40
    RUN_ID = 1
    ARTIFACT_ID = 2
    ACTIVATION_PULL_NUMBER = 88
    REPOSITORY_ID = 1300192
    REPOSITORY_NODE = "R_kgDOExample"

    def setUp(self) -> None:
        self.manifest = package_submission.validate_manifest(valid_manifest())
        self.repository_url = self.manifest["project"]["repository_url"]
        self.api_base = "https://api.github.com/repos/example-owner/routecontract"
        self.git_show_patcher = patch.object(
            package_submission, "_git_show_bytes", side_effect=self.tagged_bytes
        )
        self.git_show_patcher.start()
        self.addCleanup(self.git_show_patcher.stop)
        self.graphql_issues_by_number: dict[int, dict] = {}
        self.graphql_mutate = None
        self.graphql_patcher = patch.object(
            package_submission,
            "request_graphql_issue",
            side_effect=self.fake_graphql_issue,
        )
        self.graphql_patcher.start()
        self.addCleanup(self.graphql_patcher.stop)
        self.activation_pull_patcher = patch.object(
            package_submission,
            "request_json_list",
            side_effect=self.fake_activation_pull_requests,
        )
        self.activation_pull_patcher.start()
        self.addCleanup(self.activation_pull_patcher.stop)
        artifact_names = (
            *self.public_assets(),
            *package_submission.RC_ACTIVATION_RECORD_VALIDATOR.WORKFLOW_ONLY_FILES,
        )
        self.artifact_download_patcher = patch.object(
            package_submission,
            "download_and_validate_public_rc_workflow_artifact",
            return_value={name: digest("7") for name in sorted(artifact_names)},
        )
        self.artifact_download = self.artifact_download_patcher.start()
        self.addCleanup(self.artifact_download_patcher.stop)

    @staticmethod
    def tagged_bytes(_commit: str, path: str) -> bytes:
        return (REPOSITORY_ROOT / path).read_bytes()

    def fake_graphql_issue(self, _owner: str, _repository: str, number: int) -> dict:
        rest = deepcopy(self.graphql_issues_by_number[number])
        user = rest["user"]
        issue = {
            "id": rest["node_id"],
            "number": rest["number"],
            "url": rest["html_url"],
            "title": rest["title"],
            "body": rest["body"],
            "createdAt": rest["created_at"],
            "updatedAt": rest["updated_at"],
            "authorAssociation": rest["author_association"],
            "author": {
                "__typename": "User",
                "login": user["login"],
                "id": user["node_id"],
                "databaseId": user["id"],
            },
            "editor": None,
            "lastEditedAt": None,
            "includesCreatedEdit": False,
            "userContentEdits": {
                "totalCount": 0,
                "nodes": [],
                "pageInfo": {"hasNextPage": False},
            },
            "timelineItems": {
                "totalCount": 0,
                "nodes": [],
                "pageInfo": {"hasNextPage": False},
            },
        }
        payload = {
            "data": {
                "repository": {
                    "id": self.REPOSITORY_NODE,
                    "nameWithOwner": "example-owner/routecontract",
                    "issue": issue,
                }
            }
        }
        if self.graphql_mutate is not None:
            self.graphql_mutate(payload)
        return payload

    @staticmethod
    def public_assets(version: str = "0.1.0-rc1") -> list[str]:
        return [
            f"routecontract-{version}-source.zip",
            f"routecontract-shardingsphere-5.5-{version}.jar",
            f"routecontract-shardingsphere-5.5-{version}-sources.jar",
            f"routecontract-shardingsphere-5.5-{version}-javadoc.jar",
            "routecontract-shardingsphere-5.5.pom",
            "routecontract-shardingsphere-5.5-cyclonedx.json",
            "routecontract-shardingsphere-5.5-cyclonedx.xml",
            "routecontract-aggregate-cyclonedx.json",
            "routecontract-aggregate-cyclonedx.xml",
            "supply-chain-evidence.json",
            "test-summary.txt",
            "SHA256SUMS",
        ]

    def payload_digests(self) -> dict[str, str]:
        return {
            name: hashlib.sha256(name.encode("utf-8")).hexdigest()
            for name in self.public_assets()
            if name != package_submission.CHECKSUMS_NAME
        }

    def checksum_bytes(self) -> bytes:
        return "".join(
            f"{checksum}  {name}\n"
            for name, checksum in sorted(self.payload_digests().items())
        ).encode("utf-8")

    def activation_record(self) -> dict:
        form = "independent-rc1-install.yml"
        return {
            "issueFormFilename": form,
            "issueFormPermalink": (
                f"{self.repository_url}/blob/{self.TAG_COMMIT}/"
                f".github/ISSUE_TEMPLATE/{form}"
            ),
            "issueFormUrl": f"{self.repository_url}/issues/new?template={form}",
            "publicAssets": self.public_assets(),
            "releaseEvidence": {
                "artifactDigest": f"sha256:{digest('d')}",
                "artifactFileCount": 17,
                "artifactId": self.ARTIFACT_ID,
                "headSha": self.TAG_COMMIT,
                "runId": self.RUN_ID,
                "runUrl": f"{self.repository_url}/actions/runs/{self.RUN_ID}",
            },
            "releaseImmutability": {"enabled": True, "enforcedByOwner": True},
            "releaseState": {"draft": False, "immutable": True, "prerelease": True},
            "releaseUrl": f"{self.repository_url}/releases/tag/v0.1.0-rc1",
            "repository": self.repository_url,
            "schemaVersion": 2,
            "sha256sumsSha256": hashlib.sha256(self.checksum_bytes()).hexdigest(),
            "tag": "v0.1.0-rc1",
            "tagCommit": self.TAG_COMMIT,
            "taggedProtocolUrl": (
                f"{self.repository_url}/blob/v0.1.0-rc1/docs/independent-install-study.md"
            ),
            "taggedReadmeUrl": f"{self.repository_url}/blob/v0.1.0-rc1/README.md",
        }

    def activation_marker(self) -> str:
        return (
            "ROUTECONTRACT_RC_ACTIVATION_VERIFIED tag=v0.1.0-rc1 "
            f"commit={self.TAG_COMMIT} run={self.RUN_ID} "
            f"artifact={self.ARTIFACT_ID} assets=12"
        )

    def eligible_issue(self, content: dict, number: int = 42) -> dict:
        evidence = content["external_evidence"]
        body_lines = [f"Exact tag tested: {evidence['tested_tag']}"]
        if evidence["branch"] in {"rc_only", "zero"}:
            body_lines.extend(
                (
                    self.activation_marker(),
                    f"ACTIVATION_RECORD_PERMALINK {evidence['activation_record_url']}",
                    "PUBLIC_RECRUITMENT_RECORD_PERMALINK "
                    f"{evidence['recruitment_record_url']}",
                )
            )
        body_lines.extend(
            f"- [x] {label}"
            for label in package_submission.RESULT_ISSUE_REQUIRED_CHECKBOXES
        )
        body_lines.extend(
            (
                "### Task A first outcome — exact-tag Quick Start",
                "UNASSISTED_PASS",
            )
        )
        return {
            "repository_url": self.api_base,
            "html_url": f"{self.repository_url}/issues/{number}",
            "number": number,
            "title": f"[independent-install] clean attempt {number}",
            "node_id": f"I_kwDOExample{number}",
            "user": {
                "id": 10_000 + number,
                "node_id": f"U_kgDOExample{number}",
                "login": f"independent-tester-{number}",
                "type": "User",
            },
            "author_association": "NONE",
            "body": "\n".join(body_lines),
            "labels": [{"name": "evidence"}, {"name": "community"}],
            "created_at": "2026-07-23T00:00:00Z",
            "updated_at": "2026-07-23T00:01:00Z",
        }

    def unrelated_issue(self, number: int) -> dict:
        return {
            "repository_url": self.api_base,
            "html_url": f"{self.repository_url}/issues/{number}",
            "number": number,
            "title": f"ordinary bug {number}",
            "node_id": f"I_kwDOOrdinary{number}",
            "user": {
                "id": 20_000 + number,
                "node_id": f"U_kgDOOrdinary{number}",
                "login": "ordinary-user",
                "type": "User",
            },
            "author_association": "NONE",
            "body": "unrelated report",
            "labels": [{"name": "bug"}],
            "created_at": "2026-07-23T00:00:00Z",
            "updated_at": "2026-07-23T00:01:00Z",
        }

    def recruitment_comment(self, content: dict) -> dict:
        evidence = content["external_evidence"]
        return {
            "html_url": evidence["recruitment_record_url"],
            "issue_url": f"{self.api_base}/issues/9",
            "user": {"login": "example-owner", "type": "User"},
            "author_association": "OWNER",
            "body": "\n".join(
                (
                    "ROUTECONTRACT_PUBLIC_RECRUITMENT_OPEN tag=v0.1.0-rc1",
                    self.activation_marker(),
                    f"ACTIVATION_RECORD_PERMALINK {evidence['activation_record_url']}",
                )
            ),
            "created_at": "2026-07-21T00:00:00Z",
            "updated_at": "2026-07-21T00:05:00Z",
        }

    def release_assets(self, tested_tag: str) -> list[dict]:
        checksum_sha = hashlib.sha256(self.checksum_bytes()).hexdigest()
        assets: list[dict] = []
        for asset_id, name in enumerate(self.public_assets(), start=100):
            asset_sha = (
                checksum_sha
                if name == package_submission.CHECKSUMS_NAME
                else self.payload_digests()[name]
            )
            assets.append(
                {
                    "id": asset_id,
                    "name": name,
                    "size": len(self.checksum_bytes()) if name == "SHA256SUMS" else 123,
                    "state": "uploaded",
                    "digest": f"sha256:{asset_sha}",
                    "url": f"{self.api_base}/releases/assets/{asset_id}",
                    "browser_download_url": (
                        f"{self.repository_url}/releases/download/{tested_tag}/{name}"
                    ),
                    "created_at": "2026-07-20T02:00:00Z",
                    "updated_at": "2026-07-20T02:01:00Z",
                }
            )
        return assets

    def activation_pull_request(self) -> dict:
        return {
            "id": 8800,
            "node_id": "PR_kwDOActivation88",
            "number": self.ACTIVATION_PULL_NUMBER,
            "html_url": f"{self.repository_url}/pull/{self.ACTIVATION_PULL_NUMBER}",
            "state": "closed",
            "merged": True,
            "merged_at": "2026-07-20T05:00:00Z",
            "merge_commit_sha": self.RECORD_COMMIT,
            "base": {
                "ref": "main",
                "repo": {"full_name": "example-owner/routecontract"},
            },
        }

    def fake_activation_pull_requests(self, url: str) -> list[dict]:
        self.assertEqual(
            f"{self.api_base}/commits/{self.RECORD_COMMIT}/pulls?per_page=100",
            url,
        )
        return [deepcopy(self.activation_pull_request())]

    def fake_json(
        self,
        content: dict,
        *,
        record: dict | None = None,
        issues: list[dict] | None = None,
        mutate=None,
    ):
        evidence = content["external_evidence"]
        activation = deepcopy(record or self.activation_record())
        issues_by_number = {
            issue["number"]: deepcopy(issue) for issue in (issues or [])
        }
        self.graphql_issues_by_number = deepcopy(issues_by_number)

        def respond(url: str) -> dict:
            if url == self.api_base:
                value = {
                    "id": self.REPOSITORY_ID,
                    "node_id": self.REPOSITORY_NODE,
                    "full_name": "example-owner/routecontract",
                    "private": False,
                    "archived": False,
                }
            elif "/contents/docs/evidence/" in url:
                raw = json.dumps(activation, separators=(",", ":")).encode("utf-8")
                value = {
                    "type": "file",
                    "path": (
                        "docs/evidence/independent-rc-activation-v0.1.0-rc1.json"
                    ),
                    "sha": self.RECORD_BLOB,
                    "html_url": evidence["activation_record_url"],
                    "encoding": "base64",
                    "content": base64.b64encode(raw).decode("ascii"),
                    "size": len(raw),
                }
            elif "/contents/.github/ISSUE_TEMPLATE/independent-rc1-install.yml" in url:
                raw = self.tagged_bytes(self.TAG_COMMIT, ".github/ISSUE_TEMPLATE/independent-rc1-install.yml")
                value = {
                    "type": "file",
                    "path": ".github/ISSUE_TEMPLATE/independent-rc1-install.yml",
                    "sha": self.FORM_BLOB,
                    "html_url": activation["issueFormPermalink"],
                    "encoding": "base64",
                    "content": base64.b64encode(raw).decode("ascii"),
                    "size": len(raw),
                }
            elif "/contents/docs/independent-install-study.md" in url:
                raw = self.tagged_bytes(self.TAG_COMMIT, "docs/independent-install-study.md")
                value = {
                    "type": "file",
                    "path": "docs/independent-install-study.md",
                    "sha": self.PROTOCOL_BLOB,
                    "html_url": activation["taggedProtocolUrl"],
                    "encoding": "base64",
                    "content": base64.b64encode(raw).decode("ascii"),
                    "size": len(raw),
                }
            elif "/contents/README.md" in url:
                raw = self.tagged_bytes(self.TAG_COMMIT, "README.md")
                value = {
                    "type": "file",
                    "path": "README.md",
                    "sha": self.README_BLOB,
                    "html_url": activation["taggedReadmeUrl"],
                    "encoding": "base64",
                    "content": base64.b64encode(raw).decode("ascii"),
                    "size": len(raw),
                }
            elif f"/commits/{self.RECORD_COMMIT}" in url:
                value = {
                    "sha": self.RECORD_COMMIT,
                    "parents": [{"sha": self.TAG_COMMIT}],
                    "files": [
                        {
                            "filename": (
                                "docs/evidence/"
                                "independent-rc-activation-v0.1.0-rc1.json"
                            ),
                            "status": "added",
                        }
                    ],
                    "commit": {
                        "tree": {"sha": self.RECORD_TREE},
                        "author": {"date": "2026-07-20T04:45:00Z"},
                        "committer": {"date": "2026-07-20T04:50:00Z"},
                    },
                }
            elif url == f"{self.api_base}/pulls/{self.ACTIVATION_PULL_NUMBER}":
                value = self.activation_pull_request()
            elif f"/git/trees/{self.RECORD_TREE}" in url:
                value = {
                    "sha": self.RECORD_TREE,
                    "truncated": False,
                    "tree": [
                        {
                            "path": (
                                "docs/evidence/"
                                "independent-rc-activation-v0.1.0-rc1.json"
                            ),
                            "mode": "100644",
                            "type": "blob",
                            "sha": self.RECORD_BLOB,
                        }
                    ],
                }
            elif url == f"{self.api_base}/compare/{self.RECORD_COMMIT}...main":
                value = {
                    "status": "ahead",
                    "ahead_by": 3,
                    "behind_by": 0,
                    "base_commit": {"sha": self.RECORD_COMMIT},
                    "merge_base_commit": {"sha": self.RECORD_COMMIT},
                    "head_commit": {"sha": self.manifest["project"]["commit"]},
                }
            elif f"/commits/{self.TAG_COMMIT}" in url:
                value = {
                    "sha": self.TAG_COMMIT,
                    "commit": {"tree": {"sha": self.TAG_TREE}},
                }
            elif f"/git/trees/{self.TAG_TREE}" in url:
                value = {
                    "sha": self.TAG_TREE,
                    "truncated": False,
                    "tree": [
                        {
                            "path": ".github/ISSUE_TEMPLATE/independent-rc1-install.yml",
                            "mode": "100644",
                            "type": "blob",
                            "sha": self.FORM_BLOB,
                        },
                        {
                            "path": "docs/independent-install-study.md",
                            "mode": "100644",
                            "type": "blob",
                            "sha": self.PROTOCOL_BLOB,
                        },
                        {
                            "path": "README.md",
                            "mode": "100644",
                            "type": "blob",
                            "sha": self.README_BLOB,
                        },
                    ],
                }
            elif "/git/ref/tags/v0.1.0-rc1" in url:
                value = {
                    "ref": "refs/tags/v0.1.0-rc1",
                    "object": {
                        "type": "tag",
                        "sha": self.TAG_OBJECT,
                        "url": f"{self.api_base}/git/tags/{self.TAG_OBJECT}",
                    },
                }
            elif url == f"{self.api_base}/git/tags/{self.TAG_OBJECT}":
                value = {
                    "sha": self.TAG_OBJECT,
                    "tag": "v0.1.0-rc1",
                    "object": {"type": "commit", "sha": self.TAG_COMMIT},
                }
            elif url == f"{self.api_base}/actions/runs/{self.RUN_ID}":
                value = {
                    "id": self.RUN_ID,
                    "html_url": activation["releaseEvidence"]["runUrl"],
                    "head_sha": self.TAG_COMMIT,
                    "head_branch": "v0.1.0-rc1",
                    "event": "push",
                    "status": "completed",
                    "conclusion": "success",
                    "name": "Release evidence",
                    "path": ".github/workflows/release-evidence.yml",
                    "repository": {"full_name": "example-owner/routecontract"},
                    "created_at": "2026-07-20T00:00:00Z",
                    "updated_at": "2026-07-20T01:00:00Z",
                }
            elif url == f"{self.api_base}/actions/artifacts/{self.ARTIFACT_ID}":
                value = {
                    "id": self.ARTIFACT_ID,
                    "name": f"routecontract-release-evidence-{self.TAG_COMMIT}",
                    "digest": activation["releaseEvidence"]["artifactDigest"],
                    "expired": False,
                    "size_in_bytes": 456,
                    "workflow_run": {
                        "id": self.RUN_ID,
                        "head_sha": self.TAG_COMMIT,
                        "head_branch": "v0.1.0-rc1",
                    },
                    "created_at": "2026-07-20T00:20:00Z",
                    "updated_at": "2026-07-20T00:30:00Z",
                }
            elif "/releases/tags/v0.1.0-rc1" in url:
                value = {
                    "draft": False,
                    "prerelease": True,
                    "immutable": True,
                    "tag_name": "v0.1.0-rc1",
                    "html_url": f"{self.repository_url}/releases/tag/v0.1.0-rc1",
                    "created_at": "2026-07-20T01:30:00Z",
                    "published_at": "2026-07-20T03:00:00Z",
                    "updated_at": "2026-07-20T04:00:00Z",
                    "assets": self.release_assets("v0.1.0-rc1"),
                }
            elif "/issues/comments/777" in url:
                value = self.recruitment_comment(content)
            elif "/releases/tags/v0.1.0" in url:
                value = {
                    "draft": False,
                    "prerelease": False,
                    "immutable": True,
                    "tag_name": "v0.1.0",
                    "html_url": f"{self.repository_url}/releases/tag/v0.1.0",
                    "created_at": "2026-07-20T00:00:00Z",
                    "published_at": "2026-07-21T00:00:00Z",
                    "updated_at": "2026-07-21T00:05:00Z",
                }
            elif "/issues/" in url:
                number = int(url.rsplit("/", 1)[1])
                if number not in issues_by_number:
                    raise AssertionError(f"unexpected direct Issue request: {url}")
                value = deepcopy(issues_by_number[number])
            else:
                raise AssertionError(f"unexpected public-evidence request: {url}")
            value = deepcopy(value)
            if mutate is not None:
                mutate(url, value)
            return value

        return respond

    @staticmethod
    def fake_pages(
        pages: dict[int, list[dict]],
        links: dict[int, list[str]] | None = None,
    ):
        headers = links or {}

        def respond(url: str) -> tuple[list[dict], list[str]]:
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            page = int(query["page"][0]) if "page" in query else 1
            return deepcopy(pages.get(page, [])), deepcopy(headers.get(page, []))

        return respond

    def materialized(self, branch: str) -> dict:
        return package_submission.validate_and_materialize_report_content(
            valid_report_content(branch),
            self.manifest,
            current_utc=TEST_CURRENT_UTC,
        )

    def test_both_enabled_branches_bind_to_public_github_evidence(self) -> None:
        for branch in ("rc_only", "zero"):
            content = self.materialized(branch)
            issue = self.eligible_issue(content)
            page_one = [issue] if branch != "zero" else [self.unrelated_issue(17)]
            with self.subTest(branch=branch), patch.object(
                package_submission, "request_json",
                side_effect=self.fake_json(content, issues=[issue]),
            ), patch.object(
                package_submission, "request_json_list_page",
                side_effect=self.fake_pages({1: page_one, 2: []}),
            ) as listed, patch.object(
                package_submission, "request_bytes", return_value=self.checksum_bytes()
            ):
                metadata = package_submission.validate_public_external_evidence(
                    content, self.manifest
                )
            self.assertEqual(branch, metadata["branch"])
            self.assertGreaterEqual(listed.call_count, 1)
            if branch == "rc_only":
                self.assertIn("activation_record_commit", metadata)
                self.assertIn("recruitment_effective_at", metadata)
                self.assertEqual(17, metadata["activation_artifact_file_count"])
                self.assertTrue(metadata["activation_artifact_raw_osv_absent"])
                self.assertEqual("independent-tester-42", metadata["result_issue_author"])
            else:
                self.assertIn("activation_record_commit", metadata)
                self.assertIn("recruitment_effective_at", metadata)
                self.assertEqual(17, metadata["activation_artifact_file_count"])
                self.assertTrue(metadata["activation_artifact_raw_osv_absent"])
                self.assertIsNone(metadata["result_issue_url"])
                self.assertEqual(0, metadata["qualified_result_count"])
        self.assertEqual(2, self.artifact_download.call_count)

    def test_rejects_nonexact_activation_schema_and_version_derived_form(self) -> None:
        for mutation in (
            {"schemaVersion": 1},
            {"schemaVersion": 2.0},
            {"issueFormFilename": "independent-rc-install.yml"},
            {
                "issueFormPermalink": (
                    f"{self.repository_url}/blob/{self.TAG_COMMIT}/.github/"
                    "ISSUE_TEMPLATE/independent-rc-install.yml"
                )
            },
            {
                "issueFormUrl": (
                    f"{self.repository_url}/issues/new?template=independent-rc2-install.yml"
                )
            },
            {"releaseState": {"draft": 0, "immutable": 1, "prerelease": 1}},
            {"releaseState": {"draft": False, "immutable": True, "prerelease": None}},
        ):
            content = self.materialized("rc_only")
            record = self.activation_record()
            record.update(mutation)
            with self.subTest(mutation=mutation), patch.object(
                package_submission, "request_json",
                side_effect=self.fake_json(content, record=record),
            ), patch.object(
                package_submission, "request_json_list_page",
                side_effect=self.fake_pages({1: [], 2: []}),
            ), patch.object(
                package_submission, "request_bytes", return_value=self.checksum_bytes()
            ), self.assertRaisesRegex(package_submission.GateError, "exact activated RC identity"):
                package_submission.validate_public_external_evidence(
                    content, self.manifest
                )

        content = self.materialized("rc_only")
        record = self.activation_record()
        record["releaseEvidence"]["artifactFileCount"] = 17.0
        with patch.object(
            package_submission, "request_json",
            side_effect=self.fake_json(content, record=record),
        ), patch.object(
            package_submission, "request_json_list_page",
            side_effect=self.fake_pages({1: [], 2: []}),
        ), patch.object(
            package_submission, "request_bytes", return_value=self.checksum_bytes()
        ), self.assertRaisesRegex(package_submission.GateError, "exact activated RC identity"):
            package_submission.validate_public_external_evidence(content, self.manifest)

        for key, value in (
            ("releaseEvidence", ["not-an-object"]),
            ("releaseImmutability", "not-an-object"),
        ):
            record = self.activation_record()
            record[key] = value
            with self.subTest(key=key), patch.object(
                package_submission,
                "request_json",
                side_effect=self.fake_json(content, record=record),
            ), patch.object(
                package_submission,
                "request_json_list_page",
                side_effect=self.fake_pages({1: []}),
            ), patch.object(
                package_submission, "request_bytes", return_value=self.checksum_bytes()
            ), self.assertRaisesRegex(package_submission.GateError, "malformed nested"):
                package_submission.validate_public_external_evidence(
                    content, self.manifest
                )

    def test_rejects_broken_rc_run_artifact_tree_main_asset_or_checksum(self) -> None:
        content = self.materialized("rc_only")
        issue = self.eligible_issue(content)

        def wrong_tree(_url: str, value: dict) -> None:
            if value.get("sha") == self.RECORD_TREE and "tree" in value:
                value["tree"][0]["mode"] = "120000"

        def wrong_main(url: str, value: dict) -> None:
            if "/compare/" in url:
                value["merge_base_commit"]["sha"] = "8" * 40

        def missing_archived(url: str, value: dict) -> None:
            if url == self.api_base:
                value.pop("archived")

        def failed_run(url: str, value: dict) -> None:
            if url.endswith(f"/actions/runs/{self.RUN_ID}"):
                value["conclusion"] = "failure"

        def wrong_artifact(url: str, value: dict) -> None:
            if url.endswith(f"/actions/artifacts/{self.ARTIFACT_ID}"):
                value["digest"] = f"sha256:{digest('e')}"

        def mutable_release(url: str, value: dict) -> None:
            if "/releases/tags/v0.1.0-rc1" in url:
                value["immutable"] = False

        def starter_asset(url: str, value: dict) -> None:
            if "/releases/tags/v0.1.0-rc1" in url:
                value["assets"][0]["state"] = "starter"

        def missing_tagged_protocol(url: str, value: dict) -> None:
            if url.endswith(f"/git/trees/{self.TAG_TREE}?recursive=1"):
                value["tree"] = [
                    entry
                    for entry in value["tree"]
                    if entry["path"] != "docs/independent-install-study.md"
                ]

        def corrupt_form_bytes(url: str, value: dict) -> None:
            if "/contents/.github/ISSUE_TEMPLATE/independent-rc1-install.yml" in url:
                raw = (
                    b"name: Independent RC installation\n"
                    b'title: "[independent-install] "\n'
                    b"labels: [evidence, community]\n"
                    b"description: |\n"
                    b"  body: []\n"
                    b"  Issue-form source: <record issueFormPermalink>\n"
                    b"body: []\n"
                )
                value["content"] = base64.b64encode(raw).decode("ascii")
                value["size"] = len(raw)

        def post_cutoff_record_date(url: str, value: dict) -> None:
            if url.endswith(f"/commits/{self.RECORD_COMMIT}"):
                value["commit"]["committer"]["date"] = "2026-08-02T00:00:00Z"

        def post_cutoff_pull_merge(url: str, value: dict) -> None:
            if url.endswith(f"/pulls/{self.ACTIVATION_PULL_NUMBER}"):
                value["merged_at"] = "2026-08-02T00:00:00Z"

        for label, mutator in (
            ("tree", wrong_tree),
            ("main", wrong_main),
            ("repository", missing_archived),
            ("run", failed_run),
            ("artifact", wrong_artifact),
            ("release", mutable_release),
            ("asset", starter_asset),
            ("tagged-protocol", missing_tagged_protocol),
            ("form-structural-decoy", corrupt_form_bytes),
            ("record-date-after-cutoff", post_cutoff_record_date),
            ("activation-pull-after-cutoff", post_cutoff_pull_merge),
        ):
            with self.subTest(label=label), patch.object(
                package_submission, "request_json",
                side_effect=self.fake_json(content, issues=[issue], mutate=mutator),
            ), patch.object(
                package_submission, "request_json_list_page",
                side_effect=self.fake_pages({1: [issue], 2: []}),
            ), patch.object(
                package_submission, "request_bytes", return_value=self.checksum_bytes()
            ), self.assertRaises(package_submission.GateError):
                package_submission.validate_public_external_evidence(content, self.manifest)

        with patch.object(
            package_submission, "request_json",
            side_effect=self.fake_json(content, issues=[issue]),
        ), patch.object(
            package_submission, "request_json_list", return_value=[]
        ), patch.object(
            package_submission, "request_json_list_page",
            side_effect=self.fake_pages({1: [issue], 2: []}),
        ), patch.object(
            package_submission, "request_bytes", return_value=self.checksum_bytes()
        ), self.assertRaisesRegex(package_submission.GateError, "main pull request"):
            package_submission.validate_public_external_evidence(
                content, self.manifest
            )

        with patch.object(
            package_submission, "request_json",
            side_effect=self.fake_json(content, issues=[issue]),
        ), patch.object(
            package_submission, "request_json_list_page",
            side_effect=self.fake_pages({1: [issue], 2: []}),
        ), patch.object(
            package_submission, "request_bytes", return_value=b"corrupt\n"
        ), self.assertRaises(package_submission.GateError):
            package_submission.validate_public_external_evidence(content, self.manifest)

    def test_recruitment_requires_exact_owner_lines_and_final_edit_time(self) -> None:
        content = self.materialized("rc_only")
        issue = self.eligible_issue(content)

        def bot(url: str, value: dict) -> None:
            if "/issues/comments/777" in url:
                value["user"]["type"] = "Bot"

        def member(url: str, value: dict) -> None:
            if "/issues/comments/777" in url:
                value["author_association"] = "MEMBER"

        def partial_line(url: str, value: dict) -> None:
            if "/issues/comments/777" in url:
                value["body"] = value["body"].replace(
                    "ROUTECONTRACT_PUBLIC_RECRUITMENT_OPEN tag=v0.1.0-rc1",
                    "ROUTECONTRACT_PUBLIC_RECRUITMENT_OPEN tag=v0.1.0-rc1 extra",
                )

        def edited_after_cutoff(url: str, value: dict) -> None:
            if "/issues/comments/777" in url:
                value["updated_at"] = "2026-08-02T00:00:00Z"

        def hidden_comment(url: str, value: dict) -> None:
            if "/issues/comments/777" in url:
                value["body"] = f"<!--\n{value['body']}\n-->"

        def activation_time_equal(url: str, value: dict) -> None:
            if "/issues/comments/777" in url:
                value["created_at"] = "2026-07-20T04:00:00Z"

        for label, mutator in (
            ("bot", bot),
            ("association", member),
            ("partial", partial_line),
            ("updated", edited_after_cutoff),
            ("hidden-comment", hidden_comment),
            ("equal-activation-second", activation_time_equal),
        ):
            with self.subTest(label=label), patch.object(
                package_submission, "request_json",
                side_effect=self.fake_json(content, issues=[issue], mutate=mutator),
            ), patch.object(
                package_submission, "request_json_list_page",
                side_effect=self.fake_pages({1: [issue], 2: []}),
            ), patch.object(
                package_submission, "request_bytes", return_value=self.checksum_bytes()
            ), self.assertRaises(package_submission.GateError):
                package_submission.validate_public_external_evidence(content, self.manifest)

    def test_result_requires_checked_lines_user_type_exact_tag_and_cutoff(self) -> None:
        cases: list[tuple[str, str, object]] = []
        rc_content = self.materialized("rc_only")
        unchecked = self.eligible_issue(rc_content)
        required = package_submission.RESULT_ISSUE_REQUIRED_CHECKBOXES[0]
        unchecked["body"] = unchecked["body"].replace(
            f"- [x] {required}", f"- [ ] {required}"
        )
        cases.append(("unchecked", "rc_only", unchecked))

        duplicate_state = self.eligible_issue(rc_content)
        duplicate_state["body"] += f"\n- [ ] {required}"
        cases.append(("checked-and-unchecked", "rc_only", duplicate_state))

        for index, label in enumerate(
            package_submission.RESULT_ISSUE_REQUIRED_CHECKBOXES
        ):
            omitted = self.eligible_issue(rc_content, number=100 + index)
            omitted["body"] = omitted["body"].replace(f"- [x] {label}\n", "")
            cases.append((f"omitted-required-{index}", "rc_only", omitted))

        bot = self.eligible_issue(rc_content)
        bot["user"]["type"] = "Bot"
        cases.append(("bot", "rc_only", bot))

        unknown = self.eligible_issue(rc_content)
        unknown["author_association"] = "UNKNOWN"
        cases.append(("association", "rc_only", unknown))

        owner = self.eligible_issue(rc_content)
        owner["user"] = {"login": "example-owner", "type": "User"}
        owner["author_association"] = "OWNER"
        cases.append(("owner", "rc_only", owner))

        after_cutoff = self.eligible_issue(rc_content)
        after_cutoff["updated_at"] = "2026-08-02T00:00:00Z"
        cases.append(("post-cutoff", "rc_only", after_cutoff))

        equal_recruitment = self.eligible_issue(rc_content)
        equal_recruitment["created_at"] = "2026-07-21T00:05:00Z"
        cases.append(("equal-recruitment-second", "rc_only", equal_recruitment))

        inline_comment = self.eligible_issue(rc_content)
        for label in package_submission.RESULT_ISSUE_REQUIRED_CHECKBOXES:
            inline_comment["body"] = inline_comment["body"].replace(
                f"- [x] {label}", f"- [<!-- -->x] {label}"
            )
        cases.append(("inline-comment-checkbox-forgery", "rc_only", inline_comment))

        for wrapper_label, prefix, suffix in (
            ("html-comment", "<!--\n", "\n-->"),
            ("fenced-code", "```text\n", "\n```"),
            ("blockquote", "> ", ""),
            ("space-tab-indented-code", " \t", ""),
            ("nested-under-negation", "  ", ""),
        ):
            hidden = self.eligible_issue(rc_content)
            if wrapper_label == "blockquote":
                hidden["body"] = "\n".join(
                    f"> {line}" for line in hidden["body"].splitlines()
                )
            elif wrapper_label == "space-tab-indented-code":
                hidden["body"] = "\n".join(
                    f" \t{line}" for line in hidden["body"].splitlines()
                )
            elif wrapper_label == "nested-under-negation":
                hidden["body"] = "- These statements are NOT true:\n" + "\n".join(
                    f"  {line}" for line in hidden["body"].splitlines()
                )
            else:
                hidden["body"] = f"{prefix}{hidden['body']}{suffix}"
            cases.append((wrapper_label, "rc_only", hidden))

        for label, branch, issue in cases:
            content = rc_content
            with self.subTest(label=label), patch.object(
                package_submission, "request_json",
                side_effect=self.fake_json(content, issues=[issue]),
            ), patch.object(
                package_submission, "request_json_list_page",
                side_effect=self.fake_pages({1: [issue], 2: []}),
            ), patch.object(
                package_submission, "request_bytes", return_value=self.checksum_bytes()
            ), self.assertRaises(package_submission.GateError):
                package_submission.validate_public_external_evidence(content, self.manifest)

    def test_graphql_requires_exact_unedited_opener_authored_issue(self) -> None:
        content = self.materialized("rc_only")
        issue = self.eligible_issue(content)

        def mutate(path: tuple[str, ...], value) -> None:
            def apply(payload: dict) -> None:
                parent = payload
                for component in path[:-1]:
                    parent = parent[component]
                parent[path[-1]] = value

            self.graphql_mutate = apply

        cases = (
            (("data", "repository", "id"), "R_wrong"),
            (("data", "repository", "issue", "body"), "changed"),
            (("data", "repository", "issue", "title"), "changed"),
            (("data", "repository", "issue", "author", "id"), "U_wrong"),
            (("data", "repository", "issue", "author", "__typename"), "Bot"),
            (
                ("data", "repository", "issue", "editor"),
                {"__typename": "User", "login": "maintainer"},
            ),
            (("data", "repository", "issue", "lastEditedAt"), "2026-07-23T00:02:00Z"),
            (("data", "repository", "issue", "includesCreatedEdit"), True),
            (("data", "repository", "issue", "userContentEdits", "totalCount"), 1),
            (("data", "repository", "issue", "userContentEdits", "totalCount"), False),
            (("data", "repository", "issue", "timelineItems", "totalCount"), 1),
            (("data", "repository", "issue", "timelineItems", "totalCount"), False),
        )
        for path, value in cases:
            mutate(path, value)
            try:
                with self.subTest(path=path), patch.object(
                    package_submission,
                    "request_json",
                    side_effect=self.fake_json(content, issues=[issue]),
                ), patch.object(
                    package_submission,
                    "request_json_list_page",
                    side_effect=self.fake_pages({1: [issue]}),
                ), patch.object(
                    package_submission, "request_bytes", return_value=self.checksum_bytes()
                ), self.assertRaisesRegex(
                    package_submission.GateError, "edited, renamed, or not the exact"
                ):
                    package_submission.validate_public_external_evidence(
                        content, self.manifest
                    )
            finally:
                self.graphql_mutate = None

    def test_graphql_transport_rejects_duplicate_or_partial_envelopes(self) -> None:
        self.graphql_patcher.stop()
        valid = '{"data":{"repository":null}}'
        with patch.object(
            package_submission,
            "require_safe_github_cli_release_verification",
            return_value="/usr/local/bin/gh",
        ), patch.object(package_submission, "run", return_value=valid) as invoked:
            self.assertEqual(
                {"data": {"repository": None}},
                package_submission.request_graphql_issue("owner", "repo", 7),
            )
        command = invoked.call_args.args[0]
        self.assertIn("--hostname", command)
        self.assertIn("github.com", command)
        self.assertIn("number=7", command)

        for label, raw in (
            ("duplicate", '{"data":{},"data":{}}'),
            ("errors", '{"data":{},"errors":[]}'),
            ("extensions", '{"data":{},"extensions":{}}'),
            ("null-data", '{"data":null}'),
            ("array-data", '{"data":[]}'),
        ):
            with self.subTest(label=label), patch.object(
                package_submission,
                "require_safe_github_cli_release_verification",
                return_value="/usr/local/bin/gh",
            ), patch.object(
                package_submission, "run", return_value=raw
            ), self.assertRaises(package_submission.GateError):
                package_submission.request_graphql_issue("owner", "repo", 7)

    def test_zero_enumerates_and_rejects_an_eligible_result(self) -> None:
        content = self.materialized("zero")
        issue = self.eligible_issue(content)
        with patch.object(
            package_submission, "request_json",
            side_effect=self.fake_json(content, issues=[issue]),
        ), patch.object(
            package_submission, "request_json_list_page",
            side_effect=self.fake_pages({1: [issue], 2: []}),
        ), patch.object(
            package_submission, "request_bytes", return_value=self.checksum_bytes()
        ), self.assertRaisesRegex(package_submission.GateError, "qualified result count"):
            package_submission.validate_public_external_evidence(content, self.manifest)

    def test_direct_collector_rejects_boolean_or_float_result_counts(self) -> None:
        for branch, value in (("zero", False), ("rc_only", True), ("rc_only", 1.0)):
            content = self.materialized(branch)
            content["external_evidence"]["qualified_result_count"] = value
            with self.subTest(branch=branch, value=value), self.assertRaisesRegex(
                package_submission.GateError, "typed"
            ):
                package_submission.validate_public_external_evidence(
                    content, self.manifest
                )

    def test_follows_page_two_and_rejects_foreign_or_partial_pagination(self) -> None:
        content = self.materialized("rc_only")
        issue = self.eligible_issue(content)
        first_page = [self.unrelated_issue(number) for number in range(1000, 1100)]
        earliest = datetime(2026, 7, 21, 0, 5, 0, tzinfo=timezone.utc)
        initial_url = package_submission._issue_initial_url(self.api_base, earliest)
        initial_query = urllib.parse.parse_qsl(
            urllib.parse.urlparse(initial_url).query
        )
        next_url = (
            f"https://api.github.com/repositories/{self.REPOSITORY_ID}/issues?"
            + urllib.parse.urlencode(
                [
                    *initial_query,
                    ("page", "2"),
                    ("after", "opaque-cursor-token"),
                ]
            )
        )
        with patch.object(
            package_submission, "request_json",
            side_effect=self.fake_json(content, issues=[issue]),
        ), patch.object(
            package_submission, "request_json_list_page",
            side_effect=self.fake_pages(
                {1: first_page, 2: [issue]},
                {
                    1: [
                        f'<{next_url}>; rel="next"',
                        f'<{next_url}>; rel="last"',
                    ]
                },
            ),
        ) as listed, patch.object(
            package_submission, "request_bytes", return_value=self.checksum_bytes()
        ):
            metadata = package_submission.validate_public_external_evidence(
                content, self.manifest
            )
        self.assertEqual([42], metadata["enumeration_eligible_issue_numbers"])
        self.assertEqual(2, metadata["enumeration_pages"])
        self.assertEqual(
            [initial_url, next_url],
            [call.args[0] for call in listed.call_args_list],
        )
        self.assertIn(("since", "2026-07-21T00:04:59Z"), initial_query)

        with patch.object(
            package_submission, "request_json",
            side_effect=self.fake_json(content, issues=[issue]),
        ), patch.object(
            package_submission, "request_json_list_page",
            side_effect=self.fake_pages(
                {1: [], 2: [issue]},
                {1: [f'<{next_url}>; rel="next"']},
            ),
        ), patch.object(
            package_submission, "request_bytes", return_value=self.checksum_bytes()
        ):
            empty_first_page = package_submission.validate_public_external_evidence(
                content, self.manifest
            )
        self.assertEqual([42], empty_first_page["enumeration_eligible_issue_numbers"])
        self.assertEqual(2, empty_first_page["enumeration_pages"])

        for label, page, header in (
            (
                "foreign",
                first_page,
                '<https://example.invalid/issues?page=2>; rel="next"',
            ),
            ("partial", first_page, f'<{next_url}>; rel='),
        ):
            with self.subTest(label=label), patch.object(
                package_submission, "request_json",
                side_effect=self.fake_json(content, issues=[issue]),
            ), patch.object(
                package_submission, "request_json_list_page",
                side_effect=self.fake_pages(
                    {1: page, 2: [issue], 3: []}, {1: [header]}
                ),
            ), patch.object(
                package_submission, "request_bytes", return_value=self.checksum_bytes()
            ), self.assertRaises(package_submission.GateError):
                package_submission.validate_public_external_evidence(content, self.manifest)

    def test_rejects_missing_next_when_link_advertises_a_later_last_page(self) -> None:
        earliest = datetime(2026, 7, 21, 0, 5, 0, tzinfo=timezone.utc)
        initial_url = package_submission._issue_initial_url(self.api_base, earliest)
        initial_query = urllib.parse.parse_qsl(
            urllib.parse.urlparse(initial_url).query
        )
        later_url = (
            f"https://api.github.com/repositories/{self.REPOSITORY_ID}/issues?"
            + urllib.parse.urlencode([*initial_query, ("page", "2")])
        )
        for branch in ("rc_only", "zero"):
            content = self.materialized(branch)
            issue = self.eligible_issue(content)
            with self.subTest(branch=branch), patch.object(
                package_submission, "request_json",
                side_effect=self.fake_json(content, issues=[issue]),
            ), patch.object(
                package_submission, "request_json_list_page",
                return_value=([], [f'<{later_url}>; rel="last"']),
            ), patch.object(
                package_submission, "request_bytes", return_value=self.checksum_bytes()
            ), self.assertRaisesRegex(package_submission.GateError, "omits next"):
                package_submission.validate_public_external_evidence(
                    content, self.manifest
                )

    def test_rejects_next_link_that_skips_numeric_pages(self) -> None:
        content = self.materialized("zero")
        earliest = datetime(2026, 7, 21, 0, 5, 0, tzinfo=timezone.utc)
        initial_query = urllib.parse.parse_qsl(
            urllib.parse.urlparse(
                package_submission._issue_initial_url(self.api_base, earliest)
            ).query
        )
        skipped = (
            f"https://api.github.com/repositories/{self.REPOSITORY_ID}/issues?"
            + urllib.parse.urlencode([*initial_query, ("page", "999")])
        )
        with patch.object(
            package_submission, "request_json",
            side_effect=self.fake_json(content, issues=[]),
        ), patch.object(
            package_submission, "request_json_list_page",
            return_value=([], [f'<{skipped}>; rel="next"']),
        ), patch.object(
            package_submission, "request_bytes", return_value=self.checksum_bytes()
        ), self.assertRaisesRegex(package_submission.GateError, "skips a numeric page"):
            package_submission.validate_public_external_evidence(
                content, self.manifest
            )

    def test_rejects_two_eligible_results_instead_of_selecting_one(self) -> None:
        content = self.materialized("rc_only")
        first = self.eligible_issue(content, 42)
        second = self.eligible_issue(content, 43)
        with patch.object(
            package_submission, "request_json",
            side_effect=self.fake_json(content, issues=[first, second]),
        ), patch.object(
            package_submission, "request_json_list_page",
            side_effect=self.fake_pages({1: [first, second], 2: []}),
        ), patch.object(
            package_submission, "request_bytes", return_value=self.checksum_bytes()
        ), self.assertRaisesRegex(package_submission.GateError, "qualified result count"):
            package_submission.validate_public_external_evidence(content, self.manifest)

    def test_contextual_form_issues_do_not_poison_zero_or_one_qualified_result(self) -> None:
        rc_content = self.materialized("rc_only")
        eligible = self.eligible_issue(rc_content, 42)
        deviation = self.eligible_issue(rc_content, 43)
        deviation["body"] = deviation["body"].replace(
            "UNASSISTED_PASS", "PROTOCOL_DEVIATION"
        )
        with patch.object(
            package_submission, "request_json",
            side_effect=self.fake_json(rc_content, issues=[eligible, deviation]),
        ), patch.object(
            package_submission, "request_json_list_page",
            side_effect=self.fake_pages({1: [eligible, deviation], 2: []}),
        ), patch.object(
            package_submission, "request_bytes", return_value=self.checksum_bytes()
        ):
            metadata = package_submission.validate_public_external_evidence(
                rc_content, self.manifest
            )
        self.assertEqual(1, metadata["qualified_result_count"])
        self.assertEqual([42], metadata["enumeration_eligible_issue_numbers"])

        zero_content = self.materialized("zero")
        not_run = self.eligible_issue(zero_content, 44)
        not_run["body"] = not_run["body"].replace("UNASSISTED_PASS", "NOT_RUN")
        with patch.object(
            package_submission, "request_json",
            side_effect=self.fake_json(zero_content, issues=[not_run]),
        ), patch.object(
            package_submission, "request_json_list_page",
            side_effect=self.fake_pages({1: [not_run], 2: []}),
        ), patch.object(
            package_submission, "request_bytes", return_value=self.checksum_bytes()
        ):
            metadata = package_submission.validate_public_external_evidence(
                zero_content, self.manifest
            )
        self.assertEqual(0, metadata["qualified_result_count"])
        self.assertEqual([], metadata["enumeration_eligible_issue_numbers"])

    def test_transport_preserves_repeated_link_fields_and_rejects_invalid_utf8(self) -> None:
        class Headers:
            @staticmethod
            def raw_items():
                return iter((('Link', '<https://api.github.com/a>; rel=next'),
                             ('lInK', '<https://api.github.com/b>; rel="last"')))

        class Response:
            headers = Headers()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read(_limit: int | None = None) -> bytes:
                return b"[]"

        with patch.object(
            package_submission.urllib.request, "urlopen", return_value=Response()
        ), patch.object(package_submission, "verified_tls_context", return_value=None):
            data, headers = package_submission.request_bytes_with_headers(
                "https://api.github.com/example", limit=100
            )
        self.assertEqual(b"[]", data)
        self.assertEqual(
            [
                '<https://api.github.com/a>; rel=next',
                '<https://api.github.com/b>; rel="last"',
            ],
            headers["link"],
        )
        self.assertEqual(
            {"next": "https://api.github.com/a", "last": "https://api.github.com/b"},
            package_submission._parse_link_headers(headers["link"]),
        )
        with patch.object(
            package_submission,
            "request_bytes_with_headers",
            return_value=(b"\xff", {}),
        ), self.assertRaisesRegex(package_submission.GateError, "did not return JSON"):
            package_submission.request_json_list_page("https://api.github.com/example")

    def test_link_traversal_accepts_pr_only_empty_and_full_terminal_pages(self) -> None:
        content = self.materialized("zero")
        evidence = content["external_evidence"]
        earliest = datetime(2026, 7, 21, 0, 5, 0, tzinfo=timezone.utc)
        cutoff = datetime(2026, 8, 1, 6, 0, 0, tzinfo=timezone.utc)
        fixed_query = urllib.parse.parse_qsl(
            urllib.parse.urlparse(
                package_submission._issue_initial_url(self.api_base, earliest)
            ).query
        )

        def next_url(page: int) -> str:
            return (
                f"https://api.github.com/repositories/{self.REPOSITORY_ID}/issues?"
                + urllib.parse.urlencode(
                    [*fixed_query, ("page", str(page)), ("after", f"cursor-{page}")]
                )
            )

        pull_request = {
            "number": 900,
            "repository_url": self.api_base,
            "pull_request": {"url": "https://api.github.com/pulls/900"},
        }
        with patch.object(
            package_submission,
            "request_json_list_page",
            side_effect=[
                ([pull_request], [f'<{next_url(2)}>; REL=Next']),
                ([], []),
            ],
        ):
            eligible, metadata = package_submission._enumerate_result_issues(
                evidence,
                self.manifest,
                self.api_base,
                self.REPOSITORY_ID,
                self.REPOSITORY_NODE,
                earliest,
                cutoff,
                self.activation_marker(),
            )
        self.assertEqual([], eligible)
        self.assertEqual(2, metadata["enumeration_pages"])

        terminal_full_page = [
            {
                "number": number,
                "repository_url": self.api_base,
                "pull_request": {"url": f"https://api.github.com/pulls/{number}"},
            }
            for number in range(1000, 1100)
        ]
        with patch.object(
            package_submission,
            "request_json_list_page",
            return_value=(terminal_full_page, []),
        ):
            _, terminal_metadata = package_submission._enumerate_result_issues(
                evidence,
                self.manifest,
                self.api_base,
                self.REPOSITORY_ID,
                self.REPOSITORY_NODE,
                earliest,
                cutoff,
                self.activation_marker(),
            )
        self.assertEqual(1, terminal_metadata["enumeration_pages"])

    def test_exact_page_cap_accepts_terminal_and_rejects_another_next(self) -> None:
        content = self.materialized("zero")
        evidence = content["external_evidence"]
        earliest = datetime(2026, 7, 21, 0, 5, 0, tzinfo=timezone.utc)
        cutoff = datetime(2026, 8, 1, 6, 0, 0, tzinfo=timezone.utc)
        fixed_query = urllib.parse.parse_qsl(
            urllib.parse.urlparse(
                package_submission._issue_initial_url(self.api_base, earliest)
            ).query
        )

        def next_url(page: int) -> str:
            return (
                f"https://api.github.com/repositories/{self.REPOSITORY_ID}/issues?"
                + urllib.parse.urlencode(
                    [*fixed_query, ("page", str(page)), ("after", f"cursor-{page}")]
                )
            )

        def pages(*, next_after_cap: bool):
            page = 0

            def respond(_url: str):
                nonlocal page
                page += 1
                if page < package_submission.MAX_ISSUE_ENUMERATION_PAGES:
                    return [], [f'<{next_url(page + 1)}>; rel="next"']
                if next_after_cap:
                    return [], [f'<{next_url(page + 1)}>; rel="next"']
                return [], []

            return respond

        with patch.object(
            package_submission,
            "request_json_list_page",
            side_effect=pages(next_after_cap=False),
        ):
            _, metadata = package_submission._enumerate_result_issues(
                evidence,
                self.manifest,
                self.api_base,
                self.REPOSITORY_ID,
                self.REPOSITORY_NODE,
                earliest,
                cutoff,
                self.activation_marker(),
            )
        self.assertEqual(100, metadata["enumeration_pages"])

        with patch.object(
            package_submission,
            "request_json_list_page",
            side_effect=pages(next_after_cap=True),
        ), self.assertRaisesRegex(package_submission.GateError, "safety page limit"):
            package_submission._enumerate_result_issues(
                evidence,
                self.manifest,
                self.api_base,
                self.REPOSITORY_ID,
                self.REPOSITORY_NODE,
                earliest,
                cutoff,
                self.activation_marker(),
            )

    def test_rejects_malformed_foreign_duplicate_and_looping_link_targets(self) -> None:
        content = self.materialized("zero")
        evidence = content["external_evidence"]
        earliest = datetime(2026, 7, 21, 0, 5, 0, tzinfo=timezone.utc)
        cutoff = datetime(2026, 8, 1, 6, 0, 0, tzinfo=timezone.utc)
        initial = package_submission._issue_initial_url(self.api_base, earliest)
        parsed = urllib.parse.urlparse(initial)
        query = parsed.query
        invalid = (
            f"https://api.github.com/repositories/999/issues?{query}&page=2",
            f"https://api.github.com/repositories/{self.REPOSITORY_ID}/issues?"
            f"{query}&state=all&page=2",
            f"https://api.github.com/repositories/{self.REPOSITORY_ID}/issues?"
            f"{query}&after=",
            f"https://api.github.com/repositories/{self.REPOSITORY_ID}/issues?"
            f"{query}&unexpected=value",
            f"https://api.github.com/repositories/{self.REPOSITORY_ID}/issues?"
            f"{query}&page=2#fragment",
        )
        for target in invalid:
            with self.subTest(target=target), self.assertRaises(
                package_submission.GateError
            ):
                package_submission._validated_issue_operation_key(
                    target, self.api_base, self.REPOSITORY_ID, earliest
                )
        for headers in (
            [""],
            [
                f'<{initial}>; rel="next"',
                f'<{initial}>; rel=Next',
            ],
        ):
            with self.subTest(headers=headers), self.assertRaises(
                package_submission.GateError
            ):
                package_submission._parse_link_headers(headers)

        with patch.object(
            package_submission,
            "request_json_list_page",
            return_value=([], [f'<{initial}>; rel="next"']),
        ), self.assertRaisesRegex(package_submission.GateError, "loop"):
            package_submission._enumerate_result_issues(
                evidence,
                self.manifest,
                self.api_base,
                self.REPOSITORY_ID,
                self.REPOSITORY_NODE,
                earliest,
                cutoff,
                self.activation_marker(),
            )

        foreign_last = '<https://example.invalid/issues?page=9>; rel="last"'
        with patch.object(
            package_submission,
            "request_json_list_page",
            return_value=([], [foreign_last]),
        ), self.assertRaisesRegex(package_submission.GateError, "foreign"):
            package_submission._enumerate_result_issues(
                evidence,
                self.manifest,
                self.api_base,
                self.REPOSITORY_ID,
                self.REPOSITORY_NODE,
                earliest,
                cutoff,
                self.activation_marker(),
            )

        reverse_next = (
            f"https://api.github.com/repositories/{self.REPOSITORY_ID}/issues?"
            f"{query}&before=reverse-cursor"
        )
        with patch.object(
            package_submission,
            "request_json_list_page",
            return_value=([], [f'<{reverse_next}>; rel="next"']),
        ), self.assertRaisesRegex(package_submission.GateError, "reverse cursor"):
            package_submission._enumerate_result_issues(
                evidence,
                self.manifest,
                self.api_base,
                self.REPOSITORY_ID,
                self.REPOSITORY_NODE,
                earliest,
                cutoff,
                self.activation_marker(),
            )



class PublicRcWorkflowArtifactBindingTest(unittest.TestCase):
    TAG_COMMIT = "c" * 40
    RUN_ID = 11
    ARTIFACT_ID = 22

    @staticmethod
    def public_assets() -> tuple[str, ...]:
        version = "0.1.0-rc1"
        return (
            f"routecontract-{version}-source.zip",
            f"routecontract-shardingsphere-5.5-{version}.jar",
            f"routecontract-shardingsphere-5.5-{version}-sources.jar",
            f"routecontract-shardingsphere-5.5-{version}-javadoc.jar",
            "routecontract-shardingsphere-5.5.pom",
            "routecontract-shardingsphere-5.5-cyclonedx.json",
            "routecontract-shardingsphere-5.5-cyclonedx.xml",
            "routecontract-aggregate-cyclonedx.json",
            "routecontract-aggregate-cyclonedx.xml",
            "supply-chain-evidence.json",
            "test-summary.txt",
            "SHA256SUMS",
        )

    def public_payloads(self) -> dict[str, bytes]:
        return {
            name: f"release-byte::{name}\n".encode("utf-8")
            for name in self.public_assets()
            if name != package_submission.CHECKSUMS_NAME
        }

    def declared(self) -> dict[str, str]:
        return {
            name: hashlib.sha256(data).hexdigest()
            for name, data in self.public_payloads().items()
        }

    def checksum_bytes(self) -> bytes:
        return "".join(
            f"{value}  {name}\n" for name, value in sorted(self.declared().items())
        ).encode("ascii")

    def members(self) -> dict[str, bytes]:
        result = self.public_payloads()
        result[package_submission.CHECKSUMS_NAME] = self.checksum_bytes()
        result.update(
            {
                name: f"workflow-only::{name}\n".encode("utf-8")
                for name in package_submission.RC_ACTIVATION_RECORD_VALIDATOR.WORKFLOW_ONLY_FILES
            }
        )
        return result

    @staticmethod
    def write_zip(path: Path, members: dict[str, bytes]) -> None:
        with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
            for name, data in members.items():
                archive.writestr(name, data)

    def record(self, artifact_zip: Path) -> dict:
        return {
            "tag": "v0.1.0-rc1",
            "tagCommit": self.TAG_COMMIT,
            "issueFormFilename": "independent-rc1-install.yml",
            "publicAssets": list(self.public_assets()),
            "sha256sumsSha256": hashlib.sha256(self.checksum_bytes()).hexdigest(),
            "releaseEvidence": {
                "artifactDigest": f"sha256:{package_submission.sha256(artifact_zip)}",
                "artifactFileCount": 17,
                "artifactId": self.ARTIFACT_ID,
                "headSha": self.TAG_COMMIT,
                "runId": self.RUN_ID,
                "runUrl": "https://github.com/example-owner/routecontract/actions/runs/11",
            },
        }

    def test_accepts_exact_17_flat_files_and_binds_all_release_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            artifact_zip = Path(raw) / "artifact.zip"
            source_members = self.members()
            self.write_zip(artifact_zip, source_members)
            observed = package_submission.validate_public_rc_workflow_artifact_archive(
                artifact_zip,
                artifact_zip.stat().st_size,
                self.record(artifact_zip),
                self.declared(),
            )

        expected_names = set(self.public_assets()) | set(
            package_submission.RC_ACTIVATION_RECORD_VALIDATOR.WORKFLOW_ONLY_FILES
        )
        self.assertEqual(17, len(observed))
        self.assertEqual(expected_names, set(observed))
        self.assertNotIn("osv-raw.json", observed)
        for name in self.public_assets():
            self.assertEqual(
                hashlib.sha256(source_members[name]).hexdigest(), observed[name]
            )

    def test_rejects_digest_size_member_bytes_raw_osv_and_nonflat_names(self) -> None:
        mutations = {
            "release-byte-mismatch": lambda members: members.__setitem__(
                self.public_assets()[0], b"different public release bytes"
            ),
            "missing": lambda members: members.pop("environment.txt"),
            "raw-osv": lambda members: (
                members.pop("environment.txt"),
                members.__setitem__("osv-raw.json", b'{"results":[]}\n'),
            ),
            "nonflat": lambda members: (
                members.pop("environment.txt"),
                members.__setitem__("nested/environment.txt", b"unsafe\n"),
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                artifact_zip = Path(raw) / "artifact.zip"
                members = self.members()
                mutate(members)
                self.write_zip(artifact_zip, members)
                with self.assertRaises(package_submission.GateError):
                    package_submission.validate_public_rc_workflow_artifact_archive(
                        artifact_zip,
                        artifact_zip.stat().st_size,
                        self.record(artifact_zip),
                        self.declared(),
                    )

        with tempfile.TemporaryDirectory() as raw:
            artifact_zip = Path(raw) / "artifact.zip"
            self.write_zip(artifact_zip, self.members())
            record = self.record(artifact_zip)
            record["releaseEvidence"]["artifactDigest"] = f"sha256:{digest('0')}"
            with self.assertRaisesRegex(package_submission.GateError, "digest"):
                package_submission.validate_public_rc_workflow_artifact_archive(
                    artifact_zip,
                    artifact_zip.stat().st_size,
                    record,
                    self.declared(),
                )
            with self.assertRaisesRegex(package_submission.GateError, "size"):
                package_submission.validate_public_rc_workflow_artifact_archive(
                    artifact_zip,
                    artifact_zip.stat().st_size + 1,
                    self.record(artifact_zip),
                    self.declared(),
                )

    def test_rejects_a_symlink_member_even_with_the_exact_name_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            artifact_zip = Path(raw) / "artifact.zip"
            with ZipFile(artifact_zip, "w", compression=ZIP_DEFLATED) as archive:
                for name, data in self.members().items():
                    if name == "environment.txt":
                        info = ZipInfo(name)
                        info.external_attr = (
                            package_submission.stat.S_IFLNK | 0o777
                        ) << 16
                        archive.writestr(info, b"target")
                    else:
                        archive.writestr(name, data)
            with self.assertRaisesRegex(package_submission.GateError, "flat regular"):
                package_submission.validate_public_rc_workflow_artifact_archive(
                    artifact_zip,
                    artifact_zip.stat().st_size,
                    self.record(artifact_zip),
                    self.declared(),
                )

    def test_download_uses_safe_gh_exact_artifact_endpoint_and_declared_size(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            source = Path(raw) / "source.zip"
            self.write_zip(source, self.members())
            record = self.record(source)
            manifest = package_submission.validate_manifest(valid_manifest())

            def fake_download(
                gh: str,
                repository_root: Path,
                endpoint: str,
                destination: Path,
                expected_size: int,
                *,
                accept: str,
            ) -> None:
                self.assertEqual("/safe/bin/gh", gh)
                self.assertEqual(REPOSITORY_ROOT, repository_root)
                self.assertEqual(
                    "repos/example-owner/routecontract/actions/artifacts/22/zip",
                    endpoint,
                )
                self.assertEqual(source.stat().st_size, expected_size)
                self.assertEqual("application/vnd.github+json", accept)
                destination.write_bytes(source.read_bytes())

            with patch.object(
                package_submission,
                "require_safe_github_cli_release_verification",
                return_value="/safe/bin/gh",
            ), patch.object(
                package_submission.RC_ACTIVATION_RECORD_VALIDATOR,
                "_download_gh_file",
                side_effect=fake_download,
            ) as downloaded:
                observed = (
                    package_submission.download_and_validate_public_rc_workflow_artifact(
                        manifest, record, source.stat().st_size, self.declared()
                    )
                )

        self.assertEqual(1, downloaded.call_count)
        self.assertEqual(17, len(observed))


class PublicExternalSnapshotRevalidationTest(unittest.TestCase):
    @staticmethod
    def snapshot() -> dict:
        return {
            "branch": "rc_only",
            "qualified_result_count": 1,
            "result_issue_url": "https://github.com/example-owner/routecontract/issues/42",
            "result_issue_body_sha256": digest("1"),
            "result_issue_labels": ["community", "evidence"],
            "result_issue_updated_at": "2026-07-23T00:01:00+00:00",
            "recruitment_body_sha256": digest("2"),
            "activation_run": {"updated_at": "2026-07-20T01:00:00+00:00"},
            "activation_artifact_id": 2,
            "activation_artifact_digest": f"sha256:{digest('3')}",
            "activation_artifact_size_bytes": 456,
            "activation_artifact_raw_osv_absent": True,
            "activation_artifact_member_digests": {"a": digest("4")},
            "activation_artifact": {"size_in_bytes": 456},
            "activation_release": {
                "updated_at": "2026-07-20T04:00:00+00:00",
                "assets": [{"name": "a", "digest": f"sha256:{digest('4')}"}],
            },
        }

    def test_unchanged_second_observation_passes_and_reuses_artifact_binding(self) -> None:
        initial = self.snapshot()
        with patch.object(
            package_submission,
            "validate_public_external_evidence",
            return_value=deepcopy(initial),
        ) as collected:
            observed = package_submission.revalidate_public_external_evidence(
                initial, {"external_evidence": {}}, valid_manifest()
            )
        self.assertEqual(initial, observed)
        self.assertIs(initial, collected.call_args.kwargs["artifact_binding_cache"])

    def test_each_public_claim_mutation_fails_before_final_archive(self) -> None:
        mutation_paths = (
            ("result_issue_body_sha256",),
            ("result_issue_labels",),
            ("result_issue_updated_at",),
            ("recruitment_body_sha256",),
            ("activation_run", "updated_at"),
            ("activation_artifact", "size_in_bytes"),
            ("activation_release", "updated_at"),
            ("activation_release", "assets"),
        )
        for path in mutation_paths:
            initial = self.snapshot()
            changed = deepcopy(initial)
            parent = changed
            for component in path[:-1]:
                parent = parent[component]
            current = parent[path[-1]]
            parent[path[-1]] = [*current, "changed"] if isinstance(current, list) else f"{current}-changed"
            with self.subTest(path=path), patch.object(
                package_submission,
                "validate_public_external_evidence",
                return_value=changed,
            ), self.assertRaisesRegex(
                package_submission.GateError, "changed between packaging observations"
            ):
                package_submission.revalidate_public_external_evidence(
                    initial, {"external_evidence": {}}, valid_manifest()
                )

        source = (REPOSITORY_ROOT / "submission" / "tools" / "package_submission.py").read_text(
            encoding="utf-8"
        )
        main_source = source[source.index("def main()") :]
        public_requery = main_source.index("revalidate_public_evidence(")
        external_requery = main_source.index("revalidate_public_external_evidence(")
        archive = main_source.index("build_upload_zip(")
        publish = main_source.index("os.replace(staging, output)")
        self.assertLess(public_requery, external_requery)
        self.assertLess(external_requery, archive)
        self.assertLess(archive, publish)

    def test_complete_release_ci_video_snapshot_is_recollected_exactly(self) -> None:
        initial = {
            "repository_full_name": "example-owner/routecontract",
            "commit": "a" * 40,
            "ci_run_id": 11,
            "ci_conclusion": "success",
            "workflow_artifact_id": 22,
            "workflow_artifact_sha256": digest("3"),
            "release_id": 33,
            "release_tag": "v0.1.0",
            "release_immutable": True,
            "youtube_video_id": "video",
            "youtube_title": "title",
            "youtube_duration_seconds": 172.0,
            "youtube_availability": "public",
            "youtube_live_status": "not_live",
            "youtube_age_limit": 0,
            "youtube_max_video_height": 1080,
        }
        arguments = (
            valid_manifest(),
            {"duration_seconds": 172.0},
            {"public_release_assets": {}},
            Path("evidence"),
            REPOSITORY_ROOT,
        )
        with patch.object(
            package_submission, "validate_public_evidence", return_value=deepcopy(initial)
        ) as collected:
            self.assertEqual(
                initial,
                package_submission.revalidate_public_evidence(initial, *arguments),
            )
        collected.assert_called_once_with(*arguments)

        for key in (
            "commit",
            "ci_conclusion",
            "workflow_artifact_sha256",
            "release_immutable",
            "youtube_availability",
            "youtube_duration_seconds",
        ):
            changed = deepcopy(initial)
            changed[key] = f"changed-{key}"
            with self.subTest(key=key), patch.object(
                package_submission, "validate_public_evidence", return_value=changed
            ), self.assertRaisesRegex(
                package_submission.GateError,
                "release/CI/video state changed between packaging observations",
            ):
                package_submission.revalidate_public_evidence(initial, *arguments)

    def test_public_collector_direct_call_fail_closes_stable_branch(self) -> None:
        with patch.object(package_submission, "request_json") as requested, self.assertRaisesRegex(
            package_submission.GateError, "supports only rc_only or zero"
        ):
            package_submission.validate_public_external_evidence(
                valid_report_content("final_stable"), valid_manifest()
            )
        requested.assert_not_called()


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

    def test_report_free_text_attestation_requires_literal_true(self) -> None:
        key = "report_free_text_contains_no_external_evidence_claims"
        for value in (False, 1, "true", None):
            manifest = valid_manifest()
            manifest["participant_attestations"][key] = value
            with self.subTest(value=value), self.assertRaisesRegex(
                package_submission.GateError, key
            ):
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

    def test_rejects_normalized_gps_and_quicktime_location_namespace_tags(self) -> None:
        for tag in (
            " GPSCOORDINATES ",
            " com.apple.quicktime.location.name ",
            "COM.APPLE.QUICKTIME.LOCATION.BODY",
            "com.apple.quicktime.location.role",
        ):
            payload = valid_ffprobe_video()
            payload["format"]["tags"][tag] = "private location fixture"
            with self.subTest(tag=tag), self.assertRaisesRegex(
                package_submission.GateError, "sensitive metadata tag"
            ):
                self.probe(payload)

    def test_does_not_broadly_reject_non_location_namespace_tag_names(self) -> None:
        payload = valid_ffprobe_video()
        payload["format"]["tags"].update(
            {
                "application_name": "RouteContract",
                "encoder_location_hint": "portable encoder fixture",
                "com.apple.quicktime.displayname": "RouteContract demo",
            }
        )

        result = self.probe(payload)

        self.assertEqual(8, result["metadata_tag_count"])

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

    def test_direct_report_validator_rejects_unsupported_final_stable_branch(self) -> None:
        with self.assertRaisesRegex(
            package_submission.GateError, "only rc_only or zero"
        ):
            package_submission.validate_report(
                Path("unsupported.docx"),
                Path("unsupported.pdf"),
                valid_report_content("final_stable"),
                valid_manifest(),
            )

    @staticmethod
    def visible_binding_fixture(content: dict) -> tuple[str, str]:
        metadata_values = set(content["metadata"].values())
        captions = [
            asset["caption"] for asset in content["assets"].values()
        ]
        caption_values = set(captions)
        sbom_values = {
            value
            for row in content["sbom"]
            for value in row.values()
        }
        ordinary = [
            value
            for value in package_submission.visible_report_values(content)
            if value not in sbom_values
            and value not in metadata_values
            and value not in caption_values
        ]
        metadata_rows = [
            f"팀명 {content['metadata']['team_name']}",
            f"팀인원 {content['metadata']['team_size']}",
            f"참가부문 {content['metadata']['division']}",
            f"과제유형 {content['metadata']['task_type']}",
            f"프로젝트명 {content['metadata']['project_name']}",
            f"프로젝트등록 {content['metadata']['repository_url']}",
            f"시연영상 {content['metadata']['video_url']}",
        ]
        pdf_metadata_rows = [
            f"팀명 {content['metadata']['team_name']} 팀인원 {content['metadata']['team_size']}",
            f"참가부문 {content['metadata']['division']} 과제유형 {content['metadata']['task_type']}",
            f"프로젝트명 {content['metadata']['project_name']}",
            f"프로젝트등록 {content['metadata']['repository_url']}",
            f"시연영상 {content['metadata']['video_url']}",
        ]
        title = "붙임1 SBOM(소프트웨어 자재명세서)"
        header = (
            f"{'번호':<8}{'라이브러리명':<36}{'버전':<24}{'라이선스':<20}"
            "공식 저장소 URL(GitHub 등) 사용 목적 및 주요 기능"
        )
        rows = [
            (
                f"{index:<8}{row['name']:<36}{row['version']:<24}"
                f"{row['license']:<20}{row['url']} {row['purpose']}"
            )
            for index, row in enumerate(content["sbom"], start=1)
        ]
        # Both strings have the exact same visible characters.  Only whitespace
        # and, in individual tests, bounded table-cell interleaving may differ.
        docx_text = "\n".join(
            [*metadata_rows, *captions, *ordinary, title, header, *rows]
        )
        pdf_text = "\n".join(
            [*pdf_metadata_rows, *captions, *ordinary, title, header, *rows]
        )
        return docx_text, pdf_text

    @staticmethod
    def write_docx(path: Path, body_xml: str) -> None:
        document = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main">'
            f"<w:body>{body_xml}</w:body></w:document>"
        )
        content_types = (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.document.main+xml"/>'
            "</Types>"
        )
        with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("word/document.xml", document)

    def test_docx_extractor_keeps_adjacent_runs_contiguous(self) -> None:
        prefix, _ = self.BASE.split("SBOM(", 1)
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "split.docx"
            self.write_docx(
                path,
                "<w:p>"
                f'<w:r><w:t xml:space="preserve">{prefix}</w:t></w:r>'
                "<w:r><w:t>SBOM(소프트웨어 자재명세서</w:t></w:r>"
                "<w:r><w:t>)</w:t></w:r>"
                "</w:p>",
            )
            extracted = package_submission.extract_docx_text(path)
            self.assertEqual(self.BASE, extracted)
            package_submission.validate_report_text_contract(extracted, self.BASE)

    def test_docx_run_split_cannot_hide_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "placeholder.docx"
            self.write_docx(
                path,
                "<w:p><w:r><w:t>"
                f"{self.BASE}"
                "</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>[[OWNER_</w:t></w:r>"
                "<w:r><w:t>VOICE]]</w:t></w:r></w:p>",
            )
            extracted = package_submission.extract_docx_text(path)
            self.assertIn("[[OWNER_VOICE]]", extracted)
            with self.assertRaisesRegex(package_submission.GateError, "unresolved gates"):
                package_submission.validate_report_text_contract(extracted, self.BASE)

    def test_docx_extractor_preserves_only_explicit_separators(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "separators.docx"
            self.write_docx(
                path,
                '<w:p><w:r><w:t xml:space="preserve">A</w:t><w:tab/>'
                "<w:t>B</w:t><w:br/><w:t>C</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>D</w:t></w:r></w:p>",
            )
            self.assertEqual(
                "A\tB\nC\nD", package_submission.extract_docx_text(path)
            )

    def test_accepts_sbom_and_development_ai_without_attachment_2(self) -> None:
        package_submission.validate_report_text_contract(self.BASE, self.BASE)

    def test_visible_binding_accepts_official_table_extraction_reordering(self) -> None:
        content = package_submission.validate_and_materialize_report_content(
            valid_report_content("rc_only"),
            package_submission.validate_manifest(valid_manifest()),
            current_utc=TEST_CURRENT_UTC,
        )
        docx_text, pdf_text = self.visible_binding_fixture(content)
        package_submission.validate_report_visible_content(
            docx_text, pdf_text, content
        )

    def test_visible_binding_rejects_pdf_cell_deletion_or_substitution(self) -> None:
        content = package_submission.validate_and_materialize_report_content(
            valid_report_content("rc_only"),
            package_submission.validate_manifest(valid_manifest()),
            current_utc=TEST_CURRENT_UTC,
        )
        text, _ = self.visible_binding_fixture(content)
        for label, mutated in (
            ("deletion", text.replace("Java 17", "Java 1", 1)),
            ("substitution", text.replace("Java 17", "Java X7", 1)),
        ):
            with self.subTest(label=label), self.assertRaisesRegex(
                package_submission.GateError, "visible-text inventory"
            ):
                package_submission.validate_report_visible_content(
                    text, mutated, content
                )

    def test_visible_binding_requires_exact_external_summary_in_pdf(self) -> None:
        content = package_submission.validate_and_materialize_report_content(
            valid_report_content("rc_only"),
            package_submission.validate_manifest(valid_manifest()),
            current_utc=TEST_CURRENT_UTC,
        )
        text, _ = self.visible_binding_fixture(content)
        summary = package_submission.external_evidence_summary(content)
        same_inventory_without_sentence = text.replace(summary, summary[::-1], 1)
        with self.assertRaisesRegex(
            package_submission.GateError, "external-evidence summary"
        ):
            package_submission.validate_report_visible_content(
                text, same_inventory_without_sentence, content
            )

    def test_visible_binding_rejects_same_inventory_semantic_reordering(self) -> None:
        content = package_submission.validate_and_materialize_report_content(
            valid_report_content("rc_only"),
            package_submission.validate_manifest(valid_manifest()),
            current_utc=TEST_CURRENT_UTC,
        )
        text, _ = self.visible_binding_fixture(content)
        target = content["background"][0]["text"]
        mutated = text.replace(target, target[::-1], 1)
        with self.assertRaisesRegex(
            package_submission.GateError, "ordered semantic text|lead-to-text row order"
        ):
            package_submission.validate_report_visible_content(text, mutated, content)

    def test_visible_binding_rejects_sbom_version_swap(self) -> None:
        content = package_submission.validate_and_materialize_report_content(
            valid_report_content("rc_only"),
            package_submission.validate_manifest(valid_manifest()),
            current_utc=TEST_CURRENT_UTC,
        )
        docx_text, pdf_text = self.visible_binding_fixture(content)
        first = content["sbom"][0]["version"]
        second = content["sbom"][1]["version"]
        first_row = next(
            line for line in pdf_text.splitlines() if re.match(r"^\s*1\s+", line)
        )
        second_row = next(
            line for line in pdf_text.splitlines() if re.match(r"^\s*2\s+", line)
        )
        pdf_text = pdf_text.replace(first_row, first_row.replace(first, second), 1)
        pdf_text = pdf_text.replace(second_row, second_row.replace(second, first), 1)
        with self.assertRaisesRegex(package_submission.GateError, "SBOM row"):
            package_submission.validate_report_visible_content(
                docx_text, pdf_text, content
            )

    def test_visible_binding_rejects_wrapped_midpoint_version_swap(self) -> None:
        content = package_submission.validate_and_materialize_report_content(
            valid_report_content("rc_only"),
            package_submission.validate_manifest(valid_manifest()),
            current_utc=TEST_CURRENT_UTC,
        )
        docx_text, pdf_text = self.visible_binding_fixture(content)
        rows = content["sbom"][:2]
        original_lines = [
            line
            for line in pdf_text.splitlines()
            if re.match(r"^\s*[12]\s+", line)
        ]
        first, second = rows
        wrapped = "\n".join(
            (
                f"{1:<8}{first['name']:<36}",
                f"{'':<44}{first['version']:<24}{first['license']:<20}"
                f"{first['url']} {first['purpose']}",
                f"{'':<44}{second['version']:<24}{second['license']:<20}"
                f"{second['url']} {second['purpose']}",
                f"{2:<8}{second['name']:<36}",
            )
        )
        pdf_text = pdf_text.replace("\n".join(original_lines), wrapped, 1)
        package_submission.validate_report_visible_content(
            docx_text, pdf_text, content
        )
        swapped_wrapped = wrapped.replace(first["version"], "[[VERSION]]", 1)
        swapped_wrapped = swapped_wrapped.replace(
            second["version"], first["version"], 1
        )
        swapped_wrapped = swapped_wrapped.replace(
            "[[VERSION]]", second["version"], 1
        )
        swapped = pdf_text.replace(wrapped, swapped_wrapped, 1)
        with self.assertRaisesRegex(
            package_submission.GateError, "version token is associated with another numbered row"
        ):
            package_submission.validate_report_visible_content(
                docx_text, swapped, content
            )

    def test_sbom_composite_version_cannot_straddle_neighbor_rows(self) -> None:
        rows = [
            {"name": "Alpha", "version": "1.0", "license": "MIT", "url": "u1", "purpose": "p1"},
            {"name": "Beta", "version": "2.0 / 2.1", "license": "MIT", "url": "u2", "purpose": "p2"},
            {"name": "Gamma", "version": "3.0", "license": "MIT", "url": "u3", "purpose": "p3"},
        ]
        header = (
            f"{'번호':<8}{'라이브러리명':<36}{'버전':<24}{'라이선스':<20}"
            "공식 저장소 URL(GitHub 등) 사용 목적 및 주요 기능"
        )
        text = "\n".join(
            (
                "붙임1 SBOM(소프트웨어 자재명세서)",
                header,
                f"{1:<8}{'Alpha':<36}{'1.0':<24}{'MIT':<20}u1 p1",
                f"{'':<44}{'2.0':<24}",
                "shared wrapped cells",
                f"{2:<8}{'Beta':<36}{'':<24}{'MIT':<20}u2 p2",
                "shared wrapped cells",
                f"{'':<44}{'2.1':<24}",
                f"{3:<8}{'Gamma':<36}{'3.0':<24}{'MIT':<20}u3 p3",
            )
        )
        with self.assertRaisesRegex(
            package_submission.GateError,
            "version token is associated with another numbered row",
        ):
            package_submission.validate_pdf_sbom_row_binding(text, rows)

    def test_sbom_accepts_junit_composite_version_split_around_own_row(self) -> None:
        rows = [
            {"name": "Alpha", "version": "1.0", "license": "MIT", "url": "u1", "purpose": "p1"},
            {
                "name": "JUnit Jupiter/Launcher",
                "version": "5.14.3 / 1.14.3",
                "license": "EPL-2.0",
                "url": "u2",
                "purpose": "p2",
            },
            {"name": "Gamma", "version": "3.0", "license": "MIT", "url": "u3", "purpose": "p3"},
        ]
        header = (
            f"{'번호':<8}{'라이브러리명':<36}{'버전':<24}{'라이선스':<20}"
            "공식 저장소 URL(GitHub 등) 사용 목적 및 주요 기능"
        )
        text = "\n".join(
            (
                "붙임1 SBOM(소프트웨어 자재명세서)",
                header,
                f"{1:<8}{'Alpha':<36}{'1.0':<24}{'MIT':<20}u1 p1",
                "",
                f"{'':<44}{'5.14.3 /':<24}",
                f"{2:<8}{'JUnit Jupiter/Launcher':<36}{'':<24}{'EPL-2.0':<20}u2 p2",
                f"{'':<44}{'1.14.3':<24}",
                "",
                f"{3:<8}{'Gamma':<36}{'3.0':<24}{'MIT':<20}u3 p3",
            )
        )
        package_submission.validate_pdf_sbom_row_binding(text, rows)

    def test_sbom_rejects_composite_token_tied_between_numbered_rows(self) -> None:
        rows = [
            {"name": "Alpha", "version": "1.0", "license": "MIT", "url": "u1", "purpose": "p1"},
            {
                "name": "Beta",
                "version": "2.0 / 2.1",
                "license": "MIT",
                "url": "u2",
                "purpose": "p2",
            },
            {"name": "Gamma", "version": "3.0", "license": "MIT", "url": "u3", "purpose": "p3"},
        ]
        header = (
            f"{'번호':<8}{'라이브러리명':<36}{'버전':<24}{'라이선스':<20}"
            "공식 저장소 URL(GitHub 등) 사용 목적 및 주요 기능"
        )
        text = "\n".join(
            (
                "붙임1 SBOM(소프트웨어 자재명세서)",
                header,
                f"{1:<8}{'Alpha':<36}{'1.0':<24}{'MIT':<20}u1 p1",
                "",
                f"{'':<44}{'2.0':<24}",
                "",
                f"{2:<8}{'Beta':<36}{'2.1':<24}{'MIT':<20}u2 p2",
                "",
                "",
                "",
                f"{3:<8}{'Gamma':<36}{'3.0':<24}{'MIT':<20}u3 p3",
            )
        )
        with self.assertRaisesRegex(
            package_submission.GateError,
            "version token is associated with another numbered row",
        ):
            package_submission.validate_pdf_sbom_row_binding(text, rows)

    def test_visible_binding_rejects_metadata_value_swap(self) -> None:
        content = package_submission.validate_and_materialize_report_content(
            valid_report_content("rc_only"),
            package_submission.validate_manifest(valid_manifest()),
            current_utc=TEST_CURRENT_UTC,
        )
        docx_text, pdf_text = self.visible_binding_fixture(content)
        team = content["metadata"]["team_name"]
        project = content["metadata"]["project_name"]
        pdf_text = pdf_text.replace(team, "[[IDENTITY]]", 1)
        pdf_text = pdf_text.replace(project, team, 1).replace(
            "[[IDENTITY]]", project, 1
        )
        with self.assertRaisesRegex(package_submission.GateError, "metadata label"):
            package_submission.validate_report_visible_content(
                docx_text, pdf_text, content
            )

    def test_visible_binding_rejects_figure_caption_swap(self) -> None:
        content = package_submission.validate_and_materialize_report_content(
            valid_report_content("rc_only"),
            package_submission.validate_manifest(valid_manifest()),
            current_utc=TEST_CURRENT_UTC,
        )
        docx_text, pdf_text = self.visible_binding_fixture(content)
        captions = [asset["caption"] for asset in content["assets"].values()]
        pdf_text = pdf_text.replace(captions[0], "[[CAPTION]]", 1)
        pdf_text = pdf_text.replace(captions[1], captions[0], 1).replace(
            "[[CAPTION]]", captions[1], 1
        )
        with self.assertRaisesRegex(package_submission.GateError, "caption order"):
            package_submission.validate_report_visible_content(
                docx_text, pdf_text, content
            )

    def test_minimum_subsequence_extra_characters_preserves_order(self) -> None:
        self.assertEqual(
            2,
            package_submission.minimum_subsequence_extra_characters("aXbYc", "abc"),
        )
        self.assertIsNone(
            package_submission.minimum_subsequence_extra_characters("cba", "abc")
        )

    def test_report_hyperlink_allowlist_comes_only_from_structured_fields(self) -> None:
        manifest = package_submission.validate_manifest(valid_manifest())
        content = package_submission.validate_and_materialize_report_content(
            valid_report_content("rc_only"),
            manifest,
            current_utc=TEST_CURRENT_UTC,
        )
        expected = {
            content["metadata"]["repository_url"],
            content["metadata"]["video_url"],
            manifest["project"]["ci_run_url"],
            manifest["project"]["release_url"],
            content["external_evidence"]["activation_record_url"],
            content["external_evidence"]["recruitment_record_url"],
            content["external_evidence"]["protocol_issue_url"],
            content["external_evidence"]["result_issue_url"],
            package_submission.UPSTREAM_ISSUE_38456_URL,
            *(row["url"] for row in content["sbom"]),
        }
        self.assertEqual(
            expected,
            package_submission.expected_report_hyperlink_targets(content, manifest),
        )
        content["other"][-1]["text"] += " https://evil.example/phish."
        self.assertEqual(
            expected,
            package_submission.expected_report_hyperlink_targets(content, manifest),
        )

    def test_pdf_raster_binding_accepts_only_identical_page_pixels(self) -> None:
        docx = Path("canonical.docx")
        pdf = Path("supplied.pdf")
        with patch.object(
            package_submission,
            "export_canonical_report_pdf",
            return_value=Path("canonical.pdf"),
        ), patch.object(
            package_submission,
            "rasterize_pdf_pages",
            side_effect=(
                [b"page-1", b"page-2"],
                [b"page-1", b"page-2"],
                [b"page-1", b"page-2"],
            ),
        ), patch.object(
            package_submission,
            "extract_pdf_pages",
            side_effect=(
                (["canonical-1", "canonical-2"], []),
                (["canonical-1", "canonical-2"], []),
                (["canonical-1", "canonical-2"], []),
            ),
        ), patch.object(
            package_submission,
            "pdf_hyperlink_fragments",
            side_effect=(
                [(1, 10, 10, 20, 10, "https://example.test/evidence", "evidence")],
                [(1, 10, 10, 20, 10, "https://example.test/evidence", "evidence")],
                [(1, 10, 10, 20, 10, "https://example.test/evidence", "evidence")],
            ),
        ), patch.object(
            package_submission,
            "pdf_hyperlink_rows",
            side_effect=(
                [(1, "https://example.test/evidence")],
                [(1, "https://example.test/evidence")],
                [(1, "https://example.test/evidence")],
            ),
        ) as rasterized:
            package_submission.validate_pdf_raster_matches_docx(docx, pdf)
        self.assertEqual(3, rasterized.call_count)

        with patch.object(
            package_submission,
            "export_canonical_report_pdf",
            return_value=Path("canonical.pdf"),
        ), patch.object(
            package_submission,
            "rasterize_pdf_pages",
            side_effect=([b"visible"], [b"visible"], [b"all-white-mask"]),
        ), self.assertRaisesRegex(package_submission.GateError, "visual raster differs"):
            package_submission.validate_pdf_raster_matches_docx(docx, pdf)

    def test_pdf_raster_binding_rejects_same_pixels_with_alternate_text(self) -> None:
        with patch.object(
            package_submission,
            "export_canonical_report_pdf",
            return_value=Path("canonical.pdf"),
        ), patch.object(
            package_submission,
            "rasterize_pdf_pages",
            side_effect=([b"same-pixels"], [b"same-pixels"], [b"same-pixels"]),
        ), patch.object(
            package_submission,
            "extract_pdf_pages",
            side_effect=(
                (["ShardingSphere 5.5.3 Apache-2.0"], []),
                (["ShardingSphere 5.5.3 Apache-2.0"], []),
                (["ShardingSphere 5.5.3.0 Apache-2"], []),
            ),
        ), self.assertRaisesRegex(package_submission.GateError, "text layer differs"):
            package_submission.validate_pdf_raster_matches_docx(
                Path("canonical.docx"), Path("actualtext.pdf")
            )

    def test_pdf_raster_binding_rejects_link_annotation_drift(self) -> None:
        with patch.object(
            package_submission,
            "export_canonical_report_pdf",
            return_value=Path("canonical.pdf"),
        ), patch.object(
            package_submission,
            "rasterize_pdf_pages",
            side_effect=([b"same"], [b"same"], [b"same"]),
        ), patch.object(
            package_submission,
            "extract_pdf_pages",
            side_effect=((['same'], []), (['same'], []), (['same'], [])),
        ), patch.object(
            package_submission,
            "pdf_hyperlink_fragments",
            side_effect=(
                [(1, 10, 10, 20, 10, "https://example.test/reviewed", "reviewed")],
                [(1, 10, 10, 20, 10, "https://example.test/reviewed", "reviewed")],
                [(1, 10, 10, 20, 10, "https://evil.example/substituted", "reviewed")],
            ),
        ), patch.object(
            package_submission,
            "pdf_hyperlink_rows",
            side_effect=(
                [(1, "https://example.test/reviewed")],
                [(1, "https://example.test/reviewed")],
                [(1, "https://evil.example/substituted")],
            ),
        ), self.assertRaisesRegex(package_submission.GateError, "positioned links differ"):
            package_submission.validate_pdf_raster_matches_docx(
                Path("canonical.docx"), Path("links.pdf")
            )

    def test_pdf_raster_binding_rejects_page_count_drift(self) -> None:
        with patch.object(
            package_submission,
            "export_canonical_report_pdf",
            return_value=Path("canonical.pdf"),
        ), patch.object(
            package_submission,
            "rasterize_pdf_pages",
            side_effect=([b"one"], [b"one"], [b"one", b"two"]),
        ), self.assertRaisesRegex(package_submission.GateError, "page count"):
            package_submission.validate_pdf_raster_matches_docx(
                Path("canonical.docx"), Path("supplied.pdf")
            )

    def test_pdf_raster_binding_rejects_nondeterministic_canonical_exports(self) -> None:
        with patch.object(
            package_submission,
            "export_canonical_report_pdf",
            side_effect=(Path("first.pdf"), Path("second.pdf")),
        ), patch.object(
            package_submission,
            "rasterize_pdf_pages",
            side_effect=([b"first"], [b"second"], [b"first"]),
        ), self.assertRaisesRegex(package_submission.GateError, "two isolated canonical"):
            package_submission.validate_pdf_raster_matches_docx(
                Path("canonical.docx"), Path("supplied.pdf")
            )

    def test_rasterizer_rejects_unbounded_page_count_before_pdftoppm(self) -> None:
        with patch.object(
            package_submission.shutil, "which", side_effect=lambda name: f"/safe/{name}"
        ), patch.object(
            package_submission, "run", return_value="Pages:          8\n"
        ) as invoked, self.assertRaisesRegex(
            package_submission.GateError, "page count exceeds"
        ):
            package_submission.rasterize_pdf_pages(
                Path("oversized.pdf"), Path("pages"), "supplied report PDF"
            )
        invoked.assert_called_once_with(["/safe/pdfinfo", "oversized.pdf"])

    def test_rasterizer_rejects_unsafe_page_box_before_pdftoppm(self) -> None:
        with patch.object(
            package_submission.shutil, "which", side_effect=lambda name: f"/safe/{name}"
        ), patch.object(
            package_submission,
            "run",
            side_effect=(
                "Pages:          1\n",
                "Page 1 size: 99999 x 99999 pts\n",
            ),
        ) as invoked, self.assertRaisesRegex(
            package_submission.GateError, "unsafe PDF page box"
        ):
            package_submission.rasterize_pdf_pages(
                Path("oversized-box.pdf"), Path("pages"), "supplied report PDF"
            )
        self.assertEqual(2, invoked.call_count)
        self.assertEqual(
            [
                call(["/safe/pdfinfo", "oversized-box.pdf"]),
                call(
                    [
                        "/safe/pdfinfo",
                        "-f",
                        "1",
                        "-l",
                        "1",
                        "-box",
                        "oversized-box.pdf",
                    ]
                ),
            ],
            invoked.call_args_list,
        )

    def test_canonical_export_rejects_unreviewed_font_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            config = root / "fonts.conf"
            config.write_text("<fontconfig/>", encoding="utf-8")
            with patch.dict(os.environ, {"FONTCONFIG_FILE": str(config)}), patch.object(
                package_submission, "require_libreoffice_writer", return_value="/safe/soffice"
            ), self.assertRaisesRegex(
                package_submission.GateError, "reviewed report font configuration"
            ):
                package_submission.export_canonical_report_pdf(
                    root / "report.docx", root / "export"
                )

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

    def test_mysql_container_row_requires_unresolved_manual_review(self) -> None:
        content_path = SCRIPT.parents[1] / "report-content.ko.json"
        with content_path.open(encoding="utf-8") as stream:
            content = json.load(stream)
        row = next(
            item for item in content["sbom"] if item["name"] == "MySQL Server 컨테이너"
        )

        self.assertEqual("8.4.11", row["version"])
        self.assertEqual(
            "Image-wide conclusion not asserted; manual review required",
            row["license"],
        )
        self.assertEqual(
            "https://dev.mysql.com/doc/refman/8.4/en/preface.html", row["url"]
        )
        self.assertIn("Testcontainers 별도 프로세스", row["purpose"])
        self.assertIn("JAR 미포함", row["purpose"])
        self.assertIn("Oracle Linux·MySQL Server/Shell", row["purpose"])
        self.assertIn("b3b90af2...857fd3fb", row["purpose"])

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
        "routecontract-mysql-example-cyclonedx.json",
        "routecontract-mysql-example-cyclonedx.xml",
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
        repository_root = root.parent
        security = repository_root / "security"
        security.mkdir()
        module = repository_root / "routecontract-shardingsphere-5.5"
        module.mkdir()
        (module / "gradle.lockfile").write_text(
            "example:runtime:1.0=runtimeClasspath\n", encoding="utf-8"
        )
        scanner_lock = {
            "database": {
                "ecosystem": "Maven",
                "generation": "1",
                "lastModified": "2026-08-09T03:03:50.782Z",
                "sha256": digest("b"),
                "size": 10,
                "url": "https://example.invalid/Maven/all.zip?generation=1",
            },
            "scanner": {
                "commit": "c" * 40,
                "name": "OSV-Scanner",
                "platforms": {
                    "linux-x86_64": {
                        "sha256": digest("d"),
                        "size": 10,
                        "url": "https://example.invalid/osv-scanner",
                    }
                },
                "scalibrVersion": "0.4.5",
                "version": "2.5.0",
            },
            "schemaVersion": 1,
        }
        (security / "osv-scanner.lock.json").write_text(
            json.dumps(scanner_lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (security / "osv-scanner.toml").write_bytes(b"")
        license_reviews = valid_license_reviews()
        vulnerability_exceptions = valid_vulnerability_exceptions()
        policy = {
            "allowedLicenseIds": ["Apache-2.0"],
            "licenseExceptions": [],
            "licenseReviewExceptions": license_reviews,
            "schemaVersion": 3,
            "vulnerabilityExceptions": vulnerability_exceptions,
        }
        (security / "supply-chain-policy.json").write_text(
            json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
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
            "routecontract-mysql-example-cyclonedx.json": "{}\n",
            "routecontract-mysql-example-cyclonedx.xml": "<bom/>\n",
            "routecontract-shardingsphere-5.5-0.1.0.jar": "main\n",
            "routecontract-shardingsphere-5.5-0.1.0-sources.jar": "sources\n",
            "routecontract-shardingsphere-5.5-0.1.0-javadoc.jar": "javadoc\n",
        }
        for name, content in files.items():
            (root / name).write_text(content, encoding="utf-8")
        supply_chain = {
            "exampleProfile": {
                "componentLicenseCount": 2,
                "mavenPackageCount": 2,
                "resolvedProfileSha256": digest("1"),
                "sbomSha256": package_submission.sha256(
                    root / "routecontract-mysql-example-cyclonedx.json"
                ),
                "xmlComponentCount": 2,
                "xmlSha256": package_submission.sha256(
                    root / "routecontract-mysql-example-cyclonedx.xml"
                ),
            },
            "publishedModule": {
                "componentLicenseCount": 2,
                "dependencyLockSha256": package_submission.sha256(
                    module / "gradle.lockfile"
                ),
                "mavenPackageCount": 2,
                "pomDependencyCount": 1,
                "pomSha256": package_submission.sha256(
                    root / "routecontract-shardingsphere-5.5.pom"
                ),
                "resolvedProfileSha256": digest("4"),
                "runtimeClosureCount": 1,
                "runtimeClosureSha256": digest("5"),
                "sbomSha256": package_submission.sha256(
                    root / "routecontract-shardingsphere-5.5-cyclonedx.json"
                ),
                "xmlComponentCount": 2,
                "xmlSha256": package_submission.sha256(
                    root / "routecontract-shardingsphere-5.5-cyclonedx.xml"
                ),
            },
            "revision": manifest["project"]["commit"],
            "sbom": {
                "componentLicenseCount": 4,
                "inventorySha256": digest("6"),
                "licensePolicy": "passed",
                "licenseReviews": license_reviews,
                "mavenPackageCount": 4,
                "policySha256": package_submission.sha256(
                    security / "supply-chain-policy.json"
                ),
                "sha256": package_submission.sha256(
                    root / "routecontract-aggregate-cyclonedx.json"
                ),
                "unresolvedLicenseReviewCount": 2,
                "xmlComponentCount": 4,
                "xmlSha256": package_submission.sha256(
                    root / "routecontract-aggregate-cyclonedx.xml"
                ),
            },
            "scanner": {
                "binarySha256": scanner_lock["scanner"]["platforms"]["linux-x86_64"]["sha256"],
                "binarySize": 10,
                "binaryUrl": "https://example.invalid/osv-scanner",
                "commit": "c" * 40,
                "database": scanner_lock["database"],
                "name": "OSV-Scanner",
                "platform": "linux-x86_64",
                "scalibrVersion": "0.4.5",
                "scannerConfigSha256": hashlib.sha256(b"").hexdigest(),
                "scannerLockSha256": package_submission.sha256(
                    security / "osv-scanner.lock.json"
                ),
                "version": "2.5.0",
            },
            "schemaVersion": 1,
            "sourceTree": "e" * 40,
            "vulnerabilities": {
                "acceptedExceptionCount": 3,
                "findingCount": 3,
                "findings": findings_for(vulnerability_exceptions),
                "unreviewedCount": 0,
            },
        }
        (root / "supply-chain-evidence.json").write_text(
            json.dumps(supply_chain, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
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

    def test_rejects_workflow_artifact_mutation_while_reading_members(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            checked = package_submission.validate_manifest(manifest)
            original = package_submission.zip_flat_file_metadata

            def mutate_after_member_read(path: Path, label: str):
                result = original(path, label)
                with path.open("ab") as stream:
                    stream.write(b"changed")
                return result

            with patch.object(
                package_submission,
                "zip_flat_file_metadata",
                side_effect=mutate_after_member_read,
            ), self.assertRaisesRegex(
                package_submission.GateError,
                "workflow artifact ZIP changed during validation",
            ):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_accepts_complete_checksummed_release_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            checked = package_submission.validate_manifest(manifest)
            commands: list[list[str]] = []

            def run_command(command: list[str], **_: object) -> str:
                if command[:2] == ["git", "rev-parse"]:
                    return "e" * 40 + "\n"
                commands.append(command)
                return ""

            with patch.object(
                package_submission,
                "run",
                side_effect=run_command,
            ), patch.object(
                package_submission, "validate_source_archive_identity", return_value=None
            ):
                result = package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )
            self.assertEqual(16, result["release_evidence_file_count"])
            self.assertEqual(17, result["workflow_artifact_file_count"])
            self.assertEqual(12, len(result["public_release_assets"]))
            self.assertEqual(50, result["test_summary"]["test_count"])
            self.assertIn("SHA256SUMS", result["public_release_assets"])
            self.assertIn("test-summary.txt", result["public_release_assets"])
            self.assertIn("supply-chain-evidence.json", result["public_release_assets"])
            self.assertEqual(0, result["supply_chain"]["unreviewed_count"])
            self.assertEqual(2, result["supply_chain"]["unresolved_license_review_count"])
            self.assertEqual(3, result["supply_chain"]["finding_count"])
            self.assertNotIn("environment.txt", result["public_release_assets"])
            self.assertNotIn(
                "routecontract-mysql-example-cyclonedx.json",
                result["public_release_assets"],
            )
            self.assertEqual(2, len(commands))
            self.assertEqual(3, commands[0].count("--verify-pair"))
            self.assertEqual(3, commands[1].count("--pair"))
            self.assertTrue(
                commands[1][1].endswith("scripts/validate-official-cyclonedx.py")
            )
            input_root = commands[1].index("--input-root")
            self.assertEqual(str(root), commands[1][input_root + 1])

    def test_rejects_missing_workflow_only_example_pair_member(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            (root / "routecontract-mysql-example-cyclonedx.xml").unlink()
            self.rebuild_artifact(root, artifact, manifest)
            checked = package_submission.validate_manifest(manifest)

            with self.assertRaisesRegex(package_submission.GateError, "exact allowlist"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_example_pair_in_public_sha256sums(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            example = root / "routecontract-mysql-example-cyclonedx.json"
            checksum_path = root / "SHA256SUMS"
            checksum_path.write_text(
                checksum_path.read_text(encoding="utf-8")
                + f"{package_submission.sha256(example)}  {example.name}\n",
                encoding="utf-8",
            )
            self.rebuild_artifact(root, artifact, manifest)
            checked = package_submission.validate_manifest(manifest)

            with self.assertRaisesRegex(package_submission.GateError, "public SHA256SUMS"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_official_six_file_validation_failure_stops_packaging(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            checked = package_submission.validate_manifest(manifest)

            def fail_official(command: list[str], **_: object) -> str:
                if command[1].endswith("scripts/validate-official-cyclonedx.py"):
                    raise package_submission.GateError("official validation failed")
                return ""

            with patch.object(
                package_submission, "run", side_effect=fail_official
            ), patch.object(
                package_submission, "validate_source_archive_identity", return_value=None
            ), self.assertRaisesRegex(
                package_submission.GateError, "official validation failed"
            ):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_sbom_mutation_after_workflow_artifact_binding(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            checked = package_submission.validate_manifest(manifest)
            original = package_submission.validate_workflow_artifact_archive

            def mutate_after_binding(*args: object, **kwargs: object):
                result = original(*args, **kwargs)
                with (
                    root / "routecontract-mysql-example-cyclonedx.json"
                ).open("a", encoding="utf-8") as stream:
                    stream.write(" \n")
                return result

            with patch.object(
                package_submission,
                "validate_workflow_artifact_archive",
                side_effect=mutate_after_binding,
            ), patch.object(
                package_submission, "validate_source_archive_identity", return_value=None
            ), self.assertRaisesRegex(
                package_submission.GateError,
                "no longer matches the workflow artifact ZIP",
            ):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_mutation_between_semantic_and_official_sbom_validation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            checked = package_submission.validate_manifest(manifest)

            def mutate_after_semantic(command: list[str], **_: object) -> str:
                if command[1].endswith("scripts/finalize-sbom.py"):
                    with (
                        root / "routecontract-aggregate-cyclonedx.json"
                    ).open("a", encoding="utf-8") as stream:
                        stream.write("mutated after semantic validation\n")
                return ""

            with patch.object(
                package_submission, "run", side_effect=mutate_after_semantic
            ), patch.object(
                package_submission, "validate_source_archive_identity", return_value=None
            ), self.assertRaisesRegex(
                package_submission.GateError,
                "changed between semantic and official validation",
            ):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_boolean_supply_chain_vulnerability_count(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            evidence_path = root / "supply-chain-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["vulnerabilities"]["unreviewedCount"] = False
            evidence_path.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.write_public_checksums(root)
            self.rebuild_artifact(root, artifact, manifest)
            checked = package_submission.validate_manifest(manifest)
            with patch.object(
                package_submission, "run", return_value="e" * 40 + "\n"
            ), patch.object(
                package_submission, "validate_source_archive_identity", return_value=None
            ), self.assertRaisesRegex(
                package_submission.GateError, "must be a non-negative integer"
            ):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_non_integer_supply_chain_schema_version(self) -> None:
        for invalid_version in (True, 1.0):
            with self.subTest(value=invalid_version), tempfile.TemporaryDirectory() as raw:
                raw_root = Path(raw).resolve()
                root = raw_root / "evidence"
                root.mkdir()
                manifest = valid_manifest()
                artifact = self.build_evidence(root, manifest)
                evidence_path = root / "supply-chain-evidence.json"
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                evidence["schemaVersion"] = invalid_version
                evidence_path.write_text(
                    json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                self.write_public_checksums(root)
                self.rebuild_artifact(root, artifact, manifest)
                checked = package_submission.validate_manifest(manifest)
                with patch.object(
                    package_submission, "run", return_value="e" * 40 + "\n"
                ), patch.object(
                    package_submission, "validate_source_archive_identity", return_value=None
                ), self.assertRaisesRegex(package_submission.GateError, "schemaVersion"):
                    package_submission.validate_release_evidence(
                        root, artifact, checked, raw_root
                    )

    def test_accepts_reviewed_exception_and_rejects_non_boolean_reachability(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            evidence_path = root / "supply-chain-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            checked = package_submission.validate_manifest(manifest)
            with patch.object(
                package_submission, "run", return_value="e" * 40 + "\n"
            ), patch.object(
                package_submission, "validate_source_archive_identity", return_value=None
            ):
                accepted = package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )
            self.assertEqual(3, accepted["supply_chain"]["finding_count"])

            evidence["vulnerabilities"]["findings"][0]["reachabilityEvidence"] = {
                "exampleProfile": 1,
                "publishedProfile": 0,
                "publishedRuntime": 0,
            }
            evidence_path.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.write_public_checksums(root)
            self.rebuild_artifact(root, artifact, manifest)
            with patch.object(
                package_submission, "run", return_value="e" * 40 + "\n"
            ), patch.object(
                package_submission, "validate_source_archive_identity", return_value=None
            ), self.assertRaisesRegex(package_submission.GateError, "flags must be booleans"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

            evidence["vulnerabilities"]["findings"][0]["reachabilityEvidence"] = {
                "exampleProfile": True,
                "publishedProfile": False,
                "publishedRuntime": False,
            }
            evidence["vulnerabilities"]["findings"][0]["exceptionId"] = "RC-TAMPERED"
            evidence_path.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.write_public_checksums(root)
            self.rebuild_artifact(root, artifact, manifest)
            with patch.object(
                package_submission, "run", return_value="e" * 40 + "\n"
            ), patch.object(
                package_submission, "validate_source_archive_identity", return_value=None
            ), self.assertRaisesRegex(package_submission.GateError, "differs from policy"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_supply_chain_evidence_for_another_revision(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            evidence_path = root / "supply-chain-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["revision"] = "2" * 40
            evidence_path.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.write_public_checksums(root)
            self.rebuild_artifact(root, artifact, manifest)
            checked = package_submission.validate_manifest(manifest)
            with patch.object(
                package_submission, "run", return_value="e" * 40 + "\n"
            ), patch.object(
                package_submission, "validate_source_archive_identity", return_value=None
            ), self.assertRaisesRegex(package_submission.GateError, "revision does not match"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_supply_chain_evidence_not_bound_to_public_sbom(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            evidence_path = root / "supply-chain-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["sbom"]["sha256"] = "f" * 64
            evidence_path.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.write_public_checksums(root)
            self.rebuild_artifact(root, artifact, manifest)
            checked = package_submission.validate_manifest(manifest)
            with patch.object(
                package_submission, "run", return_value="e" * 40 + "\n"
            ), patch.object(
                package_submission, "validate_source_archive_identity", return_value=None
            ), self.assertRaisesRegex(package_submission.GateError, "not source/artifact bound"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_supply_chain_evidence_not_bound_to_workflow_example_sbom(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            evidence_path = root / "supply-chain-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["exampleProfile"]["sbomSha256"] = "f" * 64
            evidence_path.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.write_public_checksums(root)
            self.rebuild_artifact(root, artifact, manifest)
            checked = package_submission.validate_manifest(manifest)
            with patch.object(
                package_submission, "run", return_value="e" * 40 + "\n"
            ), patch.object(
                package_submission, "validate_source_archive_identity", return_value=None
            ), self.assertRaisesRegex(package_submission.GateError, "workflow-artifact bound"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_incomplete_unresolved_license_review_set(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            evidence_path = root / "supply-chain-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["sbom"]["licenseReviews"].pop()
            evidence_path.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.write_public_checksums(root)
            self.rebuild_artifact(root, artifact, manifest)
            checked = package_submission.validate_manifest(manifest)
            with patch.object(
                package_submission, "run", return_value="e" * 40 + "\n"
            ), patch.object(
                package_submission, "validate_source_archive_identity", return_value=None
            ), self.assertRaisesRegex(package_submission.GateError, "exactly two license reviews"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

    def test_rejects_reversed_license_review_order(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raw_root = Path(raw).resolve()
            root = raw_root / "evidence"
            root.mkdir()
            manifest = valid_manifest()
            artifact = self.build_evidence(root, manifest)
            evidence_path = root / "supply-chain-evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["sbom"]["licenseReviews"].reverse()
            evidence_path.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.write_public_checksums(root)
            self.rebuild_artifact(root, artifact, manifest)
            checked = package_submission.validate_manifest(manifest)
            with patch.object(
                package_submission, "run", return_value="e" * 40 + "\n"
            ), patch.object(
                package_submission, "validate_source_archive_identity", return_value=None
            ), self.assertRaisesRegex(package_submission.GateError, "exact ordered policy"):
                package_submission.validate_release_evidence(
                    root, artifact, checked, raw_root
                )

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
            "workflow_artifact_size": 456,
            "public_release_assets": {
                "routecontract-0.1.0-source.zip": {"sha256": digest("5"), "size": 123}
            },
        }

        def fake_json(url: str) -> dict:
            if "/actions/runs/" in url:
                return {
                    "id": 123456,
                    "html_url": project["ci_run_url"],
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": project["commit"],
                    "head_branch": project["tag"],
                    "event": "push",
                    "path": ".github/workflows/release-evidence.yml",
                    "name": "Release evidence",
                    "repository": {"full_name": "example-owner/routecontract"},
                    "created_at": "2026-07-19T23:00:00Z",
                    "updated_at": "2026-07-19T23:30:00Z",
                }
            if "/actions/artifacts/" in url:
                return {
                    "id": 987654,
                    "url": (
                        "https://api.github.com/repos/example-owner/routecontract/"
                        "actions/artifacts/987654"
                    ),
                    "archive_download_url": (
                        "https://api.github.com/repos/example-owner/routecontract/"
                        "actions/artifacts/987654/zip"
                    ),
                    "name": f"routecontract-release-evidence-{project['commit']}",
                    "size_in_bytes": 456,
                    "expired": False,
                    "digest": f"sha256:{digest('a')}",
                    "created_at": "2026-07-19T23:10:00Z",
                    "updated_at": "2026-07-19T23:20:00Z",
                    "expires_at": "2026-08-19T23:20:00Z",
                    "workflow_run": {
                        "id": 123456,
                        "head_sha": project["commit"],
                        "head_branch": project["tag"],
                    },
                }
            if "/releases/tags/" in url:
                return {
                    "id": 7,
                    "created_at": "2026-07-20T00:00:00Z",
                    "published_at": "2026-07-20T00:01:00Z",
                    "updated_at": "2026-07-20T00:02:00Z",
                    "draft": False,
                    "prerelease": False,
                    "immutable": True,
                    "tag_name": project["tag"],
                    "html_url": project["release_url"],
                    "assets": [
                        {
                            "id": 8,
                            "name": evidence["source_archive_filename"],
                            "state": "uploaded",
                            "size": 123,
                            "digest": f"sha256:{digest('5')}",
                            "url": (
                                "https://api.github.com/repos/example-owner/"
                                "routecontract/releases/assets/8"
                            ),
                            "browser_download_url": (
                                "https://github.com/example-owner/routecontract/"
                                "releases/download/v0.1.0/routecontract-0.1.0-source.zip"
                            ),
                            "created_at": "2026-07-20T00:00:30Z",
                            "updated_at": "2026-07-20T00:01:30Z",
                        }
                    ],
                }
            if "/commits/" in url:
                return {
                    "sha": project["commit"],
                    "html_url": (
                        f"{project['repository_url']}/commit/{project['commit']}"
                    ),
                }
            return {
                "id": 1,
                "node_id": "R_example",
                "private": False,
                "archived": False,
                "full_name": "example-owner/routecontract",
                "html_url": project["repository_url"],
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
        self.assertEqual("success", result["ci_run"]["conclusion"])
        self.assertEqual("v0.1.0", result["release"]["tag_name"])
        self.assertIs(True, result["release"]["immutable"])
        self.assertEqual(8, result["release"]["assets"][0]["id"])
        self.assertEqual(456, result["workflow_artifact"]["size_in_bytes"])
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

    def test_real_shaped_full_collector_requery_rejects_digest_or_time_drift(self) -> None:
        for drift in ("release_asset_digest", "run_updated_at"):
            manifest = package_submission.validate_manifest(valid_manifest())
            project = manifest["project"]
            asset_name = "routecontract-0.1.0-source.zip"
            evidence = {
                "source_archive_filename": asset_name,
                "source_archive_sha256": digest("5"),
                "source_archive_size": 123,
                "workflow_artifact_size": 456,
                "public_release_assets": {
                    asset_name: {"sha256": digest("5"), "size": 123}
                },
            }
            api_base = "https://api.github.com/repos/example-owner/routecontract"
            observation = 0

            def fake_json(url: str) -> dict:
                nonlocal observation
                if url == api_base:
                    observation += 1
                    return {
                        "id": 1,
                        "node_id": "R_example",
                        "private": False,
                        "archived": False,
                        "full_name": "example-owner/routecontract",
                        "html_url": project["repository_url"],
                    }
                if "/commits/" in url:
                    return {
                        "sha": project["commit"],
                        "html_url": f"{project['repository_url']}/commit/{project['commit']}",
                    }
                if "/actions/runs/" in url:
                    return {
                        "id": 123456,
                        "html_url": project["ci_run_url"],
                        "status": "completed",
                        "conclusion": "success",
                        "head_sha": project["commit"],
                        "head_branch": project["tag"],
                        "event": "push",
                        "path": ".github/workflows/release-evidence.yml",
                        "name": "Release evidence",
                        "repository": {"full_name": "example-owner/routecontract"},
                        "created_at": "2026-07-19T23:00:00Z",
                        "updated_at": (
                            "2026-07-19T23:31:00Z"
                            if drift == "run_updated_at" and observation == 2
                            else "2026-07-19T23:30:00Z"
                        ),
                    }
                if "/actions/artifacts/" in url:
                    return {
                        "id": 987654,
                        "url": f"{api_base}/actions/artifacts/987654",
                        "archive_download_url": f"{api_base}/actions/artifacts/987654/zip",
                        "name": f"routecontract-release-evidence-{project['commit']}",
                        "size_in_bytes": 456,
                        "expired": False,
                        "digest": f"sha256:{digest('a')}",
                        "created_at": "2026-07-19T23:10:00Z",
                        "updated_at": "2026-07-19T23:20:00Z",
                        "expires_at": "2026-08-19T23:20:00Z",
                        "workflow_run": {
                            "id": 123456,
                            "head_sha": project["commit"],
                            "head_branch": project["tag"],
                        },
                    }
                if "/releases/tags/" in url:
                    return {
                        "id": 7,
                        "created_at": "2026-07-20T00:00:00Z",
                        "published_at": "2026-07-20T00:01:00Z",
                        "updated_at": "2026-07-20T00:02:00Z",
                        "draft": False,
                        "prerelease": False,
                        "immutable": True,
                        "tag_name": project["tag"],
                        "html_url": project["release_url"],
                        "assets": [
                            {
                                "id": 8,
                                "name": asset_name,
                                "state": "uploaded",
                                "size": 123,
                                "digest": (
                                    f"sha256:{digest('5')}"
                                    if drift == "release_asset_digest" and observation == 2
                                    else None
                                ),
                                "url": f"{api_base}/releases/assets/8",
                                "browser_download_url": (
                                    f"{project['repository_url']}/releases/download/"
                                    f"{project['tag']}/{asset_name}"
                                ),
                                "created_at": "2026-07-20T00:00:30Z",
                                "updated_at": "2026-07-20T00:01:30Z",
                            }
                        ],
                    }
                self.fail(f"unexpected public collector URL: {url}")

            youtube = {
                "id": "abcdefghijk",
                "title": "RouteContract demo",
                "duration_seconds": 179.0,
                "availability": "public",
                "live_status": "not_live",
                "age_limit": 0,
                "max_video_height": 1080,
            }
            arguments = (
                manifest,
                {"duration_seconds": 179.5},
                evidence,
                Path("/evidence"),
                Path("/repository"),
            )
            with self.subTest(drift=drift), patch.object(
                package_submission, "request_json", side_effect=fake_json
            ), patch.object(
                package_submission, "public_youtube_metadata", return_value=youtube
            ), patch.object(
                package_submission, "hash_remote_file", return_value=digest("5")
            ), patch.object(
                package_submission, "verify_release_attestations"
            ), patch.object(
                package_submission, "validate_remote_tag_identity"
            ):
                initial = package_submission.validate_public_evidence(*arguments)
                with self.assertRaisesRegex(
                    package_submission.GateError,
                    "release/CI/video state changed between packaging observations",
                ):
                    package_submission.revalidate_public_evidence(initial, *arguments)
            self.assertEqual(2, observation)

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
            "id": 123456,
            "html_url": project["ci_run_url"],
            "status": "completed",
            "conclusion": "success",
            "head_sha": project["commit"],
            "head_branch": project["tag"],
            "event": "push",
            "path": ".github/workflows/release-evidence.yml",
            "name": "Release evidence",
            "repository": {"full_name": "example-owner/routecontract"},
            "created_at": "2026-07-19T23:00:00Z",
            "updated_at": "2026-07-19T23:30:00Z",
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
                        return {
                            "sha": project["commit"],
                            "html_url": f"{project['repository_url']}/commit/{project['commit']}",
                        }
                    return {
                        "id": 1,
                        "node_id": "R_example",
                        "private": False,
                        "archived": False,
                        "full_name": "example-owner/routecontract",
                        "html_url": project["repository_url"],
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
        evidence = {"public_release_assets": {}, "workflow_artifact_size": 456}

        def fake_json(url: str) -> dict:
            if "/actions/runs/" in url:
                return {
                    "id": 123456,
                    "html_url": project["ci_run_url"],
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": project["commit"],
                    "head_branch": project["tag"],
                    "event": "push",
                    "path": ".github/workflows/release-evidence.yml",
                    "name": "Release evidence",
                    "repository": {"full_name": "example-owner/routecontract"},
                    "created_at": "2026-07-19T23:00:00Z",
                    "updated_at": "2026-07-19T23:30:00Z",
                }
            if "/actions/artifacts/" in url:
                return {
                    "id": 987654,
                    "url": (
                        "https://api.github.com/repos/example-owner/routecontract/"
                        "actions/artifacts/987654"
                    ),
                    "archive_download_url": (
                        "https://api.github.com/repos/example-owner/routecontract/"
                        "actions/artifacts/987654/zip"
                    ),
                    "name": f"routecontract-release-evidence-{project['commit']}",
                    "size_in_bytes": 456,
                    "expired": False,
                    "digest": f"sha256:{digest('a')}",
                    "created_at": "2026-07-19T23:10:00Z",
                    "updated_at": "2026-07-19T23:20:00Z",
                    "expires_at": "2026-08-19T23:20:00Z",
                    "workflow_run": {
                        "id": 123456,
                        "head_sha": project["commit"],
                        "head_branch": "main",
                    },
                }
            if "/commits/" in url:
                return {
                    "sha": project["commit"],
                    "html_url": f"{project['repository_url']}/commit/{project['commit']}",
                }
            return {
                "id": 1,
                "node_id": "R_example",
                "private": False,
                "archived": False,
                "full_name": "example-owner/routecontract",
                "html_url": project["repository_url"],
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
        evidence = {"public_release_assets": {}, "workflow_artifact_size": 456}
        for immutable in (False, None):
            with self.subTest(immutable=immutable):

                def fake_json(url: str) -> dict:
                    if "/actions/runs/" in url:
                        return {
                            "id": 123456,
                            "html_url": project["ci_run_url"],
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
                            "created_at": "2026-07-19T23:00:00Z",
                            "updated_at": "2026-07-19T23:30:00Z",
                        }
                    if "/actions/artifacts/" in url:
                        return {
                            "id": 987654,
                            "url": (
                                "https://api.github.com/repos/example-owner/routecontract/"
                                "actions/artifacts/987654"
                            ),
                            "archive_download_url": (
                                "https://api.github.com/repos/example-owner/routecontract/"
                                "actions/artifacts/987654/zip"
                            ),
                            "name": (
                                "routecontract-release-evidence-"
                                f"{project['commit']}"
                            ),
                            "expired": False,
                            "size_in_bytes": 456,
                            "digest": f"sha256:{digest('a')}",
                            "created_at": "2026-07-19T23:10:00Z",
                            "updated_at": "2026-07-19T23:20:00Z",
                            "expires_at": "2026-08-19T23:20:00Z",
                            "workflow_run": {
                                "id": 123456,
                                "head_sha": project["commit"],
                                "head_branch": project["tag"],
                            },
                        }
                    if "/releases/tags/" in url:
                        return {
                            "id": 7,
                            "created_at": "2026-07-20T00:00:00Z",
                            "published_at": "2026-07-20T00:01:00Z",
                            "updated_at": "2026-07-20T00:02:00Z",
                            "draft": False,
                            "prerelease": False,
                            "immutable": immutable,
                            "tag_name": project["tag"],
                            "html_url": project["release_url"],
                            "assets": [],
                        }
                    if "/commits/" in url:
                        return {
                            "sha": project["commit"],
                            "html_url": f"{project['repository_url']}/commit/{project['commit']}",
                        }
                    return {
                        "id": 1,
                        "node_id": "R_example",
                        "private": False,
                        "archived": False,
                        "full_name": "example-owner/routecontract",
                        "html_url": project["repository_url"],
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
            "workflow_artifact_size": 456,
            "public_release_assets": {
                "routecontract-0.1.0-source.zip": {"sha256": digest("5"), "size": 123}
            },
        }

        def fake_json(url: str) -> dict:
            if "/actions/runs/" in url:
                return {
                    "id": 123456,
                    "html_url": project["ci_run_url"],
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": "0" * 40,
                    "head_branch": project["tag"],
                    "event": "push",
                    "path": ".github/workflows/release-evidence.yml",
                    "name": "Release evidence",
                    "repository": {"full_name": "example-owner/routecontract"},
                    "created_at": "2026-07-19T23:00:00Z",
                    "updated_at": "2026-07-19T23:30:00Z",
                }
            if "/commits/" in url:
                return {
                    "sha": manifest["project"]["commit"],
                    "html_url": f"{project['repository_url']}/commit/{project['commit']}",
                }
            return {
                "id": 1,
                "node_id": "R_example",
                "private": False,
                "archived": False,
                "full_name": "example-owner/routecontract",
                "html_url": project["repository_url"],
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
