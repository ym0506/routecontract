#!/usr/bin/env python3
"""Render a review-only Maven RouteContract starter without touching the target.

The output is a deterministic review bundle.  It contains a two-path patch, a
six-field configuration for ``run-assisted-maven-pilot.py``, the normalized
review inputs, and next steps.  It never applies the patch and never creates,
copies, replaces, or approves a baseline.
"""

from __future__ import annotations

import argparse
import ctypes
import difflib
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Mapping, NamedTuple, Sequence


SCHEMA_VERSION = 1
MAX_CONFIG_BYTES = 64 * 1024
MAX_POM_BYTES = 2 * 1024 * 1024
MAX_PARENT_CHAIN_BYTES = 8 * 1024 * 1024
MAX_TEMPLATE_BYTES = 64 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_GIT_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_BUDGET = 10_000
MAVEN_NAMESPACE = "http://maven.apache.org/POM/4.0.0"
EXPECTED_BOUNDARY = {
    "javaVersion": "17",
    "mavenVersion": "3.9.14",
    "routeContractVersion": "0.1.2",
    "shardingSphereVersion": "5.5.3",
}
PROFILE_OFF_TEST_SHAPE = "single-non-parameterized"
PROFILE_TEMPLATE_SHA256 = (
    "82a6c92a17a64ca2889d597a80b97eb8ed057b4fcd5ab436733b0883967fa190"
)
JAVA_TEMPLATE_SHA256 = (
    "9ae4fbd3c3a46d0691a8919d90189887301681afafda8a56e73a7c70b4d0ac19"
)
CONFIG_KEYS = frozenset(
    {
        "schemaVersion",
        "projectRoot",
        "expectedTargetCommit",
        "expectedPomSha256",
        "owningModule",
        "reactorSelector",
        "profileOffTest",
        "profileOffTestShape",
        "pilotPackage",
        "pilotClass",
        "pilotMethod",
        "operationId",
        "reviewedMaxAttempts",
        "reviewedMaxDataSources",
        "dataSourceAliases",
        "shardingSphereScope",
        "javaVersion",
        "mavenVersion",
        "shardingSphereVersion",
        "routeContractVersion",
    }
)
ALIAS_KEYS = frozenset({"observedName", "alias"})
ASSISTED_CONFIG_KEYS = (
    "projectRoot",
    "owningModule",
    "reactorSelector",
    "profileOffTest",
    "pilotTest",
    "operationId",
)
OUTPUT_FILES = (
    "NEXT-STEPS.md",
    "assisted-pilot.json",
    "bundle-manifest.json",
    "pilot-spec.json",
    "routecontract-pilot.patch",
)
OUTPUT_WRITE_ORDER = (
    "NEXT-STEPS.md",
    "assisted-pilot.json",
    "pilot-spec.json",
    "routecontract-pilot.patch",
    "bundle-manifest.json",
)
_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_JAVA_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_JAVA_TEST_SELECTOR = re.compile(
    r"(?P<class>[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*)"
    r"#(?P<method>[A-Za-z_$][A-Za-z0-9_$]*)\Z"
)
_OPERATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_ALIAS_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_LOWER_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
_LOWER_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_MAVEN_COORDINATE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*\Z")
_PLACEHOLDER = re.compile(r"@@[A-Z0-9_]+@@")
_JAVA_KEYWORDS = frozenset(
    {
        "abstract", "assert", "boolean", "break", "byte", "case", "catch",
        "char", "class", "const", "continue", "default", "do", "double",
        "else", "enum", "extends", "final", "finally", "float", "for",
        "goto", "if", "implements", "import", "instanceof", "int",
        "interface", "long", "native", "new", "package", "private",
        "protected", "public", "return", "short", "static", "strictfp",
        "super", "switch", "synchronized", "this", "throw", "throws",
        "transient", "try", "void", "volatile", "while", "true", "false",
        "null", "record", "sealed", "permits", "non-sealed", "var", "yield",
        "_",
    }
)


class StarterError(RuntimeError):
    """Fail-closed input, target, template, or output violation."""


class GitSnapshot(NamedTuple):
    head: str
    status: bytes
    index: bytes
    absolute_git_dir: bytes
    common_git_dir: bytes
    worktrees: bytes


class PreparedStarter(NamedTuple):
    config: dict[str, object]
    project_root: Path
    owning_root: Path
    owning_pom: Path
    owning_pom_relative: str
    pilot_source_relative: str
    approved_relative: str
    candidate_relative: str
    target_snapshot: GitSnapshot
    target_pom_sha256: str
    inherited_pom_sha256: tuple[tuple[str, str], ...]
    reactor_parent_unverified: bool
    files_without_manifest: dict[str, bytes]


