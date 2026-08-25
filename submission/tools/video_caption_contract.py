#!/usr/bin/env python3
"""Validate the tracked video-caption corpus and render one deterministic SRT branch."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
SOURCE_RELATIVE_PATH = "submission/video-caption-cues.json"
TRACKED_SOURCE_PATH = Path(__file__).resolve().parents[1] / "video-caption-cues.json"
TIMEBASE = "milliseconds"
MAX_SOURCE_BYTES = 64 * 1024
MAX_CUE_END_MS = 175_000
MIN_CUE_DURATION_MS = 4_000
MAX_CUE_DURATION_MS = 9_000
MIN_CUE_GAP_MS = 500
MAX_LINE_CHARACTERS = 34
MAX_VISIBLE_CHARACTERS_PER_SECOND = 8.0
BRANCHES = ("zero", "rc_only")
ALLOWED_CUE_BRANCHES = frozenset(("common", *BRANCHES))
SHA256_RE = re.compile(r"[0-9a-f]{64}")
PLACEHOLDER_RE = re.compile(r"\[\[[^\]]+\]\]")


class CaptionContractError(ValueError):
    """The caption source or selected branch violates the frozen contract."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CaptionContractError("caption source contains a duplicate JSON key")
        result[key] = value
    return result


def _decode_strict_json(raw: bytes) -> Any:
    if len(raw) > MAX_SOURCE_BYTES:
        raise CaptionContractError("caption source exceeds the bounded byte limit")
    try:
        text = raw.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                CaptionContractError("caption source contains a non-finite JSON value")
            ),
        )
    except CaptionContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise CaptionContractError("caption source is not strict UTF-8 JSON") from None


def _require_exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CaptionContractError(f"{label} must be an object")
    if set(value) != expected:
        raise CaptionContractError(f"{label} has missing or unexpected keys")
    return value


