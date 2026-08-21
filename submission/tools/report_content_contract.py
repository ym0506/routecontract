#!/usr/bin/env python3
"""Validate and materialize the report's external-evidence claim."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXTERNAL_EVIDENCE_SUMMARY_MARKER = "[[EXTERNAL_EVIDENCE_SUMMARY: generated]]"
EXTERNAL_EVIDENCE_PLACEHOLDERS = {
    "branch": "[[EXTERNAL_EVIDENCE_BRANCH: rc_only|zero]]",
    "final_stable_tag": "[[EXTERNAL_EVIDENCE_FINAL_STABLE_TAG]]",
    "tested_tag": "[[EXTERNAL_EVIDENCE_TESTED_TAG]]",
    "qualified_result_count": "[[EXTERNAL_EVIDENCE_QUALIFIED_RESULT_COUNT]]",
    "result_issue_url": "[[EXTERNAL_EVIDENCE_RESULT_ISSUE_URL_OR_NULL]]",
    "activation_record_url": "[[EXTERNAL_EVIDENCE_ACTIVATION_RECORD_URL_OR_NULL]]",
    "recruitment_record_url": "[[EXTERNAL_EVIDENCE_RECRUITMENT_RECORD_URL_OR_NULL]]",
    "cutoff_utc": "[[EXTERNAL_EVIDENCE_CUTOFF_UTC]]",
}
EXTERNAL_EVIDENCE_KEYS = {
    *EXTERNAL_EVIDENCE_PLACEHOLDERS,
    "protocol_issue_url",
}
EXTERNAL_EVIDENCE_BRANCHES = {"rc_only", "zero"}
STABLE_TAG_RE = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+")
RC_TAG_RE = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+-rc[1-9][0-9]*")
CUTOFF_UTC_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
ASCII_ISSUE_NUMBER_RE = re.compile(r"[1-9][0-9]*")
FULL_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
CANONICAL_REPORT_SOURCE = Path(__file__).resolve().parents[1] / "report-content.ko.json"
# Only these private-overlay values may differ from the tracked report source. The
# block identities, ordering, static prose, assets and SBOM remain closed. External
# evidence is validated separately and its visible paragraph is always generated.
PRIVATE_OVERLAY_STRING_PATHS = (
    ("metadata", "team_name"),
    ("metadata", "team_size"),
    ("metadata", "project_name"),
    ("metadata", "repository_url"),
    ("metadata", "video_url"),
    ("environment", 2, "text"),
    ("features", 4, "text"),
    ("features", 6, "text"),
    ("other", 3, "text"),
    ("other", 6, "text"),
)


def _require_exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    missing = sorted(expected - set(value))
    unexpected = sorted(set(value) - expected)
    if missing or unexpected:
        raise ValueError(
            f"{label} keys do not match schema; missing={missing}, unexpected={unexpected}"
        )
    return value


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return "[[" in value or "]]" in value
    if isinstance(value, dict):
        return any(_contains_placeholder(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_placeholder(child) for child in value)
    return False


def _canonical_issue_url(value: Any, repository_url: str, label: str) -> str:
    prefix = f"{repository_url}/issues/"
    issue_number = value[len(prefix) :] if isinstance(value, str) and value.startswith(prefix) else ""
    if ASCII_ISSUE_NUMBER_RE.fullmatch(issue_number) is None:
        raise ValueError(f"{label} must be a canonical public Issue URL in the repository")
    return value


def _canonical_activation_record_url(
    value: Any, repository_url: str, tested_tag: str
) -> str:
    prefix = f"{repository_url}/blob/"
    suffix = f"/docs/evidence/independent-rc-activation-{tested_tag}.json"
    if not isinstance(value, str) or not value.startswith(prefix) or not value.endswith(suffix):
        raise ValueError(
            "external_evidence.activation_record_url must be the exact immutable RC activation-record permalink"
        )
    commit = value[len(prefix) : -len(suffix)]
    if FULL_COMMIT_RE.fullmatch(commit) is None:
        raise ValueError(
            "external_evidence.activation_record_url must use one lowercase 40-hex commit"
        )
    if commit == "0" * 40:
        raise ValueError(
            "external_evidence.activation_record_url must use a nonzero commit"
        )
    return value


def _canonical_recruitment_record_url(value: Any, repository_url: str) -> str:
    prefix = f"{repository_url}/issues/9#issuecomment-"
    comment_id = value[len(prefix) :] if isinstance(value, str) and value.startswith(prefix) else ""
    if ASCII_ISSUE_NUMBER_RE.fullmatch(comment_id) is None:
        raise ValueError(
            "external_evidence.recruitment_record_url must be an Issue #9 comment permalink"
        )
    return value


def _validate_current_utc(value: datetime | None) -> datetime:
    current = datetime.now(timezone.utc) if value is None else value
    if current.tzinfo is None or current.utcoffset() != timezone.utc.utcoffset(current):
        raise ValueError("current_utc must be an aware UTC datetime")
    return current


def _validate_cutoff(value: Any, *, current_utc: datetime | None) -> str:
    if not isinstance(value, str) or CUTOFF_UTC_RE.fullmatch(value) is None:
        raise ValueError("external_evidence.cutoff_utc must use YYYY-MM-DDTHH:MM:SSZ")
    try:
        cutoff = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        raise ValueError("external_evidence.cutoff_utc is not a valid UTC timestamp") from error
    if cutoff > _validate_current_utc(current_utc):
        raise ValueError("external_evidence.cutoff_utc cannot be later than current UTC")
    return value


def _path_value(root: Any, path: tuple[str | int, ...]) -> Any:
    value = root
    for component in path:
        if isinstance(component, int):
            if not isinstance(value, list) or not 0 <= component < len(value):
                raise ValueError(f"report private-overlay path is missing: {path}")
            value = value[component]
        else:
            if not isinstance(value, dict) or component not in value:
                raise ValueError(f"report private-overlay path is missing: {path}")
            value = value[component]
    return value


def _set_path_value(root: Any, path: tuple[str | int, ...], value: Any) -> None:
    parent = root
    for component in path[:-1]:
        parent = parent[component]
    parent[path[-1]] = value


def _canonical_report_source() -> dict[str, Any]:
    try:
        value = json.loads(CANONICAL_REPORT_SOURCE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not load the canonical report source: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("canonical report source must be an object")
    return value


def _validate_closed_report_overlay(data: dict[str, Any]) -> None:
    """Allow private values only at the documented overlay paths.

    This is a structural/byte-semantic boundary, not a natural-language claim
    classifier. The participant separately attests after human review that free
    text does not introduce an external-result, adoption or stable-validation
    claim outside the generated evidence row.
    """
    canonical = _canonical_report_source()
    normalized = deepcopy(data)
    for path in PRIVATE_OVERLAY_STRING_PATHS:
        candidate = _path_value(normalized, path)
        if not isinstance(candidate, str) or not candidate.strip():
            raise ValueError(f"report private-overlay value must be a non-empty string: {path}")
        _set_path_value(normalized, path, _path_value(canonical, path))
    normalized["external_evidence"] = canonical.get("external_evidence")
    if normalized != canonical:
        raise ValueError(
            "report content differs from the canonical closed source outside documented "
            "private-overlay fields"
        )


def _external_evidence_slot(data: dict[str, Any]) -> dict[str, str]:
    other = data.get("other")
    if not isinstance(other, list):
        raise ValueError("report content other must be an array")
    slots = [
        block
        for block in other
        if isinstance(block, dict) and block.get("lead") == "외부 검증"
    ]
    if len(slots) != 1:
        raise ValueError("report content must contain exactly one 외부 검증 block")
    slot = _require_exact_keys(slots[0], {"lead", "text"}, "외부 검증 block")
    if slot["text"] != EXTERNAL_EVIDENCE_SUMMARY_MARKER:
        raise ValueError(
            "외부 검증 text must remain the generated structured-evidence marker"
        )
    return slot


def _materialized_summary(
    evidence: dict[str, Any], *, repository_url: str, expected_final_tag: str | None,
    current_utc: datetime | None
) -> str:
    branch = evidence["branch"]
    if branch not in EXTERNAL_EVIDENCE_BRANCHES:
        raise ValueError(
            "external_evidence.branch must be rc_only or zero; final_stable is "
            "fail-closed until a distinct reviewed stable form and protocol exist"
        )

    final_tag = evidence["final_stable_tag"]
    if not isinstance(final_tag, str) or STABLE_TAG_RE.fullmatch(final_tag) is None:
        raise ValueError("external_evidence.final_stable_tag must be a stable vMAJOR.MINOR.PATCH")
    if expected_final_tag is not None and final_tag != expected_final_tag:
        raise ValueError(
            "external_evidence.final_stable_tag does not match the final package tag"
        )

    protocol_url = _canonical_issue_url(
        evidence["protocol_issue_url"], repository_url, "external_evidence.protocol_issue_url"
    )
    if protocol_url != f"{repository_url}/issues/9":
        raise ValueError("external_evidence.protocol_issue_url must be the fixed Issue #9 URL")

    cutoff = _validate_cutoff(evidence["cutoff_utc"], current_utc=current_utc)
    count = evidence["qualified_result_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("external_evidence.qualified_result_count must be a nonnegative integer")

    tested_tag = evidence["tested_tag"]
    result_url = evidence["result_issue_url"]
    activation_url = evidence["activation_record_url"]
    recruitment_url = evidence["recruitment_record_url"]
    history_boundary = (
        " maintainer 수정·삭제·은폐·이전·누락은 API 이력 복원·자동 검증 불가로 "
        "owner 수동 진술에 의존한다."
    )
    if not isinstance(tested_tag, str) or RC_TAG_RE.fullmatch(tested_tag) is None:
        raise ValueError("rc_only and zero evidence must name one exact vMAJOR.MINOR.PATCH-rcN tag")
    if tested_tag.rsplit("-rc", 1)[0] != final_tag:
        raise ValueError("RC evidence tag must be an RC of the exact final stable tag")
    activation_url = _canonical_activation_record_url(
        activation_url, repository_url, tested_tag
    )

    if branch == "rc_only":
        if count != 1:
            raise ValueError("rc_only external evidence requires exactly one qualified RC result")
        issue_url = _canonical_issue_url(
            result_url, repository_url, "external_evidence.result_issue_url"
        )
        if issue_url == protocol_url:
            raise ValueError("a tracking/protocol Issue cannot substitute for a result Issue")
        recruitment_url = _canonical_recruitment_record_url(
            recruitment_url, repository_url
        )
        return (
            f"두 packaging 관찰에서 cutoff 내 API-visible인 exact RC {tested_tag} 결과 "
            f"{count}건 [결과 Issue]. 저장소 owner와 다른 GitHub User의 비작성자 "
            f"self-attestation, 14개 [x]·Task A enum, 현재 GraphQL 편집 신호 없음"
            f"(editor·last edit·body edit·title rename), [활성화 기록]·[모집 기록]·"
            f"[검증 프로토콜]을 확인했다. 자동 gate는 실제 사람·작성자·비공개 독립성, "
            f"adoption, stable 검증을 증명하지 않는다. stable 외부 검증 미확보"
            f"({cutoff})." + history_boundary
        )

    if count != 0 or result_url is not None:
        raise ValueError("zero external evidence requires count=0 and result_issue_url=null")
    recruitment_url = _canonical_recruitment_record_url(
        recruitment_url, repository_url
    )
    return (
        f"exact RC {tested_tag} 공개 모집 [모집 기록]. 두 packaging 관찰의 cutoff 내 "
        f"API-visible Issue 중 owner와 다른 GitHub User의 비작성자 "
        f"self-attestation, 14개 [x]·Task A enum, 현재 GraphQL 편집 신호 없음"
        f"(editor·last edit·body edit·title rename)을 갖춘 결과는 0건이다. "
        f"[활성화 기록]·[검증 프로토콜] 확인. 실제 사람·작성자·비공개 독립성은 "
        f"자동 증명되지 않는다. stable 외부 검증 미확보({cutoff})."
        + history_boundary
    )


def materialize_external_evidence(
    data: dict[str, Any],
    *,
    allow_placeholders: bool,
    expected_final_tag: str | None = None,
    expected_repository_url: str | None = None,
    current_utc: datetime | None = None,
) -> dict[str, Any]:
    """Return a copy whose external-evidence block is generated from one strict branch."""
    if not isinstance(data, dict):
        raise ValueError("report content must be an object")
    result = deepcopy(data)
    evidence = _require_exact_keys(
        result.get("external_evidence"),
        EXTERNAL_EVIDENCE_KEYS,
        "external_evidence",
    )
    slot = _external_evidence_slot(result)
    _validate_closed_report_overlay(result)

    repository_url = expected_repository_url
    if repository_url is None:
        metadata = result.get("metadata")
        if not isinstance(metadata, dict) or not isinstance(metadata.get("repository_url"), str):
            raise ValueError("report metadata.repository_url must be a string")
        repository_url = metadata["repository_url"]

    if _contains_placeholder(evidence):
        if not allow_placeholders:
            raise ValueError("external_evidence contains unresolved structured fields")
        expected_draft = {
            **EXTERNAL_EVIDENCE_PLACEHOLDERS,
            "protocol_issue_url": f"{repository_url}/issues/9",
        }
        if evidence != expected_draft:
            raise ValueError("draft external_evidence must use the complete canonical placeholder set")
        return result

    slot["text"] = _materialized_summary(
        evidence,
        repository_url=repository_url,
        expected_final_tag=expected_final_tag,
        current_utc=current_utc,
    )
    return result
