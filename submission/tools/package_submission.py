#!/usr/bin/env python3
"""Build and verify the exact 2026 OSS contest upload package.

The organizer upload ZIP is deliberately smaller than the verification set:
it contains only the report original and PDF, plus the duplicate-benefit form
when applicable. Repository, release, SBOM and video artifacts are verified as
external evidence and are never copied into the organizer ZIP.
"""

from __future__ import annotations

import argparse
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
CHECKSUMS_NAME = "SHA256SUMS"
MAX_VIDEO_SECONDS = 180.0
MIN_VIDEO_WIDTH = 1920
MIN_VIDEO_HEIGHT = 1080
MIN_PUBLIC_VIDEO_HEIGHT = 1080
MAX_PORTABLE_FILENAME_BYTES = 255
A4_SHORT_EDGE_POINTS = 595.3
A4_LONG_EDGE_POINTS = 841.9
PAGE_SIZE_TOLERANCE_POINTS = 1.0
KST = timezone(timedelta(hours=9))
SUBMISSION_DEADLINE = datetime(2026, 8, 27, 18, 0, 0, tzinfo=KST)
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
TEST_SUMMARY_FORMAT = "routecontract-test-summary-v1"

EXPECTED_RELEASE_TEST_SUITES = {
    "io.github.ym0506.routecontract.RouteContractTest": 18,
    "io.github.ym0506.routecontract.example.DataSourceProxyComparisonMySqlTest": 1,
    "io.github.ym0506.routecontract.example.FailureBoundaryMySqlTest": 1,
    "io.github.ym0506.routecontract.example.ObservedExecutionRegressionCorpusMySqlTest": 7,
    "io.github.ym0506.routecontract.example.OperationCorrelationMySqlTest": 5,
    "io.github.ym0506.routecontract.internal.ShardingSphere553PreflightTest": 3,
    "io.github.ym0506.routecontract.manifest.ObservedExecutionManifestTest": 15,
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
        "location",
        "location-eng",
        "make",
        "model",
        "com.apple.quicktime.artist",
        "com.apple.quicktime.author",
        "com.apple.quicktime.comment",
        "com.apple.quicktime.description",
        "com.apple.quicktime.location.iso6709",
        "com.apple.quicktime.make",
        "com.apple.quicktime.model",
    }
)


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
) -> str:
    process = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        rendered = " ".join(command)
        detail = (process.stderr or process.stdout).strip()
        raise GateError(f"command failed ({process.returncode}): {rendered}\n{detail}")
    return process.stdout


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise GateError(f"invalid {label}: {error}") from error
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
    found = sorted(
        {
            match.group(0)
            for text in iter_strings(value)
            for match in PLACEHOLDER_RE.finditer(text)
        }
    )
    if found:
        raise GateError(f"{label} has unresolved [[...]] gates: {', '.join(found)}")


def require_exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise GateError(
            f"{label} keys do not match schema; missing={missing}, unexpected={unexpected}"
        )
    return value


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
    if data["schema_version"] != 1:
        raise GateError("manifest.schema_version must be 1")
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
        {"youtube_url", "title", "duration_seconds", "local_file_sha256"},
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
        raise GateError("video.duration_seconds must be a number from ffprobe/mdls")
    duration = float(video["duration_seconds"])
    if not 0 < duration <= MAX_VIDEO_SECONDS:
        raise GateError("video.duration_seconds must be greater than 0 and at most 180")
    require_digest(video["local_file_sha256"], "video.local_file_sha256")

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
            "all_submitted_code_reviewed_and_explainable",
            "source_and_dependency_licenses_reviewed",
            "final_pdf_visual_qa_completed",
            "final_video_watchthrough_completed",
            "public_repository_maintenance_obligation_accepted",
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
) -> dict[str, Any]:
    expected_digest = manifest["release_evidence"]["workflow_artifact_sha256"]
    actual_digest = sha256(artifact_zip)
    if actual_digest != expected_digest:
        raise GateError(
            f"workflow artifact ZIP checksum mismatch: expected {expected_digest}, got {actual_digest}"
        )
    members = zip_flat_file_metadata(artifact_zip, "workflow artifact ZIP")
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
    return {
        "workflow_artifact_id": manifest["release_evidence"]["workflow_artifact_id"],
        "workflow_artifact_sha256": actual_digest,
        "workflow_artifact_file_count": len(members),
    }


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
            "expected 7-suite/50-test all-passing, non-skipped result"
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
    artifact_metadata = validate_workflow_artifact_archive(
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
        "standalone-consumer.txt",
    }
    public_unsigned_names = {
        "test-summary.txt",
        "routecontract-shardingsphere-5.5.pom",
        "routecontract-shardingsphere-5.5-cyclonedx.json",
        "routecontract-shardingsphere-5.5-cyclonedx.xml",
        "routecontract-aggregate-cyclonedx.json",
        "routecontract-aggregate-cyclonedx.xml",
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
        ],
        cwd=repository_root,
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
        "release_evidence_file_count": len(actual_files),
        "public_release_assets": public_release_assets,
    }


