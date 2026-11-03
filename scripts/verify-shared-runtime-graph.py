#!/usr/bin/env python3
"""Require a second RouteContract artifact to publish exactly the reference artifact's runtime graph.

The release supply-chain evidence (SBOM, policy and OSV scan) is produced for the reference
artifact. A second artifact may reuse that evidence only if everything a consumer resolves from it
is identical: the POM dependencies, the Gradle Module Metadata variant dependencies and the locked
runtimeClasspath. Compile-only API jars are not published and are not compared.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


POM_NAMESPACE = "{http://maven.apache.org/POM/4.0.0}"
MAX_INPUT_SIZE = 4 * 1024 * 1024


class GraphError(ValueError):
    """Raised when the two published runtime graphs are not provably identical."""


def _read(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise GraphError(f"{label} must be a regular file")
    data = path.read_bytes()
    if not data or len(data) > MAX_INPUT_SIZE:
        raise GraphError(f"{label} has an unexpected size")
    return data


def pom_dependencies(path: Path, label: str) -> list[tuple[str, ...]]:
    root = ET.fromstring(_read(path, label))
    if root.tag != f"{POM_NAMESPACE}project":
        raise GraphError(f"{label} is not a Maven POM")
    if root.find(f"{POM_NAMESPACE}dependencyManagement") is not None:
        raise GraphError(f"{label} must not declare dependencyManagement")
    result = []
    for dependency in root.findall(f"{POM_NAMESPACE}dependencies/{POM_NAMESPACE}dependency"):
        fields = []
        for name in ("groupId", "artifactId", "version", "scope", "type", "classifier", "optional"):
            fields.append((dependency.findtext(f"{POM_NAMESPACE}{name}") or "").strip())
        if dependency.find(f"{POM_NAMESPACE}exclusions") is not None:
            raise GraphError(f"{label} dependency exclusions are not supported by this check")
        result.append(tuple(fields))
    return sorted(result)


def module_dependencies(path: Path, label: str) -> dict[str, list[str]]:
    try:
        document = json.loads(_read(path, label))
    except json.JSONDecodeError as error:
        raise GraphError(f"{label} is not JSON") from error
    variants = document.get("variants")
    if not isinstance(variants, list) or not variants:
        raise GraphError(f"{label} has no variants")
    result: dict[str, list[str]] = {}
    for variant in variants:
        name = variant.get("name")
        if not isinstance(name, str) or name in result:
            raise GraphError(f"{label} has an invalid or repeated variant")
        entries = []
        for key in ("dependencies", "dependencyConstraints"):
            for dependency in variant.get(key, []):
                entries.append(json.dumps({"kind": key, **dependency}, sort_keys=True))
        result[name] = sorted(entries)
    return result


def locked_runtime_classpath(path: Path, label: str) -> list[str]:
    result = []
    for line in _read(path, label).decode("utf-8").splitlines():
        if not line or line.startswith("#") or line.startswith("empty="):
            continue
        coordinate, separator, configurations = line.partition("=")
        if not separator or coordinate.count(":") != 2:
            raise GraphError(f"{label} has a malformed lock line")
        if "runtimeClasspath" in configurations.split(","):
            result.append(coordinate)
    if not result:
        raise GraphError(f"{label} locks no runtimeClasspath dependency")
    return sorted(result)


def compare(reference: dict[str, Path], candidate: dict[str, Path]) -> int:
    checks = (
        ("POM dependencies", pom_dependencies, "pom"),
        ("Gradle Module Metadata variant dependencies", module_dependencies, "module"),
        ("locked runtimeClasspath", locked_runtime_classpath, "lock"),
    )
    for label, read, key in checks:
        expected = read(reference[key], f"reference {key}")
        actual = read(candidate[key], f"candidate {key}")
        if expected != actual:
            raise GraphError(f"{label} differ: reference={expected!r}, candidate={actual!r}")
    return len(locked_runtime_classpath(candidate["lock"], "candidate lock"))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    for role in ("reference", "candidate"):
        parser.add_argument(f"--{role}-pom", type=Path, required=True)
        parser.add_argument(f"--{role}-module", type=Path, required=True)
        parser.add_argument(f"--{role}-lock", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = _parse_args(sys.argv[1:] if argv is None else argv)
    roles = {
        role: {
            "pom": getattr(arguments, f"{role}_pom"),
            "module": getattr(arguments, f"{role}_module"),
            "lock": getattr(arguments, f"{role}_lock"),
        }
        for role in ("reference", "candidate")
    }
    try:
        count = compare(roles["reference"], roles["candidate"])
    except (GraphError, ET.ParseError, UnicodeDecodeError) as error:
        print(f"shared runtime graph verification failed: {error}", file=sys.stderr)
        return 1
    print(f"verified identical published runtime graph: {count} locked runtime dependencies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
