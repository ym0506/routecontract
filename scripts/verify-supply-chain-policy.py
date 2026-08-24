#!/usr/bin/env python3
"""Fail-closed license and OSV policy checks for the verified aggregate SBOM.

OSV-Scanner 2.5.0 currently drops Maven groups when it consumes this
CycloneDX document directly. The ``inventory`` command therefore derives an
exact Gradle lockfile-shaped inventory from the verified Maven purls. The
``verify`` command rejects the scan unless that inventory and the scanner's
package set are both exactly equal to the SBOM's Maven component set.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Any
from urllib.parse import quote, unquote_to_bytes, urlsplit
import xml.etree.ElementTree as ET


HEX_40 = re.compile(r"[0-9a-f]{40}")
HEX_64 = re.compile(r"[0-9a-f]{64}")
MAVEN_PURL = re.compile(
    r"^pkg:maven/(?P<group>[^/@?]+)/(?P<name>[^/@?]+)@(?P<version>[^?]+)"
    r"(?:\?(?P<query>[^#]+))?$"
)
INVALID_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
UNSAFE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
RFC3339_UTC = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?Z"
)
XML_DECLARATION = re.compile(
    r"^<\?xml\s+version=(['\"])1\.0\1\s+encoding=(['\"])utf-8\2\s*\?>",
    re.IGNORECASE,
)
TEST_PROPERTY = {"name": "cdx:maven:package:test", "value": "true"}
TEST_CONTAINER_PROPERTY = {"name": "routecontract:usage", "value": "test-only"}
LICENSE_REVIEW_PROPERTY_NAME = "routecontract:license-review"
LICENSE_REVIEW_STATUS = "manual-review-required"
APACHE_LICENSE_URL = "https://www.apache.org/licenses/LICENSE-2.0.txt"
MAVEN_NAMESPACE = "http://maven.apache.org/POM/4.0.0"
CYCLONEDX_XML_NAMESPACE = "http://cyclonedx.org/schema/bom/1.6"
FIRST_PARTY_GROUP = "io.github.ym0506.routecontract"
AGGREGATE_ROOT_NAME = "routecontract"
PUBLISHED_ROOT_NAME = "routecontract-shardingsphere-5.5"
EXAMPLE_ROOT_NAME = "mysql-example"
MYSQL_CONTAINER_NAME = "mysql"
MYSQL_CONTAINER_VERSION = "8.4.11"
MYSQL_CONTAINER_DIGEST = (
    "b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb"
)
MYSQL_CONTAINER_PURL = (
    "pkg:oci/mysql@sha256%3A"
    f"{MYSQL_CONTAINER_DIGEST}?repository_url=registry-1.docker.io&tag=8.4.11"
)
MYSQL_CONTAINER_DOCUMENTATION_URL = (
    "https://dev.mysql.com/doc/refman/8.4/en/preface.html"
)
JTS_LICENSE_EXPRESSIONS = {
    "pkg:maven/org.locationtech.jts/jts-core@1.19.0":
        "EPL-2.0 OR BSD-3-Clause",
}
JTS_LICENSE_EXCEPTIONS = {
    purl: {
        "kind": "expression",
        "license": expression,
        "purl": purl,
        "scope": "test-runtime",
        "url": None,
    }
    for purl, expression in JTS_LICENSE_EXPRESSIONS.items()
}
FORBIDDEN_JTS_IO_GROUP = "org.locationtech.jts.io"
FORBIDDEN_JTS_IO_NAME = "jts-io-common"
FORBIDDEN_JTS_IO_PURL_PREFIX = (
    "pkg:maven/org.locationtech.jts.io/jts-io-common@"
)
REQUIRED_EXAMPLE_MAVEN_COORDINATES = (
    ("org.apache.shardingsphere", "shardingsphere-jdbc", "5.5.3"),
    ("org.apache.calcite", "calcite-core", "1.42.0"),
    ("org.apache.calcite", "calcite-linq4j", "1.42.0"),
)
MYSQL_LICENSE_REVIEW_EXCEPTION = {
    "action": (
        "re-review immediately if the MySQL OCI digest, selected platform, embedded "
        "LICENSE/INFO_SRC evidence, or test-container use boundary changes; otherwise "
        "resolve, renew with new evidence, or remove the MySQL OCI package-level "
        "license review before the 2026-12-05 expiry"
    ),
    "componentName": MYSQL_CONTAINER_NAME,
    "componentVersion": MYSQL_CONTAINER_VERSION,
    "documentationUrl": MYSQL_CONTAINER_DOCUMENTATION_URL,
    "expires": "2026-12-05",
    "owner": "RouteContract maintainers",
    "purl": MYSQL_CONTAINER_PURL,
    "rationaleCode": "MYSQL_OCI_PACKAGE_LICENSE_CONCLUSION_INCOMPLETE",
    "reviewedAt": "2026-08-24",
    "scope": "test-container",
    "sha256": MYSQL_CONTAINER_DIGEST,
    "status": LICENSE_REVIEW_STATUS,
}
SPDX_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]*|[()]")
REVIEWED_SPDX_LICENSE_IDS = {
    "Apache-2.0",
    "BSD-3-Clause",
    "EPL-1.0",
    "EPL-2.0",
    "GPL-2.0-only",
    "GPL-3.0-only",
    "LGPL-2.1-or-later",
    "MIT",
}
REVIEWED_SPDX_EXCEPTION_IDS = {
    "Classpath-exception-2.0",
    "Universal-FOSS-exception-1.0",
}
SUPPORTED_COMPONENT_FIELDS = {
    "type",
    "bom-ref",
    "publisher",
    "group",
    "name",
    "version",
    "description",
    "scope",
    "hashes",
    "licenses",
    "purl",
    "externalReferences",
    "modified",
    "properties",
    # The release profile is intentionally flat. An explicit empty collection is
    # accepted for compatibility with CycloneDX producers; any nonempty value is
    # rejected below rather than being silently omitted from the inventory.
    "components",
}
COMPONENT_FIELD_ORDER = (
    "publisher",
    "group",
    "name",
    "version",
    "description",
    "scope",
    "hashes",
    "licenses",
    "purl",
    "modified",
    "externalReferences",
    "properties",
)
DOCUMENT_FIELDS = {
    "bomFormat",
    "specVersion",
    "serialNumber",
    "version",
    "metadata",
    "components",
    "dependencies",
}
METADATA_FIELDS = {"timestamp", "tools", "component", "licenses"}
EXPECTED_TOOL_COMPONENT = {
    "type": "application",
    "author": "CycloneDX",
    "name": "cyclonedx-gradle-plugin",
    "version": "3.4.0",
}
GRADLE_METADATA_POM_COMMENTS = (
    " This module was also published with a richer model, Gradle metadata,  ",
    " which should be used instead. Do not delete the following line which  ",
    " is to indicate to Gradle or any Gradle module metadata file consumer  ",
    " that they should prefer consuming it instead. ",
    " do_not_remove: published-with-gradle-metadata ",
)


LicenseRecord = tuple[str, str, str]


class PolicyError(ValueError):
    """Raised when supply-chain evidence is incomplete or ambiguous."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _absolute_lexical_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _reject_symlink_components(path: Path, label: str) -> Path:
    absolute = _absolute_lexical_path(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            break
        except OSError as error:
            raise PolicyError(f"cannot inspect {label}: {error}") from error
        if stat.S_ISLNK(mode):
            raise PolicyError(f"{label} must not contain a symbolic link: {current}")
    return absolute


def _read_regular_bytes(path: Path, label: str) -> bytes:
    absolute = _reject_symlink_components(path, label)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(absolute, flags)
    except OSError as error:
        raise PolicyError(f"cannot open {label}: {error}") from error
    try:
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISREG(mode):
            raise PolicyError(f"{label} must be a regular non-symlink file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _read_text(path: Path, label: str) -> str:
    try:
        content = _read_regular_bytes(path, label)
        if content.startswith(b"\xef\xbb\xbf"):
            raise PolicyError(f"{label} must not contain a UTF-8 BOM")
        decoded = content.decode("utf-8")
    except UnicodeError as error:
        raise PolicyError(f"cannot decode {label} as UTF-8: {error}") from error
    if "\x00" in decoded:
        raise PolicyError(f"{label} must not contain NUL")
    return decoded


def _reject_json_control_characters(
    value: Any, label: str, *, allow_escaped_whitespace: bool
) -> None:
    if isinstance(value, str):
        pattern = UNSAFE_CONTROL if allow_escaped_whitespace else CONTROL
        if pattern.search(value):
            raise PolicyError(f"{label} contains a control character")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _reject_json_control_characters(
                child,
                f"{label}[{index}]",
                allow_escaped_whitespace=allow_escaped_whitespace,
            )
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_json_control_characters(
                key,
                f"{label} key",
                allow_escaped_whitespace=False,
            )
            _reject_json_control_characters(
                child,
                f"{label}.{key}",
                allow_escaped_whitespace=allow_escaped_whitespace,
            )


def _parse_canonical_xml(
    content: bytes,
    label: str,
    *,
    allowed_root_comments: tuple[str, ...] = (),
) -> ET.Element:
    if content.startswith(b"\xef\xbb\xbf"):
        raise PolicyError(f"{label} must not contain a UTF-8 BOM")
    try:
        decoded = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PolicyError(f"{label} must be UTF-8") from error
    if "\x00" in decoded:
        raise PolicyError(f"{label} must not contain NUL")
    declaration = XML_DECLARATION.match(decoded)
    if declaration is None:
        raise PolicyError(f"{label} must declare XML 1.0 with UTF-8 encoding")
    body = decoded[declaration.end():]
    uppercase = body.upper()
    if "<!DOCTYPE" in uppercase or "<!ENTITY" in uppercase:
        raise PolicyError(f"{label} must not contain a DTD or entity")
    lexical_comments = tuple(re.findall(r"<!--(.*?)-->", body, flags=re.DOTALL))
    if (
        lexical_comments != allowed_root_comments
        or "<?" in body
        or "<!--" in body and not lexical_comments
    ):
        raise PolicyError(f"{label} must not contain comments or processing instructions")
    try:
        parser = ET.XMLParser(
            target=ET.TreeBuilder(insert_comments=True, insert_pis=True)
        )
        root = ET.fromstring(decoded, parser=parser)
    except ET.ParseError as error:
        raise PolicyError(f"cannot parse {label}: {error}") from error
    non_elements = [
        element for element in root.iter() if not isinstance(element.tag, str)
    ]
    if allowed_root_comments:
        root_children = list(root)
        expected_count = len(allowed_root_comments)
        comments = root_children[:expected_count]
        if (
            len(non_elements) != expected_count
            or comments != non_elements
            or any(comment.tag is not ET.Comment for comment in comments)
            or tuple(comment.text or "" for comment in comments)
            != allowed_root_comments
        ):
            raise PolicyError(
                f"{label} must not contain unapproved comments or processing instructions"
            )
        for comment in comments:
            root.remove(comment)
    elif non_elements:
        raise PolicyError(f"{label} must not contain comments or processing instructions")
    return root


def _validate_timestamp(value: Any, label: str) -> str:
    text = _nonempty_string(value, label)
    if RFC3339_UTC.fullmatch(text) is None:
        raise PolicyError(f"{label} must be an RFC 3339 UTC timestamp")
    try:
        datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as error:
        raise PolicyError(f"{label} must be an RFC 3339 UTC timestamp") from error
    return text


def _parse_json_bytes(
    content: bytes, label: str, *, allow_escaped_whitespace: bool = False
) -> dict[str, Any]:
    try:
        if content.startswith(b"\xef\xbb\xbf"):
            raise PolicyError(f"{label} must not contain a UTF-8 BOM")
        decoded = content.decode("utf-8")
    except UnicodeError as error:
        raise PolicyError(f"cannot decode {label} as UTF-8: {error}") from error
    if "\x00" in decoded:
        raise PolicyError(f"{label} must not contain NUL")
    try:
        value = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except json.JSONDecodeError as error:
        raise PolicyError(f"cannot read {label}: {error}") from error
    if not isinstance(value, dict):
        raise PolicyError(f"{label} must be an object")
    _reject_json_control_characters(
        value,
        label,
        allow_escaped_whitespace=allow_escaped_whitespace,
    )
    return value


def _read_json_snapshot(
    path: Path, *, allow_escaped_whitespace: bool = False
) -> tuple[dict[str, Any], bytes]:
    label = f"JSON document {path.name}"
    content = _read_regular_bytes(path, label)
    return (
        _parse_json_bytes(
            content,
            label,
            allow_escaped_whitespace=allow_escaped_whitespace,
        ),
        content,
    )


def _read_json(
    path: Path, *, allow_escaped_whitespace: bool = False
) -> dict[str, Any]:
    value, _ = _read_json_snapshot(
        path, allow_escaped_whitespace=allow_escaped_whitespace
    )
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(_read_regular_bytes(path, f"hash input {path.name}")).hexdigest()


def _write_text_atomic(path: Path, content: str) -> None:
    absolute = _reject_symlink_components(path, f"output path {path.name}")
    parent = absolute.parent
    if absolute.name in {"", ".", ".."}:
        raise PolicyError("output path must name a file")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        parent_descriptor = os.open(parent, directory_flags)
    except OSError as error:
        raise PolicyError(f"cannot open output directory for {path.name}: {error}") from error
    temporary_name = f".{absolute.name}.{secrets.token_hex(16)}.tmp"
    temporary_created = False
    try:
        try:
            existing = os.stat(
                absolute.name, dir_fd=parent_descriptor, follow_symlinks=False
            )
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if stat.S_ISLNK(existing.st_mode):
                raise PolicyError(f"output path must not be a symbolic link: {absolute}")
            if not stat.S_ISREG(existing.st_mode):
                raise PolicyError(f"output path must be a regular file: {absolute}")
        output_flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(
            temporary_name, output_flags, 0o600, dir_fd=parent_descriptor
        )
        temporary_created = True
        try:
            encoded = content.encode("utf-8")
            offset = 0
            while offset < len(encoded):
                offset += os.write(descriptor, encoded[offset:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            replacement = os.stat(
                absolute.name, dir_fd=parent_descriptor, follow_symlinks=False
            )
        except FileNotFoundError:
            replacement = None
        if replacement is not None and not stat.S_ISREG(replacement.st_mode):
            raise PolicyError(
                f"output path changed to a non-regular or symbolic-link entry: {absolute}"
            )
        os.replace(
            temporary_name,
            absolute.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_created = False
        os.fsync(parent_descriptor)
    except PolicyError:
        raise
    except OSError as error:
        raise PolicyError(f"cannot write {path.name}: {error}") from error
    finally:
        if temporary_created:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except OSError:
                pass
        os.close(parent_descriptor)


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise PolicyError(
            f"{label} keys differ: expected {sorted(expected)}, found {sorted(actual)}"
        )


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or CONTROL.search(value):
        raise PolicyError(f"{label} must be a non-empty control-free string")
    return value


def _normalized_description(value: Any, label: str) -> str:
    if not isinstance(value, str) or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value):
        raise PolicyError(f"{label} must be a non-empty text string")
    normalized = " ".join(value.split())
    if not normalized:
        raise PolicyError(f"{label} must be a non-empty text string")
    return normalized


def _absolute_http_url(value: Any, label: str) -> str:
    text = _nonempty_string(value, label)
    if (
        INVALID_PERCENT.search(text)
        or any(ord(character) > 127 for character in text)
        or any(character in '<>"{}|\\^`' for character in text)
    ):
        raise PolicyError(f"{label} has malformed URL syntax")
    parsed = urlsplit(text)
    try:
        port = parsed.port
    except ValueError as error:
        raise PolicyError(f"{label} has an invalid port") from error
    hostname = parsed.hostname
    dns_hostname = hostname[:-1] if hostname and hostname.endswith(".") else hostname
    hostname_is_valid = False
    if dns_hostname:
        if ":" in dns_hostname:
            try:
                ipaddress.IPv6Address(dns_hostname)
                hostname_is_valid = True
            except ValueError:
                hostname_is_valid = False
        else:
            labels = dns_hostname.split(".")
            hostname_is_valid = (
                len(dns_hostname) <= 253
                and all(
                    1 <= len(part) <= 63
                    and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", part)
                    for part in labels
                )
            )
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or not hostname_is_valid
        or port is not None and not 1 <= port <= 65535
        or any(character.isspace() for character in text)
    ):
        raise PolicyError(f"{label} must be an absolute HTTP(S) URL")
    return text


def _spdx_tokens(value: str, label: str) -> list[str]:
    if value != value.strip(" "):
        raise PolicyError(f"{label} has invalid SPDX syntax")
    tokens: list[str] = []
    offset = 0
    for match in SPDX_TOKEN.finditer(value):
        gap = value[offset:match.start()]
        if gap and (set(gap) != {" "} or match.start() == offset):
            raise PolicyError(f"{label} has invalid SPDX syntax")
        tokens.append(match.group())
        offset = match.end()
    trailing = value[offset:]
    if trailing and set(trailing) != {" "} or not tokens:
        raise PolicyError(f"{label} has invalid SPDX syntax")
    return tokens


def _validate_spdx_license_id(value: str, label: str) -> str:
    if value not in REVIEWED_SPDX_LICENSE_IDS:
        raise PolicyError(f"{label} is not in the reviewed SPDX license-id set: {value}")
    return value


def _validate_spdx_expression(value: str, label: str) -> str:
    tokens = _spdx_tokens(value, label)
    position = 0

    def parse_primary() -> bool:
        nonlocal position
        if position >= len(tokens):
            raise PolicyError(f"{label} has an incomplete SPDX expression")
        token = tokens[position]
        if token == "(":
            position += 1
            parse_or()
            if position >= len(tokens) or tokens[position] != ")":
                raise PolicyError(f"{label} has unbalanced SPDX parentheses")
            position += 1
            return False
        if token in {"AND", "OR", "WITH", ")"}:
            raise PolicyError(f"{label} has invalid SPDX operator placement")
        _validate_spdx_license_id(token, label)
        position += 1
        return True

    def parse_with() -> None:
        nonlocal position
        simple_license = parse_primary()
        if position < len(tokens) and tokens[position] == "WITH":
            if not simple_license:
                raise PolicyError(f"{label} applies WITH to a compound SPDX expression")
            position += 1
            if position >= len(tokens):
                raise PolicyError(f"{label} omits the SPDX exception id")
            exception = tokens[position]
            if exception not in REVIEWED_SPDX_EXCEPTION_IDS:
                raise PolicyError(
                    f"{label} uses an unreviewed SPDX exception id: {exception}"
                )
            position += 1

    def parse_and() -> None:
        nonlocal position
        parse_with()
        while position < len(tokens) and tokens[position] == "AND":
            position += 1
            parse_with()

    def parse_or() -> None:
        nonlocal position
        parse_and()
        while position < len(tokens) and tokens[position] == "OR":
            position += 1
            parse_and()

    parse_or()
    if position != len(tokens):
        raise PolicyError(f"{label} has trailing or misplaced SPDX tokens")
    return value


def _iso_date(value: Any, label: str) -> date:
    text = _nonempty_string(value, label)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise PolicyError(f"{label} must use YYYY-MM-DD") from error
    if parsed.isoformat() != text:
        raise PolicyError(f"{label} must use canonical YYYY-MM-DD")
    return parsed


def _validate_review_window(exception: dict[str, Any], label: str) -> None:
    reviewed_at = _iso_date(exception["reviewedAt"], f"{label} reviewedAt")
    expires = _iso_date(exception["expires"], f"{label} expires")
    today = datetime.now(timezone.utc).date()
    if reviewed_at > today:
        raise PolicyError(f"{label} reviewedAt must not be in the future")
    if reviewed_at > expires:
        raise PolicyError(f"{label} reviewedAt must not be later than expires")
    if expires < today:
        raise PolicyError(f"{label} has expired")


def _strict_percent_decode(value: str, label: str) -> str:
    if INVALID_PERCENT.search(value):
        raise PolicyError(f"{label} contains malformed percent encoding")
    try:
        return unquote_to_bytes(value).decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise PolicyError(f"{label} contains invalid UTF-8 percent encoding") from error


# This parser enforces RouteContract's pinned CycloneDX-Gradle Maven PURL byte
# profile. It is intentionally narrower than the general PURL grammar: current
# release evidence has no subpaths and retains the producer's encoded
# ``project_path`` colon.
def _parse_maven_purl(
    purl: str,
) -> tuple[str, str, str, str, dict[str, str]]:
    match = MAVEN_PURL.fullmatch(purl)
    if match is None:
        raise PolicyError(f"invalid Maven purl: {purl}")
    group = _strict_percent_decode(match.group("group"), "Maven group")
    name = _strict_percent_decode(match.group("name"), "Maven name")
    version = _strict_percent_decode(match.group("version"), "Maven version")
    for label, value in (("group", group), ("name", name), ("version", version)):
        if not value or CONTROL.search(value) or any(token in value for token in (":", "=", "/")):
            raise PolicyError(f"unsafe Maven {label} in purl: {purl}")
    qualifiers: dict[str, str] = {}
    query = match.group("query")
    if query is not None:
        for field in query.split("&"):
            if field.count("=") != 1:
                raise PolicyError(f"invalid Maven purl qualifier: {purl}")
            raw_name, raw_value = field.split("=", 1)
            qualifier_name = _strict_percent_decode(raw_name, "Maven qualifier name")
            qualifier_value = _strict_percent_decode(raw_value, "Maven qualifier value")
            if (
                not qualifier_name
                or not qualifier_value
                or CONTROL.search(qualifier_name)
                or CONTROL.search(qualifier_value)
                or qualifier_name in qualifiers
            ):
                raise PolicyError(f"invalid or duplicate Maven purl qualifier: {purl}")
            qualifiers[qualifier_name] = qualifier_value
    encoded_group = quote(group, safe=".-_~")
    encoded_name = quote(name, safe=".-_~")
    encoded_version = quote(version, safe=".-_~")
    canonical = f"pkg:maven/{encoded_group}/{encoded_name}@{encoded_version}"
    canonical_query = "&".join(
        f"{quote(key, safe='.-_~')}={quote(qualifiers[key], safe='.-_~')}"
        for key in sorted(qualifiers)
    )
    expected_purl = canonical + (f"?{canonical_query}" if canonical_query else "")
    if purl != expected_purl:
        raise PolicyError(
            f"Maven purl differs from the pinned producer encoding profile: {purl}"
        )
    return canonical, group, name, version, qualifiers


def _canonical_maven_purl(purl: str) -> tuple[str, str, str, str]:
    canonical, group, name, version, qualifiers = _parse_maven_purl(purl)
    if "classifier" in qualifiers:
        raise PolicyError(f"Maven classifier is not supported: {purl}")
    return canonical, group, name, version


def _validate_resolved_maven_purl(
    purl: str,
) -> tuple[str, str, str, str, str]:
    canonical, group, name, version, qualifiers = _parse_maven_purl(purl)
    expected = (
        {"project_path"}
        if group == FIRST_PARTY_GROUP
        else {"type"}
    )
    if set(qualifiers) != expected:
        raise PolicyError(
            f"resolved Maven purl has unexpected qualifiers: {purl}"
        )
    if "type" in qualifiers and qualifiers["type"] not in {"jar", "pom"}:
        raise PolicyError(f"resolved Maven purl has unsupported type: {purl}")
    if "project_path" in qualifiers and not qualifiers["project_path"].startswith(":"):
        raise PolicyError(f"first-party project_path is invalid: {purl}")
    qualifier_text = "&".join(
        f"{quote(name, safe='.-_~')}={quote(qualifiers[name], safe='.-_~')}"
        for name in sorted(qualifiers)
    )
    resolved = f"{canonical}?{qualifier_text}"
    return resolved, canonical, group, name, version


def _is_forbidden_jts_io_identity(
    group: object, name: object, purl: object, bom_ref: object
) -> bool:
    return (
        (group == FORBIDDEN_JTS_IO_GROUP and name == FORBIDDEN_JTS_IO_NAME)
        or (
            isinstance(purl, str)
            and purl.startswith(FORBIDDEN_JTS_IO_PURL_PREFIX)
        )
        or (
            isinstance(bom_ref, str)
            and bom_ref.startswith(FORBIDDEN_JTS_IO_PURL_PREFIX)
        )
    )


def _validate_policy(policy: dict[str, Any]) -> dict[str, Any]:
    _exact_keys(
        policy,
        {
            "schemaVersion",
            "allowedLicenseIds",
            "licenseExceptions",
            "licenseReviewExceptions",
            "vulnerabilityExceptions",
        },
        "policy",
    )
    if policy["schemaVersion"] != 3:
        raise PolicyError("unsupported policy schemaVersion")
    allowed = policy["allowedLicenseIds"]
    if (
        not isinstance(allowed, list)
        or not allowed
        or any(
            not isinstance(item, str)
            or item not in REVIEWED_SPDX_LICENSE_IDS
            for item in allowed
        )
        or allowed != sorted(set(allowed))
    ):
        raise PolicyError("allowedLicenseIds must be a sorted unique non-empty array")

    license_exceptions = policy["licenseExceptions"]
    if not isinstance(license_exceptions, list):
        raise PolicyError("licenseExceptions must be an array")
    license_keys: set[tuple[str, str, str, str]] = set()
    for index, exception in enumerate(license_exceptions):
        if not isinstance(exception, dict):
            raise PolicyError(f"licenseExceptions[{index}] must be an object")
        _exact_keys(
            exception,
            {"kind", "license", "purl", "scope", "url"},
            f"licenseExceptions[{index}]",
        )
        kind = _nonempty_string(exception["kind"], "license exception kind")
        if kind not in {"expression", "id", "name"}:
            raise PolicyError("license exception kind must be expression, id, or name")
        license_value = _nonempty_string(exception["license"], "license exception value")
        raw_url = exception["url"]
        if raw_url is None:
            license_url = ""
        else:
            license_url = _absolute_http_url(raw_url, "license exception url")
        if kind == "expression" and license_url:
            raise PolicyError("license expression exceptions must use a null url")
        if kind == "name" and not license_url:
            raise PolicyError("named license exceptions must bind an exact url")
        if kind == "id":
            _validate_spdx_license_id(license_value, "license exception id")
        if kind == "expression":
            _validate_spdx_expression(license_value, "license exception expression")
        purl = _nonempty_string(exception["purl"], "license exception purl")
        if purl.startswith(FORBIDDEN_JTS_IO_PURL_PREFIX):
            raise PolicyError(
                "JTS I/O Common license exceptions are forbidden by the pinned policy"
            )
        scope = _nonempty_string(exception["scope"], "license exception scope")
        if scope not in {"test-container", "test-runtime"}:
            raise PolicyError(
                "license exception scope must be test-runtime or test-container"
            )
        if scope == "test-runtime":
            canonical, _, _, _ = _canonical_maven_purl(purl)
            if purl != canonical:
                raise PolicyError(
                    "test-runtime license exception purl must use the pinned Maven profile"
                )
        elif not purl.startswith("pkg:oci/"):
            raise PolicyError("test-container license exception purl must be OCI")
        license_key = (purl, kind, license_value, license_url)
        if license_key in license_keys:
            raise PolicyError("duplicate license exception")
        license_keys.add(license_key)
    jts_exceptions = {
        exception["purl"]: exception
        for exception in license_exceptions
        if exception.get("purl") in JTS_LICENSE_EXPRESSIONS
    }
    if jts_exceptions != JTS_LICENSE_EXCEPTIONS:
        raise PolicyError(
            "licenseExceptions must bind JTS Core 1.19.0 to its exact reviewed "
            "SPDX expression"
        )

    review_exceptions = policy["licenseReviewExceptions"]
    if not isinstance(review_exceptions, list):
        raise PolicyError("licenseReviewExceptions must be an array")
    expected_reviews = [MYSQL_LICENSE_REVIEW_EXCEPTION]
    if len(review_exceptions) != len(expected_reviews):
        raise PolicyError(
            "licenseReviewExceptions must contain exactly the pinned MySQL review"
        )
    review_purls: set[str] = set()
    for index, exception in enumerate(review_exceptions):
        if not isinstance(exception, dict):
            raise PolicyError(f"licenseReviewExceptions[{index}] must be an object")
        expected_review = expected_reviews[index]
        if index == 0 and "documentationUrl" in exception:
            _absolute_http_url(
                exception["documentationUrl"], "license review documentationUrl"
            )
        if {"reviewedAt", "expires"}.issubset(exception):
            _validate_review_window(
                exception, f"licenseReviewExceptions[{index}]"
            )
        if exception != expected_review:
            raise PolicyError(
                "license review exception must exactly identify the pinned MySQL OCI image"
            )
        purl = _nonempty_string(exception["purl"], "license review purl")
        if purl in review_purls:
            raise PolicyError("duplicate license review exception")
        review_purls.add(purl)
    if review_purls != {MYSQL_CONTAINER_PURL}:
        raise PolicyError("license review exception identity set differs")

    if policy["vulnerabilityExceptions"] != []:
        raise PolicyError("vulnerabilityExceptions must be exactly empty")
    return policy


def _load_policy(path: Path) -> dict[str, Any]:
    return _validate_policy(_read_json(path))


def _load_policy_snapshot(path: Path) -> tuple[dict[str, Any], bytes]:
    policy, content = _read_json_snapshot(path)
    return _validate_policy(policy), content


def _load_sbom(path: Path) -> dict[str, Any]:
    sbom = _read_json(path)
    if set(sbom) != DOCUMENT_FIELDS:
        raise PolicyError(
            "SBOM document fields differ from the supported CycloneDX profile: "
            f"{sorted(set(sbom) - DOCUMENT_FIELDS)}"
        )
    if sbom.get("bomFormat") != "CycloneDX" or sbom.get("specVersion") != "1.6":
        raise PolicyError("SBOM must be CycloneDX 1.6")
    if (
        type(sbom.get("version")) is not int
        or sbom.get("version") != 1
        or not isinstance(sbom.get("serialNumber"), str)
        or not sbom["serialNumber"]
    ):
        raise PolicyError("SBOM document identity must be CycloneDX version 1")
    metadata = sbom.get("metadata")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("component"), dict):
        raise PolicyError("SBOM metadata.component is missing")
    if set(metadata) != METADATA_FIELDS:
        raise PolicyError("SBOM metadata differs from the required CycloneDX profile")
    if metadata.get("licenses") != [
        {"license": {"id": "Apache-2.0", "url": APACHE_LICENSE_URL}}
    ]:
        raise PolicyError("SBOM document license is not exact Apache-2.0")
    _validate_timestamp(metadata["timestamp"], "SBOM metadata timestamp")
    if metadata["tools"] != {
        "components": [EXPECTED_TOOL_COMPONENT]
    }:
        raise PolicyError("SBOM metadata tools differ from the pinned producer")
    components = sbom.get("components")
    if not isinstance(components, list) or any(not isinstance(item, dict) for item in components):
        raise PolicyError("SBOM components must be an array of objects")
    for index, component in enumerate([metadata["component"], *components]):
        unsupported = set(component) - SUPPORTED_COMPONENT_FIELDS
        if unsupported:
            raise PolicyError(
                "SBOM component contains unsupported CycloneDX fields: "
                f"{sorted(unsupported)}"
            )
        if "components" in component:
            raise PolicyError("Nested JSON components are not supported")
        for field in ("type", "bom-ref", "name", "version", "purl"):
            _nonempty_string(component.get(field), f"SBOM component {index} {field}")
        if _is_forbidden_jts_io_identity(
            component.get("group"),
            component.get("name"),
            component.get("purl"),
            component.get("bom-ref"),
        ):
            raise PolicyError("JTS I/O Common is forbidden by the pinned policy")
        for field in ("publisher", "group", "scope"):
            if field in component:
                _nonempty_string(component[field], f"SBOM component {index} {field}")
        if "description" in component:
            _normalized_description(
                component["description"], f"SBOM component {index} description"
            )
        if "modified" in component and type(component["modified"]) is not bool:
            raise PolicyError(f"SBOM component {index} modified must be a boolean")
    dependencies = sbom.get("dependencies")
    if not isinstance(dependencies, list):
        raise PolicyError("SBOM dependencies must be an array")
    seen_refs: set[str] = set()
    for index, record in enumerate(dependencies):
        if not isinstance(record, dict) or set(record) != {"ref", "dependsOn"}:
            raise PolicyError(f"SBOM dependency record {index} is invalid")
        ref = _nonempty_string(record["ref"], f"SBOM dependency record {index} ref")
        targets = record["dependsOn"]
        if (
            ref in seen_refs
            or not isinstance(targets, list)
            or any(not isinstance(target, str) or not target for target in targets)
            or len(targets) != len(set(targets))
        ):
            raise PolicyError(f"SBOM dependency record {index} is ambiguous")
        seen_refs.add(ref)
    return sbom


def _validate_xml_pair(
    sbom: dict[str, Any], xml_path: Path, label: str
) -> tuple[int, str]:
    content = _read_regular_bytes(xml_path, f"{label} XML SBOM")
    root = _parse_canonical_xml(content, f"{label} XML SBOM")
    qname = lambda name: f"{{{CYCLONEDX_XML_NAMESPACE}}}{name}"

    def xml_leaf(
        element: ET.Element,
        element_label: str,
        expected_attributes: set[str] = frozenset(),
    ) -> str:
        if (
            set(element.attrib) != set(expected_attributes)
            or len(element)
            or not (element.text or "").strip()
            or (element.tail or "").strip()
        ):
            raise PolicyError(f"{element_label} must be an unambiguous XML leaf")
        return element.text or ""

    def xml_wrapper(
        element: ET.Element, element_label: str, expected_children: set[str]
    ) -> None:
        if (
            element.attrib
            or (element.text or "").strip()
            or (element.tail or "").strip()
            or any(child.tag not in expected_children for child in element)
        ):
            raise PolicyError(f"{element_label} has an unsupported XML shape")

    json_version = sbom.get("version")
    if type(json_version) is not int or json_version != 1:
        raise PolicyError(f"{label} JSON SBOM version must be the integer 1")
    if (
        root.tag != qname("bom")
        or set(root.attrib) != {"serialNumber", "version"}
        or root.get("version") != str(json_version)
        or (root.text or "").strip()
        or (root.tail or "").strip()
        or [child.tag for child in root]
        != [qname("metadata"), qname("components"), qname("dependencies")]
    ):
        raise PolicyError(f"{label} XML SBOM must be CycloneDX 1.6 version 1")
    serial = _nonempty_string(sbom.get("serialNumber"), f"{label} JSON serialNumber")
    if root.get("serialNumber") != serial:
        raise PolicyError(f"{label} JSON/XML serial numbers differ")
    metadata_json = sbom.get("metadata")
    expected_document_license = [
        {"license": {"id": "Apache-2.0", "url": APACHE_LICENSE_URL}}
    ]
    if (
        not isinstance(metadata_json, dict)
        or metadata_json.get("licenses") != expected_document_license
    ):
        raise PolicyError(f"{label} JSON document license is not exact Apache-2.0")

    def xml_text(parent: ET.Element, name: str, required: bool = False) -> str | None:
        values = parent.findall(qname(name))
        if len(values) > 1 or (required and len(values) != 1):
            raise PolicyError(f"{label} XML component has ambiguous {name}")
        if not values:
            return None
        if (
            values[0].attrib
            or len(values[0])
            or values[0].text is None
            or (values[0].tail or "").strip()
        ):
            raise PolicyError(f"{label} XML component has empty {name}")
        if name == "description":
            return _normalized_description(
                values[0].text, f"{label} XML component {name}"
            )
        return _nonempty_string(values[0].text, f"{label} XML component {name}")

    def json_record(component: dict[str, Any], component_label: str) -> dict[str, Any]:
        hashes = component.get("hashes", [])
        if not isinstance(hashes, list) or any(
            not isinstance(item, dict) or set(item) != {"alg", "content"}
            for item in hashes
        ):
            raise PolicyError(f"{component_label} has invalid hashes")
        hash_records = sorted(
            (
                _nonempty_string(item["alg"], f"{component_label} hash algorithm"),
                _nonempty_string(item["content"], f"{component_label} hash content"),
            )
            for item in hashes
        )
        if len(hash_records) != len(set(hash_records)):
            raise PolicyError(f"{component_label} has duplicate hashes")
        return {
            "description": (
                _normalized_description(
                    component["description"], f"{component_label} description"
                )
                if "description" in component
                else None
            ),
            "group": component.get("group"),
            "hashes": hash_records,
            "externalReferences": sorted(
                _component_external_references(component, component_label)
            ),
            "licenses": sorted(
                _component_license_records(
                    component, component_label, allow_missing=True
                )
            ),
            "name": component.get("name"),
            "modified": component.get("modified"),
            "properties": sorted(
                (item["name"], item["value"])
                for item in _component_properties(component, component_label)
            ),
            "publisher": component.get("publisher"),
            "scope": component.get("scope"),
            "type": component.get("type"),
            "version": component.get("version"),
        }

    def xml_record(component: ET.Element, component_label: str) -> tuple[str, dict[str, Any]]:
        allowed_children = {
            qname(field)
            for field in SUPPORTED_COMPONENT_FIELDS
            if field not in {"type", "bom-ref", "components"}
        }
        unsupported_children = [
            child.tag for child in component if child.tag not in allowed_children
        ]
        if unsupported_children:
            raise PolicyError(
                f"{component_label} contains unsupported CycloneDX fields: "
                f"{unsupported_children}"
            )
        child_tags = [
            child.tag.removeprefix(f"{{{CYCLONEDX_XML_NAMESPACE}}}")
            for child in component
        ]
        component_order = {
            field: index for index, field in enumerate(COMPONENT_FIELD_ORDER)
        }
        if child_tags != sorted(
            child_tags, key=component_order.__getitem__
        ) or len(child_tags) != len(set(child_tags)):
            raise PolicyError(f"{component_label} has invalid component child order")
        if (
            set(component.attrib) != {"type", "bom-ref"}
            or (component.text or "").strip()
            or (component.tail or "").strip()
        ):
            raise PolicyError(f"{component_label} has an unsupported component shape")
        purl = xml_text(component, "purl", required=True)
        if component.get("bom-ref") != purl:
            raise PolicyError(f"{component_label} bom-ref must exactly equal purl")
        license_parent = component.findall(qname("licenses"))
        if len(license_parent) > 1:
            raise PolicyError(f"{component_label} repeats its licenses element")
        if license_parent and (
            license_parent[0].attrib
            or license_parent[0].text and license_parent[0].text.strip()
            or license_parent[0].tail and license_parent[0].tail.strip()
        ):
            raise PolicyError(f"{component_label} has invalid licenses content")
        licenses: list[LicenseRecord] = []
        license_choices = [] if not license_parent else list(license_parent[0])
        if license_parent and not license_choices:
            raise PolicyError(f"{component_label} has an empty licenses element")
        expression_choices = [
            child for child in license_choices if child.tag == qname("expression")
        ]
        if expression_choices and len(license_choices) != 1:
            raise PolicyError(
                f"{component_label} licenseChoice must be one expression or license objects"
            )
        for child in license_choices:
            if child.tag == qname("expression"):
                if (
                    child.attrib
                    or len(child)
                    or child.text is None
                    or child.tail and child.tail.strip()
                ):
                    raise PolicyError(f"{component_label} has an empty license expression")
                expression = _validate_spdx_expression(
                    _nonempty_string(child.text, "XML license expression"),
                    "XML license expression",
                )
                licenses.append(
                    (
                        "expression",
                        expression,
                        "",
                    )
                )
            elif child.tag == qname("license"):
                ids = child.findall(qname("id"))
                names = child.findall(qname("name"))
                urls = child.findall(qname("url"))
                unknown = [
                    item.tag
                    for item in list(child)
                    if item.tag not in {qname("id"), qname("name"), qname("url")}
                ]
                if (
                    len(ids) + len(names) != 1
                    or len(ids) > 1
                    or len(names) > 1
                    or len(urls) > 1
                    or unknown
                ):
                    raise PolicyError(f"{component_label} has an ambiguous license")
                expected_tags = [qname("id") if ids else qname("name")]
                if urls:
                    expected_tags.append(qname("url"))
                if [item.tag for item in list(child)] != expected_tags:
                    raise PolicyError(
                        f"{component_label} has invalid license child order"
                    )
                if (
                    child.attrib
                    or child.text and child.text.strip()
                    or child.tail and child.tail.strip()
                    or any(item.attrib for item in list(child))
                ):
                    raise PolicyError(f"{component_label} has an ambiguous license")
                kind = "id" if ids else "name"
                value = ids[0] if ids else names[0]
                value_label = f"XML license {kind}"
                if len(value) or value.tail and value.tail.strip():
                    raise PolicyError(f"{component_label} license value must be a leaf")
                if urls and (len(urls[0]) or urls[0].tail and urls[0].tail.strip()):
                    raise PolicyError(f"{component_label} license url must be a leaf")
                license_url = (
                    _absolute_http_url(urls[0].text, "XML license url")
                    if urls
                    else ""
                )
                identifier_value = _nonempty_string(value.text, value_label)
                if kind == "id":
                    _validate_spdx_license_id(identifier_value, value_label)
                licenses.append(
                    (kind, identifier_value, license_url)
                )
            else:
                raise PolicyError(f"{component_label} has an unsupported license choice")
        license_identities = [(kind, value) for kind, value, _ in licenses]
        if len(license_identities) != len(set(license_identities)):
            raise PolicyError(f"{component_label} has missing or duplicate licenses")
        hash_parents = component.findall(qname("hashes"))
        if len(hash_parents) > 1:
            raise PolicyError(f"{component_label} repeats hashes")
        hashes: list[tuple[str, str]] = []
        if hash_parents:
            if (
                hash_parents[0].attrib
                or (hash_parents[0].text or "").strip()
                or (hash_parents[0].tail or "").strip()
            ):
                raise PolicyError(f"{component_label} has invalid hashes content")
            for item in list(hash_parents[0]):
                if (
                    item.tag != qname("hash")
                    or set(item.attrib) != {"alg"}
                    or len(item)
                    or (item.tail or "").strip()
                ):
                    raise PolicyError(f"{component_label} has an unsupported hash element")
                hashes.append(
                    (
                        _nonempty_string(item.get("alg"), "XML hash algorithm"),
                        _nonempty_string(item.text, "XML hash content"),
                    )
                )
        if len(hashes) != len(set(hashes)):
            raise PolicyError(f"{component_label} has duplicate hashes")
        reference_parents = component.findall(qname("externalReferences"))
        if len(reference_parents) > 1:
            raise PolicyError(f"{component_label} repeats externalReferences")
        references: list[tuple[str, str]] = []
        if reference_parents:
            if (
                reference_parents[0].attrib
                or (reference_parents[0].text or "").strip()
                or (reference_parents[0].tail or "").strip()
            ):
                raise PolicyError(
                    f"{component_label} has invalid externalReferences content"
                )
            for reference in list(reference_parents[0]):
                if (
                    reference.tag != qname("reference")
                    or set(reference.attrib) != {"type"}
                    or (reference.text or "").strip()
                    or (reference.tail or "").strip()
                    or len(reference) != 1
                    or reference[0].tag != qname("url")
                    or reference[0].attrib
                    or len(reference[0])
                    or (reference[0].tail or "").strip()
                ):
                    raise PolicyError(
                        f"{component_label} has an unsupported external reference"
                    )
                references.append(
                    (
                        _nonempty_string(
                            reference.get("type"), "XML external reference type"
                        ),
                        _nonempty_string(
                            reference[0].text, "XML external reference url"
                        ),
                    )
                )
        if len(references) != len(set(references)):
            raise PolicyError(f"{component_label} repeats an external reference")
        property_parents = component.findall(qname("properties"))
        if len(property_parents) > 1:
            raise PolicyError(f"{component_label} repeats properties")
        properties: list[tuple[str, str]] = []
        if property_parents:
            if (
                property_parents[0].attrib
                or (property_parents[0].text or "").strip()
                or (property_parents[0].tail or "").strip()
            ):
                raise PolicyError(f"{component_label} has invalid properties content")
            for item in list(property_parents[0]):
                if (
                    item.tag != qname("property")
                    or set(item.attrib) != {"name"}
                    or len(item)
                    or (item.tail or "").strip()
                ):
                    raise PolicyError(f"{component_label} property must be a leaf")
                name = _nonempty_string(item.get("name"), "XML property name")
                value = _nonempty_string(item.text, "XML property value")
                properties.append((name, value))
        if len(properties) != len({name for name, _ in properties}):
            raise PolicyError(f"{component_label} repeats a property name")
        modified_text = xml_text(component, "modified")
        if modified_text is not None and modified_text not in {"true", "false"}:
            raise PolicyError(f"{component_label} modified must be true or false")
        group = xml_text(component, "group")
        name = xml_text(component, "name", required=True)
        version = xml_text(component, "version", required=True)
        if _is_forbidden_jts_io_identity(
            group, name, purl, component.get("bom-ref")
        ):
            raise PolicyError("JTS I/O Common is forbidden by the pinned policy")
        return purl, {
            "description": xml_text(component, "description"),
            "group": group,
            "externalReferences": sorted(references),
            "hashes": sorted(hashes),
            "licenses": sorted(licenses),
            "name": name,
            "modified": None if modified_text is None else modified_text == "true",
            "properties": sorted(properties),
            "publisher": xml_text(component, "publisher"),
            "scope": xml_text(component, "scope"),
            "type": component.get("type"),
            "version": version,
        }

    metadata = root.findall(qname("metadata"))
    if len(metadata) != 1:
        raise PolicyError(f"{label} XML SBOM must contain one metadata element")
    metadata_tags = [child.tag for child in metadata[0]]
    allowed_metadata = {qname(field) for field in METADATA_FIELDS}
    metadata_order = [
        qname("timestamp"),
        qname("tools"),
        qname("authors"),
        qname("component"),
        qname("manufacture"),
        qname("supplier"),
        qname("licenses"),
        qname("properties"),
        qname("lifecycles"),
    ]
    if (
        metadata[0].attrib
        or (metadata[0].text or "").strip()
        or (metadata[0].tail or "").strip()
        or any(tag not in allowed_metadata for tag in metadata_tags)
        or metadata_tags.count(qname("timestamp")) != 1
        or metadata_tags.count(qname("tools")) != 1
        or metadata_tags.count(qname("component")) != 1
        or metadata_tags.count(qname("licenses")) != 1
        or metadata_tags != sorted(metadata_tags, key=metadata_order.index)
    ):
        raise PolicyError(f"{label} XML metadata has an unsupported shape")
    xml_timestamp = metadata[0].find(qname("timestamp"))
    json_timestamp = metadata_json.get("timestamp")
    if xml_timestamp is None or json_timestamp is None:
        raise PolicyError(f"{label} JSON/XML metadata timestamps differ")
    if _validate_timestamp(
        xml_leaf(xml_timestamp, f"{label} XML metadata timestamp"),
        f"{label} XML metadata timestamp",
    ) != json_timestamp:
        raise PolicyError(f"{label} JSON/XML metadata timestamps differ")
    xml_tools = metadata[0].find(qname("tools"))
    json_tools = metadata_json.get("tools")
    if xml_tools is None or json_tools is None:
        raise PolicyError(f"{label} JSON/XML metadata tools differ")
    xml_wrapper(xml_tools, f"{label} XML metadata tools", {qname("components")})
    if len(xml_tools) != 1:
        raise PolicyError(f"{label} XML metadata tools are ambiguous")
    tool_components = xml_tools[0]
    xml_wrapper(
        tool_components,
        f"{label} XML metadata tool components",
        {qname("component")},
    )
    if len(tool_components) != 1:
        raise PolicyError(f"{label} XML metadata tools are ambiguous")
    tool = tool_components[0]
    if (
        tool.attrib != {"type": "application"}
        or (tool.text or "").strip()
        or (tool.tail or "").strip()
        or [child.tag for child in tool]
        != [qname("author"), qname("name"), qname("version")]
        or [
            xml_leaf(child, f"{label} XML metadata tool field")
            for child in tool
        ]
        != ["CycloneDX", "cyclonedx-gradle-plugin", "3.4.0"]
    ):
        raise PolicyError(f"{label} XML metadata tool is not the pinned producer")
    document_license_parents = metadata[0].findall(qname("licenses"))
    if len(document_license_parents) != 1:
        raise PolicyError(f"{label} XML document license is missing or repeated")
    document_license_parent = document_license_parents[0]
    document_choices = list(document_license_parent)
    if (
        document_license_parent.attrib
        or (document_license_parent.text or "").strip()
        or (document_license_parent.tail or "").strip()
        or len(document_choices) != 1
        or document_choices[0].tag != qname("license")
        or document_choices[0].attrib
        or (document_choices[0].text or "").strip()
        or (document_choices[0].tail or "").strip()
        or [child.tag for child in document_choices[0]]
        != [qname("id"), qname("url")]
    ):
        raise PolicyError(f"{label} XML document license is ambiguous")
    document_id, document_url = list(document_choices[0])
    if (
        document_id.attrib
        or document_url.attrib
        or len(document_id)
        or len(document_url)
        or document_id.text != "Apache-2.0"
        or document_url.text != APACHE_LICENSE_URL
        or (document_id.tail or "").strip()
        or (document_url.tail or "").strip()
    ):
        raise PolicyError(f"{label} XML document license is not exact Apache-2.0")
    xml_root_components = metadata[0].findall(qname("component"))
    if len(xml_root_components) != 1:
        raise PolicyError(f"{label} XML SBOM must contain one metadata component")
    component_parents = root.findall(qname("components"))
    if len(component_parents) != 1:
        raise PolicyError(f"{label} XML SBOM must contain one components element")
    xml_wrapper(
        component_parents[0], f"{label} XML components", {qname("component")}
    )
    xml_components = component_parents[0].findall(qname("component"))
    if any(
        component.find(qname("components")) is not None
        for component in [xml_root_components[0], *xml_components]
    ):
        raise PolicyError(f"{label} XML SBOM contains nested components")
    json_root = sbom["metadata"]["component"]
    json_root_purl = _component_purl(json_root, f"{label} JSON metadata component")
    json_root_record = json_record(json_root, f"{label} JSON metadata component")
    xml_root_purl, xml_root_record = xml_record(
        xml_root_components[0], f"{label} XML metadata component"
    )
    if (json_root_purl, json_root_record) != (xml_root_purl, xml_root_record):
        raise PolicyError(f"{label} JSON/XML metadata components differ")

    json_records: dict[str, dict[str, Any]] = {}
    for index, component in enumerate(sbom["components"]):
        purl = _component_purl(component, f"{label} JSON component {index}")
        if purl == json_root_purl:
            raise PolicyError(f"{label} JSON repeats its metadata component")
        if purl in json_records:
            raise PolicyError(f"{label} JSON repeats component purl: {purl}")
        json_records[purl] = json_record(component, f"{label} JSON component {index}")
    xml_records: dict[str, dict[str, Any]] = {}
    for index, component in enumerate(xml_components):
        purl, record = xml_record(component, f"{label} XML component {index}")
        if purl == xml_root_purl:
            raise PolicyError(f"{label} XML repeats its metadata component")
        if purl in xml_records:
            raise PolicyError(f"{label} XML repeats component purl: {purl}")
        xml_records[purl] = record
    if json_records != xml_records:
        raise PolicyError(f"{label} JSON/XML component records differ")

    def json_dependencies() -> dict[str, set[str]]:
        records = sbom.get("dependencies")
        if not isinstance(records, list):
            raise PolicyError(f"{label} JSON dependency graph is missing")
        result: dict[str, set[str]] = {}
        for record in records:
            if not isinstance(record, dict) or set(record) != {"ref", "dependsOn"}:
                raise PolicyError(f"{label} JSON dependency record is invalid")
            ref = _nonempty_string(record["ref"], "JSON dependency ref")
            targets = record["dependsOn"]
            if not isinstance(targets, list) or len(targets) != len(set(targets)):
                raise PolicyError(f"{label} JSON dependency targets are invalid")
            if ref in result or any(not isinstance(item, str) for item in targets):
                raise PolicyError(f"{label} JSON dependency graph repeats a record")
            result[ref] = set(targets)
        return result

    xml_dependencies: dict[str, set[str]] = {}
    dependency_parents = root.findall(qname("dependencies"))
    if len(dependency_parents) != 1:
        raise PolicyError(f"{label} XML dependency graph is missing or repeated")
    xml_wrapper(
        dependency_parents[0], f"{label} XML dependencies", {qname("dependency")}
    )
    for dependency in dependency_parents[0]:
        if (
            set(dependency.attrib) != {"ref"}
            or (dependency.text or "").strip()
            or (dependency.tail or "").strip()
            or any(
                child.tag != qname("dependency")
                or set(child.attrib) != {"ref"}
                or len(child)
                or (child.text or "").strip()
                or (child.tail or "").strip()
                for child in dependency
            )
        ):
            raise PolicyError(f"{label} XML dependency graph has an unsupported shape")
        ref = _nonempty_string(dependency.get("ref"), "XML dependency ref")
        targets = [
            _nonempty_string(child.get("ref"), "XML dependency target")
            for child in dependency
        ]
        if ref in xml_dependencies or len(targets) != len(set(targets)):
            raise PolicyError(f"{label} XML dependency graph repeats a record or edge")
        xml_dependencies[ref] = set(targets)
    if json_dependencies() != xml_dependencies:
        raise PolicyError(f"{label} JSON/XML dependency graphs differ")
    return len(json_records) + 1, hashlib.sha256(content).hexdigest()


def _component_purl(component: dict[str, Any], label: str) -> str:
    purl = _nonempty_string(component.get("purl"), f"{label} purl")
    if component.get("bom-ref") != purl:
        raise PolicyError(f"{label} bom-ref must exactly equal purl")
    return purl


def _component_license_records(
    component: dict[str, Any], label: str, *, allow_missing: bool = False
) -> list[LicenseRecord]:
    if "licenses" not in component and allow_missing:
        return []
    licenses = component.get("licenses")
    if not isinstance(licenses, list) or not licenses:
        raise PolicyError(f"{label} has no license metadata")
    expression_choices = [
        choice for choice in licenses if isinstance(choice, dict) and "expression" in choice
    ]
    if expression_choices and (
        len(licenses) != 1 or set(expression_choices[0]) != {"expression"}
    ):
        raise PolicyError(
            f"{label} licenseChoice must be one expression or license objects"
        )
    records: list[LicenseRecord] = []
    for index, choice in enumerate(licenses):
        if not isinstance(choice, dict) or len(choice) != 1:
            raise PolicyError(f"{label} license choice {index} is ambiguous")
        if "expression" in choice:
            expression = _validate_spdx_expression(
                _nonempty_string(
                    choice["expression"], f"{label} license expression"
                ),
                f"{label} license expression",
            )
            records.append(
                (
                    "expression",
                    expression,
                    "",
                )
            )
            continue
        license_value = choice.get("license")
        if not isinstance(license_value, dict):
            raise PolicyError(f"{label} license choice {index} is invalid")
        identifiers = [field for field in ("id", "name") if field in license_value]
        if len(identifiers) != 1:
            raise PolicyError(
                f"{label} license choice {index} must contain exactly one id or name"
            )
        identifier = identifiers[0]
        license_identifier = _nonempty_string(
            license_value[identifier], f"{label} license {identifier}"
        )
        if identifier == "id":
            _validate_spdx_license_id(
                license_identifier, f"{label} license id"
            )
        unknown = set(license_value) - {"id", "name", "url"}
        if unknown:
            raise PolicyError(f"{label} license contains unsupported fields: {sorted(unknown)}")
        license_url = (
            _absolute_http_url(license_value["url"], f"{label} license url")
            if "url" in license_value
            else ""
        )
        records.append((identifier, license_identifier, license_url))
    identities = [(kind, value) for kind, value, _ in records]
    if len(identities) != len(set(identities)):
        raise PolicyError(f"{label} repeats a license choice")
    return records


def _component_external_references(
    component: dict[str, Any], label: str
) -> list[tuple[str, str]]:
    references = component.get("externalReferences", [])
    if not isinstance(references, list):
        raise PolicyError(f"{label} externalReferences must be an array")
    normalized: list[tuple[str, str]] = []
    for index, reference in enumerate(references):
        if not isinstance(reference, dict):
            raise PolicyError(f"{label} external reference {index} must be an object")
        _exact_keys(
            reference, {"type", "url"}, f"{label} external reference {index}"
        )
        normalized.append(
            (
                _nonempty_string(reference["type"], f"{label} reference type"),
                _nonempty_string(reference["url"], f"{label} reference url"),
            )
        )
    if len(normalized) != len(set(normalized)):
        raise PolicyError(f"{label} repeats an external reference")
    return normalized


def _component_artifact_fingerprint(
    component: dict[str, Any], label: str
) -> tuple[Any, ...]:
    hashes = component.get("hashes", [])
    if not isinstance(hashes, list) or any(
        not isinstance(item, dict) or set(item) != {"alg", "content"}
        for item in hashes
    ):
        raise PolicyError(f"{label} has invalid hashes")
    hash_records = sorted(
        (
            _nonempty_string(item["alg"], f"{label} hash algorithm"),
            _nonempty_string(item["content"], f"{label} hash content"),
        )
        for item in hashes
    )
    if len(hash_records) != len(set(hash_records)):
        raise PolicyError(f"{label} has duplicate hashes")
    return (
        component.get("type"),
        component.get("group"),
        component.get("name"),
        component.get("version"),
        tuple(
            sorted(
                _component_license_records(component, label, allow_missing=True)
            )
        ),
        tuple(hash_records),
    )


def _component_properties(
    component: dict[str, Any], label: str
) -> list[dict[str, str]]:
    properties = component.get("properties", [])
    if not isinstance(properties, list):
        raise PolicyError(f"{label} properties must be an array")
    normalized: list[dict[str, str]] = []
    names: set[str] = set()
    for index, property_value in enumerate(properties):
        if not isinstance(property_value, dict):
            raise PolicyError(f"{label} property {index} must be an object")
        _exact_keys(property_value, {"name", "value"}, f"{label} property {index}")
        name = _nonempty_string(property_value["name"], f"{label} property name")
        value = _nonempty_string(property_value["value"], f"{label} property value")
        if name in names:
            raise PolicyError(f"{label} repeats property name: {name}")
        names.add(name)
        normalized.append({"name": name, "value": value})
    return normalized


def _prove_component_scope(
    component: dict[str, Any], scope: str, label: str
) -> None:
    properties = _component_properties(component, label)
    if scope in {"test-runtime", "aggregate-test-only"}:
        if component.get("type") != "library" or TEST_PROPERTY not in properties:
            raise PolicyError(f"{label} is not proven {scope} by SBOM type/properties")
        return
    if scope == "published-module":
        published_property = {
            "name": "cdx:maven:package:test",
            "value": "false",
        }
        if component.get("type") != "library" or published_property not in properties:
            raise PolicyError(f"{label} is not proven {scope} by SBOM type/properties")
        return
    if scope == "test-container":
        if (
            component.get("type") != "container"
            or component.get("scope") != "excluded"
            or TEST_CONTAINER_PROPERTY not in properties
        ):
            raise PolicyError(
                f"{label} is not proven test-container by SBOM type/scope/properties"
            )
        return
    raise PolicyError(f"unsupported component scope: {scope}")


def _validate_licenses(
    sbom: dict[str, Any],
    policy: dict[str, Any],
    *,
    require_all_exceptions: bool = True,
) -> int:
    allowed = set(policy["allowedLicenseIds"])
    exceptions = {
        (
            entry["purl"],
            entry["kind"],
            entry["license"],
            entry["url"] or "",
        ): entry
        for entry in policy["licenseExceptions"]
    }
    review_exceptions = {
        entry["purl"]: entry for entry in policy["licenseReviewExceptions"]
    }
    used_exceptions: set[tuple[str, str, str, str]] = set()
    used_review_exceptions: set[str] = set()
    licensed_component_count = 0
    metadata_component = sbom["metadata"]["component"]
    candidates = [("metadata.component", metadata_component)] + [
        (f"components[{index}]", component)
        for index, component in enumerate(sbom["components"])
    ]
    seen_purls: set[str] = set()
    for label, component in candidates:
        purl = _component_purl(component, label)
        if purl in seen_purls:
            raise PolicyError(f"duplicate component purl: {purl}")
        seen_purls.add(purl)
        policy_purl = (
            _canonical_maven_purl(purl)[0]
            if purl.startswith("pkg:maven/")
            else purl
        )
        records = _component_license_records(component, label, allow_missing=True)
        properties = _component_properties(component, label)
        review_properties = [
            item for item in properties if item["name"] == LICENSE_REVIEW_PROPERTY_NAME
        ]
        if not records:
            review_exception = review_exceptions.get(policy_purl)
            if review_exception is None:
                raise PolicyError(f"{label} has no license metadata")
            if (
                component.get("name") != review_exception["componentName"]
                or component.get("version") != review_exception["componentVersion"]
                or policy_purl != MYSQL_CONTAINER_PURL
                or component.get("hashes")
                != [
                    {
                        "alg": "SHA-256",
                        "content": review_exception["sha256"],
                    }
                ]
            ):
                raise PolicyError(
                    "license review component must exactly identify the pinned MySQL OCI image"
                )
            expected_review_property = {
                "name": LICENSE_REVIEW_PROPERTY_NAME,
                "value": review_exception["status"],
            }
            if review_properties != [expected_review_property]:
                raise PolicyError(
                    f"license review component {policy_purl} lacks its exact status property"
                )
            expected_reference = (
                "documentation",
                review_exception["documentationUrl"],
            )
            references = _component_external_references(component, label)
            if references != [expected_reference]:
                raise PolicyError(
                    f"license review component {policy_purl} lacks its exact documentation reference"
                )
            _absolute_http_url(
                references[0][1], "license review component documentation URL"
            )
            _prove_component_scope(
                component,
                review_exception["scope"],
                f"license review component {policy_purl}",
            )
            used_review_exceptions.add(policy_purl)
            continue
        licensed_component_count += 1
        if policy_purl.startswith(f"pkg:maven/{FIRST_PARTY_GROUP}/"):
            if review_properties:
                raise PolicyError(
                    f"licensed component must not carry reserved license review status: {purl}"
                )
            if records != [("id", "Apache-2.0", APACHE_LICENSE_URL)]:
                raise PolicyError(
                    f"first-party component {policy_purl} must use exact Apache-2.0 metadata"
                )
            continue
        jts_expression = JTS_LICENSE_EXPRESSIONS.get(policy_purl)
        if jts_expression is not None:
            if purl != f"{policy_purl}?type=jar":
                raise PolicyError(
                    f"JTS component {policy_purl} must use its exact resolved JAR purl"
                )
            exception_key = (
                policy_purl,
                "expression",
                jts_expression,
                "",
            )
            if (
                records != [("expression", jts_expression, "")]
                or exception_key not in exceptions
            ):
                raise PolicyError(
                    f"JTS component {policy_purl} must use its exact reviewed SPDX expression"
                )
            _prove_component_scope(
                component,
                exceptions[exception_key]["scope"],
                f"license exception component {policy_purl}",
            )
            used_exceptions.add(exception_key)
            if review_properties:
                raise PolicyError(
                    f"licensed component must not carry reserved license review status: {purl}"
                )
            continue
        if review_properties:
            raise PolicyError(
                f"licensed component must not carry reserved license review status: {purl}"
            )
        if all(
            kind in {"expression", "id"} and value in allowed
            for kind, value, _ in records
        ):
            continue
        if len(records) != 1:
            raise PolicyError(f"unapproved license for {purl}: {records}")
        kind, value, license_url = records[0]
        exception_key = (policy_purl, kind, value, license_url)
        if exception_key not in exceptions:
            raise PolicyError(f"unapproved license for {purl}: {records}")
        exception = exceptions[exception_key]
        _prove_component_scope(
            component,
            exception["scope"],
            f"license exception component {policy_purl}",
        )
        used_exceptions.add(exception_key)
    unused = set(exceptions) - used_exceptions
    if require_all_exceptions and unused:
        raise PolicyError(f"unused license exceptions: {sorted(unused)}")
    unused_reviews = set(review_exceptions) - used_review_exceptions
    if require_all_exceptions and unused_reviews:
        raise PolicyError(
            f"unused license review exceptions: {sorted(unused_reviews)}"
        )
    return licensed_component_count


def _validate_supported_component_ecosystems(
    sbom: dict[str, Any], policy: dict[str, Any], label: str
) -> None:
    reviewed_non_maven = {
        entry["purl"] for entry in policy["licenseReviewExceptions"]
    }
    candidates = [sbom["metadata"]["component"], *sbom["components"]]
    for index, component in enumerate(candidates):
        purl = _component_purl(component, f"{label} component {index}")
        if purl.startswith("pkg:maven/"):
            continue
        if purl not in reviewed_non_maven:
            raise PolicyError(
                f"{label} contains an unsupported non-Maven component: {purl}"
            )


def _maven_inventory(sbom: dict[str, Any]) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for component in sbom["components"]:
        purl = _component_purl(component, "SBOM component")
        if not purl.startswith("pkg:maven/"):
            continue
        resolved, _, group, name, version = _validate_resolved_maven_purl(purl)
        if resolved in inventory:
            raise PolicyError(f"duplicate resolved Maven purl: {resolved}")
        if component.get("group") != group or component.get("name") != name:
            raise PolicyError(f"Maven purl does not match group/name: {purl}")
        if component.get("version") != version:
            raise PolicyError(f"Maven purl does not match version: {purl}")
        inventory[resolved] = component
    if not inventory:
        raise PolicyError("aggregate SBOM contains no Maven components")
    return inventory


def _third_party_maven_inventory(sbom: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        purl: component
        for purl, component in _maven_inventory(sbom).items()
        if not purl.startswith(f"pkg:maven/{FIRST_PARTY_GROUP}/")
    }


def _osv_maven_inventory(sbom: dict[str, Any]) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    resolved_by_gav: dict[str, str] = {}
    for resolved, component in _maven_inventory(sbom).items():
        canonical, _, _, _, _ = _parse_maven_purl(resolved)
        if canonical in inventory:
            raise PolicyError(
                "multiple resolved Maven identities collapse to one OSV coordinate: "
                f"{resolved_by_gav[canonical]}, {resolved}"
            )
        inventory[canonical] = component
        resolved_by_gav[canonical] = resolved
    return inventory


def _validate_pinned_example_dependency_contract(
    aggregate_sbom: dict[str, Any], example_sbom: dict[str, Any]
) -> None:
    for label, sbom in (
        ("aggregate SBOM", aggregate_sbom),
        ("example SBOM", example_sbom),
    ):
        inventory = _maven_inventory(sbom)
        for group, name, version in REQUIRED_EXAMPLE_MAVEN_COORDINATES:
            prefix = f"pkg:maven/{group}/{name}@"
            expected = f"{prefix}{version}?type=jar"
            matches = {purl for purl in inventory if purl.startswith(prefix)}
            if matches != {expected}:
                raise PolicyError(
                    f"{label} must contain exactly {group}:{name}:{version}; "
                    f"found={sorted(matches)}"
                )


def _maven_inventory_with_root(sbom: dict[str, Any]) -> dict[str, dict[str, Any]]:
    inventory = _maven_inventory(sbom)
    root = sbom["metadata"]["component"]
    purl = _component_purl(root, "SBOM metadata.component")
    if purl.startswith("pkg:maven/"):
        canonical, group, name, version, qualifiers = _parse_maven_purl(purl)
        resolved = canonical + "?" + "&".join(
            f"{quote(key, safe='.-_~')}={quote(qualifiers[key], safe='.-_~')}"
            for key in sorted(qualifiers)
        )
        if resolved in inventory:
            raise PolicyError(f"duplicate resolved Maven purl including root: {resolved}")
        if (
            root.get("group") != group
            or root.get("name") != name
            or root.get("version") != version
        ):
            raise PolicyError("SBOM root Maven purl does not match group/name/version")
        inventory[resolved] = root
    return inventory


def _sbom_root_identity(
    sbom: dict[str, Any], expected_name: str, label: str
) -> tuple[str, str]:
    root = sbom["metadata"]["component"]
    purl = _component_purl(root, f"{label} metadata.component")
    canonical, group, name, version, qualifiers = _parse_maven_purl(purl)
    expected_project_path = ":" if expected_name == AGGREGATE_ROOT_NAME else f":{expected_name}"
    if (
        root.get("type") != "library"
        or group != FIRST_PARTY_GROUP
        or name != expected_name
        or qualifiers != {"project_path": expected_project_path}
        or root.get("group") != group
        or root.get("name") != name
        or root.get("version") != version
    ):
        raise PolicyError(f"{label} has an unexpected first-party root identity")
    resolved = canonical + "?" + "&".join(
        f"{quote(key, safe='.-_~')}={quote(qualifiers[key], safe='.-_~')}"
        for key in sorted(qualifiers)
    )
    return resolved, version


def _validate_sbom_roles(
    aggregate_sbom: dict[str, Any],
    published_sbom: dict[str, Any],
    example_sbom: dict[str, Any],
) -> tuple[str, str, str]:
    aggregate_root, aggregate_version = _sbom_root_identity(
        aggregate_sbom, AGGREGATE_ROOT_NAME, "aggregate SBOM"
    )
    published_root, published_version = _sbom_root_identity(
        published_sbom, PUBLISHED_ROOT_NAME, "published SBOM"
    )
    example_root, example_version = _sbom_root_identity(
        example_sbom, EXAMPLE_ROOT_NAME, "example SBOM"
    )
    if len({aggregate_version, published_version, example_version}) != 1:
        raise PolicyError("aggregate/published/example SBOM versions differ")
    aggregate_components = _maven_inventory(aggregate_sbom)
    published_components = _maven_inventory(published_sbom)
    example_components = _maven_inventory(example_sbom)
    aggregate_first_party = {
        purl: component
        for purl, component in aggregate_components.items()
        if _parse_maven_purl(purl)[1] == FIRST_PARTY_GROUP
    }
    published_first_party = {
        purl: component
        for purl, component in published_components.items()
        if _parse_maven_purl(purl)[1] == FIRST_PARTY_GROUP
    }
    example_first_party = {
        purl: component
        for purl, component in example_components.items()
        if _parse_maven_purl(purl)[1] == FIRST_PARTY_GROUP
    }
    if set(aggregate_first_party) != {published_root, example_root}:
        raise PolicyError(
            "aggregate SBOM must contain exactly the published and example project components"
        )
    if published_first_party:
        raise PolicyError("published SBOM must not contain another first-party project")
    if set(example_first_party) != {published_root}:
        raise PolicyError(
            "example SBOM must contain exactly the published first-party project component"
        )
    for root, name, label in (
        (published_root, PUBLISHED_ROOT_NAME, "published"),
        (example_root, EXAMPLE_ROOT_NAME, "example"),
    ):
        if root not in aggregate_components:
            raise PolicyError(f"aggregate SBOM is missing its {label} project component")
        aggregate_project = aggregate_components[root]
        _, group, component_name, version, qualifiers = _parse_maven_purl(
            _component_purl(aggregate_project, f"aggregate {label} project component")
        )
        if (
            group != FIRST_PARTY_GROUP
            or component_name != name
            or version != aggregate_version
            or qualifiers != {"project_path": f":{name}"}
        ):
            raise PolicyError(
                f"aggregate SBOM has an unexpected {label} project identity"
            )
        if _component_properties(
            aggregate_project, f"aggregate {label} project component"
        ) != [{"name": "cdx:maven:package:test", "value": "false"}]:
            raise PolicyError(
                f"aggregate {label} project component has an unexpected role property"
            )

    aggregate_published = aggregate_first_party[published_root]
    aggregate_example = aggregate_first_party[example_root]
    direct_published_root = published_sbom["metadata"]["component"]
    direct_example_root = example_sbom["metadata"]["component"]
    example_published = example_first_party[published_root]
    for left, right, label in (
        (
            aggregate_published,
            direct_published_root,
            "aggregate/published project",
        ),
        (aggregate_example, direct_example_root, "aggregate/example project"),
        (example_published, direct_published_root, "example/published project"),
    ):
        if _component_artifact_fingerprint(left, label) != (
            _component_artifact_fingerprint(right, label)
        ):
            raise PolicyError(f"{label} component identities differ")
    if _component_properties(
        example_published, "example published project component"
    ) != [{"name": "cdx:maven:package:test", "value": "true"}]:
        raise PolicyError(
            "example published project component is not exactly test-scoped"
        )

    def root_targets(sbom: dict[str, Any], root: str, label: str) -> set[str]:
        records = sbom.get("dependencies")
        if not isinstance(records, list):
            raise PolicyError(f"{label} dependency graph is missing")
        matching = [record for record in records if record.get("ref") == root]
        if len(matching) != 1 or not isinstance(matching[0].get("dependsOn"), list):
            raise PolicyError(f"{label} dependency graph lacks one exact root record")
        return set(matching[0]["dependsOn"])

    if not {published_root, example_root} <= root_targets(
        aggregate_sbom, aggregate_root, "aggregate SBOM"
    ):
        raise PolicyError(
            "aggregate SBOM root must directly reach both first-party project components"
        )
    if published_root not in root_targets(
        example_sbom, example_root, "example SBOM"
    ):
        raise PolicyError(
            "example SBOM root must directly reach the published project component"
        )
    return aggregate_root, published_root, example_root


def _inventory_content(inventory: dict[str, dict[str, Any]]) -> str:
    coordinates = []
    for purl in inventory:
        _, group, name, version = _canonical_maven_purl(purl)
        coordinates.append(f"{group}:{name}:{version}=aggregateSbom")
    return (
        "# Generated from the verified aggregate CycloneDX SBOM; do not edit.\n"
        + "\n".join(sorted(coordinates))
        + "\nempty=\n"
    )


def _purl_set_sha256(purls: set[str]) -> str:
    content = "" if not purls else "\n".join(sorted(purls)) + "\n"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _published_pom_inventory(
    path: Path, published_sbom: dict[str, Any]
) -> dict[str, str]:
    content = _read_regular_bytes(path, "generated published POM")
    root = _parse_canonical_xml(
        content,
        "generated published POM",
        allowed_root_comments=GRADLE_METADATA_POM_COMMENTS,
    )
    namespace = {"m": MAVEN_NAMESPACE}
    if (
        root.tag != f"{{{MAVEN_NAMESPACE}}}project"
        or root.attrib
        != {
            "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation":
                "http://maven.apache.org/POM/4.0.0 "
                "https://maven.apache.org/xsd/maven-4.0.0.xsd"
        }
        or (root.text or "").strip()
        or (root.tail or "").strip()
    ):
        raise PolicyError("generated published POM has an unexpected root element")
    if root.findall("m:parent", namespace):
        raise PolicyError("generated published POM must not inherit from a parent")
    allowed_project_children = {
        f"{{{MAVEN_NAMESPACE}}}{name}"
        for name in (
            "modelVersion",
            "groupId",
            "artifactId",
            "version",
            "packaging",
            "name",
            "description",
            "url",
            "licenses",
            "scm",
            "dependencies",
        )
    }
    unexpected_project_children = [
        child.tag for child in root if child.tag not in allowed_project_children
    ]
    if unexpected_project_children:
        raise PolicyError(
            "generated published POM contains unsupported project fields: "
            f"{unexpected_project_children}"
        )

    def exact_leaf(element: ET.Element, label: str) -> str:
        if (
            element.attrib
            or len(element)
            or element.text is None
            or not element.text.strip()
            or (element.tail or "").strip()
        ):
            raise PolicyError(f"generated published POM {label} must be a scalar leaf")
        return element.text

    for optional_leaf_name in ("name", "description", "url"):
        optional_leaves = root.findall(f"m:{optional_leaf_name}", namespace)
        if len(optional_leaves) > 1:
            raise PolicyError(
                f"generated published POM repeats project {optional_leaf_name}"
            )
        if optional_leaves:
            exact_leaf(optional_leaves[0], f"project {optional_leaf_name}")
    scm_parents = root.findall("m:scm", namespace)
    if len(scm_parents) > 1:
        raise PolicyError("generated published POM repeats scm")
    if scm_parents:
        scm = scm_parents[0]
        expected_scm_fields = [
            f"{{{MAVEN_NAMESPACE}}}connection",
            f"{{{MAVEN_NAMESPACE}}}developerConnection",
            f"{{{MAVEN_NAMESPACE}}}url",
        ]
        if (
            scm.attrib
            or (scm.text or "").strip()
            or (scm.tail or "").strip()
            or [child.tag for child in scm] != expected_scm_fields
        ):
            raise PolicyError("generated published POM scm is ambiguous")
        for child in scm:
            exact_leaf(child, "scm field")

    def required_text(parent: ET.Element, name: str, label: str) -> str:
        values = parent.findall(f"m:{name}", namespace)
        if (
            len(values) != 1
        ):
            raise PolicyError(f"generated published POM must contain one {label}")
        text = _nonempty_string(exact_leaf(values[0], label).strip(), label)
        if re.fullmatch(r"[A-Za-z0-9_.-]+", text) is None:
            raise PolicyError(f"generated published POM {label} is not a literal value")
        return text

    model_version = required_text(root, "modelVersion", "modelVersion")
    if model_version != "4.0.0":
        raise PolicyError("generated published POM modelVersion must be exactly 4.0.0")
    pom_group = required_text(root, "groupId", "project groupId")
    pom_name = required_text(root, "artifactId", "project artifactId")
    pom_version = required_text(root, "version", "project version")
    packaging_nodes = root.findall("m:packaging", namespace)
    if packaging_nodes:
        if (
            len(packaging_nodes) != 1
            or packaging_nodes[0].attrib
            or len(packaging_nodes[0])
            or packaging_nodes[0].text is None
            or packaging_nodes[0].text.strip() != "jar"
            or (packaging_nodes[0].tail or "").strip()
        ):
            raise PolicyError("generated published POM packaging must be jar when present")
    license_parents = root.findall("m:licenses", namespace)
    if len(license_parents) != 1:
        raise PolicyError("generated published POM must contain one licenses element")
    license_parent = license_parents[0]
    licenses = list(license_parent)
    expected_license_children = [
        f"{{{MAVEN_NAMESPACE}}}name",
        f"{{{MAVEN_NAMESPACE}}}url",
        f"{{{MAVEN_NAMESPACE}}}distribution",
    ]
    if (
        license_parent.attrib
        or (license_parent.text or "").strip()
        or (license_parent.tail or "").strip()
        or len(licenses) != 1
        or licenses[0].tag != f"{{{MAVEN_NAMESPACE}}}license"
        or licenses[0].attrib
        or (licenses[0].text or "").strip()
        or (licenses[0].tail or "").strip()
        or [child.tag for child in licenses[0]] != expected_license_children
    ):
        raise PolicyError("generated published POM license declaration is ambiguous")
    license_values = list(licenses[0])
    if any(
        child.attrib or len(child) or (child.tail or "").strip()
        for child in license_values
    ) or [child.text for child in license_values] != [
        "The Apache License, Version 2.0",
        "https://www.apache.org/licenses/LICENSE-2.0.txt",
        "repo",
    ]:
        raise PolicyError(
            "generated published POM must declare the exact Apache-2.0 license"
        )
    pom_project, _, _, _ = _canonical_maven_purl(
        f"pkg:maven/{pom_group}/{pom_name}@{pom_version}"
    )
    sbom_project = _canonical_maven_purl(
        _component_purl(published_sbom["metadata"]["component"], "published SBOM metadata.component")
    )[0]
    if pom_project != sbom_project:
        raise PolicyError("generated published POM identity differs from published SBOM")

    dependencies: dict[str, str] = {}
    dependency_parent = root.findall("m:dependencies", namespace)
    if len(dependency_parent) > 1:
        raise PolicyError("generated published POM repeats dependencies")
    if dependency_parent and (
        dependency_parent[0].attrib
        or (dependency_parent[0].text or "").strip()
        or (dependency_parent[0].tail or "").strip()
        or any(
            child.tag != f"{{{MAVEN_NAMESPACE}}}dependency"
            for child in dependency_parent[0]
        )
    ):
        raise PolicyError("generated published POM dependencies are ambiguous")
    for dependency in root.findall("m:dependencies/m:dependency", namespace):
        allowed_children = {
            f"{{{MAVEN_NAMESPACE}}}groupId",
            f"{{{MAVEN_NAMESPACE}}}artifactId",
            f"{{{MAVEN_NAMESPACE}}}version",
            f"{{{MAVEN_NAMESPACE}}}scope",
        }
        unexpected = [child.tag for child in dependency if child.tag not in allowed_children]
        expected_dependency_order = [
            f"{{{MAVEN_NAMESPACE}}}groupId",
            f"{{{MAVEN_NAMESPACE}}}artifactId",
            f"{{{MAVEN_NAMESPACE}}}version",
        ]
        if dependency.find("m:scope", namespace) is not None:
            expected_dependency_order.append(f"{{{MAVEN_NAMESPACE}}}scope")
        if (
            dependency.attrib
            or (dependency.text or "").strip()
            or (dependency.tail or "").strip()
            or unexpected
            or [child.tag for child in dependency] != expected_dependency_order
        ):
            raise PolicyError(
                "generated published POM dependency has unsupported fields or order"
            )
        group = required_text(dependency, "groupId", "dependency groupId")
        name = required_text(dependency, "artifactId", "dependency artifactId")
        version = required_text(dependency, "version", "dependency version")
        scope_nodes = dependency.findall("m:scope", namespace)
        scope = "compile"
        if scope_nodes:
            if (
                len(scope_nodes) != 1
                or scope_nodes[0].attrib
                or len(scope_nodes[0])
                or scope_nodes[0].text is None
                or (scope_nodes[0].tail or "").strip()
            ):
                raise PolicyError("generated published POM dependency has ambiguous scope")
            scope = _nonempty_string(scope_nodes[0].text.strip(), "dependency scope")
        if scope not in {"compile", "runtime"}:
            raise PolicyError(
                f"generated published POM contains unsupported dependency scope: {scope}"
            )
        purl, _, _, _ = _canonical_maven_purl(
            f"pkg:maven/{group}/{name}@{version}"
        )
        if purl in dependencies:
            raise PolicyError(f"generated published POM repeats dependency: {purl}")
        dependencies[purl] = scope
    return dependencies


def _published_runtime_lock_inventory(path: Path) -> set[str]:
    content = _read_text(path, "published module dependency lock")
    runtime: set[str] = set()
    seen: set[str] = set()
    saw_empty = False
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line or line.startswith("#"):
            continue
        if line.startswith("empty="):
            if saw_empty:
                raise PolicyError("published dependency lock repeats empty record")
            empty_configurations = line.removeprefix("empty=").split(",")
            if any(
                re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", value) is None
                for value in empty_configurations
            ):
                raise PolicyError("published dependency lock empty record is invalid")
            saw_empty = True
            continue
        if line.count("=") != 1:
            raise PolicyError(
                f"published dependency lock line {line_number} is invalid"
            )
        coordinate, configuration_text = line.split("=", 1)
        parts = coordinate.split(":")
        if len(parts) != 3 or not configuration_text:
            raise PolicyError(
                f"published dependency lock line {line_number} is invalid"
            )
        canonical, _, _, _ = _canonical_maven_purl(
            f"pkg:maven/{parts[0]}/{parts[1]}@{parts[2]}"
        )
        configurations = configuration_text.split(",")
        if (
            canonical in seen
            or configurations != sorted(set(configurations))
            or any(
                re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", value) is None
                for value in configurations
            )
        ):
            raise PolicyError(
                f"published dependency lock line {line_number} is ambiguous"
            )
        seen.add(canonical)
        if "runtimeClasspath" in configurations:
            runtime.add(canonical)
    if not saw_empty or not seen:
        raise PolicyError("published dependency lock is incomplete")
    return runtime


def _validate_root_reachable_dependency_graph(
    sbom: dict[str, Any], label: str
) -> None:
    root_ref = _component_purl(sbom["metadata"]["component"], f"{label} root")
    component_refs = {
        _component_purl(component, f"{label} component")
        for component in sbom["components"]
    }
    nodes = {root_ref, *component_refs}
    if len(nodes) != len(sbom["components"]) + 1:
        raise PolicyError(f"{label} repeats its root or a component")
    records = sbom.get("dependencies")
    if not isinstance(records, list):
        raise PolicyError(f"{label} dependency graph is missing")
    graph: dict[str, set[str]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise PolicyError(f"{label} dependency record {index} is invalid")
        _exact_keys(record, {"ref", "dependsOn"}, f"{label} dependency record {index}")
        ref = _nonempty_string(record["ref"], f"{label} dependency ref")
        targets = record["dependsOn"]
        if ref not in nodes or not isinstance(targets, list):
            raise PolicyError(f"{label} dependency graph has an unknown ref")
        if ref in graph or ref in targets or len(targets) != len(set(targets)):
            raise PolicyError(f"{label} dependency graph repeats a node or edge")
        if any(not isinstance(target, str) or target not in nodes for target in targets):
            raise PolicyError(f"{label} dependency graph has a dangling edge")
        graph[ref] = set(targets)
    if root_ref not in graph:
        raise PolicyError(f"{label} dependency graph is missing its root record")
    if set(graph) != nodes:
        raise PolicyError(f"{label} dependency graph does not cover every node")
    reachable: set[str] = set()
    pending = [root_ref]
    while pending:
        ref = pending.pop()
        if ref in reachable:
            continue
        reachable.add(ref)
        pending.extend(graph.get(ref, set()))
    if reachable != nodes:
        raise PolicyError(f"{label} contains a node unreachable from its root")


def _published_inventory(
    published_sbom: dict[str, Any], published_pom: Path, published_lock: Path
) -> tuple[dict[str, dict[str, Any]], dict[str, str], set[str]]:
    resolved_inventory = _maven_inventory(published_sbom)
    osv_inventory = _osv_maven_inventory(published_sbom)
    pom_dependencies = _published_pom_inventory(published_pom, published_sbom)
    runtime_locked = _published_runtime_lock_inventory(published_lock)
    missing = set(pom_dependencies) - set(osv_inventory)
    if missing:
        raise PolicyError(
            f"published POM dependencies are missing from published SBOM: {sorted(missing)}"
        )
    resolved_by_gav = {
        _parse_maven_purl(resolved)[0]: resolved for resolved in resolved_inventory
    }
    for dependency in pom_dependencies:
        resolved = resolved_by_gav[dependency]
        if _parse_maven_purl(resolved)[4] != {"type": "jar"}:
            raise PolicyError(
                "published POM default-jar dependency is not a resolved jar component: "
                f"{dependency} -> {resolved}"
            )
    root_ref = _component_purl(
        published_sbom["metadata"]["component"], "published SBOM metadata.component"
    )
    root_resolved, _ = _sbom_root_identity(
        published_sbom, PUBLISHED_ROOT_NAME, "published SBOM"
    )
    exact_to_resolved: dict[str, str] = {root_ref: root_resolved}
    for component in published_sbom["components"]:
        purl = _component_purl(component, "published SBOM component")
        if not purl.startswith("pkg:maven/"):
            raise PolicyError("published SBOM must contain only Maven components")
        exact_to_resolved[purl] = _validate_resolved_maven_purl(purl)[0]
    dependency_records = published_sbom.get("dependencies")
    if not isinstance(dependency_records, list):
        raise PolicyError("published SBOM dependency graph is missing")
    graph: dict[str, set[str]] = {}
    for index, record in enumerate(dependency_records):
        if not isinstance(record, dict):
            raise PolicyError(f"published SBOM dependency record {index} is invalid")
        _exact_keys(
            record,
            {"ref", "dependsOn"},
            f"published SBOM dependency record {index}",
        )
        ref = _nonempty_string(record["ref"], "published SBOM dependency ref")
        targets = record["dependsOn"]
        if ref not in exact_to_resolved or not isinstance(targets, list):
            raise PolicyError("published SBOM dependency graph has an unknown ref")
        if ref in graph or ref in targets or len(targets) != len(set(targets)):
            raise PolicyError("published SBOM dependency graph repeats a node or edge")
        if any(target not in exact_to_resolved for target in targets):
            raise PolicyError("published SBOM dependency graph has a dangling edge")
        graph[ref] = set(targets)
    if set(graph) != set(exact_to_resolved):
        raise PolicyError("published SBOM dependency graph does not cover every node")
    reachable: set[str] = set()
    pending = [root_ref]
    while pending:
        ref = pending.pop()
        if ref in reachable:
            continue
        reachable.add(ref)
        pending.extend(graph[ref])
    if reachable != set(graph):
        raise PolicyError("published SBOM contains a node unreachable from its root")
    root_direct = {
        _parse_maven_purl(exact_to_resolved[target])[0]
        for target in graph[root_ref]
    }
    expected_pom_dependencies = {
        _parse_maven_purl(exact_to_resolved[target])[0]
        for target in graph[root_ref]
        if _parse_maven_purl(exact_to_resolved[target])[4] == {"type": "jar"}
        and _parse_maven_purl(exact_to_resolved[target])[0] in runtime_locked
    }
    if not expected_pom_dependencies:
        raise PolicyError("published runtime/direct dependency contract is empty")
    if set(pom_dependencies) != expected_pom_dependencies:
        raise PolicyError(
            "generated published POM dependencies differ from the locked runtime/direct "
            f"contract: expected={sorted(expected_pom_dependencies)}, "
            f"found={sorted(pom_dependencies)}"
        )
    if set(pom_dependencies.values()) != {"runtime"}:
        raise PolicyError(
            "generated published POM dependency scopes must exactly be runtime"
        )
    for dependency in pom_dependencies:
        if resolved_by_gav[dependency] not in {
            exact_to_resolved[target] for target in graph[root_ref]
        }:
            raise PolicyError(
                "published POM jar dependency is not the exact resolved root edge"
            )
    resolved_graph = {
        exact_to_resolved[ref]: {exact_to_resolved[target] for target in targets}
        for ref, targets in graph.items()
    }
    published_component_set = set(resolved_inventory)
    for ref, targets in resolved_graph.items():
        if ref != root_resolved and not targets <= published_component_set:
            raise PolicyError(
                "published dependency graph contains a back-edge to its project root"
            )
    canonical_graph = {
        _parse_maven_purl(ref)[0]: {
            _parse_maven_purl(target)[0] for target in targets
        }
        for ref, targets in resolved_graph.items()
    }
    runtime_closure: set[str] = set()
    pending_canonical = list(pom_dependencies)
    while pending_canonical:
        purl = pending_canonical.pop()
        if purl in runtime_closure:
            continue
        if purl not in osv_inventory:
            raise PolicyError(
                "published runtime closure escaped the published dependency set: "
                f"{purl}"
            )
        runtime_closure.add(purl)
        pending_canonical.extend(canonical_graph[purl])
    if runtime_closure != runtime_locked:
        raise PolicyError(
            "published SBOM/POM runtime closure differs from the dependency lock: "
            f"lockOnly={sorted(runtime_locked - runtime_closure)}, "
            f"closureOnly={sorted(runtime_closure - runtime_locked)}"
        )
    return resolved_inventory, pom_dependencies, runtime_closure


def _validate_resolved_profile_partition(
    aggregate_sbom: dict[str, Any],
    published_sbom: dict[str, Any],
    example_sbom: dict[str, Any],
) -> tuple[set[str], set[str], set[str], set[str]]:
    _, expected_published_root, expected_example_root = _validate_sbom_roles(
        aggregate_sbom, published_sbom, example_sbom
    )
    published = _maven_inventory_with_root(published_sbom)
    example = _maven_inventory_with_root(example_sbom)
    published_root, _ = _sbom_root_identity(
        published_sbom, PUBLISHED_ROOT_NAME, "published SBOM"
    )
    example_root, _ = _sbom_root_identity(
        example_sbom, EXAMPLE_ROOT_NAME, "example SBOM"
    )
    project_roots = {published_root, example_root}
    if (
        published_root != expected_published_root
        or example_root != expected_example_root
    ):
        raise PolicyError("direct SBOM roots changed during role validation")
    # Aggregate components include the two project modules, while each direct
    # SBOM carries its own module as metadata.component. Compare every resolved
    # third-party component, not only Maven, after removing those exact project
    # identities. Maven profile sets remain separately canonicalized for OSV.
    def resolved_identity(component: dict[str, Any], label: str) -> str:
        purl = _component_purl(component, label)
        return _validate_resolved_maven_purl(purl)[0] if purl.startswith("pkg:maven/") else purl

    def component_map(sbom: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for component in sbom["components"]:
            identity = resolved_identity(component, f"{label} component")
            if identity in result:
                raise PolicyError(f"{label} repeats resolved component identity: {identity}")
            result[identity] = component
        return result

    aggregate_component_map = component_map(aggregate_sbom, "aggregate SBOM")
    published_component_map = component_map(published_sbom, "published SBOM")
    example_component_map = component_map(example_sbom, "example SBOM")
    aggregate_components = set(aggregate_component_map) - project_roots
    direct_components = (
        set(published_component_map) | set(example_component_map)
    ) - project_roots
    if aggregate_components != direct_components:
        raise PolicyError(
            "aggregate third-party component set differs from direct profiles; "
            f"aggregateOnly={sorted(aggregate_components - direct_components)}, "
            f"profileOnly={sorted(direct_components - aggregate_components)}"
        )
    for identity in sorted(direct_components):
        candidates = [aggregate_component_map[identity]]
        if identity in published_component_map:
            candidates.append(published_component_map[identity])
        if identity in example_component_map:
            candidates.append(example_component_map[identity])
        fingerprints = {
            _component_artifact_fingerprint(
                component, f"cross-role component {identity}"
            )
            for component in candidates
        }
        if len(fingerprints) != 1:
            raise PolicyError(
                "cross-role component artifact metadata differs for resolved identity: "
                f"{identity}"
            )
    aggregate = set(_third_party_maven_inventory(aggregate_sbom))
    combined = (set(published) | set(example)) - project_roots
    if aggregate != combined:
        raise PolicyError(
            "aggregate Maven set differs from published/example direct profiles; "
            f"aggregateOnly={sorted(aggregate - combined)}, "
            f"profileOnly={sorted(combined - aggregate)}"
        )
    for purl, component in published.items():
        if purl != published_root:
            _prove_component_scope(
                component, "published-module", f"published SBOM {purl}"
            )
    for purl, component in example.items():
        if purl != example_root:
            _prove_component_scope(component, "test-runtime", f"example SBOM {purl}")
    published_resolved = set(published) - project_roots
    example_resolved = set(example) - project_roots
    published_osv = {_parse_maven_purl(purl)[0] for purl in published_resolved}
    example_osv = {_parse_maven_purl(purl)[0] for purl in example_resolved}
    if len(published_osv) != len(published_resolved) or len(example_osv) != len(example_resolved):
        raise PolicyError("resolved Maven profiles collapse to duplicate OSV coordinates")
    return published_resolved, example_resolved, published_osv, example_osv


def _validate_test_runtime_license_exception_scopes(
    policy: dict[str, Any],
    published_profile: set[str],
    example_profile: set[str],
    published_sbom: dict[str, Any],
    example_sbom: dict[str, Any],
) -> None:
    published_all = {
        _component_purl(component, "published SBOM component")
        for component in published_sbom["components"]
    }
    example_all = {
        _component_purl(component, "example SBOM component")
        for component in example_sbom["components"]
    }
    scoped_exceptions = [
        *policy["licenseExceptions"],
        *policy["licenseReviewExceptions"],
    ]
    for exception in scoped_exceptions:
        if exception["scope"] == "test-runtime":
            purl = _canonical_maven_purl(exception["purl"])[0]
            if purl in published_profile:
                raise PolicyError(
                    "published-module license cannot use a test-runtime exception: "
                    f"{purl}"
                )
            if purl not in example_profile:
                raise PolicyError(
                    f"test-runtime license exception is absent from example profile: {purl}"
                )
        elif exception["scope"] == "test-container":
            purl = exception["purl"]
            if purl in published_all:
                raise PolicyError(
                    f"published-module license review cannot use a test-container exception: {purl}"
                )
            if purl not in example_all:
                raise PolicyError(
                    f"test-container license review exception is absent from example profile: {purl}"
                )


def _load_scanner_lock(path: Path) -> dict[str, Any]:
    lock = _read_json(path)
    _exact_keys(lock, {"schemaVersion", "scanner", "database"}, "scanner lock")
    if lock["schemaVersion"] != 1:
        raise PolicyError("unsupported scanner lock schemaVersion")
    scanner = lock["scanner"]
    database = lock["database"]
    if not isinstance(scanner, dict) or not isinstance(database, dict):
        raise PolicyError("scanner lock sections must be objects")
    _exact_keys(
        scanner,
        {"name", "version", "commit", "scalibrVersion", "platforms"},
        "scanner lock scanner",
    )
    if scanner["name"] != "OSV-Scanner":
        raise PolicyError("unexpected scanner name")
    _nonempty_string(scanner["version"], "scanner version")
    if not isinstance(scanner["commit"], str) or HEX_40.fullmatch(scanner["commit"]) is None:
        raise PolicyError("scanner commit must be 40 lowercase hex characters")
    _nonempty_string(scanner["scalibrVersion"], "scalibr version")
    platforms = scanner["platforms"]
    if not isinstance(platforms, dict) or not platforms:
        raise PolicyError("scanner platforms must be a non-empty object")
    for platform_name, asset in platforms.items():
        _nonempty_string(platform_name, "platform name")
        if not isinstance(asset, dict):
            raise PolicyError("scanner platform asset must be an object")
        _exact_keys(asset, {"sha256", "size", "url"}, f"scanner platform {platform_name}")
        if not isinstance(asset["sha256"], str) or HEX_64.fullmatch(asset["sha256"]) is None:
            raise PolicyError("scanner asset sha256 must be 64 lowercase hex characters")
        if not isinstance(asset["size"], int) or asset["size"] <= 0:
            raise PolicyError("scanner asset size must be a positive integer")
        if not _nonempty_string(asset["url"], "scanner asset url").startswith("https://"):
            raise PolicyError("scanner asset url must use https")
    _exact_keys(
        database,
        {"ecosystem", "generation", "lastModified", "sha256", "size", "url"},
        "scanner lock database",
    )
    if database["ecosystem"] != "Maven":
        raise PolicyError("offline database must be Maven")
    if not isinstance(database["generation"], str) or not database["generation"].isdigit():
        raise PolicyError("database generation must be decimal text")
    last_modified_text = database["lastModified"]
    if not isinstance(last_modified_text, str) or re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", last_modified_text
    ) is None:
        raise PolicyError(
            "database lastModified must be canonical UTC with millisecond precision"
        )
    try:
        last_modified = datetime.fromisoformat(
            last_modified_text.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise PolicyError("database lastModified must be ISO-8601") from error
    if last_modified.tzinfo != timezone.utc:
        raise PolicyError("database lastModified must use UTC")
    generation_time = datetime.fromtimestamp(
        int(database["generation"]) / 1_000_000, timezone.utc
    )
    provenance_delta = (last_modified - generation_time).total_seconds()
    if provenance_delta < 0 or provenance_delta >= 1:
        raise PolicyError(
            "database lastModified does not match the pinned generation object"
        )
    if not isinstance(database["sha256"], str) or HEX_64.fullmatch(database["sha256"]) is None:
        raise PolicyError("database sha256 must be 64 lowercase hex characters")
    if not isinstance(database["size"], int) or database["size"] <= 0:
        raise PolicyError("database size must be a positive integer")
    url = _nonempty_string(database["url"], "database url")
    if not url.startswith("https://") or f"generation={database['generation']}" not in url:
        raise PolicyError("database url must be https and generation-pinned")
    return lock


def _scanner_packages(raw_scan: dict[str, Any]) -> list[dict[str, Any]]:
    results = raw_scan.get("results")
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        raise PolicyError("OSV scan must contain exactly one result")
    source = results[0].get("source")
    if not isinstance(source, dict) or source.get("type") != "lockfile":
        raise PolicyError("OSV result source must be the derived lockfile")
    packages = results[0].get("packages")
    if not isinstance(packages, list) or any(not isinstance(item, dict) for item in packages):
        raise PolicyError("OSV packages must be an array of objects")
    return packages


def _scanner_purl(entry: dict[str, Any]) -> str:
    package = entry.get("package")
    if not isinstance(package, dict) or package.get("ecosystem") != "Maven":
        raise PolicyError("OSV package must use the Maven ecosystem")
    name = _nonempty_string(package.get("name"), "OSV package name")
    version = _nonempty_string(package.get("version"), "OSV package version")
    if name.count(":") != 1:
        raise PolicyError(f"OSV Maven package lacks exact group:artifact identity: {name}")
    group, artifact = name.split(":")
    canonical, _, _, _ = _canonical_maven_purl(
        f"pkg:maven/{group}/{artifact}@{version}"
    )
    return canonical


def _fixed_version(vulnerability: dict[str, Any], package_name: str) -> str | None:
    affected = vulnerability.get("affected")
    if not isinstance(affected, list):
        raise PolicyError("OSV vulnerability affected list is missing")
    fixed: set[str] = set()
    matched = False
    for record in affected:
        if not isinstance(record, dict):
            raise PolicyError("OSV affected record must be an object")
        package = record.get("package")
        if not isinstance(package, dict) or package.get("name") != package_name:
            continue
        matched = True
        ranges = record.get("ranges", [])
        if not isinstance(ranges, list):
            raise PolicyError("OSV affected ranges must be an array")
        for range_value in ranges:
            if not isinstance(range_value, dict):
                raise PolicyError("OSV affected range must be an object")
            events = range_value.get("events", [])
            if not isinstance(events, list):
                raise PolicyError("OSV range events must be an array")
            for event in events:
                if not isinstance(event, dict):
                    raise PolicyError("OSV range event must be an object")
                if "fixed" in event:
                    fixed.add(_nonempty_string(event["fixed"], "OSV fixed version"))
    if not matched:
        raise PolicyError(f"OSV vulnerability has no affected record for {package_name}")
    if len(fixed) > 1:
        raise PolicyError(
            "OSV vulnerability has ambiguous fixed versions for "
            f"{package_name}: {sorted(fixed)}"
        )
    return next(iter(fixed), None)


def _findings(
    packages: list[dict[str, Any]], inventory: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    expected = set(inventory)
    actual: set[str] = set()
    findings: list[dict[str, Any]] = []
    for entry in packages:
        purl = _scanner_purl(entry)
        if purl in actual:
            raise PolicyError(f"OSV scan repeats package: {purl}")
        actual.add(purl)
        vulnerabilities = entry.get("vulnerabilities", [])
        groups = entry.get("groups", [])
        if not isinstance(vulnerabilities, list) or not isinstance(groups, list):
            raise PolicyError("OSV vulnerability/group fields must be arrays")
        group_ids: set[str] = set()
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("ids"), list):
                raise PolicyError("OSV vulnerability group is invalid")
            for advisory in group["ids"]:
                group_ids.add(_nonempty_string(advisory, "OSV group advisory"))
        vulnerability_ids: set[str] = set()
        package_name = purl.removeprefix("pkg:maven/").split("@", 1)[0].replace("/", ":", 1)
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                raise PolicyError("OSV vulnerability must be an object")
            advisory = _nonempty_string(vulnerability.get("id"), "OSV advisory")
            if advisory in vulnerability_ids:
                raise PolicyError(f"OSV scan repeats advisory for {purl}: {advisory}")
            vulnerability_ids.add(advisory)
            database_specific = vulnerability.get("database_specific")
            if not isinstance(database_specific, dict):
                raise PolicyError("OSV vulnerability database_specific is missing")
            severity = _nonempty_string(
                database_specific.get("severity"), "OSV vulnerability severity"
            )
            findings.append(
                {
                    "advisory": advisory,
                    "fixedVersion": _fixed_version(vulnerability, package_name),
                    "purl": purl,
                    "severity": severity,
                }
            )
        if group_ids != vulnerability_ids:
            raise PolicyError(f"OSV group/vulnerability ids differ for {purl}")
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise PolicyError(
            "OSV package set does not exactly match the SBOM Maven set; "
            f"missing={missing}, unexpected={unexpected}"
        )
    return sorted(findings, key=lambda item: (item["purl"], item["advisory"]))


def _apply_vulnerability_policy(
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if findings:
        finding = findings[0]
        raise PolicyError(
            "vulnerability findings are forbidden by the pinned policy: "
            f"{finding['purl']} {finding['advisory']}"
        )
    return []


def _inventory_command(arguments: argparse.Namespace) -> None:
    sbom = _load_sbom(arguments.sbom)
    published_sbom = _load_sbom(arguments.published_sbom)
    example_sbom = _load_sbom(arguments.example_sbom)
    policy = _load_policy(arguments.policy)
    for role_label, role_sbom in (
        ("aggregate SBOM", sbom),
        ("published SBOM", published_sbom),
        ("example SBOM", example_sbom),
    ):
        _validate_supported_component_ecosystems(role_sbom, policy, role_label)
    _validate_sbom_roles(sbom, published_sbom, example_sbom)
    _validate_pinned_example_dependency_contract(sbom, example_sbom)
    _validate_licenses(sbom, policy)
    _validate_licenses(published_sbom, policy, require_all_exceptions=False)
    _validate_licenses(example_sbom, policy, require_all_exceptions=False)
    _validate_xml_pair(sbom, arguments.sbom_xml, "aggregate")
    _validate_xml_pair(published_sbom, arguments.published_sbom_xml, "published")
    _validate_xml_pair(example_sbom, arguments.example_sbom_xml, "example")
    _published_inventory(
        published_sbom, arguments.published_pom, arguments.published_lock
    )
    _, _, published_profile, example_profile = (
        _validate_resolved_profile_partition(sbom, published_sbom, example_sbom)
    )
    _validate_root_reachable_dependency_graph(sbom, "aggregate SBOM")
    _validate_root_reachable_dependency_graph(example_sbom, "example SBOM")
    _validate_test_runtime_license_exception_scopes(
        policy, published_profile, example_profile, published_sbom, example_sbom
    )
    inventory = _osv_maven_inventory(sbom)
    _write_text_atomic(arguments.output, _inventory_content(inventory))
    print(f"verified supply-chain inventory: {len(inventory)} Maven packages")


def _verify_command(arguments: argparse.Namespace) -> None:
    if HEX_40.fullmatch(arguments.revision) is None:
        raise PolicyError("revision must be exactly 40 lowercase hex characters")
    if HEX_40.fullmatch(arguments.source_tree) is None:
        raise PolicyError("source tree must be exactly 40 lowercase hex characters")
    sbom = _load_sbom(arguments.sbom)
    published_sbom = _load_sbom(arguments.published_sbom)
    example_sbom = _load_sbom(arguments.example_sbom)
    policy, policy_content = _load_policy_snapshot(arguments.policy)
    for role_label, role_sbom in (
        ("aggregate SBOM", sbom),
        ("published SBOM", published_sbom),
        ("example SBOM", example_sbom),
    ):
        _validate_supported_component_ecosystems(role_sbom, policy, role_label)
    _validate_sbom_roles(sbom, published_sbom, example_sbom)
    _validate_pinned_example_dependency_contract(sbom, example_sbom)
    license_component_count = _validate_licenses(sbom, policy)
    published_license_component_count = _validate_licenses(
        published_sbom, policy, require_all_exceptions=False
    )
    example_license_component_count = _validate_licenses(
        example_sbom, policy, require_all_exceptions=False
    )
    aggregate_xml_component_count, aggregate_xml_sha = _validate_xml_pair(
        sbom, arguments.sbom_xml, "aggregate"
    )
    published_xml_component_count, published_xml_sha = _validate_xml_pair(
        published_sbom, arguments.published_sbom_xml, "published"
    )
    example_xml_component_count, example_xml_sha = _validate_xml_pair(
        example_sbom, arguments.example_sbom_xml, "example"
    )
    lock = _load_scanner_lock(arguments.scanner_lock)
    scanner_config = _read_regular_bytes(
        arguments.scanner_config, "explicit OSV scanner configuration"
    )
    if scanner_config:
        raise PolicyError("explicit OSV scanner configuration must be exactly empty")
    if arguments.scanner_platform not in lock["scanner"]["platforms"]:
        raise PolicyError("scanner platform is not present in the pinned lock")
    scanner_asset = lock["scanner"]["platforms"][arguments.scanner_platform]
    published_components, pom_dependencies, runtime_closure = _published_inventory(
        published_sbom, arguments.published_pom, arguments.published_lock
    )
    (
        published_resolved_profile,
        example_resolved_profile,
        published_profile,
        example_profile,
    ) = _validate_resolved_profile_partition(sbom, published_sbom, example_sbom)
    _validate_root_reachable_dependency_graph(sbom, "aggregate SBOM")
    _validate_root_reachable_dependency_graph(example_sbom, "example SBOM")
    _validate_test_runtime_license_exception_scopes(
        policy, published_profile, example_profile, published_sbom, example_sbom
    )
    inventory = _osv_maven_inventory(sbom)
    expected_inventory = _inventory_content(inventory)
    actual_inventory = _read_text(arguments.inventory, "derived Maven inventory")
    if actual_inventory != expected_inventory:
        raise PolicyError("derived Maven inventory does not exactly match the verified SBOM")
    # OSV advisory prose legitimately contains escaped tabs/newlines. Those
    # fields are not copied into sanitized evidence; still reject NUL and all
    # non-whitespace control characters throughout the decoded document.
    raw_scan = _read_json(
        arguments.raw_scan, allow_escaped_whitespace=True
    )
    findings = _findings(_scanner_packages(raw_scan), inventory)
    accepted = _apply_vulnerability_policy(findings)
    evidence = {
        "revision": arguments.revision,
        "sourceTree": arguments.source_tree,
        "scanner": {
            "binarySha256": scanner_asset["sha256"],
            "binarySize": scanner_asset["size"],
            "binaryUrl": scanner_asset["url"],
            "commit": lock["scanner"]["commit"],
            "database": {
                "ecosystem": lock["database"]["ecosystem"],
                "generation": lock["database"]["generation"],
                "lastModified": lock["database"]["lastModified"],
                "sha256": lock["database"]["sha256"],
                "size": lock["database"]["size"],
                "url": lock["database"]["url"],
            },
            "name": lock["scanner"]["name"],
            "platform": arguments.scanner_platform,
            "scalibrVersion": lock["scanner"]["scalibrVersion"],
            "scannerLockSha256": _sha256(arguments.scanner_lock),
            "scannerConfigSha256": hashlib.sha256(scanner_config).hexdigest(),
            "version": lock["scanner"]["version"],
        },
        "schemaVersion": 1,
        "sbom": {
            "componentLicenseCount": license_component_count,
            "licenseReviews": [
                {
                    key: review[key]
                    for key in (
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
                    )
                }
                for review in policy["licenseReviewExceptions"]
            ],
            "unresolvedLicenseReviewCount": len(
                policy["licenseReviewExceptions"]
            ),
            "inventorySha256": hashlib.sha256(expected_inventory.encode("utf-8")).hexdigest(),
            "licensePolicy": "passed",
            "mavenPackageCount": len(inventory),
            "policySha256": hashlib.sha256(policy_content).hexdigest(),
            "sha256": _sha256(arguments.sbom),
            "xmlComponentCount": aggregate_xml_component_count,
            "xmlSha256": aggregate_xml_sha,
        },
        "publishedModule": {
            "componentLicenseCount": published_license_component_count,
            "mavenPackageCount": len(published_resolved_profile),
            "resolvedProfileSha256": _purl_set_sha256(published_resolved_profile),
            "pomDependencyCount": len(pom_dependencies),
            "runtimeClosureCount": len(runtime_closure),
            "runtimeClosureSha256": hashlib.sha256(
                ("\n".join(sorted(runtime_closure)) + "\n").encode("utf-8")
            ).hexdigest(),
            "pomSha256": _sha256(arguments.published_pom),
            "dependencyLockSha256": _sha256(arguments.published_lock),
            "sbomSha256": _sha256(arguments.published_sbom),
            "xmlComponentCount": published_xml_component_count,
            "xmlSha256": published_xml_sha,
        },
        "exampleProfile": {
            "componentLicenseCount": example_license_component_count,
            "mavenPackageCount": len(example_resolved_profile),
            "resolvedProfileSha256": _purl_set_sha256(example_resolved_profile),
            "sbomSha256": _sha256(arguments.example_sbom),
            "xmlComponentCount": example_xml_component_count,
            "xmlSha256": example_xml_sha,
        },
        "vulnerabilities": {
            "acceptedExceptionCount": len(accepted),
            "findingCount": len(findings),
            "findings": accepted,
            "unreviewedCount": 0,
        },
    }
    _write_text_atomic(
        arguments.output, json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    )
    print(
        "verified supply-chain policy: "
        f"{len(inventory)} Maven packages, {len(findings)} findings"
    )


def _preflight_command(arguments: argparse.Namespace) -> None:
    _load_policy(arguments.policy)
    _load_scanner_lock(arguments.scanner_lock)
    scanner_config = _read_regular_bytes(
        arguments.scanner_config, "explicit OSV scanner configuration"
    )
    if scanner_config:
        raise PolicyError("explicit OSV scanner configuration must be exactly empty")
    print("verified supply-chain scanner lock, policy, and empty explicit config")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser(
        "preflight", help="validate pinned scanner inputs before downloads"
    )
    preflight.add_argument("--scanner-lock", type=Path, required=True)
    preflight.add_argument("--scanner-config", type=Path, required=True)
    preflight.add_argument("--policy", type=Path, required=True)
    preflight.set_defaults(handler=_preflight_command)

    inventory = commands.add_parser("inventory", help="derive exact scanner inventory")
    inventory.add_argument("--sbom", type=Path, required=True)
    inventory.add_argument("--sbom-xml", type=Path, required=True)
    inventory.add_argument("--published-sbom", type=Path, required=True)
    inventory.add_argument("--published-sbom-xml", type=Path, required=True)
    inventory.add_argument("--example-sbom", type=Path, required=True)
    inventory.add_argument("--example-sbom-xml", type=Path, required=True)
    inventory.add_argument("--published-pom", type=Path, required=True)
    inventory.add_argument("--published-lock", type=Path, required=True)
    inventory.add_argument("--policy", type=Path, required=True)
    inventory.add_argument("--output", type=Path, required=True)
    inventory.set_defaults(handler=_inventory_command)

    verify = commands.add_parser("verify", help="verify raw scan and write sanitized evidence")
    verify.add_argument("--sbom", type=Path, required=True)
    verify.add_argument("--sbom-xml", type=Path, required=True)
    verify.add_argument("--published-sbom", type=Path, required=True)
    verify.add_argument("--published-sbom-xml", type=Path, required=True)
    verify.add_argument("--example-sbom", type=Path, required=True)
    verify.add_argument("--example-sbom-xml", type=Path, required=True)
    verify.add_argument("--published-pom", type=Path, required=True)
    verify.add_argument("--published-lock", type=Path, required=True)
    verify.add_argument("--policy", type=Path, required=True)
    verify.add_argument("--scanner-lock", type=Path, required=True)
    verify.add_argument("--scanner-config", type=Path, required=True)
    verify.add_argument("--scanner-platform", required=True)
    verify.add_argument("--inventory", type=Path, required=True)
    verify.add_argument("--raw-scan", type=Path, required=True)
    verify.add_argument("--revision", required=True)
    verify.add_argument("--source-tree", required=True)
    verify.add_argument("--output", type=Path, required=True)
    verify.set_defaults(handler=_verify_command)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        arguments.handler(arguments)
    except PolicyError as error:
        print(f"supply-chain policy failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
