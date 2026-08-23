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
import json
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

try:
    import pwd
except ImportError:  # pragma: no cover - unavailable on Windows
    pwd = None  # type: ignore[assignment]


ARTIFACT_ID = "routecontract-shardingsphere-5.5"
POM_NAME = f"{ARTIFACT_ID}.pom"
CHECKSUMS_NAME = "SHA256SUMS"
SUPPLY_CHAIN_EVIDENCE_NAME = "supply-chain-evidence.json"
EXPECTED_MODULE_NAME = "io.github.ym0506.routecontract.shardingsphere55"
EXPECTED_PROVIDER = (
    "io.github.ym0506.routecontract.internal.RouteContractSqlExecutionHook"
)
EXPECTED_GROUP_ID = "io.github.ym0506.routecontract"
EXPECTED_PACKAGE_PREFIX = "io/github/ym0506/routecontract/"
ROUTECONTRACT_PACKAGE_PATTERN = re.compile(
    r"io/github/(?:[^/]+/)*routecontract/"
)
FORBIDDEN_DISTRIBUTION_PACKAGE_PARTS = (
    ("org", "locationtech", "jts"),
    ("org", "apache", "mahout"),
)
FORBIDDEN_DISTRIBUTION_ARTIFACT_PATTERN = re.compile(
    r"(?:^|[-_.])(?:jts|mahout)(?:[-_.]|$)"
)
FORBIDDEN_DEPENDENCY_GROUP_PREFIXES = (
    "org.locationtech.jts",
    "org.apache.mahout",
)
MAVEN_LITERAL_COORDINATE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
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
XML_DECLARATION_PATTERN = re.compile(
    r'\A(?:\ufeff)?<\?xml\s+version\s*=\s*(["\'])1\.0\1\s+'
    r'encoding\s*=\s*(["\'])([A-Za-z][A-Za-z0-9._-]*)\2'
    r'(?:\s+standalone\s*=\s*(["\'])(?:yes|no)\4)?\s*\?>'
)
CHECKSUM_LINE_PATTERN = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]*)")
JAVA_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
MAX_POM_BYTES = 1024 * 1024
MAX_CHECKSUM_BYTES = 1024 * 1024
MAX_SUPPLY_CHAIN_EVIDENCE_BYTES = 1024 * 1024
MAX_JAR_BYTES = 100 * 1024 * 1024
MAX_JAR_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_JAR_ENTRIES = 20_000
MAX_JAVADOC_NOTICE_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_ENTRY_NAME_BYTES = 4 * 1024
MAX_ARCHIVE_PATH_COMPONENTS = 256
MAX_ARCHIVE_TOTAL_PATH_COMPONENTS = 100_000
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
    "NOTICE",
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
    ".aws",
    ".codex",
    ".docker",
    ".git",
    ".gnupg",
    ".gradle",
    ".idea",
    ".kube",
    ".ssh",
    "__pycache__",
    "build",
    "out",
    "private_codex",
    "private_notes",
}
SOURCE_FORBIDDEN_FILENAMES = {
    ".netrc",
    ".npmrc",
    ".pypirc",
    "auth.json",
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
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
JAVADOC_LEGAL_ENTRIES = {
    "legal/LICENSE",
    "legal/ADDITIONAL_LICENSE_INFO",
    "legal/ASSEMBLY_EXCEPTION",
    "legal/jquery.md",
    "legal/jqueryUI.md",
}
JAVADOC_STATIC_ENTRIES = {
    "script.js",
    "search.js",
    "stylesheet.css",
    "jquery-ui.overrides.css",
    "resources/glass.png",
    "resources/x.png",
    "script-dir/jquery-3.7.1.min.js",
    "script-dir/jquery-ui.min.js",
    "script-dir/jquery-ui.min.css",
}
JAVADOC_ALLOWED_DIRECTORY_ENTRIES = {
    "META-INF/",
    "io/",
    "io/github/",
    "io/github/ym0506/",
    "io/github/ym0506/routecontract/",
    "io/github/ym0506/routecontract/internal/",
    "io/github/ym0506/routecontract/manifest/",
    "legal/",
    "resources/",
    "script-dir/",
}
JAVADOC_ALLOWED_ROOT_ENTRIES = {
    "allclasses-index.html",
    "allpackages-index.html",
    "constant-values.html",
    "element-list",
    "help-doc.html",
    "index-all.html",
    "index.html",
    "jquery-ui.overrides.css",
    "member-search-index.js",
    "module-search-index.js",
    "overview-summary.html",
    "overview-tree.html",
    "package-search-index.js",
    "script.js",
    "search.js",
    "serialized-form.html",
    "stylesheet.css",
    "tag-search-index.js",
    "type-search-index.js",
}
JAVADOC_ALLOWED_META_INF_ENTRIES = {
    "META-INF/LICENSE",
    "META-INF/MANIFEST.MF",
    "META-INF/NOTICE",
}
JAVADOC_API_HTML_PATTERN = re.compile(
    r"io/github/ym0506/routecontract/"
    r"(?:(?:internal|manifest)/)?[A-Za-z0-9_$.-]+\.html"
)


class InstallError(RuntimeError):
    """A validation or safe-install failure suitable for a concise CLI error."""


def portable_source_parts(
    parts: tuple[str, ...], path: str, *, label: str = "source archive"
) -> tuple[str, ...]:
    """Return a Windows-portable NFC/casefold key or reject unsafe segments."""
    result: list[str] = []
    for part in parts:
        normalized = unicodedata.normalize("NFC", part)
        if normalized.endswith((".", " ")):
            raise InstallError(
                f"{label} path is not portable across filesystems: {path}"
            )
        if any(character in WINDOWS_FORBIDDEN_CHARACTERS for character in normalized):
            raise InstallError(
                f"{label} path is not portable across filesystems: {path}"
            )
        folded = normalized.casefold()
        if folded in {"", ".", ".."}:
            raise InstallError(
                f"{label} path is not portable across filesystems: {path}"
            )
        basename = folded.split(".", 1)[0]
        if basename in WINDOWS_RESERVED_BASENAMES:
            raise InstallError(
                f"{label} path uses a reserved Windows name: {path}"
            )
        result.append(folded)
    return tuple(result)


def register_archive_path(
    logical_name: str,
    is_directory: bool,
    *,
    label: str,
    logical_entries: dict[tuple[str, ...], bool],
    portable_trie: dict[tuple[int, str], tuple[str, int]],
    portable_paths: dict[tuple[str, ...], tuple[str, ...]],
    total_path_components: list[int],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Register one bounded archive path and reject portable-name aliases."""
    if len(logical_name.encode("utf-8")) > MAX_ARCHIVE_ENTRY_NAME_BYTES:
        raise InstallError(f"{label} entry name exceeds the 4096-byte safety limit")
    logical_parts = PurePosixPath(logical_name).parts
    if len(logical_parts) > MAX_ARCHIVE_PATH_COMPONENTS:
        raise InstallError(f"{label} path exceeds the 256-component safety limit")
    total_path_components[0] += len(logical_parts)
    if total_path_components[0] > MAX_ARCHIVE_TOTAL_PATH_COMPONENTS:
        raise InstallError(
            f"{label} exceeds the 100000-total-path-component safety limit"
        )
    if logical_parts in logical_entries:
        raise InstallError(
            f"{label} contains a duplicate logical path: {logical_name}"
        )
    portable_parts = portable_source_parts(
        logical_parts,
        logical_name,
        label=label,
    )
    trie_node = 0
    for logical_component, portable_component in zip(
        logical_parts, portable_parts, strict=True
    ):
        edge = (trie_node, portable_component)
        previous = portable_trie.get(edge)
        if previous is not None and previous[0] != logical_component:
            raise InstallError(
                f"{label} contains a case or Unicode-normalization path collision: "
                f"{previous[0]!r}, {logical_component!r} in {logical_name!r}"
            )
        if previous is None:
            trie_node = len(portable_trie) + 1
            portable_trie[edge] = (logical_component, trie_node)
        else:
            trie_node = previous[1]
    logical_entries[logical_parts] = is_directory
    portable_paths[logical_parts] = portable_parts
    return logical_parts, portable_parts


def validate_archive_path_graph(
    logical_entries: dict[tuple[str, ...], bool],
    portable_paths: dict[tuple[str, ...], tuple[str, ...]],
    *,
    label: str,
) -> None:
    """Reject exact and portable file/descendant collisions in bounded time."""
    portable_entries = {
        portable_paths[logical_parts]: logical_parts
        for logical_parts in logical_entries
    }
    for logical_parts in logical_entries:
        logical_name = PurePosixPath(*logical_parts).as_posix()
        portable_parts = portable_paths[logical_parts]
        for length in range(1, len(logical_parts)):
            logical_ancestor = logical_parts[:length]
            if logical_entries.get(logical_ancestor) is False:
                ancestor_name = PurePosixPath(*logical_ancestor).as_posix()
                raise InstallError(
                    f"{label} contains a file/descendant path collision: "
                    f"{ancestor_name!r}, {logical_name!r}"
                )
            portable_ancestor = portable_entries.get(portable_parts[:length])
            if (
                portable_ancestor is not None
                and logical_entries.get(portable_ancestor) is False
            ):
                ancestor_name = PurePosixPath(*portable_ancestor).as_posix()
                raise InstallError(
                    f"{label} contains a case or Unicode-normalization "
                    "file/descendant collision: "
                    f"{ancestor_name!r}, {logical_name!r}"
                )


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
    if folded in SOURCE_FORBIDDEN_FILENAMES:
        return True
    if folded == ".ds_store":
        return True
    if folded == ".env" or (folded.startswith(".env.") and folded != ".env.example"):
        return True
    return folded.endswith(SOURCE_FORBIDDEN_SUFFIXES)


def crosses_jts_or_mahout_distribution_boundary(path: str) -> bool:
    """Detect JTS/Mahout package paths or JTS/Mahout-named payload files."""
    parts = tuple(
        unicodedata.normalize("NFC", part).casefold()
        for part in PurePosixPath(path).parts
    )
    for package_parts in FORBIDDEN_DISTRIBUTION_PACKAGE_PARTS:
        width = len(package_parts)
        if any(
            parts[index : index + width] == package_parts
            for index in range(len(parts))
        ):
            return True
    if not parts:
        return False
    filename = parts[-1]
    return FORBIDDEN_DISTRIBUTION_ARTIFACT_PATTERN.search(filename) is not None


def is_forbidden_jts_or_mahout_java_package(package_name: str | None) -> bool:
    """Return whether a declared Java package is inside a forbidden namespace."""
    if package_name is None:
        return False
    return any(
        package_name == prefix or package_name.startswith(f"{prefix}.")
        for prefix in FORBIDDEN_DEPENDENCY_GROUP_PREFIXES
    )


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


def scalar_xml_value(element: ET.Element, name: str) -> str:
    if len(element) != 0:
        raise InstallError(f"release POM {name} must not contain nested XML elements")
    raw = element.text or ""
    value = raw.strip(" \t\r\n")
    if not value:
        raise InstallError(f"release POM {name} must be non-empty")
    return value


def direct_xml_value(root: ET.Element, name: str) -> str:
    elements = [
        child for child in root if child.tag.rsplit("}", 1)[-1] == name
    ]
    if len(elements) != 1:
        raise InstallError(f"release POM must contain exactly one non-empty {name}")
    return scalar_xml_value(elements[0], name)


def optional_direct_xml_value(root: ET.Element, name: str) -> str | None:
    elements = [
        child for child in root if child.tag.rsplit("}", 1)[-1] == name
    ]
    if len(elements) > 1:
        raise InstallError(f"release POM contains an invalid {name}")
    return scalar_xml_value(elements[0], name) if elements else None


def validate_pom_distribution_boundary(root: ET.Element) -> None:
    """Reject relocation and direct JTS/Mahout coordinates from the Maven model."""
    if any(child.tag.rsplit("}", 1)[-1] == "parent" for child in root):
        raise InstallError("release POM must not contain a Maven parent")
    if any(
        element.tag.rsplit("}", 1)[-1] == "relocation"
        for element in root.iter()
    ):
        raise InstallError("release POM must not contain Maven relocation")
    for dependency in root.iter():
        if dependency.tag.rsplit("}", 1)[-1] != "dependency":
            continue
        values: dict[str, str] = {}
        for child in dependency:
            name = child.tag.rsplit("}", 1)[-1]
            if name in {"groupId", "artifactId"}:
                if name in values:
                    raise InstallError(
                        f"release POM dependency contains duplicate {name}"
                    )
                values[name] = scalar_xml_value(child, f"dependency {name}")
        if set(values) != {"groupId", "artifactId"} or any(
            MAVEN_LITERAL_COORDINATE_PATTERN.fullmatch(values[name]) is None
            for name in ("groupId", "artifactId")
        ):
            raise InstallError(
                "release POM dependencies must use exactly one literal groupId "
                "and artifactId"
            )
        group_id = unicodedata.normalize("NFC", values.get("groupId", "")).casefold()
        artifact_id = unicodedata.normalize(
            "NFC", values.get("artifactId", "")
        ).casefold()
        forbidden_group = any(
            group_id == prefix or group_id.startswith(f"{prefix}.")
            for prefix in FORBIDDEN_DEPENDENCY_GROUP_PREFIXES
        )
        forbidden_artifact = (
            FORBIDDEN_DISTRIBUTION_ARTIFACT_PATTERN.search(artifact_id) is not None
        )
        if forbidden_group or forbidden_artifact:
            coordinate = f"{values.get('groupId', '')}:{values.get('artifactId', '')}"
            raise InstallError(
                "release POM violates the JTS/Mahout distribution boundary: "
                f"{coordinate}"
            )


def parse_service_descriptor(text: str) -> list[str]:
    """Parse only the CR/LF and ASCII space/tab syntax used by ServiceLoader."""
    providers: list[str] = []
    for line in re.split(r"\r\n?|\n", text):
        candidate = line.split("#", 1)[0].strip(" \t")
        if candidate:
            providers.append(candidate)
    return providers


def parse_coordinate(path: Path) -> tuple[str, str]:
    if path.stat().st_size > MAX_POM_BYTES:
        raise InstallError("release POM exceeds the 1 MiB safety limit")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise InstallError("release POM must be valid UTF-8 XML") from error
    declaration = XML_DECLARATION_PATTERN.match(text)
    if declaration is None or declaration.group(3).casefold() != "utf-8":
        raise InstallError(
            "release POM XML declaration must specify version 1.0 and UTF-8 encoding"
        )
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
    validate_pom_distribution_boundary(root)
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
        SUPPLY_CHAIN_EVIDENCE_NAME,
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


def _strict_json_object(path: Path, label: str) -> dict[str, object]:
    if path.stat().st_size > MAX_SUPPLY_CHAIN_EVIDENCE_BYTES:
        raise InstallError(f"{label} exceeds the 1 MiB safety limit")
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except UnicodeError as error:
        raise InstallError(f"{label} must be valid UTF-8 JSON") from error

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise InstallError(f"{label} contains a duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except (json.JSONDecodeError, RecursionError) as error:
        raise InstallError(f"{label} is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise InstallError(f"{label} must be a JSON object")
    return value


def _exact_json_keys(value: object, expected: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        actual = set(value) if isinstance(value, dict) else set()
        raise InstallError(
            f"{label} keys do not match the release schema; "
            f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
        )
    return value


def _json_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise InstallError(f"{label} must be a lowercase 64-character SHA-256")
    return value


def _json_count(value: object, label: str, *, positive: bool = False) -> int:
    minimum = 1 if positive else 0
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "positive" if positive else "non-negative"
        raise InstallError(f"{label} must be a {qualifier} integer")
    return value


def validate_supply_chain_evidence(files: dict[str, Path]) -> None:
    """Bind the sanitized scan summary to the checksummed public artifacts.

    Final tag/revision provenance is verified by the repository's submission
    gate.  This offline installer independently rejects a malformed summary or
    one whose retained artifact hashes do not describe this exact asset set.
    """
    evidence = _strict_json_object(
        files[SUPPLY_CHAIN_EVIDENCE_NAME], "supply-chain evidence"
    )
    _exact_json_keys(
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
        raise InstallError("unsupported supply-chain evidence schemaVersion")
    for key in ("revision", "sourceTree"):
        value = evidence[key]
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
            raise InstallError(f"supply-chain evidence {key} must be 40 lowercase hex characters")

    aggregate = _exact_json_keys(
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
        raise InstallError("supply-chain evidence licensePolicy must be passed")
    for key in ("componentLicenseCount", "mavenPackageCount", "xmlComponentCount"):
        _json_count(aggregate[key], f"supply-chain evidence sbom.{key}", positive=True)
    for key in ("inventorySha256", "policySha256"):
        _json_digest(aggregate[key], f"supply-chain evidence sbom.{key}")
    unresolved_review_count = _json_count(
        aggregate["unresolvedLicenseReviewCount"],
        "supply-chain evidence sbom.unresolvedLicenseReviewCount",
    )
    if unresolved_review_count != 2:
        raise InstallError(
            "supply-chain evidence must retain exactly two unresolved license reviews"
        )
    reviews = aggregate["licenseReviews"]
    if not isinstance(reviews, list) or len(reviews) != 2:
        raise InstallError("supply-chain evidence must contain exactly two license reviews")
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
    expected_review_contracts = (
        (
            "MYSQL_OCI_PACKAGE_LICENSE_CONCLUSION_INCOMPLETE",
            "mysql",
            "test-container",
        ),
        (
            "JTS_IO_COMMON_REDISTRIBUTION_NOTICE_TREATMENT_UNCONFIRMED",
            "jts-io-common",
            "test-runtime",
        ),
    )
    for index, (raw_review, expected_contract) in enumerate(
        zip(reviews, expected_review_contracts, strict=True)
    ):
        review = _exact_json_keys(
            raw_review, review_keys, f"supply-chain evidence license review {index}"
        )
        expected_rationale, expected_component, expected_scope = expected_contract
        if (
            review["rationaleCode"],
            review["componentName"],
            review["scope"],
        ) != (expected_rationale, expected_component, expected_scope):
            raise InstallError(
                "supply-chain evidence license reviews do not use the exact required order"
            )
        if review["status"] != "manual-review-required":
            raise InstallError("supply-chain evidence license review status is unexpected")
        for key in (
            "action",
            "componentVersion",
            "expires",
            "owner",
            "purl",
            "reviewedAt",
        ):
            if not isinstance(review[key], str) or not review[key]:
                raise InstallError(
                    f"supply-chain evidence license review {index}.{key} must be non-empty text"
                )
    expected_aggregate_hashes = {
        "sha256": sha256(files["routecontract-aggregate-cyclonedx.json"]),
        "xmlSha256": sha256(files["routecontract-aggregate-cyclonedx.xml"]),
    }
    for key, expected in expected_aggregate_hashes.items():
        if _json_digest(aggregate[key], f"supply-chain evidence sbom.{key}") != expected:
            raise InstallError(f"supply-chain evidence sbom.{key} does not match the public asset")

    published = _exact_json_keys(
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
        _json_count(published[key], f"supply-chain evidence publishedModule.{key}", positive=True)
    for key in ("dependencyLockSha256", "resolvedProfileSha256", "runtimeClosureSha256"):
        _json_digest(published[key], f"supply-chain evidence publishedModule.{key}")
    expected_published_hashes = {
        "pomSha256": sha256(files[POM_NAME]),
        "sbomSha256": sha256(files[f"{ARTIFACT_ID}-cyclonedx.json"]),
        "xmlSha256": sha256(files[f"{ARTIFACT_ID}-cyclonedx.xml"]),
    }
    for key, expected in expected_published_hashes.items():
        if _json_digest(published[key], f"supply-chain evidence publishedModule.{key}") != expected:
            raise InstallError(
                f"supply-chain evidence publishedModule.{key} does not match the public asset"
            )

    example = _exact_json_keys(
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
        _json_count(example[key], f"supply-chain evidence exampleProfile.{key}", positive=True)
    for key in ("resolvedProfileSha256", "sbomSha256", "xmlSha256"):
        _json_digest(example[key], f"supply-chain evidence exampleProfile.{key}")

    scanner = _exact_json_keys(
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
    for key in ("binarySha256", "scannerConfigSha256", "scannerLockSha256"):
        _json_digest(scanner[key], f"supply-chain evidence scanner.{key}")
    _json_count(scanner["binarySize"], "supply-chain evidence scanner.binarySize", positive=True)
    if scanner["name"] != "OSV-Scanner" or scanner["platform"] != "linux-x86_64":
        raise InstallError("supply-chain evidence scanner identity/platform is unexpected")
    for key in ("version", "scalibrVersion", "binaryUrl"):
        if not isinstance(scanner[key], str) or not scanner[key]:
            raise InstallError(f"supply-chain evidence scanner.{key} must be non-empty text")
    if not isinstance(scanner["commit"], str) or re.fullmatch(r"[0-9a-f]{40}", scanner["commit"]) is None:
        raise InstallError("supply-chain evidence scanner.commit must be 40 lowercase hex characters")
    database = _exact_json_keys(
        scanner["database"],
        {"ecosystem", "generation", "lastModified", "sha256", "size", "url"},
        "supply-chain evidence scanner.database",
    )
    if database["ecosystem"] != "Maven":
        raise InstallError("supply-chain evidence database ecosystem must be Maven")
    _json_digest(database["sha256"], "supply-chain evidence scanner.database.sha256")
    _json_count(database["size"], "supply-chain evidence scanner.database.size", positive=True)
    for key in ("generation", "lastModified", "url"):
        if not isinstance(database[key], str) or not database[key]:
            raise InstallError(f"supply-chain evidence scanner.database.{key} must be non-empty text")

    vulnerabilities = _exact_json_keys(
        evidence["vulnerabilities"],
        {"acceptedExceptionCount", "findingCount", "findings", "unreviewedCount"},
        "supply-chain evidence vulnerabilities",
    )
    unreviewed_count = _json_count(
        vulnerabilities["unreviewedCount"],
        "supply-chain evidence vulnerabilities.unreviewedCount",
    )
    if unreviewed_count != 0:
        raise InstallError("supply-chain evidence contains unreviewed vulnerabilities")
    findings = vulnerabilities["findings"]
    if not isinstance(findings, list):
        raise InstallError("supply-chain evidence vulnerabilities.findings must be an array")
    finding_count = _json_count(
        vulnerabilities["findingCount"], "supply-chain evidence vulnerabilities.findingCount"
    )
    accepted_count = _json_count(
        vulnerabilities["acceptedExceptionCount"],
        "supply-chain evidence vulnerabilities.acceptedExceptionCount",
    )
    if finding_count != len(findings) or accepted_count != len(findings):
        raise InstallError("supply-chain evidence vulnerability counts do not match findings")
    if len(findings) != 1:
        raise InstallError("supply-chain evidence must contain exactly one reviewed finding")
    finding_keys = {
        "action",
        "advisory",
        "exceptionExpires",
        "exceptionId",
        "fixedVersion",
        "owner",
        "purl",
        "rationaleCode",
        "reachabilityEvidence",
        "reviewedAt",
        "scope",
        "severity",
    }
    expected_finding_identities = {
        (
            "OSV-003",
            "GHSA-c2rv-hwqm-wjpg",
            "pkg:maven/org.apache.calcite/calcite-core@1.40.0",
        ),
    }
    observed_finding_identities: set[tuple[object, object, object]] = set()
    for index, raw_finding in enumerate(findings):
        finding = _exact_json_keys(
            raw_finding, finding_keys, f"supply-chain evidence finding {index}"
        )
        reachability = _exact_json_keys(
            finding["reachabilityEvidence"],
            {"exampleProfile", "publishedProfile", "publishedRuntime"},
            f"supply-chain evidence finding {index} reachability",
        )
        if any(not isinstance(value, bool) for value in reachability.values()):
            raise InstallError(
                f"supply-chain evidence finding {index} reachability flags must be booleans"
            )
        if reachability != {
            "exampleProfile": True,
            "publishedProfile": False,
            "publishedRuntime": False,
        }:
            raise InstallError(
                f"supply-chain evidence finding {index} is not confined to the example profile"
            )
        if finding["scope"] != "aggregate-test-only":
            raise InstallError(f"supply-chain evidence finding {index} has an unexpected scope")
        if finding["action"] != "time-bounded reviewed exception; re-evaluate by expiry":
            raise InstallError(f"supply-chain evidence finding {index} has an unexpected action")
        identity = (finding["exceptionId"], finding["advisory"], finding["purl"])
        if identity not in expected_finding_identities or identity in observed_finding_identities:
            raise InstallError(
                f"supply-chain evidence finding {index} identity is unexpected or duplicate"
            )
        observed_finding_identities.add(identity)
        for key in (
            "action",
            "advisory",
            "exceptionExpires",
            "exceptionId",
            "owner",
            "purl",
            "rationaleCode",
            "reviewedAt",
            "severity",
        ):
            if not isinstance(finding[key], str) or not finding[key]:
                raise InstallError(
                    f"supply-chain evidence finding {index}.{key} must be non-empty text"
                )
    if observed_finding_identities != expected_finding_identities:
        raise InstallError("supply-chain evidence reviewed finding set is incomplete")


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


def require_javadoc_text_markers(
    archive: ZipFile, entry: str, markers: tuple[str, ...], description: str
) -> None:
    info = archive.getinfo(entry)
    if info.file_size > MAX_JAVADOC_NOTICE_BYTES:
        raise InstallError(
            f"Javadoc JAR {entry} exceeds the 2 MiB marker-verification limit"
        )
    try:
        text = archive.read(info).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise InstallError(f"Javadoc JAR {entry} is not valid UTF-8") from error
    if any(marker not in text for marker in markers):
        raise InstallError(f"Javadoc JAR has invalid {description}")


def require_javadoc_text_patterns(
    archive: ZipFile, entry: str, patterns: tuple[str, ...], description: str
) -> None:
    info = archive.getinfo(entry)
    if info.file_size > MAX_JAVADOC_NOTICE_BYTES:
        raise InstallError(
            f"Javadoc JAR {entry} exceeds the 2 MiB marker-verification limit"
        )
    try:
        text = archive.read(info).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise InstallError(f"Javadoc JAR {entry} is not valid UTF-8") from error
    if any(re.search(pattern, text) is None for pattern in patterns):
        raise InstallError(f"Javadoc JAR has invalid {description}")


def validate_javadoc_classifier_entry_inventory(archive: ZipFile) -> None:
    """Reject classifier entries outside the pinned doclet and API-doc boundary."""
    allowed_exact = (
        JAVADOC_ALLOWED_DIRECTORY_ENTRIES
        | JAVADOC_ALLOWED_ROOT_ENTRIES
        | JAVADOC_ALLOWED_META_INF_ENTRIES
        | JAVADOC_LEGAL_ENTRIES
        | JAVADOC_STATIC_ENTRIES
    )
    unexpected = sorted(
        info.filename
        for info in archive.infolist()
        if info.filename not in allowed_exact
        and JAVADOC_API_HTML_PATTERN.fullmatch(info.filename) is None
    )
    if unexpected:
        raise InstallError(
            "Javadoc JAR contains an undeclared classifier entry: "
            f"{unexpected[0]}"
        )


def validate_javadoc_classifier_contents(archive: ZipFile) -> None:
    """Fail closed on the version-pinned standard-doclet shipped-file boundary."""
    validate_javadoc_classifier_entry_inventory(archive)
    require_javadoc_text_markers(
        archive,
        "legal/LICENSE",
        (
            "The GNU General Public License (GPL)",
            "Version 2, June 1991",
            '"CLASSPATH" EXCEPTION TO THE GPL',
        ),
        "OpenJDK GPL-2.0 license markers",
    )
    require_javadoc_text_markers(
        archive,
        "legal/ADDITIONAL_LICENSE_INFO",
        (
            "ADDITIONAL INFORMATION ABOUT LICENSING",
            "GNU Classpath Exception.",
        ),
        "OpenJDK Classpath-exception markers",
    )
    require_javadoc_text_markers(
        archive,
        "legal/ASSEMBLY_EXCEPTION",
        (
            "OPENJDK ASSEMBLY EXCEPTION",
            'only ("GPL2"), with the following clarification and special exception.',
        ),
        "OpenJDK assembly-exception markers",
    )
    for entry in ("script.js", "search.js", "jquery-ui.overrides.css"):
        require_javadoc_text_markers(
            archive,
            entry,
            (
                "DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.",
                "GNU General Public License version 2 only",
                'subject to the "Classpath" exception',
            ),
            f"GPL-2.0-only WITH Classpath-exception-2.0 header in {entry}",
        )
    require_javadoc_text_markers(
        archive,
        "stylesheet.css",
        ("Javadoc style sheet",),
        "standard-doclet stylesheet marker",
    )
    require_javadoc_text_markers(
        archive,
        "legal/jquery.md",
        (
            "Copyright OpenJS Foundation and other contributors, https://openjsf.org/",
            "Permission is hereby granted, free of charge",
            "The above copyright notice and this permission notice shall be",
            'THE SOFTWARE IS PROVIDED "AS IS"',
        ),
        "jQuery 3.7.1 version/license markers",
    )
    require_javadoc_text_patterns(
        archive,
        "legal/jquery.md",
        (r"(?m)^## jQuery v3\.7\.1\r?$",),
        "jQuery 3.7.1 version/license markers",
    )
    require_javadoc_text_patterns(
        archive,
        "script-dir/jquery-3.7.1.min.js",
        (r"(?m)^/\*! jQuery v3\.7\.1 \|", r"jquery\.org/license"),
        "jQuery 3.7.1 version/license markers",
    )
    require_javadoc_text_markers(
        archive,
        "legal/jqueryUI.md",
        (
            "Copyright OpenJS Foundation and other contributors, https://openjsf.org/",
            "Permission is hereby granted, free of charge",
            "The above copyright notice and this permission notice shall be",
            'THE SOFTWARE IS PROVIDED "AS IS"',
            "CC0: http://creativecommons.org/publicdomain/zero/1.0/",
        ),
        "jQuery UI 1.14.1 version/license markers",
    )
    require_javadoc_text_patterns(
        archive,
        "legal/jqueryUI.md",
        (r"(?m)^## jQuery UI v1\.14\.1\r?$",),
        "jQuery UI 1.14.1 version/license markers",
    )
    for entry in (
        "script-dir/jquery-ui.min.js",
        "script-dir/jquery-ui.min.css",
    ):
        require_javadoc_text_patterns(
            archive,
            entry,
            (
                r"(?m)^/\*! jQuery UI - v1\.14\.1(?: - [^\r\n]+)?\r?$",
                r"(?m)^\* Copyright OpenJS Foundation and other contributors; Licensed MIT \*/\r?$",
            ),
            "jQuery UI 1.14.1 version/license markers",
        )
    for entry in ("resources/glass.png", "resources/x.png"):
        info = archive.getinfo(entry)
        with archive.open(info) as stream:
            if stream.read(8) != b"\x89PNG\r\n\x1a\n":
                raise InstallError(
                    f"Javadoc JAR has an invalid standard-doclet PNG marker in {entry}"
                )


def validate_thin_first_party_jar_inventory(names: set[str], label: str) -> None:
    """Allow only first-party namespace paths and exact Maven metadata paths."""
    suffix = {"main JAR": ".class", "sources JAR": ".java"}.get(label)
    if suffix is None:
        return
    exact_files = {
        "META-INF/MANIFEST.MF",
        "META-INF/LICENSE",
        "META-INF/NOTICE",
        SERVICE_DESCRIPTOR,
    }
    unexpected = sorted(
        name
        for name in names
        if not name.endswith("/")
        and name not in exact_files
        and not (name.startswith(EXPECTED_PACKAGE_PREFIX) and name.endswith(suffix))
    )
    if unexpected:
        raise InstallError(
            f"{label} violates the thin first-party JAR boundary: {unexpected[0]}"
        )


def validate_sources_classifier_contents(archive: ZipFile, names: set[str]) -> None:
    """Bind every sources-JAR Java declaration to its first-party namespace path."""
    for name in sorted(names):
        if not name.endswith(".java"):
            continue
        source = read_archive_text(
            archive,
            name,
            f"sources JAR Java file {name}",
        )
        declared_package = declared_java_package(java_tokens(source, name), name)
        if is_forbidden_jts_or_mahout_java_package(declared_package):
            raise InstallError(
                "sources JAR violates the JTS/Mahout distribution boundary: "
                f"{name}"
            )
        expected_package = PurePosixPath(name).parent.as_posix().replace("/", ".")
        if declared_package != expected_package:
            raise InstallError(
                f"sources JAR Java package does not match its path: {name}"
            )


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
            if len(infos) > MAX_JAR_ENTRIES:
                raise InstallError(f"{label} exceeds the 20000-entry safety limit")
            names: set[str] = set()
            logical_entries: dict[tuple[str, ...], bool] = {}
            portable_trie: dict[tuple[int, str], tuple[str, int]] = {}
            portable_paths: dict[tuple[str, ...], tuple[str, ...]] = {}
            total_path_components = [0]
            uncompressed = 0
            for info in infos:
                original_name = getattr(info, "orig_filename", info.filename)
                if original_name != info.filename or "\x00" in original_name:
                    raise InstallError(
                        f"{label} contains a truncated or NUL-bearing entry name"
                    )
                if any(
                    ord(character) < 32 or ord(character) == 127
                    for character in info.filename
                ):
                    raise InstallError(
                        f"{label} contains a control character in an entry"
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
                    raise InstallError(f"{label} contains an unsafe entry: {info.filename}")
                canonical_name = PurePosixPath(*pure.parts).as_posix()
                if is_directory:
                    canonical_name += "/"
                if canonical_name != info.filename:
                    raise InstallError(
                        f"{label} contains a non-canonical entry name: {info.filename}"
                    )
                if crosses_jts_or_mahout_distribution_boundary(canonical_name):
                    raise InstallError(
                        f"{label} violates the JTS/Mahout distribution boundary: "
                        f"{info.filename}"
                    )
                if is_directory:
                    if unix_type not in (0, stat.S_IFDIR) or info.file_size != 0:
                        raise InstallError(
                            f"{label} directory has an incompatible type or payload: "
                            f"{info.filename}"
                        )
                elif unix_type not in (0, stat.S_IFREG):
                    raise InstallError(
                        f"{label} contains a special or mismatched Unix entry: "
                        f"{info.filename}"
                    )
                if info.filename in names:
                    raise InstallError(f"{label} contains a duplicate entry: {info.filename}")
                names.add(info.filename)
                logical_name = canonical_name.rstrip("/")
                register_archive_path(
                    logical_name,
                    is_directory,
                    label=label,
                    logical_entries=logical_entries,
                    portable_trie=portable_trie,
                    portable_paths=portable_paths,
                    total_path_components=total_path_components,
                )
                uncompressed += info.file_size
                if uncompressed > MAX_JAR_UNCOMPRESSED_BYTES:
                    raise InstallError(
                        f"{label} exceeds the 200 MiB uncompressed safety limit"
                    )
            validate_archive_path_graph(
                logical_entries,
                portable_paths,
                label=label,
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
            validate_thin_first_party_jar_inventory(names, label)
            if label == "sources JAR":
                validate_sources_classifier_contents(archive, names)
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
                providers = parse_service_descriptor(
                    archive.read(SERVICE_DESCRIPTOR).decode(
                        "utf-8", errors="strict"
                    )
                )
                if providers != [EXPECTED_PROVIDER]:
                    raise InstallError("main JAR has an unexpected SQLExecutionHook provider")
            elif label == "Javadoc JAR":
                validate_javadoc_classifier_contents(archive)
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
        required_entries=(
            common_entries
            | JAVADOC_LEGAL_ENTRIES
            | JAVADOC_STATIC_ENTRIES
            | {"io/github/ym0506/routecontract/RouteContract.html"}
        ),
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
            logical_entries: dict[tuple[str, ...], bool] = {}
            portable_trie: dict[tuple[int, str], tuple[str, int]] = {}
            portable_paths: dict[tuple[str, ...], tuple[str, ...]] = {}
            total_path_components = [0]
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
                _, portable_parts = register_archive_path(
                    logical_name,
                    is_directory,
                    label="source archive",
                    logical_entries=logical_entries,
                    portable_trie=portable_trie,
                    portable_paths=portable_paths,
                    total_path_components=total_path_components,
                )
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
                if crosses_jts_or_mahout_distribution_boundary(relative):
                    raise InstallError(
                        "source archive violates the JTS/Mahout distribution "
                        f"boundary: {relative}"
                    )
                if (
                    not is_directory
                    and PurePosixPath(relative).suffix.casefold() == ".class"
                ):
                    raise InstallError(
                        "source archive contains a compiled Java class: "
                        f"{relative}"
                    )
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
            validate_archive_path_graph(
                logical_entries,
                portable_paths,
                label="source archive",
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
                if PurePosixPath(relative).suffix.casefold() != ".java":
                    continue
                archive_name = f"{expected_root}/{relative}"
                source = read_archive_text(
                    archive,
                    archive_name,
                    f"source archive Java file {relative}",
                )
                tokens = java_tokens(source, relative)
                declared_package = declared_java_package(tokens, relative)
                if is_forbidden_jts_or_mahout_java_package(declared_package):
                    raise InstallError(
                        "source archive violates the JTS/Mahout distribution "
                        f"boundary: {relative}"
                    )
                expected_package = expected_java_package(relative)
                if expected_package is None:
                    raise InstallError(
                        "source archive Java file is outside the conventional "
                        f"source roots: {relative}"
                    )
                if expected_package != "io.github.ym0506.routecontract" and not (
                    expected_package.startswith("io.github.ym0506.routecontract.")
                ):
                    raise InstallError(
                        "source archive violates the first-party Java source "
                        f"boundary: {relative}"
                    )
                java_token_map[relative] = tokens
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
            source_providers = parse_service_descriptor(
                read_archive_text(
                    archive,
                    f"{expected_root}/{SOURCE_SERVICE_DESCRIPTOR_PATH}",
                    "source archive SQLExecutionHook descriptor",
                    limit=64 * 1024,
                )
            )
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


def conventional_maven_repositories() -> set[Path]:
    """Return process-home and POSIX account-home Maven defaults."""
    homes = {Path.home()}
    if pwd is not None:
        try:
            account_home = pwd.getpwuid(os.getuid()).pw_dir
        except (KeyError, OSError):
            account_home = ""
        if account_home:
            homes.add(Path(account_home))
    return {
        (home / ".m2" / "repository").resolve(strict=False)
        for home in homes
    }


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
    repository_key = tuple(
        unicodedata.normalize("NFC", part).casefold() for part in repository.parts
    )
    for conventional_default_repository in conventional_maven_repositories():
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
    validate_supply_chain_evidence(files)
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
