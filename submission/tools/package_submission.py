#!/usr/bin/env python3
"""Build and verify the exact 2026 OSS contest upload package.

The organizer upload ZIP is deliberately smaller than the verification set:
it contains only the report original and PDF, plus the duplicate-benefit form
when applicable. Repository, release, SBOM and video artifacts are verified as
external evidence and are never copied into the organizer ZIP.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import importlib.util
import json
import math
import os
import re
import shutil
import ssl
import stat
import subprocess
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo


NOTICE_URL = "https://osscontest.kr/notice/39"
OFFICIAL_REPORT_FILENAME_PREFIX = "2026 오픈소스 개발자대회 결과보고서_"
LEGACY_SUBMISSION_FILENAMES = {
    "RouteContract_2026_OSS_Contest.zip",
    "01_RouteContract_Result_Report.docx",
    "02_RouteContract_Result_Report.pdf",
}
PACKAGE_METADATA_NAME = "PACKAGE-METADATA.json"
PACKAGE_METADATA_SCHEMA_VERSION = 4
CHECKSUMS_NAME = "SHA256SUMS"
SUPPLY_CHAIN_EVIDENCE_NAME = "supply-chain-evidence.json"
MYSQL_CONTAINER_DIGEST = (
    "b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb"
)
MYSQL_DOCUMENTATION_URL = "https://dev.mysql.com/doc/refman/8.4/en/preface.html"
EXPECTED_MYSQL_LICENSE_REVIEW = {
    "action": (
        "re-review immediately if the MySQL OCI digest, selected platform, embedded "
        "LICENSE/INFO_SRC evidence, or test-container use boundary changes; otherwise "
        "resolve, renew with new evidence, or remove the MySQL OCI package-level "
        "license review before the 2026-12-05 expiry"
    ),
    "componentName": "mysql",
    "componentVersion": "8.4.11",
    "expires": "2026-12-05",
    "owner": "RouteContract maintainers",
    "purl": (
        "pkg:oci/mysql@sha256%3A"
        f"{MYSQL_CONTAINER_DIGEST}?repository_url=registry-1.docker.io&tag=8.4.11"
    ),
    "rationaleCode": "MYSQL_OCI_PACKAGE_LICENSE_CONCLUSION_INCOMPLETE",
    "reviewedAt": "2026-08-24",
    "scope": "test-container",
    "status": "manual-review-required",
}
EXPECTED_MYSQL_POLICY_LICENSE_REVIEW = {
    **EXPECTED_MYSQL_LICENSE_REVIEW,
    "documentationUrl": MYSQL_DOCUMENTATION_URL,
    "sha256": MYSQL_CONTAINER_DIGEST,
}
MIN_VIDEO_SECONDS = 173.0
MAX_VIDEO_SECONDS = 175.0
MIN_VIDEO_WIDTH = 1920
MIN_VIDEO_HEIGHT = 1080
MIN_PUBLIC_VIDEO_HEIGHT = 1080
MIN_DECODED_VIDEO_FPS = 20.0
DECODE_DURATION_TOLERANCE_SECONDS = 0.25
MAX_PORTABLE_FILENAME_BYTES = 255
MAX_PUBLIC_ASSET_BYTES = 250 * 1024 * 1024
# These are validation ceilings for already captured subprocess output and
# bounded network reads; ``run`` itself does not stream-limit stdout.
MAX_JSON_TOOL_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_PUBLIC_JSON_RESPONSE_BYTES = 8_000_000
MAX_PUBLIC_ACTIVATION_RECORD_BYTES = 1024 * 1024
MAX_ISSUE_ENUMERATION_PAGES = 100
A4_SHORT_EDGE_POINTS = 595.3
A4_LONG_EDGE_POINTS = 841.9
PAGE_SIZE_TOLERANCE_POINTS = 1.0
MAX_PDF_VALUE_INTERLEAVED_CHARACTERS = 256
MAX_PDF_BLOCK_ROW_INTERLEAVED_CHARACTERS = 64
APPROVED_ISSUE_FORM_SHA256_BY_FILENAME = {
    "independent-rc1-install.yml": (
        "0f4afc4ac098e0ee425704168f045352b3e2a77f856a0ae7438a9f93d955e583"
    ),
    "independent-rc2-install.yml": (
        "518c4102b9a0f7725b46b825ad5952263b3418bdb07b0164c54a037d902e7f8a"
    ),
}
APPROVED_REPORT_FONTCONFIG_SHA256 = (
    "1aad4c0015115d649ca8d3be015141539fd5f037445408a8ee14a0306af6c5d1"
)
KST = timezone(timedelta(hours=9))
SUBMISSION_DEADLINE = datetime(2026, 8, 27, 18, 0, 0, tzinfo=KST)
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
TEST_SUMMARY_FORMAT = "routecontract-test-summary-v1"
PUBLIC_EXTERNAL_EVIDENCE_OWNER_ATTESTATION = (
    "I reviewed the external-evidence window and confirm that no eligible outcome "
    "or evidence Issue was maintainer-edited, deleted, hidden, transferred, or "
    "knowingly omitted."
)
NO_RUNTIME_AI_DISCLOSURE = "runtime에는 AI 모델·데이터셋·외부 AI API가 없다."
WORDPROCESSINGML_NAMESPACE = (
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
)
DOCX_REVISION_IDENTIFIER_ELEMENT_TAGS = frozenset(
    f"{{{WORDPROCESSINGML_NAMESPACE}}}{local_name}"
    for local_name in ("rsids", "rsidRoot", "rsid")
)

EXPECTED_RELEASE_TEST_SUITES = {
    "io.github.ym0506.routecontract.RouteContractTest": 18,
    "io.github.ym0506.routecontract.example.DataSourceProxyComparisonMySqlTest": 1,
    "io.github.ym0506.routecontract.example.FailureBoundaryMySqlTest": 1,
    "io.github.ym0506.routecontract.example.ObservedExecutionRegressionCorpusMySqlTest": 7,
    "io.github.ym0506.routecontract.example.OperationCorrelationMySqlTest": 5,
    "io.github.ym0506.routecontract.internal.ShardingSphere553PreflightTest": 3,
    "io.github.ym0506.routecontract.manifest.ObservedExecutionManifestTest": 17,
}

PLACEHOLDER_RE = re.compile(r"\[\[[^\]]+\]\]")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
TAG_RE = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+")
SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,62}")
REPOSITORY_RE = re.compile(
    r"https://github\.com/(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))"
    r"/(?P<repo>[A-Za-z0-9_.-]+)"
)
YOUTUBE_RE = re.compile(
    r"https://www\.youtube\.com/watch\?v=(?P<id>[A-Za-z0-9_-]{11})"
)
PORTABLE_FILENAME_FORBIDDEN = frozenset('<>:"/\\|?*')
SENSITIVE_VIDEO_METADATA_TAGS = frozenset(
    {
        "album_artist",
        "artist",
        "author",
        "comment",
        "description",
        "device",
        "gpscoordinates",
        "location",
        "location-eng",
        "make",
        "model",
        "com.apple.quicktime.artist",
        "com.apple.quicktime.author",
        "com.apple.quicktime.comment",
        "com.apple.quicktime.description",
        "com.apple.quicktime.location.iso6709",
        "com.apple.quicktime.location.name",
        "com.apple.quicktime.make",
        "com.apple.quicktime.model",
    }
)
SENSITIVE_VIDEO_METADATA_PREFIXES = (
    "com.apple.quicktime.location.",
)
UPSTREAM_ISSUE_38456_URL = "https://github.com/apache/shardingsphere/issues/38456"


class GateError(RuntimeError):
    """A final-submission invariant was not satisfied."""


def load_github_cli_release_safety() -> Any:
    """Load the repository's single fail-closed GitHub CLI safety module."""
    path = Path(__file__).resolve().parents[2] / "scripts/gh_cli_release_safety.py"
    spec = importlib.util.spec_from_file_location(
        "routecontract_gh_cli_release_safety", path
    )
    if spec is None or spec.loader is None:
        raise GateError("could not load the GitHub CLI release-safety module")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError):
        raise GateError("could not load the GitHub CLI release-safety module") from None
    return module


GITHUB_CLI_RELEASE_SAFETY = load_github_cli_release_safety()


def load_report_content_contract() -> Any:
    """Load the pure-stdlib structured external-evidence contract."""
    path = Path(__file__).resolve().parent / "report_content_contract.py"
    spec = importlib.util.spec_from_file_location(
        "routecontract_report_content_contract", path
    )
    if spec is None or spec.loader is None:
        raise GateError("could not load the report-content contract")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError):
        raise GateError("could not load the report-content contract") from None
    return module


REPORT_CONTENT_CONTRACT = load_report_content_contract()


def load_video_caption_contract() -> Any:
    """Load the pure-stdlib caption-source validator and SRT renderer."""
    path = Path(__file__).resolve().parent / "video_caption_contract.py"
    spec = importlib.util.spec_from_file_location(
        "routecontract_video_caption_contract", path
    )
    if spec is None or spec.loader is None:
        raise GateError("could not load the video-caption contract")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError):
        raise GateError("could not load the video-caption contract") from None
    return module


VIDEO_CAPTION_CONTRACT = load_video_caption_contract()
VIDEO_CAPTION_SOURCE_PATH = VIDEO_CAPTION_CONTRACT.TRACKED_SOURCE_PATH


def _decode_strict_json(
    data: str | bytes,
    failure_message: str,
    *,
    maximum_bytes: int | None = None,
) -> Any:
    try:
        return REPORT_CONTENT_CONTRACT.decode_strict_json(
            data, maximum_bytes=maximum_bytes
        )
    except ValueError:
        raise GateError(failure_message) from None


def load_rc_activation_record_validator() -> Any:
    """Load the existing bounded GitHub-download and workflow-ZIP validator."""
    path = Path(__file__).resolve().parents[2] / "scripts/validate-rc-activation-record.py"
    module_name = "routecontract_rc_activation_record_validator"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise GateError("could not load the RC activation-record validator")
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves forward annotations through sys.modules while loading.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError):
        sys.modules.pop(module_name, None)
        raise GateError("could not load the RC activation-record validator") from None
    return module


RC_ACTIVATION_RECORD_VALIDATOR = load_rc_activation_record_validator()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--report-pdf", type=Path, required=True)
    parser.add_argument("--video-file", type=Path, required=True)
    parser.add_argument("--release-evidence-dir", type=Path, required=True)
    parser.add_argument("--release-evidence-artifact", type=Path, required=True)
    parser.add_argument("--duplicate-benefit-confirmation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--builder-python",
        type=Path,
        # ``python3`` is commonly a symlink (including the python.org macOS
        # installer).  Canonicalize only this trusted current-interpreter
        # default so the later user-input symlink checks remain fail-closed.
        default=Path(sys.executable).resolve(),
        help="Python with python-docx, Pillow and lxml; defaults to this interpreter",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def absolute_without_resolving(path: Path, label: str) -> Path:
    expanded = path.expanduser()
    if ".." in expanded.parts:
        raise GateError(f"{label} must not contain parent traversal: {path}")
    return expanded if expanded.is_absolute() else Path.cwd() / expanded


def reject_symlink_components(
    path: Path, label: str, *, allow_missing_tail: bool = False
) -> Path:
    absolute = absolute_without_resolving(path, label)
    parts = absolute.parts
    current = Path(parts[0])
    for part in parts[1:]:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            if allow_missing_tail:
                break
            raise GateError(f"{label} path component does not exist: {current}") from None
        if stat.S_ISLNK(mode):
            raise GateError(f"{label} must not use a symlink component: {current}")
    return Path(os.path.abspath(absolute))


def require_file(path: Path, label: str) -> Path:
    resolved = reject_symlink_components(path, label)
    if not resolved.is_file():
        raise GateError(f"{label} is missing or not a regular file: {resolved}")
    return resolved


def require_python_interpreter(path: Path, label: str) -> Path:
    """Allow only the final symlink used by a standard virtual environment."""
    absolute = absolute_without_resolving(path, label)
    reject_symlink_components(absolute.parent, f"{label} parent")
    try:
        final_mode = os.lstat(absolute).st_mode
    except FileNotFoundError:
        raise GateError(f"{label} is missing: {absolute}") from None
    if not (stat.S_ISREG(final_mode) or stat.S_ISLNK(final_mode)):
        raise GateError(f"{label} is not a regular file or final symlink: {absolute}")
    try:
        target = absolute.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise GateError(f"{label} final symlink cannot be resolved: {error}") from error
    if not target.is_file() or not os.access(target, os.X_OK):
        raise GateError(f"{label} target is not an executable regular file: {target}")
    # Return the unresolved venv path: Python uses it to discover pyvenv.cfg.
    return Path(os.path.abspath(absolute))


def require_directory(path: Path, label: str) -> Path:
    resolved = reject_symlink_components(path, label)
    if not resolved.is_dir():
        raise GateError(f"{label} is missing or not a directory: {resolved}")
    return resolved


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
    failure_label: str | None = None,
) -> str:
    try:
        process = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
        if failure_label is not None:
            raise GateError(f"{failure_label} could not be completed") from None
        raise
    if process.returncode != 0:
        if failure_label is not None:
            raise GateError(f"{failure_label} failed")
        rendered = " ".join(command)
        detail = (process.stderr or process.stdout).strip()
        raise GateError(f"command failed ({process.returncode}): {rendered}\n{detail}")
    return process.stdout


def load_json(
    path: Path, label: str, *, maximum_bytes: int = 1024 * 1024
) -> dict[str, Any]:
    try:
        if path.stat().st_size > maximum_bytes:
            raise GateError(f"{label} exceeds the {maximum_bytes}-byte safety limit")
        raw = path.read_bytes()
        if len(raw) > maximum_bytes:
            raise GateError(f"{label} exceeds the {maximum_bytes}-byte safety limit")
    except GateError:
        raise
    except OSError:
        raise GateError(f"invalid {label}: input is unavailable") from None
    value = _decode_strict_json(
        raw,
        f"invalid {label}: strict UTF-8 JSON is required",
        maximum_bytes=maximum_bytes,
    )
    if not isinstance(value, dict):
        raise GateError(f"{label} must be a JSON object")
    return value


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def reject_placeholders(value: Any, label: str) -> None:
    placeholder_count = sum(_unresolved_gate_count(text) for text in iter_strings(value))
    if placeholder_count:
        raise GateError(
            f"{label} has unresolved [[...]] gates (count={placeholder_count})"
        )


def _unresolved_gate_count(text: str) -> int:
    complete = list(PLACEHOLDER_RE.finditer(text))
    fragments = PLACEHOLDER_RE.sub("", text)
    return len(complete) + fragments.count("[[") + fragments.count("]]")


def validate_and_materialize_report_content(
    content: dict[str, Any], manifest: dict[str, Any], *, current_utc: datetime
) -> dict[str, Any]:
    """Bind one generated external-evidence branch to the final package identity."""
    try:
        materialized = REPORT_CONTENT_CONTRACT.materialize_external_evidence(
            content,
            allow_placeholders=False,
            expected_final_tag=manifest["project"]["tag"],
            expected_repository_url=manifest["project"]["repository_url"],
            current_utc=current_utc,
        )
    except (TypeError, ValueError) as error:
        raise GateError(f"invalid report external-evidence contract: {error}") from error
    reject_placeholders(materialized, "report content")
    evidence_id_count = REPORT_CONTENT_CONTRACT.count_reader_facing_evidence_ids(
        materialized
    )
    if evidence_id_count:
        raise GateError(
            "report content contains reader-facing audit evidence IDs "
            f"(count={evidence_id_count})"
        )
    return materialized


def require_exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        missing = expected - actual
        unexpected = actual - expected
        raise GateError(
            f"{label} keys do not match schema; missing_count={len(missing)}, "
            f"unexpected_count={len(unexpected)}"
        )
    return value


def object_or_empty(value: Any) -> dict[str, Any]:
    """Return mappings unchanged and make malformed nested API values fail normally."""
    return value if isinstance(value, dict) else {}


def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise GateError(f"{label} must be a lowercase 64-character SHA-256")
    return value


def parse_repository_url(url: Any) -> tuple[str, str, str]:
    if not isinstance(url, str):
        raise GateError("project.repository_url must be a string")
    match = REPOSITORY_RE.fullmatch(url)
    if match is None or url.endswith(".git"):
        raise GateError(
            "project.repository_url must be one canonical public HTTPS GitHub repository URL"
        )
    return match.group("owner"), match.group("repo"), url


def require_portable_filename_component(value: Any, label: str) -> str:
    """Validate one registration value without silently changing it."""
    if not isinstance(value, str) or not value:
        raise GateError(f"{label} must be a non-empty string")
    if value != unicodedata.normalize("NFC", value):
        raise GateError(f"{label} must already use Unicode NFC normalization")
    if value != value.strip():
        raise GateError(f"{label} must not have leading or trailing whitespace")
    if value in {".", ".."} or value.endswith((".", " ")):
        raise GateError(f"{label} is not a portable filename component")
    if any(
        character in PORTABLE_FILENAME_FORBIDDEN
        or unicodedata.category(character).startswith("C")
        for character in value
    ):
        raise GateError(
            f"{label} contains a control, path separator or non-portable filename character"
        )
    return value


def require_registration_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise GateError(f"{label} must be a non-empty string")
    if value != unicodedata.normalize("NFC", value):
        raise GateError(f"{label} must already use Unicode NFC normalization")
    if value != value.strip():
        raise GateError(f"{label} must not have leading or trailing whitespace")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise GateError(f"{label} contains a control or formatting character")
    return value


def official_submission_filenames(identity: dict[str, Any]) -> dict[str, str]:
    receipt_number = require_portable_filename_component(
        identity["receipt_number"], "submission_identity.receipt_number"
    )
    team_name = require_portable_filename_component(
        identity["team_name"], "submission_identity.team_name"
    )
    basename = f"{OFFICIAL_REPORT_FILENAME_PREFIX}{receipt_number}({team_name})"
    filenames = {
        "basename": basename,
        "docx": f"{basename}.docx",
        "pdf": f"{basename}.pdf",
        "zip": f"{basename}.zip",
    }
    for label, filename in filenames.items():
        if label == "basename":
            continue
        if PurePosixPath(filename).name != filename or "\\" in filename:
            raise GateError(f"derived official {label} filename is not a safe basename")
        if len(filename.encode("utf-8")) > MAX_PORTABLE_FILENAME_BYTES:
            raise GateError(
                f"derived official {label} filename exceeds "
                f"{MAX_PORTABLE_FILENAME_BYTES} UTF-8 bytes"
            )
    return filenames


def validate_submission_identity_matches_content(
    content: dict[str, Any], manifest: dict[str, Any]
) -> None:
    metadata = content.get("metadata")
    if not isinstance(metadata, dict):
        raise GateError("report content metadata must be an object")
    identity = manifest["submission_identity"]
    field_map = {
        "team_name": "team_name",
        "registered_project_name": "project_name",
        "team_size": "team_size",
        "division": "division",
        "task_type": "task_type",
    }
    for identity_key, metadata_key in field_map.items():
        if metadata.get(metadata_key) != identity[identity_key]:
            raise GateError(
                f"report content metadata.{metadata_key} must exactly match "
                f"submission_identity.{identity_key}"
            )


def validate_video_external_evidence_branch_matches_content(
    content: dict[str, Any], manifest: dict[str, Any]
) -> None:
    branch = object_or_empty(content.get("external_evidence")).get("branch")
    if manifest["video"]["external_evidence_branch"] != branch:
        raise GateError(
            "video.external_evidence_branch must exactly match the generated "
            "report external-evidence branch"
        )


def video_caption_branch_evidence(
    expected_source_sha256: str, branch: str
) -> dict[str, Any]:
    """Bind the fixed tracked cue source to one deterministic selected SRT."""
    try:
        return VIDEO_CAPTION_CONTRACT.build_branch_evidence(
            VIDEO_CAPTION_SOURCE_PATH, expected_source_sha256, branch
        )
    except (OSError, ValueError):
        raise GateError(
            "video.caption_contract does not match the strict tracked caption source"
        ) from None


def manifest_video_caption_evidence(manifest: dict[str, Any]) -> dict[str, Any]:
    """Revalidate and materialize caption evidence from a validated manifest."""
    video = manifest["video"]
    return video_caption_branch_evidence(
        video["caption_contract"]["source_sha256"],
        video["external_evidence_branch"],
    )


def require_caption_cues_fit_duration(
    caption_evidence: dict[str, Any], duration_seconds: float, label: str
) -> None:
    """Require the selected branch's final cue to fit in an observed duration."""
    last_cue_end_ms = caption_evidence["selected_last_cue_end_ms"]
    if duration_seconds * 1_000 < last_cue_end_ms:
        raise GateError(
            f"{label} ends before the selected caption branch's final cue"
        )


def validate_manifest(data: dict[str, Any]) -> dict[str, Any]:
    require_exact_keys(
        data,
        {
            "schema_version",
            "official_notice_url",
            "submission_identity",
            "project",
            "report",
            "video",
            "release_evidence",
            "participant_attestations",
            "duplicate_benefit_confirmation",
        },
        "manifest",
    )
    reject_placeholders(data, "manifest")
    if (
        isinstance(data["schema_version"], bool)
        or not isinstance(data["schema_version"], int)
        or data["schema_version"] != 5
    ):
        raise GateError("manifest.schema_version must be 5")
    if data["official_notice_url"] != NOTICE_URL:
        raise GateError(f"official_notice_url must be {NOTICE_URL}")

    identity = require_exact_keys(
        data["submission_identity"],
        {
            "receipt_number",
            "team_name",
            "registered_project_name",
            "team_size",
            "division",
            "task_type",
        },
        "submission_identity",
    )
    official_filenames = official_submission_filenames(identity)
    for key in ("registered_project_name", "team_size", "division", "task_type"):
        require_registration_text(identity[key], f"submission_identity.{key}")

    project = require_exact_keys(
        data["project"],
        {"slug", "repository_url", "commit", "tag", "ci_run_url", "release_url"},
        "project",
    )
    if not isinstance(project["slug"], str) or SLUG_RE.fullmatch(project["slug"]) is None:
        raise GateError("project.slug must be lowercase ASCII letters, digits and hyphens")
    owner, repository, repository_url = parse_repository_url(project["repository_url"])
    commit = project["commit"]
    tag = project["tag"]
    if not isinstance(commit, str) or COMMIT_RE.fullmatch(commit) is None:
        raise GateError("project.commit must be a lowercase 40-character Git commit SHA")
    if not isinstance(tag, str) or TAG_RE.fullmatch(tag) is None:
        raise GateError("project.tag must be a stable vMAJOR.MINOR.PATCH release tag")
    expected_ci_prefix = f"{repository_url}/actions/runs/"
    if (
        not isinstance(project["ci_run_url"], str)
        or not project["ci_run_url"].startswith(expected_ci_prefix)
        or not project["ci_run_url"][len(expected_ci_prefix) :].isdigit()
    ):
        raise GateError("project.ci_run_url must be a public Actions run for the repository")
    if project["release_url"] != f"{repository_url}/releases/tag/{tag}":
        raise GateError("project.release_url must be the final tag's canonical GitHub Release URL")

    report = require_exact_keys(
        data["report"],
        {"docx_sha256", "pdf_sha256", "runtime_ai_attachment"},
        "report",
    )
    require_digest(report["docx_sha256"], "report.docx_sha256")
    require_digest(report["pdf_sha256"], "report.pdf_sha256")
    if report["runtime_ai_attachment"] != "not_applicable":
        raise GateError(
            "RouteContract has no runtime AI path; report.runtime_ai_attachment must be not_applicable"
        )

    video = require_exact_keys(
        data["video"],
        {
            "youtube_url",
            "title",
            "duration_seconds",
            "local_file_sha256",
            "external_evidence_branch",
            "caption_contract",
        },
        "video",
    )
    if not isinstance(video["youtube_url"], str) or YOUTUBE_RE.fullmatch(
        video["youtube_url"]
    ) is None:
        raise GateError("video.youtube_url must be a canonical YouTube watch URL")
    if not isinstance(video["title"], str) or not video["title"].strip():
        raise GateError("video.title must be non-empty")
    if isinstance(video["duration_seconds"], bool) or not isinstance(
        video["duration_seconds"], (int, float)
    ):
        raise GateError("video.duration_seconds must be a number from ffprobe")
    duration = float(video["duration_seconds"])
    if not MIN_VIDEO_SECONDS <= duration <= MAX_VIDEO_SECONDS:
        raise GateError(
            "video.duration_seconds must be from 173 through 175 seconds inclusive"
        )
    require_digest(video["local_file_sha256"], "video.local_file_sha256")
    branch = video["external_evidence_branch"]
    if not isinstance(branch, str) or branch not in {"rc_only", "zero"}:
        raise GateError("video.external_evidence_branch must be rc_only or zero")
    caption_contract = require_exact_keys(
        video["caption_contract"],
        {"schema_version", "source_path", "source_sha256"},
        "video.caption_contract",
    )
    if (
        type(caption_contract["schema_version"]) is not int
        or caption_contract["schema_version"] != VIDEO_CAPTION_CONTRACT.SCHEMA_VERSION
    ):
        raise GateError(
            "video.caption_contract.schema_version must be "
            f"{VIDEO_CAPTION_CONTRACT.SCHEMA_VERSION}"
        )
    if caption_contract["source_path"] != VIDEO_CAPTION_CONTRACT.SOURCE_RELATIVE_PATH:
        raise GateError(
            "video.caption_contract.source_path must be "
            f"{VIDEO_CAPTION_CONTRACT.SOURCE_RELATIVE_PATH}"
        )
    require_digest(
        caption_contract["source_sha256"],
        "video.caption_contract.source_sha256",
    )
    caption_evidence = video_caption_branch_evidence(
        caption_contract["source_sha256"], branch
    )
    require_caption_cues_fit_duration(caption_evidence, duration, "manifest video")

    evidence = require_exact_keys(
        data["release_evidence"],
        {
            "workflow_artifact_id",
            "workflow_artifact_sha256",
            "source_archive_filename",
            "source_archive_sha256",
            "aggregate_sbom_json_sha256",
            "aggregate_sbom_xml_sha256",
            "signature_filenames",
        },
        "release_evidence",
    )
    filename = evidence["source_archive_filename"]
    artifact_id = evidence["workflow_artifact_id"]
    if isinstance(artifact_id, bool) or not isinstance(artifact_id, int) or artifact_id <= 0:
        raise GateError("release_evidence.workflow_artifact_id must be a positive integer")
    require_digest(
        evidence["workflow_artifact_sha256"],
        "release_evidence.workflow_artifact_sha256",
    )
    expected_source_filename = f"{project['slug']}-{tag[1:]}-source.zip"
    if (
        not isinstance(filename, str)
        or PurePosixPath(filename).name != filename
        or "\\" in filename
        or filename != expected_source_filename
    ):
        raise GateError(
            "release_evidence.source_archive_filename must exactly match the final tag: "
            + expected_source_filename
        )
    for key in (
        "source_archive_sha256",
        "aggregate_sbom_json_sha256",
        "aggregate_sbom_xml_sha256",
    ):
        require_digest(evidence[key], f"release_evidence.{key}")
    signatures = evidence["signature_filenames"]
    if not isinstance(signatures, list) or any(not isinstance(item, str) for item in signatures):
        raise GateError("release_evidence.signature_filenames must be a list of basenames")
    if len(signatures) != len(set(signatures)):
        raise GateError("release_evidence.signature_filenames contains duplicates")
    if signatures:
        raise GateError(
            "v0.1 release evidence does not implement signature generation; "
            "release_evidence.signature_filenames must be empty"
        )
    for signature in signatures:
        if (
            PurePosixPath(signature).name != signature
            or "\\" in signature
            or not signature.endswith((".asc", ".sig"))
        ):
            raise GateError(f"invalid explicit signature filename: {signature}")

    attestations = require_exact_keys(
        data["participant_attestations"],
        {
            "registration_matches_report",
            "single_entry_per_participant_confirmed",
            "duplicate_benefit_status_reviewed",
            "ai_assistance_scope_confirmed",
            "core_behavior_boundaries_artifacts_and_dependency_roles_reviewed_and_explainable",
            "report_free_text_contains_no_external_evidence_claims",
            "report_free_text_privacy_reviewed",
            "public_external_evidence_history_and_maintainer_edits_reviewed",
            "source_and_dependency_licenses_reviewed",
            "final_pdf_visual_qa_completed",
            "final_local_video_actual_screen_caption_watchthrough_completed",
            "final_public_video_frame_audio_caption_equivalence_review_completed",
            "five_year_public_repository_visibility_obligation_if_selected_accepted",
            "owner_voice_ai_assistance_disclosed_and_participant_reviewed",
            "maintenance_order_and_period_confirmed",
            "origin_and_prior_work_statement_confirmed",
        },
        "participant_attestations",
    )
    incomplete_attestations = sorted(
        key for key, value in attestations.items() if value is not True
    )
    if incomplete_attestations:
        raise GateError(
            "participant attestations must be explicitly true after human review: "
            + ", ".join(incomplete_attestations)
        )

    duplicate = require_exact_keys(
        data["duplicate_benefit_confirmation"],
        {"status", "sha256"},
        "duplicate_benefit_confirmation",
    )
    if duplicate["status"] not in {"not_applicable", "required"}:
        raise GateError(
            "duplicate_benefit_confirmation.status must be not_applicable or required"
        )
    if duplicate["status"] == "not_applicable":
        if duplicate["sha256"] is not None:
            raise GateError("duplicate-benefit SHA must be null when it is not applicable")
    else:
        raise GateError(
            "duplicate-benefit status=required is disabled until the organizer's exact "
            "source form and identity/title contract are locally validated"
        )

    return {
        **data,
        "github_owner": owner,
        "github_repository": repository,
        "official_submission_filenames": official_filenames,
    }


