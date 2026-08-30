#!/usr/bin/env python3
"""Validate the exact Gradle Kotlin pilot runtime provenance artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat


COORDINATE = (
    "io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0"
)
JAR_SHA256 = "d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc"
POM_SHA256 = "05570bfa238ef77db255a46efdd5bbb25e994ae0137db86491a46a25e28deac9"
DIGEST = re.compile(r"[0-9a-f]{64}")
COORDINATE_PATH = Path(
    "io/github/ym0506/routecontract/routecontract-shardingsphere-5.5/0.1.0"
)


class ProvenanceError(RuntimeError):
    """An exact provenance contract failure."""


def exact_keys(value: object, expected: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ProvenanceError(f"{label} must have exact keys {sorted(expected)}")
    return value


def regular_real_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ProvenanceError(f"{label} must be a non-empty path string")
    path = Path(value)
    if not path.is_absolute():
        raise ProvenanceError(f"{label} must be absolute")
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise ProvenanceError(f"{label} does not exist: {path}") from error
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ProvenanceError(f"{label} must be one regular non-symlink file")
    real = path.resolve(strict=True)
    if real != path:
        raise ProvenanceError(f"{label} must have no symlink path component")
    return real


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise ProvenanceError("provenance must be a regular non-symlink file")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProvenanceError(f"provenance is not exact UTF-8 JSON: {error}") from error
    root = exact_keys(
        document,
        {
            "schemaVersion",
            "coordinate",
            "resolvedComponent",
            "repositoryRoot",
            "jar",
            "pom",
            "origins",
            "claimBoundary",
        },
        "provenance",
    )
    if root["schemaVersion"] != 1:
        raise ProvenanceError("schemaVersion must be exactly 1")
    if root["coordinate"] != COORDINATE or root["resolvedComponent"] != COORDINATE:
        raise ProvenanceError("requested and selected RouteContract GAV must both be exact")

    repository_text = root["repositoryRoot"]
    if not isinstance(repository_text, str) or not repository_text:
        raise ProvenanceError("repositoryRoot must be a non-empty path string")
    repository = Path(repository_text)
    if not repository.is_absolute() or repository.is_symlink() or not repository.is_dir():
        raise ProvenanceError("repositoryRoot must be an absolute real directory")
    repository = repository.resolve(strict=True)
    if repository != Path(repository_text):
        raise ProvenanceError("repositoryRoot must have no symlink path component")

    jar_entry = exact_keys(root["jar"], {"path", "sha256"}, "jar")
    pom_entry = exact_keys(root["pom"], {"path", "sha256"}, "pom")
    jar = regular_real_path(jar_entry["path"], "jar.path")
    pom = regular_real_path(pom_entry["path"], "pom.path")
    expected_directory = repository / COORDINATE_PATH
    if jar != expected_directory / "routecontract-shardingsphere-5.5-0.1.0.jar":
        raise ProvenanceError("jar.path is not the canonical coordinate path")
    if pom != expected_directory / "routecontract-shardingsphere-5.5-0.1.0.pom":
        raise ProvenanceError("pom.path is not the canonical coordinate path")
    for entry, expected, actual, label in (
        (jar_entry, JAR_SHA256, sha256(jar), "jar"),
        (pom_entry, POM_SHA256, sha256(pom), "pom"),
    ):
        declared = entry["sha256"]
        if not isinstance(declared, str) or DIGEST.fullmatch(declared) is None:
            raise ProvenanceError(f"{label}.sha256 must be 64 lowercase hex characters")
        if declared != expected or actual != expected:
            raise ProvenanceError(f"{label} SHA-256 is not the exact expected value")

    origins = exact_keys(
        root["origins"],
        {
            "routeContractClass",
            "providerClass",
            "serviceDescriptorCount",
            "serviceDescriptorJars",
        },
        "origins",
    )
    if origins["routeContractClass"] != str(jar) or origins["providerClass"] != str(jar):
        raise ProvenanceError("API and provider origins must both be the exact coordinate JAR")
    if origins["serviceDescriptorCount"] != 1 or origins["serviceDescriptorJars"] != [str(jar)]:
        raise ProvenanceError("exactly one matching SPI descriptor must originate in the JAR")

    claim = exact_keys(
        root["claimBoundary"],
        {
            "dependencyVerification",
            "externalUser",
            "humanApprovedBaseline",
            "adoption",
        },
        "claimBoundary",
    )
    if claim != {
        "dependencyVerification": "selected-invariant-graph-only",
        "externalUser": False,
        "humanApprovedBaseline": False,
        "adoption": False,
    }:
        raise ProvenanceError("claimBoundary must preserve the exact non-adoption boundary")
    return root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("provenance", type=Path)
    args = parser.parse_args()
    try:
        validate(args.provenance)
    except (OSError, ProvenanceError) as error:
        print(f"ROUTECONTRACT_GRADLE_PROVENANCE_ERROR {error}")
        return 2
    print(
        "ROUTECONTRACT_GRADLE_PROVENANCE "
        f"coordinate={COORDINATE} jarSha256={JAR_SHA256} "
        f"pomSha256={POM_SHA256} origins=EXACT claim=SELECTED_INVARIANTS_ONLY"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
