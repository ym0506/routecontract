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
import unicodedata
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
    r"io/github/(?:[^/]+/)*routecontract/"
)
MULTI_RELEASE_ENTRY_PATTERN = re.compile(
    r"META-INF/versions/[1-9][0-9]*/(.+)"
)
SERVICE_DESCRIPTOR = (
    "META-INF/services/"
    "org.apache.shardingsphere.infra.executor.sql.hook.SQLExecutionHook"
)
VERSION_PART = r"(?:0|[1-9][0-9]{0,8})"
RELEASE_VERSION_PATTERN = re.compile(
    rf"{VERSION_PART}\.{VERSION_PART}\.{VERSION_PART}(?:-rc[1-9][0-9]{{0,5}})?"
)
CHECKSUM_LINE_PATTERN = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]*)")
JAVA_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
MAX_POM_BYTES = 1024 * 1024
MAX_CHECKSUM_BYTES = 1024 * 1024
MAX_JAR_BYTES = 100 * 1024 * 1024
MAX_JAR_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_SOURCE_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_SOURCE_ARCHIVE_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_SOURCE_ARCHIVE_ENTRIES = 20_000
MAX_SOURCE_TEXT_BYTES = 5 * 1024 * 1024
SOURCE_PUBLIC_API_PATH = (
    "routecontract-shardingsphere-5.5/src/main/java/"
    "io/github/ym0506/routecontract/RouteContract.java"
)
SOURCE_HOOK_PATH = (
    "routecontract-shardingsphere-5.5/src/main/java/"
    "io/github/ym0506/routecontract/internal/"
    "RouteContractSqlExecutionHook.java"
)
SOURCE_SERVICE_DESCRIPTOR_PATH = (
    "routecontract-shardingsphere-5.5/src/main/resources/" + SERVICE_DESCRIPTOR
)
SOURCE_REQUIRED_PATHS = {
    "README.md",
    "LICENSE",
    "build.gradle",
    "settings.gradle",
    "gradlew",
    "scripts/install-release-assets.py",
    SOURCE_PUBLIC_API_PATH,
    SOURCE_HOOK_PATH,
    SOURCE_SERVICE_DESCRIPTOR_PATH,
}
SOURCE_FORBIDDEN_PARTS = {
    ".agents",
    ".codex",
    ".git",
    ".gradle",
    ".idea",
    "__pycache__",
    "build",
    "out",
    "private_codex",
    "private_notes",
}
SOURCE_FORBIDDEN_PREFIXES = (
    "submission/draft",
    "submission/final",
    "submission/package",
    "submission/private",
)
SOURCE_FORBIDDEN_SUFFIXES = (".pyc", ".pyo", ".pem", ".key", ".p12", ".pfx", ".jks")
WINDOWS_FORBIDDEN_CHARACTERS = frozenset('<>:"|?*')
WINDOWS_RESERVED_BASENAMES = {
    "aux",
    "clock$",
    "con",
    "conin$",
    "conout$",
    "nul",
    "prn",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
    *(f"com{number}" for number in ("¹", "²", "³")),
    *(f"lpt{number}" for number in ("¹", "²", "³")),
}


class InstallError(RuntimeError):
    """A validation or safe-install failure suitable for a concise CLI error."""


def portable_source_parts(parts: tuple[str, ...], path: str) -> tuple[str, ...]:
    """Return a Windows-portable NFC/casefold key or reject unsafe segments."""
    result: list[str] = []
    for part in parts:
        normalized = unicodedata.normalize("NFC", part)
        if normalized.endswith((".", " ")):
            raise InstallError(
                f"source archive path is not portable across filesystems: {path}"
            )
        if any(character in WINDOWS_FORBIDDEN_CHARACTERS for character in normalized):
            raise InstallError(
                f"source archive path is not portable across filesystems: {path}"
            )
        folded = normalized.casefold()
        if folded in {"", ".", ".."}:
            raise InstallError(
                f"source archive path is not portable across filesystems: {path}"
            )
        basename = folded.split(".", 1)[0]
        if basename in WINDOWS_RESERVED_BASENAMES:
            raise InstallError(
                f"source archive path uses a reserved Windows name: {path}"
            )
        result.append(folded)
    return tuple(result)