class _SingleValue(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"{option_string} may be supplied only once")
        setattr(namespace, self.dest, values)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _metadata(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_stable_regular(path: Path, label: str, maximum: int) -> bytes:
    if not path.is_absolute() or path != Path(os.path.normpath(os.fspath(path))):
        raise StarterError(f"{label} must be an absolute normalized path")
    try:
        if path.resolve(strict=True) != path:
            raise StarterError(f"{label} must use its canonical non-symlink path")
    except OSError as error:
        raise StarterError(f"{label} is unavailable") from error

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise StarterError(f"{label} must be a regular non-symlink file") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise StarterError(f"{label} must be a regular non-symlink file")
        if before.st_size > maximum:
            raise StarterError(f"{label} exceeds its size limit")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if len(payload) > maximum:
            raise StarterError(f"{label} exceeds its size limit")
        if _metadata(before) != _metadata(after):
            raise StarterError(f"{label} changed while it was read")
    finally:
        os.close(descriptor)
    try:
        named = os.lstat(path)
        resolved_after = path.resolve(strict=True)
    except OSError as error:
        raise StarterError(f"{label} disappeared while it was read") from error
    if (
        resolved_after != path
        or not stat.S_ISREG(named.st_mode)
        or _metadata(named) != _metadata(after)
    ):
        raise StarterError(f"{label} identity changed while it was read")
    return payload


def _duplicate_safe_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        _validate_text(key, "JSON key")
        if key in result:
            raise StarterError("JSON contains a duplicate key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise StarterError(f"config contains a non-JSON numeric constant: {value}")


def _validate_text(value: str, label: str) -> None:
    if unicodedata.normalize("NFC", value) != value:
        raise StarterError(f"{label} must use NFC text")
    if any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        for character in value
    ):
        raise StarterError(f"{label} contains an unsafe Unicode character")


def _reject_extended_acl(descriptor: int, label: str) -> None:
    """Reject macOS extended ACLs that chmod(2) does not necessarily remove."""
    if sys.platform != "darwin":
        return
    try:
        library = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        get_acl = library.acl_get_fd_np
        free_acl = library.acl_free
    except (OSError, AttributeError) as error:
        raise StarterError(f"{label} extended ACL state is unavailable") from error
    get_acl.argtypes = [ctypes.c_int, ctypes.c_int]
    get_acl.restype = ctypes.c_void_p
    free_acl.argtypes = [ctypes.c_void_p]
    free_acl.restype = ctypes.c_int
    ctypes.set_errno(0)
    acl = get_acl(descriptor, 0x00000100)
    if acl:
        free_result = free_acl(acl)
        if free_result != 0:
            raise StarterError(f"{label} extended ACL state could not be released")
        raise StarterError(f"{label} must not carry an extended ACL")
    if ctypes.get_errno() != errno.ENOENT:
        raise StarterError(f"{label} extended ACL state is unavailable")


def _validate_all_text(value: object, label: str = "config") -> None:
    if isinstance(value, str):
        _validate_text(value, label)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_all_text(item, f"{label}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_text(key, f"{label} key")
            _validate_all_text(item, f"{label}.{key}")


def _load_config(path: Path) -> dict[str, object]:
    payload = _read_stable_regular(path, "config", MAX_CONFIG_BYTES)
    if payload.startswith(b"\xef\xbb\xbf"):
        raise StarterError("config must not contain a UTF-8 BOM")
    try:
        parsed = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_duplicate_safe_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StarterError("config must be strict UTF-8 JSON") from error
    if not isinstance(parsed, dict):
        raise StarterError("config must be one JSON object")
    _validate_all_text(parsed)
    if frozenset(parsed) != CONFIG_KEYS:
        missing = sorted(CONFIG_KEYS - frozenset(parsed))
        unknown = sorted(frozenset(parsed) - CONFIG_KEYS)
        raise StarterError(
            f"config keys must match the schema exactly; missing={missing}, unknown={unknown}"
        )
    return parsed


def _require_string(config: Mapping[str, object], key: str) -> str:
    value = config[key]
    if not isinstance(value, str) or not value:
        raise StarterError(f"config field {key} must be a non-empty string")
    return value


def _require_exact_boundary(config: Mapping[str, object]) -> None:
    if type(config["schemaVersion"]) is not int or config["schemaVersion"] != SCHEMA_VERSION:
        raise StarterError(f"schemaVersion must be exactly {SCHEMA_VERSION}")
    for key, expected in EXPECTED_BOUNDARY.items():
        actual = _require_string(config, key)
        if actual != expected:
            raise StarterError(f"{key} must be exactly {expected}")


def _require_canonical_directory(value: str, label: str) -> Path:
    if len(value) > 4096:
        raise StarterError(f"{label} is too long")
    path = Path(value)
    if not path.is_absolute() or path != Path(os.path.normpath(value)):
        raise StarterError(f"{label} must be an absolute normalized path")
    try:
        metadata = os.lstat(path)
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise StarterError(f"{label} is unavailable") from error
    if not stat.S_ISDIR(metadata.st_mode) or resolved != path:
        raise StarterError(f"{label} must be a canonical non-symlink directory")
    return path


def _require_safe_relative_directory(root: Path, value: str) -> Path:
    if value == ".":
        return root
    if not value or len(value) > 512 or "\\" in value:
        raise StarterError("owningModule must be a safe relative POSIX path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or os.fspath(pure) != value:
        raise StarterError("owningModule must be a normalized relative POSIX path")
    if any(
        part in {"", ".", ".."} or _SAFE_SEGMENT.fullmatch(part) is None
        for part in pure.parts
    ):
        raise StarterError("owningModule contains an unsafe path segment")
    current = root
    for part in pure.parts:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError as error:
            raise StarterError("owningModule is unavailable") from error
        if not stat.S_ISDIR(metadata.st_mode) or current.resolve(strict=True) != current:
            raise StarterError("owningModule must not traverse a symlink")
    if not current.is_relative_to(root):
        raise StarterError("owningModule escaped projectRoot")
    return current


def _reject_maven_project_configuration(project_root: Path) -> None:
    dot_maven = project_root / ".mvn"
    try:
        metadata = os.lstat(dot_maven)
    except FileNotFoundError:
        return
    except OSError as error:
        raise StarterError("project .mvn state is unavailable") from error
    if not stat.S_ISDIR(metadata.st_mode) or dot_maven.resolve(strict=True) != dot_maven:
        raise StarterError("project .mvn must be a canonical non-symlink directory")
    for name in ("maven.config", "jvm.config", "extensions.xml"):
        path = dot_maven / name
        if os.path.lexists(path):
            raise StarterError(
                f"project .mvn/{name} is outside the isolated Maven starter boundary"
            )


def _require_java_identifier(value: str, label: str) -> str:
    if _JAVA_IDENTIFIER.fullmatch(value) is None or value in _JAVA_KEYWORDS:
        raise StarterError(f"{label} must be a safe Java identifier")
    return value


def _require_package(value: str) -> str:
    parts = value.split(".")
    if len(parts) < 2 or any(
        _JAVA_IDENTIFIER.fullmatch(part) is None or part in _JAVA_KEYWORDS
        for part in parts
    ):
        raise StarterError("pilotPackage must be a dotted safe Java package")
    return value


def _require_test_selector(value: str, label: str) -> tuple[str, str]:
    match = _JAVA_TEST_SELECTOR.fullmatch(value)
    if match is None:
        raise StarterError(f"{label} must be fully.qualified.Class#method")
    return match.group("class"), match.group("method")


def _require_operation_id(value: str) -> str:
    if _OPERATION_ID.fullmatch(value) is None or ".." in value:
        raise StarterError("operationId must be a safe manifest filename stem")
    return value


def _require_budget(config: Mapping[str, object], key: str) -> int:
    value = config[key]
    if type(value) is not int or not 1 <= value <= MAX_BUDGET:
        raise StarterError(f"{key} must be an integer from 1 through {MAX_BUDGET}")
    return value


def _normalize_aliases(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise StarterError("dataSourceAliases must be a non-empty array")
    normalized: list[dict[str, str]] = []
    observed_names: set[str] = set()
    aliases: set[str] = set()
    for index, entry in enumerate(value):
        if not isinstance(entry, dict) or frozenset(entry) != ALIAS_KEYS:
            raise StarterError(
                f"dataSourceAliases[{index}] keys must be observedName and alias"
            )
        observed = entry["observedName"]
        alias = entry["alias"]
        if not isinstance(observed, str) or _ALIAS_VALUE.fullmatch(observed) is None:
            raise StarterError(f"dataSourceAliases[{index}].observedName is unsafe")
        if not isinstance(alias, str) or _ALIAS_VALUE.fullmatch(alias) is None:
            raise StarterError(f"dataSourceAliases[{index}].alias is unsafe")
        if observed in observed_names:
            raise StarterError(f"duplicate observed data-source name: {observed}")
        if alias in aliases:
            raise StarterError(f"data-source alias collision: {alias}")
        observed_names.add(observed)
        aliases.add(alias)
        normalized.append({"observedName": observed, "alias": alias})
    return sorted(normalized, key=lambda item: (item["observedName"], item["alias"]))


def _git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
            "LANG": "C",
        }
    )
    return environment


def _run_git(root: Path, arguments: Sequence[str]) -> bytes:
    executable = shutil.which("git")
    if executable is None:
        raise StarterError("git is required")
    command = [
        os.path.realpath(executable),
        "--no-optional-locks",
        "-c", "core.fsmonitor=false",
        "-c", "core.quotepath=false",
        "-C", os.fspath(root),
        *arguments,
    ]
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                env=_git_environment(),
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise StarterError("git inspection failed") from error
        stdout_size = stdout_file.seek(0, os.SEEK_END)
        stderr_size = stderr_file.seek(0, os.SEEK_END)
        if (
            stdout_size > MAX_GIT_OUTPUT_BYTES
            or stderr_size > MAX_GIT_OUTPUT_BYTES
            or stdout_size + stderr_size > MAX_GIT_OUTPUT_BYTES
        ):
            raise StarterError("git inspection output exceeded its size limit")
        if completed.returncode != 0:
            raise StarterError("git inspection rejected the target repository")
        stdout_file.seek(0)
        return stdout_file.read()


def _git_snapshot(root: Path) -> GitSnapshot:
    top = _run_git(root, ["rev-parse", "--show-toplevel"]).decode("utf-8").strip()
    if Path(top).resolve(strict=True) != root:
        raise StarterError("projectRoot must be the Git worktree top level")
    head = _run_git(root, ["rev-parse", "HEAD"]).decode("ascii").strip()
    if _LOWER_HEX_40.fullmatch(head) is None:
        raise StarterError("target HEAD is not one full commit ID")
    status_bytes = _run_git(
        root,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames"],
    )
    index = _run_git(root, ["ls-files", "--stage", "-z"])
    absolute_git_dir = _run_git(root, ["rev-parse", "--absolute-git-dir"])
    common_git_dir = _run_git(
        root,
        ["rev-parse", "--path-format=absolute", "--git-common-dir"],
    )
    worktrees = _run_git(root, ["worktree", "list", "--porcelain", "-z"])
    return GitSnapshot(
        head,
        status_bytes,
        index,
        absolute_git_dir,
        common_git_dir,
        worktrees,
    )


def _git_path(payload: bytes, label: str, *, require_directory: bool) -> Path:
    if not payload.endswith(b"\n") or payload.count(b"\n") != 1:
        raise StarterError(f"{label} did not return one path")
    path = Path(os.fsdecode(payload[:-1]))
    if not path.is_absolute() or path != Path(os.path.normpath(os.fspath(path))):
        raise StarterError(f"{label} must be an absolute normalized path")
    if require_directory:
        try:
            metadata = os.lstat(path)
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise StarterError(f"{label} is unavailable") from error
        if not stat.S_ISDIR(metadata.st_mode) or resolved != path:
            raise StarterError(f"{label} must be a canonical non-symlink directory")
    return path


def _repository_boundaries(snapshot: GitSnapshot) -> tuple[Path, ...]:
    boundaries = {
        _git_path(snapshot.absolute_git_dir, "absolute Git directory", require_directory=True),
        _git_path(snapshot.common_git_dir, "common Git directory", require_directory=True),
    }
    worktree_records = [
        record[len(b"worktree "):]
        for record in snapshot.worktrees.split(b"\0")
        if record.startswith(b"worktree ")
    ]
    if not worktree_records:
        raise StarterError("Git did not report any registered worktree")
    for raw in worktree_records:
        if not raw or b"\n" in raw:
            raise StarterError("Git reported an unsafe registered worktree path")
        path = Path(os.fsdecode(raw))
        if not path.is_absolute() or path != Path(os.path.normpath(os.fspath(path))):
            raise StarterError("registered worktree path must be absolute and normalized")
        if os.path.lexists(path):
            try:
                metadata = os.lstat(path)
                resolved = path.resolve(strict=True)
            except OSError as error:
                raise StarterError("registered worktree path is unavailable") from error
            if not stat.S_ISDIR(metadata.st_mode) or resolved != path:
                raise StarterError(
                    "registered worktree path must be a canonical non-symlink directory"
                )
        boundaries.add(path)
    return tuple(sorted(boundaries, key=os.fspath))


def _reject_hidden_index_entries(root: Path) -> None:
    entries = [
        entry
        for entry in _run_git(root, ["ls-files", "-v", "-z"]).split(b"\0")
        if entry
    ]
    unsupported = [entry for entry in entries if not entry.startswith(b"H ")]
    if unsupported:
        raise StarterError(
            "target index must not contain assume-unchanged, skip-worktree, "
            "or other hidden entries"
        )


def _require_head_bound_regular(
    root: Path,
    relative: str,
    payload: bytes,
    label: str,
) -> None:
    encoded_relative = relative.encode("utf-8")
    index = _run_git(root, ["ls-files", "--stage", "-z", "--", relative])
    index_entries = [entry for entry in index.split(b"\0") if entry]
    if len(index_entries) != 1:
        raise StarterError(f"{label} must be one tracked mode-100644 file")
    index_match = re.fullmatch(
        rb"100644 ([0-9a-f]{40}) 0\t" + re.escape(encoded_relative),
        index_entries[0],
    )
    if index_match is None:
        raise StarterError(f"{label} must be one tracked mode-100644 file")

    tree = _run_git(root, ["ls-tree", "-z", "HEAD", "--", relative])
    tree_entries = [entry for entry in tree.split(b"\0") if entry]
    if len(tree_entries) != 1:
        raise StarterError(f"{label} must exist as one mode-100644 blob at target HEAD")
    tree_match = re.fullmatch(
        rb"100644 blob ([0-9a-f]{40})\t" + re.escape(encoded_relative),
        tree_entries[0],
    )
    if tree_match is None or tree_match.group(1) != index_match.group(1):
        raise StarterError(f"{label} index entry must equal the target HEAD blob")
    head_payload = _run_git(root, ["cat-file", "blob", tree_match.group(1).decode("ascii")])
    if payload != head_payload:
        raise StarterError(f"{label} worktree bytes must equal the target HEAD blob")


def _load_template(path: Path, expected_sha256: str, label: str) -> str:
    payload = _read_stable_regular(path, label, MAX_TEMPLATE_BYTES)
    if _sha256(payload) != expected_sha256:
        raise StarterError(f"{label} SHA-256 changed")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise StarterError(f"{label} must be strict UTF-8") from error
    if "\r" in text or not text.endswith("\n"):
        raise StarterError(f"{label} must use LF and end with one newline")
    return text


def _render_template(
    template: str,
    replacements: Mapping[str, str],
    expected_placeholders: frozenset[str],
    label: str,
) -> str:
    actual = frozenset(_PLACEHOLDER.findall(template))
    if actual != expected_placeholders or frozenset(replacements) != expected_placeholders:
        raise StarterError(f"{label} placeholder contract changed")
    rendered = template
    for placeholder in sorted(replacements):
        rendered = rendered.replace(placeholder, replacements[placeholder])
    if _PLACEHOLDER.search(rendered):
        raise StarterError(f"{label} retained a placeholder")
    return rendered


def _parse_pom(payload: bytes, label: str) -> tuple[str, ET.Element]:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise StarterError(f"{label} must not contain a UTF-8 BOM")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise StarterError(f"{label} must be strict UTF-8") from error
    if "\r" in text or not text.endswith("\n"):
        raise StarterError(f"{label} must use LF and end with one newline")
    if any(
        unicodedata.category(character) in {"Cf", "Cs", "Zl", "Zp"}
        or (
            unicodedata.category(character) == "Cc"
            and character not in {"\n", "\t"}
        )
        for character in text
    ):
        raise StarterError(f"{label} contains an unsafe Unicode character")
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise StarterError(f"{label} must not contain DTD or entity declarations")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise StarterError(f"{label} is not well-formed XML") from error
    if root.tag != f"{{{MAVEN_NAMESPACE}}}project":
        raise StarterError(f"{label} must use the Maven 4.0.0 project namespace")
    return text, root


def _literal_pom_value(
    element: ET.Element,
    local: str,
    label: str,
    *,
    required: bool,
) -> str | None:
    qualified = f"{{{MAVEN_NAMESPACE}}}{local}"
    values = element.findall(qualified)
    if len(values) > 1:
        raise StarterError(f"{label} contains more than one {local}")
    if not values:
        if required:
            raise StarterError(f"{label} must declare one literal {local}")
        return None
    value = (values[0].text or "").strip()
    if not value or _MAVEN_COORDINATE.fullmatch(value) is None:
        raise StarterError(f"{label} {local} must be one literal Maven coordinate value")
    return value


def _project_coordinate(root: ET.Element, label: str) -> tuple[str, str, str]:
    parent_nodes = root.findall(f"{{{MAVEN_NAMESPACE}}}parent")
    if len(parent_nodes) > 1:
        raise StarterError(f"{label} contains more than one parent")
    parent = parent_nodes[0] if parent_nodes else None
    group = _literal_pom_value(root, "groupId", label, required=False)
    version = _literal_pom_value(root, "version", label, required=False)
    artifact = _literal_pom_value(root, "artifactId", label, required=True)
    if group is None:
        if parent is None:
            raise StarterError(f"{label} must expose one literal effective groupId")
        group = _literal_pom_value(parent, "groupId", f"{label} parent", required=True)
    if version is None:
        if parent is None:
            raise StarterError(f"{label} must expose one literal effective version")
        version = _literal_pom_value(parent, "version", f"{label} parent", required=True)
    return group, artifact or "", version


def _local_parent_chain(
    project_root: Path,
    owning_pom: Path,
    owning_root: ET.Element,
) -> tuple[tuple[str, bytes, ET.Element], ...]:
    """Resolve local parents through the reactor root; reject ambiguous nested inheritance."""
    qualified_parent = f"{{{MAVEN_NAMESPACE}}}parent"
    qualified_relative = f"{{{MAVEN_NAMESPACE}}}relativePath"
    current_pom = owning_pom
    current_root = owning_root
    seen = {owning_pom}
    result: list[tuple[str, bytes, ET.Element]] = []
    cumulative_bytes = 0
    for _ in range(32):
        if current_pom == project_root / "pom.xml":
            return tuple(result)
        parents = current_root.findall(qualified_parent)
        if len(parents) > 1:
            raise StarterError("Maven parent chain contains more than one parent element")
        if not parents:
            return tuple(result)
        declared_parent = parents[0]
        relative_nodes = declared_parent.findall(qualified_relative)
        if len(relative_nodes) > 1:
            raise StarterError("Maven parent contains more than one relativePath")
        if relative_nodes:
            relative = (relative_nodes[0].text or "").strip()
            if not relative:
                raise StarterError(
                    "external Maven parent inheritance is outside the starter boundary"
                )
        else:
            relative = "../pom.xml"
        _validate_text(relative, "Maven parent relativePath")
        if (
            len(relative) > 512
            or "\\" in relative
            or Path(relative).is_absolute()
            or Path(relative) != Path(os.path.normpath(relative))
        ):
            raise StarterError("Maven parent relativePath must be a normalized local path")
        candidate = Path(
            os.path.normpath(os.fspath(current_pom.parent / relative))
        )
        try:
            metadata = os.lstat(candidate)
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise StarterError("local Maven parent POM is unavailable") from error
        if (
            not stat.S_ISREG(metadata.st_mode)
            or resolved != candidate
            or not candidate.is_relative_to(project_root)
            or candidate.name != "pom.xml"
        ):
            raise StarterError(
                "Maven parent must be a canonical in-repository pom.xml file"
            )
        if candidate in seen:
            raise StarterError("local Maven parent chain contains a cycle")
        relative_name = candidate.relative_to(project_root).as_posix()
        label = f"inherited parent POM {relative_name}"
        payload = _read_stable_regular(candidate, label, MAX_POM_BYTES)
        cumulative_bytes += len(payload)
        if cumulative_bytes > MAX_PARENT_CHAIN_BYTES:
            raise StarterError("local Maven parent chain exceeds its byte limit")
        _, parent_root = _parse_pom(payload, label)
        declared = (
            _literal_pom_value(
                declared_parent,
                "groupId",
                "declared Maven parent",
                required=True,
            ),
            _literal_pom_value(
                declared_parent,
                "artifactId",
                "declared Maven parent",
                required=True,
            ),
            _literal_pom_value(
                declared_parent,
                "version",
                "declared Maven parent",
                required=True,
            ),
        )
        if declared != _project_coordinate(parent_root, label):
            raise StarterError(
                "declared Maven parent coordinates differ from the local relativePath POM"
            )
        result.append((relative_name, payload, parent_root))
        seen.add(candidate)
        current_pom = candidate
        current_root = parent_root
    raise StarterError("local Maven parent chain exceeds 32 POMs")


def _reactor_parent_is_unverified(
    project_root: Path,
    reactor_root: ET.Element,
) -> bool:
    qualified_parent = f"{{{MAVEN_NAMESPACE}}}parent"
    qualified_relative = f"{{{MAVEN_NAMESPACE}}}relativePath"
    parents = reactor_root.findall(qualified_parent)
    if len(parents) > 1:
        raise StarterError("reactor POM contains more than one parent")
    if not parents:
        return False
    parent = parents[0]
    for local in ("groupId", "artifactId", "version"):
        _literal_pom_value(parent, local, "reactor Maven parent", required=True)
    relative_nodes = parent.findall(qualified_relative)
    if len(relative_nodes) > 1:
        raise StarterError("reactor Maven parent contains more than one relativePath")
    relative = (
        (relative_nodes[0].text or "").strip()
        if relative_nodes
        else "../pom.xml"
    )
    if relative:
        if (
            len(relative) > 512
            or "\\" in relative
            or Path(relative).is_absolute()
            or Path(relative) != Path(os.path.normpath(relative))
        ):
            raise StarterError(
                "reactor Maven parent relativePath must be empty or normalized"
            )
        candidate = Path(
            os.path.normpath(os.fspath(project_root / relative))
        )
        if candidate.is_relative_to(project_root):
            raise StarterError(
                "reactor Maven parent must not point back inside projectRoot"
            )
    return True


def _reject_custom_profile_off_report_layout(
    poms: Sequence[tuple[str, ET.Element]],
) -> None:
    namespace = {"m": MAVEN_NAMESPACE}
    qualified = lambda local: f"{{{MAVEN_NAMESPACE}}}{local}"
    blocked_surefire_settings = (
        "reportsDirectory",
        "reportNameSuffix",
        "disableXmlReport",
        "rerunFailingTestsCount",
    )
    for label, root in poms:
        if root.findall(
            ".//m:properties/m:surefire.rerunFailingTestsCount",
            namespace,
        ):
            raise StarterError(
                f"{label} surefire.rerunFailingTestsCount property is outside the "
                "single-invocation assisted runner boundary"
            )
        if root.findall(".//m:build/m:directory", namespace):
            raise StarterError(
                f"{label} custom build directory is outside the assisted runner boundary"
            )
        for plugin in root.findall(".//m:build//m:plugin", namespace):
            artifact_nodes = plugin.findall("m:artifactId", namespace)
            group_nodes = plugin.findall("m:groupId", namespace)
            if len(artifact_nodes) != 1 or len(group_nodes) > 1:
                raise StarterError(
                    f"{label} Maven plugin identity must contain one artifactId "
                    "and at most one groupId"
                )
            artifact = (artifact_nodes[0].text or "").strip()
            group = (group_nodes[0].text or "").strip() if group_nodes else ""
            if (
                not artifact
                or _MAVEN_COORDINATE.fullmatch(artifact) is None
                or (group and _MAVEN_COORDINATE.fullmatch(group) is None)
            ):
                raise StarterError(f"{label} Maven plugin identity must be literal")
            if artifact != "maven-surefire-plugin" or group not in {
                "",
                "org.apache.maven.plugins",
            }:
                continue
            if plugin.findall("m:executions/m:execution", namespace):
                raise StarterError(
                    f"{label} Surefire executions are outside the single-invocation "
                    "assisted runner boundary"
                )
            for configuration in plugin.findall(".//m:configuration", namespace):
                for setting in blocked_surefire_settings:
                    if configuration.find(f".//{qualified(setting)}") is not None:
                        raise StarterError(
                            f"{label} custom Surefire {setting} is outside the assisted "
                            "runner boundary"
                        )


def _reject_owning_active_by_default_profiles(root: ET.Element) -> None:
    namespace = {"m": MAVEN_NAMESPACE}
    values = root.findall(
        "m:profiles/m:profile/m:activation/m:activeByDefault",
        namespace,
    )
    if any((element.text or "").strip().lower() == "true" for element in values):
        raise StarterError(
            "owning POM activeByDefault profiles are outside the assisted runner "
            "boundary because activating routecontract-pilot would deactivate them"
        )


def _insert_profile(pom_text: str, pom_root: ET.Element, profile: str) -> str:
    forbidden_markers = (
        "routecontract-pilot",
        "routeContractPilot",
        "io.github.ym0506.routecontract",
        "routecontractRepositoryUrl",
        "src/routeContractPilot/java",
    )
    if any(marker in pom_text for marker in forbidden_markers):
        raise StarterError("owning POM already contains a RouteContract pilot marker")
    namespace = f"{{{MAVEN_NAMESPACE}}}"
    profiles = [child for child in pom_root if child.tag == namespace + "profiles"]
    if len(profiles) > 1:
        raise StarterError("owning POM contains more than one root profiles element")
    if len(profiles) == 1:
        if pom_text.count("</profiles>") != 1:
            raise StarterError("existing profiles element has an unsupported lexical form")
        insertion = pom_text.index("</profiles>")
        prefix = pom_text[:insertion]
        separator = "" if prefix.endswith("\n\n") else "\n"
        result = prefix + separator + profile + pom_text[insertion:]
    else:
        if "</profiles>" in pom_text:
            raise StarterError("owning POM contains an ambiguous profiles closing tag")
        if pom_text.count("</project>") != 1:
            raise StarterError("owning POM has an unsupported project closing tag")
        insertion = pom_text.index("</project>")
        prefix = pom_text[:insertion]
        separator = "" if prefix.endswith("\n\n") else "\n"
        wrapped = "  <profiles>\n" + profile + "  </profiles>\n"
        result = prefix + separator + wrapped + pom_text[insertion:]
    try:
        rendered_root = ET.fromstring(result.encode("utf-8"))
    except ET.ParseError as error:
        raise StarterError("rendered POM is not well-formed XML") from error
    rendered_profiles = rendered_root.findall(
        f"{namespace}profiles/{namespace}profile"
    )
    pilot_ids = [
        (element.findtext(namespace + "id") or "").strip()
        for element in rendered_profiles
    ]
    if pilot_ids.count("routecontract-pilot") != 1:
        raise StarterError("rendered POM does not contain exactly one pilot profile")
    return result


def _unified_diff(old: str, new: str, relative: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{relative}",
        tofile=f"b/{relative}",
        lineterm="\n",
    )
    body = "".join(diff)
    if not body:
        raise StarterError("rendered POM patch is unexpectedly empty")
    return f"diff --git a/{relative} b/{relative}\n" + body


def _new_file_diff(content: str, relative: str) -> str:
    lines = content.splitlines(keepends=True)
    if not lines or any(not line.endswith("\n") for line in lines):
        raise StarterError("rendered Java template must end every line with LF")
    additions = "".join("+" + line for line in lines)
    return (
        f"diff --git a/{relative} b/{relative}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{relative}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{additions}"
    )


def _json_bytes(value: object, *, sort_keys: bool = False) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=sort_keys)
        + "\n"
    ).encode("utf-8")


