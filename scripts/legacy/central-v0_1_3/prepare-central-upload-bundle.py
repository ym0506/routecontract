#!/usr/bin/env python3
"""Build and verify one credential-free deterministic Central upload bundle.

This program deliberately has no HTTP client, credential input, signing mode,
or publication mode.  It accepts only an already signed Gradle Maven staging
repository, an independently reviewed payload manifest, and a public-key-only
GnuPG home.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import NamedTuple, Sequence
import xml.etree.ElementTree as ET
import zipfile


SCHEMA_VERSION = 1
GROUP_ID = "io.github.ym0506.routecontract"
GROUP_PATH = PurePosixPath("io/github/ym0506/routecontract")
ARTIFACT_ID = "routecontract-shardingsphere-5.5"
CHECKSUMS = ("md5", "sha1", "sha256", "sha512")
CHECKSUM_LENGTHS = {"md5": 32, "sha1": 40, "sha256": 64, "sha512": 128}
ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
MAX_MANIFEST_BYTES = 64 * 1024
MAX_RECEIPT_BYTES = 512 * 1024
MAX_TOOL_BYTES = 2 * 1024 * 1024
MAX_STAGING_FILE_BYTES = 256 * 1024 * 1024
MAX_STAGING_BYTES = 1024 * 1024 * 1024
MAX_BUNDLE_BYTES = 1024 * 1024 * 1024
MAVEN_NAMESPACE = "http://maven.apache.org/POM/4.0.0"
_SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
_UPPER_FINGERPRINT = re.compile(r"[0-9A-F]{40}\Z")
_LOWER_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_OUTPUT_LEAF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", None)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", None)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", None)
_HAS_REQUIRED_DIR_FD = all(
    function in os.supports_dir_fd
    for function in (os.open, os.stat, os.mkdir)
)


class BundleError(RuntimeError):
    """A fail-closed staging, manifest, signature, or bundle violation."""


class PreparedStaging(NamedTuple):
    version: str
    coordinate: dict[str, str]
    coordinate_path: str
    manifest_bytes: bytes
    manifest_sha256: str
    files: dict[str, bytes]
    upload_entries: dict[str, bytes]
    entry_kinds: dict[str, str]
    excluded_entries: list[dict[str, object]]


class VerifiedBundleResult(NamedTuple):
    version: str
    bundle_path: Path
    receipt_path: Path
    bundle_sha256: str
    receipt_sha256: str


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest(payload: bytes, algorithm: str) -> str:
    if algorithm == "md5":
        value = hashlib.md5(usedforsecurity=False)
    elif algorithm == "sha1":
        value = hashlib.sha1(usedforsecurity=False)
    else:
        value = hashlib.new(algorithm)
    value.update(payload)
    return value.hexdigest()


def _metadata(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _identity(value: os.stat_result) -> tuple[int, int, int]:
    return (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode))


def _require_single_link(value: os.stat_result, label: str) -> None:
    if value.st_nlink != 1:
        raise BundleError(f"{label} must have exactly one hard link")


def _directory_flags() -> int:
    if _O_NOFOLLOW is None or _O_DIRECTORY is None or not _HAS_REQUIRED_DIR_FD:
        raise BundleError(
            "this platform lacks required O_NOFOLLOW/O_DIRECTORY/dir_fd support"
        )
    return os.O_RDONLY | _O_NOFOLLOW | _O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)


def _regular_read_flags() -> int:
    if _O_NOFOLLOW is None or _O_NONBLOCK is None:
        raise BundleError("this platform lacks required O_NOFOLLOW/O_NONBLOCK support")
    return os.O_RDONLY | _O_NOFOLLOW | _O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)


def _close_descriptor(descriptor: int, label: str) -> None:
    try:
        os.close(descriptor)
    except OSError as error:
        raise BundleError(f"could not close {label}") from error


def _open_absolute_directory(path: Path, label: str) -> tuple[int, os.stat_result]:
    _canonical_existing_path(path, label, directory=True)
    flags = _directory_flags()
    try:
        descriptor = os.open(Path(path.anchor), flags)
    except OSError as error:
        raise BundleError(f"could not open {label} root directory") from error
    try:
        for component in path.parts[1:]:
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except OSError as error:
                raise BundleError(
                    f"{label} path component must be a real directory"
                ) from error
            try:
                opened = os.fstat(child)
                named = os.stat(component, dir_fd=descriptor, follow_symlinks=False)
                if not stat.S_ISDIR(opened.st_mode) or _metadata(opened) != _metadata(named):
                    raise BundleError(f"{label} directory identity changed while opening")
                _close_descriptor(descriptor, f"{label} ancestor directory")
            except BaseException:
                try:
                    os.close(child)
                except OSError:
                    pass
                raise
            descriptor = child
        opened = os.fstat(descriptor)
        named = os.stat(path, follow_symlinks=False)
        if not stat.S_ISDIR(opened.st_mode) or _metadata(opened) != _metadata(named):
            raise BundleError(f"{label} directory identity changed while opening")
        return descriptor, opened
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _duplicate_safe_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BundleError("JSON contains a duplicate key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise BundleError(f"JSON contains a non-standard numeric constant: {value}")


def _load_json(payload: bytes, label: str, *, require_canonical: bool) -> object:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BundleError(f"{label} must be UTF-8 JSON") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_safe_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, UnicodeError) as error:
        raise BundleError(f"{label} is not valid JSON") from error
    if require_canonical and payload != _canonical_json(value):
        raise BundleError(f"{label} must use canonical sorted JSON")
    return value


def _expect_object(value: object, label: str, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise BundleError(f"{label} must be a JSON object")
    if set(value) != keys:
        raise BundleError(f"{label} has an unexpected field set")
    return value


def _canonical_existing_path(path: Path, label: str, *, directory: bool) -> Path:
    if not path.is_absolute() or path != Path(os.path.normpath(os.fspath(path))):
        raise BundleError(f"{label} must be an absolute normalized path")
    try:
        named = os.lstat(path)
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise BundleError(f"{label} is unavailable") from error
    if resolved != path:
        raise BundleError(f"{label} must use its canonical non-symlink path")
    wanted = stat.S_ISDIR(named.st_mode) if directory else stat.S_ISREG(named.st_mode)
    if not wanted:
        kind = "directory" if directory else "regular file"
        raise BundleError(f"{label} must be a non-symlink {kind}")
    return resolved


def _read_stable_regular(path: Path, label: str, maximum: int) -> bytes:
    _canonical_existing_path(path, label, directory=False)
    try:
        descriptor = os.open(path, _regular_read_flags())
    except OSError as error:
        raise BundleError(f"{label} must be a regular non-symlink file") from error
    failure: BaseException | None = None
    payload = b""
    after: os.stat_result | None = None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise BundleError(f"{label} must be a regular non-symlink file")
        _require_single_link(before, label)
        if before.st_size > maximum:
            raise BundleError(f"{label} exceeds its size limit")
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
            raise BundleError(f"{label} exceeds its size limit")
        if _metadata(before) != _metadata(after):
            raise BundleError(f"{label} changed while it was read")
    except BaseException as error:
        failure = error
    try:
        _close_descriptor(descriptor, label)
    except BundleError as error:
        if failure is None:
            failure = error
    if failure is not None:
        raise failure
    assert after is not None
    try:
        named = os.lstat(path)
        resolved_after = path.resolve(strict=True)
    except OSError as error:
        raise BundleError(f"{label} disappeared while it was read") from error
    if (
        resolved_after != path
        or not stat.S_ISREG(named.st_mode)
        or _metadata(named) != _metadata(after)
    ):
        raise BundleError(f"{label} identity changed while it was read")
    return payload


def _manifest(path: Path) -> tuple[dict[str, object], bytes, str, list[str]]:
    payload = _read_stable_regular(path, "reviewed payload manifest", MAX_MANIFEST_BYTES)
    value = _expect_object(
        _load_json(payload, "reviewed payload manifest", require_canonical=True),
        "reviewed payload manifest",
        {"schemaVersion", "coordinate", "payloads"},
    )
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != SCHEMA_VERSION:
        raise BundleError("reviewed payload manifest schemaVersion must be 1")
    coordinate = _expect_object(
        value["coordinate"],
        "reviewed payload manifest coordinate",
        {"groupId", "artifactId", "version"},
    )
    if coordinate["groupId"] != GROUP_ID or coordinate["artifactId"] != ARTIFACT_ID:
        raise BundleError("reviewed payload manifest has the wrong Maven coordinate")
    version = coordinate["version"]
    if not isinstance(version, str) or len(version) > 64:
        raise BundleError("reviewed payload manifest version must be a stable SemVer")
    match = _SEMVER.fullmatch(version)
    if match is None:
        raise BundleError("reviewed payload manifest version must be a stable SemVer")
    if tuple(int(part) for part in match.groups()) <= (0, 1, 2):
        raise BundleError("reviewed payload manifest version must be greater than 0.1.2")

    base = f"{ARTIFACT_ID}-{version}"
    names = sorted(
        (
            f"{base}.jar",
            f"{base}-sources.jar",
            f"{base}-javadoc.jar",
            f"{base}.pom",
            f"{base}.module",
        )
    )
    records = value["payloads"]
    if not isinstance(records, list) or len(records) != len(names):
        raise BundleError("reviewed payload manifest must contain exactly five payloads")
    actual_names: list[str] = []
    for index, record_value in enumerate(records):
        record = _expect_object(
            record_value,
            f"reviewed payload manifest payload {index}",
            {"name", "size", "sha256"},
        )
        name = record["name"]
        size = record["size"]
        digest = record["sha256"]
        if not isinstance(name, str):
            raise BundleError("reviewed payload manifest payload name must be text")
        if type(size) is not int or size <= 0:
            raise BundleError("reviewed payload manifest payload size must be positive")
        if not isinstance(digest, str) or _LOWER_SHA256.fullmatch(digest) is None:
            raise BundleError("reviewed payload manifest payload sha256 must be lowercase hex")
        actual_names.append(name)
    if actual_names != names:
        raise BundleError(
            "reviewed payload manifest payloads must be the exact lexicographic allowlist"
        )
    return value, payload, version, names


def _expected_inventory(version: str, payload_names: list[str]) -> tuple[set[str], set[str]]:
    coordinate_path = GROUP_PATH / ARTIFACT_ID / version
    artifact_path = GROUP_PATH / ARTIFACT_ID
    files: set[str] = set()
    for name in payload_names:
        files.add(str(coordinate_path / name))
        files.add(str(coordinate_path / f"{name}.asc"))
        for algorithm in CHECKSUMS:
            files.add(str(coordinate_path / f"{name}.{algorithm}"))
            files.add(str(coordinate_path / f"{name}.asc.{algorithm}"))
    files.add(str(artifact_path / "maven-metadata.xml"))
    for algorithm in CHECKSUMS:
        files.add(str(artifact_path / f"maven-metadata.xml.{algorithm}"))

    parts = [*GROUP_PATH.parts, ARTIFACT_ID, version]
    directories: set[str] = set()
    for length in range(1, len(parts) + 1):
        directories.add(str(PurePosixPath(*parts[:length])))
    return files, directories


def _read_regular_at(
    directory_fd: int,
    name: str,
    label: str,
    maximum: int,
    expected: tuple[int, ...],
) -> bytes:
    try:
        descriptor = os.open(name, _regular_read_flags(), dir_fd=directory_fd)
    except OSError as error:
        raise BundleError(f"{label} must remain a regular non-symlink file") from error
    failure: BaseException | None = None
    payload = b""
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or _metadata(before) != expected:
            raise BundleError(f"{label} identity changed before it was read")
        _require_single_link(before, label)
        if before.st_size > maximum:
            raise BundleError(f"{label} exceeds its size limit")
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
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if len(payload) > maximum:
            raise BundleError(f"{label} exceeds its size limit")
        if _metadata(before) != _metadata(after) or _metadata(after) != _metadata(named):
            raise BundleError(f"{label} identity changed while it was read")
    except BaseException as error:
        failure = error
    try:
        _close_descriptor(descriptor, label)
    except BundleError as error:
        if failure is None:
            failure = error
    if failure is not None:
        raise failure
    return payload


def _walk_repository(
    root_descriptor: int, *, read_files: bool
) -> tuple[
    tuple[int, ...],
    dict[str, tuple[int, ...]],
    dict[str, tuple[int, ...]],
    dict[str, bytes],
]:
    files: dict[str, tuple[int, ...]] = {}
    directories: dict[str, tuple[int, ...]] = {}
    contents: dict[str, bytes] = {}

    def visit(directory_fd: int, relative: PurePosixPath) -> None:
        parent_before = os.fstat(directory_fd)
        try:
            with os.scandir(directory_fd) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as error:
            raise BundleError("could not enumerate staging repository") from error
        for entry in entries:
            child_relative = relative / entry.name
            logical = str(child_relative)
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise BundleError("staging repository entry disappeared") from error
            if stat.S_ISLNK(metadata.st_mode):
                raise BundleError(f"staging repository contains a symbolic link: {logical}")
            if stat.S_ISDIR(metadata.st_mode):
                try:
                    child_descriptor = os.open(
                        entry.name, _directory_flags(), dir_fd=directory_fd
                    )
                except OSError as error:
                    raise BundleError(
                        f"staging repository directory could not be opened: {logical}"
                    ) from error
                child_failure: BaseException | None = None
                try:
                    opened = os.fstat(child_descriptor)
                    named = os.stat(
                        entry.name, dir_fd=directory_fd, follow_symlinks=False
                    )
                    if (
                        not stat.S_ISDIR(opened.st_mode)
                        or _metadata(metadata) != _metadata(opened)
                        or _metadata(opened) != _metadata(named)
                    ):
                        raise BundleError(
                            f"staging repository directory identity changed: {logical}"
                        )
                    directories[logical] = _metadata(opened)
                    visit(child_descriptor, child_relative)
                    named_after = os.stat(
                        entry.name, dir_fd=directory_fd, follow_symlinks=False
                    )
                    if _metadata(opened) != _metadata(named_after):
                        raise BundleError(
                            f"staging repository directory identity changed: {logical}"
                        )
                except BaseException as error:
                    child_failure = error
                try:
                    _close_descriptor(
                        child_descriptor, f"staging repository directory {logical}"
                    )
                except BundleError as error:
                    if child_failure is None:
                        child_failure = error
                if child_failure is not None:
                    raise child_failure
            elif stat.S_ISREG(metadata.st_mode):
                _require_single_link(metadata, f"staging file {logical}")
                files[logical] = _metadata(metadata)
                if read_files:
                    contents[logical] = _read_regular_at(
                        directory_fd,
                        entry.name,
                        f"staging file {logical}",
                        MAX_STAGING_FILE_BYTES,
                        files[logical],
                    )
            else:
                raise BundleError(f"staging repository contains a special file: {logical}")
        parent_after = os.fstat(directory_fd)
        if _metadata(parent_before) != _metadata(parent_after):
            label = str(relative) if relative.parts else "."
            raise BundleError(
                f"staging repository directory identity changed: {label}"
            )

    root_before = os.fstat(root_descriptor)
    visit(root_descriptor, PurePosixPath())
    root_after = os.fstat(root_descriptor)
    if _metadata(root_before) != _metadata(root_after):
        raise BundleError("staging repository root identity changed")
    return _metadata(root_after), files, directories, contents


def _read_repository(
    repository: Path, expected_files: set[str], expected_directories: set[str]
) -> dict[str, bytes]:
    root_descriptor, opened_root = _open_absolute_directory(
        repository, "staging repository"
    )
    failure: BaseException | None = None
    contents: dict[str, bytes] = {}
    try:
        first_root, first_files, first_directories, _ = _walk_repository(
            root_descriptor, read_files=False
        )
        if set(first_files) != expected_files or set(first_directories) != expected_directories:
            raise BundleError(
                "staging inventory mismatch: expected one exact Maven coordinate"
            )
        if sum(metadata[6] for metadata in first_files.values()) > MAX_STAGING_BYTES:
            raise BundleError("staging repository exceeds its total size limit")
        read_root, read_files, read_directories, contents = _walk_repository(
            root_descriptor, read_files=True
        )
        final_root, final_files, final_directories, _ = _walk_repository(
            root_descriptor, read_files=False
        )
        first_snapshot = (first_root, first_files, first_directories)
        if (
            (read_root, read_files, read_directories) != first_snapshot
            or (final_root, final_files, final_directories) != first_snapshot
        ):
            raise BundleError("staging repository changed while it was read")
        named_root = os.stat(repository, follow_symlinks=False)
        if (
            _metadata(opened_root) != _metadata(os.fstat(root_descriptor))
            or _metadata(opened_root) != _metadata(named_root)
        ):
            raise BundleError("staging repository root identity changed")
    except BaseException as error:
        failure = error
    try:
        _close_descriptor(root_descriptor, "staging repository root")
    except BundleError as error:
        if failure is None:
            failure = error
    if failure is not None:
        raise failure
    return contents


def _verify_checksum(contents: dict[str, bytes], source: str, sidecar: str, algorithm: str) -> None:
    expected = _digest(contents[source], algorithm).encode("ascii")
    actual = contents[sidecar]
    if len(actual) != CHECKSUM_LENGTHS[algorithm] or actual != expected:
        raise BundleError(f"checksum mismatch for staged file: {source}")


def _verify_xml_coordinates(contents: dict[str, bytes], version: str) -> None:
    coordinate_path = GROUP_PATH / ARTIFACT_ID / version
    base = f"{ARTIFACT_ID}-{version}"
    pom_name = str(coordinate_path / f"{base}.pom")
    pom = contents[pom_name]
    if b"<!DOCTYPE" in pom.upper() or b"<!ENTITY" in pom.upper():
        raise BundleError("staged POM must not contain a document type or entity")
    try:
        root = ET.fromstring(pom)
    except ET.ParseError as error:
        raise BundleError("staged POM is not well-formed XML") from error
    prefix = f"{{{MAVEN_NAMESPACE}}}"
    if root.tag != f"{prefix}project":
        raise BundleError("staged POM has the wrong Maven namespace")
    expected = {
        "groupId": GROUP_ID,
        "artifactId": ARTIFACT_ID,
        "version": version,
    }
    for name, wanted in expected.items():
        nodes = root.findall(f"{prefix}{name}")
        if len(nodes) != 1 or nodes[0].text != wanted:
            raise BundleError(f"staged POM {name} does not match the coordinate")

    metadata_name = str(GROUP_PATH / ARTIFACT_ID / "maven-metadata.xml")
    metadata = contents[metadata_name]
    if b"<!DOCTYPE" in metadata.upper() or b"<!ENTITY" in metadata.upper():
        raise BundleError("staged Maven metadata must not contain a document type or entity")
    try:
        metadata_root = ET.fromstring(metadata)
    except ET.ParseError as error:
        raise BundleError("staged Maven metadata is not well-formed XML") from error
    if metadata_root.tag != "metadata":
        raise BundleError("staged Maven metadata has the wrong root element")
    checks = {
        "groupId": GROUP_ID,
        "artifactId": ARTIFACT_ID,
        "versioning/latest": version,
        "versioning/release": version,
    }
    for xpath, wanted in checks.items():
        nodes = metadata_root.findall(xpath)
        if len(nodes) != 1 or nodes[0].text != wanted:
            raise BundleError(f"staged Maven metadata {xpath} does not match the coordinate")
    versions = metadata_root.findall("versioning/versions/version")
    if len(versions) != 1 or versions[0].text != version:
        raise BundleError("staged Maven metadata must contain only the reviewed version")


def _verify_module_metadata(contents: dict[str, bytes], version: str) -> None:
    coordinate_path = GROUP_PATH / ARTIFACT_ID / version
    name = str(coordinate_path / f"{ARTIFACT_ID}-{version}.module")
    value = _load_json(contents[name], "staged Gradle Module Metadata", require_canonical=False)
    if not isinstance(value, dict):
        raise BundleError("staged Gradle Module Metadata must be a JSON object")
    component = value.get("component")
    if not isinstance(component, dict):
        raise BundleError("staged Gradle Module Metadata lacks a component object")
    expected = {"group": GROUP_ID, "module": ARTIFACT_ID, "version": version}
    for key, wanted in expected.items():
        if component.get(key) != wanted:
            raise BundleError(
                f"staged Gradle Module Metadata component.{key} does not match"
            )


def _gpg_command(
    home: Path,
    arguments: list[str],
    *,
    input_payload: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    executable = shutil.which("gpg")
    if executable is None:
        raise BundleError("GnuPG is required to verify staged signatures")
    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    try:
        command = [
            executable,
            "--no-options",
            "--homedir",
            os.fspath(home),
            "--batch",
            "--no-auto-key-retrieve",
            *arguments,
        ]
        if input_payload is None:
            return subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                check=False,
            )
        return subprocess.run(
            command,
            input=input_payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            check=False,
        )
    except OSError as error:
        raise BundleError("could not execute GnuPG") from error


def _inspect_secret_material_names(home_descriptor: int) -> None:
    try:
        secring = os.stat(
            "secring.gpg", dir_fd=home_descriptor, follow_symlinks=False
        )
    except FileNotFoundError:
        secring = None
    except OSError as error:
        raise BundleError("could not inspect public GnuPG home") from error
    if secring is not None:
        raise BundleError("public GnuPG home contains secret-key material")

    try:
        private_named = os.stat(
            "private-keys-v1.d", dir_fd=home_descriptor, follow_symlinks=False
        )
    except FileNotFoundError:
        return
    except OSError as error:
        raise BundleError("could not inspect public GnuPG home") from error
    if not stat.S_ISDIR(private_named.st_mode):
        raise BundleError("public GnuPG home contains secret-key material")
    try:
        private_descriptor = os.open(
            "private-keys-v1.d", _directory_flags(), dir_fd=home_descriptor
        )
    except OSError as error:
        raise BundleError("public GnuPG home contains secret-key material") from error
    failure: BaseException | None = None
    try:
        opened = os.fstat(private_descriptor)
        named = os.stat(
            "private-keys-v1.d", dir_fd=home_descriptor, follow_symlinks=False
        )
        if (
            _metadata(private_named) != _metadata(opened)
            or _metadata(opened) != _metadata(named)
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) & 0o077
        ):
            raise BundleError("public GnuPG home contains secret-key material")
        with os.scandir(private_descriptor) as entries:
            if any(entries):
                raise BundleError("public GnuPG home contains secret-key material")
    except BaseException as error:
        failure = error
    try:
        _close_descriptor(private_descriptor, "public GnuPG private-key directory")
    except BundleError as error:
        if failure is None:
            failure = error
    if failure is not None:
        raise failure


def _verify_public_gpg_home(home: Path, expected_fingerprint: str) -> bytes:
    home_descriptor, opened_home = _open_absolute_directory(
        home, "public GnuPG home"
    )
    failure: BaseException | None = None
    exported_public_key: bytes | None = None
    try:
        if (
            opened_home.st_uid != os.geteuid()
            or stat.S_IMODE(opened_home.st_mode) & 0o077
        ):
            raise BundleError("public GnuPG home must be private to the current user")
        _inspect_secret_material_names(home_descriptor)

        secret_listing = _gpg_command(
            home, ["--with-colons", "--fixed-list-mode", "--list-secret-keys"]
        )
        if any(line.startswith(b"sec:") for line in secret_listing.stdout.splitlines()):
            raise BundleError("public GnuPG home contains secret-key material")
        if secret_listing.returncode not in (0, 2):
            raise BundleError("could not inspect public GnuPG home for secret keys")

        public_listing = _gpg_command(
            home,
            [
                "--with-colons",
                "--fixed-list-mode",
                "--fingerprint",
                "--list-keys",
            ],
        )
        if public_listing.returncode != 0:
            raise BundleError("could not list the public verification key")
        lines = [
            line.decode("utf-8", "strict").split(":")
            for line in public_listing.stdout.splitlines()
        ]
        primary_records = [line for line in lines if line[0] == "pub"]
        primary_fingerprints: list[str] = []
        current_primary = False
        for line in lines:
            if line[0] == "pub":
                current_primary = True
            elif line[0] == "sub":
                current_primary = False
            elif line[0] == "fpr" and current_primary:
                primary_fingerprints.append(line[9])
                current_primary = False
        if len(primary_records) != 1 or primary_fingerprints != [expected_fingerprint]:
            raise BundleError(
                "public GnuPG home must contain exactly the expected primary key"
            )
        primary = primary_records[0]
        validity = primary[1]
        capabilities = primary[11] if len(primary) > 11 else ""
        if validity in {"e", "r"} or "s" not in capabilities.lower():
            raise BundleError(
                "expected public primary key must be current and signing-capable"
            )
        exported = _gpg_command(home, ["--export", expected_fingerprint])
        if exported.returncode != 0 or not exported.stdout:
            raise BundleError("could not export the public verification key")
        exported_public_key = exported.stdout
        _inspect_secret_material_names(home_descriptor)
        named_home = os.stat(home, follow_symlinks=False)
        if (
            _identity(opened_home) != _identity(os.fstat(home_descriptor))
            or _identity(opened_home) != _identity(named_home)
        ):
            raise BundleError("public GnuPG home identity changed during verification")
    except BaseException as error:
        failure = error
    try:
        _close_descriptor(home_descriptor, "public GnuPG home")
    except BundleError as error:
        if failure is None:
            failure = error
    if failure is not None:
        raise failure
    if exported_public_key is None:
        raise BundleError("public verification key was not captured")
    return exported_public_key


def _verify_signature(
    signature: bytes,
    payload: bytes,
    public_gpg_home: Path,
    expected_fingerprint: str,
    label: str,
) -> None:
    if not signature.startswith(b"-----BEGIN PGP SIGNATURE-----") or not signature.rstrip().endswith(
        b"-----END PGP SIGNATURE-----"
    ):
        raise BundleError(f"staged signature is not ASCII-armored: {label}")
    with tempfile.TemporaryDirectory(prefix="routecontract-central-verify-") as temporary:
        temporary_path = Path(temporary)
        payload_path = temporary_path / "payload"
        signature_path = temporary_path / "signature.asc"
        payload_path.write_bytes(payload)
        signature_path.write_bytes(signature)
        result = _gpg_command(
            public_gpg_home,
            [
                "--status-fd",
                "1",
                "--verify",
                os.fspath(signature_path),
                os.fspath(payload_path),
            ],
        )
    status_lines = [
        line[len(b"[GNUPG:] ") :].decode("utf-8", "replace")
        for line in result.stdout.splitlines()
        if line.startswith(b"[GNUPG:] ")
    ]
    forbidden = ("BADSIG ", "ERRSIG ", "EXPSIG ", "EXPKEYSIG ", "REVKEYSIG ")
    if result.returncode != 0 or any(line.startswith(forbidden) for line in status_lines):
        raise BundleError(f"detached signature verification failed: {label}")
    valid = [line.split() for line in status_lines if line.startswith("VALIDSIG ")]
    if len(valid) != 1 or len(valid[0]) < 11:
        raise BundleError(f"detached signature produced no unique VALIDSIG: {label}")
    record = valid[0]
    if record[1] != expected_fingerprint or record[10] != expected_fingerprint:
        raise BundleError(f"detached signature did not use the expected primary key: {label}")
    if record[8] != "9":
        raise BundleError(f"detached signature did not use SHA-384: {label}")


def _prepare_staging(
    repository: Path,
    reviewed_manifest_path: Path,
    public_gpg_home: Path,
    expected_primary_fingerprint: str,
) -> PreparedStaging:
    _canonical_existing_path(repository, "staging repository", directory=True)
    if _UPPER_FINGERPRINT.fullmatch(expected_primary_fingerprint) is None:
        raise BundleError("expected primary fingerprint must be 40 uppercase hex characters")
    manifest_value, manifest_bytes, version, payload_names = _manifest(
        reviewed_manifest_path
    )
    expected_files, expected_directories = _expected_inventory(version, payload_names)
    contents = _read_repository(repository, expected_files, expected_directories)
    verified_public_key = _verify_public_gpg_home(
        public_gpg_home, expected_primary_fingerprint
    )

    coordinate_path = GROUP_PATH / ARTIFACT_ID / version
    reviewed_records = manifest_value["payloads"]
    assert isinstance(reviewed_records, list)
    for record_value in reviewed_records:
        assert isinstance(record_value, dict)
        name = record_value["name"]
        assert isinstance(name, str)
        staged = contents[str(coordinate_path / name)]
        if record_value["size"] != len(staged) or record_value["sha256"] != _sha256(staged):
            raise BundleError(f"reviewed payload mismatch for staged file: {name}")

    for name in payload_names:
        payload_path = str(coordinate_path / name)
        signature_path = f"{payload_path}.asc"
        for source in (payload_path, signature_path):
            for algorithm in CHECKSUMS:
                _verify_checksum(contents, source, f"{source}.{algorithm}", algorithm)
    metadata_path = str(GROUP_PATH / ARTIFACT_ID / "maven-metadata.xml")
    for algorithm in CHECKSUMS:
        _verify_checksum(contents, metadata_path, f"{metadata_path}.{algorithm}", algorithm)

    _verify_xml_coordinates(contents, version)
    _verify_module_metadata(contents, version)
    with tempfile.TemporaryDirectory(
        prefix="rc-central-key-", dir="/tmp"
    ) as temporary_public_home:
        snapshot_home = Path(temporary_public_home).resolve()
        snapshot_home.chmod(0o700)
        imported = _gpg_command(
            snapshot_home,
            ["--import"],
            input_payload=verified_public_key,
        )
        if imported.returncode != 0:
            raise BundleError("could not create the public-key verification snapshot")
        snapshot_public_key = _verify_public_gpg_home(
            snapshot_home, expected_primary_fingerprint
        )
        if snapshot_public_key != verified_public_key:
            raise BundleError("public-key verification snapshot changed key bytes")
        for name in payload_names:
            payload_path = str(coordinate_path / name)
            _verify_signature(
                contents[f"{payload_path}.asc"],
                contents[payload_path],
                snapshot_home,
                expected_primary_fingerprint,
                name,
            )

    upload_entries: dict[str, bytes] = {}
    entry_kinds: dict[str, str] = {}
    excluded_paths: set[str] = set()
    for name in payload_names:
        payload_path = str(coordinate_path / name)
        signature_path = f"{payload_path}.asc"
        upload_entries[payload_path] = contents[payload_path]
        entry_kinds[payload_path] = "payload"
        upload_entries[signature_path] = contents[signature_path]
        entry_kinds[signature_path] = "signature"
        for algorithm in CHECKSUMS:
            checksum_path = f"{payload_path}.{algorithm}"
            upload_entries[checksum_path] = contents[checksum_path]
            entry_kinds[checksum_path] = "payloadChecksum"
            excluded_paths.add(f"{signature_path}.{algorithm}")
    excluded_paths.add(metadata_path)
    for algorithm in CHECKSUMS:
        excluded_paths.add(f"{metadata_path}.{algorithm}")
    excluded_entries = [
        {
            "path": path,
            "size": len(contents[path]),
            "sha256": _sha256(contents[path]),
        }
        for path in sorted(excluded_paths)
    ]
    if len(upload_entries) != 30 or len(excluded_entries) != 25:
        raise BundleError("internal staging partition did not produce 30 upload and 25 excluded files")
    return PreparedStaging(
        version=version,
        coordinate={
            "groupId": GROUP_ID,
            "artifactId": ARTIFACT_ID,
            "version": version,
        },
        coordinate_path=str(coordinate_path),
        manifest_bytes=manifest_bytes,
        manifest_sha256=_sha256(manifest_bytes),
        files=contents,
        upload_entries=upload_entries,
        entry_kinds=entry_kinds,
        excluded_entries=excluded_entries,
    )


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(
        output, mode="w", compression=zipfile.ZIP_STORED, allowZip64=True
    ) as archive:
        archive.comment = b""
        for name in sorted(entries):
            info = zipfile.ZipInfo(filename=name, date_time=ZIP_DATE_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.create_version = 20
            info.extract_version = 20
            info.flag_bits = 0
            info.internal_attr = 0
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.extra = b""
            info.comment = b""
            archive.writestr(info, entries[name])
    payload = output.getvalue()
    if len(payload) > MAX_BUNDLE_BYTES:
        raise BundleError("Central upload bundle exceeds its size limit")
    return payload


def _tool_binding() -> dict[str, object]:
    tool = _read_stable_regular(Path(__file__).resolve(), "bundle tool", MAX_TOOL_BYTES)
    return {"name": Path(__file__).name, "sha256": _sha256(tool)}


def _receipt(
    prepared: PreparedStaging,
    bundle_name: str,
    bundle: bytes,
    expected_primary_fingerprint: str,
) -> dict[str, object]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "routecontract-central-upload-bundle-receipt",
        "result": "VERIFIED",
        "scope": "credential-free-local-bundle-only",
        "coordinate": {
            **prepared.coordinate,
            "path": prepared.coordinate_path,
        },
        "reviewedPayloadManifest": {
            "byteCount": len(prepared.manifest_bytes),
            "sha256": prepared.manifest_sha256,
        },
        "tool": _tool_binding(),
        "signaturePolicy": {
            "detachedSignatures": 5,
            "digest": "SHA384",
            "primaryFingerprint": expected_primary_fingerprint,
        },
        "zipProfile": {
            "archiveComment": False,
            "compression": "stored",
            "directoryEntries": False,
            "entryComment": False,
            "entryExtraFields": False,
            "entryMode": "0644",
            "entryOrder": "lexicographic",
            "timestamp": "1980-01-01T00:00:00Z",
        },
        "excludedStagingEntries": prepared.excluded_entries,
        "bundle": {
            "name": bundle_name,
            "byteCount": len(bundle),
            "sha256": _sha256(bundle),
            "entryCount": len(prepared.upload_entries),
            "entries": [
                {
                    "path": name,
                    "kind": prepared.entry_kinds[name],
                    "size": len(prepared.upload_entries[name]),
                    "sha256": _sha256(prepared.upload_entries[name]),
                }
                for name in sorted(prepared.upload_entries)
            ],
        },
        "claims": {
            "availabilityClaim": False,
            "credentialInput": False,
            "networkPublication": False,
            "portalUpload": False,
            "portalValidation": False,
            "publicReadback": False,
            "publishAction": False,
        },
    }


def _verify_zip(bundle: bytes, prepared: PreparedStaging) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(bundle), mode="r") as archive:
            if archive.comment != b"":
                raise BundleError("bundle ZIP has an archive comment")
            infos = archive.infolist()
            expected_names = sorted(prepared.upload_entries)
            if [info.filename for info in infos] != expected_names or len(infos) != 30:
                raise BundleError("bundle ZIP inventory or ordering mismatch")
            for info in infos:
                if info.is_dir() or PurePosixPath(info.filename).is_absolute():
                    raise BundleError("bundle ZIP contains a directory or absolute path")
                if (
                    info.compress_type != zipfile.ZIP_STORED
                    or info.date_time != ZIP_DATE_TIME
                    or info.create_system != 3
                    or info.create_version != 20
                    or info.extract_version != 20
                    or info.flag_bits != 0
                    or info.internal_attr != 0
                    or info.external_attr >> 16 != (stat.S_IFREG | 0o644)
                    or info.extra != b""
                    or info.comment != b""
                ):
                    raise BundleError(f"bundle ZIP entry metadata mismatch: {info.filename}")
                expected = prepared.upload_entries[info.filename]
                if info.file_size != len(expected) or info.compress_size != len(expected):
                    raise BundleError(f"bundle ZIP entry size mismatch: {info.filename}")
                if archive.read(info) != expected:
                    raise BundleError(f"bundle ZIP entry bytes mismatch: {info.filename}")
    except (zipfile.BadZipFile, EOFError, OSError) as error:
        raise BundleError("bundle is not a valid ZIP archive") from error
    if bundle != _zip_bytes(prepared.upload_entries):
        raise BundleError("bundle ZIP is not the exact canonical encoding")


def _validate_output(output: Path, forbidden_roots: Sequence[Path]) -> tuple[Path, Path]:
    if not output.is_absolute() or output != Path(os.path.normpath(os.fspath(output))):
        raise BundleError("output directory must be an absolute normalized path")
    if _SAFE_OUTPUT_LEAF.fullmatch(output.name) is None:
        raise BundleError("output directory leaf must be one safe path segment")
    if os.path.lexists(output):
        raise BundleError("output directory must be a new absent path")
    parent = _canonical_existing_path(output.parent, "output parent", directory=True)
    metadata = os.stat(parent, follow_symlinks=False)
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o022:
        raise BundleError("output parent must be owned by the current user and not writable by others")
    for root in forbidden_roots:
        if output.is_relative_to(root):
            raise BundleError("output directory must be outside protected input directories")
    return output, parent


def _write_file(directory_fd: int, name: str, payload: bytes) -> os.stat_result:
    if _O_NOFOLLOW is None or not _HAS_REQUIRED_DIR_FD:
        raise BundleError("this platform lacks required safe output-file support")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | _O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
    except OSError as error:
        raise BundleError(f"could not create output file: {name}") from error
    failure: BaseException | None = None
    created: os.stat_result | None = None
    final: os.stat_result | None = None
    try:
        created = os.fstat(descriptor)
        if not stat.S_ISREG(created.st_mode):
            raise BundleError(f"created output is not a regular file: {name}")
        _require_single_link(created, f"output file {name}")
        os.fchmod(descriptor, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise BundleError(f"output write made no progress: {name}")
            view = view[written:]
        os.fsync(descriptor)
        final = os.fstat(descriptor)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            _identity(created) != _identity(final)
            or _metadata(final) != _metadata(named)
            or not stat.S_ISREG(final.st_mode)
            or final.st_uid != os.geteuid()
            or stat.S_IMODE(final.st_mode) != 0o600
        ):
            raise BundleError(f"output file identity or mode changed: {name}")
        _require_single_link(final, f"output file {name}")
    except BaseException as error:
        failure = error
    try:
        _close_descriptor(descriptor, f"output file {name}")
    except BundleError as error:
        if failure is None:
            failure = error
    if failure is not None:
        raise failure
    if final is None:
        raise BundleError(f"output file did not reach a verified state: {name}")
    return final


def _read_output_file(
    directory_fd: int,
    name: str,
    maximum: int,
    expected: os.stat_result,
) -> bytes:
    try:
        descriptor = os.open(name, _regular_read_flags(), dir_fd=directory_fd)
    except OSError as error:
        raise BundleError(f"could not reopen output file: {name}") from error
    failure: BaseException | None = None
    payload = b""
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or _identity(before) != _identity(expected)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_size > maximum
        ):
            raise BundleError(f"output file has an invalid type or size: {name}")
        _require_single_link(before, f"output file {name}")
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
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            len(payload) > maximum
            or _metadata(before) != _metadata(after)
            or _metadata(after) != _metadata(named)
        ):
            raise BundleError(f"output file identity changed during readback: {name}")
    except BaseException as error:
        failure = error
    try:
        _close_descriptor(descriptor, f"output file readback {name}")
    except BundleError as error:
        if failure is None:
            failure = error
    if failure is not None:
        raise failure
    return payload


def _write_outputs(
    output: Path,
    bundle_name: str,
    bundle: bytes,
    receipt_name: str,
    receipt: bytes,
) -> None:
    created: dict[str, os.stat_result] = {}
    parent_descriptor: int | None = None
    output_descriptor: int | None = None
    parent_identity: os.stat_result | None = None
    output_identity: os.stat_result | None = None
    output_was_created = False
    failure: BaseException | None = None
    try:
        parent_descriptor, parent_identity = _open_absolute_directory(
            output.parent, "output parent"
        )
        if (
            parent_identity.st_uid != os.geteuid()
            or stat.S_IMODE(parent_identity.st_mode) & 0o022
        ):
            raise BundleError(
                "output parent must be owned by the current user and not writable by others"
            )
        os.mkdir(output.name, mode=0o700, dir_fd=parent_descriptor)
        output_was_created = True
        try:
            output_descriptor = os.open(
                output.name,
                _directory_flags(),
                dir_fd=parent_descriptor,
            )
        except OSError as error:
            raise BundleError(
                "output directory identity changed during creation"
            ) from error
        output_named = os.stat(
            output.name, dir_fd=parent_descriptor, follow_symlinks=False
        )
        opened_output = os.fstat(output_descriptor)
        if (
            not stat.S_ISDIR(output_named.st_mode)
            or _metadata(opened_output) != _metadata(output_named)
        ):
            raise BundleError("output directory identity changed during creation")
        output_identity = opened_output
        os.fchmod(output_descriptor, 0o700)
        private_output = os.fstat(output_descriptor)
        if (
            _identity(private_output) != _identity(output_identity)
            or private_output.st_uid != os.geteuid()
            or stat.S_IMODE(private_output.st_mode) != 0o700
        ):
            raise BundleError("output directory owner or mode is not private")
        for name, payload in ((bundle_name, bundle), (receipt_name, receipt)):
            created[name] = _write_file(output_descriptor, name, payload)
        if (
            _read_output_file(
                output_descriptor,
                bundle_name,
                MAX_BUNDLE_BYTES,
                created[bundle_name],
            )
            != bundle
        ):
            raise BundleError("written bundle bytes changed during readback")
        if (
            _read_output_file(
                output_descriptor,
                receipt_name,
                MAX_RECEIPT_BYTES,
                created[receipt_name],
            )
            != receipt
        ):
            raise BundleError("written receipt bytes changed during readback")
        for name, expected in created.items():
            current = os.stat(
                name, dir_fd=output_descriptor, follow_symlinks=False
            )
            if (
                _metadata(current) != _metadata(expected)
                or current.st_uid != os.geteuid()
                or stat.S_IMODE(current.st_mode) != 0o600
            ):
                raise BundleError(f"output file identity or mode changed: {name}")
            _require_single_link(current, f"output file {name}")
        parent_after = os.stat(output.parent, follow_symlinks=False)
        output_after = os.stat(
            output.name, dir_fd=parent_descriptor, follow_symlinks=False
        )
        opened_parent_after = os.fstat(parent_descriptor)
        if (
            _metadata(opened_parent_after) != _metadata(parent_after)
            or opened_parent_after.st_uid != os.geteuid()
            or stat.S_IMODE(opened_parent_after.st_mode) & 0o022
        ):
            raise BundleError("output parent identity changed during creation")
        if (
            _metadata(os.fstat(output_descriptor)) != _metadata(output_after)
            or _identity(output_after) != _identity(output_identity)
            or output_after.st_uid != os.geteuid()
            or stat.S_IMODE(output_after.st_mode) != 0o700
        ):
            raise BundleError("output directory identity changed during creation")
        os.fsync(output_descriptor)
        os.fsync(parent_descriptor)
    except BaseException as error:
        failure = error

    if output_descriptor is not None:
        try:
            _close_descriptor(output_descriptor, "output directory")
        except BundleError as error:
            if failure is None:
                failure = error
        output_descriptor = None

    if parent_descriptor is not None:
        try:
            _close_descriptor(parent_descriptor, "output parent")
        except BundleError as error:
            if failure is None:
                failure = error
        parent_descriptor = None

    if failure is not None:
        if isinstance(failure, OSError):
            message = "output transaction failed"
        else:
            message = str(failure)
        if output_was_created:
            message += (
                "; partial output may remain at the requested path; "
                "failure handling performed no rename or deletion"
            )
        raise BundleError(message) from failure


def build_bundle(
    *,
    repository: Path,
    reviewed_manifest_path: Path,
    public_gpg_home: Path,
    expected_primary_fingerprint: str,
    output_directory: Path,
) -> VerifiedBundleResult:
    repository = Path(repository)
    reviewed_manifest_path = Path(reviewed_manifest_path)
    public_gpg_home = Path(public_gpg_home)
    output_directory = Path(output_directory)
    _canonical_existing_path(repository, "staging repository", directory=True)
    _canonical_existing_path(reviewed_manifest_path, "reviewed payload manifest", directory=False)
    _canonical_existing_path(public_gpg_home, "public GnuPG home", directory=True)
    _validate_output(output_directory, (repository, public_gpg_home))
    prepared = _prepare_staging(
        repository,
        reviewed_manifest_path,
        public_gpg_home,
        expected_primary_fingerprint,
    )
    bundle_name = f"{ARTIFACT_ID}-{prepared.version}-central-upload.zip"
    receipt_name = f"{ARTIFACT_ID}-{prepared.version}-central-upload-receipt.json"
    bundle = _zip_bytes(prepared.upload_entries)
    receipt_value = _receipt(
        prepared, bundle_name, bundle, expected_primary_fingerprint
    )
    receipt = _canonical_json(receipt_value)
    _verify_zip(bundle, prepared)
    _write_outputs(output_directory, bundle_name, bundle, receipt_name, receipt)
    bundle_path = output_directory / bundle_name
    receipt_path = output_directory / receipt_name
    return VerifiedBundleResult(
        version=prepared.version,
        bundle_path=bundle_path,
        receipt_path=receipt_path,
        bundle_sha256=_sha256(bundle),
        receipt_sha256=_sha256(receipt),
    )


def _receipt_claims(value: dict[str, object]) -> None:
    claims = value.get("claims")
    expected_keys = {
        "availabilityClaim",
        "credentialInput",
        "networkPublication",
        "portalUpload",
        "portalValidation",
        "publicReadback",
        "publishAction",
    }
    if not isinstance(claims, dict) or set(claims) != expected_keys:
        raise BundleError("receipt claims have an unexpected field set")
    for key in sorted(expected_keys):
        if claims[key] is not False:
            raise BundleError(f"receipt claims.{key} must be false")


def verify_bundle(
    *,
    repository: Path,
    bundle_path: Path,
    receipt_path: Path,
    reviewed_manifest_path: Path,
    public_gpg_home: Path,
    expected_primary_fingerprint: str,
) -> VerifiedBundleResult:
    repository = Path(repository)
    bundle_path = Path(bundle_path)
    receipt_path = Path(receipt_path)
    reviewed_manifest_path = Path(reviewed_manifest_path)
    public_gpg_home = Path(public_gpg_home)
    prepared = _prepare_staging(
        repository,
        reviewed_manifest_path,
        public_gpg_home,
        expected_primary_fingerprint,
    )
    receipt_bytes = _read_stable_regular(receipt_path, "bundle receipt", MAX_RECEIPT_BYTES)
    receipt_value = _expect_object(
        _load_json(receipt_bytes, "bundle receipt", require_canonical=True),
        "bundle receipt",
        {
            "schemaVersion",
            "kind",
            "result",
            "scope",
            "coordinate",
            "reviewedPayloadManifest",
            "tool",
            "signaturePolicy",
            "zipProfile",
            "excludedStagingEntries",
            "bundle",
            "claims",
        },
    )
    _receipt_claims(receipt_value)
    bundle_record = receipt_value.get("bundle")
    if not isinstance(bundle_record, dict):
        raise BundleError("receipt bundle must be an object")
    recorded_sha256 = bundle_record.get("sha256")
    if not isinstance(recorded_sha256, str) or _LOWER_SHA256.fullmatch(recorded_sha256) is None:
        raise BundleError("receipt bundle.sha256 must be lowercase hex")
    bundle = _read_stable_regular(bundle_path, "Central upload bundle", MAX_BUNDLE_BYTES)
    if _sha256(bundle) != recorded_sha256:
        raise BundleError("bundle SHA-256 mismatch against the receipt")
    if bundle_record.get("byteCount") != len(bundle):
        raise BundleError("bundle byte count mismatch against the receipt")
    expected_name = f"{ARTIFACT_ID}-{prepared.version}-central-upload.zip"
    if bundle_path.name != expected_name or bundle_record.get("name") != expected_name:
        raise BundleError("bundle filename mismatch")
    expected_receipt_name = (
        f"{ARTIFACT_ID}-{prepared.version}-central-upload-receipt.json"
    )
    if receipt_path.name != expected_receipt_name:
        raise BundleError("bundle receipt filename mismatch")
    _verify_zip(bundle, prepared)
    expected_receipt = _receipt(
        prepared, expected_name, bundle, expected_primary_fingerprint
    )
    if receipt_value != expected_receipt:
        raise BundleError("bundle receipt does not match the verified inputs and tool")
    return VerifiedBundleResult(
        version=prepared.version,
        bundle_path=bundle_path,
        receipt_path=receipt_path,
        bundle_sha256=_sha256(bundle),
        receipt_sha256=_sha256(receipt_bytes),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or verify one credential-free RouteContract Central upload bundle",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "verify"):
        subparser = subparsers.add_parser(command, allow_abbrev=False)
        subparser.add_argument("--repository", required=True, type=Path)
        subparser.add_argument("--reviewed-payload-manifest", required=True, type=Path)
        subparser.add_argument("--public-gpg-home", required=True, type=Path)
        subparser.add_argument("--expected-primary-fingerprint", required=True)
        if command == "build":
            subparser.add_argument("--output-directory", required=True, type=Path)
        else:
            subparser.add_argument("--bundle", required=True, type=Path)
            subparser.add_argument("--receipt", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        print("routecontract Central bundle error: Python 3.10 or newer is required", file=sys.stderr)
        return 2
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "build":
            result = build_bundle(
                repository=arguments.repository,
                reviewed_manifest_path=arguments.reviewed_payload_manifest,
                public_gpg_home=arguments.public_gpg_home,
                expected_primary_fingerprint=arguments.expected_primary_fingerprint,
                output_directory=arguments.output_directory,
            )
            marker = "ROUTECONTRACT_CENTRAL_BUNDLE_BUILT"
        else:
            result = verify_bundle(
                repository=arguments.repository,
                bundle_path=arguments.bundle,
                receipt_path=arguments.receipt,
                reviewed_manifest_path=arguments.reviewed_payload_manifest,
                public_gpg_home=arguments.public_gpg_home,
                expected_primary_fingerprint=arguments.expected_primary_fingerprint,
            )
            marker = "ROUTECONTRACT_CENTRAL_BUNDLE_VERIFIED"
    except (BundleError, OSError) as error:
        print(f"routecontract Central bundle error: {error}", file=sys.stderr)
        return 2
    print(
        f"{marker} coordinate={GROUP_ID}:{ARTIFACT_ID}:{result.version} entries=30 "
        f"bundleSha256={result.bundle_sha256} "
        f"receiptSha256={result.receipt_sha256} VERIFIED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
