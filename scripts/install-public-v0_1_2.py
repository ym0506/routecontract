#!/usr/bin/env python3
"""Download and install the exact public RouteContract v0.1.2 Release.

This version-specific convenience wrapper performs only public HTTPS reads. It
downloads the immutable Release's exact asset set, the installer stored in the
peeled release commit, and a fixed-hash post-release checksum preparer. It
verifies their fixed SHA-256 anchors and delegates to those helpers. The
delegated installer retains the full asset, archive, POM, JAR,
supply-chain-evidence, destination, and review-expiry gates.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import urllib.parse
from collections.abc import Callable
from typing import Optional

try:
    import pwd
except ImportError:  # pragma: no cover - unavailable on non-POSIX systems
    pwd = None  # type: ignore[assignment]


REPOSITORY_SLUG = "ym0506/routecontract"
VERSION = "0.1.2"
TAG = f"v{VERSION}"
TAG_OBJECT = "6adacbe04d60b3af83d9067a14a878d26a6c90f5"
RELEASE_COMMIT = "fc4fdd16c21574afa1150654ce354cf8004b138b"
RELEASE_URL = f"https://github.com/{REPOSITORY_SLUG}/releases/tag/{TAG}"
RELEASE_DOWNLOAD_BASE = (
    f"https://github.com/{REPOSITORY_SLUG}/releases/download/{TAG}"
)
INSTALLER_URL = (
    f"https://raw.githubusercontent.com/{REPOSITORY_SLUG}/{RELEASE_COMMIT}/"
    "scripts/install-release-assets.py"
)
CHECKSUM_PREPARER_COMMIT = "2264b6e6292ee80f131148f2acef601cbaede096"
CHECKSUM_PREPARER_URL = (
    f"https://raw.githubusercontent.com/{REPOSITORY_SLUG}/"
    f"{CHECKSUM_PREPARER_COMMIT}/scripts/prepare_maven_v0_1_2_checksums.py"
)
EXPECTED_INDEX_SHA256 = (
    "7849adf417f0170b08d01902b023e8b328d8796f7c2aeacc471eb7acf8e2b217"
)
EXPECTED_INSTALLER_SHA256 = (
    "134b265709ac071dedd395da269426d83f1972f602c3b3f7d2201eecc525e204"
)
EXPECTED_CHECKSUM_PREPARER_SHA256 = (
    "ee1928e578819fb597fffe7f1c72c055ff74ec6b36d37fe35f29c7fbd382b7b7"
)
ASSET_NAMES = (
    "SHA256SUMS",
    f"routecontract-{VERSION}-source.zip",
    f"routecontract-shardingsphere-5.5-{VERSION}.jar",
    f"routecontract-shardingsphere-5.5-{VERSION}-sources.jar",
    f"routecontract-shardingsphere-5.5-{VERSION}-javadoc.jar",
    "routecontract-shardingsphere-5.5.pom",
    "routecontract-shardingsphere-5.5-cyclonedx.json",
    "routecontract-shardingsphere-5.5-cyclonedx.xml",
    "routecontract-aggregate-cyclonedx.json",
    "routecontract-aggregate-cyclonedx.xml",
    "supply-chain-evidence.json",
    "test-summary.txt",
)
EXPECTED_DOWNLOAD_SIZES = {
    INSTALLER_URL: 77_732,
    CHECKSUM_PREPARER_URL: 10_727,
    f"{RELEASE_DOWNLOAD_BASE}/SHA256SUMS": 1_155,
    f"{RELEASE_DOWNLOAD_BASE}/routecontract-{VERSION}-source.zip": 1_062_150,
    f"{RELEASE_DOWNLOAD_BASE}/routecontract-shardingsphere-5.5-{VERSION}.jar": 75_891,
    f"{RELEASE_DOWNLOAD_BASE}/routecontract-shardingsphere-5.5-{VERSION}-sources.jar": 46_313,
    f"{RELEASE_DOWNLOAD_BASE}/routecontract-shardingsphere-5.5-{VERSION}-javadoc.jar": 208_628,
    f"{RELEASE_DOWNLOAD_BASE}/routecontract-shardingsphere-5.5.pom": 2_138,
    f"{RELEASE_DOWNLOAD_BASE}/routecontract-shardingsphere-5.5-cyclonedx.json": 114_460,
    f"{RELEASE_DOWNLOAD_BASE}/routecontract-shardingsphere-5.5-cyclonedx.xml": 103_653,
    f"{RELEASE_DOWNLOAD_BASE}/routecontract-aggregate-cyclonedx.json": 373_935,
    f"{RELEASE_DOWNLOAD_BASE}/routecontract-aggregate-cyclonedx.xml": 338_758,
    f"{RELEASE_DOWNLOAD_BASE}/supply-chain-evidence.json": 3_700,
    f"{RELEASE_DOWNLOAD_BASE}/test-summary.txt": 950,
}
ALLOWED_HTTPS_HOSTS = frozenset(
    {
        "github.com",
        "raw.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
)
DOWNLOAD_TIMEOUT_SECONDS = 300
INSTALL_TIMEOUT_SECONDS = 300
CURL_STDERR_LIMIT = 64 * 1024
CURL_HEADER_LIMIT = 64 * 1024
GITHUB_AUTH_ENVIRONMENT = frozenset(
    {
        "GH_ENTERPRISE_TOKEN",
        "GH_TOKEN",
        "GITHUB_AUTH_TOKEN",
        "GITHUB_ENTERPRISE_TOKEN",
        "GITHUB_TOKEN",
    }
)


class PublicInstallError(RuntimeError):
    """A fail-closed public download or installation error."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_https_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    try:
        port = parsed.port
    except ValueError as error:
        raise PublicInstallError("refusing an untrusted download URL") from error
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.hostname not in ALLOWED_HTTPS_HOSTS
        or port not in (None, 443)
        or not parsed.path.startswith("/")
        or parsed.fragment
    ):
        raise PublicInstallError("refusing an untrusted download URL")