def _safe_missing_path(path: Path, root: Path, label: str) -> None:
    if not path.is_relative_to(root):
        raise StarterError(f"{label} escaped the owning module")
    current = path.parent
    while current != root and not os.path.lexists(current):
        current = current.parent
    if not current.is_relative_to(root):
        raise StarterError(f"{label} escaped the owning module")
    if os.path.lexists(current):
        try:
            metadata = os.lstat(current)
        except OSError as error:
            raise StarterError(f"{label} parent is unavailable") from error
        if not stat.S_ISDIR(metadata.st_mode) or current.resolve(strict=True) != current:
            raise StarterError(f"{label} parent must not traverse a symlink")
    if os.path.lexists(path):
        raise StarterError(f"{label} must start absent")


def _prepare(config_path: Path) -> PreparedStarter:
    config = _load_config(config_path)
    _require_exact_boundary(config)
    project_root = _require_canonical_directory(
        _require_string(config, "projectRoot"), "projectRoot"
    )
    _reject_maven_project_configuration(project_root)
    owning_module = _require_string(config, "owningModule")
    owning_root = _require_safe_relative_directory(project_root, owning_module)
    owning_pom = owning_root / "pom.xml"
    root_pom = project_root / "pom.xml"
    root_payload = _read_stable_regular(root_pom, "reactor POM", MAX_POM_BYTES)
    owning_payload = (
        root_payload
        if owning_pom == root_pom
        else _read_stable_regular(owning_pom, "owning POM", MAX_POM_BYTES)
    )
    root_text, root_root_element = _parse_pom(root_payload, "reactor POM")
    if owning_pom == root_pom:
        owning_text = root_text
        owning_root_element = root_root_element
    else:
        owning_text, owning_root_element = _parse_pom(owning_payload, "owning POM")
    reactor_parent_unverified = _reactor_parent_is_unverified(
        project_root,
        root_root_element,
    )
    parent_chain = _local_parent_chain(project_root, owning_pom, owning_root_element)
    report_layout_by_path: dict[str, tuple[str, ET.Element]] = {
        "pom.xml": ("reactor POM", root_root_element),
        owning_pom.relative_to(project_root).as_posix(): (
            "owning POM",
            owning_root_element,
        ),
    }
    for relative, _, element in parent_chain:
        report_layout_by_path[relative] = (f"inherited parent POM {relative}", element)
    report_layout_poms = tuple(
        report_layout_by_path[relative]
        for relative in sorted(report_layout_by_path)
    )
    _reject_custom_profile_off_report_layout(report_layout_poms)
    _reject_owning_active_by_default_profiles(owning_root_element)
    owning_pom_relative = owning_pom.relative_to(project_root).as_posix()
    reactor_selector = _require_string(config, "reactorSelector")
    if reactor_selector != owning_pom_relative:
        raise StarterError(
            "reactorSelector must equal the owning POM path relative to projectRoot"
        )

    expected_commit = _require_string(config, "expectedTargetCommit")
    expected_pom_sha = _require_string(config, "expectedPomSha256")
    if _LOWER_HEX_40.fullmatch(expected_commit) is None:
        raise StarterError("expectedTargetCommit must be one lowercase full commit ID")
    if _LOWER_HEX_64.fullmatch(expected_pom_sha) is None:
        raise StarterError("expectedPomSha256 must be one lowercase SHA-256")

    snapshot = _git_snapshot(project_root)
    if snapshot.status:
        raise StarterError("target worktree must be clean, including untracked files")
    _reject_hidden_index_entries(project_root)
    if snapshot.head != expected_commit:
        raise StarterError("target HEAD differs from expectedTargetCommit")
    _require_head_bound_regular(project_root, "pom.xml", root_payload, "reactor POM")
    if owning_pom != root_pom:
        _require_head_bound_regular(
            project_root,
            owning_pom_relative,
            owning_payload,
            "owning POM",
        )
    inherited_bindings: list[tuple[str, str]] = []
    for relative, payload, _ in parent_chain:
        if relative in {"pom.xml", owning_pom_relative}:
            continue
        _require_head_bound_regular(
            project_root,
            relative,
            payload,
            f"inherited parent POM {relative}",
        )
        inherited_bindings.append((relative, _sha256(payload)))
    actual_pom_sha = _sha256(owning_payload)
    if actual_pom_sha != expected_pom_sha:
        raise StarterError("owning POM differs from expectedPomSha256")

    profile_class, profile_method = _require_test_selector(
        _require_string(config, "profileOffTest"), "profileOffTest"
    )
    if _require_string(config, "profileOffTestShape") != PROFILE_OFF_TEST_SHAPE:
        raise StarterError(
            "profileOffTestShape must be exactly single-non-parameterized"
        )
    package_name = _require_package(_require_string(config, "pilotPackage"))
    pilot_class = _require_java_identifier(
        _require_string(config, "pilotClass"), "pilotClass"
    )
    if not pilot_class.endswith("Test"):
        raise StarterError("pilotClass must end with Test")
    pilot_method = _require_java_identifier(
        _require_string(config, "pilotMethod"), "pilotMethod"
    )
    pilot_fqcn = f"{package_name}.{pilot_class}"
    if pilot_fqcn == profile_class:
        raise StarterError("profileOffTest and generated pilot test need distinct classes")
    operation_id = _require_operation_id(_require_string(config, "operationId"))
    max_attempts = _require_budget(config, "reviewedMaxAttempts")
    max_data_sources = _require_budget(config, "reviewedMaxDataSources")
    aliases = _normalize_aliases(config["dataSourceAliases"])
    if max_data_sources > len(aliases):
        raise StarterError(
            "reviewedMaxDataSources cannot exceed the explicit alias universe"
        )
    scope = _require_string(config, "shardingSphereScope")
    if scope not in {"compile", "runtime", "test"}:
        raise StarterError("shardingSphereScope must be compile, runtime, or test")

    package_path = PurePosixPath(*package_name.split("."))
    pilot_source_relative = (
        PurePosixPath(owning_module if owning_module != "." else "")
        / "src"
        / "routeContractPilot"
        / "java"
        / package_path
        / f"{pilot_class}.java"
    ).as_posix()
    approved_relative = (
        PurePosixPath(owning_module if owning_module != "." else "")
        / "src"
        / "routeContractPilot"
        / "resources"
        / "route-contracts"
        / f"{operation_id}.json"
    ).as_posix()
    candidate_relative = (
        PurePosixPath(owning_module if owning_module != "." else "")
        / "target"
        / "routecontract"
        / f"{operation_id}.candidate.json"
    ).as_posix()
    _safe_missing_path(project_root / pilot_source_relative, owning_root, "pilot source")
    _safe_missing_path(project_root / approved_relative, owning_root, "approved baseline")
    _safe_missing_path(project_root / candidate_relative, owning_root, "candidate")

    repository_root = Path(__file__).resolve(strict=True).parent.parent
    templates = repository_root / "examples" / "maven-pilot" / "starter-templates"
    profile_template = _load_template(
        templates / "maven-profile.xml.in",
        PROFILE_TEMPLATE_SHA256,
        "Maven profile template",
    )
    java_template = _load_template(
        templates / "RouteContractPilotTest.java.in",
        JAVA_TEMPLATE_SHA256,
        "Java pilot template",
    )
    rendered_profile = _render_template(
        profile_template,
        {
            "@@ROUTECONTRACT_VERSION@@": EXPECTED_BOUNDARY["routeContractVersion"],
            "@@SHARDINGSPHERE_VERSION@@": EXPECTED_BOUNDARY["shardingSphereVersion"],
            "@@SHARDINGSPHERE_SCOPE@@": scope,
        },
        frozenset(
            {
                "@@ROUTECONTRACT_VERSION@@",
                "@@SHARDINGSPHERE_VERSION@@",
                "@@SHARDINGSPHERE_SCOPE@@",
            }
        ),
        "Maven profile template",
    )
    rendered_pom = _insert_profile(owning_text, owning_root_element, rendered_profile)

    alias_entries = ",\n".join(
        f'                Map.entry("{item["observedName"]}", "{item["alias"]}")'
        for item in aliases
    )
    rendered_java = _render_template(
        java_template,
        {
            "@@PACKAGE_NAME@@": package_name,
            "@@PILOT_CLASS@@": pilot_class,
            "@@PILOT_METHOD@@": pilot_method,
            "@@OPERATION_ID@@": operation_id,
            "@@MAX_ATTEMPTS@@": str(max_attempts),
            "@@MAX_DATA_SOURCES@@": str(max_data_sources),
            "@@ALIAS_ENTRIES@@": alias_entries,
            "@@ROUTECONTRACT_VERSION@@": EXPECTED_BOUNDARY["routeContractVersion"],
        },
        frozenset(
            {
                "@@PACKAGE_NAME@@",
                "@@PILOT_CLASS@@",
                "@@PILOT_METHOD@@",
                "@@OPERATION_ID@@",
                "@@MAX_ATTEMPTS@@",
                "@@MAX_DATA_SOURCES@@",
                "@@ALIAS_ENTRIES@@",
                "@@ROUTECONTRACT_VERSION@@",
            }
        ),
        "Java pilot template",
    )
    patch_text = _unified_diff(
        owning_text,
        rendered_pom,
        owning_pom_relative,
    ) + _new_file_diff(rendered_java, pilot_source_relative)

    normalized_config = dict(config)
    normalized_config["dataSourceAliases"] = aliases
    assisted_config = {
        "projectRoot": os.fspath(project_root),
        "owningModule": owning_module,
        "reactorSelector": reactor_selector,
        "profileOffTest": _require_string(config, "profileOffTest"),
        "pilotTest": f"{pilot_fqcn}#{pilot_method}",
        "operationId": operation_id,
    }
    if tuple(assisted_config) != ASSISTED_CONFIG_KEYS:
        raise StarterError("internal assisted config order changed")

    report_root_relative = (
        PurePosixPath(owning_module if owning_module != "." else "")
        / "target"
        / "surefire-reports"
    )
    profile_report_relative = (
        report_root_relative / f"TEST-{profile_class}.xml"
    ).as_posix()
    pilot_report_relative = (
        report_root_relative / f"TEST-{pilot_fqcn}.xml"
    ).as_posix()
    ci_config_fields_literal = json.dumps(
        {
            "owningModule": owning_module,
            "reactorSelector": reactor_selector,
            "profileOffTest": f"{profile_class}#{profile_method}",
            "pilotTest": f"{pilot_fqcn}#{pilot_method}",
            "operationId": operation_id,
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )
    external_parent_note = (
        "The reactor declares an external parent above the checked local POM chain. Its effective "
        "build/report settings were not inspected by this generator; the assisted wrapper must "
        "still observe the exact default profile-off XML report or the pilot is incompatible.\n\n"
        if reactor_parent_unverified
        else ""
    )
    next_steps = f"""# RouteContract Maven pilot: review-only next steps

This bundle records the generation-time target commit `{expected_commit}` and owning POM SHA-256
`{actual_pom_sha}`. It does not enforce those values later when someone applies the patch. The
generator did not modify the target repository, apply the patch, run Maven, or create/approve a
baseline. Retain the renderer's out-of-band `manifestSha256` success field. Before consuming the
bundle, hash `bundle-manifest.json` against that field and verify each `generatedFiles` byte count
and SHA-256 recorded by the manifest.

{external_parent_note}1. Immediately before review or application, require the target to still be a clean checkout at
   exactly `{expected_commit}`, re-hash `{owning_pom_relative}` to
   `{actual_pom_sha}`, and rerun this generator if either value moved. Review
   `routecontract-pilot.patch`, `pilot-spec.json`, and the explicit aliases/budgets. Do not apply
   the patch merely because this bundle was generated.
2. If the target maintainers accept the approach, apply the patch themselves on a disposable
   branch and replace `ROUTECONTRACT_STARTER_REVIEW_REQUIRED` with exactly one supported Java 17,
   ShardingSphere-JDBC 5.5.3, synchronous non-batch `PreparedStatement` operation. Preserve its
   existing business assertion. Review target-specific dependency convergence; the generated
   profile is a starting point, not a claim that the graph fits. `profileOffTest` must continue to
   select exactly one ordinary, non-parameterized Surefire testcase with the bare configured
   method name.
3. `assisted-pilot.json` and `pilot-spec.json` are host-local: their absolute `projectRoot` binds
   the generation-time target path. Do not commit either file or copy either one to another
   checkout. `pilot-spec.json` is review evidence; only `assisted-pilot.json` is runner input.
   While the target remains at that same canonical path, run the existing assisted wrapper from
   the RouteContract checkout
   containing the verifier. It downloads exact Maven 3.9.14, verifies and installs the immutable
   `0.1.2` Release assets into a private repository, and checks the profile-off and profile-on
   boundaries:

   ```bash
   bundle_root="/absolute/path/to/the-new-output-directory-used-with---output"
   python3 -I scripts/run-assisted-maven-pilot.py \\
     --config "${{bundle_root}}/assisted-pilot.json" \\
     --expected-outcome review
   ```

4. The review run must leave `{candidate_relative}` and must leave the approved path
   `{approved_relative}` absent. Inspect the operation ID, aliases, budgets, callback outcomes,
   parameter shape, and rewritten-SQL fingerprint. Never infer SQL semantics or business success
   from hook callbacks.
5. Only a target-repository maintainer may approve the baseline by copying the exact reviewed
   candidate bytes to the approved path in a separate action. This bundle contains no baseline and
   grants no approval. After that human action, remove only these stale target-relative evidence
   files if they exist; never remove the approved `src/routeContractPilot/...` file:

   - `{candidate_relative}`
   - `{profile_report_relative}`
   - `{pilot_report_relative}`

   From the same RouteContract checkout, while the target remains at the same canonical path, run
   this self-contained local matched check:

   ```bash
   bundle_root="/absolute/path/to/the-new-output-directory-used-with---output"
   python3 -I scripts/run-assisted-maven-pilot.py \\
     --config "${{bundle_root}}/assisted-pilot.json" \\
     --expected-outcome matched
   ```

6. CI must materialize a fresh mode-`0600` six-field config at job time because its checkout has a
   different absolute root. From the target repository root, create an absent temporary config
   with the same five reviewed logical fields and the CI checkout's canonical path; do not commit
   either host's absolute-path config:

   ```bash
   target_root="$(pwd -P)"
   ci_config="${{RUNNER_TEMP:?}}/routecontract-assisted-maven-pilot.json"
   test ! -e "${{ci_config}}"
   python3 -I - "${{target_root}}" "${{ci_config}}" <<'PY'
   import json
   import os
   from pathlib import Path
   import sys

   root = Path(sys.argv[1]).resolve(strict=True)
   destination = Path(sys.argv[2])
   config = {ci_config_fields_literal}
   config = {{"projectRoot": os.fspath(root), **config}}
   payload = (json.dumps(config, ensure_ascii=False, indent=2) + "\\n").encode("utf-8")
   flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
   descriptor = os.open(destination, flags, 0o600)
   try:
       os.fchmod(descriptor, 0o600)
       view = memoryview(payload)
       while view:
           written = os.write(descriptor, view)
           if written <= 0:
               raise OSError("CI config write made no progress")
           view = view[written:]
       os.fsync(descriptor)
   finally:
       os.close(descriptor)
   PY
   python3 -I /absolute/path/to/pinned-routecontract/scripts/run-assisted-maven-pilot.py \\
     --config "${{ci_config}}" \\
     --expected-outcome matched
   ```

   Keep the target's existing business assertion and this exact matched check in its normal public
   CI review. A passing maintainer-local run or draft PR is not adoption evidence.

Supported boundary: Java 17, Apache Maven 3.9.14, exactly ShardingSphere-JDBC 5.5.3, and one
normal-returning, non-interrupted, synchronous non-batch `PreparedStatement` operation. Stop on a
different version, incompatible dependency graph, `.mvn` execution customization, async/reactive
propagation, ShardingSphere-Proxy, batch execution, SQL Federation, or an operation whose existing
business assertion cannot be preserved.
"""
    files = {
        "NEXT-STEPS.md": next_steps.encode("utf-8"),
        "assisted-pilot.json": _json_bytes(assisted_config),
        "pilot-spec.json": _json_bytes(normalized_config, sort_keys=True),
        "routecontract-pilot.patch": patch_text.encode("utf-8"),
    }
    return PreparedStarter(
        normalized_config,
        project_root,
        owning_root,
        owning_pom,
        owning_pom_relative,
        pilot_source_relative,
        approved_relative,
        candidate_relative,
        snapshot,
        actual_pom_sha,
        tuple(inherited_bindings),
        reactor_parent_unverified,
        files,
    )


def _require_new_output_root(
    value: str,
    prepared: PreparedStarter,
) -> tuple[Path, Path, str]:
    _validate_text(value, "output root")
    if not value or len(value) > 4096:
        raise StarterError("output root has an invalid length")
    output = Path(value)
    if not output.is_absolute() or output != Path(os.path.normpath(value)):
        raise StarterError("output root must be an absolute normalized path")
    parent = output.parent
    try:
        parent_metadata = os.lstat(parent)
        resolved_parent = parent.resolve(strict=True)
    except OSError as error:
        raise StarterError("output parent is unavailable") from error
    if not stat.S_ISDIR(parent_metadata.st_mode) or resolved_parent != parent:
        raise StarterError("output parent must be an existing canonical non-symlink directory")
    if (
        parent_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(parent_metadata.st_mode) & 0o022
    ):
        raise StarterError(
            "output parent must be owned by the current user and not group/other writable"
        )
    if _SAFE_SEGMENT.fullmatch(output.name) is None or output.name in {".", ".."}:
        raise StarterError("output leaf must be one safe path segment")
    if os.path.lexists(output):
        raise StarterError("output root must be new and absent")
    forbidden_roots = _repository_boundaries(prepared.target_snapshot)
    if any(output.is_relative_to(root) for root in forbidden_roots):
        raise StarterError(
            "output root must be outside every target Git worktree and administration directory"
        )
    return output, parent, output.name


def _write_one(directory_fd: int, name: str, payload: bytes) -> os.stat_result:
    if name not in OUTPUT_FILES or PurePosixPath(name).name != name:
        raise StarterError("internal output filename escaped the bundle root")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
    except OSError as error:
        raise StarterError(f"cannot create output file: {name}") from error
    created_identity: os.stat_result | None = None
    try:
        created_identity = os.fstat(descriptor)
        os.fchmod(descriptor, 0o600)
        _reject_extended_acl(descriptor, f"output file {name}")
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise StarterError(f"output write made no progress: {name}")
            view = view[written:]
        os.fsync(descriptor)
        created = os.fstat(descriptor)
    except BaseException as error:
        try:
            if created_identity is None:
                os.unlink(name, dir_fd=directory_fd)
            else:
                named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if (
                    named.st_dev == created_identity.st_dev
                    and named.st_ino == created_identity.st_ino
                ):
                    os.unlink(name, dir_fd=directory_fd)
        except OSError:
            pass
        try:
            os.close(descriptor)
        except OSError:
            pass
        if isinstance(error, OSError):
            raise StarterError(f"cannot complete output file: {name}") from error
        raise
    try:
        os.close(descriptor)
    except OSError as error:
        try:
            named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (
                created_identity is not None
                and named.st_dev == created_identity.st_dev
                and named.st_ino == created_identity.st_ino
            ):
                os.unlink(name, dir_fd=directory_fd)
        except OSError:
            pass
        raise StarterError(f"cannot close output file: {name}") from error
    return created


def _manifest(prepared: PreparedStarter) -> bytes:
    generated = [
        {
            "bytes": len(payload),
            "path": name,
            "sha256": _sha256(payload),
        }
        for name, payload in sorted(prepared.files_without_manifest.items())
    ]
    value = {
        "baselineGenerated": False,
        "boundary": EXPECTED_BOUNDARY,
        "generatedFiles": generated,
        "kind": "routecontract-maven-pilot-review-bundle",
        "reviewOnly": True,
        "schemaVersion": SCHEMA_VERSION,
        "target": {
            "approvedBaselinePath": prepared.approved_relative,
            "candidatePath": prepared.candidate_relative,
            "commit": prepared.target_snapshot.head,
            "externalParentAboveReactorUnverified": prepared.reactor_parent_unverified,
            "owningPomPath": prepared.owning_pom_relative,
            "owningPomSha256": prepared.target_pom_sha256,
            "pilotSourcePath": prepared.pilot_source_relative,
            "statusSha256": _sha256(prepared.target_snapshot.status),
        },
        "templateSha256": {
            "javaPilot": JAVA_TEMPLATE_SHA256,
            "mavenProfile": PROFILE_TEMPLATE_SHA256,
        },
    }
    return _json_bytes(value, sort_keys=True)


def _revalidate_target(prepared: PreparedStarter) -> None:
    current = _git_snapshot(prepared.project_root)
    if current != prepared.target_snapshot:
        raise StarterError(
            "target repository changed during bundle creation; do not trust the bundle"
        )
    _reject_hidden_index_entries(prepared.project_root)
    root_pom = prepared.project_root / "pom.xml"
    root_payload = _read_stable_regular(root_pom, "reactor POM", MAX_POM_BYTES)
    owning_payload = (
        root_payload
        if prepared.owning_pom == root_pom
        else _read_stable_regular(prepared.owning_pom, "owning POM", MAX_POM_BYTES)
    )
    _require_head_bound_regular(
        prepared.project_root,
        "pom.xml",
        root_payload,
        "reactor POM",
    )
    if prepared.owning_pom != root_pom:
        _require_head_bound_regular(
            prepared.project_root,
            prepared.owning_pom_relative,
            owning_payload,
            "owning POM",
        )
    for relative, expected_sha256 in prepared.inherited_pom_sha256:
        inherited = _read_stable_regular(
            prepared.project_root / relative,
            f"inherited parent POM {relative}",
            MAX_POM_BYTES,
        )
        _require_head_bound_regular(
            prepared.project_root,
            relative,
            inherited,
            f"inherited parent POM {relative}",
        )
        if _sha256(inherited) != expected_sha256:
            raise StarterError(
                f"inherited parent POM changed during bundle creation: {relative}"
            )
    if _sha256(owning_payload) != prepared.target_pom_sha256:
        raise StarterError("owning POM changed during bundle creation")
    _safe_missing_path(
        prepared.project_root / prepared.pilot_source_relative,
        prepared.owning_root,
        "pilot source",
    )
    _safe_missing_path(
        prepared.project_root / prepared.approved_relative,
        prepared.owning_root,
        "approved baseline",
    )
    _safe_missing_path(
        prepared.project_root / prepared.candidate_relative,
        prepared.owning_root,
        "candidate",
    )
    if _git_snapshot(prepared.project_root) != prepared.target_snapshot:
        raise StarterError(
            "target repository changed during final bundle verification; do not trust the bundle"
        )
    _reject_hidden_index_entries(prepared.project_root)


def _require_named_output_root(output: Path, created: os.stat_result) -> None:
    try:
        named = os.lstat(output)
        resolved = output.resolve(strict=True)
    except OSError as error:
        raise StarterError("output root identity changed") from error
    if (
        not stat.S_ISDIR(named.st_mode)
        or named.st_dev != created.st_dev
        or named.st_ino != created.st_ino
        or stat.S_IMODE(named.st_mode) != 0o700
        or resolved != output
    ):
        raise StarterError("output root identity or mode changed")


def _verify_output_file(
    directory_fd: int,
    name: str,
    created: os.stat_result,
    expected: bytes,
) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as error:
        raise StarterError(f"output file identity changed: {name}") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_dev != created.st_dev
            or before.st_ino != created.st_ino
            or stat.S_IMODE(before.st_mode) != 0o600
        ):
            raise StarterError(f"output file identity or mode changed: {name}")
        _reject_extended_acl(descriptor, f"output file {name}")
        if before.st_size > MAX_OUTPUT_BYTES:
            raise StarterError(f"output file exceeds its size limit: {name}")
        chunks: list[bytes] = []
        remaining = MAX_OUTPUT_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if len(payload) > MAX_OUTPUT_BYTES:
            raise StarterError(f"output file exceeds its size limit: {name}")
        if _metadata(before) != _metadata(after):
            raise StarterError(f"output file changed while it was verified: {name}")
    finally:
        os.close(descriptor)
    try:
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as error:
        raise StarterError(f"output file identity changed: {name}") from error
    if _metadata(named) != _metadata(after):
        raise StarterError(f"output file identity changed: {name}")
    if payload != expected:
        raise StarterError(f"output file bytes changed: {name}")