def validate_video_metadata_tags(value: Any, label: str) -> int:
    if value is None:
        return 0
    if not isinstance(value, dict):
        raise GateError(f"ffprobe {label} metadata tags must be an object")
    normalized: dict[str, str] = {}
    for key, tag_value in value.items():
        if not isinstance(key, str) or not isinstance(tag_value, str):
            raise GateError(f"ffprobe {label} metadata tags must contain only strings")
        normalized_key = key.strip().casefold()
        if normalized_key in SENSITIVE_VIDEO_METADATA_TAGS:
            raise GateError(
                f"local demonstration file contains sensitive metadata tag: {key}"
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
            "ffprobe is required to verify duration, 1080p dimensions, audio, "
            "and privacy-safe video metadata"
        )
    output = run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:format_tags:stream=index,codec_type,width,height:stream_tags:stream_disposition=default,attached_pic,still_image:chapter=id:chapter_tags:program=id:program_tags",
            "-of",
            "json",
            str(path),
        ]
    )
    try:
        data = json.loads(output)
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
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise GateError(f"ffprobe returned incomplete video metadata: {error}") from error

    metadata_tag_count = validate_video_metadata_tags(
        format_metadata.get("tags"), "format"
    )
    for stream in streams:
        metadata_tag_count += validate_video_metadata_tags(
            stream.get("tags"), f"stream {stream.get('index', '?')}"
        )
    for scope, entries in (("chapter", chapters), ("program", programs)):
        for entry in entries:
            metadata_tag_count += validate_video_metadata_tags(
                entry.get("tags"), f"{scope} {entry.get('id', '?')}"
            )

    video_streams = [
        stream for stream in streams if stream.get("codec_type") == "video"
    ]
    audio_streams = [
        stream for stream in streams if stream.get("codec_type") == "audio"
    ]
    if not video_streams:
        raise GateError("local demonstration file has no video stream")
    if not audio_streams:
        raise GateError("local demonstration file must contain at least one audio stream")

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
            f"{MIN_VIDEO_WIDTH}x{MIN_VIDEO_HEIGHT}; got {width}x{height}"
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