def _validate_release_redirect(initial_url: str, status: str, redirect_url: str) -> None:
    _validate_https_url(initial_url)
    _validate_https_url(redirect_url)
    initial = urllib.parse.urlsplit(initial_url)
    redirect = urllib.parse.urlsplit(redirect_url)
    expected_urls = {
        f"{RELEASE_DOWNLOAD_BASE}/{name}" for name in ASSET_NAMES
    }
    if initial_url not in expected_urls or initial.query:
        raise PublicInstallError("Release asset download origin is not exact")
    if (
        status != "302"
        or redirect.hostname != "release-assets.githubusercontent.com"
        or not redirect.path.startswith("/github-production-release-asset/")
    ):
        raise PublicInstallError("Release asset redirect is not an exact allowed 302")


def _curl_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in GITHUB_AUTH_ENVIRONMENT:
        environment.pop(name, None)
    return environment


def _curl_common_arguments(curl: Path) -> list[str]:
    return [
        os.fspath(curl),
        "--disable",
        "--proto",
        "=https",
        "--proto-redir",
        "=https",
        "--tlsv1.2",
        "--fail",
        "--silent",
        "--show-error",
        "--retry",
        "3",
        "--connect-timeout",
        "15",
        "--max-time",
        str(DOWNLOAD_TIMEOUT_SECONDS),
        "--user-agent",
        "routecontract-public-installer-v0.1.2",
        "--header",
        "Accept-Encoding: identity",
    ]


def _remove_private_download(path: Path) -> None:
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
    except OSError:
        pass


