#!/usr/bin/env python3
"""Validate and materialize the report's external-evidence claim."""

from __future__ import annotations

import json
import math
import re
import unicodedata
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
READER_FACING_EVIDENCE_ID_RE = re.compile(
    r"(?<![A-Za-z0-9])E(?:0[1-9]|1[0-4])(?![A-Za-z0-9])",
    re.IGNORECASE,
)
CANONICAL_REPORT_SOURCE = Path(__file__).resolve().parents[1] / "report-content.ko.json"
# Only these private-overlay values may differ from the tracked report source. The
# block identities, ordering, static prose, assets and SBOM remain closed. External
# evidence is validated separately and its visible paragraph is always generated.
STRUCTURED_PRIVATE_OVERLAY_STRING_PATHS = (
    ("metadata", "team_name"),
    ("metadata", "team_size"),
    ("metadata", "division"),
    ("metadata", "task_type"),
    ("metadata", "project_name"),
    ("metadata", "repository_url"),
    ("metadata", "video_url"),
)
OWNER_FREE_TEXT_OVERLAY_STRING_PATHS = (
    ("environment", 2, "text"),
    ("features", 4, "text"),
    ("features", 6, "text"),
    ("other", 4, "text"),
    ("other", 5, "text"),
    ("other", 8, "text"),
)
PRIVATE_OVERLAY_STRING_PATHS = (
    *STRUCTURED_PRIVATE_OVERLAY_STRING_PATHS,
    *OWNER_FREE_TEXT_OVERLAY_STRING_PATHS,
)
PRIVATE_OVERLAY_SENSITIVE_PATTERNS = (
    (
        "EMAIL_ADDRESS",
        re.compile(
            r"(?<![\w@])[\w.!#$%&'*+/=?^`{|}~-]+@(?:[\w-]+\.)+[\w-]{2,}(?![\w@])",
            re.IGNORECASE,
        ),
    ),
    (
        "LOCAL_PATH",
        re.compile(
            r"(?:(?<![\w])~(?:[/\\]|[A-Z0-9._-]+(?:[/\\]|(?=$|[\s,;:.)\]])))|"
            r"(?<![A-Z0-9])/(?:Users|home|root|private/tmp|var/folders|tmp|Volumes|workspaces?|mnt)"
            r"(?:[/\\]|(?=$|[\s,;:.)\]]))|"
            r"[A-Z]:\\(?:Users|Documents and Settings)\\|\\\\[^\\\s]+\\[^\\\s]+|"
            r"Mobile Documents|com~apple~CloudDocs|(?:^|[/\\])\.(?:codex|agents)(?:[/\\]|$))",
            re.IGNORECASE,
        ),
    ),
    (
        "CREDENTIAL_OR_TOKEN",
        re.compile(
            r"(?:\b(?:password|passwd|pwd|token|secret|api[_-]?key|authorization|"
            r"client[_-]?secret|access[_-]?token|refresh[_-]?token|username|user|"
            r"aws[_-]?secret[_-]?access[_-]?key|aws[_-]?access[_-]?key[_-]?id|"
            r"비밀번호|API\s*키|토큰)\s*[:=]\s*\S+|\bBearer\s+[A-Z0-9._~+/-]{8,}|"
            r"\b(?:github_pat_|gh[pousr]_|sk-)[A-Z0-9_-]{12,}|"
            r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|"
            r"\beyJ[A-Z0-9_-]{5,}\.[A-Z0-9_-]{5,}\.[A-Z0-9_-]{5,}\b)",
            re.IGNORECASE,
        ),
    ),
    ("JDBC_URL", re.compile(r"\bjdbc:[a-z0-9]+:", re.IGNORECASE)),
    (
        "RAW_SQL",
        re.compile(
            r"\b(?:SELECT\s+.+?\s+FROM|INSERT\s+INTO|UPDATE\s+\S+\s+SET|"
            r"DELETE\s+FROM|MERGE\s+INTO|ALTER\s+TABLE|CREATE\s+TABLE|"
            r"DROP\s+TABLE|TRUNCATE\s+TABLE)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "PRIVATE_TOPOLOGY",
        re.compile(
            r"(?:\b(?:localhost|host\.docker\.internal)\b|"
            r"\b(?:10(?:\.\d{1,3}){3}|127(?:\.\d{1,3}){3}|"
            r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])"
            r"(?:\.\d{1,3}){2})\b|"
            r"\[(?:::1|f[cd][0-9a-f]{0,2}:[0-9a-f:]*|"
            r"fe[89ab][0-9a-f]{0,1}:[0-9a-f:]*)\]|"
            r"(?<![0-9a-f:])(?:::1|f[cd][0-9a-f]{0,2}:[0-9a-f:]*|"
            r"fe[89ab][0-9a-f]{0,1}:[0-9a-f:]*)(?![0-9a-f:])|"
            r"\b[a-z0-9][a-z0-9.-]*\.(?:internal|local)(?::\d{2,5})?\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "KOREAN_PHONE_NUMBER",
        re.compile(r"(?<!\d)01[016789][\s.-]*\d{3,4}[\s.-]*\d{4}(?!\d)"),
    ),
    (
        "KOREAN_RESIDENT_NUMBER",
        re.compile(r"(?<!\d)\d{6}-[1-4]\d{6}(?!\d)"),
    ),
    (
        "PRIVATE_KEY",
        re.compile(r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----", re.IGNORECASE),
    ),
    (
        "MAC_ADDRESS",
        re.compile(r"\b(?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2}\b", re.IGNORECASE),
    ),
)
PRIVATE_OVERLAY_SQL_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
PRIVATE_OVERLAY_SQL_LINE_COMMENT_RES = (
    re.compile(r"--[^\r\n]*(?:\r\n?|\n|$)"),
    re.compile(r"#[^\r\n]*(?:\r\n?|\n|$)"),
)
PRIVATE_OVERLAY_DEFAULT_IGNORABLE_RANGES = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)


