#!/usr/bin/env python3
"""Install a checksummed RouteContract GitHub Release into an explicit Maven repo.

This script deliberately has no default repository and performs no network
access. Download the exact public GitHub Release assets into one directory,
then pass that directory and an isolated, absolute Maven repository path.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


ARTIFACT_ID = "routecontract-shardingsphere-5.5"
POM_NAME = f"{ARTIFACT_ID}.pom"
CHECKSUMS_NAME = "SHA256SUMS"
EXPECTED_MODULE_NAME = "io.github.ym0506.routecontract.shardingsphere55"
EXPECTED_PROVIDER = (
    "io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook"
)
EXPECTED_GROUP_ID = "io.github.ym0506.routecontract"
EXPECTED_PACKAGE_PREFIX = "io/github/ym0506/routecontract/"
ROUTECONTRACT_PACKAGE_PATTERN = re.compile(
    r"io/github/[^/]+/routecontract/"
)
MULTI_RELEASE_ENTRY_PATTERN = re.compile(
    r"META-INF/versions/[1-9][0-9]*/(.+)"
)
SERVICE_DESCRIPTOR = (
    "META-INF/services/"
    "org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook"
)
VERSION_PART = r"(?:0|[1-9][0-9]{0,8})"
VERSION_PATTERN = re.compile(rf"{VERSION_PART}\.{VERSION_PART}\.{VERSION_PART}")
CHECKSUM_LINE_PATTERN = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]*)")
MAX_POM_BYTES = 1024 * 1024
MAX_CHECKSUM_BYTES = 1024 * 1024
MAX_JAR_BYTES = 100 * 1024 * 1024
MAX_JAR_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


class InstallError(RuntimeError):
    """A validation or safe-install failure suitable for a concise CLI error."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def absolute_path(raw: str, label: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise InstallError(f"{label} must be an explicit absolute path")
    return path


def require_flat_regular_files(directory: Path) -> dict[str, Path]:
    if directory.is_symlink() or not directory.is_dir():
        raise InstallError("release assets path must be a real directory, not a symlink")
    files: dict[str, Path] = {}
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file():
            raise InstallError(
                f"release assets must be a flat set of regular files: {path.name}"
            )
        files[path.name] = path
    return files


def parse_checksums(path: Path) -> dict[str, str]:
    if path.stat().st_size > MAX_CHECKSUM_BYTES:
        raise InstallError("SHA256SUMS exceeds the 1 MiB safety limit")
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        raise InstallError("SHA256SUMS must end with a newline")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise InstallError("SHA256SUMS must contain ASCII only") from error
    checksums: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        match = CHECKSUM_LINE_PATTERN.fullmatch(line)
        if match is None:
            raise InstallError(f"invalid SHA256SUMS line {number}: {line!r}")
        digest, filename = match.groups()
        if filename == CHECKSUMS_NAME or filename in checksums:
            raise InstallError(f"duplicate or recursive SHA256SUMS entry: {filename}")
        checksums[filename] = digest
    if not checksums:
        raise InstallError("SHA256SUMS is empty")
    return checksums


def verify_checksum(path: Path, expected: str) -> None:
    actual = sha256(path)
    if not hmac.compare_digest(actual, expected):
        raise InstallError(
            f"checksum mismatch for {path.name}: expected {expected}, got {actual}"
        )


def direct_xml_value(root: ET.Element, name: str) -> str:
    values = [
        (child.text or "").strip()
        for child in root
        if child.tag.rsplit("}", 1)[-1] == name
    ]
    if len(values) != 1 or not values[0]:
        raise InstallError(f"release POM must contain exactly one non-empty {name}")
    return values[0]


def optional_direct_xml_value(root: ET.Element, name: str) -> str | None:
    values = [
        (child.text or "").strip()
        for child in root
        if child.tag.rsplit("}", 1)[-1] == name
    ]
    if len(values) > 1 or (values and not values[0]):
        raise InstallError(f"release POM contains an invalid {name}")
    return values[0] if values else None