def validate_local_video(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    expected_hash = manifest["video"]["local_file_sha256"]
    actual_hash = sha256(path)
    if actual_hash != expected_hash:
        raise GateError(f"video SHA-256 mismatch: expected {expected_hash}, got {actual_hash}")
    metadata = local_video_metadata(path)
    duration = float(metadata["duration_seconds"])
    if not 0 < duration <= MAX_VIDEO_SECONDS:
        raise GateError(f"local video is {duration:.3f}s; official maximum is 180.000s")
    declared = float(manifest["video"]["duration_seconds"])
    if abs(duration - declared) > 0.1:
        raise GateError(
            f"video duration differs from manifest: declared={declared:.3f}, actual={duration:.3f}"
        )
    metadata["sha256"] = actual_hash
    return metadata


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
    headers = {"User-Agent": "RouteContract-contest-submission-verifier/1"}
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
    except (urllib.error.URLError, TimeoutError) as error:
        raise GateError(f"public URL is unavailable: {url}: {error}") from error
    if limit is not None and len(data) > limit:
        raise GateError(f"public response exceeded the verification limit: {url}")
    return data


def request_json(url: str) -> dict[str, Any]:
    try:
        value = json.loads(request_bytes(url, accept="application/vnd.github+json", limit=8_000_000))
    except json.JSONDecodeError as error:
        raise GateError(f"public endpoint did not return JSON: {url}: {error}") from error
    if not isinstance(value, dict):
        raise GateError(f"public endpoint returned a non-object: {url}")
    return value


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
        ]
    )
    try:
        metadata = json.loads(output)
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
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise GateError(
            f"yt-dlp returned incomplete public video duration metadata: {error}"
        ) from error

    availability = metadata.get("availability")
    if availability != "public":
        raise GateError(
            "YouTube availability must be public; "
            f"yt-dlp reported {availability!r}"
        )
    live_status = metadata.get("live_status")
    if live_status != "not_live":
        raise GateError(
            "YouTube demonstration must be a non-live upload; "
            f"yt-dlp reported live_status={live_status!r}"
        )
    if "age_limit" not in metadata:
        raise GateError("YouTube age_limit must be 0 or null; yt-dlp omitted it")
    age_limit = metadata["age_limit"]
    if age_limit is not None and (
        isinstance(age_limit, bool)
        or not isinstance(age_limit, (int, float))
        or not math.isfinite(float(age_limit))
        or float(age_limit) != 0.0
    ):
        raise GateError(
            "YouTube age_limit must be 0 or null for logged-out playback; "
            f"yt-dlp reported {age_limit!r}"
        )

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
        if height is not None and (
            isinstance(height, bool)
            or not isinstance(height, (int, float))
            or not math.isfinite(float(height))
            or float(height) <= 0
        ):
            raise GateError("yt-dlp format metadata contains an invalid height")
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
            height is not None
            and float(height) >= MIN_PUBLIC_VIDEO_HEIGHT
            and isinstance(vcodec, str)
            and bool(vcodec.strip())
            and vcodec.strip().casefold() != "none"
            and parsed_url is not None
            and parsed_url.scheme in {"http", "https"}
            and bool(parsed_url.netloc)
            and has_drm is False
        ):
            downloadable_video_heights.append(int(height))
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
        raise GateError(
            f"public YouTube title mismatch: expected {manifest['video']['title']!r}, "
            f"got {youtube['title']!r}"
        )
    if youtube["duration_seconds"] > MAX_VIDEO_SECONDS:
        raise GateError("public YouTube video exceeds the official 180-second maximum")
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
    if repository_data.get("private") is not False or repository_data.get("archived") is True:
        raise GateError("representative GitHub repository is private or archived")
    if str(repository_data.get("full_name", "")).casefold() != f"{owner}/{repository}".casefold():
        raise GateError("GitHub repository identity does not match the manifest")

    commit_data = request_json(f"{api_base}/commits/{project['commit']}")
    if commit_data.get("sha") != project["commit"]:
        raise GateError("manifest commit is not publicly readable")

    run_id = project["ci_run_url"].rsplit("/", 1)[1]
    run_data = request_json(f"{api_base}/actions/runs/{run_id}")
    if (
        run_data.get("status") != "completed"
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
    run_repo = (run_data.get("repository") or {}).get("full_name", "")
    if str(run_repo).casefold() != f"{owner}/{repository}".casefold():
        raise GateError("Actions run belongs to a different repository")

    artifact_id = manifest["release_evidence"]["workflow_artifact_id"]
    artifact_data = request_json(f"{api_base}/actions/artifacts/{artifact_id}")
    expected_artifact_name = f"routecontract-release-evidence-{project['commit']}"
    artifact_run = artifact_data.get("workflow_run") or {}
    if (
        artifact_data.get("id") != artifact_id
        or artifact_data.get("name") != expected_artifact_name
        or artifact_data.get("expired") is not False
        or artifact_data.get("digest")
        != f"sha256:{manifest['release_evidence']['workflow_artifact_sha256']}"
        or artifact_run.get("id") != int(run_id)
        or artifact_run.get("head_sha") != project["commit"]
        or artifact_run.get("head_branch") != project["tag"]
    ):
        raise GateError(
            "public workflow artifact ID/digest/run/revision does not match local release evidence"
        )

    release_data = request_json(
        f"{api_base}/releases/tags/{urllib.parse.quote(project['tag'], safe='')}"
    )
    if (
        release_data.get("draft") is not False
        or release_data.get("prerelease") is not False
        or release_data.get("tag_name") != project["tag"]
    ):
        raise GateError("final GitHub Release is draft/prerelease or has the wrong tag")
    if release_data.get("immutable") is not True:
        raise GateError("final GitHub Release is not immutable")
    if release_data.get("html_url") != project["release_url"]:
        raise GateError("public GitHub Release URL does not match the manifest")
    release_assets_by_name: dict[str, list[dict[str, Any]]] = {}
    for asset in release_data.get("assets", []):
        release_assets_by_name.setdefault(str(asset.get("name")), []).append(asset)
    expected_release_names = set(evidence["public_release_assets"])
    if set(release_assets_by_name) != expected_release_names:
        raise GateError(
            "GitHub Release assets violate the exact allowlist; "
            f"missing={sorted(expected_release_names - set(release_assets_by_name))}, "
            f"unexpected={sorted(set(release_assets_by_name) - expected_release_names)}"
        )
    for asset_name, expected in evidence["public_release_assets"].items():
        matching_assets = release_assets_by_name.get(asset_name, [])
        if len(matching_assets) != 1:
            raise GateError(f"GitHub Release must contain exactly one {asset_name} asset")
        asset = matching_assets[0]
        if asset.get("state") != "uploaded":
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

    verify_release_attestations(manifest, evidence, evidence_dir)
    # The immutable Release now prevents a later tag rewrite. Recheck origin
    # after that public/attestation gate to close the earlier network TOCTOU.
    validate_remote_tag_identity(repository_root, manifest)

    youtube = public_youtube_metadata(manifest["video"]["youtube_url"])
    validate_public_youtube_contract(manifest, local_video, youtube)

    return {
        "repository_full_name": repository_data["full_name"],
        "commit": commit_data["sha"],
        "ci_run_id": int(run_id),
        "ci_conclusion": run_data["conclusion"],
        "workflow_artifact_id": artifact_data["id"],
        "workflow_artifact_sha256": manifest["release_evidence"][
            "workflow_artifact_sha256"
        ],
        "release_id": release_data.get("id"),
        "release_tag": release_data["tag_name"],
        "release_immutable": release_data["immutable"],
        "youtube_video_id": youtube["id"],
        "youtube_title": youtube["title"],
        "youtube_duration_seconds": youtube["duration_seconds"],
        "youtube_availability": youtube["availability"],
        "youtube_live_status": youtube["live_status"],
        "youtube_age_limit": youtube["age_limit"],
        "youtube_max_video_height": youtube["max_video_height"],
    }


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
        raise GateError(f"could not inspect generated DOCX: {error}") from error
    chunks: list[str] = []
    for element in root.iter():
        local = element.tag.rsplit("}", 1)[-1]
        if local == "t" and element.text:
            chunks.append(element.text)
        elif local in {"tab", "br", "cr", "p"}:
            chunks.append("\n")
    return " ".join(chunks)


def validate_docx_privacy(path: Path) -> None:
    try:
        with ZipFile(path) as package:
            names = set(package.namelist())
            if "docProps/custom.xml" in names:
                raise GateError("generated DOCX unexpectedly contains custom properties")
            core = ET.fromstring(package.read("docProps/core.xml"))
    except (BadZipFile, OSError, KeyError, ET.ParseError) as error:
        if isinstance(error, GateError):
            raise
        raise GateError(f"could not inspect DOCX privacy metadata: {error}") from error
    values = {
        element.tag.rsplit("}", 1)[-1]: (element.text or "").strip()
        for element in core
    }
    if values.get("creator") != "RouteContract project" or values.get(
        "lastModifiedBy"
    ) != "RouteContract project":
        raise GateError("DOCX author metadata is not privacy-sanitized")
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
        raise GateError(
            f"{label} contains private path/identity metadata: "
            f"literals={leaked}, email={email_match.group(0) if email_match else None}"
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
        key: {"expected": value, "actual": fields.get(key)}
        for key, value in expected.items()
        if fields.get(key) != value
    }
    if mismatched:
        raise GateError(f"PDF privacy/safety properties mismatch: {mismatched}")
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
            raise GateError(f"PDF XMP metadata is malformed: {error}") from error
        creator_values = [
            (element.text or "").strip()
            for creator in xmp.iter()
            if creator.tag.rsplit("}", 1)[-1] == "creator"
            for element in creator.iter()
            if element.tag.rsplit("}", 1)[-1] == "li"
        ]
        if creator_values != ["RouteContract project"]:
            raise GateError(f"PDF XMP creator is not sanitized: {creator_values}")

    attachments = run([pdfdetach, "-list", str(path)]).strip()
    if attachments != "0 embedded files":
        raise GateError(f"PDF must not contain embedded files: {attachments}")
    javascript = run([pdfinfo, "-js", str(path)]).strip()
    if javascript:
        raise GateError("PDF contains document-level JavaScript")


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


def validate_report_text_contract(docx_text: str, pdf_text: str) -> None:
    for label, text in (("DOCX", docx_text), ("PDF", pdf_text)):
        placeholders = sorted(set(PLACEHOLDER_RE.findall(text)))
        if placeholders:
            raise GateError(f"{label} contains unresolved gates: {placeholders}")
        if "결과보고서 작성 안내" in text:
            raise GateError(f"{label} still contains the organizer writing-guide page")
        if "AI 모델 활용 및 라이선스 기술 명세서" in text:
            raise GateError(f"{label} incorrectly contains inapplicable Attachment 2")
        if "SBOM(소프트웨어 자재명세서)" not in text:
            raise GateError(f"{label} is missing mandatory Attachment 1 SBOM")
        if (
            "개발 보조 AI" not in text
            or "제품에는 AI 모델" not in text
            or "외부 AI API 호출이 없다" not in text
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


def validate_report(
    docx_path: Path,
    pdf_path: Path,
    content: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    validate_submission_identity_matches_content(content, manifest)
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
    validate_pdf_privacy(pdf_path)
    pages, page_sizes = extract_pdf_pages(pdf_path)
    pdf_text = "\n".join(pages)
    validate_report_text_contract(docx_text, pdf_text)

    normalized_docx = normalize_visible_text(docx_text)
    normalized_pdf = normalize_visible_text(pdf_text)
    missing_docx: list[str] = []
    missing_pdf: list[str] = []
    for value in visible_report_values(content):
        normalized = normalize_visible_text(value)
        if normalized not in normalized_docx:
            missing_docx.append(value)
        if normalized not in normalized_pdf:
            missing_pdf.append(value)
    if missing_docx:
        raise GateError(f"generated DOCX is missing content values: {missing_docx[:3]}")
    if missing_pdf:
        raise GateError(f"PDF is stale or missing content values: {missing_pdf[:3]}")

    metadata = content["metadata"]
    if metadata["repository_url"] != manifest["project"]["repository_url"]:
        raise GateError("report repository URL and package manifest do not match")
    if metadata["video_url"] != manifest["video"]["youtube_url"]:
        raise GateError("report YouTube URL and package manifest do not match")
    for url in (
        manifest["project"]["repository_url"],
        manifest["project"]["ci_run_url"],
        manifest["project"]["release_url"],
        manifest["video"]["youtube_url"],
    ):
        normalized = normalize_visible_text(url)
        if normalized not in normalized_docx or normalized not in normalized_pdf:
            raise GateError(f"public evidence URL is missing from DOCX/PDF: {url}")
    expected_group = f"io.github.{manifest['github_owner'].casefold()}.routecontract"
    normalized_group = normalize_visible_text(expected_group)
    if normalized_group not in normalized_docx or normalized_group not in normalized_pdf:
        raise GateError(
            f"final Maven install coordinate group is missing from DOCX/PDF: {expected_group}"
        )

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

    manifest = validate_manifest(load_json(manifest_path, "package manifest"))
    validate_submission_deadline()
    content = load_json(content_path, "report content")
    reject_placeholders(content, "report content")
    validate_submission_identity_matches_content(content, manifest)
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
    public_metadata = validate_public_evidence(
        manifest, video_metadata, evidence_metadata, evidence_dir, repository_root
    )
    official_filenames = manifest["official_submission_filenames"]

    builder = repository_root / "submission" / "tools" / "build_official_report.py"
    assets_dir = repository_root / "submission" / "assets"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".routecontract-submission-", dir=output.parent) as temp:
        staging = Path(temp) / output.name
        upload_dir = staging / "official-upload"
        upload_dir.mkdir(parents=True)
        report_docx = upload_dir / official_filenames["docx"]
        run(
            [
                str(builder_python),
                str(builder),
                "--template",
                str(template),
                "--content",
                str(content_path),
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
        upload_zip = staging / official_filenames["zip"]
        build_upload_zip(upload_dir, upload_zip, expected_names)

        package_metadata = {
            "schema_version": 1,
            "validated_at_utc": datetime.now(timezone.utc).isoformat(),
            "official_notice_url": NOTICE_URL,
            "official_deadline": SUBMISSION_DEADLINE.isoformat(),
            "official_upload_zip": official_filenames["zip"],
            "official_upload_files": expected_names,
            "official_upload_file_count": len(expected_names),
            "source_video_sbom_are_not_separate_uploads": True,
            "project": manifest["project"],
            "report": report_metadata,
            "video": {
                **video_metadata,
                "youtube_url": manifest["video"]["youtube_url"],
            },
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