def count_reader_facing_evidence_ids(value: Any) -> int:
    """Count E01-E14 after compatibility and case normalization."""
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFKC", value)
        normalized = "".join(
            character
            for character in normalized
            if unicodedata.category(character) != "Cf"
        )
        return len(READER_FACING_EVIDENCE_ID_RE.findall(normalized))
    if isinstance(value, dict):
        return sum(count_reader_facing_evidence_ids(child) for child in value.values())
    if isinstance(value, list):
        return sum(count_reader_facing_evidence_ids(child) for child in value)
    return 0


class StrictJsonError(ValueError):
    """Value-free failure for duplicate, non-finite, or malformed JSON."""


STRICT_JSON_MAX_CONTAINER_DEPTH = 64
STRICT_JSON_MAX_NODES = 100_000
STRICT_JSON_MAX_INTEGER_DIGITS = 1_000
CANONICAL_REPORT_SOURCE_MAX_BYTES = 1024 * 1024


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise StrictJsonError("strict JSON validation failed")
        value[key] = child
    return value


def _reject_non_finite_json_constant(_value: str) -> None:
    raise StrictJsonError("strict JSON validation failed")


def _parse_finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise StrictJsonError("strict JSON validation failed")
    return parsed


def _parse_bounded_json_int(value: str) -> int:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) > STRICT_JSON_MAX_INTEGER_DIGITS:
        raise StrictJsonError("strict JSON validation failed")
    return int(value)


def _validate_strict_json_shape(value: Any) -> None:
    """Bound JSON iteratively: scalar root depth 0; root container depth 1.

    The node budget counts the root and every array element or object member value.
    Object keys are not separate nodes.
    """
    node_count = 0
    pending: list[tuple[Any, int]] = [(value, 0)]
    while pending:
        current, parent_container_depth = pending.pop()
        node_count += 1
        if node_count > STRICT_JSON_MAX_NODES:
            raise StrictJsonError("strict JSON validation failed")
        if isinstance(current, dict):
            container_depth = parent_container_depth + 1
            if container_depth > STRICT_JSON_MAX_CONTAINER_DEPTH:
                raise StrictJsonError("strict JSON validation failed")
            pending.extend(
                (child, container_depth) for child in current.values()
            )
        elif isinstance(current, list):
            container_depth = parent_container_depth + 1
            if container_depth > STRICT_JSON_MAX_CONTAINER_DEPTH:
                raise StrictJsonError("strict JSON validation failed")
            pending.extend((child, container_depth) for child in current)


def decode_strict_json(
    data: str | bytes, *, maximum_bytes: int | None = None
) -> Any:
    """Decode strict UTF-8 JSON with value-free, fail-closed limits.

    ``maximum_bytes`` applies to the UTF-8 byte representation, not code points.
    Integer digits exclude a leading minus sign.  Container depth and node-count
    semantics are documented by :func:`_validate_strict_json_shape`.
    """
    try:
        if maximum_bytes is not None and (
            type(maximum_bytes) is not int or maximum_bytes < 0
        ):
            raise StrictJsonError("strict JSON validation failed")
        if isinstance(data, bytes):
            if maximum_bytes is not None and len(data) > maximum_bytes:
                raise StrictJsonError("strict JSON validation failed")
            text = data.decode("utf-8", errors="strict")
        elif isinstance(data, str):
            text = data
            if maximum_bytes is not None and len(text.encode("utf-8")) > maximum_bytes:
                raise StrictJsonError("strict JSON validation failed")
        else:
            raise StrictJsonError("strict JSON validation failed")
        value = json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_non_finite_json_constant,
            parse_float=_parse_finite_json_float,
            parse_int=_parse_bounded_json_int,
        )
        _validate_strict_json_shape(value)
        return value
    except (UnicodeError, TypeError, ValueError, RecursionError):
        raise StrictJsonError("strict JSON validation failed") from None


def _is_default_ignorable_or_filler(character: str) -> bool:
    codepoint = ord(character)
    return unicodedata.name(character, "").endswith(" FILLER") or any(
        first <= codepoint <= last
        for first, last in PRIVATE_OVERLAY_DEFAULT_IGNORABLE_RANGES
    )