def parse_coordinate(path: Path) -> tuple[str, str]:
    if path.stat().st_size > MAX_POM_BYTES:
        raise InstallError("release POM exceeds the 1 MiB safety limit")
    raw = path.read_bytes()
    uppercase = raw.upper()
    if b"<!DOCTYPE" in uppercase or b"<!ENTITY" in uppercase:
        raise InstallError("release POM must not contain a DTD or entity declaration")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise InstallError(f"release POM is not valid XML: {error}") from error
    if root.tag.rsplit("}", 1)[-1] != "project":
        raise InstallError("release POM root element must be project")
    if direct_xml_value(root, "modelVersion") != "4.0.0":
        raise InstallError("release POM modelVersion must be 4.0.0")
    group = direct_xml_value(root, "groupId")
    artifact = direct_xml_value(root, "artifactId")
    version = direct_xml_value(root, "version")
    packaging = optional_direct_xml_value(root, "packaging")
    if group != EXPECTED_GROUP_ID:
        raise InstallError(
            f"release POM groupId must be exactly {EXPECTED_GROUP_ID}"
        )
    if artifact != ARTIFACT_ID:
        raise InstallError(
            f"release POM artifactId must be exactly {ARTIFACT_ID}, got {artifact!r}"
        )
    if VERSION_PATTERN.fullmatch(version) is None:
        raise InstallError(
            "release POM version must be a stable MAJOR.MINOR.PATCH value"
        )
    if packaging not in (None, "jar"):
        raise InstallError("release POM packaging must be jar when specified")
    return group, version


def expected_public_payloads(version: str) -> set[str]:
    return {
        f"{ARTIFACT_ID}-{version}.jar",
        f"{ARTIFACT_ID}-{version}-sources.jar",
        f"{ARTIFACT_ID}-{version}-javadoc.jar",
        POM_NAME,
        f"{ARTIFACT_ID}-cyclonedx.json",
        f"{ARTIFACT_ID}-cyclonedx.xml",
        "routecontract-aggregate-cyclonedx.json",
        "routecontract-aggregate-cyclonedx.xml",
        "test-summary.txt",
        f"routecontract-{version}-source.zip",
    }


def validate_checksum_allowlist(
    checksums: dict[str, str], public_payloads: set[str]
) -> None:
    declared = set(checksums)
    missing = public_payloads - declared
    unexpected = declared - public_payloads
    if missing or unexpected:
        raise InstallError(
            "SHA256SUMS violates the public Release checksum allowlist; "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )


def parse_jar_main_manifest(raw: bytes) -> dict[str, str]:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise InstallError(f"main JAR manifest is not valid UTF-8: {error}") from error
    unfolded: list[str] = []
    for line in text.splitlines():
        if line.startswith(" "):
            if not unfolded or unfolded[-1] == "":
                raise InstallError("main JAR manifest has an orphan continuation line")
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)

    attributes: dict[str, str] = {}
    for line in unfolded:
        if line == "":
            break
        if ": " not in line:
            raise InstallError(f"main JAR manifest has an invalid header: {line!r}")
        name, value = line.split(": ", 1)
        normalized = name.casefold()
        if not name or normalized in attributes:
            raise InstallError(f"main JAR manifest has a duplicate header: {name!r}")
        attributes[normalized] = value
    return attributes