def _require_plain_line(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CaptionContractError(f"{label} must be non-empty trimmed text")
    if value != unicodedata.normalize("NFC", value):
        raise CaptionContractError(f"{label} must use Unicode NFC")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise CaptionContractError(f"{label} contains a control or formatting character")
    if PLACEHOLDER_RE.search(value):
        raise CaptionContractError(f"{label} contains an unresolved placeholder")
    if len(value) > MAX_LINE_CHARACTERS:
        raise CaptionContractError(
            f"{label} exceeds {MAX_LINE_CHARACTERS} characters"
        )
    return value


def _cue_sort_key(cue: dict[str, Any]) -> tuple[int, int, int]:
    branch_rank = {"common": 0, "zero": 1, "rc_only": 2}
    return cue["start_ms"], cue["end_ms"], branch_rank[cue["branch"]]


def validate_contract(value: Any) -> dict[str, Any]:
    """Return a validated copy of the exact schema-v1 caption contract."""
    root = _require_exact_keys(
        value, {"schema_version", "timebase", "cues"}, "caption source"
    )
    if type(root["schema_version"]) is not int or root["schema_version"] != SCHEMA_VERSION:
        raise CaptionContractError(
            f"caption source schema_version must be {SCHEMA_VERSION}"
        )
    if root["timebase"] != TIMEBASE:
        raise CaptionContractError(f"caption source timebase must be {TIMEBASE}")
    raw_cues = root["cues"]
    if not isinstance(raw_cues, list) or not raw_cues:
        raise CaptionContractError("caption source cues must be a non-empty array")

    cues: list[dict[str, Any]] = []
    identities: set[tuple[str, int, int]] = set()
    for ordinal, raw_cue in enumerate(raw_cues):
        cue = _require_exact_keys(
            raw_cue, {"branch", "start_ms", "end_ms", "lines"}, f"cue {ordinal}"
        )
        branch = cue["branch"]
        start_ms = cue["start_ms"]
        end_ms = cue["end_ms"]
        if not isinstance(branch, str) or branch not in ALLOWED_CUE_BRANCHES:
            raise CaptionContractError(f"cue {ordinal} has an unsupported branch")
        if (
            type(start_ms) is not int
            or type(end_ms) is not int
            or start_ms < 0
            or end_ms <= start_ms
            or end_ms > MAX_CUE_END_MS
        ):
            raise CaptionContractError(f"cue {ordinal} has invalid millisecond bounds")
        duration_ms = end_ms - start_ms
        if not MIN_CUE_DURATION_MS <= duration_ms <= MAX_CUE_DURATION_MS:
            raise CaptionContractError(f"cue {ordinal} has an invalid display duration")
        raw_lines = cue["lines"]
        if not isinstance(raw_lines, list) or len(raw_lines) != 2:
            raise CaptionContractError(f"cue {ordinal} must contain exactly two lines")
        lines = [
            _require_plain_line(line, f"cue {ordinal} line {line_ordinal}")
            for line_ordinal, line in enumerate(raw_lines, start=1)
        ]
        visible_characters = sum(
            1 for character in "".join(lines) if not character.isspace()
        )
        if visible_characters * 1_000 > duration_ms * MAX_VISIBLE_CHARACTERS_PER_SECOND:
            raise CaptionContractError(f"cue {ordinal} exceeds the reading-density limit")
        identity = (branch, start_ms, end_ms)
        if identity in identities:
            raise CaptionContractError("caption source contains a duplicate cue identity")
        identities.add(identity)
        cues.append(
            {
                "branch": branch,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "lines": lines,
            }
        )

    if cues != sorted(cues, key=_cue_sort_key):
        raise CaptionContractError("caption source cues are not in canonical order")
    branch_specific = {
        branch: [cue for cue in cues if cue["branch"] == branch]
        for branch in BRANCHES
    }
    if any(len(branch_specific[branch]) != 1 for branch in BRANCHES):
        raise CaptionContractError(
            "caption source must contain exactly one cue for each selected branch"
        )
    if {
        (cue["start_ms"], cue["end_ms"])
        for branch in BRANCHES
        for cue in branch_specific[branch]
    } != {
        (
            branch_specific[BRANCHES[0]][0]["start_ms"],
            branch_specific[BRANCHES[0]][0]["end_ms"],
        )
    }:
        raise CaptionContractError("branch-specific cues must occupy the same time window")

    validated = {
        "schema_version": SCHEMA_VERSION,
        "timebase": TIMEBASE,
        "cues": cues,
    }
    for branch in BRANCHES:
        select_cues(validated, branch)
    return validated


def select_cues(contract: dict[str, Any], branch: str) -> list[dict[str, Any]]:
    """Select common cues plus exactly one requested external-evidence branch."""
    if branch not in BRANCHES:
        raise CaptionContractError("caption branch must be zero or rc_only")
    selected = sorted(
        [cue for cue in contract["cues"] if cue["branch"] in {"common", branch}],
        key=_cue_sort_key,
    )
    if not selected:
        raise CaptionContractError("selected caption branch has no cues")
    for previous, current in zip(selected, selected[1:]):
        if current["start_ms"] - previous["end_ms"] < MIN_CUE_GAP_MS:
            raise CaptionContractError(
                "selected caption cues overlap or violate the minimum gap"
            )
    return selected


def _srt_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def render_srt(contract: dict[str, Any], branch: str) -> bytes:
    """Render deterministic UTF-8/LF SRT bytes for one selected branch."""
    blocks: list[str] = []
    for index, cue in enumerate(select_cues(contract, branch), start=1):
        blocks.append(
            "\n".join(
                (
                    str(index),
                    f"{_srt_timestamp(cue['start_ms'])} --> {_srt_timestamp(cue['end_ms'])}",
                    *cue["lines"],
                )
            )
        )
    return ("\n\n".join(blocks) + "\n").encode("utf-8")


def _canonical_selected_cues(contract: dict[str, Any], branch: str) -> bytes:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "branch": branch,
        "cues": select_cues(contract, branch),
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def load_contract(path: Path, expected_sha256: str | None = None) -> tuple[dict[str, Any], str]:
    """Read, digest and strictly validate one regular tracked caption source."""
    if path.is_symlink() or not path.is_file():
        raise CaptionContractError("caption source must be a regular non-symlink file")
    raw = path.read_bytes()
    source_sha256 = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        if SHA256_RE.fullmatch(expected_sha256) is None:
            raise CaptionContractError("caption source expected SHA-256 is invalid")
        if source_sha256 != expected_sha256:
            raise CaptionContractError("caption source SHA-256 mismatch")
    return validate_contract(_decode_strict_json(raw)), source_sha256


def build_branch_evidence(
    path: Path, expected_sha256: str, branch: str
) -> dict[str, Any]:
    """Build stable metadata binding the source, selected cues and rendered SRT."""
    contract, source_sha256 = load_contract(path, expected_sha256)
    selected = select_cues(contract, branch)
    selected_bytes = _canonical_selected_cues(contract, branch)
    srt_bytes = render_srt(contract, branch)
    return {
        "schema_version": SCHEMA_VERSION,
        "source_path": SOURCE_RELATIVE_PATH,
        "source_sha256": source_sha256,
        "selected_branch": branch,
        "selected_cue_count": len(selected),
        "selected_last_cue_end_ms": selected[-1]["end_ms"],
        "selected_cues_sha256": hashlib.sha256(selected_bytes).hexdigest(),
        "srt_sha256": hashlib.sha256(srt_bytes).hexdigest(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch", choices=BRANCHES, required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    contract, source_sha256 = load_contract(
        TRACKED_SOURCE_PATH, args.expected_source_sha256
    )
    srt_bytes = render_srt(contract, args.branch)
    args.output.write_bytes(srt_bytes)
    print(f"caption_source_sha256={source_sha256}")
    print(f"caption_srt_sha256={hashlib.sha256(srt_bytes).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