def validate_submission_deadline(now: datetime | None = None) -> None:
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise GateError("submission deadline check requires a timezone-aware clock")
    if observed.astimezone(KST) >= SUBMISSION_DEADLINE:
        raise GateError(
            "the official submission deadline has passed: 2026-08-27 18:00 KST"
        )


def assert_ignored_if_inside_repository(path: Path, repository_root: Path, label: str) -> None:
    try:
        path.relative_to(repository_root)
    except ValueError:
        return
    process = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", str(path)],
        cwd=repository_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if process.returncode != 0:
        raise GateError(
            f"{label} contains final/private values but is not gitignored: {path}"
        )


def canonical_remote(url: str) -> tuple[str, str] | None:
    patterns = (
        re.compile(r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$"),
        re.compile(r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$"),
        re.compile(r"ssh://git@github\.com/([^/]+)/(.+?)(?:\.git)?$"),
    )
    for pattern in patterns:
        match = pattern.fullmatch(url.strip())
        if match:
            return match.group(1).casefold(), match.group(2).casefold()
    return None


def validate_remote_tag_identity(
    repository_root: Path, manifest: dict[str, Any]
) -> None:
    """Require origin to preserve the exact local annotated tag object and peel."""
    project = manifest["project"]
    local_tag_object = run(
        ["git", "rev-parse", f"refs/tags/{project['tag']}"], cwd=repository_root
    ).strip()
    git_env = os.environ.copy()
    git_env["GIT_TERMINAL_PROMPT"] = "0"
    remote_tags = run(
        [
            "git",
            "ls-remote",
            "--tags",
            "origin",
            f"refs/tags/{project['tag']}",
            f"refs/tags/{project['tag']}^{{}}",
        ],
        cwd=repository_root,
        env=git_env,
    )
    remote_refs: dict[str, str] = {}
    for line in remote_tags.splitlines():
        fields = line.split()
        if len(fields) != 2 or fields[1] in remote_refs:
            raise GateError("origin returned an invalid or duplicate final-tag reference")
        remote_refs[fields[1]] = fields[0]
    base_ref = f"refs/tags/{project['tag']}"
    peeled_ref = f"{base_ref}^{{}}"
    if set(remote_refs) != {base_ref, peeled_ref}:
        raise GateError("origin must publish the exact annotated final tag and peeled commit")
    if (
        remote_refs[base_ref] != local_tag_object
        or remote_refs[peeled_ref] != project["commit"]
    ):
        raise GateError(
            "origin final tag object or peeled commit does not match the local final tag"
        )


def validate_git_state(repository_root: Path, manifest: dict[str, Any]) -> None:
    project = manifest["project"]
    owner = manifest["github_owner"]
    repository = manifest["github_repository"]
    expected_remote = (owner.casefold(), repository.casefold())
    actual_root = Path(run(["git", "rev-parse", "--show-toplevel"], cwd=repository_root).strip())
    if actual_root.resolve() != repository_root:
        raise GateError(f"repository root mismatch: expected {repository_root}, got {actual_root}")
    head = run(["git", "rev-parse", "HEAD"], cwd=repository_root).strip()
    if head != project["commit"]:
        raise GateError(f"HEAD {head} does not match final manifest commit {project['commit']}")
    status_output = run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=repository_root
    )
    if status_output.strip():
        raise GateError("repository must be clean before final packaging:\n" + status_output.rstrip())
    origin = run(["git", "remote", "get-url", "origin"], cwd=repository_root).strip()
    if canonical_remote(origin) != expected_remote:
        raise GateError("origin does not match the representative repository owner/name")
    tag_type = run(
        ["git", "cat-file", "-t", f"refs/tags/{project['tag']}"], cwd=repository_root
    ).strip()
    if tag_type != "tag":
        raise GateError("final release tag must be an annotated tag")
    tagged_commit = run(
        ["git", "rev-parse", f"refs/tags/{project['tag']}^{{commit}}"], cwd=repository_root
    ).strip()
    if tagged_commit != project["commit"]:
        raise GateError("final tag does not point to the manifest commit")

    build_text = (repository_root / "build.gradle").read_text(encoding="utf-8")
    group_match = re.search(r"(?m)^group\s*=\s*['\"]([^'\"]+)['\"]\s*$", build_text)
    expected_group = f"io.github.{owner.casefold()}.routecontract"
    if group_match is None or group_match.group(1) != expected_group:
        raise GateError(
            f"Maven group must match the final GitHub owner: expected {expected_group}"
        )
    version_match = re.search(r"(?m)^version\s*=\s*['\"]([^'\"]+)['\"]\s*$", build_text)
    if version_match is None:
        raise GateError("could not read the release version from build.gradle")
    project_version = version_match.group(1)
    if project_version.endswith("-SNAPSHOT") or project["tag"] != f"v{project_version}":
        raise GateError(
            f"tag/version mismatch or snapshot release: tag={project['tag']}, version={project_version}"
        )

    validate_remote_tag_identity(repository_root, manifest)


def zip_flat_file_metadata(path: Path, label: str) -> dict[str, dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    try:
        with ZipFile(path) as archive:
            for info in archive.infolist():
                pure = PurePosixPath(info.filename)
                if (
                    info.is_dir()
                    or pure.is_absolute()
                    or len(pure.parts) != 1
                    or ".." in pure.parts
                    or "\\" in info.filename
                ):
                    raise GateError(f"{label} must contain only flat regular files: {info.filename}")
                unix_mode = info.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise GateError(f"{label} contains a symlink: {info.filename}")
                if info.filename in files:
                    raise GateError(f"{label} contains a duplicate member: {info.filename}")
                digest = hashlib.sha256()
                with archive.open(info) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                files[info.filename] = {"sha256": digest.hexdigest(), "size": info.file_size}
    except (BadZipFile, OSError, ValueError) as error:
        if isinstance(error, GateError):
            raise
        raise GateError(f"could not inspect {label}: {error}") from error
    if not files:
        raise GateError(f"{label} is empty")
    return files


def validate_workflow_artifact_archive(
    artifact_zip: Path,
    evidence_dir: Path,
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    expected_digest = manifest["release_evidence"]["workflow_artifact_sha256"]
    actual_digest = sha256(artifact_zip)
    if actual_digest != expected_digest:
        raise GateError(
            f"workflow artifact ZIP checksum mismatch: expected {expected_digest}, got {actual_digest}"
        )
    members = zip_flat_file_metadata(artifact_zip, "workflow artifact ZIP")
    if sha256(artifact_zip) != actual_digest:
        raise GateError("workflow artifact ZIP changed during validation")
    directory_files = {
        path.name: {"sha256": sha256(path), "size": path.stat().st_size}
        for path in evidence_dir.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    if members != directory_files:
        raise GateError(
            "release evidence directory is not byte-identical to the workflow artifact ZIP; "
            f"archive_only={sorted(set(members) - set(directory_files))}, "
            f"directory_only={sorted(set(directory_files) - set(members))}"
        )
    return (
        {
            "workflow_artifact_id": manifest["release_evidence"]["workflow_artifact_id"],
            "workflow_artifact_sha256": actual_digest,
            "workflow_artifact_size": artifact_zip.stat().st_size,
            "workflow_artifact_file_count": len(members),
        },
        members,
    )


def parse_checksum_manifest(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/\\]+)", line)
        if match is None:
            raise GateError(f"invalid SHA256SUMS line {line_number}: {line!r}")
        digest, filename = match.groups()
        if filename in checksums or filename == CHECKSUMS_NAME:
            raise GateError(f"duplicate or recursive SHA256SUMS entry: {filename}")
        checksums[filename] = digest
    if not checksums:
        raise GateError("release SHA256SUMS is empty")
    return checksums


def expected_release_test_summary(revision: str) -> str:
    lines = [
        f"format={TEST_SUMMARY_FORMAT}",
        f"revision={revision}",
        f"suite_count={len(EXPECTED_RELEASE_TEST_SUITES)}",
        f"test_count={sum(EXPECTED_RELEASE_TEST_SUITES.values())}",
        "failure_count=0",
        "error_count=0",
        "skipped_count=0",
    ]
    lines.extend(
        f"suite={suite}|tests={EXPECTED_RELEASE_TEST_SUITES[suite]}|"
        "failures=0|errors=0|skipped=0"
        for suite in sorted(EXPECTED_RELEASE_TEST_SUITES)
    )
    return "\n".join(lines) + "\n"


def validate_release_test_summary(path: Path, revision: str) -> dict[str, Any]:
    if path.stat().st_size > 16 * 1024:
        raise GateError("release test summary unexpectedly exceeds 16 KiB")
    try:
        observed = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise GateError(f"release test summary is not valid UTF-8: {error}") from error
    if observed != expected_release_test_summary(revision):
        raise GateError(
            "release test summary must exactly identify the final revision and the "
            "expected 7-suite/52-test all-passing, non-skipped result"
        )
    return {
        "format": TEST_SUMMARY_FORMAT,
        "revision": revision,
        "suite_count": len(EXPECTED_RELEASE_TEST_SUITES),
        "test_count": sum(EXPECTED_RELEASE_TEST_SUITES.values()),
        "failure_count": 0,
        "error_count": 0,
        "skipped_count": 0,
        "sha256": sha256(path),
    }


def load_strict_json(path: Path, label: str, *, maximum_bytes: int = 1024 * 1024) -> dict[str, Any]:
    try:
        if path.stat().st_size > maximum_bytes:
            raise GateError(f"{label} exceeds the {maximum_bytes}-byte safety limit")
        raw = path.read_bytes()
        if len(raw) > maximum_bytes:
            raise GateError(f"{label} exceeds the {maximum_bytes}-byte safety limit")
    except GateError:
        raise
    except OSError:
        raise GateError(f"{label} input is unavailable") from None
    value = _decode_strict_json(
        raw,
        f"{label} must be valid UTF-8 strict JSON",
        maximum_bytes=maximum_bytes,
    )
    if not isinstance(value, dict):
        raise GateError(f"{label} must be a JSON object")
    return value


def require_nonnegative_integer(value: Any, label: str, *, positive: bool = False) -> int:
    minimum = 1 if positive else 0
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "positive" if positive else "non-negative"
        raise GateError(f"{label} must be a {qualifier} integer")
    return value


def validate_supply_chain_evidence(
    path: Path,
    actual_files: dict[str, Path],
    manifest: dict[str, Any],
    repository_root: Path,
) -> dict[str, Any]:
    """Validate the public sanitized scan result and its exact source bindings."""
    evidence = load_strict_json(path, "supply-chain evidence")
    require_exact_keys(
        evidence,
        {
            "exampleProfile",
            "publishedModule",
            "revision",
            "sbom",
            "scanner",
            "schemaVersion",
            "sourceTree",
            "vulnerabilities",
        },
        "supply-chain evidence",
    )
    if type(evidence["schemaVersion"]) is not int or evidence["schemaVersion"] != 1:
        raise GateError("unsupported supply-chain evidence schemaVersion")
    if evidence["revision"] != manifest["project"]["commit"]:
        raise GateError("supply-chain evidence revision does not match the final commit")
    expected_tree = run(
        ["git", "rev-parse", f"{manifest['project']['commit']}^{{tree}}"],
        cwd=repository_root,
    ).strip()
    if evidence["sourceTree"] != expected_tree:
        raise GateError("supply-chain evidence sourceTree does not match the final Git tree")

    aggregate = require_exact_keys(
        evidence["sbom"],
        {
            "componentLicenseCount",
            "inventorySha256",
            "licensePolicy",
            "licenseReviews",
            "mavenPackageCount",
            "policySha256",
            "sha256",
            "unresolvedLicenseReviewCount",
            "xmlComponentCount",
            "xmlSha256",
        },
        "supply-chain evidence sbom",
    )
    if aggregate["licensePolicy"] != "passed":
        raise GateError("supply-chain evidence licensePolicy must be passed")
    for key in ("componentLicenseCount", "mavenPackageCount", "xmlComponentCount"):
        require_nonnegative_integer(
            aggregate[key], f"supply-chain evidence sbom.{key}", positive=True
        )
    for key in ("inventorySha256", "policySha256", "sha256", "xmlSha256"):
        require_digest(aggregate[key], f"supply-chain evidence sbom.{key}")
    unresolved_review_count = require_nonnegative_integer(
        aggregate["unresolvedLicenseReviewCount"],
        "supply-chain evidence sbom.unresolvedLicenseReviewCount",
    )
    if unresolved_review_count != 1:
        raise GateError(
            "supply-chain evidence must retain exactly one unresolved license review"
        )
    expected_aggregate_hashes = {
        "sha256": sha256(actual_files["routecontract-aggregate-cyclonedx.json"]),
        "xmlSha256": sha256(actual_files["routecontract-aggregate-cyclonedx.xml"]),
        "policySha256": sha256(repository_root / "security/supply-chain-policy.json"),
    }
    for key, expected in expected_aggregate_hashes.items():
        if aggregate[key] != expected:
            raise GateError(f"supply-chain evidence sbom.{key} is not source/artifact bound")

    published = require_exact_keys(
        evidence["publishedModule"],
        {
            "componentLicenseCount",
            "dependencyLockSha256",
            "mavenPackageCount",
            "pomDependencyCount",
            "pomSha256",
            "resolvedProfileSha256",
            "runtimeClosureCount",
            "runtimeClosureSha256",
            "sbomSha256",
            "xmlComponentCount",
            "xmlSha256",
        },
        "supply-chain evidence publishedModule",
    )
    for key in (
        "componentLicenseCount",
        "mavenPackageCount",
        "pomDependencyCount",
        "runtimeClosureCount",
        "xmlComponentCount",
    ):
        require_nonnegative_integer(
            published[key],
            f"supply-chain evidence publishedModule.{key}",
            positive=True,
        )
    for key in (
        "dependencyLockSha256",
        "pomSha256",
        "resolvedProfileSha256",
        "runtimeClosureSha256",
        "sbomSha256",
        "xmlSha256",
    ):
        require_digest(published[key], f"supply-chain evidence publishedModule.{key}")
    expected_published_hashes = {
        "dependencyLockSha256": sha256(
            repository_root / "routecontract-shardingsphere-5.5/gradle.lockfile"
        ),
        "pomSha256": sha256(actual_files["routecontract-shardingsphere-5.5.pom"]),
        "sbomSha256": sha256(
            actual_files["routecontract-shardingsphere-5.5-cyclonedx.json"]
        ),
        "xmlSha256": sha256(
            actual_files["routecontract-shardingsphere-5.5-cyclonedx.xml"]
        ),
    }
    for key, expected in expected_published_hashes.items():
        if published[key] != expected:
            raise GateError(
                f"supply-chain evidence publishedModule.{key} is not source/artifact bound"
            )

    example = require_exact_keys(
        evidence["exampleProfile"],
        {
            "componentLicenseCount",
            "mavenPackageCount",
            "resolvedProfileSha256",
            "sbomSha256",
            "xmlComponentCount",
            "xmlSha256",
        },
        "supply-chain evidence exampleProfile",
    )
    for key in ("componentLicenseCount", "mavenPackageCount", "xmlComponentCount"):
        require_nonnegative_integer(
            example[key], f"supply-chain evidence exampleProfile.{key}", positive=True
        )
    for key in ("resolvedProfileSha256", "sbomSha256", "xmlSha256"):
        require_digest(example[key], f"supply-chain evidence exampleProfile.{key}")
    expected_example_hashes = {
        "sbomSha256": sha256(
            actual_files["routecontract-mysql-example-cyclonedx.json"]
        ),
        "xmlSha256": sha256(
            actual_files["routecontract-mysql-example-cyclonedx.xml"]
        ),
    }
    for key, expected in expected_example_hashes.items():
        if example[key] != expected:
            raise GateError(
                f"supply-chain evidence exampleProfile.{key} is not workflow-artifact bound"
            )

    scanner_lock = load_strict_json(
        repository_root / "security/osv-scanner.lock.json", "OSV scanner lock"
    )
    require_exact_keys(scanner_lock, {"database", "scanner", "schemaVersion"}, "OSV scanner lock")
    if type(scanner_lock["schemaVersion"]) is not int or scanner_lock["schemaVersion"] != 1:
        raise GateError("unsupported OSV scanner lock schemaVersion")
    locked_scanner = require_exact_keys(
        scanner_lock["scanner"],
        {"commit", "name", "platforms", "scalibrVersion", "version"},
        "OSV scanner lock scanner",
    )
    platforms = locked_scanner["platforms"]
    if not isinstance(platforms, dict) or "linux-x86_64" not in platforms:
        raise GateError("OSV scanner lock lacks linux-x86_64")
    locked_asset = require_exact_keys(
        platforms["linux-x86_64"], {"sha256", "size", "url"}, "OSV scanner lock asset"
    )
    locked_database = require_exact_keys(
        scanner_lock["database"],
        {"ecosystem", "generation", "lastModified", "sha256", "size", "url"},
        "OSV scanner lock database",
    )
    scanner = require_exact_keys(
        evidence["scanner"],
        {
            "binarySha256",
            "binarySize",
            "binaryUrl",
            "commit",
            "database",
            "name",
            "platform",
            "scalibrVersion",
            "scannerConfigSha256",
            "scannerLockSha256",
            "version",
        },
        "supply-chain evidence scanner",
    )
    expected_scanner = {
        "binarySha256": locked_asset["sha256"],
        "binarySize": locked_asset["size"],
        "binaryUrl": locked_asset["url"],
        "commit": locked_scanner["commit"],
        "database": locked_database,
        "name": locked_scanner["name"],
        "platform": "linux-x86_64",
        "scalibrVersion": locked_scanner["scalibrVersion"],
        "scannerConfigSha256": hashlib.sha256(
            (repository_root / "security/osv-scanner.toml").read_bytes()
        ).hexdigest(),
        "scannerLockSha256": sha256(repository_root / "security/osv-scanner.lock.json"),
        "version": locked_scanner["version"],
    }
    if scanner != expected_scanner:
        raise GateError("supply-chain scanner/database provenance differs from the source lock")
    if (repository_root / "security/osv-scanner.toml").read_bytes() != b"":
        raise GateError("the final OSV scanner configuration is not exactly empty")

    vulnerabilities = require_exact_keys(
        evidence["vulnerabilities"],
        {"acceptedExceptionCount", "findingCount", "findings", "unreviewedCount"},
        "supply-chain evidence vulnerabilities",
    )
    unreviewed_count = require_nonnegative_integer(
        vulnerabilities["unreviewedCount"],
        "supply-chain evidence vulnerabilities.unreviewedCount",
    )
    if unreviewed_count != 0:
        raise GateError("supply-chain evidence contains unreviewed findings")
    findings = vulnerabilities["findings"]
    if not isinstance(findings, list):
        raise GateError("supply-chain evidence findings must be an array")
    for key in ("acceptedExceptionCount", "findingCount"):
        require_nonnegative_integer(
            vulnerabilities[key], f"supply-chain evidence vulnerabilities.{key}"
        )
    if (
        vulnerabilities["findingCount"] != len(findings)
        or vulnerabilities["acceptedExceptionCount"] != len(findings)
    ):
        raise GateError("supply-chain evidence finding counts are inconsistent")
    if (
        vulnerabilities["acceptedExceptionCount"] != 0
        or vulnerabilities["findingCount"] != 0
        or findings
    ):
        raise GateError(
            "supply-chain evidence must contain zero vulnerability findings and accepted exceptions"
        )

    policy = load_strict_json(
        repository_root / "security/supply-chain-policy.json", "supply-chain policy"
    )
    require_exact_keys(
        policy,
        {
            "allowedLicenseIds",
            "licenseExceptions",
            "licenseReviewExceptions",
            "schemaVersion",
            "vulnerabilityExceptions",
        },
        "supply-chain policy",
    )
    if type(policy["schemaVersion"]) is not int or policy["schemaVersion"] != 3:
        raise GateError("unsupported supply-chain policy schemaVersion")

    reviews = aggregate["licenseReviews"]
    policy_reviews = policy["licenseReviewExceptions"]
    if not isinstance(reviews, list) or not isinstance(policy_reviews, list):
        raise GateError("supply-chain license reviews must be arrays")
    if len(reviews) != 1 or len(policy_reviews) != 1:
        raise GateError("supply-chain evidence and policy must contain exactly one license review")
    review_keys = {
        "action",
        "componentName",
        "componentVersion",
        "expires",
        "owner",
        "purl",
        "rationaleCode",
        "reviewedAt",
        "scope",
        "status",
    }
    policy_review_keys = review_keys | {"documentationUrl", "sha256"}
    projected_policy_reviews: list[dict[str, Any]] = []
    policy_review_codes: set[str] = set()
    for index, raw_policy_review in enumerate(policy_reviews):
        policy_review = require_exact_keys(
            raw_policy_review,
            policy_review_keys,
            f"supply-chain policy license review {index}",
        )
        rationale = policy_review["rationaleCode"]
        if not isinstance(rationale, str) or not rationale or rationale in policy_review_codes:
            raise GateError("supply-chain policy license review rationaleCode is invalid or duplicate")
        policy_review_codes.add(rationale)
        projected_policy_reviews.append(
            {field: policy_review[field] for field in review_keys}
        )
    if policy_reviews != [EXPECTED_MYSQL_POLICY_LICENSE_REVIEW]:
        raise GateError(
            "supply-chain policy license review must exactly identify the pinned MySQL OCI image"
        )

    validated_reviews: list[dict[str, Any]] = []
    for index, raw_review in enumerate(reviews):
        review = require_exact_keys(
            raw_review, review_keys, f"supply-chain evidence license review {index}"
        )
        validated_reviews.append(review)
        if review["status"] != "manual-review-required":
            raise GateError("supply-chain evidence license review status is unexpected")
        try:
            review_expiry = datetime.strptime(review["expires"], "%Y-%m-%d").date()
        except (TypeError, ValueError) as error:
            raise GateError("supply-chain evidence license review expiry is invalid") from error
        if review_expiry < datetime.now(timezone.utc).date():
            raise GateError("supply-chain evidence contains an expired license review")
    if validated_reviews != projected_policy_reviews:
        raise GateError(
            "supply-chain evidence license reviews must equal the exact ordered policy projection"
        )

    exceptions = policy["vulnerabilityExceptions"]
    if not isinstance(exceptions, list):
        raise GateError("supply-chain vulnerabilityExceptions must be an array")
    if exceptions:
        raise GateError("supply-chain policy must contain zero vulnerability exceptions")

    return {
        "sha256": sha256(path),
        "revision": evidence["revision"],
        "source_tree": evidence["sourceTree"],
        "scanner_version": scanner["version"],
        "scanner_database_last_modified": locked_database["lastModified"],
        "maven_package_count": aggregate["mavenPackageCount"],
        "unresolved_license_review_count": unresolved_review_count,
        "finding_count": vulnerabilities["findingCount"],
        "unreviewed_count": vulnerabilities["unreviewedCount"],
    }


def source_archive_members(
    path: Path, expected_root: str
) -> dict[str, dict[str, Any]]:
    if path.stat().st_size > 50 * 1024 * 1024:
        raise GateError("source release archive unexpectedly exceeds 50 MiB")
    forbidden_parts = {
        ".git",
        ".codex",
        ".agents",
        "build",
        "private_notes",
        "private_codex",
        "__pycache__",
    }
    forbidden_prefixes = (
        "submission/draft/",
        "submission/final/",
        "submission/private/",
        "submission/package/",
    )
    roots: set[str] = set()
    files: dict[str, dict[str, Any]] = {}
    try:
        with ZipFile(path) as archive:
            if not archive.infolist():
                raise GateError("source archive is empty")
            for info in archive.infolist():
                pure = PurePosixPath(info.filename)
                if pure.is_absolute() or ".." in pure.parts or not pure.parts:
                    raise GateError(f"unsafe source archive member: {info.filename}")
                roots.add(pure.parts[0])
                unix_mode = info.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise GateError(f"source archive contains a symlink: {info.filename}")
                if info.is_dir():
                    continue
                relative = PurePosixPath(*pure.parts[1:]).as_posix()
                if any(part in forbidden_parts for part in pure.parts):
                    raise GateError(f"private/generated path leaked into source archive: {info.filename}")
                if relative.startswith(forbidden_prefixes) or relative.endswith((".pyc", ".DS_Store")):
                    raise GateError(f"private/generated file leaked into source archive: {info.filename}")
                if relative in files:
                    raise GateError(f"source archive contains a duplicate path: {relative}")
                digest = hashlib.sha256()
                with archive.open(info) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                files[relative] = {
                    "sha256": digest.hexdigest(),
                    "size": info.file_size,
                    "mode": unix_mode & 0o777,
                }
    except BadZipFile as error:
        raise GateError(f"could not inspect source archive: {error}") from error
    if len(roots) != 1:
        raise GateError(f"source archive must have one top-level directory, found {sorted(roots)}")
    root = next(iter(roots))
    if root != expected_root:
        raise GateError(
            f"source archive root mismatch: expected {expected_root}, found {root}"
        )
    required = {"README.md", "LICENSE", "NOTICE", "build.gradle", "gradlew"}
    missing = sorted(required - set(files))
    if missing:
        raise GateError(f"source archive is missing required files: {missing}")
    return files


def validate_source_archive(path: Path, expected_root: str) -> str:
    source_archive_members(path, expected_root)
    return expected_root


def validate_source_archive_identity(
    source: Path,
    repository_root: Path,
    commit: str,
    expected_root: str,
) -> None:
    observed = source_archive_members(source, expected_root)
    with tempfile.TemporaryDirectory(prefix=".routecontract-git-archive-") as raw:
        expected_archive = Path(raw) / "expected-source.zip"
        run(
            [
                "git",
                "archive",
                "--format=zip",
                f"--prefix={expected_root}/",
                f"--output={expected_archive}",
                commit,
            ],
            cwd=repository_root,
        )
        expected = source_archive_members(expected_archive, expected_root)
    if observed != expected:
        paths = sorted(set(observed) | set(expected))
        mismatched = [path for path in paths if observed.get(path) != expected.get(path)]
        raise GateError(
            "source release archive is not content-identical to the final Git tree: "
            + ", ".join(mismatched[:10])
        )


def validate_release_evidence(
    evidence_dir: Path,
    artifact_zip: Path,
    manifest: dict[str, Any],
    repository_root: Path,
) -> dict[str, Any]:
    artifact_metadata, artifact_members = validate_workflow_artifact_archive(
        artifact_zip, evidence_dir, manifest
    )
    checksum_path = require_file(evidence_dir / CHECKSUMS_NAME, "release SHA256SUMS")
    declared = parse_checksum_manifest(checksum_path)
    actual_files: dict[str, Path] = {}
    for path in evidence_dir.iterdir():
        if path.name == CHECKSUMS_NAME:
            continue
        if path.is_symlink() or not path.is_file():
            raise GateError(f"release evidence must be a flat set of regular files: {path}")
        actual_files[path.name] = path

    version = manifest["project"]["tag"][1:]
    jar_names = {
        f"routecontract-shardingsphere-5.5-{version}.jar",
        f"routecontract-shardingsphere-5.5-{version}-sources.jar",
        f"routecontract-shardingsphere-5.5-{version}-javadoc.jar",
    }
    private_evidence_names = {
        "environment.txt",
        "mysql-image.txt",
        "routecontract-mysql-example-cyclonedx.json",
        "routecontract-mysql-example-cyclonedx.xml",
        "standalone-consumer.txt",
    }
    public_unsigned_names = {
        "test-summary.txt",
        "routecontract-shardingsphere-5.5.pom",
        "routecontract-shardingsphere-5.5-cyclonedx.json",
        "routecontract-shardingsphere-5.5-cyclonedx.xml",
        "routecontract-aggregate-cyclonedx.json",
        "routecontract-aggregate-cyclonedx.xml",
        SUPPLY_CHAIN_EVIDENCE_NAME,
        manifest["release_evidence"]["source_archive_filename"],
        *jar_names,
    }
    signatures = set(manifest["release_evidence"]["signature_filenames"])
    for signature in signatures:
        signed_name = signature.removesuffix(".asc").removesuffix(".sig")
        if signed_name not in public_unsigned_names:
            raise GateError(f"signature does not correspond to an allowed release asset: {signature}")
    public_release_names = public_unsigned_names | signatures
    if set(declared) != public_release_names:
        raise GateError(
            "public SHA256SUMS must declare exactly the public Release payloads; "
            f"missing={sorted(public_release_names - set(declared))}, "
            f"unexpected={sorted(set(declared) - public_release_names)}"
        )
    exact_evidence_names = public_release_names | private_evidence_names
    if set(actual_files) != exact_evidence_names:
        raise GateError(
            "release evidence violates the exact allowlist; "
            f"missing={sorted(exact_evidence_names - set(actual_files))}, "
            f"unexpected={sorted(set(actual_files) - exact_evidence_names)}"
        )
    for filename, expected in declared.items():
        actual = sha256(actual_files[filename])
        if actual != expected:
            raise GateError(
                f"public Release checksum mismatch for {filename}: "
                f"expected {expected}, got {actual}"
            )

    environment_text = actual_files["environment.txt"].read_text(encoding="utf-8")
    if f"revision={manifest['project']['commit']}" not in environment_text.splitlines():
        raise GateError("release environment revision does not match the final commit")
    standalone_text = actual_files["standalone-consumer.txt"].read_text(
        encoding="utf-8", errors="replace"
    )
    expected_coordinate = (
        f"io.github.{manifest['github_owner'].casefold()}.routecontract:"
        f"routecontract-shardingsphere-5.5:{version}"
    )
    expected_consumer_marker = (
        "ROUTECONTRACT_RELEASE_ASSET_CONSUMER "
        f"coordinate={expected_coordinate} result=VERIFIED_MYSQL"
    )
    if standalone_text.splitlines().count(expected_consumer_marker) != 1:
        raise GateError(
            "release evidence must contain the exact final-asset standalone consumer marker once"
        )
    test_summary = validate_release_test_summary(
        actual_files["test-summary.txt"], manifest["project"]["commit"]
    )

    pom_path = actual_files["routecontract-shardingsphere-5.5.pom"]
    try:
        pom_root = ET.fromstring(pom_path.read_bytes())
    except ET.ParseError as error:
        raise GateError(f"release POM is not valid XML: {error}") from error
    pom_values = {
        child.tag.rsplit("}", 1)[-1]: (child.text or "").strip()
        for child in pom_root
        if child.tag.rsplit("}", 1)[-1] in {"groupId", "artifactId", "version"}
    }
    expected_pom = {
        "groupId": f"io.github.{manifest['github_owner'].casefold()}.routecontract",
        "artifactId": "routecontract-shardingsphere-5.5",
        "version": version,
    }
    if pom_values != expected_pom:
        raise GateError(f"release POM coordinates mismatch: {pom_values}, expected {expected_pom}")

    evidence_spec = manifest["release_evidence"]
    source = actual_files[evidence_spec["source_archive_filename"]]
    aggregate_json = actual_files["routecontract-aggregate-cyclonedx.json"]
    aggregate_xml = actual_files["routecontract-aggregate-cyclonedx.xml"]
    published_json = actual_files[
        "routecontract-shardingsphere-5.5-cyclonedx.json"
    ]
    published_xml = actual_files[
        "routecontract-shardingsphere-5.5-cyclonedx.xml"
    ]
    example_json = actual_files["routecontract-mysql-example-cyclonedx.json"]
    example_xml = actual_files["routecontract-mysql-example-cyclonedx.xml"]
    supply_chain_path = actual_files[SUPPLY_CHAIN_EVIDENCE_NAME]
    release_sbom_paths = (
        aggregate_json,
        aggregate_xml,
        published_json,
        published_xml,
        example_json,
        example_xml,
    )

    def release_sbom_fingerprint() -> tuple[tuple[str, str], ...]:
        return tuple(
            (
                path.name,
                sha256(require_file(path, f"release SBOM {path.name}")),
            )
            for path in release_sbom_paths
        )

    # Bind both validators directly to the six bytes recorded in the already
    # checksum-verified workflow artifact. Re-hashing the directory only here
    # would allow a mutation after the archive/directory comparison to become a
    # new baseline that no longer matched the artifact named in the manifest.
    bound_release_sboms = tuple(
        (path.name, artifact_members[path.name]["sha256"])
        for path in release_sbom_paths
    )
    if release_sbom_fingerprint() != bound_release_sboms:
        raise GateError(
            "release evidence SBOM no longer matches the workflow artifact ZIP"
        )
    bound_supply_chain_sha = artifact_members[SUPPLY_CHAIN_EVIDENCE_NAME]["sha256"]
    if (
        sha256(require_file(supply_chain_path, "supply-chain evidence"))
        != bound_supply_chain_sha
        or bound_supply_chain_sha != declared[SUPPLY_CHAIN_EVIDENCE_NAME]
    ):
        raise GateError(
            "supply-chain evidence no longer matches the workflow artifact ZIP and public checksum"
        )
    observed = {
        "source_archive": sha256(source),
        "aggregate_sbom_json": sha256(aggregate_json),
        "aggregate_sbom_xml": sha256(aggregate_xml),
    }
    expected_pairs = {
        "source_archive": evidence_spec["source_archive_sha256"],
        "aggregate_sbom_json": evidence_spec["aggregate_sbom_json_sha256"],
        "aggregate_sbom_xml": evidence_spec["aggregate_sbom_xml_sha256"],
    }
    for label, digest in observed.items():
        if digest != expected_pairs[label]:
            raise GateError(
                f"manifest checksum mismatch for {label}: expected {expected_pairs[label]}, got {digest}"
            )
    expected_archive_root = f"{manifest['project']['slug']}-{version}"
    archive_root = validate_source_archive(source, expected_archive_root)
    validate_source_archive_identity(
        source,
        repository_root,
        manifest["project"]["commit"],
        expected_archive_root,
    )
    run(
        [
            sys.executable,
            str(repository_root / "scripts" / "finalize-sbom.py"),
            "--first-party-group",
            f"io.github.{manifest['github_owner'].casefold()}.routecontract",
            "--verify-pair",
            str(aggregate_json),
            str(aggregate_xml),
            "--verify-pair",
            str(published_json),
            str(published_xml),
            "--verify-pair",
            str(example_json),
            str(example_xml),
        ],
        cwd=repository_root,
    )
    run(
        [
            sys.executable,
            str(repository_root / "scripts" / "validate-official-cyclonedx.py"),
            "--input-root",
            str(evidence_dir),
            "--pair",
            "aggregate",
            aggregate_json.name,
            aggregate_xml.name,
            "--pair",
            "published",
            published_json.name,
            published_xml.name,
            "--pair",
            "example",
            example_json.name,
            example_xml.name,
        ],
        cwd=repository_root,
    )
    if release_sbom_fingerprint() != bound_release_sboms:
        raise GateError(
            "release evidence SBOM changed between semantic and official validation"
        )
    supply_chain = validate_supply_chain_evidence(
        supply_chain_path,
        actual_files,
        manifest,
        repository_root,
    )
    if (
        release_sbom_fingerprint() != bound_release_sboms
        or sha256(require_file(supply_chain_path, "supply-chain evidence"))
        != bound_supply_chain_sha
    ):
        raise GateError(
            "release evidence changed while validating the sanitized supply-chain contract"
        )
    public_release_assets = {
        name: {"sha256": declared[name], "size": actual_files[name].stat().st_size}
        for name in sorted(public_release_names)
    }
    public_release_assets[CHECKSUMS_NAME] = {
        "sha256": sha256(checksum_path),
        "size": checksum_path.stat().st_size,
    }
    return {
        **artifact_metadata,
        "source_archive_filename": source.name,
        "source_archive_root": archive_root,
        "source_archive_size": source.stat().st_size,
        "source_archive_sha256": observed["source_archive"],
        "aggregate_sbom_json_sha256": observed["aggregate_sbom_json"],
        "aggregate_sbom_xml_sha256": observed["aggregate_sbom_xml"],
        "test_summary": test_summary,
        "supply_chain": supply_chain,
        "release_evidence_file_count": len(actual_files),
        "public_release_assets": public_release_assets,
    }


def validate_video_metadata_tags(value: Any, label: str) -> int:
    if value is None:
        return 0
    if not isinstance(value, dict):
        raise GateError(f"ffprobe {label} metadata tags must be an object")
    normalized: dict[str, str] = {}
    for index, (key, tag_value) in enumerate(value.items()):
        if not isinstance(key, str) or not isinstance(tag_value, str):
            raise GateError(f"ffprobe {label} metadata tags must contain only strings")
        normalized_key = key.strip().casefold()
        if normalized_key in SENSITIVE_VIDEO_METADATA_TAGS or any(
            normalized_key.startswith(prefix)
            for prefix in SENSITIVE_VIDEO_METADATA_PREFIXES
        ):
            raise GateError(
                "local demonstration file contains a sensitive metadata tag "
                f"(index={index})"
            )
        normalized[key] = tag_value
    reject_sensitive_metadata(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True),
        f"local demonstration {label} metadata",
    )
    return len(normalized)


def local_video_metadata(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise GateError(
            "ffprobe is required to verify duration, 1080p dimensions, the "
            "caption-first no-audio contract, and privacy-safe video metadata"
        )
    output = run(
        [
            ffprobe,
            "-v",
            "error",
            "-f",
            "mov",
            "-protocol_whitelist",
            "file",
            "-show_entries",
            "format=duration:format_tags:stream=index,codec_type,width,height:stream_tags:stream_disposition=default,attached_pic,still_image:chapter=id:chapter_tags:program=id:program_tags",
            "-of",
            "json",
            str(path),
        ],
        failure_label="ffprobe video metadata probe",
    )
    try:
        data = _decode_strict_json(
            output,
            "ffprobe returned incomplete video metadata: invalid strict JSON",
            maximum_bytes=MAX_JSON_TOOL_OUTPUT_BYTES,
        )
        if not isinstance(data, dict):
            raise TypeError("top-level value is not an object")
        format_metadata = data["format"]
        streams = data["streams"]
        if not isinstance(format_metadata, dict):
            raise TypeError("format is not an object")
        if not isinstance(streams, list):
            raise TypeError("streams is not an array")
        chapters = data.get("chapters", [])
        programs = data.get("programs", [])
        if not isinstance(chapters, list) or any(
            not isinstance(chapter, dict) for chapter in chapters
        ):
            raise TypeError("chapters is not an array of objects")
        if not isinstance(programs, list) or any(
            not isinstance(program, dict) for program in programs
        ):
            raise TypeError("programs is not an array of objects")
        duration_value = format_metadata["duration"]
        if isinstance(duration_value, bool):
            raise TypeError("duration is boolean")
        duration = float(duration_value)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("duration is not a positive finite number")
        if any(not isinstance(stream, dict) for stream in streams):
            raise TypeError("a stream is not an object")
    except (KeyError, TypeError, ValueError, OverflowError):
        raise GateError(
            "ffprobe returned incomplete video metadata: invalid field shape or value"
        ) from None

    metadata_tag_count = validate_video_metadata_tags(
        format_metadata.get("tags"), "format"
    )
    for stream_ordinal, stream in enumerate(streams):
        metadata_tag_count += validate_video_metadata_tags(
            stream.get("tags"), f"stream ordinal {stream_ordinal}"
        )
    for scope, entries in (("chapter", chapters), ("program", programs)):
        for entry_ordinal, entry in enumerate(entries):
            metadata_tag_count += validate_video_metadata_tags(
                entry.get("tags"), f"{scope} ordinal {entry_ordinal}"
            )

    video_streams = [
        stream for stream in streams if stream.get("codec_type") == "video"
    ]
    audio_streams = [
        stream for stream in streams if stream.get("codec_type") == "audio"
    ]
    if not video_streams:
        raise GateError("local demonstration file has no video stream")
    if audio_streams:
        raise GateError(
            "caption-first local demonstration file must contain no audio streams"
        )

    playable_video_streams: list[dict[str, Any]] = []
    for stream in video_streams:
        width = stream.get("width")
        height = stream.get("height")
        if (
            isinstance(width, bool)
            or not isinstance(width, int)
            or isinstance(height, bool)
            or not isinstance(height, int)
            or width <= 0
            or height <= 0
        ):
            raise GateError("ffprobe returned invalid video stream dimensions")
        disposition = stream.get("disposition")
        if not isinstance(disposition, dict) or any(
            type(disposition.get(key)) is not int
            or disposition[key] not in {0, 1}
            for key in ("default", "attached_pic", "still_image")
        ):
            raise GateError("ffprobe returned invalid video stream disposition")
        if disposition["attached_pic"] == 0 and disposition["still_image"] == 0:
            playable_video_streams.append(stream)
    if not playable_video_streams:
        raise GateError("local demonstration file has no playable motion video stream")

    stream_indexes = [stream.get("index") for stream in playable_video_streams]
    if any(type(index) is not int or index < 0 for index in stream_indexes) or len(
        set(stream_indexes)
    ) != len(stream_indexes):
        raise GateError("ffprobe returned invalid or duplicate motion video stream indexes")
    default_video_streams = [
        stream
        for stream in playable_video_streams
        if stream["disposition"]["default"] == 1
    ]
    if len(default_video_streams) > 1:
        raise GateError("local demonstration file has multiple default motion video streams")
    selected_video = (
        default_video_streams[0]
        if default_video_streams
        else min(playable_video_streams, key=lambda stream: stream["index"])
    )
    width = selected_video["width"]
    height = selected_video["height"]
    if width < MIN_VIDEO_WIDTH or height < MIN_VIDEO_HEIGHT:
        raise GateError(
            "local demonstration video must be at least "
            f"{MIN_VIDEO_WIDTH}x{MIN_VIDEO_HEIGHT}"
        )
    return {
        "duration_seconds": duration,
        "width": width,
        "height": height,
        "video_stream_count": len(video_streams),
        "audio_stream_count": len(audio_streams),
        "selected_video_stream_index": selected_video.get("index"),
        "selected_video_is_default": bool(
            selected_video["disposition"]["default"]
        ),
        "metadata_tag_count": metadata_tag_count,
        "probe": "ffprobe",
    }


def validate_full_motion_video_decode(
    path: Path, stream_index: int, expected_duration: float
) -> dict[str, Any]:
    """Decode the complete selected motion stream instead of trusting headers."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise GateError(
            "ffmpeg is required to decode the complete selected motion video stream"
        )
    output = run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-xerror",
            "-err_detect",
            "explode",
            "-f",
            "mov",
            "-protocol_whitelist",
            "file",
            "-progress",
            "pipe:1",
            "-nostats",
            "-i",
            str(path),
            "-map",
            f"0:{stream_index}",
            "-an",
            "-sn",
            "-dn",
            "-f",
            "null",
            "-",
        ],
        timeout_seconds=600,
        failure_label="ffmpeg full motion-video decode",
    )
    frames = re.findall(r"(?m)^frame=([0-9]{1,12})$", output)
    out_times = re.findall(r"(?m)^out_time_us=([0-9]{1,18})$", output)
    if (
        not frames
        or not out_times
        or int(frames[-1]) <= 0
        or not output.rstrip().endswith("progress=end")
    ):
        raise GateError("ffmpeg did not complete the selected motion-video decode")
    decoded_frames = int(frames[-1])
    decoded_duration = int(out_times[-1]) / 1_000_000
    if abs(decoded_duration - expected_duration) > DECODE_DURATION_TOLERANCE_SECONDS:
        raise GateError("decoded motion-video duration differs from the container duration")
    minimum_frames = max(1, math.ceil(decoded_duration * MIN_DECODED_VIDEO_FPS))
    if decoded_frames < minimum_frames:
        raise GateError(
            "decoded motion-video frame count is too low for the declared duration"
        )
    return {
        "decode_probe": "ffmpeg",
        "decoded_frame_count": decoded_frames,
        "decoded_duration_seconds": decoded_duration,
        "minimum_frame_count": minimum_frames,
    }


def validate_local_video(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    expected_hash = manifest["video"]["local_file_sha256"]
    actual_hash = sha256(path)
    if actual_hash != expected_hash:
        raise GateError(f"video SHA-256 mismatch: expected {expected_hash}, got {actual_hash}")
    metadata = local_video_metadata(path)
    duration = float(metadata["duration_seconds"])
    if not MIN_VIDEO_SECONDS <= duration <= MAX_VIDEO_SECONDS:
        raise GateError(
            "local video duration must be from 173 through 175 seconds inclusive"
        )
    require_caption_cues_fit_duration(
        manifest_video_caption_evidence(manifest), duration, "local video"
    )
    declared = float(manifest["video"]["duration_seconds"])
    if abs(duration - declared) > 0.1:
        raise GateError("video duration differs from manifest")
    stream_index = metadata["selected_video_stream_index"]
    if type(stream_index) is not int or stream_index < 0:
        raise GateError("local video has no selected motion-video stream index")
    metadata.update(
        validate_full_motion_video_decode(path, stream_index, duration)
    )
    if sha256(path) != actual_hash:
        raise GateError("local demonstration file changed during validation")
    metadata["sha256"] = actual_hash
    return metadata


def revalidate_local_video_hash_before_metadata(
    path: Path, expected_sha256: str
) -> str:
    """Rehash the video at the last point before audit metadata is materialized."""
    actual_sha256 = sha256(path)
    if actual_sha256 != expected_sha256:
        raise GateError(
            "local demonstration file changed before package metadata write"
        )
    return actual_sha256


def package_video_metadata(
    video_metadata: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    """Materialize the exact video audit-metadata shape."""
    attestations = manifest["participant_attestations"]
    return {
        **video_metadata,
        "youtube_url": manifest["video"]["youtube_url"],
        "external_evidence_branch": manifest["video"][
            "external_evidence_branch"
        ],
        "caption_contract": manifest_video_caption_evidence(manifest),
        "local_burned_in_caption_pixels_automatically_verified": False,
        "local_actual_screen_caption_watchthrough_participant_attested": attestations[
            "final_local_video_actual_screen_caption_watchthrough_completed"
        ],
        "public_frame_audio_caption_equivalence_automatically_verified": False,
        "public_frame_audio_caption_equivalence_participant_attested": attestations[
            "final_public_video_frame_audio_caption_equivalence_review_completed"
        ],
    }


def verified_tls_context() -> ssl.SSLContext:
    """Build a TLS context from the version-pinned certifi CA bundle."""
    try:
        certifi = importlib.import_module("certifi")
    except ModuleNotFoundError as error:
        raise GateError(
            "the pinned certifi CA bundle is required; run this gate with the "
            "report-builder virtual environment"
        ) from error
    try:
        ca_bundle = Path(certifi.where())
    except (AttributeError, TypeError) as error:
        raise GateError("certifi did not provide a usable CA bundle path") from error
    if ca_bundle.is_symlink() or not ca_bundle.is_file():
        raise GateError("certifi CA bundle is not a regular file")
    try:
        return ssl.create_default_context(cafile=str(ca_bundle))
    except (OSError, ssl.SSLError) as error:
        raise GateError(f"could not load the certifi CA bundle: {error}") from error


def request_bytes(url: str, *, accept: str | None = None, limit: int | None = None) -> bytes:
    data, _ = request_bytes_with_headers(url, accept=accept, limit=limit)
    return data


def request_bytes_with_headers(
    url: str, *, accept: str | None = None, limit: int | None = None
) -> tuple[bytes, dict[str, list[str]]]:
    headers = {
        "User-Agent": "RouteContract-contest-submission-verifier/1",
        "Cache-Control": "no-cache",
    }
    if accept:
        headers["Accept"] = accept
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if urllib.parse.urlparse(url).netloc == "api.github.com":
        headers["X-GitHub-Api-Version"] = "2026-03-10"
        if token:
            headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(
            request, timeout=20, context=verified_tls_context()
        ) as response:
            data = response.read() if limit is None else response.read(limit + 1)
            headers: dict[str, list[str]] = {}
            raw_items = (
                response.headers.raw_items()
                if hasattr(response.headers, "raw_items")
                else response.headers.items()
            )
            for key, value in raw_items:
                headers.setdefault(str(key).casefold(), []).append(str(value))
    except (urllib.error.URLError, TimeoutError) as error:
        raise GateError(f"public URL is unavailable: {url}: {error}") from error
    if limit is not None and len(data) > limit:
        raise GateError(f"public response exceeded the verification limit: {url}")
    return data, headers


def _decode_public_json(data: bytes, url: str) -> Any:
    return _decode_strict_json(
        data,
        f"public endpoint did not return JSON; strict JSON is required: {url}",
        maximum_bytes=MAX_JSON_TOOL_OUTPUT_BYTES,
    )


def request_json(url: str) -> dict[str, Any]:
    value = _decode_public_json(
        request_bytes(
            url,
            accept="application/vnd.github+json",
            limit=MAX_PUBLIC_JSON_RESPONSE_BYTES,
        ),
        url,
    )
    if not isinstance(value, dict):
        raise GateError(f"public endpoint returned a non-object: {url}")
    return value


def request_json_list(url: str) -> list[dict[str, Any]]:
    value = _decode_public_json(
        request_bytes(
            url,
            accept="application/vnd.github+json",
            limit=MAX_PUBLIC_JSON_RESPONSE_BYTES,
        ),
        url,
    )
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise GateError(f"public endpoint did not return an object array: {url}")
    return value


def request_json_list_page(url: str) -> tuple[list[dict[str, Any]], list[str]]:
    data, headers = request_bytes_with_headers(
        url,
        accept="application/vnd.github+json",
        limit=MAX_PUBLIC_JSON_RESPONSE_BYTES,
    )
    value = _decode_public_json(data, url)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise GateError(f"public endpoint did not return an object array: {url}")
    return value, headers.get("link", [])


def hash_remote_file(url: str, expected_size: int) -> str:
    digest = hashlib.sha256()
    total = 0
    headers = {"User-Agent": "RouteContract-contest-submission-verifier/1"}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(
            request, timeout=30, context=verified_tls_context()
        ) as response:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                total += len(chunk)
                if total > expected_size:
                    raise GateError("public release asset is larger than its declared size")
                digest.update(chunk)
    except (urllib.error.URLError, TimeoutError) as error:
        raise GateError(f"could not download public release asset: {url}: {error}") from error
    if total != expected_size:
        raise GateError(
            f"public release asset size mismatch: expected {expected_size}, downloaded {total}"
        )
    return digest.hexdigest()


def public_youtube_metadata(url: str) -> dict[str, Any]:
    video_id = YOUTUBE_RE.fullmatch(url).group("id")  # validated earlier
    oembed_url = "https://www.youtube.com/oembed?" + urllib.parse.urlencode(
        {"url": url, "format": "json"}
    )
    oembed = request_json(oembed_url)
    title = oembed.get("title")
    if not isinstance(title, str) or not title:
        raise GateError("YouTube oEmbed response has no public title")

    yt_dlp = shutil.which("yt-dlp")
    if not yt_dlp:
        raise GateError(
            "yt-dlp is required to verify public availability, non-live status, "
            "age limit, duration, and downloadable 1080p formats"
        )
    output = run(
        [
            yt_dlp,
            "--ignore-config",
            "--no-playlist",
            "--check-all-formats",
            "--dump-single-json",
            "--skip-download",
            "--",
            url,
        ],
        failure_label="yt-dlp public video metadata probe",
    )
    try:
        metadata = _decode_strict_json(
            output,
            "yt-dlp returned incomplete public video duration metadata: invalid strict JSON",
            maximum_bytes=MAX_JSON_TOOL_OUTPUT_BYTES,
        )
        if not isinstance(metadata, dict):
            raise TypeError("top-level value is not an object")
        if metadata.get("id") != video_id:
            raise GateError("yt-dlp returned a different YouTube video ID")
        duration_value = metadata["duration"]
        if isinstance(duration_value, bool):
            raise TypeError("duration is boolean")
        duration = float(duration_value)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("duration is not a positive finite number")
    except (KeyError, TypeError, ValueError, OverflowError):
        raise GateError(
            "yt-dlp returned incomplete public video duration metadata: "
            "invalid field shape or value"
        ) from None

    availability = metadata.get("availability")
    if availability != "public":
        raise GateError("YouTube availability must be public")
    live_status = metadata.get("live_status")
    if live_status != "not_live":
        raise GateError("YouTube demonstration must be a non-live upload")
    if "age_limit" not in metadata:
        raise GateError("YouTube age_limit must be 0 or null; yt-dlp omitted it")
    age_limit = metadata["age_limit"]
    if age_limit is not None:
        try:
            valid_age_limit = (
                not isinstance(age_limit, bool)
                and isinstance(age_limit, (int, float))
                and math.isfinite(float(age_limit))
                and float(age_limit) == 0.0
            )
        except (TypeError, ValueError, OverflowError):
            valid_age_limit = False
        if not valid_age_limit:
            raise GateError(
                "YouTube age_limit must be 0 or null for logged-out playback"
            ) from None

    formats = metadata.get("formats")
    if not isinstance(formats, list) or any(
        not isinstance(item, dict) for item in formats
    ):
        raise GateError("yt-dlp format metadata must be an array of objects")
    downloadable_video_heights: list[int] = []
    for item in formats:
        height = item.get("height")
        vcodec = item.get("vcodec")
        format_url = item.get("url")
        has_drm = item.get("has_drm")
        height_number: float | None = None
        if height is not None:
            try:
                valid_height = (
                    not isinstance(height, bool)
                    and isinstance(height, (int, float))
                    and math.isfinite(float(height))
                    and float(height) > 0
                )
                height_number = float(height) if valid_height else None
            except (TypeError, ValueError, OverflowError):
                valid_height = False
            if not valid_height:
                raise GateError("yt-dlp format metadata contains an invalid height") from None
        if vcodec is not None and not isinstance(vcodec, str):
            raise GateError("yt-dlp format metadata contains an invalid vcodec")
        if format_url is not None and not isinstance(format_url, str):
            raise GateError("yt-dlp format metadata contains an invalid URL")
        if has_drm is not None and not isinstance(has_drm, bool):
            raise GateError("yt-dlp format metadata contains an invalid DRM flag")
        parsed_url = (
            urllib.parse.urlparse(format_url)
            if isinstance(format_url, str) and format_url
            else None
        )
        if (
            height_number is not None
            and height_number >= MIN_PUBLIC_VIDEO_HEIGHT
            and isinstance(vcodec, str)
            and bool(vcodec.strip())
            and vcodec.strip().casefold() != "none"
            and parsed_url is not None
            and parsed_url.scheme in {"http", "https"}
            and bool(parsed_url.netloc)
            and has_drm is False
        ):
            downloadable_video_heights.append(int(height_number))
    if not downloadable_video_heights:
        raise GateError(
            "YouTube has no downloadable video format at 1080p or higher"
        )
    return {
        "id": video_id,
        "title": title,
        "duration_seconds": duration,
        "availability": availability,
        "live_status": live_status,
        "age_limit": age_limit,
        "max_video_height": max(downloadable_video_heights),
    }


def validate_public_youtube_contract(
    manifest: dict[str, Any],
    local_video: dict[str, Any],
    youtube: dict[str, Any],
) -> None:
    if youtube["title"] != manifest["video"]["title"]:
        raise GateError("public YouTube title mismatch")
    if not MIN_VIDEO_SECONDS <= youtube["duration_seconds"] <= MAX_VIDEO_SECONDS:
        raise GateError(
            "public YouTube video duration must be from 173 through 175 seconds inclusive"
        )
    require_caption_cues_fit_duration(
        manifest_video_caption_evidence(manifest),
        float(youtube["duration_seconds"]),
        "public YouTube video",
    )
    if abs(
        float(youtube["duration_seconds"])
        - float(local_video["duration_seconds"])
    ) > 1.0:
        raise GateError("public YouTube duration does not match the checksummed local video")


def require_safe_github_cli_release_verification() -> str:
    """Return the exact ``gh`` path accepted by the shared safety preflight."""
    try:
        executable, _ = GITHUB_CLI_RELEASE_SAFETY.require_safe_github_cli()
    except GITHUB_CLI_RELEASE_SAFETY.GithubCliSafetyError as error:
        raise GateError(str(error)) from None
    return executable


def verify_release_attestations(
    manifest: dict[str, Any], evidence: dict[str, Any], evidence_dir: Path
) -> None:
    """Verify the immutable Release and every attached asset with GitHub attestations."""
    gh = require_safe_github_cli_release_verification()
    project = manifest["project"]
    repository = f"{manifest['github_owner']}/{manifest['github_repository']}"
    run([gh, "release", "verify", project["tag"], "--repo", repository])
    for asset_name in sorted(evidence["public_release_assets"]):
        asset_path = evidence_dir / asset_name
        if asset_path.is_symlink() or not asset_path.is_file():
            raise GateError(
                f"release attestation input is not a regular file: {asset_name}"
            )
        run(
            [
                gh,
                "release",
                "verify-asset",
                project["tag"],
                str(asset_path),
                "--repo",
                repository,
            ]
        )


RESULT_ISSUE_REQUIRED_CHECKBOXES = (
    "I am a human tester and not the RouteContract author, an AI agent, or a person operating the maintainer's machine or VM.",
    "I did not author, review, privately pretest, or prepare code, documentation, workflow, installer, or release assets in the tested tag, and I did not create or publish its tag or Release or prepare its activation record.",
    "I used my own workspace, Gradle home, Maven target, Docker daemon, and downloaded assets; I used no private/unreleased artifact, maintainer cache, maintainer Docker daemon, or maintainer-provided setup.",
    "Before both first outcomes, I used no RouteContract-specific AI/search advice or maintainer help, public or private; general prerequisite help came only from the linked official Java, Docker, Git, Bash/POSIX, OS, shell, or Task-B Python documentation.",
    "Any private invitation I received contained neutral logistics only, with no RouteContract command, expected output, classification, setup guidance, or troubleshooting.",
    "I was not offered money, a gift, a reciprocal favor, contest support, or another benefit for this attempt; I was not asked to star or follow the project; and I was not asked or expected to pass, endorse, report a positive result, or use favorable wording.",
    "I preserved every started attempt and disclosed any prior RouteContract exposure, relationship, or compensation without publishing private identity details.",
    "I understand that Task A can support an exact-RC clean Quick Start claim and Task B can support only exact-RC packaging/install evidence; neither result automatically applies to final v0.1.0.",
    "I understand this does not prove route plans, physical-table counts, commit or business success, production readiness, publisher identity, security, performance, adoption, endorsement, upstream acceptance, or a contest score.",
    "I will not edit this Issue title or body after submission; every later recovery will be a timestamped comment, and a final-release claim requires a new non-author run on that final release.",
    "I removed full logs, credentials, raw SQL and bind values, customer data, private topology, hostnames, absolute paths, JDBC URLs, container identifiers, and trace/span identifiers.",
    "If sensitive data or a possible vulnerability appeared, I stopped before public disclosure and followed SECURITY.md. Even through private reporting, I neither requested, sent, nor retained full logs, diagnostics, or data dumps.",
    "I am the participant and am filing this issue from my own account. I agree that this minimized first-attempt record may remain public.",
    "I uploaded no file or screenshot and removed unnecessary personal data, including real name/email/school/employer/city, usernames/home paths, IP/device details, Docker context/registry/proxy, environment dumps, and Git configuration.",
)
ELIGIBLE_AUTHOR_ASSOCIATIONS = {
    "NONE",
    "CONTRIBUTOR",
    "FIRST_TIMER",
    "FIRST_TIME_CONTRIBUTOR",
}
ELIGIBLE_TASK_A_OUTCOMES = {
    "UNASSISTED_PASS",
    "PRODUCT_OR_DOC_BLOCKED",
    "PREREQUISITE_BLOCKED",
    "TIMEOUT_OR_WITHDRAWN",
}
PUBLIC_RECRUITMENT_MARKER = "ROUTECONTRACT_PUBLIC_RECRUITMENT_OPEN"


def parse_github_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise GateError(f"{label} is missing a GitHub UTC timestamp")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        raise GateError(f"{label} has an invalid GitHub UTC timestamp") from error
    return parsed


def contains_exact_body_line(body: str, line: str) -> bool:
    return body.splitlines().count(line) == 1


def contains_unique_body_marker(body: str, line: str, prefix: str) -> bool:
    """Require one exact column-zero marker and no conflicting family member."""
    lines = body.splitlines()
    return lines.count(line) == 1 and sum(
        candidate.startswith(prefix) for candidate in lines
    ) == 1


def visible_github_markdown_evidence(body: str) -> str:
    """Return only top-level Markdown lines that GitHub can visibly render as evidence.

    The evidence grammar deliberately excludes comments, code, blockquotes, and raw
    HTML containers. Those constructs can display a literal ``- [x]`` or marker in
    source without rendering it as the participant-facing statement being checked.
    """
    if not isinstance(body, str):
        raise GateError("GitHub evidence body must be text")
    # GitHub expands tabs while deciding whether a line is an indented code
    # block.  Mixed one-to-three-space + tab prefixes are therefore ambiguous
    # if we later normalize the line with ``strip()``.  The closed evidence
    # grammar never needs tabs, so reject them before parsing instead of
    # accidentally treating code-block text as a visible attestation.
    if "\t" in body:
        raise GateError("GitHub evidence body cannot use tab indentation")
    # Comments are not needed by the closed Issue Form.  Reject them instead of
    # deleting them: ``- [<!-- -->x]`` renders as plain text in GitHub but would
    # become a checked task item if comment bytes were normalized away first.
    if "<!--" in body or "-->" in body:
        raise GateError("GitHub evidence body cannot use HTML comments")
    uncommented = body

    visible: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    raw_container: str | None = None
    raw_open = re.compile(
        r" {0,3}<(?P<tag>pre|script|style|textarea|template)(?:\s|>|$)", re.IGNORECASE
    )
    for raw_line in uncommented.splitlines():
        line = raw_line.rstrip("\r")
        if raw_container is not None:
            if re.search(rf"</{raw_container}\s*>", line, re.IGNORECASE):
                raw_container = None
            continue
        container_match = raw_open.match(line)
        if container_match is not None:
            raw_container = container_match.group("tag").casefold()
            if re.search(rf"</{raw_container}\s*>", line, re.IGNORECASE):
                raw_container = None
            continue
        fence_match = re.match(r" {0,3}(`{3,}|~{3,})", line)
        if fence_character is not None:
            if (
                fence_match is not None
                and fence_match.group(1)[0] == fence_character
                and len(fence_match.group(1)) >= fence_length
                and not line[fence_match.end() :].strip()
            ):
                fence_character = None
                fence_length = 0
            continue
        if fence_match is not None:
            fence_character = fence_match.group(1)[0]
            fence_length = len(fence_match.group(1))
            continue
        if re.match(r" {0,3}<", line):
            raise GateError(
                "GitHub evidence body uses a raw HTML block that cannot carry evidence"
            )
        if line.startswith("\t") or line.startswith("    "):
            continue
        if re.match(r" {0,3}>", line):
            continue
        visible.append(line)
    if fence_character is not None:
        raise GateError("GitHub evidence body has an unclosed fenced code block")
    if raw_container is not None:
        raise GateError("GitHub evidence body has an unclosed raw HTML container")
    return "\n".join(visible)


def contains_exact_tag_token(body: str, tag: str) -> bool:
    boundary = r"0-9A-Za-z._+\-"
    return re.search(
        rf"(?<![{boundary}]){re.escape(tag)}(?![{boundary}])", body
    ) is not None


def checked_result_attestations(body: str) -> bool:
    lines = body.splitlines()
    for label in RESULT_ISSUE_REQUIRED_CHECKBOXES:
        # One required label means one visible checkbox state.  In particular,
        # a checked line cannot be paired with a second unchecked/unknown-state
        # copy of the same attestation.
        if body.count(label) != 1:
            return False
        states = [
            match.group("state")
            for candidate in lines
            if (
                match := re.fullmatch(
                    rf"- \[(?P<state>[^\]]*)\] {re.escape(label)}", candidate
                )
            )
        ]
        if len(states) != 1 or states[0] not in {"x", "X"}:
            return False
    return True


def task_a_first_outcome(body: str) -> str | None:
    heading = "### Task A first outcome — exact-tag Quick Start"
    lines = body.splitlines()
    indexes = [index for index, line in enumerate(lines) if line == heading]
    if len(indexes) != 1:
        return None
    for candidate in lines[indexes[0] + 1 :]:
        if candidate:
            return candidate if candidate in ELIGIBLE_TASK_A_OUTCOMES else None
    return None


def parse_public_checksum_manifest(data: bytes) -> dict[str, str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise GateError("public RC SHA256SUMS is not UTF-8") from error
    checksums: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/\\]+)", line)
        if match is None:
            raise GateError(f"invalid public RC SHA256SUMS line {line_number}: {line!r}")
        digest_value, filename = match.groups()
        if digest_value == "0" * 64:
            raise GateError(f"zero public RC SHA256SUMS digest at line {line_number}")
        if filename in checksums or filename == CHECKSUMS_NAME:
            raise GateError(f"duplicate or recursive public RC SHA256SUMS entry: {filename}")
        checksums[filename] = digest_value
    if not checksums:
        raise GateError("public RC SHA256SUMS is empty")
    return checksums


def validate_public_rc_workflow_artifact_archive(
    artifact_zip: Path,
    artifact_size: int,
    record: dict[str, Any],
    declared: dict[str, str],
) -> dict[str, str]:
    """Reuse the activation validator to bind the 17-file artifact to Release bytes."""
    try:
        metadata = artifact_zip.lstat()
    except OSError as error:
        raise GateError(
            f"cannot inspect downloaded public RC workflow artifact: {error}"
        ) from None
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or type(artifact_size) is not int
        or metadata.st_size != artifact_size
    ):
        raise GateError(
            "downloaded public RC workflow artifact size does not match GitHub metadata"
        )
    public_assets = tuple(record["publicAssets"])
    payloads = public_assets[:-1]
    if public_assets[-1:] != (CHECKSUMS_NAME,) or set(declared) != set(payloads):
        raise GateError(
            "public RC workflow artifact cannot be bound to a closed Release checksum set"
        )
    local_digests = {name: declared[name] for name in payloads}
    local_digests[CHECKSUMS_NAME] = record["sha256sumsSha256"]
    validated_record = RC_ACTIVATION_RECORD_VALIDATOR.ValidatedRecord(
        document=record,
        tag=record["tag"],
        version=record["tag"].removeprefix("v"),
        tag_commit=record["tagCommit"],
        run_id=record["releaseEvidence"]["runId"],
        artifact_id=record["releaseEvidence"]["artifactId"],
        issue_form_filename=record["issueFormFilename"],
        public_assets=public_assets,
        payloads=payloads,
    )
    try:
        members = RC_ACTIVATION_RECORD_VALIDATOR.validate_workflow_artifact_archive(
            artifact_zip, validated_record, local_digests
        )
    except RC_ACTIVATION_RECORD_VALIDATOR.ActivationError as error:
        raise GateError(
            f"public RC workflow artifact failed strong byte binding: {error}"
        ) from None
    if "osv-raw.json" in members:
        raise GateError("public RC workflow artifact must not contain the raw OSV report")
    return {name: members[name] for name in sorted(members)}


def download_and_validate_public_rc_workflow_artifact(
    manifest: dict[str, Any],
    record: dict[str, Any],
    artifact_size: int,
    declared: dict[str, str],
) -> dict[str, str]:
    """Download the exact Actions artifact through authenticated safety-checked gh."""
    gh = require_safe_github_cli_release_verification()
    repository_root = Path(__file__).resolve().parents[2]
    owner = manifest["github_owner"]
    repository = manifest["github_repository"]
    artifact_id = record["releaseEvidence"]["artifactId"]
    endpoint = f"repos/{owner}/{repository}/actions/artifacts/{artifact_id}/zip"
    with tempfile.TemporaryDirectory(prefix="routecontract-public-rc-artifact-") as raw:
        artifact_zip = Path(raw) / "workflow-artifact.zip"
        try:
            RC_ACTIVATION_RECORD_VALIDATOR._download_gh_file(
                gh,
                repository_root,
                endpoint,
                artifact_zip,
                artifact_size,
                accept="application/vnd.github+json",
            )
        except RC_ACTIVATION_RECORD_VALIDATOR.ActivationError as error:
            raise GateError(
                f"could not download exact public RC workflow artifact: {error}"
            ) from None
        return validate_public_rc_workflow_artifact_archive(
            artifact_zip, artifact_size, record, declared
        )


def report_cutoff_utc(content: dict[str, Any]) -> datetime:
    return parse_github_utc(
        content["external_evidence"]["cutoff_utc"], "report external-evidence cutoff"
    )


def _decode_public_contents_file(
    payload: dict[str, Any],
    expected_url: str,
    expected_path: str,
    label: str,
    *,
    maximum_size: int = MAX_PUBLIC_JSON_RESPONSE_BYTES,
) -> tuple[bytes, str]:
    blob_sha = payload.get("sha")
    size = payload.get("size")
    if (
        payload.get("type") != "file"
        or payload.get("html_url") != expected_url
        or payload.get("path") != expected_path
        or payload.get("encoding") != "base64"
        or not isinstance(payload.get("content"), str)
        or not isinstance(blob_sha, str)
        or COMMIT_RE.fullmatch(blob_sha) is None
        or blob_sha == "0" * 40
        or type(size) is not int
        or not 0 < size <= maximum_size
    ):
        raise GateError(f"{label} does not resolve to one bounded public ordinary file")
    try:
        encoded = re.sub(r"\s+", "", payload["content"])
        decoded = base64.b64decode(encoded, validate=True)
    except (ValueError, UnicodeEncodeError) as error:
        raise GateError(f"{label} is not canonical base64 content") from error
    if len(decoded) != size:
        raise GateError(f"{label} decoded size does not match GitHub metadata")
    return decoded, blob_sha


def _decode_activation_record(
    payload: dict[str, Any], expected_url: str, expected_path: str
) -> tuple[dict[str, Any], bytes, str]:
    raw, blob_sha = _decode_public_contents_file(
        payload,
        expected_url,
        expected_path,
        "public RC activation record",
        maximum_size=MAX_PUBLIC_ACTIVATION_RECORD_BYTES,
    )
    try:
        record = _decode_public_json(raw, expected_url)
    except GateError:
        raise GateError(
            "public RC activation record is not canonical base64 UTF-8 strict JSON"
        ) from None
    if not isinstance(record, dict):
        raise GateError("public RC activation record must be a JSON object")
    try:
        reject_placeholders(record, "public RC activation record")
    except RecursionError:
        raise GateError(
            "public RC activation record is not canonical base64 UTF-8 strict JSON"
        ) from None
    return record, raw, blob_sha


def _git_show_bytes(commit: str, path: str) -> bytes:
    repository_root = Path(__file__).resolve().parents[2]
    process = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=repository_root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise GateError(f"local tagged file is unavailable: {path}")
    if not process.stdout or len(process.stdout) > 8_000_000:
        raise GateError(f"local tagged file is empty or too large: {path}")
    return process.stdout


def _decode_utf8_with_required_anchors(
    data: bytes, label: str, anchors: Iterable[str], *, unique: bool = True
) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise GateError(f"{label} is not UTF-8") from error
    for anchor in anchors:
        count = text.count(anchor)
        if (unique and count != 1) or (not unique and count < 1):
            raise GateError(f"{label} is missing one exact required anchor: {anchor}")
    return text


def _validate_tagged_issue_form_bytes(data: bytes, filename: str) -> None:
    expected_sha256 = APPROVED_ISSUE_FORM_SHA256_BY_FILENAME.get(filename)
    if expected_sha256 is None:
        raise GateError("tagged Issue Form version is outside the contest package allowlist")
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise GateError(
            "version-derived tagged Issue Form bytes do not match the reviewed version-specific form"
        )
    checkbox_anchors = tuple(
        f"        - label: {label}\n          required: true"
        for label in RESULT_ISSUE_REQUIRED_CHECKBOXES
    )
    _decode_utf8_with_required_anchors(
        data,
        "version-derived tagged Issue Form",
        (
            "name: Independent RC installation",
            'title: "[independent-install] "',
            "labels: [evidence, community]",
            f"Issue-form source: <record issueFormPermalink>",
            "PUBLIC_RECRUITMENT_RECORD_PERMALINK <exact Issue #9 recruitment comment permalink>",
            *checkbox_anchors,
        ),
    )
    text = data.decode("utf-8")
    task_a_block = (
        "    id: task_a_first_result\n"
        "    attributes:\n"
        "      label: Task A first outcome — exact-tag Quick Start"
    )
    if text.count(task_a_block) != 1 or any(
        text.count(f"        - {outcome}") < 1
        for outcome in ELIGIBLE_TASK_A_OUTCOMES
    ):
        raise GateError("version-derived tagged Issue Form has a malformed Task A outcome field")


def _validate_activation_record_publicly(
    evidence: dict[str, Any], manifest: dict[str, Any], api_base: str, cutoff: datetime,
    repository_node_id: str,
    artifact_binding_cache: dict[str, Any] | None = None,
) -> tuple[datetime, dict[str, Any]]:
    repository_url = manifest["project"]["repository_url"]
    tested_tag = evidence["tested_tag"]
    permalink = evidence["activation_record_url"]
    prefix = f"{repository_url}/blob/"
    suffix = f"/docs/evidence/independent-rc-activation-{tested_tag}.json"
    record_commit = permalink[len(prefix) : -len(suffix)]
    record_path = suffix.removeprefix("/")
    encoded_path = urllib.parse.quote(record_path, safe="/")
    payload = request_json(
        f"{api_base}/contents/{encoded_path}?ref={urllib.parse.quote(record_commit, safe='')}"
    )
    record, raw_record, record_blob_sha = _decode_activation_record(
        payload, permalink, record_path
    )
    tag_commit = record.get("tagCommit")
    expected_release_url = f"{repository_url}/releases/tag/{tested_tag}"
    version = tested_tag.removeprefix("v")
    rc_suffix = tested_tag.rsplit("-", 1)[1]
    issue_form_filename = f"independent-{rc_suffix}-install.yml"
    expected_issue_form_permalink = (
        f"{repository_url}/blob/{tag_commit}/.github/ISSUE_TEMPLATE/"
        f"{issue_form_filename}"
    )
    expected_issue_form_url = (
        f"{repository_url}/issues/new?template={issue_form_filename}"
    )
    expected_public_assets = [
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
    expected_record_keys = {
        "issueFormFilename",
        "issueFormPermalink",
        "issueFormUrl",
        "publicAssets",
        "releaseEvidence",
        "releaseImmutability",
        "releaseState",
        "releaseUrl",
        "repository",
        "schemaVersion",
        "sha256sumsSha256",
        "tag",
        "tagCommit",
        "taggedProtocolUrl",
        "taggedReadmeUrl",
    }
    release_evidence = record.get("releaseEvidence")
    release_immutability = record.get("releaseImmutability")
    if not isinstance(release_evidence, dict) or not isinstance(
        release_immutability, dict
    ):
        raise GateError("public RC activation record has malformed nested objects")
    run_id = release_evidence.get("runId")
    artifact_id = release_evidence.get("artifactId")
    if (
        set(record) != expected_record_keys
        or type(record.get("schemaVersion")) is not int
        or record.get("schemaVersion") != 2
        or record.get("repository") != repository_url
        or record.get("tag") != tested_tag
        or not isinstance(tag_commit, str)
        or COMMIT_RE.fullmatch(tag_commit) is None
        or tag_commit == "0" * 40
        or record.get("releaseUrl") != expected_release_url
        or not isinstance(record.get("releaseState"), dict)
        or set(record["releaseState"]) != {"draft", "immutable", "prerelease"}
        or record["releaseState"].get("draft") is not False
        or record["releaseState"].get("immutable") is not True
        or record["releaseState"].get("prerelease") is not True
        or record.get("issueFormFilename") != issue_form_filename
        or record.get("issueFormPermalink") != expected_issue_form_permalink
        or record.get("issueFormUrl") != expected_issue_form_url
        or record.get("publicAssets") != expected_public_assets
        or record.get("taggedProtocolUrl")
        != f"{repository_url}/blob/{tested_tag}/docs/independent-install-study.md"
        or record.get("taggedReadmeUrl") != f"{repository_url}/blob/{tested_tag}/README.md"
        or set(release_evidence)
        != {"artifactDigest", "artifactFileCount", "artifactId", "headSha", "runId", "runUrl"}
        or release_evidence.get("headSha") != tag_commit
        or type(release_evidence.get("artifactFileCount")) is not int
        or release_evidence.get("artifactFileCount") != 17
        or not isinstance(release_evidence.get("artifactDigest"), str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", release_evidence["artifactDigest"])
        is None
        or release_evidence.get("artifactDigest") == f"sha256:{'0' * 64}"
        or isinstance(run_id, bool)
        or not isinstance(run_id, int)
        or run_id <= 0
        or isinstance(artifact_id, bool)
        or not isinstance(artifact_id, int)
        or artifact_id <= 0
        or release_evidence.get("runUrl") != f"{repository_url}/actions/runs/{run_id}"
        or set(release_immutability) != {"enabled", "enforcedByOwner"}
        or release_immutability.get("enabled") is not True
        or not isinstance(release_immutability.get("enforcedByOwner"), bool)
        or not isinstance(record.get("sha256sumsSha256"), str)
        or SHA256_RE.fullmatch(record["sha256sumsSha256"]) is None
        or record.get("sha256sumsSha256") == "0" * 64
    ):
        raise GateError("public RC activation record does not bind the exact activated RC identity")

    commit_data = request_json(f"{api_base}/commits/{record_commit}")
    parents = commit_data.get("parents") or []
    files = commit_data.get("files") or []
    record_commit_payload = object_or_empty(commit_data.get("commit"))
    record_tree_sha = object_or_empty(record_commit_payload.get("tree")).get("sha")
    record_author_at = parse_github_utc(
        object_or_empty(record_commit_payload.get("author")).get("date"),
        "activation-record commit author date",
    )
    record_committer_at = parse_github_utc(
        object_or_empty(record_commit_payload.get("committer")).get("date"),
        "activation-record commit committer date",
    )
    if (
        commit_data.get("sha") != record_commit
        or [parent.get("sha") for parent in parents] != [tag_commit]
        or len(files) != 1
        or files[0].get("filename") != record_path
        or files[0].get("status") != "added"
        or not isinstance(record_tree_sha, str)
        or COMMIT_RE.fullmatch(record_tree_sha) is None
        or record_tree_sha == "0" * 40
    ):
        raise GateError("activation record is not the one-file direct child of the exact RC tag")

    associated_pulls = request_json_list(
        f"{api_base}/commits/{record_commit}/pulls?per_page=100"
    )
    if len(associated_pulls) >= 100:
        raise GateError("activation-record pull-request association is unbounded")
    expected_repository = f"{manifest['github_owner']}/{manifest['github_repository']}"
    validated_pulls: list[
        tuple[dict[str, Any], dict[str, Any], datetime, dict[str, Any]]
    ] = []
    observed_pull_numbers: set[int] = set()
    for associated_pull in associated_pulls:
        pull_number = associated_pull.get("number")
        pull_id = associated_pull.get("id")
        pull_node_id = associated_pull.get("node_id")
        expected_pull_url = f"{repository_url}/pull/{pull_number}"
        listed_merge_commit = associated_pull.get("merge_commit_sha")
        associated_base = object_or_empty(associated_pull.get("base"))
        associated_base_repository = object_or_empty(associated_base.get("repo"))
        if (
            type(pull_number) is not int
            or pull_number <= 0
            or pull_number in observed_pull_numbers
            or type(pull_id) is not int
            or pull_id <= 0
            or not isinstance(pull_node_id, str)
            or not pull_node_id
            or associated_pull.get("html_url") != expected_pull_url
            or associated_pull.get("state") != "closed"
            or not isinstance(associated_pull.get("merged_at"), str)
            or "merge_commit_sha" not in associated_pull
            or associated_base.get("ref") != "main"
            or associated_base_repository.get("full_name") != expected_repository
            or (
                listed_merge_commit is not None
                and listed_merge_commit != record_commit
            )
        ):
            raise GateError("activation-record pull-request association is malformed")
        observed_pull_numbers.add(pull_number)

        direct_pull = request_json(f"{api_base}/pulls/{pull_number}")
        direct_base = object_or_empty(direct_pull.get("base"))
        direct_base_repository = object_or_empty(direct_base.get("repo"))
        direct_merge_commit = direct_pull.get("merge_commit_sha")
        activation_merged_at = parse_github_utc(
            direct_pull.get("merged_at"), "activation-record pull request merged_at"
        )

        if (
            type(direct_pull.get("number")) is not int
            or direct_pull["number"] <= 0
            or direct_pull["number"] != pull_number
            or type(direct_pull.get("id")) is not int
            or direct_pull["id"] <= 0
            or direct_pull["id"] != pull_id
            or not isinstance(direct_pull.get("node_id"), str)
            or not direct_pull["node_id"]
            or direct_pull["node_id"] != pull_node_id
            or not isinstance(direct_pull.get("html_url"), str)
            or direct_pull.get("html_url") != expected_pull_url
            or not isinstance(direct_pull.get("state"), str)
            or direct_pull.get("state") != "closed"
            or direct_pull.get("merged") is not True
            or not isinstance(direct_pull.get("merged_at"), str)
            or "merge_commit_sha" not in direct_pull
            or (
                direct_merge_commit is not None
                and direct_merge_commit != record_commit
            )
            or direct_base.get("ref") != "main"
            or direct_base_repository.get("full_name") != expected_repository
            or associated_pull.get("state") != direct_pull.get("state")
            or associated_pull.get("merged_at") != direct_pull.get("merged_at")
            or associated_base.get("ref") != direct_base.get("ref")
            or associated_base_repository.get("full_name")
            != direct_base_repository.get("full_name")
            or not record_author_at
            <= record_committer_at
            <= activation_merged_at
            <= cutoff
        ):
            raise GateError(
                "activation-record pull request does not bind the public main merge and cutoff"
            )
        graphql_pull = _validate_graphql_activation_pull(
            request_graphql_activation_pull(
                manifest["github_owner"], manifest["github_repository"], pull_number
            ),
            manifest,
            repository_node_id,
            direct_pull,
            record_commit,
        )
        validated_pulls.append(
            (associated_pull, direct_pull, activation_merged_at, graphql_pull)
        )

    if len(validated_pulls) != 1:
        raise GateError(
            "activation-record commit has no unique server-timestamped main pull request"
        )
    associated_pull, direct_pull, activation_merged_at, graphql_pull = validated_pulls[0]
    pull_number = associated_pull["number"]
    pull_id = associated_pull["id"]
    pull_node_id = associated_pull["node_id"]
    expected_pull_url = f"{repository_url}/pull/{pull_number}"
    record_tree = request_json(f"{api_base}/git/trees/{record_tree_sha}?recursive=1")
    record_tree_entries = record_tree.get("tree")
    if not isinstance(record_tree_entries, list):
        raise GateError("activation-record commit tree is malformed")
    record_entries = [
        entry
        for entry in record_tree_entries
        if isinstance(entry, dict) and entry.get("path") == record_path
    ]
    if (
        record_tree.get("sha") != record_tree_sha
        or record_tree.get("truncated") is not False
        or len(record_entries) != 1
        or record_entries[0].get("mode") != "100644"
        or record_entries[0].get("type") != "blob"
        or record_entries[0].get("sha") != record_blob_sha
    ):
        raise GateError("activation record is not an ordinary 100644 blob in its commit tree")
    public_main = request_json(f"{api_base}/commits/main")
    comparison = request_json(f"{api_base}/compare/{record_commit}...main")
    base_commit = comparison.get("base_commit")
    merge_base = comparison.get("merge_base_commit")
    ahead_by = comparison.get("ahead_by")
    behind_by = comparison.get("behind_by")
    status = comparison.get("status")
    if (
        not isinstance(base_commit, dict)
        or not isinstance(merge_base, dict)
        or public_main.get("sha") != manifest["project"]["commit"]
        or base_commit.get("sha") != record_commit
        or merge_base.get("sha") != record_commit
        or type(ahead_by) is not int
        or type(behind_by) is not int
        or behind_by != 0
        or status not in {"ahead", "identical"}
        or (status == "identical" and ahead_by != 0)
        or (status == "ahead" and ahead_by <= 0)
    ):
        raise GateError("activation-record commit is not an ancestor of final public main")

    form_path = f".github/ISSUE_TEMPLATE/{issue_form_filename}"
    tagged_files = (
        (
            form_path,
            expected_issue_form_permalink,
            tag_commit,
            "version-derived tagged Issue Form",
        ),
        (
            "docs/independent-install-study.md",
            record["taggedProtocolUrl"],
            tested_tag,
            "tagged independent-install protocol",
        ),
        (
            "README.md",
            record["taggedReadmeUrl"],
            tested_tag,
            "tagged README",
        ),
    )
    tagged_file_metadata: dict[str, dict[str, str]] = {}
    for tagged_path, expected_html_url, ref, label in tagged_files:
        encoded_tagged_path = urllib.parse.quote(tagged_path, safe="/")
        tagged_payload = request_json(
            f"{api_base}/contents/{encoded_tagged_path}?ref="
            f"{urllib.parse.quote(ref, safe='')}"
        )
        public_bytes, blob_sha = _decode_public_contents_file(
            tagged_payload, expected_html_url, tagged_path, label
        )
        local_tagged_bytes = _git_show_bytes(tag_commit, tagged_path)
        if public_bytes != local_tagged_bytes:
            raise GateError(f"{label} public bytes differ from the exact local RC tag")
        tagged_file_metadata[tagged_path] = {
            "blob_sha": blob_sha,
            "sha256": hashlib.sha256(public_bytes).hexdigest(),
        }
    form_bytes = _git_show_bytes(tag_commit, form_path)
    current_form_path = Path(__file__).resolve().parents[2] / form_path
    try:
        current_form_bytes = current_form_path.read_bytes()
    except OSError as error:
        raise GateError(f"preserved version-derived Issue Form is unavailable: {error}") from error
    if current_form_path.is_symlink() or current_form_bytes != form_bytes:
        raise GateError("current checkout does not byte-preserve the tagged version-derived Issue Form")
    _validate_tagged_issue_form_bytes(form_bytes, issue_form_filename)
    protocol_bytes = _git_show_bytes(tag_commit, "docs/independent-install-study.md")
    _decode_utf8_with_required_anchors(
        protocol_bytes,
        "tagged independent-install protocol",
        (
            "ROUTECONTRACT_RC_ACTIVATION_VERIFIED",
            "ACTIVATION_RECORD_PERMALINK",
            issue_form_filename,
            "./scripts/quickstart-demo.sh",
            "final stable release",
        ),
        unique=False,
    )
    readme_bytes = _git_show_bytes(tag_commit, "README.md")
    _decode_utf8_with_required_anchors(
        readme_bytes,
        "tagged README",
        ("./scripts/quickstart-demo.sh", "ShardingSphere-JDBC 5.5.3"),
        unique=False,
    )
    tag_commit_data = request_json(f"{api_base}/commits/{tag_commit}")
    tag_tree_sha = object_or_empty(
        object_or_empty(tag_commit_data.get("commit")).get("tree")
    ).get("sha")
    if (
        tag_commit_data.get("sha") != tag_commit
        or not isinstance(tag_tree_sha, str)
        or COMMIT_RE.fullmatch(tag_tree_sha) is None
        or tag_tree_sha == "0" * 40
    ):
        raise GateError("public RC tag commit tree is malformed")
    tag_tree = request_json(f"{api_base}/git/trees/{tag_tree_sha}?recursive=1")
    tag_tree_entries = tag_tree.get("tree")
    if not isinstance(tag_tree_entries, list):
        raise GateError("public RC tag tree is malformed")
    if (
        tag_tree.get("sha") != tag_tree_sha
        or tag_tree.get("truncated") is not False
    ):
        raise GateError("public RC tag tree is truncated or has the wrong identity")
    for tagged_path, _, _, label in tagged_files:
        entries = [
            entry
            for entry in tag_tree_entries
            if isinstance(entry, dict) and entry.get("path") == tagged_path
        ]
        if (
            len(entries) != 1
            or entries[0].get("mode") != "100644"
            or entries[0].get("type") != "blob"
            or entries[0].get("sha")
            != tagged_file_metadata[tagged_path]["blob_sha"]
        ):
            raise GateError(f"{label} is not one exact 100644 blob in the RC tree")

    tag_ref = request_json(
        f"{api_base}/git/ref/tags/{urllib.parse.quote(tested_tag, safe='')}"
    )
    tag_object_reference = object_or_empty(tag_ref.get("object"))
    tag_object_sha = tag_object_reference.get("sha")
    if (
        tag_ref.get("ref") != f"refs/tags/{tested_tag}"
        or tag_object_reference.get("type") != "tag"
        or not isinstance(tag_object_sha, str)
        or COMMIT_RE.fullmatch(tag_object_sha) is None
        or tag_object_sha == "0" * 40
        or tag_object_reference.get("url") != f"{api_base}/git/tags/{tag_object_sha}"
    ):
        raise GateError("public RC tag is missing or is not annotated")
    tag_object = request_json(tag_object_reference["url"])
    if (
        tag_object.get("sha") != tag_object_sha
        or tag_object.get("tag") != tested_tag
        or
        object_or_empty(tag_object.get("object")).get("type") != "commit"
        or object_or_empty(tag_object.get("object")).get("sha") != tag_commit
    ):
        raise GateError("annotated RC tag does not resolve to the activation-record parent")

    run = request_json(f"{api_base}/actions/runs/{run_id}")
    run_created = parse_github_utc(run.get("created_at"), "RC release-evidence run created_at")
    run_updated = parse_github_utc(run.get("updated_at"), "RC release-evidence run updated_at")
    if (
        run.get("id") != run_id
        or run.get("html_url") != release_evidence["runUrl"]
        or run.get("head_sha") != tag_commit
        or run.get("head_branch") != tested_tag
        or run.get("event") != "push"
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("name") != "Release evidence"
        or run.get("path") != ".github/workflows/release-evidence.yml"
        or str(object_or_empty(run.get("repository")).get("full_name", "")).casefold()
        != expected_repository.casefold()
        or run_created > run_updated
    ):
        raise GateError("public RC release-evidence run does not match the activation record")

    artifact = request_json(f"{api_base}/actions/artifacts/{artifact_id}")
    artifact_run = object_or_empty(artifact.get("workflow_run"))
    artifact_size = artifact.get("size_in_bytes")
    artifact_created = parse_github_utc(
        artifact.get("created_at"), "RC workflow artifact created_at"
    )
    artifact_updated = parse_github_utc(
        artifact.get("updated_at"), "RC workflow artifact updated_at"
    )
    if (
        artifact.get("id") != artifact_id
        or artifact.get("name") != f"routecontract-release-evidence-{tag_commit}"
        or artifact.get("digest") != release_evidence["artifactDigest"]
        or artifact.get("expired") is not False
        or type(artifact_size) is not int
        or not 0 < artifact_size <= MAX_PUBLIC_ASSET_BYTES
        or artifact_run.get("id") != run_id
        or artifact_run.get("head_sha") != tag_commit
        or artifact_run.get("head_branch") != tested_tag
        or artifact_created > artifact_updated
    ):
        raise GateError("public RC workflow artifact does not match the activation record")

    release = request_json(
        f"{api_base}/releases/tags/{urllib.parse.quote(tested_tag, safe='')}"
    )
    assets = release.get("assets")
    release_created = parse_github_utc(release.get("created_at"), "RC Release created_at")
    release_published = parse_github_utc(
        release.get("published_at"), "RC Release published_at"
    )
    release_updated = parse_github_utc(release.get("updated_at"), "RC Release updated_at")
    if (
        release.get("draft") is not False
        or release.get("prerelease") is not True
        or release.get("immutable") is not True
        or release.get("tag_name") != tested_tag
        or release.get("html_url") != expected_release_url
        or not isinstance(assets, list)
        or not release_created <= release_published <= release_updated
    ):
        raise GateError("public RC Release is missing, mutable, or not the exact prerelease")

    assets_by_name: dict[str, dict[str, Any]] = {}
    for asset in assets:
        if (
            not isinstance(asset, dict)
            or not isinstance(asset.get("name"), str)
            or asset["name"] in assets_by_name
        ):
            raise GateError("public RC Release contains malformed or duplicate assets")
        assets_by_name[asset["name"]] = asset
    if set(assets_by_name) != set(expected_public_assets):
        raise GateError("public RC Release assets do not match the exact allowlist")

    checksum_asset = assets_by_name[CHECKSUMS_NAME]
    checksum_size = checksum_asset.get("size")
    checksum_download_url = (
        f"{repository_url}/releases/download/{tested_tag}/{CHECKSUMS_NAME}"
    )
    if (
        type(checksum_size) is not int
        or not 0 < checksum_size <= 1_000_000
        or checksum_asset.get("browser_download_url") != checksum_download_url
    ):
        raise GateError("public RC SHA256SUMS asset has an invalid size")
    checksum_bytes = request_bytes(checksum_download_url, limit=1_000_000)
    if len(checksum_bytes) != checksum_size:
        raise GateError("public RC SHA256SUMS download size does not match GitHub metadata")
    checksum_digest = hashlib.sha256(checksum_bytes).hexdigest()
    if checksum_digest != record["sha256sumsSha256"]:
        raise GateError("public RC SHA256SUMS does not match the activation record")
    declared = parse_public_checksum_manifest(checksum_bytes)
    if set(declared) != set(expected_public_assets) - {CHECKSUMS_NAME}:
        raise GateError("public RC SHA256SUMS does not declare the exact payload allowlist")

    asset_updated_times: list[datetime] = []
    asset_snapshot: list[dict[str, Any]] = []
    for name in expected_public_assets:
        asset = assets_by_name[name]
        asset_id = asset.get("id")
        asset_size = asset.get("size")
        asset_created = parse_github_utc(
            asset.get("created_at"), f"RC Release asset {name} created_at"
        )
        asset_updated = parse_github_utc(
            asset.get("updated_at"), f"RC Release asset {name} updated_at"
        )
        expected_digest = (
            record["sha256sumsSha256"] if name == CHECKSUMS_NAME else declared[name]
        )
        expected_api_url = f"{api_base}/releases/assets/{asset_id}"
        expected_download_url = f"{repository_url}/releases/download/{tested_tag}/{name}"
        if (
            type(asset_id) is not int
            or asset_id <= 0
            or type(asset_size) is not int
            or not 0 < asset_size <= MAX_PUBLIC_ASSET_BYTES
            or asset.get("state") != "uploaded"
            or asset.get("digest") != f"sha256:{expected_digest}"
            or asset.get("url") != expected_api_url
            or asset.get("browser_download_url") != expected_download_url
            or not asset_created <= asset_updated <= release_published
        ):
            raise GateError(f"public RC Release asset metadata does not match {name}")
        asset_updated_times.append(asset_updated)
        asset_snapshot.append(
            {
                "id": asset_id,
                "name": name,
                "size": asset_size,
                "state": asset["state"],
                "digest": asset["digest"],
                "url": asset["url"],
                "browser_download_url": asset["browser_download_url"],
                "created_at": asset_created.isoformat(),
                "updated_at": asset_updated.isoformat(),
            }
        )

    cached_members = (
        artifact_binding_cache.get("activation_artifact_member_digests")
        if isinstance(artifact_binding_cache, dict)
        else None
    )
    expected_artifact_names = set(expected_public_assets) | set(
        RC_ACTIVATION_RECORD_VALIDATOR.WORKFLOW_ONLY_FILES
    )
    if (
        isinstance(cached_members, dict)
        and artifact_binding_cache.get("activation_artifact_id") == artifact_id
        and artifact_binding_cache.get("activation_artifact_digest")
        == release_evidence["artifactDigest"]
        and artifact_binding_cache.get("activation_artifact_size_bytes")
        == artifact_size
        and artifact_binding_cache.get("activation_artifact_raw_osv_absent") is True
        and set(cached_members) == expected_artifact_names
        and all(
            isinstance(name, str)
            and isinstance(digest_value, str)
            and SHA256_RE.fullmatch(digest_value) is not None
            for name, digest_value in cached_members.items()
        )
    ):
        artifact_members = dict(cached_members)
    else:
        artifact_members = download_and_validate_public_rc_workflow_artifact(
            manifest, record, artifact_size, declared
        )

    if max(run_updated, artifact_updated) > release_published:
        raise GateError("public RC run/artifact chronology is later than Release publication")
    public_prerequisites_latest = max(
        run_updated, artifact_updated, release_updated, *asset_updated_times
    )
    if not public_prerequisites_latest < activation_merged_at <= cutoff:
        raise GateError(
            "public RC activation prerequisites or main merge fall outside the cutoff order"
        )
    public_prerequisites_latest = activation_merged_at
    success_marker = (
        f"ROUTECONTRACT_RC_ACTIVATION_VERIFIED tag={tested_tag} commit={tag_commit} "
        f"run={run_id} artifact={artifact_id} assets=12"
    )
    return public_prerequisites_latest, {
        "activation_record_url": permalink,
        "activation_record_commit": record_commit,
        "activation_record_blob_sha": record_blob_sha,
        "activation_record_sha256": hashlib.sha256(raw_record).hexdigest(),
        "activation_record_tree_sha": record_tree_sha,
        "activation_record_author_at": record_author_at.isoformat(),
        "activation_record_committer_at": record_committer_at.isoformat(),
        "activation_pull_request": {
            "id": pull_id,
            "node_id": pull_node_id,
            "number": pull_number,
            "url": expected_pull_url,
            "merge_commit_sha": record_commit,
            "merged_at": activation_merged_at.isoformat(),
            "base_ref": "main",
            "base_repository": expected_repository,
            "graphql_verified": graphql_pull,
        },
        "activation_tag_commit": tag_commit,
        "activation_tag_tree_sha": tag_tree_sha,
        "activation_tag_object_sha": tag_object_sha,
        "activation_tagged_files": {
            path: tagged_file_metadata[path] for path, _, _, _ in tagged_files
        },
        "activation_public_prerequisites_latest_at": public_prerequisites_latest.isoformat(),
        "activation_main_comparison": {
            "status": status,
            "ahead_by": ahead_by,
            "behind_by": behind_by,
            "head_sha": public_main["sha"],
        },
        "activation_run": {
            "id": run_id,
            "html_url": run["html_url"],
            "head_sha": run["head_sha"],
            "head_branch": run["head_branch"],
            "event": run["event"],
            "status": run["status"],
            "conclusion": run["conclusion"],
            "name": run["name"],
            "path": run["path"],
            "repository_full_name": run["repository"]["full_name"],
            "created_at": run_created.isoformat(),
            "updated_at": run_updated.isoformat(),
        },
        "activation_artifact": {
            "id": artifact_id,
            "name": artifact["name"],
            "digest": artifact["digest"],
            "expired": artifact["expired"],
            "size_in_bytes": artifact_size,
            "workflow_run": {
                "id": artifact_run["id"],
                "head_sha": artifact_run["head_sha"],
                "head_branch": artifact_run["head_branch"],
            },
            "created_at": artifact_created.isoformat(),
            "updated_at": artifact_updated.isoformat(),
        },
        "activation_release": {
            "tag_name": release["tag_name"],
            "html_url": release["html_url"],
            "draft": release["draft"],
            "prerelease": release["prerelease"],
            "immutable": release["immutable"],
            "created_at": release_created.isoformat(),
            "published_at": release_published.isoformat(),
            "updated_at": release_updated.isoformat(),
            "assets": asset_snapshot,
        },
        "activation_run_id": run_id,
        "activation_artifact_id": artifact_id,
        "activation_artifact_digest": release_evidence["artifactDigest"],
        "activation_artifact_size_bytes": artifact_size,
        "activation_artifact_file_count": len(artifact_members),
        "activation_artifact_member_digests": artifact_members,
        "activation_artifact_raw_osv_absent": "osv-raw.json" not in artifact_members,
        "activation_sha256sums_sha256": record["sha256sumsSha256"],
        "activation_success_marker": success_marker,
    }


def _validate_recruitment_record_publicly(
    evidence: dict[str, Any], manifest: dict[str, Any], api_base: str,
    prerequisites_latest: datetime, activation_metadata: dict[str, Any], cutoff: datetime
) -> tuple[datetime, dict[str, Any]]:
    permalink = evidence["recruitment_record_url"]
    comment_id = permalink.rsplit("#issuecomment-", 1)[1]
    comment = request_json(f"{api_base}/issues/comments/{comment_id}")
    body = comment.get("body")
    owner = manifest["github_owner"]
    user = comment.get("user")
    opening_marker = f"{PUBLIC_RECRUITMENT_MARKER} tag={evidence['tested_tag']}"
    activation_permalink_marker = (
        f"ACTIVATION_RECORD_PERMALINK {evidence['activation_record_url']}"
    )
    if not isinstance(body, str):
        raise GateError("Issue #9 recruitment comment body is missing")
    visible_body = visible_github_markdown_evidence(body)
    if (
        comment.get("html_url") != permalink
        or comment.get("issue_url") != f"{api_base}/issues/9"
        or not isinstance(user, dict)
        or user.get("type") != "User"
        or not isinstance(user.get("login"), str)
        or user["login"].casefold() != owner.casefold()
        or comment.get("author_association") != "OWNER"
        or not contains_unique_body_marker(
            visible_body, opening_marker, f"{PUBLIC_RECRUITMENT_MARKER} "
        )
        or not contains_unique_body_marker(
            visible_body,
            activation_metadata["activation_success_marker"],
            "ROUTECONTRACT_RC_ACTIVATION_VERIFIED ",
        )
        or not contains_unique_body_marker(
            visible_body, activation_permalink_marker, "ACTIVATION_RECORD_PERMALINK "
        )
    ):
        raise GateError("Issue #9 recruitment permalink does not bind the exact public RC opening")
    created_at = parse_github_utc(
        comment.get("created_at"), "public recruitment comment created_at"
    )
    updated_at = parse_github_utc(
        comment.get("updated_at"), "public recruitment comment updated_at"
    )
    if not prerequisites_latest < created_at <= updated_at <= cutoff:
        raise GateError("public recruitment was not opened between activation and cutoff")
    # Results must follow the final public edit, not merely the original comment.
    return updated_at, {
        "recruitment_record_url": permalink,
        "recruitment_created_at": created_at.isoformat(),
        "recruitment_effective_at": updated_at.isoformat(),
        "recruitment_body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "recruitment_author": user["login"],
        "recruitment_author_association": comment["author_association"],
    }


def _issue_label_names(issue: dict[str, Any]) -> set[str]:
    labels = issue.get("labels")
    if not isinstance(labels, list) or any(not isinstance(label, dict) for label in labels):
        raise GateError("public Issue labels are malformed")
    names: set[str] = set()
    for label in labels:
        name = label.get("name")
        if not isinstance(name, str) or not name.strip():
            raise GateError("public Issue has a malformed label name")
        names.add(name.casefold())
    return names


ACTIVATION_PULL_QUERY = """
query RouteContractActivationPull($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    id
    nameWithOwner
    pullRequest(number: $number) {
      id
      databaseId
      number
      url
      state
      merged
      mergedAt
      baseRefName
      baseRepository { id nameWithOwner }
      mergeCommit { oid }
    }
  }
}
""".strip()


ISSUE_EDIT_HISTORY_QUERY = """
query RouteContractIssueEditHistory($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    id
    nameWithOwner
    issue(number: $number) {
      id
      number
      url
      title
      body
      createdAt
      updatedAt
      authorAssociation
      author { __typename login ... on User { id databaseId } }
      editor { __typename login ... on User { id databaseId } }
      lastEditedAt
      includesCreatedEdit
      userContentEdits(first: 1) {
        totalCount
        nodes { id }
        pageInfo { hasNextPage }
      }
      timelineItems(first: 1, itemTypes: [RENAMED_TITLE_EVENT]) {
        totalCount
        nodes { __typename }
        pageInfo { hasNextPage }
      }
    }
  }
}
""".strip()


def _request_authenticated_graphql(
    query: str, owner: str, repository: str, number: int, label: str
) -> dict[str, Any]:
    gh = require_safe_github_cli_release_verification()
    environment = os.environ.copy()
    environment.update(
        {
            "GH_PROMPT_DISABLED": "1",
            "GH_PAGER": "cat",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    output = run(
        [
            gh,
            "api",
            "graphql",
            "--hostname",
            "github.com",
            "--method",
            "POST",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"repo={repository}",
            "-F",
            f"number={number}",
        ],
        env=environment,
        timeout_seconds=60,
        failure_label=f"authenticated GitHub GraphQL {label} query",
    )
    try:
        payload = REPORT_CONTENT_CONTRACT.decode_strict_json(
            output, maximum_bytes=MAX_JSON_TOOL_OUTPUT_BYTES
        )
    except ValueError:
        raise GateError(
            f"authenticated GitHub GraphQL {label} query returned invalid JSON"
        ) from None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"data"}
        or not isinstance(payload["data"], dict)
    ):
        raise GateError(
            f"authenticated GitHub GraphQL {label} query returned errors, extensions, "
            "or a partial envelope"
        )
    return payload


def request_graphql_activation_pull(
    owner: str, repository: str, number: int
) -> dict[str, Any]:
    return _request_authenticated_graphql(
        ACTIVATION_PULL_QUERY, owner, repository, number, "activation Pull Request"
    )


def request_graphql_issue(owner: str, repository: str, number: int) -> dict[str, Any]:
    return _request_authenticated_graphql(
        ISSUE_EDIT_HISTORY_QUERY, owner, repository, number, "Issue"
    )


def _validate_graphql_activation_pull(
    payload: dict[str, Any],
    manifest: dict[str, Any],
    repository_node_id: str,
    rest_pull: dict[str, Any],
    record_commit: str,
) -> dict[str, Any]:
    data = payload.get("data")
    graphql_repository = data.get("repository") if isinstance(data, dict) else None
    pull = (
        graphql_repository.get("pullRequest")
        if isinstance(graphql_repository, dict)
        else None
    )
    base_repository = pull.get("baseRepository") if isinstance(pull, dict) else None
    merge_commit = pull.get("mergeCommit") if isinstance(pull, dict) else None
    expected_repository = (
        f"{manifest['github_owner']}/{manifest['github_repository']}"
    )
    if (
        not isinstance(data, dict)
        or set(data) != {"repository"}
        or not isinstance(graphql_repository, dict)
        or set(graphql_repository) != {"id", "nameWithOwner", "pullRequest"}
        or not isinstance(pull, dict)
        or set(pull)
        != {
            "id",
            "databaseId",
            "number",
            "url",
            "state",
            "merged",
            "mergedAt",
            "baseRefName",
            "baseRepository",
            "mergeCommit",
        }
        or not isinstance(base_repository, dict)
        or set(base_repository) != {"id", "nameWithOwner"}
        or not isinstance(merge_commit, dict)
        or set(merge_commit) != {"oid"}
        or not isinstance(graphql_repository.get("id"), str)
        or not graphql_repository["id"]
        or graphql_repository["id"] != repository_node_id
        or not isinstance(graphql_repository.get("nameWithOwner"), str)
        or graphql_repository.get("nameWithOwner") != expected_repository
        or not isinstance(base_repository.get("id"), str)
        or not base_repository["id"]
        or base_repository["id"] != repository_node_id
        or not isinstance(base_repository.get("nameWithOwner"), str)
        or base_repository.get("nameWithOwner") != expected_repository
        or not isinstance(pull.get("id"), str)
        or not pull["id"]
        or pull["id"] != rest_pull.get("node_id")
        or type(pull.get("databaseId")) is not int
        or pull["databaseId"] <= 0
        or type(rest_pull.get("id")) is not int
        or rest_pull["id"] <= 0
        or pull["databaseId"] != rest_pull["id"]
        or type(pull.get("number")) is not int
        or pull["number"] <= 0
        or type(rest_pull.get("number")) is not int
        or rest_pull["number"] <= 0
        or pull["number"] != rest_pull["number"]
        or not isinstance(pull.get("url"), str)
        or pull.get("url") != rest_pull.get("html_url")
        or not isinstance(pull.get("state"), str)
        or pull.get("state") != "MERGED"
        or pull.get("merged") is not True
        or not isinstance(pull.get("mergedAt"), str)
        or pull.get("mergedAt") != rest_pull.get("merged_at")
        or not isinstance(pull.get("baseRefName"), str)
        or pull.get("baseRefName") != "main"
        or not isinstance(merge_commit.get("oid"), str)
        or merge_commit.get("oid") != record_commit
    ):
        raise GateError(
            "authenticated GitHub GraphQL activation Pull Request does not bind "
            "the exact public main merge"
        )
    return {
        "repository_id": graphql_repository["id"],
        "repository_name_with_owner": graphql_repository["nameWithOwner"],
        "id": pull["id"],
        "database_id": pull["databaseId"],
        "number": pull["number"],
        "url": pull["url"],
        "state": pull["state"],
        "merged": pull["merged"],
        "merged_at": pull["mergedAt"],
        "base_ref": pull["baseRefName"],
        "base_repository_id": base_repository["id"],
        "base_repository_name_with_owner": base_repository["nameWithOwner"],
        "merge_commit_sha": merge_commit["oid"],
    }


def _validate_unedited_graphql_issue(
    rest_issue: dict[str, Any], payload: dict[str, Any], manifest: dict[str, Any],
    repository_node_id: str
) -> dict[str, Any]:
    data = payload.get("data")
    repository = data.get("repository") if isinstance(data, dict) else None
    issue = repository.get("issue") if isinstance(repository, dict) else None
    if not isinstance(repository, dict) or not isinstance(issue, dict):
        raise GateError("authenticated GitHub GraphQL Issue identity is missing")
    rest_user = rest_issue.get("user")
    author = issue.get("author")
    edits = issue.get("userContentEdits")
    renames = issue.get("timelineItems")
    expected_name = f"{manifest['github_owner']}/{manifest['github_repository']}"
    if (
        repository.get("id") != repository_node_id
        or str(repository.get("nameWithOwner", "")).casefold()
        != expected_name.casefold()
        or issue.get("id") != rest_issue.get("node_id")
        or issue.get("number") != rest_issue.get("number")
        or issue.get("url") != rest_issue.get("html_url")
        or issue.get("title") != rest_issue.get("title")
        or issue.get("body") != rest_issue.get("body")
        or issue.get("createdAt") != rest_issue.get("created_at")
        or issue.get("updatedAt") != rest_issue.get("updated_at")
        or issue.get("authorAssociation") != rest_issue.get("author_association")
        or not isinstance(rest_user, dict)
        or not isinstance(author, dict)
        or author.get("__typename") != "User"
        or author.get("login") != rest_user.get("login")
        or author.get("id") != rest_user.get("node_id")
        or author.get("databaseId") != rest_user.get("id")
        or issue.get("editor") is not None
        or issue.get("lastEditedAt") is not None
        or issue.get("includesCreatedEdit") is not False
        or not isinstance(edits, dict)
        or type(edits.get("totalCount")) is not int
        or edits["totalCount"] != 0
        or edits.get("nodes") != []
        or edits.get("pageInfo") != {"hasNextPage": False}
        or not isinstance(renames, dict)
        or type(renames.get("totalCount")) is not int
        or renames["totalCount"] != 0
        or renames.get("nodes") != []
        or renames.get("pageInfo") != {"hasNextPage": False}
    ):
        raise GateError(
            "result Issue is edited, renamed, or not the exact opener-authored GraphQL record"
        )
    return {
        "result_issue_graphql_id": issue["id"],
        "result_issue_author_graphql_id": author["id"],
        "result_issue_edit_history": "no_edits_or_title_renames_visible",
    }


def _result_candidate_signal(issue: dict[str, Any], evidence: dict[str, Any]) -> bool:
    title = issue.get("title")
    body = issue.get("body")
    label_names: set[str] = set()
    labels = issue.get("labels")
    if isinstance(labels, list):
        label_names = {
            str(label.get("name", "")).casefold()
            for label in labels
            if isinstance(label, dict)
        }
    if (
        not isinstance(title, str)
        or not title.startswith("[independent-install] ")
        or not title.removeprefix("[independent-install] ").strip()
        or not {"evidence", "community"}.issubset(label_names)
        or not isinstance(body, str)
    ):
        return False
    # A reserved form-shaped Issue with malformed Markdown is ambiguous, not a
    # harmless contextual record.  Let parser errors fail the collection.  A
    # well-formed NOT_RUN/PROTOCOL_DEVIATION record reaches the structural
    # checks below and is cleanly excluded from the qualified count.
    visible_body = visible_github_markdown_evidence(body)
    activation_url = evidence.get("activation_record_url")
    recruitment_url = evidence.get("recruitment_record_url")
    lines = visible_body.splitlines()
    return bool(
        contains_exact_tag_token(visible_body, evidence["tested_tag"])
        and checked_result_attestations(visible_body)
        and task_a_first_outcome(visible_body) is not None
        and isinstance(activation_url, str)
        and contains_unique_body_marker(
            visible_body,
            f"ACTIVATION_RECORD_PERMALINK {activation_url}",
            "ACTIVATION_RECORD_PERMALINK ",
        )
        and isinstance(recruitment_url, str)
        and contains_unique_body_marker(
            visible_body,
            f"PUBLIC_RECRUITMENT_RECORD_PERMALINK {recruitment_url}",
            "PUBLIC_RECRUITMENT_RECORD_PERMALINK ",
        )
        and sum(
            line.startswith("ROUTECONTRACT_RC_ACTIVATION_VERIFIED ")
            for line in lines
        )
        == 1
    )


def _validate_result_issue_publicly(
    issue: dict[str, Any], evidence: dict[str, Any], manifest: dict[str, Any],
    api_base: str, repository_node_id: str, cutoff: datetime, earliest_time: datetime
) -> dict[str, Any]:
    number = issue.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        raise GateError("result Issue number is not a positive ASCII integer")
    repository_url = manifest["project"]["repository_url"]
    issue_url = f"{repository_url}/issues/{number}"
    body = issue.get("body")
    user = issue.get("user")
    association = issue.get("author_association")
    labels = _issue_label_names(issue)
    owner = manifest["github_owner"]
    if not isinstance(body, str):
        raise GateError("result Issue body is missing")
    visible_body = visible_github_markdown_evidence(body)
    if (
        issue.get("html_url") != issue_url
        or "pull_request" in issue
        or not isinstance(issue.get("title"), str)
        or not issue["title"].startswith("[independent-install] ")
        or not issue["title"].removeprefix("[independent-install] ").strip()
        or not isinstance(user, dict)
        or user.get("type") != "User"
        or not isinstance(user.get("login"), str)
        or not user["login"].strip()
        or type(user.get("id")) is not int
        or user["id"] <= 0
        or not isinstance(user.get("node_id"), str)
        or not user["node_id"].strip()
        or not isinstance(issue.get("node_id"), str)
        or not issue["node_id"].strip()
        or user["login"].casefold() == owner.casefold()
        or association not in ELIGIBLE_AUTHOR_ASSOCIATIONS
        or not contains_exact_tag_token(visible_body, evidence["tested_tag"])
        or not checked_result_attestations(visible_body)
        or task_a_first_outcome(visible_body) is None
        or not {"evidence", "community"}.issubset(labels)
    ):
        raise GateError("result URL is not an eligible participant-owned evidence Issue")
    activation_success = issue.get("_expected_activation_success_marker")
    activation_permalink = (
        f"ACTIVATION_RECORD_PERMALINK {evidence['activation_record_url']}"
    )
    recruitment_permalink = (
        "PUBLIC_RECRUITMENT_RECORD_PERMALINK "
        f"{evidence['recruitment_record_url']}"
    )
    if (
        not isinstance(activation_success, str)
        or not contains_unique_body_marker(
            visible_body, activation_success, "ROUTECONTRACT_RC_ACTIVATION_VERIFIED "
        )
        or not contains_unique_body_marker(
            visible_body, activation_permalink, "ACTIVATION_RECORD_PERMALINK "
        )
        or not contains_unique_body_marker(
            visible_body,
            recruitment_permalink,
            "PUBLIC_RECRUITMENT_RECORD_PERMALINK ",
        )
    ):
        raise GateError(
            "RC result Issue does not bind the exact activation and recruitment records"
        )
    created_at = parse_github_utc(
        issue.get("created_at"), "participant result Issue created_at"
    )
    updated_at = parse_github_utc(
        issue.get("updated_at"), "participant result Issue updated_at"
    )
    if not earliest_time < created_at <= updated_at <= cutoff:
        raise GateError("participant result Issue falls outside the activated cutoff window")
    graphql_metadata = _validate_unedited_graphql_issue(
        issue,
        request_graphql_issue(
            manifest["github_owner"], manifest["github_repository"], number
        ),
        manifest,
        repository_node_id,
    )
    return {
        "result_issue_url": issue_url,
        "result_issue_number": number,
        "result_issue_author": user["login"],
        "result_issue_author_association": association,
        "result_issue_created_at": created_at.isoformat(),
        "result_issue_updated_at": updated_at.isoformat(),
        "result_issue_title": issue["title"],
        "result_issue_labels": sorted(labels),
        "result_issue_task_a_first_outcome": task_a_first_outcome(visible_body),
        "result_issue_body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        **graphql_metadata,
    }


def _split_link_header_value(value: str) -> list[str]:
    if any(ord(character) < 32 and character != "\t" for character in value):
        raise GateError("GitHub Issue pagination Link header contains a control character")
    segments: list[str] = []
    start = 0
    in_angle = False
    in_quote = False
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if in_quote and character == "\\":
            escaped = True
            continue
        if character == '"' and not in_angle:
            in_quote = not in_quote
        elif character == "<" and not in_quote:
            if in_angle:
                raise GateError("GitHub Issue pagination Link header is malformed")
            in_angle = True
        elif character == ">" and not in_quote:
            if not in_angle:
                raise GateError("GitHub Issue pagination Link header is malformed")
            in_angle = False
        elif character == "," and not in_angle and not in_quote:
            segments.append(value[start:index].strip())
            start = index + 1
    if escaped or in_angle or in_quote:
        raise GateError("GitHub Issue pagination Link header is malformed")
    segments.append(value[start:].strip())
    if any(not segment for segment in segments):
        raise GateError("GitHub Issue pagination Link header has an empty entry")
    return segments


def _split_link_parameters(value: str) -> list[str]:
    components: list[str] = []
    start = 0
    in_quote = False
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if in_quote and character == "\\":
            escaped = True
            continue
        if character == '"':
            in_quote = not in_quote
        elif character == ";" and not in_quote:
            components.append(value[start:index])
            start = index + 1
    if escaped or in_quote:
        raise GateError("GitHub Issue pagination Link parameter is malformed")
    components.append(value[start:])
    return components


def _parse_link_headers(values: list[str]) -> dict[str, str]:
    links: dict[str, str] = {}
    for value in values:
        if not isinstance(value, str):
            raise GateError("GitHub Issue pagination Link header is not text")
        for segment in _split_link_header_value(value):
            match = re.fullmatch(r"<([^<>]+)>(.*)", segment)
            if match is None:
                raise GateError("GitHub Issue pagination Link header is malformed")
            url, parameter_text = match.groups()
            parameters: dict[str, str] = {}
            raw_parameters = _split_link_parameters(parameter_text)
            if not raw_parameters or raw_parameters[0].strip():
                raise GateError("GitHub Issue pagination Link parameter is malformed")
            for raw_parameter in raw_parameters[1:]:
                parameter = raw_parameter.strip()
                if not parameter or "=" not in parameter:
                    raise GateError("GitHub Issue pagination Link parameter is malformed")
                name, raw_value = (part.strip() for part in parameter.split("=", 1))
                if re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name) is None:
                    raise GateError("GitHub Issue pagination Link parameter name is malformed")
                name = name.casefold()
                if name in parameters:
                    raise GateError("GitHub Issue pagination Link parameter is repeated")
                if raw_value.startswith('"'):
                    if len(raw_value) < 2 or not raw_value.endswith('"'):
                        raise GateError("GitHub Issue pagination quoted parameter is malformed")
                    raw_value = re.sub(r"\\(.)", r"\1", raw_value[1:-1])
                elif re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", raw_value) is None:
                    raise GateError("GitHub Issue pagination Link parameter value is malformed")
                parameters[name] = raw_value
            relations = parameters.get("rel", "").split()
            if not relations:
                raise GateError("GitHub Issue pagination Link entry has no relation")
            for relation in relations:
                relation = relation.casefold()
                if re.fullmatch(r"[a-z]+", relation) is None:
                    raise GateError("GitHub Issue pagination relation is malformed")
                if relation in links:
                    raise GateError("GitHub Issue pagination Link header repeats a relation")
                links[relation] = url
    return links


def _issue_initial_url(api_base: str, earliest_time: datetime) -> str:
    inclusive_since = earliest_time - timedelta(seconds=1)
    return f"{api_base}/issues?" + urllib.parse.urlencode(
        {
            "state": "all",
            "sort": "created",
            "direction": "asc",
            "since": inclusive_since.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "per_page": "100",
        }
    )


def _validated_issue_operation_key(
    link: str, api_base: str, repository_id: int, earliest_time: datetime
) -> tuple[str, tuple[tuple[str, str], ...]]:
    expected = urllib.parse.urlparse(_issue_initial_url(api_base, earliest_time))
    actual = urllib.parse.urlparse(link)
    try:
        actual_pairs = urllib.parse.parse_qsl(
            actual.query, keep_blank_values=True, strict_parsing=True
        )
        expected_pairs = urllib.parse.parse_qsl(
            expected.query, keep_blank_values=True, strict_parsing=True
        )
    except ValueError as error:
        raise GateError("GitHub Issue pagination link query is malformed") from error
    if len({key for key, _ in actual_pairs}) != len(actual_pairs):
        raise GateError("GitHub Issue pagination link repeats a query parameter")
    actual_query = dict(actual_pairs)
    expected_query = dict(expected_pairs)
    pagination_keys = set(actual_query).intersection({"page", "after", "before"})
    cursor_keys = pagination_keys.intersection({"after", "before"})
    fixed_query = {
        key: value for key, value in actual_query.items() if key not in pagination_keys
    }
    allowed_paths = {expected.path, f"/repositories/{repository_id}/issues"}
    if (
        actual.scheme != "https"
        or actual.netloc != "api.github.com"
        or actual.path not in allowed_paths
        or fixed_query != expected_query
        or actual.params
        or actual.fragment
        or len(cursor_keys) > 1
    ):
        raise GateError("GitHub Issue pagination link is foreign or malformed")
    if "page" in pagination_keys and re.fullmatch(
        r"[1-9][0-9]*", actual_query["page"]
    ) is None:
        raise GateError("GitHub Issue pagination page selector is malformed")
    for selector in pagination_keys.intersection({"after", "before"}):
        value = actual_query[selector]
        if (
            not value
            or len(value) > 4_096
            or any(ord(character) < 33 for character in value)
        ):
            raise GateError("GitHub Issue pagination cursor selector is malformed")
    return (
        f"repository:{repository_id}:issues",
        tuple(sorted(actual_query.items())),
    )


def _enumerate_result_issues(
    evidence: dict[str, Any], manifest: dict[str, Any], api_base: str,
    repository_id: int, repository_node_id: str, earliest_time: datetime, cutoff: datetime,
    activation_success_marker: str | None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    observed_numbers: set[int] = set()
    eligible: list[dict[str, Any]] = []
    fetched_pages = 0
    page_url = _issue_initial_url(api_base, earliest_time)
    visited_targets = {
        _validated_issue_operation_key(
            page_url, api_base, repository_id, earliest_time
        )
    }
    for page_index in range(1, MAX_ISSUE_ENUMERATION_PAGES + 1):
        current_target = _validated_issue_operation_key(
            page_url, api_base, repository_id, earliest_time
        )
        issues, link_headers = request_json_list_page(page_url)
        fetched_pages += 1
        links = _parse_link_headers(link_headers)
        unexpected_relations = set(links) - {"next", "prev", "first", "last"}
        if unexpected_relations:
            raise GateError("GitHub Issue pagination contains an unknown relation")
        link_targets = {
            relation: _validated_issue_operation_key(
                link, api_base, repository_id, earliest_time
            )
            for relation, link in links.items()
        }
        if len(issues) > 100:
            raise GateError("GitHub Issue pagination exceeded per_page=100")
        for listed in issues:
            number = listed.get("number")
            if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
                raise GateError("GitHub Issue enumeration contains a malformed number")
            if number in observed_numbers:
                raise GateError("GitHub Issue pagination repeated an Issue")
            observed_numbers.add(number)
            if listed.get("repository_url") != api_base:
                raise GateError("GitHub Issue enumeration returned a foreign repository item")
            if "pull_request" in listed:
                continue
            created_at = parse_github_utc(
                listed.get("created_at"), f"enumerated Issue #{number} created_at"
            )
            updated_at = parse_github_utc(
                listed.get("updated_at"), f"enumerated Issue #{number} updated_at"
            )
            if created_at < earliest_time or created_at > cutoff:
                continue
            if updated_at < created_at:
                raise GateError("an Issue in the evidence window has reversed timestamps")
            if updated_at > cutoff:
                raise GateError(
                    "an Issue created in the evidence window was edited after cutoff; "
                    "the historical candidate set is ambiguous"
                )
            if not _result_candidate_signal(listed, evidence):
                continue
            direct = request_json(f"{api_base}/issues/{number}")
            listed_user = object_or_empty(listed.get("user"))
            direct_user = object_or_empty(direct.get("user"))
            if (
                direct.get("number") != number
                or direct.get("repository_url") != api_base
                or direct.get("html_url") != listed.get("html_url")
                or direct.get("title") != listed.get("title")
                or direct.get("body") != listed.get("body")
                or direct.get("created_at") != listed.get("created_at")
                or direct.get("updated_at") != listed.get("updated_at")
                or direct.get("author_association") != listed.get("author_association")
                or direct_user.get("login") != listed_user.get("login")
                or direct_user.get("type") != listed_user.get("type")
                or _issue_label_names(direct) != _issue_label_names(listed)
                or ("pull_request" in direct) != ("pull_request" in listed)
            ):
                raise GateError("enumerated Issue changed during public evidence validation")
            if activation_success_marker is not None:
                direct = dict(direct)
                direct["_expected_activation_success_marker"] = activation_success_marker
            eligible.append(
                _validate_result_issue_publicly(
                    direct,
                    evidence,
                    manifest,
                    api_base,
                    repository_node_id,
                    cutoff,
                    earliest_time,
                )
            )
        next_url = links.get("next")
        last_target = link_targets.get("last")
        # A terminal response cannot simultaneously advertise a distinct last
        # page.  Treating the missing ``next`` as EOF in that state would let a
        # partial/malformed Link header hide later eligible Issues.
        if next_url is None and last_target is not None and last_target != current_target:
            raise GateError(
                "GitHub Issue pagination omits next while advertising a later last page"
            )
        if next_url is not None and last_target == current_target:
            raise GateError(
                "GitHub Issue pagination advertises next after the current last page"
            )
        if next_url is None:
            break
        if page_index == MAX_ISSUE_ENUMERATION_PAGES:
            raise GateError("GitHub Issue enumeration exceeded the safety page limit")
        next_target = link_targets["next"]
        if "before" in dict(next_target[1]):
            raise GateError("GitHub Issue pagination next link uses a reverse cursor")
        current_query = dict(current_target[1])
        next_query = dict(next_target[1])
        current_page = int(current_query.get("page", "1"))
        if "page" in next_query and int(next_query["page"]) != current_page + 1:
            raise GateError("GitHub Issue pagination next link skips a numeric page")
        if "page" in current_query and "page" not in next_query:
            raise GateError("GitHub Issue pagination drops its numeric page sequence")
        if next_target in visited_targets:
            raise GateError("GitHub Issue pagination next link forms a loop")
        visited_targets.add(next_target)
        page_url = next_url
    else:
        raise GateError("GitHub Issue enumeration exceeded the safety page limit")
    eligible.sort(key=lambda item: item["result_issue_number"])
    return eligible, {
        "enumeration_pages": fetched_pages,
        "enumeration_unique_items": len(observed_numbers),
        "enumeration_eligible_count": len(eligible),
        "enumeration_eligible_issue_numbers": [
            item["result_issue_number"] for item in eligible
        ],
    }


def validate_public_external_evidence(
    content: dict[str, Any], manifest: dict[str, Any],
    *, artifact_binding_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve every structured external claim against public GitHub state."""
    evidence = content["external_evidence"]
    if evidence.get("branch") not in {"rc_only", "zero"}:
        raise GateError(
            "external evidence supports only rc_only or zero until a distinct "
            "reviewed stable form and protocol exist"
        )
    if evidence["branch"] == "rc_only":
        if (
            type(evidence.get("qualified_result_count")) is not int
            or evidence["qualified_result_count"] != 1
            or not isinstance(evidence.get("result_issue_url"), str)
        ):
            raise GateError("rc_only external evidence requires exactly one typed result")
    elif (
        type(evidence.get("qualified_result_count")) is not int
        or evidence["qualified_result_count"] != 0
        or evidence.get("result_issue_url") is not None
    ):
        raise GateError("zero external evidence requires an exact typed zero result")
    cutoff = report_cutoff_utc(content)
    owner = manifest["github_owner"]
    repository = manifest["github_repository"]
    api_base = (
        "https://api.github.com/repos/"
        f"{urllib.parse.quote(owner)}/{urllib.parse.quote(repository)}"
    )
    repository_payload = request_json(api_base)
    repository_id = repository_payload.get("id")
    repository_node_id = repository_payload.get("node_id")
    if (
        type(repository_id) is not int
        or repository_id <= 0
        or not isinstance(repository_node_id, str)
        or not repository_node_id.strip()
        or str(repository_payload.get("full_name", "")).casefold()
        != f"{owner}/{repository}".casefold()
        or repository_payload.get("private") is not False
        or repository_payload.get("archived") is not False
    ):
        raise GateError("public repository identity for Issue enumeration is invalid")
    result: dict[str, Any] = {
        "branch": evidence["branch"],
        "tested_tag": evidence["tested_tag"],
        "cutoff_utc": cutoff.isoformat(),
        "repository_id": repository_id,
        "repository_node_id": repository_node_id,
        "owner_history_attestation_sha256": hashlib.sha256(
            PUBLIC_EXTERNAL_EVIDENCE_OWNER_ATTESTATION.encode("utf-8")
        ).hexdigest(),
        "owner_history_attestation_confirmed": manifest["participant_attestations"][
            "public_external_evidence_history_and_maintainer_edits_reviewed"
        ],
        "owner_history_attestation_automatically_verified": False,
    }
    activation_time, activation_metadata = _validate_activation_record_publicly(
        evidence,
        manifest,
        api_base,
        cutoff,
        repository_node_id,
        artifact_binding_cache=artifact_binding_cache,
    )
    result.update(activation_metadata)
    recruitment_time, recruitment_metadata = _validate_recruitment_record_publicly(
        evidence,
        manifest,
        api_base,
        activation_time,
        activation_metadata,
        cutoff,
    )
    result.update(recruitment_metadata)
    earliest_time = recruitment_time
    eligible, enumeration = _enumerate_result_issues(
        evidence,
        manifest,
        api_base,
        repository_id,
        repository_node_id,
        earliest_time,
        cutoff,
        activation_metadata["activation_success_marker"],
    )
    derived_count = len(eligible)
    derived_url = eligible[0]["result_issue_url"] if derived_count == 1 else None
    if derived_count != evidence["qualified_result_count"]:
        raise GateError(
            "public Issue enumeration does not match the asserted qualified result count"
        )
    if derived_url != evidence["result_issue_url"]:
        raise GateError(
            "public Issue enumeration does not match the asserted result Issue URL"
        )
    result.update(enumeration)
    result["qualified_result_count"] = derived_count
    result["result_issue_url"] = derived_url
    if derived_count == 1:
        result.update(eligible[0])
    return result


def canonical_external_snapshot_bytes(snapshot: dict[str, Any]) -> bytes:
    if not isinstance(snapshot, dict):
        raise GateError("public external-evidence snapshot must be an object")
    try:
        return json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise GateError("public external-evidence snapshot is not canonical JSON") from error


def canonical_public_snapshot_bytes(snapshot: dict[str, Any]) -> bytes:
    """Canonicalize any projected public-state snapshot for exact comparison."""
    return canonical_external_snapshot_bytes(snapshot)


def _require_same_public_snapshot_shape(
    expected: Any, observed: Any, label: str
) -> None:
    """Reject malformed second observations before canonical JSON comparison."""
    if type(observed) is not type(expected):
        raise GateError(
            f"{label} changed between packaging observations: malformed value type"
        )
    if isinstance(expected, dict):
        if set(observed) != set(expected):
            raise GateError(
                f"{label} changed between packaging observations: malformed object shape"
            )
        for key in expected:
            _require_same_public_snapshot_shape(expected[key], observed[key], label)
    elif isinstance(expected, list):
        if len(observed) != len(expected):
            raise GateError(
                f"{label} changed between packaging observations: malformed list shape"
            )
        for expected_item, observed_item in zip(expected, observed, strict=True):
            _require_same_public_snapshot_shape(expected_item, observed_item, label)


def revalidate_public_external_evidence(
    initial_snapshot: dict[str, Any], content: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    """Repeat the full public collector and reject any eligibility/provenance drift."""
    observed = validate_public_external_evidence(
        content, manifest, artifact_binding_cache=initial_snapshot
    )
    _require_same_public_snapshot_shape(initial_snapshot, observed, "public evidence")
    if canonical_external_snapshot_bytes(observed) != canonical_external_snapshot_bytes(
        initial_snapshot
    ):
        raise GateError(
            "public external-evidence snapshot changed between packaging observations"
        )
    return observed


def validate_public_evidence(
    manifest: dict[str, Any],
    local_video: dict[str, Any],
    evidence: dict[str, Any],
    evidence_dir: Path,
    repository_root: Path,
) -> dict[str, Any]:
    project = manifest["project"]
    owner = manifest["github_owner"]
    repository = manifest["github_repository"]
    encoded_repo = f"{urllib.parse.quote(owner)}/{urllib.parse.quote(repository)}"
    api_base = f"https://api.github.com/repos/{encoded_repo}"

    repository_data = request_json(api_base)
    repository_id = repository_data.get("id")
    repository_node_id = repository_data.get("node_id")
    if (
        type(repository_id) is not int
        or repository_id <= 0
        or not isinstance(repository_node_id, str)
        or not repository_node_id.strip()
        or repository_data.get("private") is not False
        or repository_data.get("archived") is not False
        or repository_data.get("html_url") != project["repository_url"]
    ):
        raise GateError("representative GitHub repository is private or archived")
    if str(repository_data.get("full_name", "")).casefold() != f"{owner}/{repository}".casefold():
        raise GateError("GitHub repository identity does not match the manifest")

    commit_data = request_json(f"{api_base}/commits/{project['commit']}")
    expected_commit_url = f"{project['repository_url']}/commit/{project['commit']}"
    if (
        commit_data.get("sha") != project["commit"]
        or commit_data.get("html_url") != expected_commit_url
    ):
        raise GateError("manifest commit is not publicly readable")

    run_id = project["ci_run_url"].rsplit("/", 1)[1]
    run_data = request_json(f"{api_base}/actions/runs/{run_id}")
    run_created_at = parse_github_utc(
        run_data.get("created_at"), "Release evidence run created_at"
    )
    run_updated_at = parse_github_utc(
        run_data.get("updated_at"), "Release evidence run updated_at"
    )
    if (
        type(run_data.get("id")) is not int
        or run_data["id"] != int(run_id)
        or run_data.get("html_url") != project["ci_run_url"]
        or run_data.get("status") != "completed"
        or run_data.get("conclusion") != "success"
        or run_data.get("head_sha") != project["commit"]
        or run_data.get("name") != "Release evidence"
    ):
        raise GateError("public Release evidence workflow is not green for the final commit")
    expected_workflow_path = ".github/workflows/release-evidence.yml"
    if (
        run_data.get("event") != "push"
        or run_data.get("head_branch") != project["tag"]
        or run_data.get("path") != expected_workflow_path
    ):
        raise GateError(
            "public Release evidence run is not the expected tag-push workflow"
        )
    run_repo = object_or_empty(run_data.get("repository")).get("full_name", "")
    if str(run_repo).casefold() != f"{owner}/{repository}".casefold():
        raise GateError("Actions run belongs to a different repository")

    artifact_id = manifest["release_evidence"]["workflow_artifact_id"]
    artifact_data = request_json(f"{api_base}/actions/artifacts/{artifact_id}")
    expected_artifact_name = f"routecontract-release-evidence-{project['commit']}"
    artifact_run = object_or_empty(artifact_data.get("workflow_run"))
    artifact_size = artifact_data.get("size_in_bytes")
    expected_artifact_api_url = f"{api_base}/actions/artifacts/{artifact_id}"
    expected_artifact_download_url = f"{expected_artifact_api_url}/zip"
    artifact_created_at = parse_github_utc(
        artifact_data.get("created_at"), "Release evidence artifact created_at"
    )
    artifact_updated_at = parse_github_utc(
        artifact_data.get("updated_at"), "Release evidence artifact updated_at"
    )
    artifact_expires_at = parse_github_utc(
        artifact_data.get("expires_at"), "Release evidence artifact expires_at"
    )
    if (
        artifact_data.get("id") != artifact_id
        or artifact_data.get("url") != expected_artifact_api_url
        or artifact_data.get("archive_download_url") != expected_artifact_download_url
        or artifact_data.get("name") != expected_artifact_name
        or artifact_data.get("expired") is not False
        or type(artifact_size) is not int
        or artifact_size != evidence["workflow_artifact_size"]
        or artifact_data.get("digest")
        != f"sha256:{manifest['release_evidence']['workflow_artifact_sha256']}"
        or artifact_run.get("id") != int(run_id)
        or artifact_run.get("head_sha") != project["commit"]
        or artifact_run.get("head_branch") != project["tag"]
        or not run_created_at
        <= artifact_created_at
        <= artifact_updated_at
        <= run_updated_at
        < artifact_expires_at
    ):
        raise GateError(
            "public workflow artifact ID/digest/run/revision does not match local release evidence"
        )

    release_data = request_json(
        f"{api_base}/releases/tags/{urllib.parse.quote(project['tag'], safe='')}"
    )
    release_id = release_data.get("id")
    release_created_at = parse_github_utc(
        release_data.get("created_at"), "final Release created_at"
    )
    release_published_at = parse_github_utc(
        release_data.get("published_at"), "final Release published_at"
    )
    release_updated_at = parse_github_utc(
        release_data.get("updated_at"), "final Release updated_at"
    )
    if (
        type(release_id) is not int
        or release_id <= 0
        or release_data.get("draft") is not False
        or release_data.get("prerelease") is not False
        or release_data.get("tag_name") != project["tag"]
        or not release_created_at <= release_published_at <= release_updated_at
    ):
        raise GateError("final GitHub Release is draft/prerelease or has the wrong tag")
    if release_data.get("immutable") is not True:
        raise GateError("final GitHub Release is not immutable")
    if release_data.get("html_url") != project["release_url"]:
        raise GateError("public GitHub Release URL does not match the manifest")
    release_assets = release_data.get("assets")
    if not isinstance(release_assets, list) or any(
        not isinstance(asset, dict) for asset in release_assets
    ):
        raise GateError("GitHub Release assets are malformed")
    release_assets_by_name: dict[str, list[dict[str, Any]]] = {}
    for asset in release_assets:
        release_assets_by_name.setdefault(str(asset.get("name")), []).append(asset)
    expected_release_names = set(evidence["public_release_assets"])
    if set(release_assets_by_name) != expected_release_names:
        raise GateError(
            "GitHub Release assets violate the exact allowlist; "
            f"missing={sorted(expected_release_names - set(release_assets_by_name))}, "
            f"unexpected={sorted(set(release_assets_by_name) - expected_release_names)}"
        )
    release_asset_snapshot: list[dict[str, Any]] = []
    for asset_name, expected in evidence["public_release_assets"].items():
        matching_assets = release_assets_by_name.get(asset_name, [])
        if len(matching_assets) != 1:
            raise GateError(f"GitHub Release must contain exactly one {asset_name} asset")
        asset = matching_assets[0]
        asset_id = asset.get("id")
        asset_created_at = parse_github_utc(
            asset.get("created_at"), f"GitHub Release asset created_at: {asset_name}"
        )
        asset_updated_at = parse_github_utc(
            asset.get("updated_at"), f"GitHub Release asset updated_at: {asset_name}"
        )
        expected_asset_api_url = f"{api_base}/releases/assets/{asset_id}"
        expected_download_url = (
            f"{project['repository_url']}/releases/download/{project['tag']}/"
            f"{urllib.parse.quote(asset_name, safe='')}"
        )
        if (
            type(asset_id) is not int
            or asset_id <= 0
            or asset.get("url") != expected_asset_api_url
            or asset.get("browser_download_url") != expected_download_url
            or asset.get("state") != "uploaded"
            or not release_created_at
            <= asset_created_at
            <= asset_updated_at
            <= release_updated_at
        ):
            raise GateError(f"GitHub Release asset is not fully uploaded: {asset_name}")
        if asset.get("size") != expected["size"]:
            raise GateError(f"GitHub Release asset size mismatch: {asset_name}")
        published_digest = asset.get("digest")
        if published_digest:
            if published_digest != f"sha256:{expected['sha256']}":
                raise GateError(f"GitHub Release asset digest mismatch: {asset_name}")
        else:
            remote_hash = hash_remote_file(asset["browser_download_url"], expected["size"])
            if remote_hash != expected["sha256"]:
                raise GateError(f"downloaded GitHub Release checksum mismatch: {asset_name}")
        release_asset_snapshot.append(
            {
                "id": asset_id,
                "name": asset_name,
                "state": asset["state"],
                "size": asset["size"],
                "digest": published_digest,
                "url": asset["url"],
                "browser_download_url": asset["browser_download_url"],
                "created_at": asset_created_at.isoformat(),
                "updated_at": asset_updated_at.isoformat(),
            }
        )

    if not run_created_at <= run_updated_at <= release_published_at:
        raise GateError(
            "Release evidence run/artifact chronology is not before Release publication"
        )

    verify_release_attestations(manifest, evidence, evidence_dir)
    # The immutable Release now prevents a later tag rewrite. Recheck origin
    # after that public/attestation gate to close the earlier network TOCTOU.
    validate_remote_tag_identity(repository_root, manifest)

    youtube = public_youtube_metadata(manifest["video"]["youtube_url"])
    validate_public_youtube_contract(manifest, local_video, youtube)

    return {
        "repository": {
            "id": repository_id,
            "node_id": repository_node_id,
            "full_name": repository_data["full_name"],
            "html_url": repository_data["html_url"],
            "private": repository_data["private"],
            "archived": repository_data["archived"],
        },
        "commit": {"sha": commit_data["sha"], "html_url": commit_data["html_url"]},
        "ci_run": {
            "id": run_data["id"],
            "html_url": run_data["html_url"],
            "status": run_data["status"],
            "conclusion": run_data["conclusion"],
            "head_sha": run_data["head_sha"],
            "head_branch": run_data["head_branch"],
            "event": run_data["event"],
            "path": run_data["path"],
            "name": run_data["name"],
            "repository_full_name": run_repo,
            "created_at": run_created_at.isoformat(),
            "updated_at": run_updated_at.isoformat(),
        },
        "workflow_artifact": {
            "id": artifact_data["id"],
            "url": artifact_data["url"],
            "name": artifact_data["name"],
            "size_in_bytes": artifact_size,
            "expired": artifact_data["expired"],
            "digest": artifact_data["digest"],
            "archive_download_url": artifact_data["archive_download_url"],
            "created_at": artifact_created_at.isoformat(),
            "updated_at": artifact_updated_at.isoformat(),
            "expires_at": artifact_expires_at.isoformat(),
            "workflow_run": {
                "id": artifact_run["id"],
                "head_sha": artifact_run["head_sha"],
                "head_branch": artifact_run["head_branch"],
            },
        },
        "release": {
            "id": release_id,
            "tag_name": release_data["tag_name"],
            "html_url": release_data["html_url"],
            "draft": release_data["draft"],
            "prerelease": release_data["prerelease"],
            "immutable": release_data["immutable"],
            "created_at": release_created_at.isoformat(),
            "published_at": release_published_at.isoformat(),
            "updated_at": release_updated_at.isoformat(),
            "assets": sorted(release_asset_snapshot, key=lambda item: item["name"]),
        },
        "youtube_video_id": youtube["id"],
        "youtube_title": youtube["title"],
        "youtube_duration_seconds": youtube["duration_seconds"],
        "youtube_availability": youtube["availability"],
        "youtube_live_status": youtube["live_status"],
        "youtube_age_limit": youtube["age_limit"],
        "youtube_max_video_height": youtube["max_video_height"],
    }


def revalidate_public_evidence(
    initial_snapshot: dict[str, Any],
    manifest: dict[str, Any],
    local_video: dict[str, Any],
    evidence: dict[str, Any],
    evidence_dir: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Repeat the complete public release/CI/video collector before archiving."""
    observed = validate_public_evidence(
        manifest, local_video, evidence, evidence_dir, repository_root
    )
    _require_same_public_snapshot_shape(
        initial_snapshot, observed, "release/CI/video state"
    )
    if canonical_public_snapshot_bytes(observed) != canonical_public_snapshot_bytes(
        initial_snapshot
    ):
        raise GateError("public release/CI/video state changed between packaging observations")
    return observed


def extract_docx_text(path: Path) -> str:
    try:
        with ZipFile(path) as package:
            names = set(package.namelist())
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                raise GateError("generated DOCX is not a valid Word package")
            if any("vbaProject" in name or name.endswith(".bin") for name in names):
                raise GateError("generated report unexpectedly contains executable/binary parts")
            root = ET.fromstring(package.read("word/document.xml"))
    except (BadZipFile, OSError, KeyError, ET.ParseError) as error:
        raise GateError(
            "could not inspect generated DOCX (category=PACKAGE_OR_XML)"
        ) from error
    paragraphs: list[str] = []
    for paragraph in root.iter():
        if paragraph.tag.rsplit("}", 1)[-1] != "p":
            continue
        chunks: list[str] = []
        for element in paragraph.iter():
            local = element.tag.rsplit("}", 1)[-1]
            if local == "t" and element.text:
                # OOXML runs in one paragraph are visually contiguous. Inserting
                # a synthetic separator here corrupts words, years and the SBOM
                # title whenever Writer splits formatting across adjacent runs.
                chunks.append(element.text)
            elif local == "tab":
                chunks.append("\t")
            elif local in {"br", "cr"}:
                chunks.append("\n")
        paragraphs.append("".join(chunks))
    return "\n".join(paragraphs)


def validate_docx_privacy(path: Path) -> None:
    try:
        with ZipFile(path) as package:
            names = set(package.namelist())
            if "docProps/custom.xml" in names:
                raise GateError("generated DOCX unexpectedly contains custom properties")
            core = ET.fromstring(package.read("docProps/core.xml"))
            rsid_count = 0
            for name in names:
                is_story_part = (
                    name == "word/document.xml"
                    or re.fullmatch(r"word/header\d+\.xml", name) is not None
                    or re.fullmatch(r"word/footer\d+\.xml", name) is not None
                    or name in {"word/footnotes.xml", "word/endnotes.xml"}
                )
                if not is_story_part and name not in {
                    "word/settings.xml",
                    "word/styles.xml",
                }:
                    continue
                root = ET.fromstring(package.read(name))
                rsid_count += sum(
                    1
                    for element in root.iter()
                    for attribute in element.attrib
                    if attribute.startswith(f"{{{WORDPROCESSINGML_NAMESPACE}}}rsid")
                )
                rsid_count += sum(
                    1
                    for element in root.iter()
                    if element.tag in DOCX_REVISION_IDENTIFIER_ELEMENT_TAGS
                )
    except (BadZipFile, OSError, KeyError, ET.ParseError) as error:
        if isinstance(error, GateError):
            raise
        raise GateError(
            "could not inspect DOCX privacy metadata (category=PACKAGE_OR_XML)"
        ) from error
    values = {
        element.tag.rsplit("}", 1)[-1]: (element.text or "").strip()
        for element in core
    }
    if values.get("creator") != "RouteContract project" or values.get(
        "lastModifiedBy"
    ) != "RouteContract project":
        raise GateError("DOCX author metadata is not privacy-sanitized")
    if rsid_count:
        raise GateError(
            "DOCX contains Word revision session identifiers "
            f"(count={rsid_count})"
        )
    serialized = ET.tostring(core, encoding="unicode")
    reject_sensitive_metadata(serialized, "DOCX core metadata")


def reject_sensitive_metadata(text: str, label: str) -> None:
    forbidden_literals = (
        "/Users/",
        "\\Users\\",
        "Mobile Documents",
        "com~apple~CloudDocs",
        ".codex",
        ".agents",
        "김 지우",
    )
    leaked = [item for item in forbidden_literals if item.casefold() in text.casefold()]
    email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.IGNORECASE)
    if leaked or email_match:
        categories = []
        if leaked:
            categories.append("PRIVATE_LITERAL")
        if email_match:
            categories.append("EMAIL_ADDRESS")
        raise GateError(
            f"{label} contains private path/identity metadata "
            f"(categories={','.join(categories)}, count={len(leaked) + bool(email_match)})"
        )


def validate_pdf_privacy(path: Path) -> None:
    pdfinfo = shutil.which("pdfinfo")
    pdfdetach = shutil.which("pdfdetach")
    if not pdfinfo or not pdfdetach:
        raise GateError("Poppler pdfinfo and pdfdetach are required for PDF privacy checks")
    info_text = run([pdfinfo, str(path)])
    fields: dict[str, str] = {}
    for line in info_text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    expected = {
        "Author": "RouteContract project",
        "Custom Metadata": "no",
        "UserProperties": "no",
        "Suspects": "no",
        "Form": "none",
        "JavaScript": "no",
        "Encrypted": "no",
    }
    mismatched = {
        key
        for key, value in expected.items()
        if fields.get(key) != value
    }
    if mismatched:
        raise GateError(
            "PDF privacy/safety properties mismatch "
            f"(field_count={len(mismatched)})"
        )
    if fields.get("Creator") != "Writer" or not fields.get("Producer", "").startswith(
        "LibreOffice"
    ):
        raise GateError("PDF must be the inspected LibreOffice Writer export")
    reject_sensitive_metadata(info_text, "PDF document information")

    metadata_text = run([pdfinfo, "-meta", str(path)])
    if metadata_text.strip():
        reject_sensitive_metadata(metadata_text, "PDF XMP metadata")
        try:
            xmp = ET.fromstring(metadata_text.encode("utf-8"))
        except ET.ParseError as error:
            raise GateError("PDF XMP metadata is malformed (category=XML_PARSE)") from error
        creator_values = [
            (element.text or "").strip()
            for creator in xmp.iter()
            if creator.tag.rsplit("}", 1)[-1] == "creator"
            for element in creator.iter()
            if element.tag.rsplit("}", 1)[-1] == "li"
        ]
        if creator_values != ["RouteContract project"]:
            raise GateError(
                "PDF XMP creator is not sanitized "
                f"(field=creator, value_count={len(creator_values)})"
            )

    attachments = run([pdfdetach, "-list", str(path)]).strip()
    if attachments != "0 embedded files":
        raise GateError("PDF must not contain embedded files (category=EMBEDDED_FILE)")
    javascript = run([pdfinfo, "-js", str(path)]).strip()
    if javascript:
        raise GateError("PDF contains document-level JavaScript")


def require_libreoffice_writer() -> str:
    candidates = (
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise GateError("LibreOffice Writer is required for canonical report raster binding")


def export_canonical_report_pdf(docx_path: Path, output_dir: Path) -> Path:
    soffice = require_libreoffice_writer()
    fontconfig_value = os.environ.get("FONTCONFIG_FILE")
    if not isinstance(fontconfig_value, str) or not fontconfig_value:
        raise GateError(
            "FONTCONFIG_FILE must name the exact font configuration used for the report export"
        )
    fontconfig_path = Path(fontconfig_value)
    if (
        not fontconfig_path.is_absolute()
        or fontconfig_path.is_symlink()
        or not fontconfig_path.is_file()
        or not 0 < fontconfig_path.stat().st_size <= 1_000_000
    ):
        raise GateError("FONTCONFIG_FILE is not one bounded absolute regular file")
    if sha256(fontconfig_path) != APPROVED_REPORT_FONTCONFIG_SHA256:
        raise GateError("FONTCONFIG_FILE does not match the reviewed report font configuration")
    profile = output_dir / "libreoffice-profile"
    export_dir = output_dir / "libreoffice-export"
    profile.mkdir()
    export_dir.mkdir()
    run(
        [
            soffice,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            "--nolockcheck",
            f"-env:UserInstallation={profile.resolve().as_uri()}",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(export_dir),
            str(docx_path),
        ]
    )
    rendered = export_dir / f"{docx_path.stem}.pdf"
    if rendered.is_symlink() or not rendered.is_file() or rendered.stat().st_size <= 0:
        raise GateError("LibreOffice did not create the canonical report PDF")
    return rendered


def rasterize_pdf_pages(path: Path, output_dir: Path, label: str) -> list[bytes]:
    pdftoppm = shutil.which("pdftoppm")
    pdfinfo = shutil.which("pdfinfo")
    if not pdftoppm or not pdfinfo:
        raise GateError("Poppler pdftoppm and pdfinfo are required for report raster binding")
    info = run([pdfinfo, str(path)])
    count_match = re.search(r"(?m)^Pages:\s+([0-9]+)\s*$", info)
    if count_match is None:
        raise GateError(f"{label} has no bounded PDF page count")
    page_count = int(count_match.group(1))
    if not 1 <= page_count <= 7:
        raise GateError(f"{label} PDF page count exceeds the report safety limit")
    box_info = run([pdfinfo, "-f", "1", "-l", str(page_count), "-box", str(path)])
    page_sizes = parse_pdf_page_sizes(box_info, page_count)
    if any(
        not 100.0 <= dimension <= 2_000.0
        for page_size in page_sizes
        for dimension in page_size
    ):
        raise GateError(f"{label} has an unsafe PDF page box")
    output_dir.mkdir()
    prefix = output_dir / "page"
    run([pdftoppm, "-r", "144", "-png", str(path), str(prefix)])
    try:
        pages = sorted(
            output_dir.glob("page-*.png"),
            key=lambda item: int(item.stem.rsplit("-", 1)[1]),
        )
    except ValueError as error:
        raise GateError(f"{label} produced a malformed raster page name") from error
    if not pages or any(page.is_symlink() or page.stat().st_size <= 0 for page in pages):
        raise GateError(f"{label} did not rasterize into report pages")
    if len(pages) != page_count:
        raise GateError(f"{label} raster page count differs from pdfinfo")
    return [page.read_bytes() for page in pages]


def validate_pdf_raster_matches_docx(docx_path: Path, supplied_pdf: Path) -> None:
    """Reject text-layer-only or visually masked PDFs using a trusted DOCX export."""
    temp_parent = "/private/tmp" if sys.platform == "darwin" and Path("/private/tmp").is_dir() else None
    with tempfile.TemporaryDirectory(
        prefix=".routecontract-report-raster-", dir=temp_parent
    ) as raw:
        root = Path(raw)
        first_root = root / "first-export"
        second_root = root / "second-export"
        first_root.mkdir()
        second_root.mkdir()
        first_pdf = export_canonical_report_pdf(docx_path, first_root)
        second_pdf = export_canonical_report_pdf(docx_path, second_root)
        first_pages = rasterize_pdf_pages(
            first_pdf, root / "first-pages", "first canonical DOCX export"
        )
        second_pages = rasterize_pdf_pages(
            second_pdf, root / "second-pages", "second canonical DOCX export"
        )
        supplied_pages = rasterize_pdf_pages(
            supplied_pdf, root / "supplied-pages", "supplied report PDF"
        )
        if first_pages != second_pages:
            raise GateError(
                "two isolated canonical DOCX exports produced different visual rasters"
            )
        if len(first_pages) != len(supplied_pages):
            raise GateError("supplied PDF raster page count differs from canonical DOCX export")
        mismatched = [
            index
            for index, (canonical, supplied) in enumerate(
                zip(first_pages, supplied_pages), start=1
            )
            if canonical != supplied
        ]
        if mismatched:
            raise GateError(
                "supplied PDF visual raster differs from canonical DOCX export on pages "
                f"{mismatched}"
            )
        first_text_pages, _ = extract_pdf_pages(first_pdf)
        second_text_pages, _ = extract_pdf_pages(second_pdf)
        supplied_text_pages, _ = extract_pdf_pages(supplied_pdf)
        if first_text_pages != second_text_pages:
            raise GateError(
                "two isolated canonical DOCX exports produced different PDF text layers"
            )
        if supplied_text_pages != first_text_pages:
            raise GateError(
                "supplied PDF text layer differs from the canonical DOCX export"
            )
        first_fragments = Counter(
            pdf_hyperlink_fragments(first_pdf, root / "first-links", "first canonical DOCX export")
        )
        second_fragments = Counter(
            pdf_hyperlink_fragments(second_pdf, root / "second-links", "second canonical DOCX export")
        )
        supplied_fragments = Counter(
            pdf_hyperlink_fragments(supplied_pdf, root / "supplied-links", "supplied report PDF")
        )
        if first_fragments != second_fragments:
            raise GateError(
                "two isolated canonical DOCX exports produced different positioned PDF links"
            )
        if supplied_fragments != first_fragments:
            raise GateError(
                "supplied PDF positioned links differ from the canonical DOCX export"
            )
        first_links = Counter(pdf_hyperlink_rows(first_pdf, len(first_pages)))
        second_links = Counter(pdf_hyperlink_rows(second_pdf, len(second_pages)))
        supplied_links = Counter(pdf_hyperlink_rows(supplied_pdf, len(supplied_pages)))
        if first_links != second_links:
            raise GateError(
                "two isolated canonical DOCX exports produced different PDF link annotations"
            )
        if supplied_links != first_links:
            raise GateError(
                "supplied PDF link annotations differ from the canonical DOCX export"
            )


def parse_pdf_page_sizes(info: str, page_count: int) -> list[tuple[float, float]]:
    size_matches = re.findall(
        r"(?m)^Page\s+([0-9]+)\s+size:\s+([0-9.]+)\s+x\s+([0-9.]+)\s+pts"
        r"(?:\s+\([^()\r\n]*\))?\s*$",
        info,
    )
    expected_pages = set(range(1, page_count + 1))
    observed_pages = [int(page) for page, _, _ in size_matches]
    if len(size_matches) != page_count or set(observed_pages) != expected_pages:
        raise GateError(
            "pdfinfo did not report exactly one physical size for every PDF page"
        )
    sizes_by_page = {
        int(page): (float(width), float(height))
        for page, width, height in size_matches
    }
    return [sizes_by_page[index] for index in range(1, page_count + 1)]


def extract_pdf_pages(path: Path) -> tuple[list[str], list[tuple[float, float]]]:
    pdftotext = shutil.which("pdftotext")
    pdfinfo = shutil.which("pdfinfo")
    if not pdftotext or not pdfinfo:
        raise GateError("Poppler pdftotext and pdfinfo are required for final report verification")
    info = run([pdfinfo, str(path)])
    match = re.search(r"(?m)^Pages:\s+([0-9]+)\s*$", info)
    if match is None:
        raise GateError("pdfinfo did not report the PDF page count")
    page_count = int(match.group(1))
    text = run([pdftotext, "-layout", str(path), "-"])
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    if len(pages) != page_count:
        raise GateError(
            f"PDF text page count mismatch: pdfinfo={page_count}, extracted={len(pages)}"
        )
    box_info = run(
        [pdfinfo, "-f", "1", "-l", str(page_count), "-box", str(path)]
    )
    return pages, parse_pdf_page_sizes(box_info, page_count)


def normalize_visible_text(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", text))


def page_contains_sbom_row(page: str, row: dict[str, str]) -> bool:
    normalized_page = normalize_visible_text(page)
    name_tokens = [
        normalize_visible_text(token)
        for token in re.split(r"\s+", row["name"].strip())
        if token
    ]
    version = normalize_visible_text(row["version"])
    return bool(name_tokens and version) and all(
        token in normalized_page for token in (*name_tokens, version)
    )


def visible_report_values(content: dict[str, Any]) -> list[str]:
    values: list[str] = []
    metadata = content.get("metadata", {})
    if isinstance(metadata, dict):
        values.extend(str(value) for value in metadata.values())
    assets = content.get("assets", {})
    if isinstance(assets, dict):
        for asset in assets.values():
            if isinstance(asset, dict) and isinstance(asset.get("caption"), str):
                values.append(asset["caption"])
    for key in (
        "project_intro",
        "background",
        "environment",
        "architecture",
        "features",
        "effects",
        "other",
    ):
        blocks = content.get(key, [])
        if isinstance(blocks, list):
            for block in blocks:
                if isinstance(block, dict):
                    values.extend(
                        value for field in ("lead", "text") if isinstance((value := block.get(field)), str)
                    )
    sbom = content.get("sbom", [])
    if isinstance(sbom, list):
        for row in sbom:
            if isinstance(row, dict):
                values.extend(str(value) for value in row.values())
    return [value for value in values if value.strip()]


def expected_report_hyperlink_targets(
    content: dict[str, Any], manifest: dict[str, Any]
) -> set[str]:
    """Return the closed, structured allowlist of report link targets."""
    metadata = object_or_empty(content.get("metadata"))
    project = object_or_empty(manifest.get("project"))
    evidence = object_or_empty(content.get("external_evidence"))
    targets = {
        metadata.get("repository_url"),
        metadata.get("video_url"),
        project.get("ci_run_url"),
        project.get("release_url"),
        evidence.get("activation_record_url"),
        evidence.get("recruitment_record_url"),
        evidence.get("protocol_issue_url"),
        UPSTREAM_ISSUE_38456_URL,
    }
    if evidence.get("branch") == "rc_only":
        targets.add(evidence.get("result_issue_url"))
    rows = content.get("sbom")
    if not isinstance(rows, list):
        raise GateError("report SBOM rows are missing while deriving hyperlink targets")
    for row in rows:
        if not isinstance(row, dict):
            raise GateError("report SBOM row is malformed while deriving hyperlink targets")
        targets.add(row.get("url"))
    if None in targets or any(not isinstance(target, str) for target in targets):
        raise GateError("report structured hyperlink target is missing")
    for target in targets:
        assert isinstance(target, str)
        parsed = urllib.parse.urlparse(target)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or not target.isascii()
            or target != target.strip()
            or any(ord(character) < 33 for character in target)
        ):
            raise GateError("report contains an unsafe structured hyperlink target")
    return {target for target in targets if isinstance(target, str)}


def expected_report_hyperlink_bindings(
    content: dict[str, Any], manifest: dict[str, Any]
) -> set[tuple[str, str]]:
    """Bind each visible DOCX link label to its reviewed structured target."""
    metadata = object_or_empty(content.get("metadata"))
    project = object_or_empty(manifest.get("project"))
    evidence = object_or_empty(content.get("external_evidence"))
    pairs = {
        (metadata.get("repository_url"), metadata.get("repository_url")),
        (metadata.get("video_url"), metadata.get("video_url")),
        (project.get("ci_run_url"), project.get("ci_run_url")),
        (project.get("release_url"), project.get("release_url")),
        ("[활성화 기록]", evidence.get("activation_record_url")),
        ("[모집 기록]", evidence.get("recruitment_record_url")),
        ("[검증 프로토콜]", evidence.get("protocol_issue_url")),
        ("#38456", UPSTREAM_ISSUE_38456_URL),
    }
    if evidence.get("branch") == "rc_only":
        pairs.add(("[결과 Issue]", evidence.get("result_issue_url")))
    rows = content.get("sbom")
    if not isinstance(rows, list):
        raise GateError("report SBOM rows are missing while deriving hyperlink labels")
    for row in rows:
        if not isinstance(row, dict):
            raise GateError("report SBOM row is malformed while deriving hyperlink labels")
        pairs.add((row.get("url"), row.get("url")))
    if any(
        not isinstance(display, str)
        or not display
        or not isinstance(target, str)
        or not target
        for display, target in pairs
    ):
        raise GateError("report structured hyperlink label or target is missing")
    return {(display, target) for display, target in pairs if isinstance(display, str) and isinstance(target, str)}


def validate_docx_hyperlinks(
    path: Path, content: dict[str, Any], manifest: dict[str, Any]
) -> None:
    relationship_namespace = (
        "http://schemas.openxmlformats.org/package/2006/relationships"
    )
    office_relationship_namespace = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    )
    word_namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    try:
        with ZipFile(path) as package:
            document = ET.fromstring(package.read("word/document.xml"))
            relationships = ET.fromstring(
                package.read("word/_rels/document.xml.rels")
            )
    except (BadZipFile, OSError, KeyError, ET.ParseError) as error:
        raise GateError(
            "could not inspect DOCX hyperlinks (category=PACKAGE_OR_XML)"
        ) from error
    relationship_targets: dict[str, str] = {}
    for relationship in relationships.findall(
        f"{{{relationship_namespace}}}Relationship"
    ):
        if relationship.get("Type", "").endswith("/hyperlink"):
            relationship_id = relationship.get("Id")
            target = relationship.get("Target")
            if (
                not relationship_id
                or not target
                or relationship.get("TargetMode") != "External"
                or relationship_id in relationship_targets
            ):
                raise GateError("DOCX contains a malformed external hyperlink relationship")
            relationship_targets[relationship_id] = target
    hyperlink_nodes = list(document.iter(f"{{{word_namespace}}}hyperlink"))
    used_ids = [
        node.get(f"{{{office_relationship_namespace}}}id") for node in hyperlink_nodes
    ]
    if any(not relationship_id for relationship_id in used_ids):
        raise GateError("DOCX contains an unbound hyperlink node")
    if set(used_ids) != set(relationship_targets):
        raise GateError("DOCX hyperlink nodes and relationships are not exactly bound")
    actual = {relationship_targets[relationship_id] for relationship_id in used_ids}
    expected = expected_report_hyperlink_targets(content, manifest)
    if actual != expected:
        raise GateError(
            "DOCX hyperlink targets differ from the exact materialized report URLs: "
            f"missing_count={len(expected - actual)}, extra_count={len(actual - expected)}"
        )
    actual_bindings = {
        ("".join(node.itertext()), relationship_targets[relationship_id])
        for node, relationship_id in zip(hyperlink_nodes, used_ids)
    }
    expected_bindings = expected_report_hyperlink_bindings(content, manifest)
    if actual_bindings != expected_bindings:
        raise GateError(
            "DOCX visible hyperlink labels differ from their exact structured targets: "
            f"missing_count={len(expected_bindings - actual_bindings)}, "
            f"extra_count={len(actual_bindings - expected_bindings)}"
        )


def pdf_hyperlink_fragments(
    path: Path, output_dir: Path, label: str
) -> list[tuple[int, int, int, int, int, str, str]]:
    """Extract positioned visible hyperlink fragments using Poppler's XML view."""
    pdftohtml = shutil.which("pdftohtml")
    if not pdftohtml:
        raise GateError("Poppler pdftohtml is required for positioned PDF link checks")
    output_dir.mkdir()
    xml_path = output_dir / "links.xml"
    run([pdftohtml, "-xml", "-hidden", "-i", "-q", str(path), str(xml_path)])
    if xml_path.is_symlink() or not xml_path.is_file() or not 0 < xml_path.stat().st_size <= 32_000_000:
        raise GateError(f"{label} did not produce one bounded hyperlink XML view")
    try:
        root = ET.fromstring(xml_path.read_bytes())
    except ET.ParseError as error:
        raise GateError(f"{label} hyperlink XML is malformed") from error
    fragments: list[tuple[int, int, int, int, int, str, str]] = []
    pages = root.findall("page")
    if not 1 <= len(pages) <= 7:
        raise GateError(f"{label} hyperlink XML has an unsafe page count")
    for expected_page, page in enumerate(pages, start=1):
        if page.get("number") != str(expected_page):
            raise GateError(f"{label} hyperlink XML page numbering is noncanonical")
        for text_node in page.findall("text"):
            try:
                top, left, width, height = (
                    int(text_node.get(name, ""))
                    for name in ("top", "left", "width", "height")
                )
            except ValueError as error:
                raise GateError(f"{label} hyperlink fragment coordinates are malformed") from error
            if min(top, left, width, height) < 0 or width == 0 or height == 0:
                raise GateError(f"{label} hyperlink fragment has unsafe geometry")
            for anchor in text_node.iter("a"):
                target = anchor.get("href")
                visible = "".join(anchor.itertext())
                if not isinstance(target, str) or not target.startswith("https://") or not visible:
                    raise GateError(f"{label} contains a malformed positioned hyperlink")
                fragments.append(
                    (expected_page, top, left, width, height, target, visible)
                )
    return fragments


def pdf_hyperlink_rows(path: Path, page_count: int) -> list[tuple[int, str]]:
    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        raise GateError("Poppler pdfinfo is required for PDF hyperlink checks")
    output = run([pdfinfo, "-url", str(path)])
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines or re.fullmatch(r"\s*Page\s+Type\s+URL\s*", lines[0]) is None:
        raise GateError("pdfinfo did not return the expected hyperlink table")
    actual: list[tuple[int, str]] = []
    for line in lines[1:]:
        match = re.fullmatch(r"\s*([1-9][0-9]*)\s+Annotation\s+(https://\S+)\s*", line)
        if match is None:
            raise GateError("PDF contains a malformed or non-HTTPS link annotation")
        page = int(match.group(1))
        if page > page_count:
            raise GateError("PDF hyperlink annotation names an out-of-range page")
        actual.append((page, match.group(2)))
    return actual


def validate_pdf_hyperlinks(
    path: Path,
    content: dict[str, Any],
    manifest: dict[str, Any],
    page_count: int,
) -> None:
    rows = pdf_hyperlink_rows(path, page_count)
    actual = {target for _, target in rows}
    expected = expected_report_hyperlink_targets(content, manifest)
    if actual != expected:
        raise GateError(
            "PDF link annotations differ from the exact materialized report URLs: "
            f"missing_count={len(expected - actual)}, extra_count={len(actual - expected)}"
        )


def external_evidence_summary(content: dict[str, Any]) -> str:
    rows = [
        block.get("text")
        for block in content.get("other", [])
        if isinstance(block, dict) and block.get("lead") == "외부 검증"
    ]
    if len(rows) != 1 or not isinstance(rows[0], str) or not rows[0].strip():
        raise GateError("materialized report must contain one external-evidence summary")
    return rows[0]


def minimum_subsequence_extra_characters(haystack: str, needle: str) -> int | None:
    """Return the smallest number of interleaved characters preserving needle order."""
    if not needle:
        return 0
    best: int | None = None
    search_from = 0
    while True:
        start = haystack.find(needle[0], search_from)
        if start < 0:
            return best
        cursor = start
        for character in needle:
            cursor = haystack.find(character, cursor)
            if cursor < 0:
                return best
            cursor += 1
        end = cursor
        cursor = end - 1
        minimal_start = cursor
        for character in reversed(needle):
            position = haystack.rfind(character, start, cursor + 1)
            if position < 0:  # pragma: no cover - forward match guarantees this
                break
            minimal_start = position
            cursor = position - 1
        else:
            extra = end - minimal_start - len(needle)
            best = extra if best is None else min(best, extra)
            if best == 0:
                return 0
            search_from = minimal_start + 1
            continue
        search_from = start + 1


def visible_report_block_rows(content: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for key in (
        "project_intro",
        "background",
        "environment",
        "architecture",
        "features",
        "effects",
        "other",
    ):
        for block in content.get(key, []):
            if isinstance(block, dict) and all(
                isinstance(block.get(field), str) for field in ("lead", "text")
            ):
                rows.append(block["lead"] + block["text"])
    return rows


def validate_pdf_metadata_and_caption_binding(
    pdf_text: str, content: dict[str, Any]
) -> None:
    normalized_pdf = normalize_visible_text(pdf_text)
    metadata = content["metadata"]
    label_values = (
        ("팀명", metadata["team_name"], 16),
        (
            "팀인원",
            metadata["team_size"],
            len(normalize_visible_text(metadata["team_name"])) + 32,
        ),
        ("참가부문", metadata["division"], 16),
        ("과제유형", metadata["task_type"], 16),
        ("프로젝트명", metadata["project_name"], 16),
        ("프로젝트등록", metadata["repository_url"], 16),
        ("시연영상", metadata["video_url"], 16),
    )
    for label, value, maximum_extra in label_values:
        extra = minimum_subsequence_extra_characters(
            normalized_pdf, normalize_visible_text(label + value)
        )
        if extra is None or extra > maximum_extra:
            raise GateError(
                f"PDF does not bind report metadata label {label!r} to its canonical value"
            )

    captions = [
        asset["caption"]
        for asset in content["assets"].values()
        if isinstance(asset, dict) and isinstance(asset.get("caption"), str)
    ]
    if captions and minimum_subsequence_extra_characters(
        normalized_pdf, normalize_visible_text("".join(captions))
    ) is None:
        raise GateError("PDF does not preserve canonical figure-number/caption order")


def validate_pdf_sbom_row_binding(
    pdf_text: str, sbom_rows: list[dict[str, str]]
) -> None:
    """Bind each SBOM tuple to its numbered row in Poppler's layout text.

    Wrapped cells are interleaved by vertical position, so a contiguous tuple
    is not available. Composite version tokens may straddle their numbered row.
    A header-derived version-column anchor owns those tokens by their unique
    nearest marker; bounded midpoint windows independently require the complete
    row character multiset.
    """
    lines = pdf_text.splitlines()
    title_indexes = [
        index
        for index, line in enumerate(lines)
        if normalize_visible_text(line)
        == normalize_visible_text("붙임1 SBOM(소프트웨어 자재명세서)")
    ]
    if len(title_indexes) != 1:
        raise GateError("PDF must contain one visible Attachment 1 SBOM title")
    title_index = title_indexes[0]
    header_indexes = [
        index
        for index in range(title_index + 1, len(lines))
        if all(
            token in lines[index]
            for token in ("번호", "라이브러리명", "버전", "라이선스")
        )
    ]
    if len(header_indexes) != 1:
        raise GateError("PDF Attachment 1 has no unique visible SBOM header")
    header_index = header_indexes[0]
    header_line = lines[header_index]
    version_header_start = header_line.index("버전")
    license_header_start = header_line.index("라이선스")
    if license_header_start <= version_header_start + 1:
        raise GateError("PDF Attachment 1 SBOM version column is malformed")
    version_column_start = max(0, version_header_start - 6)
    marker_indexes: list[int] = []
    search_from = header_index + 1
    for number, row in enumerate(sbom_rows, start=1):
        candidates = [
            index
            for index in range(search_from, len(lines))
            if re.match(rf"^\s*{number}\s+", lines[index])
        ]
        if len(candidates) != 1:
            raise GateError(f"PDF SBOM row {number} has no unique numbered line")
        marker = candidates[0]
        marker_indexes.append(marker)
        search_from = marker + 1

    # Bind the version column independently of the deliberately wider row
    # windows below. Writer may split a composite version above and below its
    # numbered marker. Each semantic token must occur exactly once in the
    # version column, and the mean token line must have this row's marker as
    # its unique nearest marker. A neighbouring row therefore cannot lend its
    # version to an overlapping wrapped-cell window.
    for offset, row in enumerate(sbom_rows):
        version_tokens = [
            normalize_visible_text(token)
            for token in row["version"].split("/")
            if normalize_visible_text(token)
        ]
        token_lines: list[int] = []
        for token in version_tokens:
            pattern = re.compile(
                rf"(?<![0-9A-Za-z]){re.escape(token)}(?![0-9A-Za-z])"
            )
            occurrences = [
                index
                for index in range(header_index + 1, len(lines))
                if pattern.search(
                    unicodedata.normalize(
                        "NFC", lines[index][version_column_start:license_header_start]
                    )
                )
            ]
            if len(occurrences) != 1:
                raise GateError(
                    f"PDF SBOM row {offset + 1} has a missing or duplicate version token"
                )
            token_lines.append(occurrences[0])
        anchor = sum(token_lines) / len(token_lines)
        anchor_distances = [abs(marker - anchor) for marker in marker_indexes]
        anchor_nearest = min(anchor_distances)
        if (
            anchor_distances.count(anchor_nearest) != 1
            or anchor_distances.index(anchor_nearest) != offset
        ):
            raise GateError(
                f"PDF SBOM row {offset + 1} version token is associated with "
                "another numbered row"
            )
        for token_line in token_lines:
            distances = [abs(marker - token_line) for marker in marker_indexes]
            nearest = min(distances)
            if distances.count(nearest) != 1 or distances.index(nearest) != offset:
                raise GateError(
                    f"PDF SBOM row {offset + 1} version token is associated with "
                    "another numbered row"
                )

    for offset, (marker, row) in enumerate(zip(marker_indexes, sbom_rows)):
        if offset == 0:
            first = header_index + 1
        else:
            previous_marker = marker_indexes[offset - 1]
            first = max(previous_marker + 1, (previous_marker + marker) // 2)
        if offset + 1 == len(marker_indexes):
            last = len(lines) - 1
        else:
            next_marker = marker_indexes[offset + 1]
            last = min(next_marker - 1, (marker + next_marker + 1) // 2)
        window = Counter(normalize_visible_text("\n".join(lines[first : last + 1])))
        expected = Counter(
            normalize_visible_text(
                "".join(row[field] for field in ("name", "version", "license", "url", "purpose"))
            )
        )
        if expected - window:
            raise GateError(
                f"PDF SBOM row {offset + 1} does not preserve its canonical component tuple"
            )


def validate_report_visible_content(
    docx_text: str, pdf_text: str, content: dict[str, Any]
) -> None:
    """Bind the canonical DOCX to the geometrically extracted PDF text layer.

    Writer/Poppler can interleave adjacent table cells and page-boundary labels,
    so arbitrary cell values are not required to remain contiguous in PDF text.
    The complete visible character inventory must still match, while the one
    generated external-evidence sentence must remain exact and contiguous in
    both formats.
    """
    normalized_docx = normalize_visible_text(docx_text)
    normalized_pdf = normalize_visible_text(pdf_text)
    if Counter(normalized_docx) != Counter(normalized_pdf):
        raise GateError(
            "PDF visible-text inventory differs from the canonical strict DOCX"
        )
    report_values = visible_report_values(content)
    missing_docx_indexes = [
        index
        for index, value in enumerate(report_values)
        if normalize_visible_text(value) not in normalized_docx
    ]
    if missing_docx_indexes:
        raise GateError(
            "generated DOCX is missing canonical content values "
            f"(count={len(missing_docx_indexes)}, indexes={missing_docx_indexes[:10]})"
        )
    summary = normalize_visible_text(external_evidence_summary(content))
    if normalized_docx.count(summary) != 1 or normalized_pdf.count(summary) != 1:
        raise GateError(
            "generated external-evidence summary must appear exactly once in DOCX and PDF"
        )
    unordered_pdf_value_indexes = []
    for index, value in enumerate(report_values):
        normalized = normalize_visible_text(value)
        extra = minimum_subsequence_extra_characters(normalized_pdf, normalized)
        if extra is None or extra > MAX_PDF_VALUE_INTERLEAVED_CHARACTERS:
            unordered_pdf_value_indexes.append(index)
    if unordered_pdf_value_indexes:
        raise GateError(
            "PDF is missing the ordered semantic text of canonical values "
            f"(count={len(unordered_pdf_value_indexes)}, "
            f"indexes={unordered_pdf_value_indexes[:10]})"
        )
    report_rows = visible_report_block_rows(content)
    unordered_pdf_row_indexes = []
    for index, row in enumerate(report_rows):
        normalized = normalize_visible_text(row)
        extra = minimum_subsequence_extra_characters(normalized_pdf, normalized)
        if extra is None or extra > MAX_PDF_BLOCK_ROW_INTERLEAVED_CHARACTERS:
            unordered_pdf_row_indexes.append(index)
    if unordered_pdf_row_indexes:
        raise GateError(
            "PDF does not preserve canonical lead-to-text row order "
            f"(count={len(unordered_pdf_row_indexes)}, "
            f"indexes={unordered_pdf_row_indexes[:10]})"
        )
    validate_pdf_metadata_and_caption_binding(pdf_text, content)
    validate_pdf_sbom_row_binding(pdf_text, content["sbom"])


def validate_report_text_contract(docx_text: str, pdf_text: str) -> None:
    for label, text in (("DOCX", docx_text), ("PDF", pdf_text)):
        compact = normalize_visible_text(text)
        placeholder_count = _unresolved_gate_count(text)
        if placeholder_count:
            raise GateError(
                f"{label} contains unresolved gates (count={placeholder_count})"
            )
        evidence_id_count = REPORT_CONTENT_CONTRACT.count_reader_facing_evidence_ids(
            text
        )
        if evidence_id_count:
            raise GateError(
                f"{label} contains reader-facing audit evidence IDs "
                f"(count={evidence_id_count})"
            )
        if "결과보고서 작성 안내" in text:
            raise GateError(f"{label} still contains the organizer writing-guide page")
        if "AI 모델 활용 및 라이선스 기술 명세서" in text:
            raise GateError(f"{label} incorrectly contains inapplicable Attachment 2")
        if normalize_visible_text("SBOM(소프트웨어 자재명세서)") not in compact:
            raise GateError(f"{label} is missing mandatory Attachment 1 SBOM")
        if (
            normalize_visible_text("개발 보조 AI") not in compact
            or normalize_visible_text(NO_RUNTIME_AI_DISCLOSURE) not in compact
        ):
            raise GateError(f"{label} is missing the development-AI/no-runtime-AI disclosure")


def report_page_contract(
    pages: list[str],
    page_sizes: list[tuple[float, float]],
    sbom_rows: list[dict[str, str]],
) -> dict[str, int]:
    if len(page_sizes) != len(pages):
        raise GateError("PDF text and physical page-size counts do not match")
    blank_pages = [index + 1 for index, page in enumerate(pages) if not page.strip()]
    if blank_pages:
        raise GateError(f"PDF contains blank pages: {blank_pages}")
    sbom_pages = [
        index
        for index, page in enumerate(pages)
        if "붙임1" in page and "SBOM(소프트웨어 자재명세서)" in page
    ]
    if len(sbom_pages) != 1:
        raise GateError(f"expected one Attachment 1 start page, found {sbom_pages}")
    body_pages = sbom_pages[0]
    if not 1 <= body_pages <= 5:
        raise GateError(f"result-report body has {body_pages} pages; official maximum is 5")
    attachment_1_pages = len(pages) - body_pages
    if attachment_1_pages < 1:
        raise GateError("Attachment 1 must contain at least one trailing page")

    def is_a4(width: float, height: float, *, landscape: bool) -> bool:
        expected = (
            (A4_LONG_EDGE_POINTS, A4_SHORT_EDGE_POINTS)
            if landscape
            else (A4_SHORT_EDGE_POINTS, A4_LONG_EDGE_POINTS)
        )
        return all(
            abs(actual - target) <= PAGE_SIZE_TOLERANCE_POINTS
            for actual, target in zip((width, height), expected)
        )

    for index, (width, height) in enumerate(page_sizes):
        if width <= 0 or height <= 0:
            raise GateError(f"PDF page {index + 1} has an invalid physical size")
        if index < body_pages and not is_a4(width, height, landscape=False):
            raise GateError(f"result-report body page {index + 1} must be A4 portrait")
        if index >= body_pages and not is_a4(width, height, landscape=True):
            raise GateError(f"Attachment 1 page {index + 1} must be A4 landscape")

    if not sbom_rows:
        raise GateError("Attachment 1 has no declared SBOM rows")
    for index in range(body_pages, len(pages)):
        if not any(page_contains_sbom_row(pages[index], row) for row in sbom_rows):
            raise GateError(
                f"Attachment 1 page {index + 1} has no declared SBOM row anchor"
            )
    last_row = sbom_rows[-1]
    if not page_contains_sbom_row(pages[-1], last_row):
        raise GateError(
            f"the last declared SBOM row is missing from final page: {last_row['name']}"
        )
    return {
        "body_pages": body_pages,
        "attachment_1_pages": attachment_1_pages,
        "total_pages": len(pages),
    }


def validate_report_release_identity(docx_text: str, manifest: dict[str, Any]) -> None:
    """Bind reader-visible release identity to the strict package manifest."""
    normalized_docx = normalize_visible_text(docx_text)
    version = manifest["project"]["tag"][1:]
    coordinate = (
        f"io.github.{manifest['github_owner'].casefold()}.routecontract:"
        f"routecontract-shardingsphere-5.5:{version}"
    )
    required = {
        "final Maven install coordinate": coordinate,
        "final commit SHA": manifest["project"]["commit"],
    }
    for label, value in required.items():
        if normalize_visible_text(value) not in normalized_docx:
            raise GateError(f"{label} is missing from canonical DOCX")


def validate_report(
    docx_path: Path,
    pdf_path: Path,
    content: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    if object_or_empty(content.get("external_evidence")).get("branch") not in {
        "rc_only",
        "zero",
    }:
        raise GateError(
            "report validation supports only rc_only or zero until a distinct "
            "reviewed stable form and protocol exist"
        )
    validate_submission_identity_matches_content(content, manifest)
    validate_video_external_evidence_branch_matches_content(content, manifest)
    docx_hash = sha256(docx_path)
    pdf_hash = sha256(pdf_path)
    if docx_hash != manifest["report"]["docx_sha256"]:
        raise GateError(
            f"strict DOCX checksum mismatch: expected {manifest['report']['docx_sha256']}, "
            f"got {docx_hash}"
        )
    if pdf_hash != manifest["report"]["pdf_sha256"]:
        raise GateError(
            f"PDF checksum mismatch: expected {manifest['report']['pdf_sha256']}, got {pdf_hash}"
        )
    docx_text = extract_docx_text(docx_path)
    validate_docx_privacy(docx_path)
    validate_docx_hyperlinks(docx_path, content, manifest)
    validate_pdf_privacy(pdf_path)
    validate_pdf_raster_matches_docx(docx_path, pdf_path)
    pages, page_sizes = extract_pdf_pages(pdf_path)
    validate_pdf_hyperlinks(pdf_path, content, manifest, len(pages))
    pdf_text = "\n".join(pages)
    validate_report_text_contract(docx_text, pdf_text)

    validate_report_visible_content(docx_text, pdf_text, content)
    normalized_docx = normalize_visible_text(docx_text)

    metadata = content["metadata"]
    if metadata["repository_url"] != manifest["project"]["repository_url"]:
        raise GateError("report repository URL and package manifest do not match")
    if metadata["video_url"] != manifest["video"]["youtube_url"]:
        raise GateError("report YouTube URL and package manifest do not match")
    for index, url in enumerate((
        manifest["project"]["repository_url"],
        manifest["project"]["ci_run_url"],
        manifest["project"]["release_url"],
        manifest["video"]["youtube_url"],
    )):
        normalized = normalize_visible_text(url)
        if normalized not in normalized_docx:
            raise GateError(
                "public evidence URL is missing from canonical DOCX "
                f"(index={index})"
            )
    validate_report_release_identity(docx_text, manifest)

    page_metadata = report_page_contract(pages, page_sizes, content["sbom"])
    return {
        "docx_sha256": docx_hash,
        "pdf_sha256": pdf_hash,
        **page_metadata,
        "attachment_2": "absent_not_applicable",
    }


def zip_regular_file(archive: ZipFile, source: Path, arcname: str) -> None:
    info = ZipInfo(arcname, ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    archive.writestr(info, source.read_bytes())


def build_upload_zip(upload_dir: Path, output_zip: Path, expected_names: list[str]) -> None:
    if any(name in LEGACY_SUBMISSION_FILENAMES for name in expected_names):
        raise GateError("legacy RouteContract submission filenames are forbidden")
    for name in expected_names:
        if PurePosixPath(name).name != name or "\\" in name:
            raise GateError(f"upload ZIP entry must be a safe basename: {name}")
    with ZipFile(output_zip, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name in expected_names:
            zip_regular_file(archive, upload_dir / name, name)
    with ZipFile(output_zip) as archive:
        actual_names = archive.namelist()
        if actual_names != expected_names:
            raise GateError(f"upload ZIP allowlist mismatch: {actual_names}")
        for name in expected_names:
            if archive.read(name) != (upload_dir / name).read_bytes():
                raise GateError(f"upload ZIP byte verification failed: {name}")


def validate_upload_directory(upload_dir: Path, expected_names: list[str]) -> None:
    actual_names = sorted(path.name for path in upload_dir.iterdir())
    legacy_names = sorted(set(actual_names).intersection(LEGACY_SUBMISSION_FILENAMES))
    if legacy_names:
        raise GateError(
            f"legacy RouteContract submission filenames are forbidden: {legacy_names}"
        )
    if actual_names != sorted(expected_names):
        raise GateError(f"official upload directory allowlist mismatch: {actual_names}")


def validate_duplicate_confirmation(
    path: Path | None, manifest: dict[str, Any]
) -> tuple[Path | None, str | None]:
    duplicate = manifest["duplicate_benefit_confirmation"]
    if duplicate["status"] == "not_applicable":
        if path is not None:
            raise GateError(
                "duplicate-benefit file was supplied while the manifest says not_applicable"
            )
        return None, None
    raise GateError(
        "duplicate-benefit status=required is disabled until the organizer's exact "
        "source form and identity/title contract are locally validated"
    )


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    repository_root = require_directory(args.repository_root, "repository root")
    manifest_path = require_file(args.manifest, "private package manifest")
    template = require_file(args.template, "official report template")
    content_path = require_file(args.content, "private final report content")
    report_pdf = require_file(args.report_pdf, "final report PDF")
    video_file = require_file(args.video_file, "final demonstration video")
    evidence_dir = require_directory(args.release_evidence_dir, "release evidence directory")
    evidence_artifact = require_file(
        args.release_evidence_artifact, "downloaded release evidence artifact ZIP"
    )
    builder_python = require_python_interpreter(
        args.builder_python, "report builder Python"
    )
    output = reject_symlink_components(
        args.output, "proposed package output", allow_missing_tail=True
    )
    if output.exists():
        raise GateError(f"output already exists; refusing to overwrite it: {output}")
    assert_ignored_if_inside_repository(output, repository_root, "proposed package output")

    validation_utc = datetime.now(timezone.utc)
    manifest = validate_manifest(load_json(manifest_path, "package manifest"))
    validate_submission_deadline(validation_utc)
    raw_content = load_json(content_path, "report content")
    content = validate_and_materialize_report_content(
        raw_content,
        manifest,
        current_utc=validation_utc,
    )
    validate_submission_identity_matches_content(content, manifest)
    validate_video_external_evidence_branch_matches_content(content, manifest)
    for path, label in (
        (manifest_path, "package manifest"),
        (content_path, "report content"),
        (report_pdf, "final report PDF"),
        (video_file, "final demonstration video"),
        (evidence_dir, "release evidence directory"),
        (evidence_artifact, "downloaded release evidence artifact ZIP"),
    ):
        assert_ignored_if_inside_repository(path, repository_root, label)

    duplicate_path, duplicate_name = validate_duplicate_confirmation(
        args.duplicate_benefit_confirmation, manifest
    )
    if duplicate_path:
        assert_ignored_if_inside_repository(
            duplicate_path, repository_root, "duplicate-benefit confirmation"
        )

    validate_git_state(repository_root, manifest)
    evidence_metadata = validate_release_evidence(
        evidence_dir, evidence_artifact, manifest, repository_root
    )
    video_metadata = validate_local_video(video_file, manifest)
    public_core_snapshot = validate_public_evidence(
        manifest, video_metadata, evidence_metadata, evidence_dir, repository_root
    )
    external_snapshot = validate_public_external_evidence(
        content, manifest
    )
    public_metadata = {**public_core_snapshot, "external_evidence": external_snapshot}
    # Count and result URL in the ignored private input are assertions only. The
    # report source used by the final renderer is rebuilt from the complete
    # public Issue enumeration so a hand-selected URL cannot become visible.
    derived_content_source = deepcopy(raw_content)
    derived_external = derived_content_source["external_evidence"]
    derived_external["qualified_result_count"] = external_snapshot[
        "qualified_result_count"
    ]
    derived_external["result_issue_url"] = external_snapshot["result_issue_url"]
    content = validate_and_materialize_report_content(
        derived_content_source,
        manifest,
        current_utc=validation_utc,
    )
    validate_submission_identity_matches_content(content, manifest)
    validate_video_external_evidence_branch_matches_content(content, manifest)
    official_filenames = manifest["official_submission_filenames"]

    builder = repository_root / "submission" / "tools" / "build_official_report.py"
    assets_dir = repository_root / "submission" / "assets"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".routecontract-submission-", dir=output.parent) as temp:
        staging = Path(temp) / output.name
        upload_dir = staging / "official-upload"
        upload_dir.mkdir(parents=True)
        derived_content_path = Path(temp) / "enumeration-derived-report-content.json"
        write_json(derived_content_path, derived_content_source)
        report_docx = upload_dir / official_filenames["docx"]
        run(
            [
                str(builder_python),
                str(builder),
                "--template",
                str(template),
                "--content",
                str(derived_content_path),
                "--assets-dir",
                str(assets_dir),
                "--output",
                str(report_docx),
                "--strict-final",
            ],
            cwd=repository_root,
        )
        report_pdf_copy = upload_dir / official_filenames["pdf"]
        shutil.copy2(report_pdf, report_pdf_copy)

        expected_names = [official_filenames["docx"], official_filenames["pdf"]]
        if duplicate_path and duplicate_name:
            shutil.copy2(duplicate_path, upload_dir / duplicate_name)
            expected_names.append(duplicate_name)
        validate_upload_directory(upload_dir, expected_names)

        report_metadata = validate_report(report_docx, report_pdf_copy, content, manifest)
        final_public_core_snapshot = revalidate_public_evidence(
            public_core_snapshot,
            manifest,
            video_metadata,
            evidence_metadata,
            evidence_dir,
            repository_root,
        )
        final_external_snapshot = revalidate_public_external_evidence(
            external_snapshot, content, manifest
        )
        public_metadata = {
            **final_public_core_snapshot,
            "external_evidence": final_external_snapshot,
        }
        upload_zip = staging / official_filenames["zip"]
        build_upload_zip(upload_dir, upload_zip, expected_names)
        video_metadata["sha256"] = revalidate_local_video_hash_before_metadata(
            video_file, video_metadata["sha256"]
        )

        package_metadata = {
            "schema_version": PACKAGE_METADATA_SCHEMA_VERSION,
            "validated_at_utc": validation_utc.isoformat(),
            "official_notice_url": NOTICE_URL,
            "official_deadline": SUBMISSION_DEADLINE.isoformat(),
            "official_upload_zip": official_filenames["zip"],
            "official_upload_files": expected_names,
            "official_upload_file_count": len(expected_names),
            "source_video_sbom_are_not_separate_uploads": True,
            "project": manifest["project"],
            "report": report_metadata,
            "video": package_video_metadata(video_metadata, manifest),
            "release_evidence": evidence_metadata,
            "public_evidence": public_metadata,
            "duplicate_benefit_confirmation": manifest[
                "duplicate_benefit_confirmation"
            ]["status"],
        }
        metadata_path = staging / PACKAGE_METADATA_NAME
        write_json(metadata_path, package_metadata)

        checksum_targets = [
            *(upload_dir / name for name in expected_names),
            upload_zip,
            metadata_path,
        ]
        checksum_lines = []
        for path in sorted(checksum_targets, key=lambda item: item.relative_to(staging).as_posix()):
            relative = path.relative_to(staging).as_posix()
            checksum_lines.append(f"{sha256(path)}  {relative}")
        (staging / CHECKSUMS_NAME).write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

        with ZipFile(upload_zip) as archive:
            if archive.namelist() != expected_names:
                raise GateError("final ZIP changed after validation")
            forbidden_suffixes = (".json", ".xml", ".mp4", ".jar")
            if any(name.casefold().endswith(forbidden_suffixes) for name in archive.namelist()):
                raise GateError("source/video/SBOM/release evidence leaked into the upload ZIP")
        os.replace(staging, output)

    print(f"package={output}")
    print(f"upload_zip={output / official_filenames['zip']}")
    print(f"upload_files={len(expected_names)}")
    print(f"report_pages={report_metadata['total_pages']}")
    print(f"video_seconds={video_metadata['duration_seconds']:.3f}")
    print(f"commit={manifest['project']['commit']}")
    print(f"tag={manifest['project']['tag']}")


if __name__ == "__main__":
    try:
        main()
    except GateError as error:
        print(f"SUBMISSION_GATE_FAILED: {error}", file=sys.stderr)
        raise SystemExit(1) from error