def _discover_release_redirect(curl: Path, initial_url: str) -> str:
    _validate_https_url(initial_url)
    try:
        result = subprocess.run(
            [
                *_curl_common_arguments(curl),
                "--head",
                "--max-redirs",
                "0",
                "--output",
                os.devnull,
                "--write-out",
                "%{http_code}\n%{redirect_url}",
                initial_url,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=DOWNLOAD_TIMEOUT_SECONDS + 30,
            env=_curl_environment(),
        )
    except subprocess.TimeoutExpired as error:
        raise PublicInstallError("Release redirect discovery timed out") from error
    except OSError as error:
        raise PublicInstallError("curl could not inspect the public Release URL") from error
    if result.returncode != 0:
        raise PublicInstallError(
            f"Release redirect discovery failed with curl exit {result.returncode}; "
            "curl diagnostics are withheld because redirect URLs can be signed"
        )
    if len(result.stdout) > CURL_HEADER_LIMIT:
        raise PublicInstallError("Release redirect metadata exceeds the safety limit")
    try:
        status, redirect_url = result.stdout.decode(
            "utf-8", errors="strict"
        ).split("\n", 1)
    except (UnicodeDecodeError, ValueError) as error:
        raise PublicInstallError("curl returned malformed Release redirect metadata") from error
    _validate_release_redirect(initial_url, status, redirect_url)
    return redirect_url


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise PublicInstallError("short write while receiving a public download")
        offset += written


def _read_header_statuses(path: Path) -> list[str]:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise PublicInstallError("curl response headers are missing") from error
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise PublicInstallError("curl response headers are not a regular file")
    if metadata.st_size > CURL_HEADER_LIMIT:
        raise PublicInstallError("curl response headers exceed the safety limit")
    try:
        headers = path.read_bytes().decode("iso-8859-1", errors="strict")
    except (OSError, UnicodeDecodeError) as error:
        raise PublicInstallError("curl response headers are unreadable") from error
    return re.findall(r"(?m)^HTTP/[^\r\n ]+ ([0-9]{3})(?:[ \r]|$)", headers)


def _fetch_exact_url(
    curl: Path,
    url: str,
    destination: Path,
    expected_size: int,
) -> None:
    _validate_https_url(url)
    if destination.exists() or destination.is_symlink():
        raise PublicInstallError(f"refusing to overwrite download: {destination.name}")
    header_path = destination.parent / (
        f".{destination.name}.headers.{os.getpid()}.{secrets.token_hex(12)}"
    )
    descriptor: Optional[int] = None
    process: Optional[subprocess.Popen[bytes]] = None
    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW"),
            0o600,
        )
        process = subprocess.Popen(
            [
                *_curl_common_arguments(curl),
                "--max-redirs",
                "0",
                "--max-filesize",
                str(expected_size),
                "--dump-header",
                os.fspath(header_path),
                url,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_curl_environment(),
        )
        if process.stdout is None or process.stderr is None:  # pragma: no cover
            raise PublicInstallError("curl pipes were not created")
        total = 0
        while True:
            chunk = process.stdout.read(min(64 * 1024, expected_size + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > expected_size:
                process.terminate()
                raise PublicInstallError(
                    f"public download exceeds the hard byte limit: {destination.name}"
                )
            _write_all(descriptor, chunk)
        diagnostics = process.stderr.read(CURL_STDERR_LIMIT + 1)
        if len(diagnostics) > CURL_STDERR_LIMIT:
            process.terminate()
            raise PublicInstallError("curl diagnostics exceed the safety limit")
        try:
            returncode = process.wait(timeout=30)
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.wait()
            raise PublicInstallError("curl did not exit after its download timeout") from error
        os.fsync(descriptor)
        if returncode != 0:
            raise PublicInstallError(
                f"public download failed with curl exit {returncode}: "
                f"{destination.name}; curl diagnostics are withheld because URLs can be signed"
            )
        statuses = _read_header_statuses(header_path)
        if not statuses or statuses[-1] != "200" or any(
            status.startswith("3") for status in statuses
        ):
            raise PublicInstallError(
                f"public download did not return a direct final 200: {destination.name}"
            )
        if total != expected_size:
            raise PublicInstallError(
                f"public download size mismatch for {destination.name}: "
                f"expected={expected_size}, actual={total}"
            )
    except KeyboardInterrupt:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        raise
    except OSError as error:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        raise PublicInstallError("curl could not complete the public download") from error
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
        if descriptor is not None:
            os.close(descriptor)
        _remove_private_download(header_path)
        if sys.exc_info()[0] is not None:
            _remove_private_download(destination)


def _find_curl() -> Path:
    discovered = shutil.which("curl")
    if discovered is None:
        raise PublicInstallError("curl is required for public HTTPS downloads")
    curl = Path(discovered)
    try:
        resolved = curl.resolve(strict=True)
    except OSError as error:
        raise PublicInstallError("curl executable is unavailable") from error
    if not resolved.is_file():
        raise PublicInstallError("curl executable is not a regular file")
    return resolved


def _download_with_curl(
    curl: Path,
    url: str,
    destination: Path,
    expected_size: int,
) -> None:
    _validate_https_url(url)
    if url in (INSTALLER_URL, CHECKSUM_PREPARER_URL):
        direct_url = url
    elif url in {
        f"{RELEASE_DOWNLOAD_BASE}/{name}" for name in ASSET_NAMES
    }:
        direct_url = _discover_release_redirect(curl, url)
    else:
        raise PublicInstallError("public download origin is not exact")
    _fetch_exact_url(curl, direct_url, destination, expected_size)


def _require_posix_capabilities() -> None:
    if os.name != "posix":
        raise PublicInstallError("this exact v0.1.2 installer requires a POSIX system")
    for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"):
        if getattr(os, name, None) is None:
            raise PublicInstallError(
                f"this exact v0.1.2 installer requires os.{name} before network access"
            )
    for operation in (os.open, os.mkdir, os.link, os.unlink):
        if operation not in os.supports_dir_fd:
            raise PublicInstallError(
                "this exact v0.1.2 installer requires POSIX dir-fd operations"
            )
    if os.listdir not in os.supports_fd or os.link not in os.supports_follow_symlinks:
        raise PublicInstallError(
            "this exact v0.1.2 installer requires POSIX fd and no-follow operations"
        )


def _path_key(path: Path) -> tuple[str, ...]:
    return tuple(unicodedata.normalize("NFC", part).casefold() for part in path.parts)


def _conventional_maven_repositories() -> set[Path]:
    homes = {Path.home()}
    if pwd is not None:
        try:
            account_home = pwd.getpwuid(os.getuid()).pw_dir
        except (KeyError, OSError):
            account_home = ""
        if account_home:
            homes.add(Path(account_home))
    return {
        (home / ".m2" / "repository").resolve(strict=False) for home in homes
    }


def _validate_repository_argument(raw: str) -> Path:
    repository = Path(raw)
    if not repository.is_absolute():
        raise PublicInstallError("target Maven repository must be an absolute path")
    if repository != Path(os.path.normpath(os.fspath(repository))):
        raise PublicInstallError("target Maven repository must be a normalized path")
    if repository.exists() or repository.is_symlink():
        raise PublicInstallError("target Maven repository must be a new absent path")
    repository = repository.resolve(strict=False)
    repository_key = _path_key(repository)
    for conventional in _conventional_maven_repositories():
        conventional_key = _path_key(conventional)
        if repository_key[: len(conventional_key)] == conventional_key:
            raise PublicInstallError(
                "target Maven repository must not be ~/.m2/repository or below it"
            )
    parent = repository.parent
    if not parent.is_dir() or parent.is_symlink():
        raise PublicInstallError(
            "target Maven repository parent must be an existing canonical directory"
        )
    return repository


def _directory_open_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK


def _retained_residue_message(repository: Path) -> str:
    return (
        "reserved target residue was retained for the requested path "
        f"{repository}; after a path-binding change the original path may no "
        "longer name that reservation; do not reuse or repair the original or "
        "any moved reservation, and choose a new absent target path"
    )


def _assert_directory_binding(path: Path, descriptor: int) -> None:
    try:
        if path.is_symlink() or path.resolve(strict=True) != path:
            raise PublicInstallError("reserved Maven repository path binding changed")
        current = os.open(path, _directory_open_flags())
    except OSError as error:
        raise PublicInstallError("reserved Maven repository path binding changed") from error
    try:
        expected_metadata = os.fstat(descriptor)
        current_metadata = os.fstat(current)
        if (
            not stat.S_ISDIR(expected_metadata.st_mode)
            or not stat.S_ISDIR(current_metadata.st_mode)
            or (expected_metadata.st_dev, expected_metadata.st_ino)
            != (current_metadata.st_dev, current_metadata.st_ino)
        ):
            raise PublicInstallError("reserved Maven repository path binding changed")
    finally:
        os.close(current)


def _reserve_repository(repository: Path) -> int:
    created = False
    descriptor: Optional[int] = None
    try:
        parent_descriptor = os.open(repository.parent, _directory_open_flags())
        try:
            if repository.parent.resolve(strict=True) != repository.parent:
                raise PublicInstallError(
                    "target Maven repository parent binding changed"
                )
            try:
                os.mkdir(repository.name, mode=0o700, dir_fd=parent_descriptor)
            except FileExistsError as error:
                raise PublicInstallError(
                    "target Maven repository became occupied before installation"
                ) from error
            created = True
            descriptor = os.open(
                repository.name,
                _directory_open_flags(),
                dir_fd=parent_descriptor,
            )
        finally:
            os.close(parent_descriptor)
        if descriptor is None:  # pragma: no cover - defensive invariant
            raise PublicInstallError("target Maven repository reservation failed")
        os.fchmod(descriptor, 0o700)
        _assert_directory_binding(repository, descriptor)
        return descriptor
    except BaseException as error:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            detail = (
                str(error)
                if isinstance(error, PublicInstallError)
                else "target Maven repository initialization failed after creation"
            )
            raise PublicInstallError(
                f"{detail}; {_retained_residue_message(repository)}"
            ) from error
        raise


def _coordinate_parts() -> tuple[str, ...]:
    return (
        "io",
        "github",
        "ym0506",
        "routecontract",
        "routecontract-shardingsphere-5.5",
        VERSION,
    )


def _payload_names() -> set[str]:
    return {
        f"routecontract-shardingsphere-5.5-{VERSION}.pom",
        f"routecontract-shardingsphere-5.5-{VERSION}.jar",
        f"routecontract-shardingsphere-5.5-{VERSION}-sources.jar",
        f"routecontract-shardingsphere-5.5-{VERSION}-javadoc.jar",
    }


def _expected_coordinate_names() -> set[str]:
    payload_names = _payload_names()
    return payload_names | {
        f"{name}.{algorithm}"
        for name in payload_names
        for algorithm in ("sha1", "sha256")
    }


def _staged_coordinate(repository: Path) -> Path:
    coordinate = repository.joinpath(*_coordinate_parts())
    try:
        metadata = coordinate.lstat()
    except OSError as error:
        raise PublicInstallError(
            "staged Maven coordinate is missing after helper success"
        ) from error
    if coordinate.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise PublicInstallError("staged Maven coordinate is not a directory")
    descriptor = os.open(coordinate, _directory_open_flags())
    try:
        actual_names = set(os.listdir(descriptor))
        if actual_names != _expected_coordinate_names():
            raise PublicInstallError("staged Maven coordinate inventory is not exact")
        for name in actual_names:
            metadata = os.stat(
                name,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
            if not stat.S_ISREG(metadata.st_mode):
                raise PublicInstallError(
                    "staged Maven coordinate inventory is not exact"
                )
    finally:
        os.close(descriptor)
    return coordinate


def _open_new_directory(parent_descriptor: int, name: str) -> int:
    if not name or name in (".", "..") or os.sep in name:
        raise PublicInstallError("internal Maven coordinate path is invalid")
    os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
    descriptor = os.open(name, _directory_open_flags(), dir_fd=parent_descriptor)
    try:
        os.fchmod(descriptor, 0o700)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _sha256_descriptor(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while chunk := os.read(descriptor, 1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def _copy_regular_file_at(
    source_descriptor: int,
    destination_descriptor: int,
    name: str,
) -> None:
    source = os.open(
        name,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=source_descriptor,
    )
    destination: Optional[int] = None
    try:
        source_metadata = os.fstat(source)
        if not stat.S_ISREG(source_metadata.st_mode):
            raise PublicInstallError("staged Maven coordinate inventory is not exact")
        expected_digest = _sha256_descriptor(source)
        os.lseek(source, 0, os.SEEK_SET)
        destination = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            stat.S_IMODE(source_metadata.st_mode),
            dir_fd=destination_descriptor,
        )
        os.fchmod(destination, stat.S_IMODE(source_metadata.st_mode))
        copied = 0
        while chunk := os.read(source, 1024 * 1024):
            copied += len(chunk)
            _write_all(destination, chunk)
        os.fsync(destination)
        if copied != source_metadata.st_size:
            raise PublicInstallError("published Maven file size is not exact")
    finally:
        if destination is not None:
            os.close(destination)
        os.close(source)

    published = os.open(
        name,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=destination_descriptor,
    )
    try:
        published_metadata = os.fstat(published)
        if (
            not stat.S_ISREG(published_metadata.st_mode)
            or published_metadata.st_size != source_metadata.st_size
            or stat.S_IMODE(published_metadata.st_mode)
            != stat.S_IMODE(source_metadata.st_mode)
            or _sha256_descriptor(published) != expected_digest
        ):
            raise PublicInstallError("published Maven file bytes or mode are not exact")
    finally:
        os.close(published)


def _publish_staged_coordinate(
    staged_coordinate: Path,
    repository_descriptor: int,
) -> None:
    if os.listdir(repository_descriptor):
        raise PublicInstallError("reserved Maven repository is not empty")
    source_descriptor = os.open(staged_coordinate, _directory_open_flags())
    opened_directories: list[int] = []
    try:
        actual_names = set(os.listdir(source_descriptor))
        expected_names = _expected_coordinate_names()
        if actual_names != expected_names:
            raise PublicInstallError("staged Maven coordinate inventory is not exact")

        parent_descriptor = repository_descriptor
        for part in _coordinate_parts():
            child_descriptor = _open_new_directory(parent_descriptor, part)
            opened_directories.append(child_descriptor)
            parent_descriptor = child_descriptor

        for name in sorted(expected_names):
            _copy_regular_file_at(source_descriptor, parent_descriptor, name)
        hierarchy_descriptors = [repository_descriptor, *opened_directories]
        hierarchy_expectations: list[set[str]] = [
            {part} for part in _coordinate_parts()
        ] + [expected_names]
        for descriptor, expected_inventory in zip(
            hierarchy_descriptors,
            hierarchy_expectations,
        ):
            os.fsync(descriptor)
            if set(os.listdir(descriptor)) != expected_inventory:
                raise PublicInstallError(
                    "published Maven repository inventory is not exact"
                )
    finally:
        for descriptor in reversed(opened_directories):
            os.close(descriptor)
        os.close(source_descriptor)


def install_public_release(
    repository: Path,
    *,
    downloader: Optional[Callable[[str, Path], None]] = None,
) -> None:
    _require_posix_capabilities()
    repository = _validate_repository_argument(os.fspath(repository))
    if downloader is None:
        curl = _find_curl()
        selected_downloader = lambda url, destination: _download_with_curl(
            curl, url, destination, EXPECTED_DOWNLOAD_SIZES[url]
        )
    else:
        selected_downloader = downloader
    repository_descriptor = _reserve_repository(repository)
    try:
        try:
            with tempfile.TemporaryDirectory(
                prefix="routecontract-v0.1.2-public-"
            ) as raw:
                temporary_root = Path(raw).resolve(strict=True)
                assets = temporary_root / "assets"
                assets.mkdir(mode=0o700)
                installer = temporary_root / "install-release-assets.py"
                checksum_preparer = (
                    temporary_root / "prepare_maven_v0_1_2_checksums.py"
                )
                staged_repository = temporary_root / "staged-maven"

                selected_downloader(INSTALLER_URL, installer)
                if _sha256(installer) != EXPECTED_INSTALLER_SHA256:
                    raise PublicInstallError("tag-pinned installer SHA-256 mismatch")
                selected_downloader(CHECKSUM_PREPARER_URL, checksum_preparer)
                if _sha256(checksum_preparer) != EXPECTED_CHECKSUM_PREPARER_SHA256:
                    raise PublicInstallError(
                        "commit-pinned checksum preparer SHA-256 mismatch"
                    )

                for name in ASSET_NAMES:
                    selected_downloader(
                        f"{RELEASE_DOWNLOAD_BASE}/{name}",
                        assets / name,
                    )
                if _sha256(assets / "SHA256SUMS") != EXPECTED_INDEX_SHA256:
                    raise PublicInstallError("immutable Release SHA256SUMS mismatch")

                try:
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-I",
                            os.fspath(installer),
                            "--release-assets-dir",
                            os.fspath(assets),
                            "--repository",
                            os.fspath(staged_repository),
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                        timeout=INSTALL_TIMEOUT_SECONDS,
                    )
                except subprocess.TimeoutExpired as error:
                    raise PublicInstallError("tag-pinned installer timed out") from error
                if result.returncode != 0:
                    stderr = result.stderr.decode("utf-8", errors="replace").strip()
                    raise PublicInstallError(
                        "tag-pinned installer rejected the release or destination"
                        + (f": {stderr}" if stderr else "")
                    )

                try:
                    checksum_result = subprocess.run(
                        [
                            sys.executable,
                            "-I",
                            os.fspath(checksum_preparer),
                            "--repository",
                            os.fspath(staged_repository),
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                        timeout=INSTALL_TIMEOUT_SECONDS,
                    )
                except subprocess.TimeoutExpired as error:
                    raise PublicInstallError("checksum preparation timed out") from error
                if checksum_result.returncode != 0:
                    stderr = checksum_result.stderr.decode(
                        "utf-8", errors="replace"
                    ).strip()
                    raise PublicInstallError(
                        "commit-pinned Maven checksum preparation failed"
                        + (f": {stderr}" if stderr else "")
                    )
                staged_coordinate = _staged_coordinate(staged_repository)
                _assert_directory_binding(repository, repository_descriptor)
                _publish_staged_coordinate(
                    staged_coordinate,
                    repository_descriptor,
                )
                _assert_directory_binding(repository, repository_descriptor)
        except KeyboardInterrupt as error:
            raise PublicInstallError(
                "installation was interrupted after target reservation"
            ) from error
        except PublicInstallError:
            raise
        except OSError as error:
            raise PublicInstallError(
                "a local operation failed after target reservation"
            ) from error
    except PublicInstallError as error:
        raise PublicInstallError(
            f"{error}; {_retained_residue_message(repository)}"
        ) from error
    finally:
        os.close(repository_descriptor)
    print(
        "ROUTECONTRACT_PUBLIC_INSTALL_OK "
        f"version={VERSION} repository={repository} "
        f"tagObjectAnchor={TAG_OBJECT} releaseCommit={RELEASE_COMMIT}"
    )
    print(f"Authoritative immutable Release: {RELEASE_URL}")
    print(
        "The delegated installer retains its 2026-12-05 UTC evidence-review expiry; "
        "this helper does not bypass it."
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download and install the exact public RouteContract v0.1.2 Release "
            "into a new explicit Maven repository without a GitHub login, "
            "token, or API call."
        )
    )
    parser.add_argument(
        "--repository",
        required=True,
        help=(
            "absolute, normalized, absent target Maven repository; symlinked "
            "parents such as macOS /tmp are canonicalized before reservation; "
            "~/.m2/repository is rejected by the tag-pinned installer"
        ),
    )
    return parser.parse_args(argv)


def run(argv: list[str]) -> int:
    if sys.version_info < (3, 10):
        raise PublicInstallError("Python 3.10 or newer is required")
    arguments = parse_args(argv)
    repository = _validate_repository_argument(arguments.repository)
    install_public_release(repository)
    return 0


def main() -> int:
    try:
        return run(sys.argv[1:])
    except (PublicInstallError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
