#!/usr/bin/env python3
"""Run the reviewed external Maven pilot from six repository facts.

The wrapper deliberately does not create, copy, replace, or remove an approved
baseline.  It derives the existing verifier's twelve inputs from strict JSON,
then delegates all Maven and RouteContract decisions to the pinned verifier.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Iterator, Mapping, NamedTuple, Sequence


MAX_CONFIG_BYTES = 16 * 1024
MAX_VERIFIER_OUTPUT_BYTES = 1024 * 1024
PROCESS_SIGNAL_GRACE_SECONDS = 2.0
EXPECTED_VERIFIER_SHA256 = (
    "56db3afdef99286a488c98f726453e5623a182bc91737b08d1f8a2f01f2fabb5"
)
EXPECTED_INSTALLER_SHA256 = (
    "134b265709ac071dedd395da269426d83f1972f602c3b3f7d2201eecc525e204"
)
EXPECTED_CHECKSUM_PREPARER_SHA256 = (
    "ee1928e578819fb597fffe7f1c72c055ff74ec6b36d37fe35f29c7fbd382b7b7"
)
MAVEN_ARCHIVE_URL = (
    "https://archive.apache.org/dist/maven/maven-3/3.9.14/binaries/"
    "apache-maven-3.9.14-bin.tar.gz"
)
MAVEN_ARCHIVE_SHA512 = (
    "d50af8ab5e6005b46a07f0ce9d3719e67cfdf898da988a84871304cd59fb1af0"
    "fef2f99dea709e6e66f21f732f905979b5c2dce6b6860406f60a70e84d9cf0b8"
)
MAVEN_ARCHIVE_MAX_BYTES = 12 * 1024 * 1024
MAVEN_EXPANDED_MAX_BYTES = 64 * 1024 * 1024
MAVEN_TOP_DIRECTORY = "apache-maven-3.9.14"
VERIFIER = Path(__file__).resolve(strict=True).with_name(
    "verify-external-maven-integration.sh"
)
CONFIG_KEYS = frozenset(
    {
        "projectRoot",
        "owningModule",
        "reactorSelector",
        "profileOffTest",
        "pilotTest",
        "operationId",
    }
)
ROUTECONTRACT_ENVIRONMENT_KEYS = (
    "ROUTECONTRACT_EXPECTED_OUTCOME",
    "ROUTECONTRACT_REACTOR_POM",
    "ROUTECONTRACT_OWNING_POM",
    "ROUTECONTRACT_REACTOR_SELECTOR",
    "ROUTECONTRACT_PROFILE_OFF_REPORT",
    "ROUTECONTRACT_PROFILE_OFF_CLASS",
    "ROUTECONTRACT_PROFILE_OFF_METHOD",
    "ROUTECONTRACT_TEST_CLASS",
    "ROUTECONTRACT_TEST_METHOD",
    "ROUTECONTRACT_CANDIDATE_PATH",
    "ROUTECONTRACT_APPROVED_PATH",
    "ROUTECONTRACT_SUREFIRE_REPORT",
)

_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_JAVA_IDENTIFIER = r"[A-Za-z_$][A-Za-z0-9_$]*"
_TEST_SELECTOR = re.compile(
    rf"(?P<class>{_JAVA_IDENTIFIER}(?:\.{_JAVA_IDENTIFIER})*)"
    rf"#(?P<method>{_JAVA_IDENTIFIER})\Z"
)
_OPERATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class AssistedPilotError(RuntimeError):
    """A fail-closed configuration, integrity, or baseline error."""


class AssistedPilotInterrupt(KeyboardInterrupt):
    def __init__(self, signal_number: int):
        super().__init__(signal_number)
        self.signal_number = signal_number


class BaselineIdentity(NamedTuple):
    device: int
    inode: int
    mode: int
    links: int
    owner: int
    group: int
    size: int
    modified_ns: int
    changed_ns: int
    sha256: str


class Invocation(NamedTuple):
    verifier: Path
    cwd: Path
    owning_root: Path
    expected_outcome: str
    routecontract_environment: dict[str, str]
    approved_path: Path
    approved_identity: BaselineIdentity | None
    output_paths: tuple[Path, Path, Path]


class VerifierResult(NamedTuple):
    returncode: int
    stdout: bytes
    stderr: bytes


class ProcessSignalState:
    def __init__(self) -> None:
        self.signal_number: int | None = None
        self.received_at: float | None = None
        self.process_group: int | None = None
        self.forward_error = False
        self.escalated = False

    def attach(self, process_group: int) -> None:
        if process_group <= 1 or process_group == os.getpgrp():
            raise AssistedPilotError("refusing to attach an unsafe process group")
        self.process_group = process_group
        if self.escalated:
            self._forward(signal.SIGKILL)
        elif self.signal_number is not None:
            self._forward(self.signal_number)

    def detach(self) -> None:
        self.process_group = None

    def receive(self, signal_number: int) -> None:
        forwarded = signal_number
        if self.signal_number is None:
            self.signal_number = signal_number
            self.received_at = time.monotonic()
        else:
            self.escalated = True
            forwarded = signal.SIGKILL
        self._forward(forwarded)

    def _forward(self, signal_number: int) -> None:
        if self.process_group is None:
            return
        try:
            os.killpg(self.process_group, signal_number)
        except ProcessLookupError:
            return
        except OSError:
            self.forward_error = True


class _SingleValue(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"{option_string} may be supplied only once")
        setattr(namespace, self.dest, values)


def _read_regular_file_with_metadata(
    path: Path, label: str, maximum: int
) -> tuple[bytes, os.stat_result]:
    if not path.is_absolute() or path != Path(os.path.normpath(os.fspath(path))):
        raise AssistedPilotError(f"{label} must be an absolute normalized path")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise AssistedPilotError(f"{label} is unavailable") from error
    if resolved != path:
        raise AssistedPilotError(f"{label} must use its canonical path")

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise AssistedPilotError(f"{label} must be a regular non-symlink file") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise AssistedPilotError(f"{label} must be a regular non-symlink file")
        if before.st_size > maximum:
            raise AssistedPilotError(f"{label} exceeds its size limit")
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
            raise AssistedPilotError(f"{label} exceeds its size limit")
        if _metadata_tuple(before) != _metadata_tuple(after):
            raise AssistedPilotError(f"{label} changed while it was read")
    finally:
        os.close(descriptor)

    try:
        named = os.lstat(path)
    except OSError as error:
        raise AssistedPilotError(f"{label} disappeared while it was read") from error
    if not stat.S_ISREG(named.st_mode) or _metadata_tuple(named) != _metadata_tuple(
        after
    ):
        raise AssistedPilotError(f"{label} identity changed while it was read")
    return payload, after


def _metadata_tuple(metadata: os.stat_result) -> tuple[int, ...]:
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


def _read_regular_file(path: Path, label: str, maximum: int) -> bytes:
    payload, _ = _read_regular_file_with_metadata(path, label, maximum)
    return payload


def _duplicate_safe_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AssistedPilotError("config contains a duplicate key")
        result[key] = value
    return result


def load_config(path: Path) -> dict[str, str]:
    path_text = os.fspath(path)
    if any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
        for character in path_text
    ):
        raise AssistedPilotError("config path contains an unsafe Unicode character")
    payload = _read_regular_file(path, "config", MAX_CONFIG_BYTES)
    try:
        text = payload.decode("utf-8", errors="strict")
        parsed = json.loads(text, object_pairs_hook=_duplicate_safe_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AssistedPilotError("config must be strict UTF-8 JSON") from error
    if not isinstance(parsed, dict):
        raise AssistedPilotError("config must be one JSON object")
    keys = frozenset(parsed)
    if keys != CONFIG_KEYS:
        raise AssistedPilotError("config keys must match the six-field schema exactly")
    result: dict[str, str] = {}
    for key in sorted(CONFIG_KEYS):
        value = parsed[key]
        if not isinstance(value, str):
            raise AssistedPilotError(f"config field {key} must be a string")
        if unicodedata.normalize("NFC", value) != value:
            raise AssistedPilotError(f"config field {key} must use NFC text")
        if any(
            unicodedata.category(character) in {"Cc", "Cf", "Cs", "Zl", "Zp"}
            for character in value
        ):
            raise AssistedPilotError(
                f"config field {key} contains an unsafe Unicode character"
            )
        result[key] = value
    return result


def _require_canonical_directory(value: str, label: str) -> Path:
    if not value or len(value) > 4096:
        raise AssistedPilotError(f"{label} has an invalid length")
    path = Path(value)
    if not path.is_absolute() or path != Path(os.path.normpath(value)):
        raise AssistedPilotError(f"{label} must be an absolute normalized path")
    try:
        resolved = path.resolve(strict=True)
        metadata = os.lstat(path)
    except OSError as error:
        raise AssistedPilotError(f"{label} is unavailable") from error
    if resolved != path or not stat.S_ISDIR(metadata.st_mode):
        raise AssistedPilotError(f"{label} must be a canonical non-symlink directory")
    return path


def _require_regular_path(path: Path, root: Path, label: str) -> None:
    if path != Path(os.path.normpath(os.fspath(path))):
        raise AssistedPilotError(f"{label} must be normalized")
    if not path.is_relative_to(root):
        raise AssistedPilotError(f"{label} escaped the project root")
    try:
        metadata = os.lstat(path)
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise AssistedPilotError(f"{label} is unavailable") from error
    if not stat.S_ISREG(metadata.st_mode) or resolved != path:
        raise AssistedPilotError(f"{label} must be a canonical regular non-symlink file")


def _reject_maven_project_configuration(project_root: Path) -> None:
    dot_maven = project_root / ".mvn"
    try:
        metadata = os.lstat(dot_maven)
    except FileNotFoundError:
        return
    except OSError as error:
        raise AssistedPilotError("project .mvn state is unavailable") from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise AssistedPilotError("project .mvn must be a non-symlink directory")
    try:
        if dot_maven.resolve(strict=True) != dot_maven:
            raise AssistedPilotError("project .mvn must be a canonical directory")
    except OSError as error:
        raise AssistedPilotError("project .mvn state is unavailable") from error

    for name in ("maven.config", "jvm.config", "extensions.xml"):
        path = dot_maven / name
        try:
            os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise AssistedPilotError(f"project .mvn/{name} state is unavailable") from error
        raise AssistedPilotError(
            f"project .mvn/{name} is not accepted by the isolated pilot lane"
        )


def _require_module(root: Path, value: str) -> Path:
    if value == ".":
        return root
    if not value or len(value) > 512 or "\\" in value:
        raise AssistedPilotError("owningModule must be a safe relative POSIX path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or os.fspath(pure) != value:
        raise AssistedPilotError("owningModule must be a normalized relative POSIX path")
    if any(
        part in {"", ".", ".."} or _SAFE_SEGMENT.fullmatch(part) is None
        for part in pure.parts
    ):
        raise AssistedPilotError("owningModule contains an unsafe path segment")
    current = root
    for part in pure.parts:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError as error:
            raise AssistedPilotError("owningModule is unavailable") from error
        if not stat.S_ISDIR(metadata.st_mode):
            raise AssistedPilotError("owningModule must not traverse a symlink")
    if not current.resolve(strict=True).is_relative_to(root):
        raise AssistedPilotError("owningModule escaped projectRoot")
    return current


def _parse_test(value: str, field: str) -> tuple[str, str]:
    if not value or len(value) > 512:
        raise AssistedPilotError(f"{field} has an invalid length")
    match = _TEST_SELECTOR.fullmatch(value)
    if match is None:
        raise AssistedPilotError(f"{field} must be an exact Java Class#method selector")
    return match.group("class"), match.group("method")


def _validate_missing_output(path: Path, root: Path, label: str) -> None:
    if not path.is_relative_to(root) or path == root:
        raise AssistedPilotError(f"{label} escaped its owning module")
    relative = path.relative_to(root)
    current = root
    for part in relative.parts[:-1]:
        current /= part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            break
        except OSError as error:
            raise AssistedPilotError(f"{label} ancestor is unavailable") from error
        if not stat.S_ISDIR(metadata.st_mode):
            raise AssistedPilotError(f"{label} ancestor must be a non-symlink directory")
    try:
        os.lstat(path)
    except FileNotFoundError:
        return
    except OSError as error:
        raise AssistedPilotError(f"{label} state is unavailable") from error
    raise AssistedPilotError(f"{label} must start absent")


def _file_identity(path: Path, root: Path) -> BaselineIdentity:
    _require_regular_path(path, root, "approved baseline")
    payload, metadata = _read_regular_file_with_metadata(
        path, "approved baseline", 5 * 1024 * 1024
    )
    if metadata.st_nlink != 1:
        raise AssistedPilotError("approved baseline must have exactly one hard link")
    return BaselineIdentity(
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        hashlib.sha256(payload).hexdigest(),
    )


def _reject_ambient_routecontract(environment: Mapping[str, str]) -> None:
    if any(key.startswith("ROUTECONTRACT_") for key in environment):
        raise AssistedPilotError("ambient ROUTECONTRACT_ variables are not accepted")


def _read_verified_execution_bundle() -> dict[str, bytes]:
    expected = {
        VERIFIER.name: EXPECTED_VERIFIER_SHA256,
        "install-release-assets.py": EXPECTED_INSTALLER_SHA256,
        "prepare_maven_v0_1_2_checksums.py": EXPECTED_CHECKSUM_PREPARER_SHA256,
    }
    payloads: dict[str, bytes] = {}
    for name, digest in expected.items():
        payload = _read_regular_file(
            VERIFIER.with_name(name), f"reviewed execution bundle file {name}", 1024 * 1024
        )
        if hashlib.sha256(payload).hexdigest() != digest:
            raise AssistedPilotError(
                f"reviewed execution bundle file {name} does not match its SHA-256"
            )
        payloads[name] = payload
    return payloads


def _verify_verifier() -> None:
    _read_verified_execution_bundle()


def _write_all(descriptor: int, payload: bytes, label: str) -> None:
    offset = 0
    while offset < len(payload):
        try:
            written = os.write(descriptor, payload[offset:])
        except OSError as error:
            raise AssistedPilotError(f"unable to write {label}") from error
        if written <= 0:
            raise AssistedPilotError(f"write made no progress for {label}")
        offset += written


def _write_private_bytes(path: Path, payload: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, mode)
    try:
        _write_all(descriptor, payload, "private execution-bundle file")
        os.fchmod(descriptor, mode)
    finally:
        os.close(descriptor)


def _materialize_verified_execution_bundle(private_tmp: Path) -> Path:
    payloads = _read_verified_execution_bundle()
    directory = private_tmp / "reviewed-verifier"
    directory.mkdir(mode=0o700)
    for name, payload in payloads.items():
        _write_private_bytes(
            directory / name,
            payload,
            0o700 if name == VERIFIER.name else 0o600,
        )
    return directory / VERIFIER.name


def _canonical_executable(name: str, path_value: str) -> Path:
    selected = shutil.which(name, path=path_value)
    if selected is None:
        raise AssistedPilotError(f"required command is missing: {name}")
    try:
        resolved = Path(selected).resolve(strict=True)
        metadata = os.lstat(resolved)
    except OSError as error:
        raise AssistedPilotError(f"required command is unavailable: {name}") from error
    if not stat.S_ISREG(metadata.st_mode) or not os.access(resolved, os.X_OK):
        raise AssistedPilotError(f"required command is not an executable file: {name}")
    return resolved


def _java_home(java_launcher: Path) -> Path:
    probe_environment = {
        "HOME": os.fspath(Path("/tmp").resolve(strict=True)),
        "LC_ALL": "C",
        "LANG": "C",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    }
    try:
        completed = subprocess.run(
            [os.fspath(java_launcher), "-XshowSettings:properties", "-version"],
            env=probe_environment,
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AssistedPilotError("unable to inspect the Java runtime") from error
    if completed.returncode != 0:
        raise AssistedPilotError("unable to inspect the Java runtime")
    match = re.search(
        r"^\s*java\.home\s*=\s*(?P<home>.+?)\s*$",
        completed.stdout + completed.stderr,
        flags=re.MULTILINE,
    )
    if match is None:
        raise AssistedPilotError("Java did not report its runtime home")
    return _require_canonical_directory(match.group("home"), "Java home")


def _write_private_file(path: Path, payload: str, mode: int = 0o600) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, mode)
    try:
        data = payload.encode("utf-8")
        _write_all(descriptor, data, "private configuration file")
        os.fchmod(descriptor, mode)
    finally:
        os.close(descriptor)


def _download_maven_archive(curl: Path, destination: Path) -> None:
    clean_environment = {
        "HOME": os.fspath(destination.parent),
        "LC_ALL": "C",
        "LANG": "C",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    }
    try:
        completed = subprocess.run(
            [
                os.fspath(curl),
                "--disable",
                "--proto",
                "=https",
                "--tlsv1.2",
                "--fail",
                "--silent",
                "--show-error",
                "--connect-timeout",
                "15",
                "--max-time",
                "300",
                "--max-filesize",
                str(MAVEN_ARCHIVE_MAX_BYTES),
                "--remove-on-error",
                "--output",
                os.fspath(destination),
                MAVEN_ARCHIVE_URL,
            ],
            env=clean_environment,
            check=False,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise AssistedPilotError("unable to download the pinned Maven archive") from error
    if completed.returncode != 0:
        raise AssistedPilotError("unable to download the pinned Maven archive")
    payload = _read_regular_file(
        destination, "Maven archive", MAVEN_ARCHIVE_MAX_BYTES
    )
    if hashlib.sha512(payload).hexdigest() != MAVEN_ARCHIVE_SHA512:
        raise AssistedPilotError("Maven archive does not match the pinned SHA-512")


def _extract_maven_archive(archive_path: Path, destination: Path) -> Path:
    seen: dict[PurePosixPath, str] = {}
    expanded_size = 0
    try:
        archive = tarfile.open(archive_path, mode="r:gz")
    except (OSError, tarfile.TarError) as error:
        raise AssistedPilotError("pinned Maven archive is not a readable tar file") from error
    with archive:
        members = archive.getmembers()
        if not members or len(members) > 512:
            raise AssistedPilotError("pinned Maven archive has an invalid member count")
        for member in members:
            pure = PurePosixPath(member.name)
            if (
                pure.is_absolute()
                or not pure.parts
                or pure.parts[0] != MAVEN_TOP_DIRECTORY
                or any(part in {"", ".", ".."} for part in pure.parts)
            ):
                raise AssistedPilotError("pinned Maven archive has an unsafe member path")
            member_kind = "directory" if member.isdir() else "file"
            if pure in seen:
                if member_kind == "directory" and seen[pure] == "directory":
                    continue
                raise AssistedPilotError("pinned Maven archive has a duplicate member path")
            seen[pure] = member_kind
            target = destination.joinpath(*pure.parts)
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            if not member.isfile() or member.size < 0:
                raise AssistedPilotError(
                    "pinned Maven archive contains a non-regular member"
                )
            expanded_size += member.size
            if expanded_size > MAVEN_EXPANDED_MAX_BYTES:
                raise AssistedPilotError("pinned Maven archive exceeds its expanded limit")
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is None:
                raise AssistedPilotError("pinned Maven archive member is unreadable")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_CLOEXEC", 0)
            descriptor = os.open(target, flags, 0o700 if member.mode & 0o111 else 0o600)
            actual_size = 0
            try:
                while True:
                    chunk = extracted.read(64 * 1024)
                    if not chunk:
                        break
                    actual_size += len(chunk)
                    if actual_size > member.size:
                        raise AssistedPilotError(
                            "pinned Maven archive member exceeded its declared size"
                        )
                    _write_all(descriptor, chunk, "pinned Maven archive member")
                os.fchmod(descriptor, 0o700 if member.mode & 0o111 else 0o600)
            finally:
                os.close(descriptor)
                extracted.close()
            if actual_size != member.size:
                raise AssistedPilotError(
                    "pinned Maven archive member size did not match"
                )

    maven_home = destination / MAVEN_TOP_DIRECTORY
    launcher = maven_home / "bin" / "mvn"
    _read_regular_file(launcher, "pinned Maven launcher", 128 * 1024)
    if not os.access(launcher, os.X_OK):
        raise AssistedPilotError("pinned Maven launcher is not executable")
    boot_jars = tuple((maven_home / "boot").glob("plexus-classworlds-*.jar"))
    if len(boot_jars) != 1:
        raise AssistedPilotError("pinned Maven archive has an invalid boot classpath")
    _read_regular_file(boot_jars[0], "pinned Maven boot JAR", 2 * 1024 * 1024)
    return maven_home


@contextlib.contextmanager
def _isolated_maven_environment(
    invocation: Invocation, ambient_environment: Mapping[str, str]
) -> Iterator[dict[str, str]]:
    path_value = ambient_environment.get("PATH", "")
    curl = _canonical_executable("curl", path_value)
    java_launcher = _canonical_executable("java", path_value)
    java_home = _java_home(java_launcher)
    java = java_home / "bin" / "java"
    if not java.is_file() or not os.access(java, os.X_OK):
        raise AssistedPilotError("Java home does not contain an executable java")
    python = Path(sys.executable).resolve(strict=True)
    if not python.is_file() or not os.access(python, os.X_OK):
        raise AssistedPilotError("current Python interpreter is not executable")

    temporary_parent = Path("/tmp").resolve(strict=True)
    with tempfile.TemporaryDirectory(
        prefix="routecontract-assisted-maven.", dir=temporary_parent
    ) as temporary:
        root = Path(temporary).resolve(strict=True)
        os.chmod(root, 0o700)
        private_home = root / "home"
        private_tmp = root / "tmp"
        private_bin = root / "bin"
        extraction_root = root / "maven"
        for directory in (private_home, private_tmp, private_bin, extraction_root):
            directory.mkdir(mode=0o700)

        archive_path = root / "apache-maven-3.9.14-bin.tar.gz"
        _download_maven_archive(curl, archive_path)
        maven_home = _extract_maven_archive(archive_path, extraction_root)

        os.symlink(python, private_bin / "python3")
        os.symlink(curl, private_bin / "curl")
        settings = root / "empty-settings.xml"
        toolchains = root / "empty-toolchains.xml"
        _write_private_file(
            settings,
            '<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"/>\n',
        )
        _write_private_file(
            toolchains,
            '<toolchains xmlns="http://maven.apache.org/TOOLCHAINS/1.1.0"/>\n',
        )

        environment = {
            "HOME": os.fspath(private_home),
            "TMPDIR": os.fspath(private_tmp),
            "LC_ALL": "C",
            "LANG": "C",
            "PATH": os.pathsep.join(
                (
                    os.fspath(private_bin),
                    os.fspath(maven_home / "bin"),
                    os.fspath(java_home / "bin"),
                    "/usr/bin",
                    "/bin",
                    "/usr/sbin",
                    "/sbin",
                )
            ),
            "JAVA_HOME": os.fspath(java_home),
            "MAVEN_SKIP_RC": "true",
            "MAVEN_BASEDIR": os.fspath(invocation.cwd),
            "MAVEN_ARGS": " ".join(
                (
                    "--settings",
                    os.fspath(settings),
                    "--global-settings",
                    os.fspath(settings),
                    "--toolchains",
                    os.fspath(toolchains),
                    "--global-toolchains",
                    os.fspath(toolchains),
                )
            ),
            "MAVEN_OPTS": " ".join(
                (
                    f"-Duser.home={private_home}",
                    f"-Djava.io.tmpdir={private_tmp}",
                )
            ),
        }
        environment.update(invocation.routecontract_environment)
        yield environment


@contextlib.contextmanager
def _handled_signals() -> Iterator[None]:
    previous: dict[int, object] = {}

    def interrupt(signal_number, _frame):
        raise AssistedPilotInterrupt(signal_number)

    for name in ("SIGINT", "SIGTERM", "SIGHUP"):
        signal_number = getattr(signal, name, None)
        if signal_number is not None:
            previous[signal_number] = signal.getsignal(signal_number)
            signal.signal(signal_number, interrupt)
    try:
        yield
    finally:
        for signal_number, handler in previous.items():
            signal.signal(signal_number, handler)


@contextlib.contextmanager
def _latched_process_signals(state: ProcessSignalState) -> Iterator[None]:
    previous: dict[int, object] = {}

    def latch(signal_number, _frame):
        state.receive(signal_number)

    for name in ("SIGINT", "SIGTERM", "SIGHUP"):
        signal_number = getattr(signal, name, None)
        if signal_number is not None:
            previous[signal_number] = signal.getsignal(signal_number)
            signal.signal(signal_number, latch)
    try:
        yield
    finally:
        for signal_number, handler in previous.items():
            signal.signal(signal_number, handler)


def _signal_process_group(process_group: int, signal_number: int) -> bool:
    if process_group <= 1 or process_group == os.getpgrp():
        raise AssistedPilotError("refusing to signal an unsafe process group")
    try:
        os.killpg(process_group, signal_number)
    except ProcessLookupError:
        return False
    except PermissionError as error:
        raise AssistedPilotError(
            "unable to control the external verifier process group"
        ) from error
    return True


def _process_group_exists(process_group: int) -> bool:
    return _signal_process_group(process_group, 0)


def _wait_for_process_group_exit(process_group: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while _process_group_exists(process_group):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def _quiesce_process_group(process_group: int) -> bool:
    """Stop remaining same-PGID descendants and report whether any existed."""
    if not _process_group_exists(process_group):
        return False
    _signal_process_group(process_group, signal.SIGTERM)
    if not _wait_for_process_group_exit(
        process_group, PROCESS_SIGNAL_GRACE_SECONDS
    ):
        _signal_process_group(process_group, signal.SIGKILL)
        if not _wait_for_process_group_exit(
            process_group, PROCESS_SIGNAL_GRACE_SECONDS
        ):
            raise AssistedPilotError(
                "external verifier process group could not be quiesced"
            )
    return True


def _terminate_process_group(
    process: subprocess.Popen[bytes], process_group: int
) -> None:
    _signal_process_group(process_group, signal.SIGTERM)
    try:
        process.wait(timeout=PROCESS_SIGNAL_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    _signal_process_group(process_group, signal.SIGKILL)
    try:
        process.wait(timeout=PROCESS_SIGNAL_GRACE_SECONDS)
    except subprocess.TimeoutExpired as error:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        raise AssistedPilotError(
            "external verifier leader could not be terminated"
        ) from error


def _kill_process_group_now(
    process: subprocess.Popen[bytes], process_group: int
) -> None:
    _signal_process_group(process_group, signal.SIGKILL)
    try:
        process.wait(timeout=PROCESS_SIGNAL_GRACE_SECONDS)
    except subprocess.TimeoutExpired as error:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        raise AssistedPilotError(
            "external verifier leader did not stop after SIGKILL"
        ) from error


def _wait_after_forwarded_signal(
    process: subprocess.Popen[bytes],
    process_group: int,
    state: ProcessSignalState,
) -> None:
    if state.escalated:
        _kill_process_group_now(process, process_group)
        return
    received_at = state.received_at
    remaining = 0.0
    if received_at is not None:
        remaining = max(
            0.0,
            received_at + PROCESS_SIGNAL_GRACE_SECONDS - time.monotonic(),
        )
    try:
        process.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        _kill_process_group_now(process, process_group)


def _read_capped_output(handle, label: str) -> bytes:
    handle.flush()
    if os.fstat(handle.fileno()).st_size > MAX_VERIFIER_OUTPUT_BYTES:
        raise AssistedPilotError(f"external verifier {label} exceeded its size limit")
    handle.seek(0)
    payload = handle.read(MAX_VERIFIER_OUTPUT_BYTES + 1)
    if len(payload) > MAX_VERIFIER_OUTPUT_BYTES:
        raise AssistedPilotError(f"external verifier {label} exceeded its size limit")
    return payload


def _run_verifier(
    invocation: Invocation,
    child_environment: Mapping[str, str],
    state: ProcessSignalState,
) -> VerifierResult:
    private_tmp = _require_canonical_directory(
        child_environment["TMPDIR"], "isolated TMPDIR"
    )
    staged_verifier = _materialize_verified_execution_bundle(private_tmp)
    if state.signal_number is not None:
        raise AssistedPilotInterrupt(state.signal_number)

    process: subprocess.Popen[bytes] | None = None
    process_group: int | None = None
    lingering_group = False
    output_exceeded = False
    primary_error: BaseException | None = None
    result: VerifierResult | None = None
    with tempfile.TemporaryFile(mode="w+b", dir=private_tmp) as stdout_file, tempfile.TemporaryFile(
        mode="w+b", dir=private_tmp
    ) as stderr_file:
        try:
            try:
                process = subprocess.Popen(
                    [os.fspath(staged_verifier)],
                    cwd=invocation.cwd,
                    env=dict(child_environment),
                    shell=False,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    start_new_session=True,
                    close_fds=True,
                )
            except OSError as error:
                raise AssistedPilotError(
                    "unable to execute the external verifier"
                ) from error
            process_group = process.pid
            state.attach(process_group)

            while process.poll() is None:
                if (
                    os.fstat(stdout_file.fileno()).st_size
                    + os.fstat(stderr_file.fileno()).st_size
                    > MAX_VERIFIER_OUTPUT_BYTES
                ):
                    output_exceeded = True
                    _kill_process_group_now(process, process_group)
                    break
                if state.signal_number is not None:
                    _wait_after_forwarded_signal(process, process_group, state)
                    break
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass
        except BaseException as error:
            primary_error = error
        finally:
            cleanup_error: BaseException | None = None
            if process is not None and process_group is not None:
                try:
                    if process.poll() is None:
                        _terminate_process_group(process, process_group)
                    lingering_group = _quiesce_process_group(process_group)
                except BaseException as error:
                    cleanup_error = error
                finally:
                    state.detach()
            if cleanup_error is not None:
                raise cleanup_error

        if primary_error is not None:
            raise primary_error.with_traceback(primary_error.__traceback__)
        if state.forward_error:
            raise AssistedPilotError(
                "unable to forward a signal to the external verifier process group"
            )
        if lingering_group:
            raise AssistedPilotError(
                "external verifier left descendant processes running"
            )
        if output_exceeded:
            raise AssistedPilotError("external verifier output exceeded its size limit")
        if process is None or process.returncode is None:
            raise AssistedPilotError("external verifier did not produce an exit status")
        stdout = _read_capped_output(stdout_file, "stdout")
        stderr = _read_capped_output(stderr_file, "stderr")
        if len(stdout) + len(stderr) > MAX_VERIFIER_OUTPUT_BYTES:
            raise AssistedPilotError("external verifier output exceeded its size limit")
        result = VerifierResult(process.returncode, stdout, stderr)
    return result


def _write_binary_output(stream, payload: bytes) -> None:
    if not payload:
        return
    binary = getattr(stream, "buffer", None)
    if binary is not None:
        binary.write(payload)
        binary.flush()
    else:
        stream.write(payload.decode("utf-8", errors="replace"))


def _require_external_success_marker(result: VerifierResult, outcome: str) -> None:
    marker = f"ROUTECONTRACT_EXTERNAL_MAVEN outcome={outcome} VERIFIED\n".encode()
    if result.stdout.splitlines(keepends=True).count(marker) != 1:
        raise AssistedPilotError(
            "external verifier returned success without its exact success marker"
        )


def prepare_invocation(
    config_path: Path,
    expected_outcome: str,
    ambient_environment: Mapping[str, str],
) -> Invocation:
    if expected_outcome not in {"review", "matched"}:
        raise AssistedPilotError("expected outcome must be review or matched")
    _reject_ambient_routecontract(ambient_environment)
    _verify_verifier()
    config = load_config(config_path)

    project_root = _require_canonical_directory(config["projectRoot"], "projectRoot")
    _reject_maven_project_configuration(project_root)
    owning_directory = _require_module(project_root, config["owningModule"])
    reactor_pom = project_root / "pom.xml"
    owning_pom = owning_directory / "pom.xml"
    _require_regular_path(reactor_pom, project_root, "reactor POM")
    _require_regular_path(owning_pom, project_root, "owning POM")

    selector = config["reactorSelector"]
    expected_selector = owning_pom.relative_to(project_root).as_posix()
    if selector != expected_selector:
        raise AssistedPilotError(
            "reactorSelector must equal the owning POM path relative to projectRoot"
        )
    profile_class, profile_method = _parse_test(
        config["profileOffTest"], "profileOffTest"
    )
    pilot_class, pilot_method = _parse_test(config["pilotTest"], "pilotTest")
    if profile_class == pilot_class:
        raise AssistedPilotError("profileOffTest and pilotTest need distinct test classes")
    operation_id = config["operationId"]
    if (
        _OPERATION_ID.fullmatch(operation_id) is None
        or ".." in operation_id
        or len(operation_id) > 128
    ):
        raise AssistedPilotError("operationId must be a safe manifest filename stem")

    reports = owning_directory / "target" / "surefire-reports"
    profile_report = reports / f"TEST-{profile_class}.xml"
    pilot_report = reports / f"TEST-{pilot_class}.xml"
    candidate = (
        owning_directory
        / "target"
        / "routecontract"
        / f"{operation_id}.candidate.json"
    )
    approved = (
        owning_directory
        / "src"
        / "routeContractPilot"
        / "resources"
        / "route-contracts"
        / f"{operation_id}.json"
    )
    for path, label in (
        (profile_report, "profile-off report"),
        (pilot_report, "pilot report"),
        (candidate, "candidate"),
    ):
        _validate_missing_output(path, owning_directory, label)

    approved_identity = None
    if expected_outcome == "review":
        _validate_missing_output(approved, owning_directory, "approved baseline")
    else:
        approved_identity = _file_identity(approved, owning_directory)

    values = {
        "ROUTECONTRACT_EXPECTED_OUTCOME": expected_outcome,
        "ROUTECONTRACT_REACTOR_POM": os.fspath(reactor_pom),
        "ROUTECONTRACT_OWNING_POM": os.fspath(owning_pom),
        "ROUTECONTRACT_REACTOR_SELECTOR": selector,
        "ROUTECONTRACT_PROFILE_OFF_REPORT": os.fspath(profile_report),
        "ROUTECONTRACT_PROFILE_OFF_CLASS": profile_class,
        "ROUTECONTRACT_PROFILE_OFF_METHOD": profile_method,
        "ROUTECONTRACT_TEST_CLASS": pilot_class,
        "ROUTECONTRACT_TEST_METHOD": pilot_method,
        "ROUTECONTRACT_CANDIDATE_PATH": os.fspath(candidate),
        "ROUTECONTRACT_APPROVED_PATH": os.fspath(approved),
        "ROUTECONTRACT_SUREFIRE_REPORT": os.fspath(pilot_report),
    }
    if tuple(values) != ROUTECONTRACT_ENVIRONMENT_KEYS:
        raise AssistedPilotError("internal verifier environment mapping changed")
    return Invocation(
        VERIFIER,
        project_root,
        owning_directory,
        expected_outcome,
        values,
        approved,
        approved_identity,
        (profile_report, candidate, pilot_report),
    )


def _assert_baseline_postcondition(invocation: Invocation) -> None:
    if invocation.expected_outcome == "review":
        try:
            _validate_missing_output(
                invocation.approved_path, invocation.owning_root, "approved baseline"
            )
        except AssistedPilotError as error:
            raise AssistedPilotError(
                "child verifier created the approved baseline or redirected its path"
            ) from error
        return
    current = _file_identity(invocation.approved_path, invocation.owning_root)
    if current != invocation.approved_identity:
        raise AssistedPilotError("approved baseline changed during assisted verification")
    for path in invocation.output_paths:
        try:
            metadata = os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise AssistedPilotError("pilot output identity became unavailable") from error
        if stat.S_ISREG(metadata.st_mode) and (
            metadata.st_dev,
            metadata.st_ino,
        ) == (current.device, current.inode):
            raise AssistedPilotError("pilot output shares the approved baseline inode")


def execute(
    invocation: Invocation,
    ambient_environment: Mapping[str, str] | None = None,
) -> int:
    ambient = dict(os.environ if ambient_environment is None else ambient_environment)
    _reject_ambient_routecontract(ambient)
    isolation = contextlib.ExitStack()
    baseline_checked = False
    result: VerifierResult | None = None
    state = ProcessSignalState()
    try:
        child_environment = isolation.enter_context(
            _isolated_maven_environment(invocation, ambient)
        )
        _reject_maven_project_configuration(invocation.cwd)
        with _latched_process_signals(state):
            try:
                result = _run_verifier(invocation, child_environment, state)
            finally:
                try:
                    isolation.close()
                finally:
                    baseline_checked = True
                    _assert_baseline_postcondition(invocation)
    finally:
        try:
            isolation.close()
        finally:
            if not baseline_checked:
                _assert_baseline_postcondition(invocation)
    if state.signal_number is not None:
        raise AssistedPilotInterrupt(state.signal_number)
    if result is None:
        raise AssistedPilotError("external verifier did not return a result")
    if result.returncode == 0:
        _require_external_success_marker(result, invocation.expected_outcome)
    _write_binary_output(sys.stdout, result.stdout)
    _write_binary_output(sys.stderr, result.stderr)
    if result.returncode == 0:
        print(
            "ROUTECONTRACT_ASSISTED_MAVEN "
            f"outcome={invocation.expected_outcome} VERIFIED"
        )
    return result.returncode if 0 <= result.returncode <= 255 else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one reviewed RouteContract Maven pilot from strict JSON",
        allow_abbrev=False,
    )
    parser.set_defaults(config=None, expected_outcome=None)
    parser.add_argument(
        "--config",
        required=True,
        action=_SingleValue,
        type=Path,
        help="absolute canonical path to the six-field JSON config",
    )
    parser.add_argument(
        "--expected-outcome",
        required=True,
        action=_SingleValue,
        choices=("review", "matched"),
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    try:
        parsed = _parser().parse_args(arguments)
        invocation = prepare_invocation(
            parsed.config, parsed.expected_outcome, os.environ
        )
        with _handled_signals():
            return execute(invocation, os.environ)
    except AssistedPilotError as error:
        print(f"ROUTECONTRACT_ASSISTED_MAVEN_ERROR {error}", file=sys.stderr)
        return 2
    except AssistedPilotInterrupt as error:
        print("ROUTECONTRACT_ASSISTED_MAVEN_ERROR interrupted", file=sys.stderr)
        return 128 + error.signal_number
    except KeyboardInterrupt:
        print("ROUTECONTRACT_ASSISTED_MAVEN_ERROR interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