def forbidden_source_path(relative: str, parts: tuple[str, ...]) -> bool:
    """Return whether a release source path is private, generated, or credential-like."""
    if any(part in SOURCE_FORBIDDEN_PARTS for part in parts):
        return True
    if any(
        relative == prefix or relative.startswith(f"{prefix}/")
        for prefix in SOURCE_FORBIDDEN_PREFIXES
    ):
        return True
    folded = parts[-1]
    if folded == ".ds_store":
        return True
    if folded == ".env" or (folded.startswith(".env.") and folded != ".env.example"):
        return True
    return folded.endswith(SOURCE_FORBIDDEN_SUFFIXES)


def translate_java_unicode_escapes(source: str, path: str) -> str:
    """Apply Java's pre-tokenization Unicode-escape translation once."""
    translated: list[str] = []
    index = 0
    last_output_from_unicode_escape = False
    trailing_output_backslashes = 0
    while index < len(source):
        character = source[index]
        if character != "\\":
            translated.append(character)
            last_output_from_unicode_escape = False
            trailing_output_backslashes = 0
            index += 1
            continue
        eligible = (
            last_output_from_unicode_escape
            or trailing_output_backslashes % 2 == 0
        )
        if eligible and index + 1 < len(source) and source[index + 1] == "u":
            digits = index + 1
            while digits < len(source) and source[digits] == "u":
                digits += 1
            escape = source[digits : digits + 4]
            if len(escape) != 4 or any(
                character not in "0123456789abcdefABCDEF" for character in escape
            ):
                raise InstallError(
                    f"source archive Java file has a malformed Unicode escape: {path}"
                )
            character = chr(int(escape, 16))
            translated.append(character)
            index = digits + 4
            last_output_from_unicode_escape = True
            trailing_output_backslashes = (
                trailing_output_backslashes + 1 if character == "\\" else 0
            )
            continue
        translated.append(character)
        last_output_from_unicode_escape = False
        trailing_output_backslashes += 1
        index += 1
    return "".join(translated)


def java_tokens(source: str, path: str) -> list[str]:
    """Tokenize enough Java syntax to validate packages and one top-level class."""
    source = translate_java_unicode_escapes(source, path)
    tokens: list[str] = []
    index = 1 if source.startswith("\ufeff") else 0
    while index < len(source):
        character = source[index]
        if character.isspace():
            index += 1
            continue
        if source.startswith("//", index):
            line_feed = source.find("\n", index + 2)
            carriage_return = source.find("\r", index + 2)
            endings = [position for position in (line_feed, carriage_return) if position >= 0]
            if not endings:
                index = len(source)
                continue
            line_end = min(endings)
            index = line_end + 1
            if source[line_end] == "\r" and index < len(source) and source[index] == "\n":
                index += 1
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end < 0:
                raise InstallError(f"source archive Java file has an unterminated comment: {path}")
            index = end + 2
            continue
        if source.startswith('"""', index):
            index += 3
            while True:
                end = source.find('"""', index)
                if end < 0:
                    raise InstallError(
                        f"source archive Java file has an unterminated text block: {path}"
                    )
                backslashes = 0
                cursor = end - 1
                while cursor >= index and source[cursor] == "\\":
                    backslashes += 1
                    cursor -= 1
                if backslashes % 2 == 0:
                    index = end + 3
                    break
                index = end + 3
            tokens.append("<literal>")
            continue
        if character in {'"', "'"}:
            quote = character
            index += 1
            while index < len(source):
                if source[index] == "\\":
                    index += 2
                    continue
                if source[index] == quote:
                    index += 1
                    break
                index += 1
            else:
                raise InstallError(
                    f"source archive Java file has an unterminated literal: {path}"
                )
            tokens.append("<literal>")
            continue
        identifier = JAVA_IDENTIFIER_PATTERN.match(source, index)
        if identifier is not None:
            tokens.append(identifier.group(0))
            index = identifier.end()
            continue
        tokens.append(character)
        index += 1
    return tokens


def declared_java_package(tokens: list[str], path: str) -> str | None:
    """Read the active package declaration at the start of a Java compilation unit."""
    filename = PurePosixPath(path).name
    if filename == "module-info.java":
        if not tokens or tokens[0] not in {"module", "open"}:
            raise InstallError(
                f"source archive module descriptor has unexpected leading syntax: {path}"
            )
        return None
    if not tokens or tokens[0] != "package":
        raise InstallError(
            f"source archive Java file has no active leading package declaration: {path}"
        )
    segments: list[str] = []
    index = 1
    expect_identifier = True
    while index < len(tokens):
        token = tokens[index]
        if expect_identifier:
            if JAVA_IDENTIFIER_PATTERN.fullmatch(token) is None:
                break
            segments.append(token)
            expect_identifier = False
        elif token == ".":
            expect_identifier = True
        elif token == ";":
            return ".".join(segments)
        else:
            break
        index += 1
    raise InstallError(f"source archive Java file has an invalid package declaration: {path}")


