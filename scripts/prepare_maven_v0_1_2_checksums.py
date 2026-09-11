#!/usr/bin/env python3
"""Prepare strict Maven sidecars for the exact immutable RouteContract v0.1.2.

The release installer deliberately writes only the four Maven payloads.  This
helper re-binds those installed bytes to fixed public Release SHA-256 values,
then publishes raw Maven `.sha1` and `.sha256` sidecars without overwriting any
existing path.  It is intended for a new, private, single-writer repository;
failed repositories are evidence to retain, not destinations to repair.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import secrets
import stat
import sys


GROUP_PATH = Path("io/github/ym0506/routecontract")
ARTIFACT_ID = "routecontract-shardingsphere-5.5"
VERSION = "0.1.2"
EXPECTED_ARTIFACTS: dict[str, dict[str, str]] = {
    f"{ARTIFACT_ID}-{VERSION}.pom": {
        "sha1": "a8399a2804e41348f857e16988bbaa2b072eba79",
        "sha256": "70b5d4161d1532e9f9cb699071790a7806d87658511d931477544fa06037b85d",
    },
    f"{ARTIFACT_ID}-{VERSION}.jar": {
        "sha1": "86856916485df62867cb832c105d30abb600060c",
        "sha256": "d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc",
    },
    f"{ARTIFACT_ID}-{VERSION}-sources.jar": {
        "sha1": "d9f4d35086022a0e1af9e5d36830c7df3768226e",
        "sha256": "f1f7e0a10a165b713ee1483c219480786021135867275345b0b9ba1e5f51fea9",
    },
    f"{ARTIFACT_ID}-{VERSION}-javadoc.jar": {
        "sha1": "a15c4c77a1643db2524efa489040da417c08ccfb",
        "sha256": "e97fd6cd99df21404bc015af17eac1856c17c695f75f190a709e102a74c748ac",
    },
}


class ChecksumPreparationError(RuntimeError):
    """A fail-closed repository preparation error."""


def _required_flag(name: str) -> int:
    value = getattr(os, name, None)
    if value is None:
        raise ChecksumPreparationError(
            f"this POSIX-only helper requires os.{name}; use another absent repository"
        )
    return value


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | _required_flag("O_DIRECTORY")
        | _required_flag("O_NOFOLLOW")
        | _required_flag("O_NONBLOCK")
    )


def _open_directory_chain(parent_fd: int, components: tuple[str, ...]) -> int:
    current_fd = os.dup(parent_fd)
    try:
        for component in components:
            if component in ("", ".", ".."):
                raise ChecksumPreparationError("directory path contains an unsafe component")
            next_fd = os.open(
                component,
                _directory_open_flags(),
                dir_fd=current_fd,
            )
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _hash_file_at(directory_fd: int, name: str) -> dict[str, str]:
    descriptor = os.open(
        name,
        os.O_RDONLY
        | _required_flag("O_NOFOLLOW")
        | _required_flag("O_NONBLOCK"),
        dir_fd=directory_fd,
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ChecksumPreparationError(f"installed artifact is not a regular file: {name}")
        sha1 = hashlib.sha1(usedforsecurity=False)
        sha256 = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            sha1.update(chunk)
            sha256.update(chunk)
        return {"sha1": sha1.hexdigest(), "sha256": sha256.hexdigest()}
    finally:
        os.close(descriptor)


def _read_file_at(directory_fd: int, name: str) -> bytes:
    descriptor = os.open(
        name,
        os.O_RDONLY
        | _required_flag("O_NOFOLLOW")
        | _required_flag("O_NONBLOCK"),
        dir_fd=directory_fd,
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ChecksumPreparationError(f"sidecar is not a regular file: {name}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 4096)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _write_new_sidecar(directory_fd: int, name: str, payload: bytes) -> None:
    temporary_name = (
        f".routecontract-checksum.{os.getpid()}.{secrets.token_hex(12)}.tmp"
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | _required_flag("O_NOFOLLOW"),
            0o600,
            dir_fd=directory_fd,
        )
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise ChecksumPreparationError(f"short write while staging {name}")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        try:
            os.link(
                temporary_name,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError as error:
            raise ChecksumPreparationError(f"refusing to overwrite sidecar: {name}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _inventory(directory_fd: int) -> set[str]:
    return set(os.listdir(directory_fd))


def _assert_initial_inventory(directory_fd: int) -> None:
    actual = _inventory(directory_fd)
    expected = set(EXPECTED_ARTIFACTS)
    if actual != expected:
        raise ChecksumPreparationError(
            "installed coordinate must have the exact four-file inventory; "
            f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
        )


def _assert_artifact_hashes(directory_fd: int) -> None:
    for name, expected in EXPECTED_ARTIFACTS.items():
        actual = _hash_file_at(directory_fd, name)
        if actual["sha256"] != expected["sha256"]:
            raise ChecksumPreparationError(
                f"installed artifact SHA-256 mismatch for {name}: "
                f"expected={expected['sha256']}, actual={actual['sha256']}"
            )
        if actual["sha1"] != expected["sha1"]:
            raise ChecksumPreparationError(
                f"installed artifact SHA-1 mismatch for {name}: "
                f"expected={expected['sha1']}, actual={actual['sha1']}"
            )


def _assert_final_state(directory_fd: int) -> None:
    expected_inventory = set(EXPECTED_ARTIFACTS)
    for name in EXPECTED_ARTIFACTS:
        expected_inventory.add(f"{name}.sha1")
        expected_inventory.add(f"{name}.sha256")
    actual_inventory = _inventory(directory_fd)
    if actual_inventory != expected_inventory:
        raise ChecksumPreparationError(
            "prepared coordinate violates the exact twelve-file inventory; "
            f"missing={sorted(expected_inventory - actual_inventory)}, "
            f"unexpected={sorted(actual_inventory - expected_inventory)}"
        )
    _assert_artifact_hashes(directory_fd)
    for name, expected in EXPECTED_ARTIFACTS.items():
        for algorithm, length in (("sha1", 40), ("sha256", 64)):
            sidecar_name = f"{name}.{algorithm}"
            expected_bytes = (expected[algorithm] + "\n").encode("ascii")
            actual_bytes = _read_file_at(directory_fd, sidecar_name)
            if len(actual_bytes) != length + 1 or actual_bytes != expected_bytes:
                raise ChecksumPreparationError(
                    f"prepared sidecar bytes do not match {sidecar_name}"
                )


def prepare_repository(repository: Path) -> Path:
    if not repository.is_absolute():
        raise ChecksumPreparationError("Maven repository must be an explicit absolute path")
    if repository.is_symlink():
        raise ChecksumPreparationError("Maven repository must not be a symbolic link")
    if not repository.is_dir():
        raise ChecksumPreparationError("Maven repository must be an existing directory")

    coordinate = repository / GROUP_PATH / ARTIFACT_ID / VERSION
    if coordinate.is_symlink() or not coordinate.is_dir():
        raise ChecksumPreparationError(
            f"exact installed RouteContract coordinate is missing or unsafe: {coordinate}"
        )

    repository_fd = os.open(repository, _directory_open_flags())
    try:
        try:
            directory_fd = _open_directory_chain(
                repository_fd,
                (*GROUP_PATH.parts, ARTIFACT_ID, VERSION),
            )
        except OSError as error:
            raise ChecksumPreparationError(
                f"exact installed RouteContract coordinate is missing or unsafe: {coordinate}"
            ) from error
    finally:
        os.close(repository_fd)
    try:
        _assert_initial_inventory(directory_fd)
        _assert_artifact_hashes(directory_fd)
        for name in sorted(EXPECTED_ARTIFACTS):
            for algorithm in ("sha1", "sha256"):
                payload = (EXPECTED_ARTIFACTS[name][algorithm] + "\n").encode("ascii")
                _write_new_sidecar(directory_fd, f"{name}.{algorithm}", payload)
        os.fsync(directory_fd)
        _assert_final_state(directory_fd)
    finally:
        os.close(directory_fd)
    return coordinate


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare SHA-1 and SHA-256 Maven sidecars for the exact immutable "
            "RouteContract v0.1.2 installed coordinate."
        )
    )
    parser.add_argument(
        "--repository",
        required=True,
        help="absolute explicit Maven repository created by install-release-assets.py",
    )
    return parser.parse_args(argv)


def run(argv: list[str]) -> int:
    arguments = parse_args(argv)
    coordinate = prepare_repository(Path(arguments.repository))
    print(f"Prepared exact RouteContract v0.1.2 Maven sidecars: {coordinate}")
    print("Prepared algorithms: SHA-256 and SHA-1 (raw lowercase hex plus LF).")
    print(
        "This preparation alone does not prove which algorithm a Maven transfer validated."
    )
    return 0


def main() -> int:
    try:
        return run(sys.argv[1:])
    except (ChecksumPreparationError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
