#!/usr/bin/env python3
"""Finalize and verify RouteContract CycloneDX JSON/XML release metadata.

CycloneDX Gradle plugin 3.4.0's ``licenseChoice`` task property writes the BOM
document license at ``metadata.licenses``. It does not populate the distinct
``licenses`` field on ``metadata.component``. This script keeps the plugin
output as its source of dependency truth, copies it to a verified output, and
adds first-party licenses plus reviewed license metadata for the exact
test-only artifacts and pinned MySQL fixture that the dependency-only plugin
output cannot fully represent.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import quote, unquote, unquote_to_bytes
import xml.etree.ElementTree as ET


FIRST_PARTY_GROUP = ""
LICENSE_ID = "Apache-2.0"
LICENSE_URL = "https://www.apache.org/licenses/LICENSE-2.0.txt"
CYCLONEDX_XML_NAMESPACE = "http://cyclonedx.org/schema/bom/1.6"
MYSQL_CONNECTOR_GROUP = "com.mysql"
MYSQL_CONNECTOR_NAME = "mysql-connector-j"
MYSQL_CONNECTOR_VERSION = "26.7.0"
MYSQL_CONNECTOR_LICENSE_EXPRESSION = (
    "GPL-2.0-only WITH Universal-FOSS-exception-1.0"
)
REVIEWED_MAVEN_LICENSE_EXPRESSIONS = {
    ("jakarta.transaction", "jakarta.transaction-api", "1.3.3"):
        "EPL-2.0 OR (GPL-2.0-only WITH Classpath-exception-2.0)",
    ("net.java.dev.jna", "jna", "5.13.0"):
        "(Apache-2.0 OR LGPL-2.1-or-later) AND MIT",
    ("org.locationtech.jts", "jts-core", "1.19.0"):
        "EPL-2.0 OR BSD-3-Clause",
}
LICENSE_OVERRIDE_MAVEN_COORDINATES = (
    *REVIEWED_MAVEN_LICENSE_EXPRESSIONS.keys(),
    (MYSQL_CONNECTOR_GROUP, MYSQL_CONNECTOR_NAME, MYSQL_CONNECTOR_VERSION),
)
MYSQL_EXAMPLE_NAME = "mysql-example"
MYSQL_552_EXAMPLE_NAME = "mysql-5.5.2-example"
MYSQL_EXAMPLE_NAMES = frozenset({MYSQL_EXAMPLE_NAME, MYSQL_552_EXAMPLE_NAME})
MYSQL_CONTAINER_NAME = "mysql"
MYSQL_CONTAINER_VERSION = "8.4.11"
MYSQL_CONTAINER_DIGEST = (
    "b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb"
)
MYSQL_CONTAINER_PURL = (
    "pkg:oci/mysql@sha256%3A"
    f"{MYSQL_CONTAINER_DIGEST}?repository_url=registry-1.docker.io&tag=8.4.11"
)
MYSQL_CONTAINER_REVIEW_PROPERTY = "routecontract:license-review"
MYSQL_CONTAINER_REVIEW_VALUE = "manual-review-required"
FORBIDDEN_JTS_IO_GROUP = "org.locationtech.jts.io"
FORBIDDEN_JTS_IO_NAME = "jts-io-common"
FORBIDDEN_JTS_IO_PURL_PREFIX = (
    "pkg:maven/org.locationtech.jts.io/jts-io-common@"
)
REQUIRED_EXAMPLE_MAVEN_COORDINATES = {
    MYSQL_EXAMPLE_NAME: (
        ("org.apache.shardingsphere", "shardingsphere-jdbc", "5.5.3"),
        ("org.apache.calcite", "calcite-core", "1.42.0"),
        ("org.apache.calcite", "calcite-linq4j", "1.42.0"),
    ),
    MYSQL_552_EXAMPLE_NAME: (
        ("org.apache.shardingsphere", "shardingsphere-jdbc", "5.5.2"),
        ("org.apache.calcite", "calcite-core", "1.38.0"),
        ("org.apache.calcite", "calcite-linq4j", "1.38.0"),
    ),
}
MYSQL_CONTAINER_DOCUMENTATION_URL = (
    "https://dev.mysql.com/doc/refman/8.4/en/preface.html"
)
MYSQL_CONTAINER_USAGE_PROPERTY = "routecontract:usage"
MYSQL_CONTAINER_USAGE_VALUE = "test-only"
DOCUMENT_LICENSE = [{"license": {"id": LICENSE_ID, "url": LICENSE_URL}}]
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
# This is the exact Maven PURL byte profile emitted by the pinned CycloneDX
# Gradle producer, not a general-purpose PURL parser. In particular, it accepts
# the producer's percent-encoded ``project_path`` colon and rejects subpaths.
CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f]")
MAVEN_PURL = re.compile(
    r"^pkg:maven/(?P<group>[^/@?]+)/(?P<name>[^/@?]+)@(?P<version>[^?]+)"
    r"(?:\?(?P<query>[^#]+))?$"
)
MAVEN_PURL_EQUIVALENT_PREFIX = re.compile(r"^pkg:/*maven/", re.IGNORECASE)
PURL_QUALIFIER_KEY = re.compile(r"^[a-z][a-z0-9._-]*$")
INVALID_PERCENT_ENCODING = re.compile(r"%(?![0-9A-Fa-f]{2})")
RFC3339_UTC = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?Z"
)
XML_DECLARATION = re.compile(
    r"^<\?xml\s+version=(['\"])1\.0\1\s+encoding=(['\"])utf-8\2\s*\?>",
    re.IGNORECASE,
)
AGGREGATE_ROOT_NAME = "routecontract"
CORE_ROOT_NAME = "routecontract-core"
PUBLISHED_ROOT_NAME = "routecontract-shardingsphere-5.5"
ADAPTER_552_ROOT_NAME = "routecontract-shardingsphere-5.5.2"
EXPECTED_FIRST_PARTY_CHILDREN = {
    AGGREGATE_ROOT_NAME: {
        CORE_ROOT_NAME,
        PUBLISHED_ROOT_NAME,
        ADAPTER_552_ROOT_NAME,
        MYSQL_EXAMPLE_NAME,
        MYSQL_552_EXAMPLE_NAME,
    },
    CORE_ROOT_NAME: set(),
    PUBLISHED_ROOT_NAME: {CORE_ROOT_NAME},
    ADAPTER_552_ROOT_NAME: {CORE_ROOT_NAME},
    MYSQL_EXAMPLE_NAME: {CORE_ROOT_NAME, PUBLISHED_ROOT_NAME},
    MYSQL_552_EXAMPLE_NAME: {CORE_ROOT_NAME, ADAPTER_552_ROOT_NAME},
}
# Exact first-party edges emitted by the pinned direct-BOM producer. The MySQL
# example owns the adapter directly and reaches core transitively through it.
# The aggregate producer also preserves the included projects' transitive
# first-party ownership edges.
EXPECTED_FIRST_PARTY_DEPENDENCIES = {
    AGGREGATE_ROOT_NAME: {
        AGGREGATE_ROOT_NAME: {
            CORE_ROOT_NAME,
            PUBLISHED_ROOT_NAME,
            ADAPTER_552_ROOT_NAME,
            MYSQL_EXAMPLE_NAME,
            MYSQL_552_EXAMPLE_NAME,
        },
        CORE_ROOT_NAME: set(),
        PUBLISHED_ROOT_NAME: {CORE_ROOT_NAME},
        ADAPTER_552_ROOT_NAME: {CORE_ROOT_NAME},
        MYSQL_EXAMPLE_NAME: {PUBLISHED_ROOT_NAME},
        MYSQL_552_EXAMPLE_NAME: {ADAPTER_552_ROOT_NAME},
    },
    CORE_ROOT_NAME: {CORE_ROOT_NAME: set()},
    PUBLISHED_ROOT_NAME: {
        PUBLISHED_ROOT_NAME: {CORE_ROOT_NAME},
        CORE_ROOT_NAME: set(),
    },
    ADAPTER_552_ROOT_NAME: {
        ADAPTER_552_ROOT_NAME: {CORE_ROOT_NAME},
        CORE_ROOT_NAME: set(),
    },
    MYSQL_EXAMPLE_NAME: {
        MYSQL_EXAMPLE_NAME: {PUBLISHED_ROOT_NAME},
        PUBLISHED_ROOT_NAME: {CORE_ROOT_NAME},
        CORE_ROOT_NAME: set(),
    },
    MYSQL_552_EXAMPLE_NAME: {
        MYSQL_552_EXAMPLE_NAME: {ADAPTER_552_ROOT_NAME},
        ADAPTER_552_ROOT_NAME: {CORE_ROOT_NAME},
        CORE_ROOT_NAME: set(),
    },
}


LicenseRecord = tuple[str, str, str]


class SbomError(ValueError):
    """Raised when an SBOM cannot be finalized without ambiguity."""


def _reject_control_characters(value: object, label: str) -> None:
    if isinstance(value, str):
        if CONTROL_CHARACTER.search(value):
            raise SbomError(f"{label} contains a control character")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _reject_control_characters(child, f"{label}[{index}]")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_control_characters(key, f"{label} key")
            _reject_control_characters(child, f"{label}.{key}")


def _validate_timestamp(value: object, label: str) -> str:
    if not isinstance(value, str) or RFC3339_UTC.fullmatch(value) is None:
        raise SbomError(f"{label} must be an RFC 3339 UTC timestamp")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise SbomError(f"{label} must be an RFC 3339 UTC timestamp") from error
    return value


def _strict_percent_decode(value: str, label: str) -> str:
    if INVALID_PERCENT_ENCODING.search(value):
        raise SbomError(f"{label} contains malformed percent encoding")
    try:
        return unquote_to_bytes(value).decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise SbomError(f"{label} contains invalid UTF-8 percent encoding") from error


def _parse_supported_maven_purl(
    purl: str, label: str
) -> tuple[str, str, str, dict[str, str]]:
    match = MAVEN_PURL.fullmatch(purl)
    if match is None:
        raise SbomError(f"{label} has an invalid Maven purl")
    group = _strict_percent_decode(match.group("group"), f"{label} Maven group")
    name = _strict_percent_decode(match.group("name"), f"{label} Maven name")
    version = _strict_percent_decode(match.group("version"), f"{label} Maven version")
    for field, value in (("group", group), ("name", name), ("version", version)):
        if (
            not value
            or CONTROL_CHARACTER.search(value)
            or any(token in value for token in (":", "=", "/"))
        ):
            raise SbomError(f"{label} has an unsafe Maven {field}")

    qualifiers: dict[str, str] = {}
    query = match.group("query")
    if query is not None:
        for field in query.split("&"):
            if field.count("=") != 1:
                raise SbomError(f"{label} has an invalid Maven purl qualifier")
            raw_name, raw_value = field.split("=", 1)
            if PURL_QUALIFIER_KEY.fullmatch(raw_name) is None:
                raise SbomError(f"{label} has an invalid Maven purl qualifier key")
            qualifier_name = raw_name
            qualifier_value = _strict_percent_decode(
                raw_value, f"{label} Maven qualifier value"
            )
            if (
                not qualifier_name
                or not qualifier_value
                or CONTROL_CHARACTER.search(qualifier_name)
                or CONTROL_CHARACTER.search(qualifier_value)
                or qualifier_name in qualifiers
            ):
                raise SbomError(f"{label} has an invalid or duplicate Maven qualifier")
            qualifiers[qualifier_name] = qualifier_value

    canonical = (
        "pkg:maven/"
        f"{quote(group, safe='.-_~')}/{quote(name, safe='.-_~')}"
        f"@{quote(version, safe='.-_~')}"
    )
    canonical_query = "&".join(
        f"{quote(key, safe='.-_~')}={quote(qualifiers[key], safe='.-_~')}"
        for key in sorted(qualifiers)
    )
    expected = canonical + (f"?{canonical_query}" if canonical_query else "")
    if purl != expected:
        raise SbomError(
            f"{label} Maven purl differs from the pinned producer profile"
        )
    return group, name, version, qualifiers


def _validate_supported_maven_component_identity(
    group: object, name: object, version: object, purl: str, label: str
) -> None:
    if MAVEN_PURL_EQUIVALENT_PREFIX.match(purl) is None:
        return
    parsed_group, parsed_name, parsed_version, _ = _parse_supported_maven_purl(
        purl, label
    )
    if (group, name, version) != (parsed_group, parsed_name, parsed_version):
        raise SbomError(f"{label} Maven purl does not match group/name/version")


def _read_canonical_utf8(path: Path, label: str) -> str:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise SbomError(f"Cannot read {label} {path}: {error}") from error
    if content.startswith(b"\xef\xbb\xbf"):
        raise SbomError(f"{label} must not contain a UTF-8 BOM: {path}")
    try:
        decoded = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise SbomError(f"{label} must be UTF-8: {path}: {error}") from error
    if "\x00" in decoded:
        raise SbomError(f"{label} must not contain NUL: {path}")
    return decoded


def _parse_canonical_xml(path: Path, label: str) -> ET.ElementTree:
    decoded = _read_canonical_utf8(path, label)
    declaration = XML_DECLARATION.match(decoded)
    if declaration is None:
        raise SbomError(f"{label} must declare XML 1.0 with UTF-8 encoding: {path}")
    body = decoded[declaration.end():]
    uppercase = body.upper()
    if "<!DOCTYPE" in uppercase or "<!ENTITY" in uppercase:
        raise SbomError(f"{label} must not contain a DTD or entity: {path}")
    if "<!--" in body or "<?" in body:
        raise SbomError(f"{label} must not contain comments or processing instructions: {path}")
    try:
        parser = ET.XMLParser(
            target=ET.TreeBuilder(insert_comments=True, insert_pis=True)
        )
        root = ET.fromstring(decoded, parser=parser)
    except ET.ParseError as error:
        raise SbomError(f"Cannot read {label} {path}: {error}") from error
    if any(not isinstance(element.tag, str) for element in root.iter()):
        raise SbomError(f"{label} must not contain comments or processing instructions: {path}")
    return ET.ElementTree(root)


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SbomError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _json_identity(component: dict[str, object]) -> tuple[object, object, object]:
    return component.get("group"), component.get("name"), component.get("version")


def _json_has_exact_document_license(document: dict[str, object]) -> bool:
    metadata = document.get("metadata")
    return isinstance(metadata, dict) and metadata.get("licenses") == DOCUMENT_LICENSE


def _validate_json_document_profile(document: dict[str, object]) -> None:
    if set(document) != DOCUMENT_FIELDS:
        raise SbomError(
            "JSON document fields differ from the supported CycloneDX profile: "
            f"{sorted(set(document) - DOCUMENT_FIELDS)}"
        )
    if (
        document.get("bomFormat") != "CycloneDX"
        or document.get("specVersion") != "1.6"
        or type(document.get("version")) is not int
        or document.get("version") != 1
        or not isinstance(document.get("serialNumber"), str)
        or not document["serialNumber"]
    ):
        raise SbomError("JSON document identity differs from CycloneDX 1.6 version 1")
    metadata = document.get("metadata")
    if (
        not isinstance(metadata, dict)
        or set(metadata) != METADATA_FIELDS
        or not isinstance(metadata.get("component"), dict)
        or metadata.get("licenses") != DOCUMENT_LICENSE
    ):
        raise SbomError("JSON metadata differs from the supported CycloneDX profile")
    _validate_timestamp(metadata["timestamp"], "JSON metadata timestamp")
    if metadata["tools"] != {
        "components": [EXPECTED_TOOL_COMPONENT]
    }:
        raise SbomError("JSON metadata tools differ from the pinned CycloneDX producer")
    components = document.get("components")
    if not isinstance(components, list) or any(
        not isinstance(component, dict) for component in components
    ):
        raise SbomError("JSON components must be an array of objects")
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, list):
        raise SbomError("JSON dependencies must be an array")
    seen_refs: set[str] = set()
    for index, record in enumerate(dependencies):
        if not isinstance(record, dict) or set(record) != {"ref", "dependsOn"}:
            raise SbomError(f"JSON dependency record {index} is invalid")
        ref = record["ref"]
        targets = record["dependsOn"]
        if (
            not isinstance(ref, str)
            or not ref
            or ref in seen_refs
            or not isinstance(targets, list)
            or any(not isinstance(target, str) or not target for target in targets)
            or len(targets) != len(set(targets))
        ):
            raise SbomError(f"JSON dependency record {index} is ambiguous")
        seen_refs.add(ref)


def _json_first_party_components(document: dict[str, object]) -> list[dict[str, object]]:
    metadata = document.get("metadata")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("component"), dict):
        raise SbomError("JSON metadata.component is missing")
    candidates: list[dict[str, object]] = [metadata["component"]]
    components = document.get("components", [])
    if not isinstance(components, list):
        raise SbomError("JSON components must be an array")
    candidates.extend(component for component in components if isinstance(component, dict))
    return [component for component in candidates if component.get("group") == FIRST_PARTY_GROUP]


def _json_components(document: dict[str, object]) -> list[dict[str, object]]:
    metadata = document.get("metadata")
    metadata_component = (
        metadata.get("component") if isinstance(metadata, dict) else None
    )
    if not isinstance(metadata_component, dict):
        raise SbomError("JSON metadata.component is missing")
    components = document.get("components", [])
    if not isinstance(components, list) or any(not isinstance(component, dict) for component in components):
        raise SbomError("JSON components must contain only objects")
    for index, component in enumerate([metadata_component, *components]):
        unsupported = set(component) - SUPPORTED_COMPONENT_FIELDS
        if unsupported:
            raise SbomError(
                "JSON component contains unsupported CycloneDX fields: "
                f"{sorted(unsupported)}"
            )
        if "components" in component:
            raise SbomError("Nested JSON components are not supported")
        for field in ("type", "bom-ref", "name", "version", "purl"):
            if not isinstance(component.get(field), str) or not component[field]:
                raise SbomError(f"JSON component {index} has an invalid {field}")
        if component["bom-ref"] != component["purl"]:
            raise SbomError(f"JSON component {index} bom-ref must equal purl")
        for field in ("publisher", "group", "description", "scope"):
            if field in component and (
                not isinstance(component[field], str) or not component[field]
            ):
                raise SbomError(f"JSON component {index} has an invalid {field}")
        if "modified" in component and type(component["modified"]) is not bool:
            raise SbomError(f"JSON component {index} modified must be a boolean")
        hashes = component.get("hashes", [])
        if not isinstance(hashes, list) or any(
            not isinstance(item, dict)
            or set(item) != {"alg", "content"}
            or any(not isinstance(item[key], str) or not item[key] for key in item)
            for item in hashes
        ):
            raise SbomError(f"JSON component {index} has invalid hashes")
        references = component.get("externalReferences", [])
        if not isinstance(references, list) or any(
            not isinstance(item, dict)
            or set(item) != {"type", "url"}
            or any(not isinstance(item[key], str) or not item[key] for key in item)
            for item in references
        ):
            raise SbomError(f"JSON component {index} has invalid externalReferences")
        properties = component.get("properties", [])
        if not isinstance(properties, list) or any(
            not isinstance(item, dict)
            or set(item) != {"name", "value"}
            or any(not isinstance(item[key], str) or not item[key] for key in item)
            for item in properties
        ):
            raise SbomError(f"JSON component {index} has invalid properties")
        if len(properties) != len({item["name"] for item in properties}):
            raise SbomError(f"JSON component {index} repeats a property name")
    return components


def _json_component_license_records(
    component: dict[str, object], label: str
) -> tuple[LicenseRecord, ...]:
    if "licenses" not in component:
        return ()
    choices = component["licenses"]
    if not isinstance(choices, list) or not choices:
        raise SbomError(f"{label} has an empty or invalid licenses value")
    if any(isinstance(choice, dict) and "expression" in choice for choice in choices):
        if len(choices) != 1 or set(choices[0]) != {"expression"}:
            raise SbomError(
                f"{label} licenseChoice must be one expression or license objects"
            )
    records: list[LicenseRecord] = []
    for choice in choices:
        if not isinstance(choice, dict) or len(choice) != 1:
            raise SbomError(f"{label} contains an ambiguous license choice")
        if "expression" in choice:
            expression = choice["expression"]
            if not isinstance(expression, str) or not expression.strip():
                raise SbomError(f"{label} contains an empty license expression")
            records.append(("expression", expression, ""))
            continue
        license_value = choice.get("license")
        if not isinstance(license_value, dict):
            raise SbomError(f"{label} contains an invalid license choice")
        identifiers = [field for field in ("id", "name") if field in license_value]
        if (
            len(identifiers) != 1
            or set(license_value) - {"id", "name", "url"}
        ):
            raise SbomError(f"{label} contains an ambiguous license object")
        kind = identifiers[0]
        value = license_value[kind]
        url = license_value.get("url", "")
        if (
            not isinstance(value, str)
            or not value.strip()
            or not isinstance(url, str)
            or ("url" in license_value and not url.strip())
        ):
            raise SbomError(f"{label} contains an empty license value")
        records.append((kind, value, url))
    if len(records) != len(set(records)):
        raise SbomError(f"{label} repeats a license choice")
    return tuple(sorted(records))


def _json_component_license_map(
    document: dict[str, object]
) -> dict[str, tuple[LicenseRecord, ...]]:
    metadata = document.get("metadata")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("component"), dict):
        raise SbomError("JSON metadata.component is missing")
    components = [metadata["component"], *_json_components(document)]
    result: dict[str, tuple[LicenseRecord, ...]] = {}
    for index, component in enumerate(components):
        purl = component.get("purl")
        if (
            not isinstance(purl, str)
            or not purl
            or component.get("bom-ref") != purl
            or purl in result
        ):
            raise SbomError(f"JSON component {index} has an ambiguous purl identity")
        result[purl] = _json_component_license_records(
            component, f"JSON component {purl}"
        )
    return result


def _json_mysql_example_names(document: dict[str, object]) -> set[str]:
    return {
        str(component.get("name"))
        for component in _json_first_party_components(document)
        if component.get("name") in MYSQL_EXAMPLE_NAMES
    }


def _json_has_mysql_example(document: dict[str, object]) -> bool:
    return bool(_json_mysql_example_names(document))


def _maven_jar_purl(group: str, name: str, version: str) -> str:
    return f"pkg:maven/{group}/{name}@{version}?type=jar"


def _json_exact_maven_components(
    document: dict[str, object], group: str, name: str, version: str
) -> list[dict[str, object]]:
    expected_purl = _maven_jar_purl(group, name, version)
    candidates = [
        component
        for component in _json_components(document)
        if (
            component.get("group") == group and component.get("name") == name
        )
        or component.get("bom-ref") == expected_purl
        or component.get("purl") == expected_purl
    ]
    for component in candidates:
        expected = {
            "type": "library",
            "bom-ref": expected_purl,
            "group": group,
            "name": name,
            "version": version,
            "purl": expected_purl,
        }
        actual = {field: component.get(field) for field in expected}
        if actual != expected:
            raise SbomError(
                f"Reviewed Maven component identity differs for {group}:{name}:{version}: "
                f"{actual}"
            )
    return candidates


def _validate_json_maven_coordinate_versions(
    document: dict[str, object], group: str, name: str, versions: set[str]
) -> None:
    expected_purls = {_maven_jar_purl(group, name, version) for version in versions}
    candidates = [
        component
        for component in _json_components(document)
        if (component.get("group") == group and component.get("name") == name)
        or component.get("bom-ref") in expected_purls
        or component.get("purl") in expected_purls
    ]
    actual_versions: list[str] = []
    for component in candidates:
        version = component.get("version")
        if not isinstance(version, str) or version not in versions:
            raise SbomError(
                f"Unexpected Maven component version for {group}:{name}: {version}"
            )
        expected_purl = _maven_jar_purl(group, name, version)
        expected = {
            "type": "library",
            "bom-ref": expected_purl,
            "group": group,
            "name": name,
            "version": version,
            "purl": expected_purl,
        }
        actual = {field: component.get(field) for field in expected}
        if actual != expected:
            raise SbomError(
                f"Reviewed Maven component identity differs for "
                f"{group}:{name}:{version}: {actual}"
            )
        actual_versions.append(version)
    if sorted(actual_versions) != sorted(versions):
        raise SbomError(
            "Example SBOM must contain exactly the pinned Maven versions: "
            f"{group}:{name}:{sorted(versions)}"
        )


def _is_forbidden_jts_io_identity(
    group: object, name: object, purl: object, bom_ref: object
) -> bool:
    def decoded(value: object) -> object:
        if not isinstance(value, str):
            return value
        try:
            return unquote(value, encoding="utf-8", errors="strict")
        except UnicodeDecodeError:
            return value

    group = decoded(group)
    name = decoded(name)
    purl = decoded(purl)
    bom_ref = decoded(bom_ref)
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


def _validate_json_pinned_example_dependency_contract(
    document: dict[str, object],
) -> None:
    metadata = document.get("metadata")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("component"), dict):
        raise SbomError("JSON metadata.component is missing")
    for component in [metadata["component"], *_json_components(document)]:
        if _is_forbidden_jts_io_identity(
            component.get("group"),
            component.get("name"),
            component.get("purl"),
            component.get("bom-ref"),
        ):
            raise SbomError("JTS I/O Common is forbidden by the pinned dependency contract")

    example_names = _json_mysql_example_names(document)
    if not example_names:
        return
    expected_versions: dict[tuple[str, str], set[str]] = {}
    for example_name in sorted(example_names):
        for group, name, version in REQUIRED_EXAMPLE_MAVEN_COORDINATES[example_name]:
            expected_versions.setdefault((group, name), set()).add(version)
    for (group, name), versions in sorted(expected_versions.items()):
        _validate_json_maven_coordinate_versions(document, group, name, versions)


def _json_mysql_connectors(document: dict[str, object]) -> list[dict[str, object]]:
    return _json_exact_maven_components(
        document,
        MYSQL_CONNECTOR_GROUP,
        MYSQL_CONNECTOR_NAME,
        MYSQL_CONNECTOR_VERSION,
    )


def _json_mysql_containers(document: dict[str, object]) -> list[dict[str, object]]:
    return [
        component
        for component in _json_components(document)
        if (
            component.get("type") == "container"
            and component.get("name") == MYSQL_CONTAINER_NAME
        )
        or component.get("bom-ref") == MYSQL_CONTAINER_PURL
        or component.get("purl") == MYSQL_CONTAINER_PURL
    ]


def _json_license_override_coordinates(
    document: dict[str, object],
) -> set[tuple[str, str, str]]:
    present: set[tuple[str, str, str]] = set()
    for coordinate in LICENSE_OVERRIDE_MAVEN_COORDINATES:
        components = _json_exact_maven_components(document, *coordinate)
        if len(components) > 1:
            raise SbomError(
                f"Multiple {coordinate[0]}:{coordinate[1]} components are ambiguous"
            )
        if components:
            present.add(coordinate)
    return present


def _set_json_reviewed_maven_licenses(document: dict[str, object]) -> None:
    for (group, name, expected_version), expression in (
        REVIEWED_MAVEN_LICENSE_EXPRESSIONS.items()
    ):
        components = _json_exact_maven_components(
            document, group, name, expected_version
        )
        if len(components) > 1:
            raise SbomError(f"Multiple {group}:{name} components are ambiguous")
        if not components:
            continue
        component = components[0]
        component["licenses"] = [{"expression": expression}]


def _verify_json_reviewed_maven_licenses(document: dict[str, object]) -> None:
    for (group, name, expected_version), expression in (
        REVIEWED_MAVEN_LICENSE_EXPRESSIONS.items()
    ):
        components = _json_exact_maven_components(
            document, group, name, expected_version
        )
        if len(components) > 1:
            raise SbomError(f"Multiple {group}:{name} components are ambiguous")
        if not components:
            continue
        component = components[0]
        if component.get("licenses") != [{"expression": expression}]:
            raise SbomError(f"Reviewed license metadata is missing for {group}:{name}")


def _json_mysql_container() -> dict[str, object]:
    return {
        "type": "container",
        "bom-ref": MYSQL_CONTAINER_PURL,
        "name": MYSQL_CONTAINER_NAME,
        "version": MYSQL_CONTAINER_VERSION,
        "scope": "excluded",
        "hashes": [{"alg": "SHA-256", "content": MYSQL_CONTAINER_DIGEST}],
        "purl": MYSQL_CONTAINER_PURL,
        "externalReferences": [
            {
                "type": "documentation",
                "url": MYSQL_CONTAINER_DOCUMENTATION_URL,
            }
        ],
        "properties": [
            {
                "name": MYSQL_CONTAINER_REVIEW_PROPERTY,
                "value": MYSQL_CONTAINER_REVIEW_VALUE,
            },
            {
                "name": MYSQL_CONTAINER_USAGE_PROPERTY,
                "value": MYSQL_CONTAINER_USAGE_VALUE,
            }
        ],
    }


def _set_json_mysql_supply_chain(document: dict[str, object]) -> None:
    _set_json_reviewed_maven_licenses(document)
    connectors = _json_mysql_connectors(document)
    if len(connectors) > 1:
        raise SbomError("Multiple MySQL Connector/J components are ambiguous")
    for connector in connectors:
        if connector.get("version") != MYSQL_CONNECTOR_VERSION:
            raise SbomError(
                f"Expected MySQL Connector/J {MYSQL_CONNECTOR_VERSION}, found {connector.get('version')}"
            )
        connector["licenses"] = [{"expression": MYSQL_CONNECTOR_LICENSE_EXPRESSION}]

    if not _json_has_mysql_example(document):
        if _json_mysql_containers(document):
            raise SbomError("Library-only BOM must not contain the MySQL test container")
        return
    if len(connectors) != 1:
        raise SbomError("MySQL example BOM must contain exactly one MySQL Connector/J component")
    containers = _json_mysql_containers(document)
    if not containers:
        container = _json_mysql_container()
        _json_components(document).append(container)
    elif len(containers) == 1:
        if containers[0] != _json_mysql_container():
            raise SbomError("Existing MySQL container component conflicts with the pinned fixture")
    else:
        raise SbomError("Multiple MySQL container components are ambiguous")

    dependencies = document.get("dependencies")
    if not isinstance(dependencies, list):
        raise SbomError("JSON dependencies must be an array")
    mysql_examples = [
        component
        for component in _json_first_party_components(document)
        if component.get("name") in MYSQL_EXAMPLE_NAMES
    ]
    for mysql_example in mysql_examples:
        mysql_example_ref = mysql_example.get("bom-ref")
        if not isinstance(mysql_example_ref, str):
            raise SbomError("MySQL example component has no bom-ref")
        dependency_entries = [
            entry
            for entry in dependencies
            if isinstance(entry, dict) and entry.get("ref") == mysql_example_ref
        ]
        if len(dependency_entries) != 1:
            raise SbomError("MySQL example must have exactly one dependency entry")
        depends_on = dependency_entries[0].setdefault("dependsOn", [])
        if not isinstance(depends_on, list) or any(
            not isinstance(value, str) for value in depends_on
        ):
            raise SbomError("MySQL example dependsOn must be an array of references")
        if MYSQL_CONTAINER_PURL not in depends_on:
            depends_on.append(MYSQL_CONTAINER_PURL)
            depends_on.sort()
    container_entries = [
        entry
        for entry in dependencies
        if isinstance(entry, dict) and entry.get("ref") == MYSQL_CONTAINER_PURL
    ]
    if not container_entries:
        dependencies.append({"ref": MYSQL_CONTAINER_PURL, "dependsOn": []})
    elif container_entries != [{"ref": MYSQL_CONTAINER_PURL, "dependsOn": []}]:
        raise SbomError("MySQL container dependency record must be one empty leaf")


def _verify_json_mysql_supply_chain(document: dict[str, object]) -> None:
    _verify_json_reviewed_maven_licenses(document)
    connectors = _json_mysql_connectors(document)
    if _json_has_mysql_example(document) and len(connectors) != 1:
        raise SbomError("MySQL example BOM must contain exactly one MySQL Connector/J component")
    for connector in connectors:
        if connector.get("version") != MYSQL_CONNECTOR_VERSION:
            raise SbomError("Unexpected MySQL Connector/J version")
        if connector.get("licenses") != [{"expression": MYSQL_CONNECTOR_LICENSE_EXPRESSION}]:
            raise SbomError("MySQL Connector/J license exception is missing from JSON")

    containers = _json_mysql_containers(document)
    if not _json_has_mysql_example(document):
        if containers:
            raise SbomError("Library-only BOM must not contain the MySQL test container")
        return
    if containers != [_json_mysql_container()]:
        raise SbomError("Pinned MySQL container component is missing or incorrect in JSON")

    dependencies = document.get("dependencies", [])
    for mysql_example in (
        component
        for component in _json_first_party_components(document)
        if component.get("name") in MYSQL_EXAMPLE_NAMES
    ):
        mysql_example_ref = mysql_example.get("bom-ref")
        matching = [
            entry
            for entry in dependencies
            if isinstance(entry, dict) and entry.get("ref") == mysql_example_ref
        ]
        depends_on = matching[0].get("dependsOn") if len(matching) == 1 else None
        if (
            len(matching) != 1
            or not isinstance(depends_on, list)
            or MYSQL_CONTAINER_PURL not in depends_on
        ):
            raise SbomError(
                "MySQL example dependency graph does not reference the pinned container"
            )
    container_entries = [
        entry
        for entry in dependencies
        if isinstance(entry, dict) and entry.get("ref") == MYSQL_CONTAINER_PURL
    ]
    if container_entries != [{"ref": MYSQL_CONTAINER_PURL, "dependsOn": []}]:
        raise SbomError("MySQL container dependency record must be one empty leaf")


def _set_json_component_license(component: dict[str, object]) -> None:
    existing = component.get("licenses")
    if existing not in (None, []):
        if not _json_has_exact_component_license(component):
            raise SbomError(
                f"Refusing to replace a non-{LICENSE_ID} license on {_json_identity(component)}"
            )
        return
    component["licenses"] = [{"license": {"id": LICENSE_ID, "url": LICENSE_URL}}]


def _json_has_exact_component_license(component: dict[str, object]) -> bool:
    choices = component.get("licenses")
    if not isinstance(choices, list) or len(choices) != 1:
        return False
    choice = choices[0]
    if not isinstance(choice, dict) or set(choice) != {"license"}:
        return False
    license_value = choice["license"]
    return (
        isinstance(license_value, dict)
        and set(license_value) == {"id", "url"}
        and license_value.get("id") == LICENSE_ID
        and license_value.get("url") == LICENSE_URL
    )


def _load_json(
    path: Path, *, add_missing_license: bool
) -> tuple[dict[str, object], set[tuple[object, object, object]], object]:
    try:
        decoded = _read_canonical_utf8(path, "CycloneDX JSON")
        document = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except SbomError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SbomError(f"Cannot read CycloneDX JSON {path}: {error}") from error
    if not isinstance(document, dict) or document.get("bomFormat") != "CycloneDX":
        raise SbomError(f"Not a CycloneDX JSON BOM: {path}")
    _reject_control_characters(document, "CycloneDX JSON")
    if document.get("specVersion") != "1.6":
        raise SbomError(f"Expected CycloneDX JSON 1.6 in {path}")
    _validate_json_document_profile(document)
    _validate_json_pinned_example_dependency_contract(document)
    components = _json_first_party_components(document)
    if not components:
        raise SbomError(f"No {FIRST_PARTY_GROUP} component found in {path}")
    if add_missing_license:
        for component in components:
            _set_json_component_license(component)
        _set_json_mysql_supply_chain(document)
    identities = {_json_identity(component) for component in components}
    return document, identities, document.get("serialNumber")


def _qname(local_name: str) -> str:
    return f"{{{CYCLONEDX_XML_NAMESPACE}}}{local_name}"


def _validate_xml_wrapper(
    element: ET.Element, label: str, expected_children: set[str]
) -> None:
    if (
        element.attrib
        or (element.text or "").strip()
        or (element.tail or "").strip()
        or any(child.tag not in expected_children for child in element)
    ):
        raise SbomError(f"{label} has an unsupported XML shape")


def _validate_xml_leaf(
    element: ET.Element,
    label: str,
    *,
    expected_attributes: set[str] = frozenset(),
) -> str:
    if (
        set(element.attrib) != set(expected_attributes)
        or len(element)
        or not (element.text or "").strip()
        or (element.tail or "").strip()
    ):
        raise SbomError(f"{label} must be an unambiguous XML leaf")
    return element.text or ""


def _validate_xml_document_profile(root: ET.Element) -> None:
    if (
        root.tag != _qname("bom")
        or set(root.attrib) != {"serialNumber", "version"}
        or not root.get("serialNumber")
        or root.get("version") != "1"
        or (root.text or "").strip()
        or (root.tail or "").strip()
        or [child.tag for child in root]
        != [_qname("metadata"), _qname("components"), _qname("dependencies")]
    ):
        raise SbomError("XML document differs from the supported CycloneDX 1.6 profile")
    metadata, components, dependencies = list(root)
    metadata_tags = [child.tag for child in metadata]
    if (
        metadata.attrib
        or (metadata.text or "").strip()
        or (metadata.tail or "").strip()
        or any(tag not in {_qname(field) for field in METADATA_FIELDS} for tag in metadata_tags)
        or metadata_tags.count(_qname("timestamp")) != 1
        or metadata_tags.count(_qname("tools")) != 1
        or metadata_tags.count(_qname("component")) != 1
        or metadata_tags.count(_qname("licenses")) != 1
        or metadata_tags != sorted(
            metadata_tags,
            key=[
                _qname("timestamp"),
                _qname("tools"),
                _qname("authors"),
                _qname("component"),
                _qname("manufacture"),
                _qname("supplier"),
                _qname("licenses"),
                _qname("properties"),
                _qname("lifecycles"),
            ].index,
        )
    ):
        raise SbomError("XML metadata differs from the supported CycloneDX profile")
    timestamp = metadata.find(_qname("timestamp"))
    if timestamp is None:
        raise SbomError("XML metadata timestamp is missing")
    _validate_timestamp(
        _validate_xml_leaf(timestamp, "XML metadata timestamp"),
        "XML metadata timestamp",
    )
    tools = metadata.find(_qname("tools"))
    if tools is None:
        raise SbomError("XML metadata tools are missing")
    _validate_xml_wrapper(tools, "XML metadata tools", {_qname("components")})
    tool_components = list(tools)
    if len(tool_components) != 1:
        raise SbomError("XML metadata tools must contain one components wrapper")
    tool_wrapper = tool_components[0]
    _validate_xml_wrapper(
        tool_wrapper, "XML metadata tool components", {_qname("component")}
    )
    if len(tool_wrapper) != 1:
        raise SbomError("XML metadata tools must contain one producer component")
    tool = tool_wrapper[0]
    if (
        tool.attrib != {"type": "application"}
        or (tool.text or "").strip()
        or (tool.tail or "").strip()
        or [child.tag for child in tool]
        != [_qname("author"), _qname("name"), _qname("version")]
        or [
            _validate_xml_leaf(child, "XML metadata tool field")
            for child in tool
        ]
        != ["CycloneDX", "cyclonedx-gradle-plugin", "3.4.0"]
    ):
        raise SbomError("XML metadata tool differs from the pinned producer")
    _validate_xml_wrapper(components, "XML components", {_qname("component")})
    _validate_xml_wrapper(dependencies, "XML dependencies", {_qname("dependency")})
    seen_refs: set[str] = set()
    for dependency in dependencies:
        if (
            dependency.tag != _qname("dependency")
            or set(dependency.attrib) != {"ref"}
            or not dependency.get("ref")
            or dependency.get("ref") in seen_refs
            or (dependency.text or "").strip()
            or (dependency.tail or "").strip()
            or any(
                child.tag != _qname("dependency")
                or set(child.attrib) != {"ref"}
                or not child.get("ref")
                or len(child)
                or (child.text or "").strip()
                or (child.tail or "").strip()
                for child in dependency
            )
        ):
            raise SbomError("XML dependency graph has an unsupported shape")
        targets = [child.get("ref") for child in dependency]
        if len(targets) != len(set(targets)):
            raise SbomError("XML dependency graph repeats an edge")
        seen_refs.add(dependency.get("ref") or "")


def _xml_identity(component: ET.Element) -> tuple[object, object, object]:
    return (
        component.findtext(_qname("group")),
        component.findtext(_qname("name")),
        component.findtext(_qname("version")),
    )


def _xml_has_exact_document_license(root: ET.Element) -> bool:
    licenses = root.find(f"{_qname('metadata')}/{_qname('licenses')}")
    if (
        licenses is None
        or licenses.attrib
        or (licenses.text or "").strip()
        or (licenses.tail or "").strip()
        or len(licenses) != 1
    ):
        return False
    license_element = licenses[0]
    if (
        license_element.tag != _qname("license")
        or license_element.attrib
        or (license_element.text or "").strip()
        or (license_element.tail or "").strip()
        or [child.tag for child in license_element]
        != [_qname("id"), _qname("url")]
    ):
        return False
    identifier, url = list(license_element)
    return (
        not identifier.attrib
        and not url.attrib
        and len(identifier) == 0
        and len(url) == 0
        and identifier.text == LICENSE_ID
        and url.text == LICENSE_URL
        and not (identifier.tail or "").strip()
        and not (url.tail or "").strip()
    )


def _xml_first_party_components(root: ET.Element) -> list[ET.Element]:
    metadata_component = root.find(f"{_qname('metadata')}/{_qname('component')}")
    if metadata_component is None:
        raise SbomError("XML metadata/component is missing")
    candidates = [metadata_component]
    candidates.extend(root.findall(f"{_qname('components')}/{_qname('component')}"))
    return [
        component
        for component in candidates
        if component.findtext(_qname("group")) == FIRST_PARTY_GROUP
    ]


def _xml_components(root: ET.Element) -> list[ET.Element]:
    metadata_component = root.find(f"{_qname('metadata')}/{_qname('component')}")
    if metadata_component is None:
        raise SbomError("XML metadata/component is missing")
    components = root.find(_qname("components"))
    if components is None:
        raise SbomError("XML components element is missing")
    values = components.findall(_qname("component"))
    if any(
        component.find(_qname("components")) is not None
        for component in [metadata_component, *values]
    ):
        raise SbomError("Nested XML components are not supported")
    return values


def _xml_component_license_records(
    component: ET.Element, label: str
) -> tuple[LicenseRecord, ...]:
    allowed_children = {
        _qname(field)
        for field in SUPPORTED_COMPONENT_FIELDS
        if field not in {"type", "bom-ref"}
    }
    unsupported = [child.tag for child in component if child.tag not in allowed_children]
    if unsupported:
        raise SbomError(
            f"{label} contains unsupported CycloneDX fields: {unsupported}"
        )
    child_tags = [
        child.tag.removeprefix(f"{{{CYCLONEDX_XML_NAMESPACE}}}")
        for child in component
    ]
    order = {field: index for index, field in enumerate(COMPONENT_FIELD_ORDER)}
    if child_tags != sorted(child_tags, key=order.__getitem__) or len(child_tags) != len(
        set(child_tags)
    ):
        raise SbomError(f"{label} has invalid CycloneDX component child order")
    if (
        set(component.attrib) != {"type", "bom-ref"}
        or (component.text or "").strip()
        or (component.tail or "").strip()
    ):
        raise SbomError(f"{label} has an unsupported component shape")
    for field in (
        "publisher",
        "group",
        "name",
        "version",
        "description",
        "scope",
        "purl",
        "modified",
    ):
        value = component.find(_qname(field))
        if value is not None:
            _validate_xml_leaf(value, f"{label} {field}")
    hash_wrappers = component.findall(_qname("hashes"))
    if hash_wrappers:
        hashes = hash_wrappers[0]
        _validate_xml_wrapper(hashes, f"{label} hashes", {_qname("hash")})
        for item in hashes:
            _validate_xml_leaf(
                item, f"{label} hash", expected_attributes={"alg"}
            )
    reference_wrappers = component.findall(_qname("externalReferences"))
    if reference_wrappers:
        references = reference_wrappers[0]
        _validate_xml_wrapper(
            references, f"{label} externalReferences", {_qname("reference")}
        )
        for reference in references:
            if (
                set(reference.attrib) != {"type"}
                or (reference.text or "").strip()
                or (reference.tail or "").strip()
                or [child.tag for child in reference] != [_qname("url")]
            ):
                raise SbomError(f"{label} contains an invalid external reference")
            _validate_xml_leaf(reference[0], f"{label} external reference URL")
    property_wrappers = component.findall(_qname("properties"))
    if property_wrappers:
        properties = property_wrappers[0]
        _validate_xml_wrapper(
            properties, f"{label} properties", {_qname("property")}
        )
        property_names: list[str] = []
        for item in properties:
            _validate_xml_leaf(
                item, f"{label} property", expected_attributes={"name"}
            )
            property_names.append(item.get("name") or "")
        if len(property_names) != len(set(property_names)):
            raise SbomError(f"{label} repeats a property name")
    license_parents = component.findall(_qname("licenses"))
    if len(license_parents) > 1:
        raise SbomError(f"{label} repeats its licenses element")
    if not license_parents:
        return ()
    licenses = license_parents[0]
    choices = list(licenses)
    if (
        licenses.attrib
        or (licenses.text or "").strip()
        or (licenses.tail or "").strip()
        or not choices
    ):
        raise SbomError(f"{label} has an empty or invalid licenses element")
    if any(choice.tag == _qname("expression") for choice in choices) and (
        len(choices) != 1 or choices[0].tag != _qname("expression")
    ):
        raise SbomError(
            f"{label} licenseChoice must be one expression or license objects"
        )
    records: list[LicenseRecord] = []
    for choice in choices:
        if choice.tag == _qname("expression"):
            if (
                choice.attrib
                or len(choice)
                or not (choice.text or "").strip()
                or (choice.tail or "").strip()
            ):
                raise SbomError(f"{label} contains an invalid license expression")
            records.append(("expression", choice.text or "", ""))
            continue
        if choice.tag != _qname("license"):
            raise SbomError(f"{label} contains an unsupported license choice")
        children = list(choice)
        child_tags = [child.tag for child in children]
        valid_orders = {
            (_qname("id"),),
            (_qname("name"),),
            (_qname("id"), _qname("url")),
            (_qname("name"), _qname("url")),
        }
        if (
            choice.attrib
            or (choice.text or "").strip()
            or (choice.tail or "").strip()
            or tuple(child_tags) not in valid_orders
            or any(
                child.attrib
                or len(child)
                or not (child.text or "").strip()
                or (child.tail or "").strip()
                for child in children
            )
        ):
            raise SbomError(f"{label} contains an ambiguous license object")
        kind = children[0].tag.removeprefix(
            f"{{{CYCLONEDX_XML_NAMESPACE}}}"
        )
        records.append(
            (kind, children[0].text or "", children[1].text or "" if len(children) == 2 else "")
        )
    if len(records) != len(set(records)):
        raise SbomError(f"{label} repeats a license choice")
    return tuple(sorted(records))


def _xml_component_license_map(
    root: ET.Element,
) -> dict[str, tuple[LicenseRecord, ...]]:
    metadata_component = root.find(f"{_qname('metadata')}/{_qname('component')}")
    if metadata_component is None:
        raise SbomError("XML metadata/component is missing")
    components = [metadata_component, *_xml_components(root)]
    result: dict[str, tuple[LicenseRecord, ...]] = {}
    for index, component in enumerate(components):
        purls = component.findall(_qname("purl"))
        if (
            len(purls) != 1
            or purls[0].attrib
            or len(purls[0])
            or not (purls[0].text or "").strip()
            or (purls[0].tail or "").strip()
        ):
            raise SbomError(f"XML component {index} has an ambiguous purl")
        purl = purls[0].text or ""
        if component.get("bom-ref") != purl or purl in result:
            raise SbomError(f"XML component {index} has an ambiguous purl identity")
        result[purl] = _xml_component_license_records(
            component, f"XML component {purl}"
        )
    return result


def _normalized_description(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _json_component_record(
    component: dict[str, object], label: str
) -> dict[str, object]:
    purl = component.get("purl")
    if not isinstance(purl, str) or not purl or component.get("bom-ref") != purl:
        raise SbomError(f"{label} has an ambiguous purl identity")
    _validate_supported_maven_component_identity(
        component.get("group"),
        component.get("name"),
        component.get("version"),
        purl,
        label,
    )
    hashes = tuple(
        sorted(
            (str(item["alg"]), str(item["content"]))
            for item in component.get("hashes", [])
        )
    )
    references = tuple(
        sorted(
            (str(item["type"]), str(item["url"]))
            for item in component.get("externalReferences", [])
        )
    )
    properties = tuple(
        sorted(
            (str(item["name"]), str(item["value"]))
            for item in component.get("properties", [])
        )
    )
    description = component.get("description")
    return {
        "bom-ref": component.get("bom-ref"),
        "description": (
            _normalized_description(description)
            if isinstance(description, str)
            else None
        ),
        "externalReferences": references,
        "group": component.get("group"),
        "hashes": hashes,
        "licenses": _json_component_license_records(component, label),
        "modified": component.get("modified"),
        "name": component.get("name"),
        "properties": properties,
        "publisher": component.get("publisher"),
        "purl": purl,
        "scope": component.get("scope"),
        "type": component.get("type"),
        "version": component.get("version"),
    }


def _xml_component_record(
    component: ET.Element, label: str
) -> tuple[str, dict[str, object]]:
    _xml_component_license_records(component, label)

    def optional_text(name: str) -> str | None:
        values = component.findall(_qname(name))
        if len(values) > 1:
            raise SbomError(f"{label} repeats {name}")
        if not values:
            return None
        return _validate_xml_leaf(values[0], f"{label} {name}")

    purl = optional_text("purl")
    group = optional_text("group")
    name = optional_text("name")
    version = optional_text("version")
    component_type = component.get("type")
    if (
        purl is None
        or name is None
        or version is None
        or not component_type
        or component.get("bom-ref") != purl
    ):
        raise SbomError(f"{label} has an ambiguous component identity")
    _validate_supported_maven_component_identity(
        group, name, version, purl, label
    )

    hashes: list[tuple[str, str]] = []
    hash_parent = component.find(_qname("hashes"))
    if hash_parent is not None:
        for item in hash_parent:
            algorithm = item.get("alg")
            if not algorithm:
                raise SbomError(f"{label} has an empty hash algorithm")
            hashes.append(
                (algorithm, _validate_xml_leaf(item, f"{label} hash", expected_attributes={"alg"}))
            )

    references: list[tuple[str, str]] = []
    reference_parent = component.find(_qname("externalReferences"))
    if reference_parent is not None:
        for item in reference_parent:
            reference_type = item.get("type")
            if not reference_type or len(item) != 1:
                raise SbomError(f"{label} has an ambiguous external reference")
            references.append(
                (
                    reference_type,
                    _validate_xml_leaf(item[0], f"{label} external reference URL"),
                )
            )

    properties: list[tuple[str, str]] = []
    property_parent = component.find(_qname("properties"))
    if property_parent is not None:
        for item in property_parent:
            property_name = item.get("name")
            if not property_name:
                raise SbomError(f"{label} has an empty property name")
            properties.append(
                (
                    property_name,
                    _validate_xml_leaf(
                        item, f"{label} property", expected_attributes={"name"}
                    ),
                )
            )

    modified = optional_text("modified")
    if modified is not None and modified not in {"true", "false"}:
        raise SbomError(f"{label} modified must be true or false")
    description = optional_text("description")
    return purl, {
        "bom-ref": component.get("bom-ref"),
        "description": (
            _normalized_description(description) if description is not None else None
        ),
        "externalReferences": tuple(sorted(references)),
        "group": group,
        "hashes": tuple(sorted(hashes)),
        "licenses": _xml_component_license_records(component, label),
        "modified": None if modified is None else modified == "true",
        "name": name,
        "properties": tuple(sorted(properties)),
        "publisher": optional_text("publisher"),
        "purl": purl,
        "scope": optional_text("scope"),
        "type": component_type,
        "version": version,
    }


def _json_all_component_records(
    document: dict[str, object], label: str
) -> tuple[str, dict[str, dict[str, object]]]:
    metadata = document["metadata"]
    if not isinstance(metadata, dict) or not isinstance(metadata.get("component"), dict):
        raise SbomError(f"{label} JSON metadata.component is missing")
    components = [metadata["component"], *_json_components(document)]
    records: dict[str, dict[str, object]] = {}
    for index, component in enumerate(components):
        record = _json_component_record(component, f"{label} JSON component {index}")
        purl = str(record["purl"])
        if purl in records:
            raise SbomError(f"{label} JSON repeats component purl: {purl}")
        records[purl] = record
    return str(components[0]["purl"]), records


def _xml_all_component_records(
    root: ET.Element, label: str
) -> tuple[str, dict[str, dict[str, object]]]:
    metadata_component = root.find(f"{_qname('metadata')}/{_qname('component')}")
    if metadata_component is None:
        raise SbomError(f"{label} XML metadata.component is missing")
    components = [metadata_component, *_xml_components(root)]
    records: dict[str, dict[str, object]] = {}
    for index, component in enumerate(components):
        purl, record = _xml_component_record(
            component, f"{label} XML component {index}"
        )
        if purl in records:
            raise SbomError(f"{label} XML repeats component purl: {purl}")
        records[purl] = record
    return str(metadata_component.findtext(_qname("purl"))), records


def _json_dependency_graph(document: dict[str, object], label: str) -> dict[str, frozenset[str]]:
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, list):
        raise SbomError(f"{label} JSON dependency graph is missing")
    graph: dict[str, frozenset[str]] = {}
    for index, entry in enumerate(dependencies):
        if not isinstance(entry, dict) or set(entry) != {"ref", "dependsOn"}:
            raise SbomError(f"{label} JSON dependency record {index} is invalid")
        ref = entry["ref"]
        targets = entry["dependsOn"]
        if not isinstance(ref, str) or not isinstance(targets, list):
            raise SbomError(f"{label} JSON dependency record {index} is invalid")
        if ref in graph or ref in targets:
            raise SbomError(f"{label} JSON dependency graph repeats or self-references a node")
        graph[ref] = frozenset(str(target) for target in targets)
    return graph


def _xml_dependency_graph(root: ET.Element, label: str) -> dict[str, frozenset[str]]:
    dependencies = root.find(_qname("dependencies"))
    if dependencies is None:
        raise SbomError(f"{label} XML dependency graph is missing")
    graph: dict[str, frozenset[str]] = {}
    for entry in dependencies:
        ref = entry.get("ref")
        if ref is None:
            raise SbomError(f"{label} XML dependency record has no ref")
        targets = [child.get("ref") for child in entry]
        if ref in graph or ref in targets or any(target is None for target in targets):
            raise SbomError(f"{label} XML dependency graph repeats or self-references a node")
        graph[ref] = frozenset(str(target) for target in targets)
    return graph


def _validate_role_and_graph(
    root_ref: str, records: dict[str, dict[str, object]], graph: dict[str, frozenset[str]], label: str
) -> str:
    root = records[root_ref]
    root_name = root.get("name")
    if root_name not in EXPECTED_FIRST_PARTY_CHILDREN:
        raise SbomError(f"{label} has an unsupported RouteContract root role: {root_name}")
    root_version = root.get("version")
    expected_root_purl = (
        f"pkg:maven/{FIRST_PARTY_GROUP}/{root_name}@{root_version}"
        f"?project_path=%3A{'' if root_name == AGGREGATE_ROOT_NAME else root_name}"
    )
    if (
        root.get("type") != "library"
        or root.get("group") != FIRST_PARTY_GROUP
        or root_ref != expected_root_purl
        or root.get("licenses") != (("id", LICENSE_ID, LICENSE_URL),)
    ):
        raise SbomError(f"{label} has an unexpected first-party root identity")

    first_party_children: dict[str, dict[str, object]] = {}
    for purl, record in records.items():
        if purl == root_ref or record.get("group") != FIRST_PARTY_GROUP:
            continue
        name = record.get("name")
        version = record.get("version")
        if not isinstance(name, str):
            raise SbomError(f"{label} has an ambiguous first-party component")
        expected_purl = (
            f"pkg:maven/{FIRST_PARTY_GROUP}/{name}@{version}?project_path=%3A{name}"
        )
        if (
            name in first_party_children
            or record.get("type") != "library"
            or version != root_version
            or purl != expected_purl
            or record.get("licenses") != (("id", LICENSE_ID, LICENSE_URL),)
        ):
            raise SbomError(f"{label} has an unexpected first-party component: {name}")
        first_party_children[name] = record
    if set(first_party_children) != EXPECTED_FIRST_PARTY_CHILDREN[str(root_name)]:
        raise SbomError(
            f"{label} first-party role coverage differs: "
            f"{set(first_party_children)} != {EXPECTED_FIRST_PARTY_CHILDREN[str(root_name)]}"
        )

    nodes = set(records)
    if set(graph) != nodes:
        raise SbomError(f"{label} dependency graph must contain exactly one record per node")
    if any(not targets <= nodes for targets in graph.values()):
        raise SbomError(f"{label} dependency graph contains a dangling edge")

    first_party_refs = {
        str(root_name): root_ref,
        **{
            name: str(record["purl"])
            for name, record in first_party_children.items()
        },
    }
    first_party_names_by_ref = {
        ref: name for name, ref in first_party_refs.items()
    }
    observed_first_party_dependencies = {
        name: {
            first_party_names_by_ref[target]
            for target in graph[ref]
            if target in first_party_names_by_ref
        }
        for name, ref in first_party_refs.items()
    }
    expected_first_party_dependencies = EXPECTED_FIRST_PARTY_DEPENDENCIES[
        str(root_name)
    ]
    if observed_first_party_dependencies != expected_first_party_dependencies:
        raise SbomError(
            f"{label} first-party dependency ownership differs: "
            f"{observed_first_party_dependencies} != "
            f"{expected_first_party_dependencies}"
        )

    first_party_reachable: set[str] = set()
    first_party_pending = [root_ref]
    while first_party_pending:
        ref = first_party_pending.pop()
        if ref in first_party_reachable:
            continue
        first_party_reachable.add(ref)
        first_party_pending.extend(
            target for target in graph[ref] if target in first_party_names_by_ref
        )
    if first_party_reachable != set(first_party_refs.values()):
        raise SbomError(
            f"{label} first-party component is not reachable through "
            "first-party dependency edges"
        )

    reachable: set[str] = set()
    pending = [root_ref]
    while pending:
        ref = pending.pop()
        if ref in reachable:
            continue
        reachable.add(ref)
        pending.extend(graph[ref])
    if reachable != nodes:
        raise SbomError(f"{label} dependency graph contains a node unreachable from its root")
    return str(root_name)


def _verify_semantic_pair(
    json_document: dict[str, object], xml_root: ET.Element, label: str
) -> str:
    json_root, json_records = _json_all_component_records(json_document, label)
    xml_root_ref, xml_records = _xml_all_component_records(xml_root, label)
    if (json_root, json_records) != (xml_root_ref, xml_records):
        raise SbomError(f"{label} JSON/XML component records differ")
    json_metadata = json_document["metadata"]
    if not isinstance(json_metadata, dict):
        raise SbomError(f"{label} JSON metadata is invalid")
    xml_metadata = xml_root.find(_qname("metadata"))
    if xml_metadata is None:
        raise SbomError(f"{label} XML metadata is missing")
    if (
        xml_metadata.findtext(_qname("timestamp")) != json_metadata.get("timestamp")
        or json_metadata.get("tools") != {"components": [EXPECTED_TOOL_COMPONENT]}
    ):
        raise SbomError(f"{label} JSON/XML metadata timestamp or tools differ")
    json_graph = _json_dependency_graph(json_document, label)
    xml_graph = _xml_dependency_graph(xml_root, label)
    if json_graph != xml_graph:
        raise SbomError(f"{label} JSON/XML dependency graphs differ")
    return _validate_role_and_graph(json_root, json_records, json_graph, label)


def _xml_mysql_example_names(root: ET.Element) -> set[str]:
    return {
        str(component.findtext(_qname("name")))
        for component in _xml_first_party_components(root)
        if component.findtext(_qname("name")) in MYSQL_EXAMPLE_NAMES
    }


def _xml_has_mysql_example(root: ET.Element) -> bool:
    return bool(_xml_mysql_example_names(root))


def _xml_single_component_text(
    component: ET.Element, field: str, coordinate: str
) -> str | None:
    values = component.findall(_qname(field))
    if len(values) > 1:
        raise SbomError(f"Reviewed Maven component repeats {field}: {coordinate}")
    return values[0].text if values else None


def _xml_exact_maven_components(
    root: ET.Element, group: str, name: str, version: str
) -> list[ET.Element]:
    expected_purl = _maven_jar_purl(group, name, version)
    coordinate = f"{group}:{name}:{version}"
    candidates: list[ET.Element] = []
    for component in _xml_components(root):
        component_group = component.findtext(_qname("group"))
        component_name = component.findtext(_qname("name"))
        if (
            (component_group == group and component_name == name)
            or component.get("bom-ref") == expected_purl
            or component.findtext(_qname("purl")) == expected_purl
        ):
            candidates.append(component)
    for component in candidates:
        actual = {
            "type": component.get("type"),
            "bom-ref": component.get("bom-ref"),
            "group": _xml_single_component_text(component, "group", coordinate),
            "name": _xml_single_component_text(component, "name", coordinate),
            "version": _xml_single_component_text(component, "version", coordinate),
            "purl": _xml_single_component_text(component, "purl", coordinate),
        }
        expected = {
            "type": "library",
            "bom-ref": expected_purl,
            "group": group,
            "name": name,
            "version": version,
            "purl": expected_purl,
        }
        if actual != expected:
            raise SbomError(
                f"Reviewed Maven component identity differs for {coordinate}: {actual}"
            )
    return candidates


def _validate_xml_maven_coordinate_versions(
    root: ET.Element, group: str, name: str, versions: set[str]
) -> None:
    expected_purls = {_maven_jar_purl(group, name, version) for version in versions}
    candidates = [
        component
        for component in _xml_components(root)
        if (
            component.findtext(_qname("group")) == group
            and component.findtext(_qname("name")) == name
        )
        or component.get("bom-ref") in expected_purls
        or component.findtext(_qname("purl")) in expected_purls
    ]
    actual_versions: list[str] = []
    for component in candidates:
        version = component.findtext(_qname("version"))
        if version not in versions:
            raise SbomError(
                f"Unexpected Maven component version for {group}:{name}: {version}"
            )
        expected_purl = _maven_jar_purl(group, name, str(version))
        coordinate = f"{group}:{name}:{version}"
        actual = {
            "type": component.get("type"),
            "bom-ref": component.get("bom-ref"),
            "group": _xml_single_component_text(component, "group", coordinate),
            "name": _xml_single_component_text(component, "name", coordinate),
            "version": _xml_single_component_text(component, "version", coordinate),
            "purl": _xml_single_component_text(component, "purl", coordinate),
        }
        expected = {
            "type": "library",
            "bom-ref": expected_purl,
            "group": group,
            "name": name,
            "version": version,
            "purl": expected_purl,
        }
        if actual != expected:
            raise SbomError(
                f"Reviewed Maven component identity differs for {coordinate}: {actual}"
            )
        actual_versions.append(str(version))
    if sorted(actual_versions) != sorted(versions):
        raise SbomError(
            "Example SBOM must contain exactly the pinned Maven versions: "
            f"{group}:{name}:{sorted(versions)}"
        )


def _validate_xml_pinned_example_dependency_contract(root: ET.Element) -> None:
    metadata_component = root.find(f"{_qname('metadata')}/{_qname('component')}")
    if metadata_component is None:
        raise SbomError("XML metadata.component is missing")
    for component in [metadata_component, *_xml_components(root)]:
        if _is_forbidden_jts_io_identity(
            component.findtext(_qname("group")),
            component.findtext(_qname("name")),
            component.findtext(_qname("purl")),
            component.get("bom-ref"),
        ):
            raise SbomError("JTS I/O Common is forbidden by the pinned dependency contract")

    example_names = _xml_mysql_example_names(root)
    if not example_names:
        return
    expected_versions: dict[tuple[str, str], set[str]] = {}
    for example_name in sorted(example_names):
        for group, name, version in REQUIRED_EXAMPLE_MAVEN_COORDINATES[example_name]:
            expected_versions.setdefault((group, name), set()).add(version)
    for (group, name), versions in sorted(expected_versions.items()):
        _validate_xml_maven_coordinate_versions(root, group, name, versions)


def _xml_mysql_connectors(root: ET.Element) -> list[ET.Element]:
    return _xml_exact_maven_components(
        root,
        MYSQL_CONNECTOR_GROUP,
        MYSQL_CONNECTOR_NAME,
        MYSQL_CONNECTOR_VERSION,
    )


def _xml_mysql_containers(root: ET.Element) -> list[ET.Element]:
    return [
        component
        for component in _xml_components(root)
        if (
            component.get("type") == "container"
            and component.findtext(_qname("name")) == MYSQL_CONTAINER_NAME
        )
        or component.get("bom-ref") == MYSQL_CONTAINER_PURL
        or component.findtext(_qname("purl")) == MYSQL_CONTAINER_PURL
    ]


def _xml_license_override_coordinates(
    root: ET.Element,
) -> set[tuple[str, str, str]]:
    present: set[tuple[str, str, str]] = set()
    for coordinate in LICENSE_OVERRIDE_MAVEN_COORDINATES:
        components = _xml_exact_maven_components(root, *coordinate)
        if len(components) > 1:
            raise SbomError(
                f"Multiple {coordinate[0]}:{coordinate[1]} components are ambiguous"
            )
        if components:
            present.add(coordinate)
    return present


def _set_xml_license_expression(component: ET.Element, expression: str) -> None:
    licenses = component.find(_qname("licenses"))
    if licenses is None:
        licenses = ET.Element(_qname("licenses"))
        purl = component.find(_qname("purl"))
        component.insert(
            list(component).index(purl) if purl is not None else len(component),
            licenses,
        )
    else:
        licenses.clear()
    ET.SubElement(licenses, _qname("expression")).text = expression


def _set_xml_reviewed_maven_licenses(root: ET.Element) -> None:
    for (group, name, expected_version), expression in (
        REVIEWED_MAVEN_LICENSE_EXPRESSIONS.items()
    ):
        components = _xml_exact_maven_components(root, group, name, expected_version)
        if len(components) > 1:
            raise SbomError(f"Multiple {group}:{name} components are ambiguous")
        if not components:
            continue
        component = components[0]
        _set_xml_license_expression(component, expression)


def _xml_has_exact_license_expression(
    component: ET.Element, expression: str
) -> bool:
    license_parents = component.findall(_qname("licenses"))
    if len(license_parents) != 1:
        return False
    licenses = license_parents[0]
    choices = list(licenses)
    return (
        not licenses.attrib
        and not (licenses.text or "").strip()
        and not (licenses.tail or "").strip()
        and len(choices) == 1
        and choices[0].tag == _qname("expression")
        and not choices[0].attrib
        and len(choices[0]) == 0
        and choices[0].text == expression
        and not (choices[0].tail or "").strip()
    )


def _verify_xml_reviewed_maven_licenses(root: ET.Element) -> None:
    for (group, name, expected_version), expression in (
        REVIEWED_MAVEN_LICENSE_EXPRESSIONS.items()
    ):
        components = _xml_exact_maven_components(root, group, name, expected_version)
        if len(components) > 1:
            raise SbomError(f"Multiple {group}:{name} components are ambiguous")
        if not components:
            continue
        component = components[0]
        if not _xml_has_exact_license_expression(component, expression):
            raise SbomError(f"Reviewed license metadata is missing for {group}:{name}")


def _xml_mysql_container() -> ET.Element:
    component = ET.Element(
        _qname("component"), {"type": "container", "bom-ref": MYSQL_CONTAINER_PURL}
    )
    ET.SubElement(component, _qname("name")).text = MYSQL_CONTAINER_NAME
    ET.SubElement(component, _qname("version")).text = MYSQL_CONTAINER_VERSION
    ET.SubElement(component, _qname("scope")).text = "excluded"
    hashes = ET.SubElement(component, _qname("hashes"))
    ET.SubElement(hashes, _qname("hash"), {"alg": "SHA-256"}).text = MYSQL_CONTAINER_DIGEST
    ET.SubElement(component, _qname("purl")).text = MYSQL_CONTAINER_PURL
    references = ET.SubElement(component, _qname("externalReferences"))
    reference = ET.SubElement(
        references, _qname("reference"), {"type": "documentation"}
    )
    ET.SubElement(reference, _qname("url")).text = MYSQL_CONTAINER_DOCUMENTATION_URL
    properties = ET.SubElement(component, _qname("properties"))
    ET.SubElement(
        properties, _qname("property"), {"name": MYSQL_CONTAINER_REVIEW_PROPERTY}
    ).text = MYSQL_CONTAINER_REVIEW_VALUE
    ET.SubElement(
        properties, _qname("property"), {"name": MYSQL_CONTAINER_USAGE_PROPERTY}
    ).text = MYSQL_CONTAINER_USAGE_VALUE
    return component


def _xml_mysql_container_is_exact(component: ET.Element) -> bool:
    if (
        component.attrib != {"type": "container", "bom-ref": MYSQL_CONTAINER_PURL}
        or (component.text or "").strip()
        or (component.tail or "").strip()
    ):
        return False
    children = list(component)
    if [child.tag for child in children] != [
        _qname("name"),
        _qname("version"),
        _qname("scope"),
        _qname("hashes"),
        _qname("purl"),
        _qname("externalReferences"),
        _qname("properties"),
    ]:
        return False
    name, version, scope, hashes, purl, references, properties = children
    for element, expected in (
        (name, MYSQL_CONTAINER_NAME),
        (version, MYSQL_CONTAINER_VERSION),
        (scope, "excluded"),
        (purl, MYSQL_CONTAINER_PURL),
    ):
        if (
            element.attrib
            or len(element)
            or element.text != expected
            or (element.tail or "").strip()
        ):
            return False

    hash_elements = list(hashes)
    if (
        hashes.attrib
        or (hashes.text or "").strip()
        or (hashes.tail or "").strip()
        or len(hash_elements) != 1
        or hash_elements[0].tag != _qname("hash")
        or hash_elements[0].attrib != {"alg": "SHA-256"}
        or len(hash_elements[0])
        or hash_elements[0].text != MYSQL_CONTAINER_DIGEST
        or (hash_elements[0].tail or "").strip()
    ):
        return False

    if component.find(_qname("licenses")) is not None:
        return False

    reference_elements = list(references)
    if (
        references.attrib
        or (references.text or "").strip()
        or (references.tail or "").strip()
        or len(reference_elements) != 1
        or reference_elements[0].tag != _qname("reference")
        or reference_elements[0].attrib != {"type": "documentation"}
        or (reference_elements[0].text or "").strip()
        or (reference_elements[0].tail or "").strip()
        or len(reference_elements[0]) != 1
        or reference_elements[0][0].tag != _qname("url")
        or reference_elements[0][0].attrib
        or len(reference_elements[0][0])
        or reference_elements[0][0].text != MYSQL_CONTAINER_DOCUMENTATION_URL
        or (reference_elements[0][0].tail or "").strip()
    ):
        return False

    property_elements = list(properties)
    return (
        not properties.attrib
        and not (properties.text or "").strip()
        and not (properties.tail or "").strip()
        and len(property_elements) == 2
        and property_elements[0].tag == _qname("property")
        and property_elements[0].attrib == {"name": MYSQL_CONTAINER_REVIEW_PROPERTY}
        and len(property_elements[0]) == 0
        and property_elements[0].text == MYSQL_CONTAINER_REVIEW_VALUE
        and not (property_elements[0].tail or "").strip()
        and property_elements[1].tag == _qname("property")
        and property_elements[1].attrib == {"name": MYSQL_CONTAINER_USAGE_PROPERTY}
        and len(property_elements[1]) == 0
        and property_elements[1].text == MYSQL_CONTAINER_USAGE_VALUE
        and not (property_elements[1].tail or "").strip()
    )


def _set_xml_mysql_supply_chain(root: ET.Element) -> None:
    _set_xml_reviewed_maven_licenses(root)
    connectors = _xml_mysql_connectors(root)
    if len(connectors) > 1:
        raise SbomError("Multiple MySQL Connector/J components are ambiguous")
    for connector in connectors:
        version = connector.findtext(_qname("version"))
        if version != MYSQL_CONNECTOR_VERSION:
            raise SbomError(
                f"Expected MySQL Connector/J {MYSQL_CONNECTOR_VERSION}, found {version}"
            )
        _set_xml_license_expression(connector, MYSQL_CONNECTOR_LICENSE_EXPRESSION)

    if not _xml_has_mysql_example(root):
        if _xml_mysql_containers(root):
            raise SbomError("Library-only BOM must not contain the MySQL test container")
        return
    if len(connectors) != 1:
        raise SbomError("MySQL example BOM must contain exactly one MySQL Connector/J component")
    containers = _xml_mysql_containers(root)
    expected_container = _xml_mysql_container()
    if not containers:
        components = root.find(_qname("components"))
        if components is None:
            raise SbomError("XML components element is missing")
        components.append(expected_container)
    elif len(containers) == 1:
        if not _xml_mysql_container_is_exact(containers[0]):
            raise SbomError("Existing MySQL container component conflicts with the pinned fixture")
    else:
        raise SbomError("Multiple MySQL container components are ambiguous")

    dependencies = root.find(_qname("dependencies"))
    if dependencies is None:
        raise SbomError("XML dependencies element is missing")
    mysql_examples = [
        component
        for component in _xml_first_party_components(root)
        if component.findtext(_qname("name")) in MYSQL_EXAMPLE_NAMES
    ]
    for mysql_example in mysql_examples:
        mysql_example_ref = mysql_example.get("bom-ref")
        if mysql_example_ref is None:
            raise SbomError("MySQL example component has no bom-ref")
        dependency_entries = [
            entry
            for entry in dependencies.findall(_qname("dependency"))
            if entry.get("ref") == mysql_example_ref
        ]
        if len(dependency_entries) != 1:
            raise SbomError("MySQL example must have exactly one dependency entry")
        references = {
            entry.get("ref")
            for entry in dependency_entries[0].findall(_qname("dependency"))
        }
        if MYSQL_CONTAINER_PURL not in references:
            ET.SubElement(
                dependency_entries[0],
                _qname("dependency"),
                {"ref": MYSQL_CONTAINER_PURL},
            )
    container_entries = [
        entry
        for entry in dependencies.findall(_qname("dependency"))
        if entry.get("ref") == MYSQL_CONTAINER_PURL
    ]
    if not container_entries:
        ET.SubElement(
            dependencies, _qname("dependency"), {"ref": MYSQL_CONTAINER_PURL}
        )
    elif (
        len(container_entries) != 1
        or list(container_entries[0])
        or (container_entries[0].text or "").strip()
    ):
        raise SbomError("MySQL container dependency record must be one empty leaf")


def _verify_xml_mysql_supply_chain(root: ET.Element) -> None:
    _verify_xml_reviewed_maven_licenses(root)
    connectors = _xml_mysql_connectors(root)
    if _xml_has_mysql_example(root) and len(connectors) != 1:
        raise SbomError("MySQL example BOM must contain exactly one MySQL Connector/J component")
    for connector in connectors:
        if connector.findtext(_qname("version")) != MYSQL_CONNECTOR_VERSION:
            raise SbomError("Unexpected MySQL Connector/J version")
        if not _xml_has_exact_license_expression(
            connector, MYSQL_CONNECTOR_LICENSE_EXPRESSION
        ):
            raise SbomError("MySQL Connector/J license exception is missing from XML")

    containers = _xml_mysql_containers(root)
    if not _xml_has_mysql_example(root):
        if containers:
            raise SbomError("Library-only BOM must not contain the MySQL test container")
        return
    if len(containers) != 1 or not _xml_mysql_container_is_exact(containers[0]):
        raise SbomError("Pinned MySQL container component is missing or incorrect in XML")

    dependencies = root.find(_qname("dependencies"))
    if dependencies is None:
        raise SbomError("XML dependencies element is missing")
    for mysql_example in (
        component
        for component in _xml_first_party_components(root)
        if component.findtext(_qname("name")) in MYSQL_EXAMPLE_NAMES
    ):
        mysql_example_ref = mysql_example.get("bom-ref")
        matching = [
            entry
            for entry in dependencies.findall(_qname("dependency"))
            if entry.get("ref") == mysql_example_ref
        ]
        if len(matching) != 1 or MYSQL_CONTAINER_PURL not in {
            entry.get("ref") for entry in matching[0].findall(_qname("dependency"))
        }:
            raise SbomError(
                "MySQL example dependency graph does not reference the pinned container"
            )
    container_entries = [
        entry
        for entry in dependencies.findall(_qname("dependency"))
        if entry.get("ref") == MYSQL_CONTAINER_PURL
    ]
    if len(container_entries) != 1 or list(container_entries[0]):
        raise SbomError("MySQL container dependency record must be one empty leaf")


def _xml_has_exact_component_license(component: ET.Element) -> bool:
    licenses = component.find(_qname("licenses"))
    if (
        licenses is None
        or licenses.attrib
        or (licenses.text or "").strip()
        or len(licenses) != 1
    ):
        return False
    license_element = licenses.find(_qname("license"))
    if (
        license_element is None
        or license_element.attrib
        or (license_element.text or "").strip()
        or (license_element.tail or "").strip()
        or [child.tag for child in license_element]
        != [_qname("id"), _qname("url")]
    ):
        return False
    identifier, url = list(license_element)
    return (
        not identifier.attrib
        and not url.attrib
        and len(identifier) == 0
        and len(url) == 0
        and identifier.text == LICENSE_ID
        and url.text == LICENSE_URL
        and not (identifier.tail or "").strip()
        and not (url.tail or "").strip()
    )


def _set_xml_component_license(component: ET.Element) -> None:
    licenses = component.find(_qname("licenses"))
    if licenses is not None:
        if not _xml_has_exact_component_license(component):
            raise SbomError(
                f"Refusing to replace a non-{LICENSE_ID} license on {_xml_identity(component)}"
            )
        return

    licenses = ET.Element(_qname("licenses"))
    insertion_before = {
        "copyright",
        "cpe",
        "purl",
        "omniborId",
        "swhid",
        "swid",
        "modified",
        "pedigree",
        "externalReferences",
        "properties",
        "components",
        "evidence",
        "releaseNotes",
        "modelCard",
        "data",
        "cryptoProperties",
        "tags",
    }
    insertion_index = len(component)
    for index, child in enumerate(component):
        if child.tag.removeprefix(f"{{{CYCLONEDX_XML_NAMESPACE}}}") in insertion_before:
            insertion_index = index
            break
    component.insert(insertion_index, licenses)
    license_element = ET.SubElement(licenses, _qname("license"))
    ET.SubElement(license_element, _qname("id")).text = LICENSE_ID
    ET.SubElement(license_element, _qname("url")).text = LICENSE_URL


def _load_xml(
    path: Path, *, add_missing_license: bool
) -> tuple[ET.ElementTree, set[tuple[object, object, object]], object]:
    tree = _parse_canonical_xml(path, "CycloneDX XML")
    root = tree.getroot()
    if root.tag != _qname("bom"):
        raise SbomError(f"Expected CycloneDX XML 1.6 in {path}")
    _validate_xml_document_profile(root)
    _validate_xml_pinned_example_dependency_contract(root)
    _xml_component_license_map(root)
    components = _xml_first_party_components(root)
    if not components:
        raise SbomError(f"No {FIRST_PARTY_GROUP} component found in {path}")
    if add_missing_license:
        for component in components:
            _set_xml_component_license(component)
        _set_xml_mysql_supply_chain(root)
    identities = {_xml_identity(component) for component in components}
    return tree, identities, root.get("serialNumber")


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _atomic_write_xml(path: Path, tree: ET.ElementTree) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.register_namespace("", CYCLONEDX_XML_NAMESPACE)
    ET.indent(tree, space="  ")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            tree.write(output, encoding="utf-8", xml_declaration=True, short_empty_elements=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _verify_pair(json_path: Path, xml_path: Path) -> set[tuple[object, object, object]]:
    json_document, json_identities, json_serial = _load_json(
        json_path, add_missing_license=False
    )
    xml_tree, xml_identities, xml_serial = _load_xml(xml_path, add_missing_license=False)
    if json_identities != xml_identities:
        raise SbomError(
            f"JSON/XML first-party component mismatch: {json_identities} != {xml_identities}"
        )
    if json_serial != xml_serial:
        raise SbomError(f"JSON/XML serial number mismatch: {json_serial!r} != {xml_serial!r}")
    if not _json_has_exact_document_license(json_document):
        raise SbomError(f"JSON document license assertion failed: {json_path}")
    if not _xml_has_exact_document_license(xml_tree.getroot()):
        raise SbomError(f"XML document license assertion failed: {xml_path}")
    json_overrides = _json_license_override_coordinates(json_document)
    xml_overrides = _xml_license_override_coordinates(xml_tree.getroot())
    if json_overrides != xml_overrides:
        raise SbomError(
            "JSON/XML reviewed Maven component mismatch: "
            f"{json_overrides} != {xml_overrides}"
        )
    _verify_semantic_pair(json_document, xml_tree.getroot(), "Verified pair")
    if any(not _json_has_exact_component_license(component)
           for component in _json_first_party_components(json_document)):
        raise SbomError(f"JSON component license assertion failed: {json_path}")
    if any(not _xml_has_exact_component_license(component)
           for component in _xml_first_party_components(xml_tree.getroot())):
        raise SbomError(f"XML component license assertion failed: {xml_path}")
    _verify_json_mysql_supply_chain(json_document)
    _verify_xml_mysql_supply_chain(xml_tree.getroot())
    return json_identities


def _finalize_pair(source_json: Path, source_xml: Path, output_json: Path, output_xml: Path) -> None:
    json_document, json_identities, json_serial = _load_json(
        source_json, add_missing_license=True
    )
    xml_tree, xml_identities, xml_serial = _load_xml(source_xml, add_missing_license=True)
    if json_identities != xml_identities:
        raise SbomError(
            f"Source JSON/XML first-party component mismatch: {json_identities} != {xml_identities}"
        )
    if json_serial != xml_serial:
        raise SbomError(f"Source JSON/XML serial number mismatch: {json_serial!r} != {xml_serial!r}")
    json_overrides = _json_license_override_coordinates(json_document)
    xml_overrides = _xml_license_override_coordinates(xml_tree.getroot())
    if json_overrides != xml_overrides:
        raise SbomError(
            "Source JSON/XML reviewed Maven component mismatch: "
            f"{json_overrides} != {xml_overrides}"
        )
    _verify_semantic_pair(json_document, xml_tree.getroot(), "Finalized source pair")
    _atomic_write_text(output_json, json.dumps(json_document, indent=2, ensure_ascii=False) + "\n")
    _atomic_write_xml(output_xml, xml_tree)
    verified = _verify_pair(output_json, output_xml)
    print(f"Verified {LICENSE_ID} component metadata for {len(verified)} first-party component(s): {output_json}")


def _validate_pair_collection(pairs: list[tuple[Path, Path]]) -> None:
    if len(pairs) == 1:
        return
    if len(pairs) != 6:
        raise SbomError(
            "A multi-pair release verification must contain exactly aggregate, "
            "core, adapter553, adapter552, mysql553, and mysql552 pairs"
        )
    documents: dict[str, dict[str, object]] = {}
    versions: set[object] = set()
    for json_path, _ in pairs:
        document, _, _ = _load_json(json_path, add_missing_license=False)
        metadata = document["metadata"]
        if not isinstance(metadata, dict) or not isinstance(metadata.get("component"), dict):
            raise SbomError("Release pair metadata.component is missing")
        role = metadata["component"].get("name")
        if not isinstance(role, str) or role in documents:
            raise SbomError(f"Release pair repeats or has an invalid root role: {role}")
        documents[role] = document
        versions.add(metadata["component"].get("version"))
    if set(documents) != set(EXPECTED_FIRST_PARTY_CHILDREN):
        raise SbomError(
            f"Release pair root roles differ: {set(documents)} != "
            f"{set(EXPECTED_FIRST_PARTY_CHILDREN)}"
        )
    if len(versions) != 1:
        raise SbomError("Release pairs must share one project version")

    roots_and_records = {
        role: _json_all_component_records(document, role)
        for role, document in documents.items()
    }
    graphs = {
        role: _json_dependency_graph(document, role)
        for role, document in documents.items()
    }
    version = next(iter(versions))

    def purl(name: str) -> str:
        project_path = "" if name == AGGREGATE_ROOT_NAME else name
        return (
            f"pkg:maven/{FIRST_PARTY_GROUP}/{name}@{version}"
            f"?project_path=%3A{project_path}"
        )

    def module_fingerprint(record: dict[str, object]) -> tuple[object, ...]:
        # ``externalReferences`` and the producer's cdx:maven:package:test
        # property are role-context metadata: roots carry the VCS URL while
        # child records carry the dependency scope. Every release-identity and
        # content-bearing field must otherwise agree across all occurrences.
        return (
            record.get("bom-ref"),
            record.get("description"),
            record.get("type"),
            record.get("group"),
            record.get("name"),
            record.get("version"),
            record.get("purl"),
            record.get("hashes"),
            record.get("licenses"),
            record.get("modified"),
            record.get("publisher"),
            record.get("scope"),
        )

    for module_name in EXPECTED_FIRST_PARTY_CHILDREN:
        module_purl = purl(module_name)
        expected_roles = {
            role
            for role, children in EXPECTED_FIRST_PARTY_CHILDREN.items()
            if module_name == role or module_name in children
        }
        observed_records = {
            role: records[module_purl]
            for role, (_, records) in roots_and_records.items()
            if module_purl in records
        }
        if set(observed_records) != expected_roles:
            raise SbomError(
                f"Release pair occurrences for {module_name} differ: "
                f"{set(observed_records)} != {expected_roles}"
            )
        fingerprints = {
            module_fingerprint(record) for record in observed_records.values()
        }
        if len(fingerprints) != 1:
            raise SbomError(
                "Release pair first-party module records differ across roles: "
                f"{module_name}"
            )

    all_first_party_purls = {
        name: purl(name) for name in EXPECTED_FIRST_PARTY_CHILDREN
    }
    first_party_name_by_purl = {
        module_purl: name for name, module_purl in all_first_party_purls.items()
    }
    for role, (root_ref, records) in roots_and_records.items():
        graph = graphs[role]
        reachable: set[str] = set()
        pending = [root_ref]
        while pending:
            ref = pending.pop()
            if ref in reachable:
                continue
            reachable.add(ref)
            pending.extend(
                target
                for target in graph[ref]
                if target in first_party_name_by_purl
            )
        observed_names = {
            first_party_name_by_purl[ref]
            for ref in reachable
            if ref in first_party_name_by_purl
        }
        expected_names = {role, *EXPECTED_FIRST_PARTY_CHILDREN[role]}
        if observed_names != expected_names:
            raise SbomError(
                f"Release pair first-party reachability for {role} differs: "
                f"{observed_names} != {expected_names}"
            )
        if any(
            ref in first_party_name_by_purl
            and first_party_name_by_purl[ref] not in expected_names
            for ref in records
        ):
            raise SbomError(
                f"Release pair first-party record coverage for {role} is ambiguous"
            )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--first-party-group",
        required=True,
        help="exact Maven group assigned to RouteContract first-party components",
    )
    parser.add_argument(
        "--pair",
        action="append",
        nargs=4,
        metavar=("SOURCE_JSON", "SOURCE_XML", "OUTPUT_JSON", "OUTPUT_XML"),
        default=[],
        help="copy, finalize and verify one JSON/XML BOM pair",
    )
    parser.add_argument(
        "--verify-pair",
        action="append",
        nargs=2,
        metavar=("JSON", "XML"),
        default=[],
        help="assert an already-finalized JSON/XML BOM pair without writing",
    )
    arguments = parser.parse_args()
    if not arguments.pair and not arguments.verify_pair:
        parser.error("at least one --pair or --verify-pair is required")
    return arguments


def main() -> int:
    arguments = _parse_args()
    if re.fullmatch(r"io\.github\.[A-Za-z0-9-]+\.routecontract", arguments.first_party_group) is None:
        print("SBOM verification failed: invalid first-party Maven group", file=sys.stderr)
        return 1
    global FIRST_PARTY_GROUP
    FIRST_PARTY_GROUP = arguments.first_party_group
    try:
        verified_pairs: list[tuple[Path, Path]] = []
        for values in arguments.pair:
            source_json, source_xml, output_json, output_xml = (
                Path(value) for value in values
            )
            _finalize_pair(source_json, source_xml, output_json, output_xml)
            verified_pairs.append((output_json, output_xml))
        for json_value, xml_value in arguments.verify_pair:
            json_path = Path(json_value)
            xml_path = Path(xml_value)
            identities = _verify_pair(json_path, xml_path)
            verified_pairs.append((json_path, xml_path))
            print(
                f"Asserted {LICENSE_ID} component metadata for {len(identities)} "
                f"first-party component(s): {json_value}"
            )
        _validate_pair_collection(verified_pairs)
    except SbomError as error:
        print(f"SBOM verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
