#!/usr/bin/env python3
"""Finalize and verify RouteContract CycloneDX JSON/XML release metadata.

CycloneDX Gradle plugin 3.4.0's ``licenseChoice`` task property writes the BOM
document license at ``metadata.licenses``. It does not populate the distinct
``licenses`` field on ``metadata.component``. This script keeps the plugin
output as its source of dependency truth, copies it to a verified output, and
adds first-party licenses plus the exact Connector/J and pinned MySQL fixture
metadata that the dependency-only plugin output cannot fully represent.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
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
MYSQL_EXAMPLE_NAME = "mysql-example"
MYSQL_CONTAINER_NAME = "mysql"
MYSQL_CONTAINER_VERSION = "8.4.11"
MYSQL_CONTAINER_DIGEST = (
    "b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb"
)
MYSQL_CONTAINER_PURL = (
    "pkg:oci/mysql@sha256%3A"
    f"{MYSQL_CONTAINER_DIGEST}?repository_url=registry-1.docker.io&tag=8.4.11"
)
MYSQL_CONTAINER_LICENSE_ID = "GPL-2.0-only"
MYSQL_CONTAINER_USAGE_PROPERTY = "routecontract:usage"
MYSQL_CONTAINER_USAGE_VALUE = "test-only"


class SbomError(ValueError):
    """Raised when an SBOM cannot be finalized without ambiguity."""


def _json_identity(component: dict[str, object]) -> tuple[object, object, object]:
    return component.get("group"), component.get("name"), component.get("version")


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
    components = document.get("components", [])
    if not isinstance(components, list) or any(not isinstance(component, dict) for component in components):
        raise SbomError("JSON components must contain only objects")
    return components


def _json_has_mysql_example(document: dict[str, object]) -> bool:
    return any(
        component.get("name") == MYSQL_EXAMPLE_NAME
        for component in _json_first_party_components(document)
    )


def _json_mysql_connectors(document: dict[str, object]) -> list[dict[str, object]]:
    return [
        component
        for component in _json_components(document)
        if component.get("group") == MYSQL_CONNECTOR_GROUP
        and component.get("name") == MYSQL_CONNECTOR_NAME
    ]


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


def _json_mysql_container() -> dict[str, object]:
    return {
        "type": "container",
        "bom-ref": MYSQL_CONTAINER_PURL,
        "name": MYSQL_CONTAINER_NAME,
        "version": MYSQL_CONTAINER_VERSION,
        "scope": "excluded",
        "hashes": [{"alg": "SHA-256", "content": MYSQL_CONTAINER_DIGEST}],
        "licenses": [{"license": {"id": MYSQL_CONTAINER_LICENSE_ID}}],
        "purl": MYSQL_CONTAINER_PURL,
        "properties": [
            {
                "name": MYSQL_CONTAINER_USAGE_PROPERTY,
                "value": MYSQL_CONTAINER_USAGE_VALUE,
            }
        ],
    }


def _set_json_mysql_supply_chain(document: dict[str, object]) -> None:
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

    mysql_example = next(
        component
        for component in _json_first_party_components(document)
        if component.get("name") == MYSQL_EXAMPLE_NAME
    )
    mysql_example_ref = mysql_example.get("bom-ref")
    if not isinstance(mysql_example_ref, str):
        raise SbomError("MySQL example component has no bom-ref")
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, list):
        raise SbomError("JSON dependencies must be an array")
    dependency_entries = [entry for entry in dependencies if isinstance(entry, dict) and entry.get("ref") == mysql_example_ref]
    if len(dependency_entries) != 1:
        raise SbomError("MySQL example must have exactly one dependency entry")
    depends_on = dependency_entries[0].setdefault("dependsOn", [])
    if not isinstance(depends_on, list) or any(not isinstance(value, str) for value in depends_on):
        raise SbomError("MySQL example dependsOn must be an array of references")
    if MYSQL_CONTAINER_PURL not in depends_on:
        depends_on.append(MYSQL_CONTAINER_PURL)
        depends_on.sort()


def _verify_json_mysql_supply_chain(document: dict[str, object]) -> None:
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

    mysql_example_ref = next(
        component.get("bom-ref")
        for component in _json_first_party_components(document)
        if component.get("name") == MYSQL_EXAMPLE_NAME
    )
    dependencies = document.get("dependencies", [])
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
        raise SbomError("MySQL example dependency graph does not reference the pinned container")


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
        and license_value.get("id") == LICENSE_ID
        and license_value.get("url") == LICENSE_URL
    )


def _load_json(
    path: Path, *, add_missing_license: bool
) -> tuple[dict[str, object], set[tuple[object, object, object]], object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SbomError(f"Cannot read CycloneDX JSON {path}: {error}") from error
    if not isinstance(document, dict) or document.get("bomFormat") != "CycloneDX":
        raise SbomError(f"Not a CycloneDX JSON BOM: {path}")
    if document.get("specVersion") != "1.6":
        raise SbomError(f"Expected CycloneDX JSON 1.6 in {path}")
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


def _xml_identity(component: ET.Element) -> tuple[object, object, object]:
    return (
        component.findtext(_qname("group")),
        component.findtext(_qname("name")),
        component.findtext(_qname("version")),
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
    components = root.find(_qname("components"))
    if components is None:
        raise SbomError("XML components element is missing")
    return components.findall(_qname("component"))


def _xml_has_mysql_example(root: ET.Element) -> bool:
    return any(
        component.findtext(_qname("name")) == MYSQL_EXAMPLE_NAME
        for component in _xml_first_party_components(root)
    )


def _xml_mysql_connectors(root: ET.Element) -> list[ET.Element]:
    return [
        component
        for component in _xml_components(root)
        if component.findtext(_qname("group")) == MYSQL_CONNECTOR_GROUP
        and component.findtext(_qname("name")) == MYSQL_CONNECTOR_NAME
    ]


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


def _xml_mysql_container() -> ET.Element:
    component = ET.Element(
        _qname("component"), {"type": "container", "bom-ref": MYSQL_CONTAINER_PURL}
    )
    ET.SubElement(component, _qname("name")).text = MYSQL_CONTAINER_NAME
    ET.SubElement(component, _qname("version")).text = MYSQL_CONTAINER_VERSION
    ET.SubElement(component, _qname("scope")).text = "excluded"
    hashes = ET.SubElement(component, _qname("hashes"))
    ET.SubElement(hashes, _qname("hash"), {"alg": "SHA-256"}).text = MYSQL_CONTAINER_DIGEST
    licenses = ET.SubElement(component, _qname("licenses"))
    license_element = ET.SubElement(licenses, _qname("license"))
    ET.SubElement(license_element, _qname("id")).text = MYSQL_CONTAINER_LICENSE_ID
    ET.SubElement(component, _qname("purl")).text = MYSQL_CONTAINER_PURL
    properties = ET.SubElement(component, _qname("properties"))
    ET.SubElement(
        properties, _qname("property"), {"name": MYSQL_CONTAINER_USAGE_PROPERTY}
    ).text = MYSQL_CONTAINER_USAGE_VALUE
    return component


def _xml_mysql_container_is_exact(component: ET.Element) -> bool:
    if component.attrib != {"type": "container", "bom-ref": MYSQL_CONTAINER_PURL}:
        return False
    if [child.tag for child in component] != [
        _qname("name"),
        _qname("version"),
        _qname("scope"),
        _qname("hashes"),
        _qname("licenses"),
        _qname("purl"),
        _qname("properties"),
    ]:
        return False
    if component.findtext(_qname("name")) != MYSQL_CONTAINER_NAME:
        return False
    if component.findtext(_qname("version")) != MYSQL_CONTAINER_VERSION:
        return False
    if component.findtext(_qname("scope")) != "excluded":
        return False
    if component.findtext(_qname("purl")) != MYSQL_CONTAINER_PURL:
        return False

    hashes = component.find(_qname("hashes"))
    hash_elements = [] if hashes is None else list(hashes)
    if (
        len(hash_elements) != 1
        or hash_elements[0].tag != _qname("hash")
        or hash_elements[0].attrib != {"alg": "SHA-256"}
        or hash_elements[0].text != MYSQL_CONTAINER_DIGEST
    ):
        return False

    licenses = component.find(_qname("licenses"))
    license_elements = [] if licenses is None else list(licenses)
    if len(license_elements) != 1 or license_elements[0].tag != _qname("license"):
        return False
    license_children = list(license_elements[0])
    if (
        license_elements[0].attrib
        or len(license_children) != 1
        or license_children[0].tag != _qname("id")
        or license_children[0].attrib
        or license_children[0].text != MYSQL_CONTAINER_LICENSE_ID
    ):
        return False

    properties = component.find(_qname("properties"))
    property_elements = [] if properties is None else list(properties)
    return (
        len(property_elements) == 1
        and property_elements[0].tag == _qname("property")
        and property_elements[0].attrib == {"name": MYSQL_CONTAINER_USAGE_PROPERTY}
        and property_elements[0].text == MYSQL_CONTAINER_USAGE_VALUE
    )


def _set_xml_mysql_supply_chain(root: ET.Element) -> None:
    connectors = _xml_mysql_connectors(root)
    if len(connectors) > 1:
        raise SbomError("Multiple MySQL Connector/J components are ambiguous")
    for connector in connectors:
        version = connector.findtext(_qname("version"))
        if version != MYSQL_CONNECTOR_VERSION:
            raise SbomError(
                f"Expected MySQL Connector/J {MYSQL_CONNECTOR_VERSION}, found {version}"
            )
        licenses = connector.find(_qname("licenses"))
        if licenses is None:
            licenses = ET.Element(_qname("licenses"))
            purl = connector.find(_qname("purl"))
            connector.insert(list(connector).index(purl) if purl is not None else len(connector), licenses)
        else:
            licenses.clear()
        ET.SubElement(licenses, _qname("expression")).text = MYSQL_CONNECTOR_LICENSE_EXPRESSION

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

    mysql_example = next(
        component
        for component in _xml_first_party_components(root)
        if component.findtext(_qname("name")) == MYSQL_EXAMPLE_NAME
    )
    mysql_example_ref = mysql_example.get("bom-ref")
    if mysql_example_ref is None:
        raise SbomError("MySQL example component has no bom-ref")
    dependencies = root.find(_qname("dependencies"))
    if dependencies is None:
        raise SbomError("XML dependencies element is missing")
    dependency_entries = [
        entry
        for entry in dependencies.findall(_qname("dependency"))
        if entry.get("ref") == mysql_example_ref
    ]
    if len(dependency_entries) != 1:
        raise SbomError("MySQL example must have exactly one dependency entry")
    references = {entry.get("ref") for entry in dependency_entries[0].findall(_qname("dependency"))}
    if MYSQL_CONTAINER_PURL not in references:
        ET.SubElement(
            dependency_entries[0], _qname("dependency"), {"ref": MYSQL_CONTAINER_PURL}
        )


def _verify_xml_mysql_supply_chain(root: ET.Element) -> None:
    connectors = _xml_mysql_connectors(root)
    if _xml_has_mysql_example(root) and len(connectors) != 1:
        raise SbomError("MySQL example BOM must contain exactly one MySQL Connector/J component")
    for connector in connectors:
        if connector.findtext(_qname("version")) != MYSQL_CONNECTOR_VERSION:
            raise SbomError("Unexpected MySQL Connector/J version")
        licenses = connector.find(_qname("licenses"))
        if (
            licenses is None
            or len(licenses) != 1
            or licenses.findtext(_qname("expression")) != MYSQL_CONNECTOR_LICENSE_EXPRESSION
        ):
            raise SbomError("MySQL Connector/J license exception is missing from XML")

    containers = _xml_mysql_containers(root)
    if not _xml_has_mysql_example(root):
        if containers:
            raise SbomError("Library-only BOM must not contain the MySQL test container")
        return
    if len(containers) != 1 or not _xml_mysql_container_is_exact(containers[0]):
        raise SbomError("Pinned MySQL container component is missing or incorrect in XML")

    mysql_example_ref = next(
        component.get("bom-ref")
        for component in _xml_first_party_components(root)
        if component.findtext(_qname("name")) == MYSQL_EXAMPLE_NAME
    )
    dependencies = root.find(_qname("dependencies"))
    if dependencies is None:
        raise SbomError("XML dependencies element is missing")
    matching = [
        entry
        for entry in dependencies.findall(_qname("dependency"))
        if entry.get("ref") == mysql_example_ref
    ]
    if len(matching) != 1 or MYSQL_CONTAINER_PURL not in {
        entry.get("ref") for entry in matching[0].findall(_qname("dependency"))
    }:
        raise SbomError("MySQL example dependency graph does not reference the pinned container")


def _xml_has_exact_component_license(component: ET.Element) -> bool:
    licenses = component.find(_qname("licenses"))
    if licenses is None or len(licenses) != 1:
        return False
    license_element = licenses.find(_qname("license"))
    if license_element is None or len(license_element) != 2:
        return False
    return (
        license_element.findtext(_qname("id")) == LICENSE_ID
        and license_element.findtext(_qname("url")) == LICENSE_URL
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
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError) as error:
        raise SbomError(f"Cannot read CycloneDX XML {path}: {error}") from error
    root = tree.getroot()
    if root.tag != _qname("bom"):
        raise SbomError(f"Expected CycloneDX XML 1.6 in {path}")
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
    _atomic_write_text(output_json, json.dumps(json_document, indent=2, ensure_ascii=False) + "\n")
    _atomic_write_xml(output_xml, xml_tree)
    verified = _verify_pair(output_json, output_xml)
    print(f"Verified {LICENSE_ID} component metadata for {len(verified)} first-party component(s): {output_json}")


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
        for values in arguments.pair:
            _finalize_pair(*(Path(value) for value in values))
        for json_value, xml_value in arguments.verify_pair:
            identities = _verify_pair(Path(json_value), Path(xml_value))
            print(
                f"Asserted {LICENSE_ID} component metadata for {len(identities)} "
                f"first-party component(s): {json_value}"
            )
    except SbomError as error:
        print(f"SBOM verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