def _cleanup_created_bundle(
    parent_fd: int,
    directory_fd: int | None,
    leaf: str,
    directory_created: bool,
    created_directory: os.stat_result | None,
    created_files: Mapping[str, os.stat_result],
) -> None:
    if not directory_created:
        return
    if directory_fd is None or created_directory is None:
        try:
            os.rmdir(leaf, dir_fd=parent_fd)
        except OSError:
            pass
        return
    for name, created in reversed(tuple(created_files.items())):
        try:
            named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if named.st_dev == created.st_dev and named.st_ino == created.st_ino:
                os.unlink(name, dir_fd=directory_fd)
        except OSError:
            pass
    try:
        if os.listdir(directory_fd):
            return
        named_root = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        if (
            named_root.st_dev == created_directory.st_dev
            and named_root.st_ino == created_directory.st_ino
        ):
            os.rmdir(leaf, dir_fd=parent_fd)
    except OSError:
        pass


def _write_bundle(prepared: PreparedStarter, output_text: str) -> Path:
    output, parent, leaf = _require_new_output_root(output_text, prepared)
    files = dict(prepared.files_without_manifest)
    files["bundle-manifest.json"] = _manifest(prepared)
    if tuple(sorted(files)) != OUTPUT_FILES:
        raise StarterError("internal output inventory changed")

    current = _git_snapshot(prepared.project_root)
    if current != prepared.target_snapshot:
        raise StarterError("target repository changed before bundle creation")
    parent_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        expected_parent = os.lstat(parent)
        parent_fd = os.open(parent, parent_flags)
    except OSError as error:
        raise StarterError("output parent identity changed before creation") from error
    directory_fd: int | None = None
    directory_created = False
    created_directory: os.stat_result | None = None
    created_files: dict[str, os.stat_result] = {}
    try:
        opened_parent = os.fstat(parent_fd)
        if (
            not stat.S_ISDIR(opened_parent.st_mode)
            or opened_parent.st_dev != expected_parent.st_dev
            or opened_parent.st_ino != expected_parent.st_ino
            or opened_parent.st_uid != os.geteuid()
            or stat.S_IMODE(opened_parent.st_mode) & 0o022
        ):
            raise StarterError("output parent identity changed before creation")
        _reject_extended_acl(parent_fd, "output parent")
        try:
            os.mkdir(leaf, 0o700, dir_fd=parent_fd)
        except OSError as error:
            raise StarterError("output root could not be created exclusively") from error
        directory_created = True
        try:
            created_directory = os.stat(
                leaf,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            if not stat.S_ISDIR(created_directory.st_mode):
                raise StarterError("output root identity changed before opening")
            directory_fd = os.open(leaf, parent_flags, dir_fd=parent_fd)
            opened_directory = os.fstat(directory_fd)
            if (
                opened_directory.st_dev != created_directory.st_dev
                or opened_directory.st_ino != created_directory.st_ino
            ):
                raise StarterError("output root identity changed before opening")
            os.fchmod(directory_fd, 0o700)
            _reject_extended_acl(directory_fd, "output root")
            created_directory = os.fstat(directory_fd)
        except OSError as error:
            raise StarterError("output root could not be initialized") from error
        for name in OUTPUT_WRITE_ORDER:
            created_files[name] = _write_one(directory_fd, name, files[name])
        os.fsync(directory_fd)
        os.fsync(parent_fd)

        _revalidate_target(prepared)
        _require_named_output_root(output, created_directory)
        try:
            actual_names = tuple(sorted(os.listdir(directory_fd)))
        except OSError as error:
            raise StarterError("output inventory is unavailable") from error
        if actual_names != OUTPUT_FILES:
            raise StarterError("output inventory changed")
        for name in OUTPUT_FILES:
            created_file = created_files.get(name)
            if created_file is None:
                raise StarterError(f"output file identity changed: {name}")
            _verify_output_file(directory_fd, name, created_file, files[name])
        final_parent = os.fstat(parent_fd)
        if (
            final_parent.st_dev != expected_parent.st_dev
            or final_parent.st_ino != expected_parent.st_ino
            or final_parent.st_uid != os.geteuid()
            or stat.S_IMODE(final_parent.st_mode) & 0o022
        ):
            raise StarterError("output parent identity or trust boundary changed")
        _reject_extended_acl(parent_fd, "output parent")
        _reject_extended_acl(directory_fd, "output root")
        _require_named_output_root(output, created_directory)
        return output
    except BaseException:
        _cleanup_created_bundle(
            parent_fd,
            directory_fd,
            leaf,
            directory_created,
            created_directory,
            created_files,
        )
        raise
    finally:
        try:
            if directory_fd is not None:
                os.close(directory_fd)
        except OSError:
            pass
        try:
            os.close(parent_fd)
        except OSError:
            pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render one deterministic review-only Maven RouteContract starter",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--config",
        action=_SingleValue,
        help="absolute canonical path to the strict starter JSON",
    )
    parser.add_argument(
        "--output",
        action=_SingleValue,
        help="new absent absolute bundle root outside the target repository",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        print(
            "routecontract maven pilot starter error: Python 3.10 or newer is required",
            file=sys.stderr,
        )
        return 2
    parser = _parser()
    arguments = parser.parse_args(argv)
    if arguments.config is None or arguments.output is None:
        parser.error("--config and --output are required")
    try:
        _validate_text(arguments.config, "config path")
        config_path = Path(arguments.config)
        prepared = _prepare(config_path)
        output = _write_bundle(prepared, arguments.output)
    except StarterError as error:
        print(f"routecontract maven pilot starter error: {error}", file=sys.stderr)
        return 2
    print(
        "ROUTECONTRACT_MAVEN_PILOT_STARTER "
        f"targetCommit={prepared.target_snapshot.head} "
        f"manifestSha256={_sha256(_manifest(prepared))} "
        f"files={len(OUTPUT_FILES)} VERIFIED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
