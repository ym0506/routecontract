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
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Any
from urllib.parse import quote, unquote_to_bytes
import xml.etree.ElementTree as ET


HEX_40 = re.compile(r"[0-9a-f]{40}")
HEX_64 = re.compile(r"[0-9a-f]{64}")
MAVEN_PURL = re.compile(
    r"^pkg:maven/(?P<group>[^/@?]+)/(?P<name>[^/@?]+)@(?P<version>[^?]+)"
    r"(?:\?(?P<query>[^#]+))?$"
)
INVALID_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
TEST_PROPERTY = {"name": "cdx:maven:package:test", "value": "true"}
TEST_CONTAINER_PROPERTY = {"name": "routecontract:usage", "value": "test-only"}
MAVEN_NAMESPACE = "http://maven.apache.org/POM/4.0.0"
CYCLONEDX_XML_NAMESPACE = "http://cyclonedx.org/schema/bom/1.6"
FIRST_PARTY_GROUP = "io.github.ym0506.routecontract"
AGGREGATE_ROOT_NAME = "routecontract"
PUBLISHED_ROOT_NAME = "routecontract-shardingsphere-5.5"
EXAMPLE_ROOT_NAME = "mysql-example"
MAX_VULNERABILITY_EXCEPTION_DAYS = 30


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
        return _read_regular_bytes(path, label).decode("utf-8")
    except UnicodeError as error:
        raise PolicyError(f"cannot decode {label} as UTF-8: {error}") from error


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            _read_text(path, f"JSON document {path.name}"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except json.JSONDecodeError as error:
        raise PolicyError(f"cannot read JSON document {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise PolicyError(f"JSON document {path.name} must be an object")
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


def _iso_date(value: Any, label: str) -> date:
    text = _nonempty_string(value, label)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise PolicyError(f"{label} must use YYYY-MM-DD") from error
    if parsed.isoformat() != text:
        raise PolicyError(f"{label} must use canonical YYYY-MM-DD")
    return parsed


def _strict_percent_decode(value: str, label: str) -> str:
    if INVALID_PERCENT.search(value):
        raise PolicyError(f"{label} contains malformed percent encoding")
    try:
        return unquote_to_bytes(value).decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise PolicyError(f"{label} contains invalid UTF-8 percent encoding") from error


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
        raise PolicyError(f"Maven purl is not canonically percent-encoded: {purl}")
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


def _load_policy(path: Path) -> dict[str, Any]:
    policy = _read_json(path)
    _exact_keys(
        policy,
        {
            "schemaVersion",
            "allowedLicenseIds",
            "licenseExceptions",
            "vulnerabilityExceptions",
        },
        "policy",
    )
    if policy["schemaVersion"] != 1:
        raise PolicyError("unsupported policy schemaVersion")
    allowed = policy["allowedLicenseIds"]
    if (
        not isinstance(allowed, list)
        or not allowed
        or any(not isinstance(item, str) or not item for item in allowed)
        or allowed != sorted(set(allowed))
    ):
        raise PolicyError("allowedLicenseIds must be a sorted unique non-empty array")

    license_exceptions = policy["licenseExceptions"]
    if not isinstance(license_exceptions, list):
        raise PolicyError("licenseExceptions must be an array")
    license_keys: set[tuple[str, str]] = set()
    for index, exception in enumerate(license_exceptions):
        if not isinstance(exception, dict):
            raise PolicyError(f"licenseExceptions[{index}] must be an object")
        _exact_keys(exception, {"license", "purl", "scope"}, f"licenseExceptions[{index}]")
        license_value = _nonempty_string(exception["license"], "license exception value")
        purl = _nonempty_string(exception["purl"], "license exception purl")
        scope = _nonempty_string(exception["scope"], "license exception scope")
        if scope not in {"test-container", "test-runtime"}:
            raise PolicyError(
                "license exception scope must be test-runtime or test-container"
            )
        if scope == "test-runtime":
            canonical, _, _, _ = _canonical_maven_purl(purl)
            if purl != canonical:
                raise PolicyError(
                    "test-runtime license exception purl must be canonical Maven"
                )
        elif not purl.startswith("pkg:oci/"):
            raise PolicyError("test-container license exception purl must be OCI")
        if (purl, license_value) in license_keys:
            raise PolicyError("duplicate license exception")
        license_keys.add((purl, license_value))

    vulnerability_exceptions = policy["vulnerabilityExceptions"]
    if not isinstance(vulnerability_exceptions, list):
        raise PolicyError("vulnerabilityExceptions must be an array")
    vulnerability_keys: set[tuple[str, str]] = set()
    exception_ids: set[str] = set()
    expected_keys = {
        "advisory",
        "exceptionId",
        "expires",
        "fixedVersion",
        "owner",
        "purl",
        "rationaleCode",
        "reviewedAt",
        "scope",
        "severity",
    }
    for index, exception in enumerate(vulnerability_exceptions):
        if not isinstance(exception, dict):
            raise PolicyError(f"vulnerabilityExceptions[{index}] must be an object")
        _exact_keys(exception, expected_keys, f"vulnerabilityExceptions[{index}]")
        advisory = _nonempty_string(exception["advisory"], "advisory")
        exception_id = _nonempty_string(exception["exceptionId"], "exceptionId")
        purl = _nonempty_string(exception["purl"], "vulnerability purl")
        canonical, _, _, _ = _canonical_maven_purl(purl)
        if purl != canonical:
            raise PolicyError("vulnerability exception purl must not contain qualifiers")
        expires = _iso_date(exception["expires"], "expires")
        reviewed_at = _iso_date(exception["reviewedAt"], "reviewedAt")
        today = datetime.now(timezone.utc).date()
        if reviewed_at > today:
            raise PolicyError("reviewedAt must not be in the future")
        if reviewed_at > expires:
            raise PolicyError("reviewedAt must not be later than expires")
        if (expires - reviewed_at).days > MAX_VULNERABILITY_EXCEPTION_DAYS:
            raise PolicyError(
                "vulnerability exception validity must not exceed 30 days"
            )
        _nonempty_string(exception["owner"], "owner")
        _nonempty_string(exception["rationaleCode"], "rationaleCode")
        if exception["scope"] != "aggregate-test-only":
            raise PolicyError("vulnerability exception scope must be aggregate-test-only")
        severity = _nonempty_string(exception["severity"], "severity")
        if severity != severity.upper():
            raise PolicyError("severity must be uppercase")
        fixed_version = exception["fixedVersion"]
        if fixed_version is not None:
            _nonempty_string(fixed_version, "fixedVersion")
        key = (purl, advisory)
        if key in vulnerability_keys or exception_id in exception_ids:
            raise PolicyError("duplicate vulnerability exception or exceptionId")
        vulnerability_keys.add(key)
        exception_ids.add(exception_id)
    return policy


def _load_sbom(path: Path) -> dict[str, Any]:
    sbom = _read_json(path)
    if sbom.get("bomFormat") != "CycloneDX" or sbom.get("specVersion") != "1.6":
        raise PolicyError("SBOM must be CycloneDX 1.6")
    metadata = sbom.get("metadata")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("component"), dict):
        raise PolicyError("SBOM metadata.component is missing")
    components = sbom.get("components")
    if not isinstance(components, list) or any(not isinstance(item, dict) for item in components):
        raise PolicyError("SBOM components must be an array of objects")
    return sbom


def _validate_xml_pair(
    sbom: dict[str, Any], xml_path: Path, label: str
) -> tuple[int, str]:
    content = _read_regular_bytes(xml_path, f"{label} XML SBOM")
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise PolicyError(f"{label} XML SBOM must not contain a DTD or entity")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise PolicyError(f"cannot parse {label} XML SBOM: {error}") from error
    qname = lambda name: f"{{{CYCLONEDX_XML_NAMESPACE}}}{name}"
    json_version = sbom.get("version")
    if type(json_version) is not int or json_version != 1:
        raise PolicyError(f"{label} JSON SBOM version must be the integer 1")
    if root.tag != qname("bom") or root.get("version") != str(json_version):
        raise PolicyError(f"{label} XML SBOM must be CycloneDX 1.6 version 1")
    serial = _nonempty_string(sbom.get("serialNumber"), f"{label} JSON serialNumber")
    if root.get("serialNumber") != serial:
        raise PolicyError(f"{label} JSON/XML serial numbers differ")

    def xml_text(parent: ET.Element, name: str, required: bool = False) -> str | None:
        values = parent.findall(qname(name))
        if len(values) > 1 or (required and len(values) != 1):
            raise PolicyError(f"{label} XML component has ambiguous {name}")
        if not values:
            return None
        if values[0].text is None:
            raise PolicyError(f"{label} XML component has empty {name}")
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
            "group": component.get("group"),
            "hashes": hash_records,
            "licenses": sorted(_component_license_values(component, component_label)),
            "name": component.get("name"),
            "properties": sorted(
                (item["name"], item["value"])
                for item in _component_properties(component, component_label)
            ),
            "scope": component.get("scope"),
            "type": component.get("type"),
            "version": component.get("version"),
        }

    def xml_record(component: ET.Element, component_label: str) -> tuple[str, dict[str, Any]]:
        purl = xml_text(component, "purl", required=True)
        if component.get("bom-ref") != purl:
            raise PolicyError(f"{component_label} bom-ref must exactly equal purl")
        license_parent = component.findall(qname("licenses"))
        if len(license_parent) != 1:
            raise PolicyError(f"{component_label} must contain one licenses element")
        licenses: list[str] = []
        for child in list(license_parent[0]):
            if child.tag == qname("expression"):
                if child.text is None:
                    raise PolicyError(f"{component_label} has an empty license expression")
                licenses.append(_nonempty_string(child.text, "XML license expression"))
            elif child.tag == qname("license"):
                ids = child.findall(qname("id"))
                if len(ids) != 1 or ids[0].text is None:
                    raise PolicyError(f"{component_label} has an ambiguous license")
                licenses.append(_nonempty_string(ids[0].text, "XML license id"))
            else:
                raise PolicyError(f"{component_label} has an unsupported license choice")
        if not licenses or len(licenses) != len(set(licenses)):
            raise PolicyError(f"{component_label} has missing or duplicate licenses")
        hash_parents = component.findall(qname("hashes"))
        if len(hash_parents) > 1:
            raise PolicyError(f"{component_label} repeats hashes")
        hashes: list[tuple[str, str]] = []
        if hash_parents:
            for item in list(hash_parents[0]):
                if item.tag != qname("hash"):
                    raise PolicyError(f"{component_label} has an unsupported hash element")
                hashes.append(
                    (
                        _nonempty_string(item.get("alg"), "XML hash algorithm"),
                        _nonempty_string(item.text, "XML hash content"),
                    )
                )
        if len(hashes) != len(set(hashes)):
            raise PolicyError(f"{component_label} has duplicate hashes")
        property_parents = component.findall(qname("properties"))
        if len(property_parents) > 1:
            raise PolicyError(f"{component_label} repeats properties")
        properties: list[tuple[str, str]] = []
        if property_parents:
            for item in property_parents[0].findall(qname("property")):
                name = _nonempty_string(item.get("name"), "XML property name")
                value = _nonempty_string(item.text, "XML property value")
                properties.append((name, value))
        if len(properties) != len({name for name, _ in properties}):
            raise PolicyError(f"{component_label} repeats a property name")
        return purl, {
            "group": xml_text(component, "group"),
            "hashes": sorted(hashes),
            "licenses": sorted(licenses),
            "name": xml_text(component, "name", required=True),
            "properties": sorted(properties),
            "scope": xml_text(component, "scope"),
            "type": component.get("type"),
            "version": xml_text(component, "version", required=True),
        }

    metadata = root.findall(qname("metadata"))
    if len(metadata) != 1:
        raise PolicyError(f"{label} XML SBOM must contain one metadata element")
    xml_root_components = metadata[0].findall(qname("component"))
    if len(xml_root_components) != 1:
        raise PolicyError(f"{label} XML SBOM must contain one metadata component")
    component_parents = root.findall(qname("components"))
    if len(component_parents) != 1:
        raise PolicyError(f"{label} XML SBOM must contain one components element")
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
    for index, component in enumerate(
        component_parents[0].findall(qname("component"))
    ):
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
    for dependency in dependency_parents[0].findall(qname("dependency")):
        ref = _nonempty_string(dependency.get("ref"), "XML dependency ref")
        targets = [
            _nonempty_string(child.get("ref"), "XML dependency target")
            for child in dependency.findall(qname("dependency"))
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


def _component_license_values(component: dict[str, Any], label: str) -> list[str]:
    licenses = component.get("licenses")
    if not isinstance(licenses, list) or not licenses:
        raise PolicyError(f"{label} has no license metadata")
    values: list[str] = []
    for index, choice in enumerate(licenses):
        if not isinstance(choice, dict) or len(choice) != 1:
            raise PolicyError(f"{label} license choice {index} is ambiguous")
        if "expression" in choice:
            values.append(_nonempty_string(choice["expression"], f"{label} license expression"))
            continue
        license_value = choice.get("license")
        if not isinstance(license_value, dict):
            raise PolicyError(f"{label} license choice {index} is invalid")
        license_id = _nonempty_string(license_value.get("id"), f"{label} license id")
        unknown = set(license_value) - {"id", "url"}
        if unknown:
            raise PolicyError(f"{label} license contains unsupported fields: {sorted(unknown)}")
        if "url" in license_value:
            _nonempty_string(license_value["url"], f"{label} license url")
        values.append(license_id)
    if len(values) != len(set(values)):
        raise PolicyError(f"{label} repeats a license choice")
    return values


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
        tuple(sorted(_component_license_values(component, label))),
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
        (entry["purl"], entry["license"]): entry
        for entry in policy["licenseExceptions"]
    }
    used_exceptions: set[tuple[str, str]] = set()
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
        values = _component_license_values(component, label)
        if all(value in allowed for value in values):
            continue
        reviewed_choice = " OR ".join(values)
        matches = (
            [(policy_purl, reviewed_choice)]
            if (policy_purl, reviewed_choice) in exceptions
            else []
        )
        if len(matches) != 1:
            raise PolicyError(f"unapproved license for {purl}: {values}")
        exception = exceptions[matches[0]]
        _prove_component_scope(
            component,
            exception["scope"],
            f"license exception component {policy_purl}",
        )
        used_exceptions.add(matches[0])
    unused = set(exceptions) - used_exceptions
    if require_all_exceptions and unused:
        raise PolicyError(f"unused license exceptions: {sorted(unused)}")
    return len(candidates)


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
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise PolicyError("generated published POM must not contain a DTD or entity")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise PolicyError(f"cannot parse generated published POM: {error}") from error
    namespace = {"m": MAVEN_NAMESPACE}
    if root.tag != f"{{{MAVEN_NAMESPACE}}}project":
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

    def required_text(parent: ET.Element, name: str, label: str) -> str:
        values = parent.findall(f"m:{name}", namespace)
        if len(values) != 1 or values[0].text is None:
            raise PolicyError(f"generated published POM must contain one {label}")
        text = _nonempty_string(values[0].text.strip(), label)
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
            or packaging_nodes[0].text is None
            or packaging_nodes[0].text.strip() != "jar"
        ):
            raise PolicyError("generated published POM packaging must be jar when present")
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
    for dependency in root.findall("m:dependencies/m:dependency", namespace):
        allowed_children = {
            f"{{{MAVEN_NAMESPACE}}}groupId",
            f"{{{MAVEN_NAMESPACE}}}artifactId",
            f"{{{MAVEN_NAMESPACE}}}version",
            f"{{{MAVEN_NAMESPACE}}}scope",
        }
        unexpected = [child.tag for child in dependency if child.tag not in allowed_children]
        if unexpected:
            raise PolicyError(
                f"generated published POM dependency has unsupported fields: {unexpected}"
            )
        group = required_text(dependency, "groupId", "dependency groupId")
        name = required_text(dependency, "artifactId", "dependency artifactId")
        version = required_text(dependency, "version", "dependency version")
        scope_nodes = dependency.findall("m:scope", namespace)
        scope = "compile"
        if scope_nodes:
            if len(scope_nodes) != 1 or scope_nodes[0].text is None:
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
        if ref in graph or len(targets) != len(set(targets)):
            raise PolicyError(f"{label} dependency graph repeats a node or edge")
        if any(not isinstance(target, str) or target not in nodes for target in targets):
            raise PolicyError(f"{label} dependency graph has a dangling edge")
        graph[ref] = set(targets)
    if root_ref not in graph:
        raise PolicyError(f"{label} dependency graph is missing its root record")
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
        if ref in graph or len(targets) != len(set(targets)):
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
    for exception in policy["licenseExceptions"]:
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
                    f"published-module license cannot use a test-container exception: {purl}"
                )
            if purl not in example_all:
                raise PolicyError(
                    f"test-container license exception is absent from example profile: {purl}"
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
    inventory: dict[str, dict[str, Any]],
    published_inventory: set[str],
    example_inventory: set[str],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    exceptions = {
        (entry["purl"], entry["advisory"]): entry
        for entry in policy["vulnerabilityExceptions"]
    }
    used: set[tuple[str, str]] = set()
    accepted: list[dict[str, Any]] = []
    today = datetime.now(timezone.utc).date()
    for finding in findings:
        key = (finding["purl"], finding["advisory"])
        if finding["purl"] in published_inventory:
            raise PolicyError(
                "published-module vulnerability cannot use a test-only exception: "
                f"{finding['purl']} {finding['advisory']}"
            )
        if finding["purl"] not in example_inventory:
            raise PolicyError(
                "test-only vulnerability is absent from the example profile: "
                f"{finding['purl']} {finding['advisory']}"
            )
        exception = exceptions.get(key)
        if exception is None:
            raise PolicyError(
                f"unreviewed vulnerability: {finding['purl']} {finding['advisory']}"
            )
        expiry = _iso_date(exception["expires"], "expires")
        if expiry < today:
            raise PolicyError(f"expired vulnerability exception: {exception['exceptionId']}")
        component = inventory[finding["purl"]]
        _prove_component_scope(
            component,
            exception["scope"],
            f"vulnerability exception component {finding['purl']}",
        )
        for field in ("severity", "fixedVersion"):
            if finding[field] != exception[field]:
                raise PolicyError(
                    f"vulnerability exception {field} differs for {exception['exceptionId']}"
                )
        used.add(key)
        accepted.append(
            {
                "advisory": finding["advisory"],
                "action": "time-bounded reviewed exception; re-evaluate by expiry",
                "exceptionExpires": exception["expires"],
                "exceptionId": exception["exceptionId"],
                "fixedVersion": finding["fixedVersion"],
                "owner": exception["owner"],
                "purl": finding["purl"],
                "rationaleCode": exception["rationaleCode"],
                "reachabilityEvidence": {
                    "exampleProfile": True,
                    "publishedProfile": False,
                    "publishedRuntime": False,
                },
                "reviewedAt": exception["reviewedAt"],
                "scope": exception["scope"],
                "severity": finding["severity"],
            }
        )
    unused = set(exceptions) - used
    if unused:
        raise PolicyError(f"unused vulnerability exceptions: {sorted(unused)}")
    return accepted


def _inventory_command(arguments: argparse.Namespace) -> None:
    sbom = _load_sbom(arguments.sbom)
    published_sbom = _load_sbom(arguments.published_sbom)
    example_sbom = _load_sbom(arguments.example_sbom)
    policy = _load_policy(arguments.policy)
    _validate_sbom_roles(sbom, published_sbom, example_sbom)
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
    policy = _load_policy(arguments.policy)
    _validate_sbom_roles(sbom, published_sbom, example_sbom)
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
    raw_scan = _read_json(arguments.raw_scan)
    findings = _findings(_scanner_packages(raw_scan), inventory)
    accepted = _apply_vulnerability_policy(
        findings, inventory, published_profile, example_profile, policy
    )
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
            "inventorySha256": hashlib.sha256(expected_inventory.encode("utf-8")).hexdigest(),
            "licensePolicy": "passed",
            "mavenPackageCount": len(inventory),
            "policySha256": _sha256(arguments.policy),
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
        f"{len(inventory)} Maven packages, {len(findings)} reviewed findings"
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