def validate_archive(
    path: Path, *, required_entries: set[str], label: str
) -> None:
    if path.stat().st_size > MAX_JAR_BYTES:
        raise InstallError(f"{label} exceeds the 100 MiB safety limit")
    try:
        with ZipFile(path) as archive:
            infos = archive.infolist()
            if not infos:
                raise InstallError(f"{label} is empty")
            names: set[str] = set()
            uncompressed = 0
            for info in infos:
                pure = PurePosixPath(info.filename)
                unix_mode = info.external_attr >> 16
                if (
                    not info.filename
                    or "\\" in info.filename
                    or pure.is_absolute()
                    or ".." in pure.parts
                    or stat.S_ISLNK(unix_mode)
                    or info.flag_bits & 0x1
                ):
                    raise InstallError(f"{label} contains an unsafe entry: {info.filename}")
                if info.filename in names:
                    raise InstallError(f"{label} contains a duplicate entry: {info.filename}")
                names.add(info.filename)
                uncompressed += info.file_size
                if uncompressed > MAX_JAR_UNCOMPRESSED_BYTES:
                    raise InstallError(
                        f"{label} exceeds the 200 MiB uncompressed safety limit"
                    )
            missing = required_entries - names
            if missing:
                raise InstallError(f"{label} is missing required entries: {sorted(missing)}")
            unexpected_namespaces: list[str] = []
            for name in names:
                multi_release = MULTI_RELEASE_ENTRY_PATTERN.fullmatch(name)
                package_path = multi_release.group(1) if multi_release else name
                if (
                    ROUTECONTRACT_PACKAGE_PATTERN.match(package_path)
                    and not package_path.startswith(EXPECTED_PACKAGE_PREFIX)
                ):
                    unexpected_namespaces.append(name)
            unexpected_namespaces.sort()
            if unexpected_namespaces:
                raise InstallError(
                    f"{label} contains an unexpected RouteContract package namespace: "
                    f"{unexpected_namespaces}"
                )
            bad_entry = archive.testzip()
            if bad_entry is not None:
                raise InstallError(f"{label} has a CRC failure in {bad_entry}")
            if label == "main JAR":
                manifest = parse_jar_main_manifest(
                    archive.read("META-INF/MANIFEST.MF")
                )
                if manifest.get("manifest-version") != "1.0":
                    raise InstallError("main JAR manifest has an unexpected Manifest-Version")
                if manifest.get("automatic-module-name") != EXPECTED_MODULE_NAME:
                    raise InstallError("main JAR has an unexpected Automatic-Module-Name")
                providers = [
                    line.strip()
                    for line in archive.read(SERVICE_DESCRIPTOR)
                    .decode("utf-8", errors="strict")
                    .splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                ]
                if providers != [EXPECTED_PROVIDER]:
                    raise InstallError("main JAR has an unexpected SQLExecutionHook provider")
    except (BadZipFile, UnicodeDecodeError) as error:
        raise InstallError(f"{label} is not a valid RouteContract JAR: {error}") from error


def validate_jars(files: dict[str, Path], version: str) -> None:
    common_entries = {"META-INF/LICENSE", "META-INF/NOTICE"}
    validate_archive(
        files[f"{ARTIFACT_ID}-{version}.jar"],
        label="main JAR",
        required_entries=common_entries
        | {
            "META-INF/MANIFEST.MF",
            SERVICE_DESCRIPTOR,
            "io/github/ym0506/routecontract/RouteContract.class",
        },
    )
    validate_archive(
        files[f"{ARTIFACT_ID}-{version}-sources.jar"],
        label="sources JAR",
        required_entries=common_entries
        | {"io/github/ym0506/routecontract/RouteContract.java"},
    )
    validate_archive(
        files[f"{ARTIFACT_ID}-{version}-javadoc.jar"],
        label="Javadoc JAR",
        required_entries=common_entries
        | {"io/github/ym0506/routecontract/RouteContract.html"},
    )


def paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def install(
    files: dict[str, Path],
    checksums: dict[str, str],
    group: str,
    version: str,
    repository: Path,
) -> Path:
    if repository.is_symlink():
        raise InstallError("target Maven repository must not be a symlink")
    if repository.exists() and not repository.is_dir():
        raise InstallError("target Maven repository exists but is not a directory")
    group_path = Path(*group.split("."))
    checked = repository
    for component in (*group_path.parts, ARTIFACT_ID):
        checked /= component
        if checked.is_symlink():
            raise InstallError(
                f"target Maven coordinate contains a symlink component: {checked}"
            )
        if checked.exists() and not checked.is_dir():
            raise InstallError(
                f"target Maven coordinate contains a non-directory component: {checked}"
            )
    destination = repository / group_path / ARTIFACT_ID / version
    if destination.exists() or destination.is_symlink():
        raise InstallError(f"target Maven coordinate already exists: {destination}")

    destination_parent = destination.parent
    destination_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{version}.install-", dir=destination_parent
    ) as temporary:
        staging = Path(temporary)
        source_names = {
            f"{ARTIFACT_ID}-{version}.jar": f"{ARTIFACT_ID}-{version}.jar",
            f"{ARTIFACT_ID}-{version}-sources.jar": (
                f"{ARTIFACT_ID}-{version}-sources.jar"
            ),
            f"{ARTIFACT_ID}-{version}-javadoc.jar": (
                f"{ARTIFACT_ID}-{version}-javadoc.jar"
            ),
            POM_NAME: f"{ARTIFACT_ID}-{version}.pom",
        }
        for source_name, destination_name in source_names.items():
            shutil.copyfile(files[source_name], staging / destination_name)
            if not hmac.compare_digest(
                checksums[source_name], sha256(staging / destination_name)
            ):
                raise InstallError(
                    f"copy no longer matches the declared checksum for {source_name}"
                )

        try:
            destination.mkdir()
        except FileExistsError as error:
            raise InstallError(f"target Maven coordinate already exists: {destination}") from error
        try:
            for staged in staging.iterdir():
                os.replace(staged, destination / staged.name)
        except OSError:
            shutil.rmtree(destination, ignore_errors=True)
            raise
    return destination


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify exact RouteContract public release assets and install the JAR/POM "
            "into an explicit local Maven repository without network access."
        )
    )
    parser.add_argument(
        "--release-assets-dir",
        required=True,
        help="absolute directory containing the downloaded public GitHub Release assets",
    )
    parser.add_argument(
        "--repository",
        required=True,
        help="absolute target Maven repository; there is intentionally no ~/.m2 default",
    )
    return parser.parse_args(argv)


def run(argv: list[str]) -> int:
    args = parse_args(argv)
    assets_argument = absolute_path(args.release_assets_dir, "release assets directory")
    repository_argument = absolute_path(args.repository, "target Maven repository")
    if assets_argument.is_symlink():
        raise InstallError("release assets directory must not be a symlink")
    if repository_argument.is_symlink():
        raise InstallError("target Maven repository must not be a symlink")
    assets = assets_argument.resolve(strict=True)
    repository = repository_argument.resolve(strict=False)
    if paths_overlap(assets, repository):
        raise InstallError("release assets and target Maven repository must not overlap")

    files = require_flat_regular_files(assets)
    for required_name in (CHECKSUMS_NAME, POM_NAME):
        if required_name not in files:
            raise InstallError(f"release assets are missing {required_name}")
    checksums = parse_checksums(files[CHECKSUMS_NAME])
    if POM_NAME not in checksums:
        raise InstallError(f"SHA256SUMS does not declare {POM_NAME}")
    verify_checksum(files[POM_NAME], checksums[POM_NAME])
    group, version = parse_coordinate(files[POM_NAME])

    public_payloads = expected_public_payloads(version)
    expected_directory = public_payloads | {CHECKSUMS_NAME}
    actual_directory = set(files)
    if actual_directory != expected_directory:
        raise InstallError(
            "release directory violates the exact public release allowlist; "
            f"missing={sorted(expected_directory - actual_directory)}, "
            f"unexpected={sorted(actual_directory - expected_directory)}"
        )
    validate_checksum_allowlist(checksums, public_payloads)
    for filename in sorted(public_payloads):
        verify_checksum(files[filename], checksums[filename])
    validate_jars(files, version)

    destination = install(files, checksums, group, version, repository)
    print(f"Installed coordinate: {group}:{ARTIFACT_ID}:{version}")
    print(f"Explicit Maven repository: {repository}")
    print(f"Installed files: {destination}")
    print("No default Maven repository was read or modified by this installer.")
    return 0


def main() -> int:
    try:
        return run(sys.argv[1:])
    except (InstallError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