def expected_java_package(path: str) -> str | None:
    """Derive a Java package from a conventional Gradle source path."""
    parts = PurePosixPath(path).parts
    matches: list[int] = []
    for index in range(len(parts) - 2):
        if parts[index : index + 3] in (
            ("src", "main", "java"),
            ("src", "test", "java"),
        ):
            matches.append(index)
    if not matches:
        return None
    if len(matches) != 1:
        raise InstallError(f"source archive Java path has an ambiguous source root: {path}")
    source_relative = parts[matches[0] + 3 :]
    if len(source_relative) < 1 or not source_relative[-1].endswith(".java"):
        raise InstallError(f"source archive Java path is malformed: {path}")
    return ".".join(source_relative[:-1])


def read_archive_text(
    archive: ZipFile, archive_name: str, label: str, *, limit: int = MAX_SOURCE_TEXT_BYTES
) -> str:
    info = archive.getinfo(archive_name)
    if info.file_size > limit:
        raise InstallError(f"{label} exceeds the {limit}-byte text safety limit")
    try:
        return archive.read(info).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise InstallError(f"{label} is not valid UTF-8: {error}") from error


def has_top_level_hook_class(tokens: list[str]) -> bool:
    """Find the exact public SPI provider declaration at top-level brace depth."""
    expected = (
        "public",
        "final",
        "class",
        "RouteContractSqlExecutionHook",
        "implements",
        "SQLExecutionHook",
    )
    depth = 0
    for index, token in enumerate(tokens):
        if token == "{":
            depth += 1
            continue
        if token == "}":
            depth = max(0, depth - 1)
            continue
        if depth == 0 and tuple(tokens[index : index + len(expected)]) == expected:
            body = index + len(expected)
            if body >= len(tokens) or tokens[body] != "{":
                continue
            body_depth = 1
            for body_token in tokens[body + 1 :]:
                if body_token == "{":
                    body_depth += 1
                elif body_token == "}":
                    body_depth -= 1
                    if body_depth == 0:
                        return True
            return False
    return False


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
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise InstallError("release POM must be valid UTF-8 XML") from error
    uppercase = text.upper()
    if "<!DOCTYPE" in uppercase or "<!ENTITY" in uppercase:
        raise InstallError("release POM must not contain a DTD or entity declaration")
    try:
        # Parse the original bytes after the strict UTF-8 preflight so an XML
        # declaration that claims another encoding cannot be silently ignored.
        root = ET.fromstring(raw)
    except (ET.ParseError, LookupError) as error:
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
    if RELEASE_VERSION_PATTERN.fullmatch(version) is None:
        raise InstallError(
            "release POM version must be MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-rcN"
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
                portable_package_path = unicodedata.normalize(
                    "NFC", package_path
                ).casefold()
                portable_candidates = list(
                    ROUTECONTRACT_PACKAGE_PATTERN.finditer(portable_package_path)
                )
                exact_candidates = list(
                    ROUTECONTRACT_PACKAGE_PATTERN.finditer(package_path)
                )
                if portable_candidates and (
                    len(portable_candidates) != len(exact_candidates)
                    or any(
                        match.group(0) != EXPECTED_PACKAGE_PREFIX
                        for match in exact_candidates
                    )
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


def validate_source_archive(path: Path, version: str) -> None:
    """Validate bounded source-archive structure, not Git-tree provenance."""
    if path.stat().st_size > MAX_SOURCE_ARCHIVE_BYTES:
        raise InstallError("source archive exceeds the 100 MiB safety limit")
    expected_root = f"routecontract-{version}"
    try:
        with ZipFile(path) as archive:
            infos = archive.infolist()
            if not infos:
                raise InstallError("source archive is empty")
            if len(infos) > MAX_SOURCE_ARCHIVE_ENTRIES:
                raise InstallError("source archive exceeds the 20000-entry safety limit")
            logical_entries: dict[str, bool] = {}
            portable_entries: dict[str, str] = {}
            source_files: set[str] = set()
            uncompressed = 0
            unexpected_namespaces: list[str] = []
            for info in infos:
                original_name = getattr(info, "orig_filename", info.filename)
                if original_name != info.filename or "\x00" in original_name:
                    raise InstallError(
                        "source archive contains a truncated or NUL-bearing entry name"
                    )
                if any(ord(character) < 32 or ord(character) == 127 for character in info.filename):
                    raise InstallError(
                        f"source archive contains a control character in an entry: {info.filename!r}"
                    )
                pure = PurePosixPath(info.filename)
                unix_mode = info.external_attr >> 16
                unix_type = stat.S_IFMT(unix_mode)
                is_directory = info.is_dir()
                if (
                    not info.filename
                    or "\\" in info.filename
                    or pure.is_absolute()
                    or ".." in pure.parts
                    or info.flag_bits & 0x1
                ):
                    raise InstallError(
                        f"source archive contains an unsafe entry: {info.filename}"
                    )
                canonical_name = PurePosixPath(*pure.parts).as_posix()
                if is_directory:
                    canonical_name += "/"
                if canonical_name != info.filename:
                    raise InstallError(
                        f"source archive contains a non-canonical entry name: {info.filename}"
                    )
                if is_directory:
                    if unix_type not in (0, stat.S_IFDIR):
                        raise InstallError(
                            f"source archive directory has an incompatible Unix type: {info.filename}"
                        )
                    if info.file_size != 0 or info.compress_size != 0:
                        raise InstallError(
                            f"source archive directory contains a payload: {info.filename}"
                        )
                elif unix_type not in (0, stat.S_IFREG):
                    raise InstallError(
                        f"source archive contains a special or mismatched Unix entry: {info.filename}"
                    )
                logical_name = canonical_name.rstrip("/")
                if logical_name in logical_entries:
                    raise InstallError(
                        f"source archive contains a duplicate logical path: {logical_name}"
                    )
                logical_entries[logical_name] = is_directory
                portable_parts = portable_source_parts(
                    PurePosixPath(logical_name).parts, logical_name
                )
                portable_name = PurePosixPath(*portable_parts).as_posix()
                logical_parts = PurePosixPath(logical_name).parts
                for length in range(1, len(logical_parts) + 1):
                    logical_prefix = PurePosixPath(
                        *logical_parts[:length]
                    ).as_posix()
                    portable_prefix = PurePosixPath(
                        *portable_parts[:length]
                    ).as_posix()
                    previous = portable_entries.get(portable_prefix)
                    if previous is not None and previous != logical_prefix:
                        raise InstallError(
                            "source archive contains a case or Unicode-normalization "
                            f"path collision: {previous!r}, {logical_prefix!r}"
                        )
                    portable_entries[portable_prefix] = logical_prefix
                uncompressed += info.file_size
                if uncompressed > MAX_SOURCE_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise InstallError(
                        "source archive exceeds the 200 MiB uncompressed safety limit"
                    )
                if not pure.parts or pure.parts[0] != expected_root:
                    raise InstallError(
                        "source archive must contain exactly one versioned root "
                        f"{expected_root}/"
                    )
                relative_parts = pure.parts[1:]
                if not relative_parts:
                    if not is_directory:
                        raise InstallError(
                            "source archive root entry must be a directory"
                        )
                    continue
                relative = PurePosixPath(*relative_parts).as_posix()
                portable_relative_parts = portable_parts[1:]
                portable_relative = PurePosixPath(
                    *portable_relative_parts
                ).as_posix()
                if forbidden_source_path(
                    portable_relative, portable_relative_parts
                ):
                    raise InstallError(
                        f"source archive contains a private or generated path: {relative}"
                    )
                portable_relative = unicodedata.normalize("NFC", relative).casefold()
                portable_candidates = list(
                    ROUTECONTRACT_PACKAGE_PATTERN.finditer(portable_relative)
                )
                exact_candidates = list(
                    ROUTECONTRACT_PACKAGE_PATTERN.finditer(relative)
                )
                if portable_candidates and (
                    len(portable_candidates) != len(exact_candidates)
                    or any(
                        match.group(0) != EXPECTED_PACKAGE_PREFIX
                        for match in exact_candidates
                    )
                ):
                    unexpected_namespaces.append(relative)
                if is_directory:
                    continue
                source_files.add(relative)
            for logical_name, is_directory in logical_entries.items():
                parts = PurePosixPath(logical_name).parts
                for length in range(1, len(parts)):
                    ancestor = PurePosixPath(*parts[:length]).as_posix()
                    if ancestor in logical_entries and not logical_entries[ancestor]:
                        raise InstallError(
                            "source archive contains a file/descendant path collision: "
                            f"{ancestor!r}, {logical_name!r}"
                        )
            for portable_name, logical_name in portable_entries.items():
                parts = PurePosixPath(portable_name).parts
                for length in range(1, len(parts)):
                    portable_ancestor = PurePosixPath(*parts[:length]).as_posix()
                    ancestor_name = portable_entries.get(portable_ancestor)
                    if logical_entries.get(ancestor_name) is False:
                        raise InstallError(
                            "source archive contains a case or Unicode-normalization "
                            "file/descendant collision: "
                            f"{ancestor_name!r}, {logical_name!r}"
                        )
            if unexpected_namespaces:
                raise InstallError(
                    "source archive contains an unexpected RouteContract package "
                    f"namespace: {sorted(unexpected_namespaces)}"
                )
            missing = SOURCE_REQUIRED_PATHS - source_files
            if missing:
                raise InstallError(
                    f"source archive is missing canonical source paths: {sorted(missing)}"
                )
            java_token_map: dict[str, list[str]] = {}
            for relative in sorted(source_files):
                expected_package = expected_java_package(relative)
                if expected_package is None:
                    continue
                archive_name = f"{expected_root}/{relative}"
                source = read_archive_text(
                    archive,
                    archive_name,
                    f"source archive Java file {relative}",
                )
                tokens = java_tokens(source, relative)
                java_token_map[relative] = tokens
                declared_package = declared_java_package(tokens, relative)
                if PurePosixPath(relative).name == "module-info.java":
                    if expected_package:
                        raise InstallError(
                            f"source archive module descriptor is not at a source root: {relative}"
                        )
                elif declared_package != expected_package:
                    if relative == SOURCE_PUBLIC_API_PATH:
                        raise InstallError(
                            "source archive public API has an unexpected package declaration"
                        )
                    if relative == SOURCE_HOOK_PATH:
                        raise InstallError(
                            "source archive hook has an unexpected package declaration"
                        )
                    raise InstallError(
                        "source archive Java package does not match its path: "
                        f"{relative}"
                    )
            public_api_tokens = java_token_map[SOURCE_PUBLIC_API_PATH]
            if declared_java_package(public_api_tokens, SOURCE_PUBLIC_API_PATH) != (
                "io.github.ym0506.routecontract"
            ):
                raise InstallError(
                    "source archive public API has an unexpected package declaration"
                )
            hook_tokens = java_token_map[SOURCE_HOOK_PATH]
            if declared_java_package(hook_tokens, SOURCE_HOOK_PATH) != (
                "io.github.ym0506.routecontract.internal"
            ):
                raise InstallError(
                    "source archive hook has an unexpected package declaration"
                )
            if not has_top_level_hook_class(hook_tokens):
                raise InstallError(
                    "source archive hook does not declare the expected top-level SPI class"
                )
            source_providers = [
                line.strip()
                for line in read_archive_text(
                    archive,
                    f"{expected_root}/{SOURCE_SERVICE_DESCRIPTOR_PATH}",
                    "source archive SQLExecutionHook descriptor",
                    limit=64 * 1024,
                ).splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
            if source_providers != [EXPECTED_PROVIDER]:
                raise InstallError(
                    "source archive has an unexpected SQLExecutionHook provider"
                )
            bad_entry = archive.testzip()
            if bad_entry is not None:
                raise InstallError(f"source archive has a CRC failure in {bad_entry}")
    except (BadZipFile, NotImplementedError) as error:
        raise InstallError(f"source archive is not a valid ZIP: {error}") from error


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
    conventional_default_repository = (
        Path.home() / ".m2" / "repository"
    ).resolve(strict=False)
    repository_key = tuple(
        unicodedata.normalize("NFC", part).casefold() for part in repository.parts
    )
    conventional_default_key = tuple(
        unicodedata.normalize("NFC", part).casefold()
        for part in conventional_default_repository.parts
    )
    if repository_key[: len(conventional_default_key)] == conventional_default_key:
        raise InstallError(
            "target Maven repository must not be the conventional "
            "~/.m2/repository or any path below it"
        )
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
    validate_source_archive(
        files[f"routecontract-{version}-source.zip"], version
    )
    validate_jars(files, version)

    destination = install(files, checksums, group, version, repository)
    print(f"Installed coordinate: {group}:{ARTIFACT_ID}:{version}")
    print(f"Explicit Maven repository: {repository}")
    print(f"Installed files: {destination}")
    print("No artifacts were installed under the conventional ~/.m2/repository.")
    return 0


def main() -> int:
    try:
        return run(sys.argv[1:])
    except (InstallError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