def _privacy_scan_views(text: str) -> tuple[str, ...]:
    """Expose bounded comment and line-break token-splitting variants."""
    views = {text}
    for comment_re in (
        PRIVATE_OVERLAY_SQL_BLOCK_COMMENT_RE,
        *PRIVATE_OVERLAY_SQL_LINE_COMMENT_RES,
    ):
        for view in tuple(views):
            views.add(comment_re.sub("", view))
            views.add(comment_re.sub(" ", view))
    for view in tuple(views):
        views.add(re.sub(r"[\t\r\n]+", "", view))
        views.add(re.sub(r"[\t\r\n]+", " ", view))
    return tuple(sorted(views))


def _require_exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    missing = expected - set(value)
    unexpected = set(value) - expected
    if missing or unexpected:
        raise ValueError(
            f"{label} keys do not match schema; missing_count={len(missing)}, "
            f"unexpected_count={len(unexpected)}"
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
        with CANONICAL_REPORT_SOURCE.open("rb") as source:
            raw = source.read(CANONICAL_REPORT_SOURCE_MAX_BYTES + 1)
        value = decode_strict_json(
            raw, maximum_bytes=CANONICAL_REPORT_SOURCE_MAX_BYTES
        )
    except (OSError, StrictJsonError):
        raise ValueError("could not load the canonical report source") from None
    if not isinstance(value, dict):
        raise ValueError("canonical report source must be an object")
    return value


def _validate_private_overlay_text(
    value: str,
    path: tuple[str | int, ...],
    *,
    allow_canonical_marker: bool = False,
) -> None:
    """Fail closed on visible secrets or private runtime details without echoing them."""
    if any(_is_default_ignorable_or_filler(character) for character in value):
        raise ValueError(
            f"report private-overlay value is not privacy-safe: {path} "
            "(DEFAULT_IGNORABLE_OR_FILLER)"
        )
    if any(
        unicodedata.category(character).startswith("C")
        and character not in {"\t", "\n", "\r"}
        for character in value
    ):
        raise ValueError(
            f"report private-overlay value is not privacy-safe: {path} "
            "(CONTROL_OR_FORMAT_CHARACTER)"
        )
    if any(unicodedata.category(character) in {"Mn", "Me"} for character in value):
        raise ValueError(
            f"report private-overlay value is not privacy-safe: {path} "
            "(COMBINING_OR_ENCLOSING_MARK)"
        )
    normalized = unicodedata.normalize("NFKC", value)
    if not allow_canonical_marker and ("[[" in normalized or "]]" in normalized):
        raise ValueError(
            f"report private-overlay value is not privacy-safe: {path} "
            "(UNRESOLVED_MARKER)"
        )
    if any(_is_default_ignorable_or_filler(character) for character in normalized):
        raise ValueError(
            f"report private-overlay value is not privacy-safe: {path} "
            "(DEFAULT_IGNORABLE_OR_FILLER)"
        )
    if any(
        unicodedata.category(character).startswith("C")
        and character not in {"\t", "\n", "\r"}
        for character in normalized
    ):
        raise ValueError(
            f"report private-overlay value is not privacy-safe: {path} "
            "(CONTROL_OR_FORMAT_CHARACTER)"
        )
    if any(unicodedata.category(character) in {"Mn", "Me"} for character in normalized):
        raise ValueError(
            f"report private-overlay value is not privacy-safe: {path} "
            "(COMBINING_OR_ENCLOSING_MARK)"
        )
    scan_texts = _privacy_scan_views(normalized)
    for label, pattern in PRIVATE_OVERLAY_SENSITIVE_PATTERNS:
        if any(pattern.search(scan_text) for scan_text in scan_texts):
            raise ValueError(
                f"report private-overlay value is not privacy-safe: {path} ({label})"
            )


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
        if path in OWNER_FREE_TEXT_OVERLAY_STRING_PATHS:
            _validate_private_overlay_text(
                candidate,
                path,
                allow_canonical_marker=candidate == _path_value(canonical, path),
            )
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
            f"cutoff {cutoff}까지 exact RC {tested_tag}의 Task A 형식 요건을 충족한 "
            f"API-visible 공개 self-attestation {count}건 [결과 Issue]을 확인했다. "
            f"이는 실제 사람·비공개 독립성·stable 검증·채택·endorsement를 자동 "
            f"증명하지 않는다. API로 복원할 수 없는 변경 이력은 자동 검증 범위 "
            f"밖이다. [활성화 기록]·[모집 기록]·[검증 프로토콜]"
        )

    if count != 0 or result_url is not None:
        raise ValueError("zero external evidence requires count=0 and result_issue_url=null")
    recruitment_url = _canonical_recruitment_record_url(
        recruitment_url, repository_url
    )
    return (
        f"cutoff {cutoff}까지 exact RC {tested_tag} 공개 모집 [모집 기록]과 "
        f"[검증 프로토콜]을 운영했으나 API-visible Task A 형식 요건을 충족한 공개 "
        f"결과는 0건이었다. 따라서 독립 외부 설치·채택·stable 검증을 주장하지 "
        f"않는다. API로 복원할 수 없는 변경 이력은 자동 검증 범위 밖이다. "
        f"[활성화 기록]"
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
