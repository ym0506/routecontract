#!/usr/bin/env python3
"""Fail-closed validator for an independent-RC activation record.

An RC is not activated merely because this source tree declares an RC version.
This command is intentionally useful only after the annotated tag, immutable
GitHub prerelease, release-evidence run, workflow artifact, downloaded Release
assets, and a committed activation record all exist and agree.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import importlib.util
import json
import math
from pathlib import Path
from pathlib import PurePosixPath
import re
import selectors
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile


REPOSITORY = "https://github.com/ym0506/routecontract"
REPOSITORY_SLUG = "ym0506/routecontract"
GITHUB_HOST = "github.com"
QUALIFIED_REPOSITORY = f"{GITHUB_HOST}/{REPOSITORY_SLUG}"
MAX_RECORD_BYTES = 1024 * 1024
MAX_CHECKSUM_BYTES = 1024 * 1024
MAX_JSON_NESTING_DEPTH = 64
MAX_JSON_NODE_COUNT = 100_000
MAX_JSON_INTEGER_DIGITS = 1_000
# Validation ceiling for bytes already captured from the GitHub CLI process.
MAX_GITHUB_JSON_BYTES = 8 * 1024 * 1024
VERSION_PART = r"(?:0|[1-9][0-9]{0,8})"
RC_VERSION_PATTERN = re.compile(
    rf"{VERSION_PART}\.{VERSION_PART}\.{VERSION_PART}-rc[1-9][0-9]{{0,5}}"
)
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")
ARTIFACT_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
CHECKSUM_LINE_PATTERN = re.compile(
    r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]*)"
)
EXPECTED_WORKFLOW_PATH = ".github/workflows/release-evidence.yml"
EXPECTED_WORKFLOW_NAME = "Release evidence"
EXPECTED_ARTIFACT_FILE_COUNT = 17
WORKFLOW_ONLY_FILES = (
    "environment.txt",
    "mysql-image.txt",
    "routecontract-mysql-example-cyclonedx.json",
    "routecontract-mysql-example-cyclonedx.xml",
    "standalone-consumer.txt",
)
MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024
MAX_ARTIFACT_MEMBER_BYTES = 100 * 1024 * 1024
MAX_ARTIFACT_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_ARTIFACT_COMPRESSION_RATIO = 1000
DOWNLOAD_TIMEOUT_SECONDS = 180
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


class ActivationError(RuntimeError):
    """The candidate is not safe to activate for independent recruitment."""


class _StrictJsonError(ValueError):
    """Value-free failure for malformed or over-budget JSON."""


@dataclass(frozen=True)
class ValidatedRecord:
    document: dict[str, Any]
    tag: str
    version: str
    tag_commit: str
    run_id: int
    artifact_id: int
    issue_form_filename: str
    public_assets: tuple[str, ...]
    payloads: tuple[str, ...]


@dataclass(frozen=True)
class PublicMetadata:
    artifact_size: int
    release_assets: tuple[tuple[str, int, int], ...]


def expected_public_assets(version: str) -> tuple[str, ...]:
    """Return the ordered, version-derived public Release allowlist."""
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


def expected_issue_form_filename(tag: str) -> str:
    """Derive the only accepted Issue Form filename from a strict RC tag."""
    if not isinstance(tag, str) or not tag.startswith("v"):
        raise ActivationError("tag must be a strict vMAJOR.MINOR.PATCH-rcN tag")
    version = tag[1:]
    if RC_VERSION_PATTERN.fullmatch(version) is None:
        raise ActivationError("tag must be a strict vMAJOR.MINOR.PATCH-rcN tag")
    rc_suffix = version.rsplit("-", maxsplit=1)[1]
    return f"independent-{rc_suffix}-install.yml"


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _StrictJsonError("strict JSON validation failed")
        result[key] = value
    return result


def _reject_non_finite_constant(_value: str) -> None:
    raise _StrictJsonError("strict JSON validation failed")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise _StrictJsonError("strict JSON validation failed")
    return parsed


def _parse_bounded_integer(value: str) -> int:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) > MAX_JSON_INTEGER_DIGITS:
        raise _StrictJsonError("strict JSON validation failed")
    return int(value)


def _enforce_json_tree_budget(value: Any) -> None:
    """Bound JSON iteratively: scalar root depth 0; root container depth 1.

    The node budget counts the root and every array element or object member value;
    object keys are not separate nodes.
    """
    stack: list[tuple[Any, int]] = [(value, 0)]
    node_count = 0
    while stack:
        node, parent_container_depth = stack.pop()
        node_count += 1
        if node_count > MAX_JSON_NODE_COUNT:
            raise _StrictJsonError("strict JSON validation failed")
        if isinstance(node, dict):
            container_depth = parent_container_depth + 1
            if container_depth > MAX_JSON_NESTING_DEPTH:
                raise _StrictJsonError("strict JSON validation failed")
            stack.extend(
                (child, container_depth) for child in reversed(tuple(node.values()))
            )
        elif isinstance(node, list):
            container_depth = parent_container_depth + 1
            if container_depth > MAX_JSON_NESTING_DEPTH:
                raise _StrictJsonError("strict JSON validation failed")
            stack.extend(
                (child, container_depth) for child in reversed(node)
            )


def _decode_strict_json(
    data: str | bytes, *, maximum_bytes: int | None = None
) -> Any:
    """Decode strict UTF-8 JSON with the shared value-free limits.

    ``maximum_bytes`` counts UTF-8 bytes, integer digits exclude a leading minus
    sign, and tree depth/node semantics are documented by
    :func:`_enforce_json_tree_budget`.
    """
    try:
        if (
            maximum_bytes is not None
            and (type(maximum_bytes) is not int or maximum_bytes < 0)
        ):
            raise _StrictJsonError("strict JSON validation failed")
        if isinstance(data, bytes):
            if maximum_bytes is not None and len(data) > maximum_bytes:
                raise _StrictJsonError("strict JSON validation failed")
            text = data.decode("utf-8", errors="strict")
        elif isinstance(data, str):
            text = data
            encoded = text.encode("utf-8", errors="strict")
            if maximum_bytes is not None and len(encoded) > maximum_bytes:
                raise _StrictJsonError("strict JSON validation failed")
        else:
            raise _StrictJsonError("strict JSON validation failed")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite_constant,
            parse_float=_parse_finite_float,
            parse_int=_parse_bounded_integer,
        )
        _enforce_json_tree_budget(value)
        return value
    except (UnicodeError, TypeError, ValueError, RecursionError):
        raise _StrictJsonError("strict JSON validation failed") from None


def _contains_placeholder(value: Any) -> bool:
    stack = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            if "[[" in node or "]]" in node:
                return True
        elif isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            for key, child in node.items():
                if "[[" in key or "]]" in key:
                    return True
                stack.append(child)
    return False


def load_record(path: Path) -> tuple[bytes, dict[str, Any]]:
    """Load strict UTF-8 JSON, rejecting templates and duplicate keys."""
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ActivationError(f"cannot read activation record: {error}") from None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ActivationError("activation record must be a regular file, not a symlink")
    if metadata.st_size > MAX_RECORD_BYTES:
        raise ActivationError("activation record exceeds the 1 MiB safety limit")
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_RECORD_BYTES:
            raise ActivationError("activation record exceeds the 1 MiB safety limit")
        value = _decode_strict_json(raw, maximum_bytes=MAX_RECORD_BYTES)
    except _StrictJsonError:
        raise ActivationError(
            "activation record must be valid strict UTF-8 JSON"
        ) from None
    if not isinstance(value, dict):
        raise ActivationError("activation record root must be a JSON object")
    if _contains_placeholder(value):
        raise ActivationError("activation record still contains an unresolved [[...]] placeholder")
    return raw, value


def _exact_object(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ActivationError(f"{label} must be a JSON object")
    actual = set(value)
    if actual != expected:
        missing = expected - actual
        unexpected = actual - expected
        raise ActivationError(
            f"{label} keys do not match the schema; "
            f"missing_count={len(missing)}, unexpected_count={len(unexpected)}"
        )
    return value


def _exact_bool(value: Any, expected: bool, label: str) -> None:
    if type(value) is not bool or value is not expected:
        raise ActivationError(f"{label} must be exactly {str(expected).lower()}")


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ActivationError(f"{label} must be a JSON boolean")
    return value


def _positive_integer(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0 or value > 9_223_372_036_854_775_807:
        raise ActivationError(f"{label} must be a positive 64-bit JSON integer")
    return value


def _lower_hex(value: Any, pattern: re.Pattern[str], label: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ActivationError(f"{label} has an invalid lowercase hexadecimal form")
    if set(value.removeprefix("sha256:")) == {"0"}:
        raise ActivationError(f"{label} must not be an all-zero placeholder")
    return value


def _github_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ActivationError(f"{label} is missing a GitHub UTC timestamp")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        raise ActivationError(f"{label} has an invalid GitHub UTC timestamp") from None


def validate_record_schema(document: dict[str, Any]) -> ValidatedRecord:
    """Validate the closed activation schema and all derived identities."""
    top = _exact_object(
        document,
        {
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
        },
        "activation record",
    )
    if top["schemaVersion"] != 2 or type(top["schemaVersion"]) is not int:
        raise ActivationError("schemaVersion must be the JSON integer 2")
    if top["repository"] != REPOSITORY:
        raise ActivationError(f"repository must be exactly {REPOSITORY}")

    tag = top["tag"]
    if not isinstance(tag, str) or not tag.startswith("v"):
        raise ActivationError("tag must be a strict vMAJOR.MINOR.PATCH-rcN tag")
    version = tag[1:]
    if RC_VERSION_PATTERN.fullmatch(version) is None:
        raise ActivationError("tag must be a strict vMAJOR.MINOR.PATCH-rcN tag")
    tag_commit = _lower_hex(top["tagCommit"], COMMIT_PATTERN, "tagCommit")
    issue_form_filename = expected_issue_form_filename(tag)

    canonical = {
        "releaseUrl": f"{REPOSITORY}/releases/tag/{tag}",
        "taggedProtocolUrl": (
            f"{REPOSITORY}/blob/{tag}/docs/independent-install-study.md"
        ),
        "taggedReadmeUrl": f"{REPOSITORY}/blob/{tag}/README.md",
        "issueFormFilename": issue_form_filename,
        "issueFormPermalink": (
            f"{REPOSITORY}/blob/{tag_commit}/.github/ISSUE_TEMPLATE/"
            f"{issue_form_filename}"
        ),
        "issueFormUrl": (
            f"{REPOSITORY}/issues/new?template={issue_form_filename}"
        ),
    }
    for key, expected in canonical.items():
        if top[key] != expected:
            raise ActivationError(f"{key} must be exactly {expected}")

    public_assets = top["publicAssets"]
    expected_assets = expected_public_assets(version)
    if (
        not isinstance(public_assets, list)
        or any(not isinstance(item, str) for item in public_assets)
        or tuple(public_assets) != expected_assets
    ):
        raise ActivationError(
            "publicAssets must equal the ordered version-derived 12-file allowlist"
        )

    evidence = _exact_object(
        top["releaseEvidence"],
        {"artifactDigest", "artifactFileCount", "artifactId", "headSha", "runId", "runUrl"},
        "releaseEvidence",
    )
    run_id = _positive_integer(evidence["runId"], "releaseEvidence.runId")
    artifact_id = _positive_integer(
        evidence["artifactId"], "releaseEvidence.artifactId"
    )
    if evidence["artifactFileCount"] != EXPECTED_ARTIFACT_FILE_COUNT or type(
        evidence["artifactFileCount"]
    ) is not int:
        raise ActivationError("releaseEvidence.artifactFileCount must be the JSON integer 17")
    if evidence["headSha"] != tag_commit:
        raise ActivationError("releaseEvidence.headSha must equal tagCommit")
    _lower_hex(evidence["artifactDigest"], ARTIFACT_DIGEST_PATTERN, "artifactDigest")
    expected_run_url = f"{REPOSITORY}/actions/runs/{run_id}"
    if evidence["runUrl"] != expected_run_url:
        raise ActivationError(f"releaseEvidence.runUrl must be exactly {expected_run_url}")

    state = _exact_object(
        top["releaseState"], {"draft", "immutable", "prerelease"}, "releaseState"
    )
    _exact_bool(state["draft"], False, "releaseState.draft")
    _exact_bool(state["immutable"], True, "releaseState.immutable")
    _exact_bool(state["prerelease"], True, "releaseState.prerelease")

    immutability = _exact_object(
        top["releaseImmutability"], {"enabled", "enforcedByOwner"}, "releaseImmutability"
    )
    _exact_bool(immutability["enabled"], True, "releaseImmutability.enabled")
    _boolean(immutability["enforcedByOwner"], "releaseImmutability.enforcedByOwner")
    _lower_hex(top["sha256sumsSha256"], DIGEST_PATTERN, "sha256sumsSha256")

    return ValidatedRecord(
        document=top,
        tag=tag,
        version=version,
        tag_commit=tag_commit,
        run_id=run_id,
        artifact_id=artifact_id,
        issue_form_filename=issue_form_filename,
        public_assets=expected_assets,
        payloads=expected_assets[:-1],
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_asset_directory(directory: Path, record: ValidatedRecord) -> dict[str, str]:
    """Validate the exact flat asset set and every checksum."""
    if not directory.is_absolute():
        raise ActivationError("release assets directory must be an explicit absolute path")
    try:
        metadata = directory.lstat()
    except OSError as error:
        raise ActivationError(f"cannot read release assets directory: {error}") from None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ActivationError("release assets path must be a real directory, not a symlink")
    files: dict[str, Path] = {}
    for path in directory.iterdir():
        item = path.lstat()
        if stat.S_ISLNK(item.st_mode) or not stat.S_ISREG(item.st_mode):
            raise ActivationError(
                f"release assets must be a flat set of regular files: {path.name}"
            )
        files[path.name] = path
    actual = set(files)
    expected = set(record.public_assets)
    if actual != expected:
        raise ActivationError(
            "release asset directory does not match publicAssets; "
            f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
        )

    checksum_path = files["SHA256SUMS"]
    if checksum_path.stat().st_size > MAX_CHECKSUM_BYTES:
        raise ActivationError("SHA256SUMS exceeds the 1 MiB safety limit")
    raw = checksum_path.read_bytes()
    if not raw.endswith(b"\n"):
        raise ActivationError("SHA256SUMS must end with a newline")
    try:
        lines = raw.decode("ascii", errors="strict").splitlines()
    except UnicodeError:
        raise ActivationError("SHA256SUMS must contain ASCII only") from None
    checksums: dict[str, str] = {}
    ordered_names: list[str] = []
    for number, line in enumerate(lines, start=1):
        match = CHECKSUM_LINE_PATTERN.fullmatch(line)
        if match is None:
            raise ActivationError(f"invalid SHA256SUMS line {number}: {line!r}")
        digest, name = match.groups()
        if name == "SHA256SUMS" or name in checksums:
            raise ActivationError(f"duplicate or recursive SHA256SUMS entry: {name}")
        checksums[name] = digest
        ordered_names.append(name)
    if tuple(ordered_names) != record.payloads:
        raise ActivationError(
            "SHA256SUMS must declare the ordered 11-payload allowlist exactly once"
        )
    for name in record.payloads:
        actual_digest = sha256(files[name])
        if not hmac.compare_digest(actual_digest, checksums[name]):
            raise ActivationError(f"checksum mismatch for {name}")
    checksum_digest = sha256(checksum_path)
    if not hmac.compare_digest(
        checksum_digest, record.document["sha256sumsSha256"]
    ):
        raise ActivationError("SHA256SUMS hash does not match sha256sumsSha256")
    return {name: sha256(path) for name, path in files.items()}


def validate_workflow_artifact_archive(
    archive_path: Path,
    record: ValidatedRecord,
    local_digests: dict[str, str],
) -> dict[str, str]:
    """Bind the downloaded 17-file workflow artifact to all 12 Release bytes."""
    try:
        archive_metadata = archive_path.lstat()
    except OSError as error:
        raise ActivationError(f"cannot inspect downloaded workflow artifact: {error}") from None
    if (
        stat.S_ISLNK(archive_metadata.st_mode)
        or not stat.S_ISREG(archive_metadata.st_mode)
        or archive_metadata.st_size <= 0
        or archive_metadata.st_size > MAX_DOWNLOAD_BYTES
    ):
        raise ActivationError("downloaded workflow artifact must be one bounded regular ZIP file")
    evidence = record.document["releaseEvidence"]
    expected_archive_digest = evidence["artifactDigest"].removeprefix("sha256:")
    before_digest = sha256(archive_path)
    if not hmac.compare_digest(before_digest, expected_archive_digest):
        raise ActivationError("downloaded workflow artifact digest does not match artifactDigest")

    expected_names = set(record.public_assets) | set(WORKFLOW_ONLY_FILES)
    members: dict[str, str] = {}
    total_uncompressed = 0
    try:
        with ZipFile(archive_path) as archive:
            for info in archive.infolist():
                original_name = getattr(info, "orig_filename", info.filename)
                pure = PurePosixPath(info.filename)
                unix_mode = info.external_attr >> 16
                file_type = stat.S_IFMT(unix_mode)
                if (
                    original_name != info.filename
                    or "\x00" in original_name
                    or info.is_dir()
                    or pure.is_absolute()
                    or len(pure.parts) != 1
                    or pure.parts in ((), (".",), ("..",))
                    or "\\" in info.filename
                    or info.filename not in expected_names
                    or file_type not in (0, stat.S_IFREG)
                    or info.external_attr & 0x10
                    or info.flag_bits & 0x1
                    or info.compress_type not in (ZIP_STORED, ZIP_DEFLATED)
                ):
                    raise ActivationError(
                        "workflow artifact must contain only the exact 17 flat regular files: "
                        + info.filename
                    )
                if info.filename in members:
                    raise ActivationError(
                        f"workflow artifact contains duplicate member: {info.filename}"
                    )
                if (
                    info.file_size <= 0
                    or info.file_size > MAX_ARTIFACT_MEMBER_BYTES
                    or info.compress_size <= 0
                    or info.compress_size > MAX_ARTIFACT_MEMBER_BYTES
                    or info.file_size
                    > info.compress_size * MAX_ARTIFACT_COMPRESSION_RATIO
                ):
                    raise ActivationError(
                        f"workflow artifact member has an unsafe size: {info.filename}"
                    )
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_ARTIFACT_UNCOMPRESSED_BYTES:
                    raise ActivationError(
                        "workflow artifact exceeds the 250 MiB uncompressed safety limit"
                    )
                digest = hashlib.sha256()
                observed_size = 0
                with archive.open(info) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        observed_size += len(chunk)
                        if observed_size > info.file_size:
                            raise ActivationError(
                                f"workflow artifact member exceeds its declared size: {info.filename}"
                            )
                        digest.update(chunk)
                if observed_size != info.file_size:
                    raise ActivationError(
                        f"workflow artifact member size changed while reading: {info.filename}"
                    )
                members[info.filename] = digest.hexdigest()
    except (BadZipFile, OSError, RuntimeError, ValueError) as error:
        if isinstance(error, ActivationError):
            raise
        raise ActivationError(f"workflow artifact is not a safe ZIP archive: {error}") from None

    if set(members) != expected_names or len(members) != EXPECTED_ARTIFACT_FILE_COUNT:
        raise ActivationError(
            "workflow artifact does not match the exact 17-file allowlist; "
            f"missing={sorted(expected_names - set(members))}, "
            f"unexpected={sorted(set(members) - expected_names)}"
        )
    for name in record.public_assets:
        if not hmac.compare_digest(members[name], local_digests[name]):
            raise ActivationError(
                f"workflow artifact and downloaded Release asset differ: {name}"
            )
    if not hmac.compare_digest(sha256(archive_path), before_digest):
        raise ActivationError("workflow artifact changed during validation")
    return members


def _gh_download_command(gh: str, endpoint: str, accept: str) -> list[str]:
    if accept not in ("application/vnd.github+json", "application/octet-stream"):
        raise ActivationError("GitHub download requested an unsupported Accept header")
    return [
        gh,
        "api",
        "--hostname",
        GITHUB_HOST,
        "--method",
        "GET",
        "-H",
        f"Accept: {accept}",
        "-H",
        "X-GitHub-Api-Version: 2022-11-28",
        endpoint,
    ]


def _download_gh_file(
    gh: str,
    repository_root: Path,
    endpoint: str,
    destination: Path,
    expected_size: int,
    *,
    accept: str,
) -> None:
    """Stream one canonical GitHub API download into a bounded new file."""
    if (
        type(expected_size) is not int
        or expected_size <= 0
        or expected_size > MAX_DOWNLOAD_BYTES
    ):
        raise ActivationError("GitHub download size is outside the 250 MiB safety limit")
    command = _gh_download_command(gh, endpoint, accept)
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    complete = False
    try:
        with destination.open("xb") as output:
            process = subprocess.Popen(
                command,
                cwd=repository_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            if process.stdout is None:  # pragma: no cover - subprocess invariant
                raise ActivationError("GitHub download did not expose a byte stream")
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            deadline = time.monotonic() + DOWNLOAD_TIMEOUT_SECONDS
            observed_size = 0
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ActivationError("GitHub download timed out")
                events = selector.select(timeout=min(remaining, 1.0))
                if not events:
                    if process.poll() is not None:
                        chunk = process.stdout.read()
                        if chunk:
                            observed_size += len(chunk)
                            if observed_size > expected_size:
                                raise ActivationError("GitHub download exceeds its declared size")
                            output.write(chunk)
                        selector.unregister(process.stdout)
                    continue
                chunk = process.stdout.read1(1024 * 1024)
                if not chunk:
                    selector.unregister(process.stdout)
                    continue
                observed_size += len(chunk)
                if observed_size > expected_size:
                    raise ActivationError("GitHub download exceeds its declared size")
                output.write(chunk)
            return_code = process.wait(timeout=max(1.0, deadline - time.monotonic()))
            if return_code != 0:
                raise ActivationError("GitHub API byte download failed")
            output.flush()
            if observed_size != expected_size:
                raise ActivationError(
                    "GitHub download size does not match public API metadata"
                )
            complete = True
    except (OSError, subprocess.SubprocessError) as error:
        raise ActivationError(f"could not complete bounded GitHub download: {error}") from None
    finally:
        if selector is not None:
            selector.close()
        if process is not None and process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.SubprocessError:
                pass
        if not complete:
            try:
                destination.unlink()
            except FileNotFoundError:
                pass


def download_and_validate_public_bytes(
    gh: str,
    repository_root: Path,
    assets_dir: Path,
    metadata: PublicMetadata,
    record: ValidatedRecord,
    local_digests: dict[str, str],
) -> None:
    """Download the workflow artifact and Release assets from canonical API endpoints."""
    with tempfile.TemporaryDirectory(prefix="routecontract-rc-public-bytes-") as temporary:
        root = Path(temporary)
        artifact_zip = root / "workflow-artifact.zip"
        _download_gh_file(
            gh,
            repository_root,
            f"repos/{REPOSITORY_SLUG}/actions/artifacts/{record.artifact_id}/zip",
            artifact_zip,
            metadata.artifact_size,
            accept="application/vnd.github+json",
        )
        validate_workflow_artifact_archive(artifact_zip, record, local_digests)

        release_root = root / "release-assets"
        release_root.mkdir()
        for name, asset_id, expected_size in metadata.release_assets:
            downloaded = release_root / name
            _download_gh_file(
                gh,
                repository_root,
                f"repos/{REPOSITORY_SLUG}/releases/assets/{asset_id}",
                downloaded,
                expected_size,
                accept="application/octet-stream",
            )
            downloaded_digest = sha256(downloaded)
            if not hmac.compare_digest(downloaded_digest, local_digests[name]):
                raise ActivationError(
                    f"GitHub API Release download differs from the supplied asset: {name}"
                )
            if not hmac.compare_digest(downloaded_digest, sha256(assets_dir / name)):
                raise ActivationError(
                    f"supplied Release asset changed during public-byte validation: {name}"
                )


def _run(
    command: list[str], *, cwd: Path, timeout: int = 60, binary: bool = False
) -> subprocess.CompletedProcess[Any]:
    try:
        text_options: dict[str, Any] = (
            {"text": False}
            if binary
            else {"text": True, "encoding": "utf-8", "errors": "strict"}
        )
        return subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
            **text_options,
        )
    except subprocess.TimeoutExpired:
        raise ActivationError(f"could not run {command[0]}: timeout") from None
    except (OSError, UnicodeError):
        raise ActivationError(f"could not run {command[0]}") from None


def _git(repository_root: Path, arguments: list[str], *, binary: bool = False) -> Any:
    result = _run(["git", *arguments], cwd=repository_root, binary=binary)
    if result.returncode != 0:
        detail = result.stderr if isinstance(result.stderr, str) else b""
        rendered = detail.strip() if isinstance(detail, str) else ""
        raise ActivationError(
            f"git {' '.join(arguments)} failed"
            + (f": {rendered}" if rendered else "")
        )
    return result.stdout


def validate_local_repository(
    repository_root: Path, record_path: Path, raw_record: bytes, record: ValidatedRecord
) -> str:
    """Bind the record to committed bytes and a local/remote annotated tag."""
    root = repository_root.resolve(strict=True)
    if not (root / ".git").exists():
        raise ActivationError("repository root must be a Git checkout")
    try:
        relative = record_path.resolve(strict=True).relative_to(root).as_posix()
    except ValueError:
        raise ActivationError("activation record must be inside the repository root") from None
    expected_path = f"docs/evidence/independent-rc-activation-{record.tag}.json"
    if relative != expected_path:
        raise ActivationError(f"activation record path must be exactly {expected_path}")
    if _git(root, ["status", "--porcelain", "--untracked-files=all"]).strip():
        raise ActivationError("repository must be clean before activation validation")

    expected_validator = root / "scripts/validate-rc-activation-record.py"
    if Path(__file__).resolve() != expected_validator.resolve(strict=True):
        raise ActivationError("validator must be executed from the repository being validated")

    record_commit = _git(
        root, ["log", "-1", "--format=%H", "--", relative]
    ).strip()
    if COMMIT_PATTERN.fullmatch(record_commit) is None:
        raise ActivationError("activation record must be committed")
    committed = _git(root, ["show", f"{record_commit}:{relative}"], binary=True)
    if committed != raw_record:
        raise ActivationError("working activation record differs from its committed bytes")
    if _git(root, ["rev-parse", "HEAD"]).strip() != record_commit:
        raise ActivationError("clean checkout HEAD must equal the activation-record commit")

    parents = _git(root, ["rev-list", "--parents", "-n", "1", record_commit]).split()
    if parents != [record_commit, record.tag_commit]:
        raise ActivationError(
            "activation record must be the direct one-parent child of tagCommit"
        )
    changed = _git(
        root,
        [
            "diff-tree",
            "--no-commit-id",
            "--name-status",
            "-r",
            "--no-renames",
            record.tag_commit,
            record_commit,
        ],
    ).splitlines()
    if changed != [f"A\t{relative}"]:
        raise ActivationError(
            "activation-record commit must add only its exact versioned JSON file"
        )
    record_entry = _git(root, ["ls-tree", record_commit, "--", relative]).strip()
    if re.fullmatch(rf"100644 blob [0-9a-f]{{40}}\t{re.escape(relative)}", record_entry) is None:
        raise ActivationError("activation record must be one ordinary non-executable Git blob")

    tag_ref = f"refs/tags/{record.tag}"
    if _git(root, ["cat-file", "-t", tag_ref]).strip() != "tag":
        raise ActivationError("local RC tag must be an annotated tag object")
    peeled = _git(root, ["rev-parse", f"{tag_ref}^{{commit}}"]).strip()
    if peeled != record.tag_commit:
        raise ActivationError("local annotated tag does not peel to tagCommit")

    tagged_tree = _git(root, ["ls-tree", "-r", record.tag_commit]).splitlines()
    if any(line.startswith("120000 ") for line in tagged_tree):
        raise ActivationError("tagged release tree must not contain symbolic links")
    tagged_names = _git(root, ["ls-tree", "-r", "--name-only", record.tag_commit]).splitlines()
    if ".gitmodules" in tagged_names:
        raise ActivationError("tagged release tree must not contain .gitmodules")
    issue_form_path = f".github/ISSUE_TEMPLATE/{record.issue_form_filename}"
    issue_form_entry = _git(
        root, ["ls-tree", record.tag_commit, "--", issue_form_path]
    ).strip()
    if re.fullmatch(
        rf"100644 blob [0-9a-f]{{40}}\t{re.escape(issue_form_path)}",
        issue_form_entry,
    ) is None:
        raise ActivationError(
            "version-derived tagged Issue Form must be one ordinary non-executable Git blob"
        )
    required_tagged_paths = (
        ".github/workflows/release-evidence.yml",
        "README.md",
        "NOTICE",
        "build.gradle",
        "docs/independent-install-study.md",
        "docs/evidence/independent-rc-activation.example.json",
        "scripts/gh_cli_release_safety.py",
        "scripts/validate-rc-activation-record.py",
        "scripts/install-release-assets.py",
    )
    for path in required_tagged_paths:
        _git(root, ["cat-file", "-e", f"{record.tag_commit}:{path}"])
    return record_commit


def _load_safe_github_cli(repository_root: Path) -> str:
    module_path = repository_root / "scripts/gh_cli_release_safety.py"
    spec = importlib.util.spec_from_file_location("routecontract_gh_safety", module_path)
    if spec is None or spec.loader is None:
        raise ActivationError("cannot load GitHub CLI safety preflight")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        executable, _ = module.require_safe_github_cli()
    except (AttributeError, RuntimeError) as error:
        raise ActivationError(f"GitHub CLI safety preflight failed: {error}") from None
    return executable


def _gh_json(gh: str, repository_root: Path, endpoint: str) -> dict[str, Any]:
    result = _run(
        [
            gh,
            "api",
            "--hostname",
            GITHUB_HOST,
            "--method",
            "GET",
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            "X-GitHub-Api-Version: 2022-11-28",
            endpoint,
        ],
        cwd=repository_root,
    )
    if result.returncode != 0:
        raise ActivationError(f"GitHub API verification failed for {endpoint}")
    try:
        value = _decode_strict_json(
            result.stdout, maximum_bytes=MAX_GITHUB_JSON_BYTES
        )
    except _StrictJsonError:
        raise ActivationError(f"GitHub API returned invalid JSON for {endpoint}") from None
    if not isinstance(value, dict):
        raise ActivationError(f"GitHub API returned a non-object for {endpoint}")
    return value


def _gh_json_list(
    gh: str, repository_root: Path, endpoint: str
) -> list[dict[str, Any]]:
    """Read one bounded GitHub JSON array without accepting partial object shapes."""
    result = _run(
        [
            gh,
            "api",
            "--hostname",
            GITHUB_HOST,
            "--method",
            "GET",
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            "X-GitHub-Api-Version: 2022-11-28",
            endpoint,
        ],
        cwd=repository_root,
    )
    if result.returncode != 0:
        raise ActivationError(f"GitHub API verification failed for {endpoint}")
    try:
        value = _decode_strict_json(
            result.stdout, maximum_bytes=MAX_GITHUB_JSON_BYTES
        )
    except _StrictJsonError:
        raise ActivationError(f"GitHub API returned invalid JSON for {endpoint}") from None
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ActivationError(f"GitHub API returned a non-object array for {endpoint}")
    return value


def _gh_graphql_activation_pull(
    gh: str, repository_root: Path, pull_number: int
) -> dict[str, Any]:
    result = _run(
        [
            gh,
            "api",
            "graphql",
            "--hostname",
            GITHUB_HOST,
            "--method",
            "POST",
            "-f",
            f"query={ACTIVATION_PULL_QUERY}",
            "-F",
            f"owner={REPOSITORY_SLUG.split('/', 1)[0]}",
            "-F",
            f"repo={REPOSITORY_SLUG.split('/', 1)[1]}",
            "-F",
            f"number={pull_number}",
        ],
        cwd=repository_root,
    )
    if result.returncode != 0:
        raise ActivationError("authenticated GitHub GraphQL Pull Request query failed")
    try:
        payload = _decode_strict_json(
            result.stdout, maximum_bytes=MAX_GITHUB_JSON_BYTES
        )
    except _StrictJsonError:
        raise ActivationError(
            "authenticated GitHub GraphQL Pull Request query returned invalid JSON"
        ) from None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"data"}
        or not isinstance(payload["data"], dict)
    ):
        raise ActivationError(
            "authenticated GitHub GraphQL Pull Request query returned errors, "
            "extensions, or a partial envelope"
        )
    return payload


def _validate_graphql_activation_pull(
    payload: dict[str, Any],
    repository_node_id: str,
    rest_pull: dict[str, Any],
    record_commit: str,
) -> None:
    data = payload.get("data")
    repository = data.get("repository") if isinstance(data, dict) else None
    pull = repository.get("pullRequest") if isinstance(repository, dict) else None
    base_repository = pull.get("baseRepository") if isinstance(pull, dict) else None
    merge_commit = pull.get("mergeCommit") if isinstance(pull, dict) else None
    if (
        not isinstance(data, dict)
        or set(data) != {"repository"}
        or not isinstance(repository, dict)
        or set(repository) != {"id", "nameWithOwner", "pullRequest"}
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
        or not isinstance(repository.get("id"), str)
        or not repository["id"]
        or repository["id"] != repository_node_id
        or not isinstance(repository.get("nameWithOwner"), str)
        or repository.get("nameWithOwner") != REPOSITORY_SLUG
        or not isinstance(base_repository.get("id"), str)
        or not base_repository["id"]
        or base_repository["id"] != repository_node_id
        or not isinstance(base_repository.get("nameWithOwner"), str)
        or base_repository.get("nameWithOwner") != REPOSITORY_SLUG
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
        raise ActivationError(
            "authenticated GitHub GraphQL Pull Request does not bind the exact "
            "public main merge"
        )


def validate_public_metadata(
    gh: str,
    repository_root: Path,
    record_path: Path,
    raw_record: bytes,
    record_commit: str,
    record: ValidatedRecord,
    local_digests: dict[str, str],
) -> PublicMetadata:
    """Verify public repository, record, run, artifact, and immutable Release."""
    repo = _gh_json(gh, repository_root, f"repos/{REPOSITORY_SLUG}")
    repository_id = repo.get("id")
    repository_node_id = repo.get("node_id")
    if (
        type(repository_id) is not int
        or repository_id <= 0
        or repo.get("full_name") != REPOSITORY_SLUG
        or repo.get("html_url") != REPOSITORY
        or repo.get("default_branch") != "main"
        or repo.get("private") is not False
        or repo.get("archived") is not False
        or repo.get("disabled") is not False
        or not isinstance(repository_node_id, str)
        or not repository_node_id
    ):
        raise ActivationError("GitHub repository metadata is not the expected public repository")

    commit_metadata: dict[str, dict[str, Any]] = {}
    for commit in (record.tag_commit, record_commit):
        metadata = _gh_json(gh, repository_root, f"repos/{REPOSITORY_SLUG}/commits/{commit}")
        if metadata.get("sha") != commit:
            raise ActivationError(f"GitHub commit API did not return exact commit {commit}")
        commit_metadata[commit] = metadata
    record_commit_payload = commit_metadata[record_commit].get("commit")
    if not isinstance(record_commit_payload, dict):
        raise ActivationError("activation-record commit metadata is missing")
    record_author = record_commit_payload.get("author")
    record_committer = record_commit_payload.get("committer")
    if not isinstance(record_author, dict) or not isinstance(record_committer, dict):
        raise ActivationError("activation-record commit timestamps are missing")
    record_author_at = _github_utc(
        record_author.get("date"), "activation-record commit author date"
    )
    record_committer_at = _github_utc(
        record_committer.get("date"), "activation-record commit committer date"
    )

    local_tag_object = _git(
        repository_root, ["rev-parse", f"refs/tags/{record.tag}"]
    ).strip()
    tag_ref = _gh_json(
        gh, repository_root, f"repos/{REPOSITORY_SLUG}/git/ref/tags/{record.tag}"
    )
    tag_ref_object = tag_ref.get("object")
    if (
        tag_ref.get("ref") != f"refs/tags/{record.tag}"
        or not isinstance(tag_ref_object, dict)
        or tag_ref_object.get("type") != "tag"
        or tag_ref_object.get("sha") != local_tag_object
    ):
        raise ActivationError("public RC ref is not the exact local annotated tag object")
    tag_object = _gh_json(
        gh, repository_root, f"repos/{REPOSITORY_SLUG}/git/tags/{local_tag_object}"
    )
    tagged_object = tag_object.get("object")
    if (
        tag_object.get("sha") != local_tag_object
        or tag_object.get("tag") != record.tag
        or not isinstance(tagged_object, dict)
        or tagged_object.get("type") != "commit"
        or tagged_object.get("sha") != record.tag_commit
    ):
        raise ActivationError("public annotated tag object does not peel to tagCommit")
    main = _gh_json(gh, repository_root, f"repos/{REPOSITORY_SLUG}/branches/main")
    main_commit = main.get("commit")
    if (
        main.get("name") != "main"
        or not isinstance(main_commit, dict)
        or main_commit.get("sha") != record_commit
    ):
        raise ActivationError("public main must equal the activation-record commit")

    associated_endpoint = (
        f"repos/{REPOSITORY_SLUG}/commits/{record_commit}/pulls?per_page=100"
    )
    associated_pulls = _gh_json_list(
        gh, repository_root, associated_endpoint
    )
    if len(associated_pulls) >= 100:
        raise ActivationError("activation-record pull-request association is unbounded")
    validated_pulls: list[tuple[dict[str, Any], dict[str, Any], datetime]] = []
    observed_pull_numbers: set[int] = set()
    for associated_pull in associated_pulls:
        pull_number = associated_pull.get("number")
        pull_id = associated_pull.get("id")
        pull_node_id = associated_pull.get("node_id")
        expected_pull_url = f"{REPOSITORY}/pull/{pull_number}"
        listed_merge_commit = associated_pull.get("merge_commit_sha")
        associated_base = associated_pull.get("base")
        associated_base_repository = (
            associated_base.get("repo") if isinstance(associated_base, dict) else None
        )
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
            or not isinstance(associated_base, dict)
            or associated_base.get("ref") != "main"
            or not isinstance(associated_base_repository, dict)
            or associated_base_repository.get("full_name") != REPOSITORY_SLUG
            or (
                listed_merge_commit is not None
                and listed_merge_commit != record_commit
            )
        ):
            raise ActivationError("activation-record pull-request association is malformed")
        observed_pull_numbers.add(pull_number)

        direct_pull = _gh_json(
            gh, repository_root, f"repos/{REPOSITORY_SLUG}/pulls/{pull_number}"
        )
        direct_base = direct_pull.get("base")
        direct_base_repository = (
            direct_base.get("repo") if isinstance(direct_base, dict) else None
        )
        direct_merge_commit = direct_pull.get("merge_commit_sha")
        activation_merged_at = _github_utc(
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
            or (direct_merge_commit is not None and direct_merge_commit != record_commit)
            or not isinstance(direct_base, dict)
            or direct_base.get("ref") != "main"
            or not isinstance(direct_base_repository, dict)
            or direct_base_repository.get("full_name") != REPOSITORY_SLUG
            or associated_pull.get("state") != direct_pull.get("state")
            or associated_pull.get("merged_at") != direct_pull.get("merged_at")
            or associated_base.get("ref") != direct_base.get("ref")
            or associated_base_repository.get("full_name")
            != direct_base_repository.get("full_name")
        ):
            raise ActivationError(
                "activation-record pull request does not bind the public main squash merge"
            )
        _validate_graphql_activation_pull(
            _gh_graphql_activation_pull(gh, repository_root, pull_number),
            repository_node_id,
            direct_pull,
            record_commit,
        )
        validated_pulls.append((associated_pull, direct_pull, activation_merged_at))

    if len(validated_pulls) != 1:
        raise ActivationError(
            "activation-record commit must be the unique squash result of a main pull request"
        )
    associated_pull, direct_pull, activation_merged_at = validated_pulls[0]
    if not record_author_at <= record_committer_at <= activation_merged_at:
        raise ActivationError(
            "activation-record commit timestamps are later than the public main merge"
        )

    relative = record_path.resolve(strict=True).relative_to(repository_root.resolve()).as_posix()
    contents = _gh_json(
        gh,
        repository_root,
        f"repos/{REPOSITORY_SLUG}/contents/{relative}?ref={record_commit}",
    )
    if contents.get("type") != "file" or contents.get("encoding") != "base64":
        raise ActivationError("public activation record is not a base64-encoded file")
    encoded_content = contents.get("content")
    if (
        not isinstance(encoded_content, str)
        or re.fullmatch(r"[A-Za-z0-9+/=\r\n]+", encoded_content) is None
    ):
        raise ActivationError("public activation record content is malformed")
    try:
        public_record = base64.b64decode(
            encoded_content.replace("\r", "").replace("\n", ""), validate=True
        )
    except (TypeError, ValueError):
        raise ActivationError("public activation record content is malformed") from None
    if public_record != raw_record:
        raise ActivationError("public activation record bytes differ from the committed local file")

    evidence = record.document["releaseEvidence"]
    run = _gh_json(
        gh, repository_root, f"repos/{REPOSITORY_SLUG}/actions/runs/{record.run_id}"
    )
    if (
        run.get("id") != record.run_id
        or run.get("html_url") != evidence["runUrl"]
        or run.get("head_sha") != record.tag_commit
        or run.get("head_branch") != record.tag
        or run.get("event") != "push"
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("name") != EXPECTED_WORKFLOW_NAME
        or run.get("path") != EXPECTED_WORKFLOW_PATH
        or not isinstance(run.get("repository"), dict)
        or run["repository"].get("full_name") != REPOSITORY_SLUG
    ):
        raise ActivationError("release-evidence run metadata does not match the activation record")
    run_created_at = _github_utc(run.get("created_at"), "release-evidence run created_at")
    run_updated_at = _github_utc(run.get("updated_at"), "release-evidence run updated_at")
    if run_created_at > run_updated_at:
        raise ActivationError("release-evidence run timestamps are reversed")

    artifact = _gh_json(
        gh,
        repository_root,
        f"repos/{REPOSITORY_SLUG}/actions/artifacts/{record.artifact_id}",
    )
    workflow_run = artifact.get("workflow_run")
    artifact_size = artifact.get("size_in_bytes")
    if (
        artifact.get("id") != record.artifact_id
        or artifact.get("name") != f"routecontract-release-evidence-{record.tag_commit}"
        or artifact.get("digest") != evidence["artifactDigest"]
        or artifact.get("expired") is not False
        or type(artifact_size) is not int
        or artifact_size <= 0
        or artifact_size > MAX_DOWNLOAD_BYTES
        or not isinstance(workflow_run, dict)
        or workflow_run.get("id") != record.run_id
        or workflow_run.get("head_sha") != record.tag_commit
        or workflow_run.get("head_branch") != record.tag
    ):
        raise ActivationError("workflow artifact metadata does not match the activation record")
    artifact_created_at = _github_utc(
        artifact.get("created_at"), "workflow artifact created_at"
    )
    artifact_updated_at = _github_utc(
        artifact.get("updated_at"), "workflow artifact updated_at"
    )
    if artifact_created_at > artifact_updated_at:
        raise ActivationError("workflow artifact timestamps are reversed")

    release = _gh_json(
        gh, repository_root, f"repos/{REPOSITORY_SLUG}/releases/tags/{record.tag}"
    )
    assets = release.get("assets")
    if (
        release.get("tag_name") != record.tag
        or release.get("html_url") != record.document["releaseUrl"]
        or release.get("draft") is not False
        or release.get("prerelease") is not True
        or release.get("immutable") is not True
        or not isinstance(assets, list)
    ):
        raise ActivationError("GitHub Release is not the exact immutable public prerelease")
    release_created_at = _github_utc(release.get("created_at"), "RC Release created_at")
    release_published_at = _github_utc(
        release.get("published_at"), "RC Release published_at"
    )
    release_updated_at = _github_utc(release.get("updated_at"), "RC Release updated_at")
    if not release_created_at <= release_published_at <= release_updated_at:
        raise ActivationError("RC Release timestamps are reversed")
    by_name: dict[str, dict[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
            raise ActivationError("GitHub Release contains malformed asset metadata")
        if asset["name"] in by_name:
            raise ActivationError("GitHub Release contains duplicate asset names")
        by_name[asset["name"]] = asset
    if set(by_name) != set(record.public_assets):
        raise ActivationError("GitHub Release assets do not match the exact public allowlist")
    release_assets: list[tuple[str, int, int]] = []
    asset_updated_times: list[datetime] = []
    for name in record.public_assets:
        asset = by_name[name]
        asset_id = asset.get("id")
        asset_size = asset.get("size")
        asset_created_at = _github_utc(
            asset.get("created_at"), f"GitHub Release asset {name} created_at"
        )
        asset_updated_at = _github_utc(
            asset.get("updated_at"), f"GitHub Release asset {name} updated_at"
        )
        if type(asset_id) is not int or asset_id <= 0:
            raise ActivationError(f"GitHub Release asset has an invalid ID: {name}")
        expected_api_url = (
            f"https://api.github.com/repos/{REPOSITORY_SLUG}/releases/assets/{asset_id}"
        )
        expected_download_url = (
            f"{REPOSITORY}/releases/download/{record.tag}/{name}"
        )
        if (
            asset.get("state") != "uploaded"
            or type(asset_size) is not int
            or asset_size <= 0
            or asset_size > MAX_DOWNLOAD_BYTES
            or asset.get("digest") != f"sha256:{local_digests[name]}"
            or asset.get("url") != expected_api_url
            or asset.get("browser_download_url") != expected_download_url
            or asset_created_at > asset_updated_at
        ):
            raise ActivationError(f"GitHub Release asset metadata does not match {name}")
        release_assets.append((name, asset_id, asset_size))
        asset_updated_times.append(asset_updated_at)

    if max(run_updated_at, artifact_updated_at) > release_published_at:
        raise ActivationError("release-evidence run or artifact is later than RC publication")
    public_prerequisites_latest = max(
        run_updated_at,
        artifact_updated_at,
        release_updated_at,
        *asset_updated_times,
    )
    if not public_prerequisites_latest < activation_merged_at:
        raise ActivationError(
            "public RC prerequisites must precede the activation-record main merge"
        )

    immutability = _gh_json(
        gh, repository_root, f"repos/{REPOSITORY_SLUG}/immutable-releases"
    )
    recorded = record.document["releaseImmutability"]
    if (
        immutability.get("enabled") is not True
        or immutability.get("enforced_by_owner") is not recorded["enforcedByOwner"]
    ):
        raise ActivationError("repository immutable-release settings do not match the record")
    return PublicMetadata(
        artifact_size=artifact_size,
        release_assets=tuple(release_assets),
    )


def validate_release_attestations(
    gh: str, repository_root: Path, assets_dir: Path, record: ValidatedRecord
) -> None:
    commands = [
        [gh, "release", "verify", record.tag, "--repo", QUALIFIED_REPOSITORY]
    ]
    commands.extend(
        [
            gh,
            "release",
            "verify-asset",
            record.tag,
            str(assets_dir / name),
            "--repo",
            QUALIFIED_REPOSITORY,
        ]
        for name in record.public_assets
    )
    for command in commands:
        result = _run(command, cwd=repository_root, timeout=120)
        if result.returncode != 0:
            raise ActivationError(f"GitHub Release attestation failed: {' '.join(command[1:3])}")
        # The stable GitHub CLI's documented success exit status is the
        # verification signal. Its human/JSON presentation is not an API and
        # is deliberately neither parsed nor treated as a second trust source.


def validate_installer(repository_root: Path, assets_dir: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="routecontract-rc-activation-maven-") as temporary:
        repository = Path(temporary) / "repository"
        result = _run(
            [
                sys.executable,
                str(repository_root / "scripts/install-release-assets.py"),
                "--release-assets-dir",
                str(assets_dir),
                "--repository",
                str(repository),
            ],
            cwd=repository_root,
            timeout=180,
        )
        if result.returncode != 0:
            raise ActivationError("release assets failed the structural installer gate")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fail closed unless one committed RC activation record, public immutable "
            "prerelease, release evidence, exact downloaded assets, and attestations agree."
        )
    )
    parser.add_argument("--record", required=True, help="versioned committed activation-record JSON")
    parser.add_argument(
        "--release-assets-dir",
        required=True,
        help="absolute directory containing the 12 downloaded public Release assets",
    )
    parser.add_argument(
        "--repository-root",
        help="repository checkout root (defaults to the parent of this script directory)",
    )
    return parser.parse_args(argv)


def run(argv: list[str]) -> int:
    args = parse_args(argv)
    default_root = Path(__file__).resolve().parent.parent
    repository_root = Path(args.repository_root).expanduser() if args.repository_root else default_root
    repository_root = repository_root.resolve(strict=True)
    record_path = Path(args.record).expanduser()
    if not record_path.is_absolute():
        record_path = repository_root / record_path
    assets_dir = Path(args.release_assets_dir).expanduser()

    raw_record, document = load_record(record_path)
    record = validate_record_schema(document)
    local_digests = validate_asset_directory(assets_dir, record)
    record_commit = validate_local_repository(
        repository_root, record_path, raw_record, record
    )
    gh = _load_safe_github_cli(repository_root)
    metadata = validate_public_metadata(
        gh,
        repository_root,
        record_path,
        raw_record,
        record_commit,
        record,
        local_digests,
    )
    download_and_validate_public_bytes(
        gh,
        repository_root,
        assets_dir,
        metadata,
        record,
        local_digests,
    )
    validate_installer(repository_root, assets_dir)
    validate_release_attestations(gh, repository_root, assets_dir, record)

    permalink = f"{REPOSITORY}/blob/{record_commit}/{record_path.resolve().relative_to(repository_root).as_posix()}"
    print(
        "ROUTECONTRACT_RC_ACTIVATION_VERIFIED "
        f"tag={record.tag} commit={record.tag_commit} run={record.run_id} "
        f"artifact={record.artifact_id} assets={len(record.public_assets)}"
    )
    print(f"ACTIVATION_RECORD_PERMALINK {permalink}")
    return 0


def main() -> int:
    try:
        return run(sys.argv[1:])
    except (ActivationError, OSError) as error:
        print(f"RC_ACTIVATION_NO_GO: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
