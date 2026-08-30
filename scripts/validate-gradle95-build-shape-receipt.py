#!/usr/bin/env python3
"""Strictly validate a path-free Gradle 9.5.1 build-shape receipt."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}\Z")
GIT_OBJECT = re.compile(r"[0-9a-f]{40}\Z")
MAX_BYTES = 64 * 1024


class ReceiptError(ValueError):
    """The receipt does not match the exact reviewed schema and claim boundary."""


def exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ReceiptError(
            f"{label} keys differ: missing={sorted(expected - set(value))}, "
            f"unexpected={sorted(set(value) - expected)}"
        )


def exact_mapping(value: Any, expected: dict[str, Any], label: str) -> None:
    if not isinstance(value, dict):
        raise ReceiptError(f"{label} must be an object")
    exact_keys(value, set(expected), label)
    for key, expected_value in expected.items():
        actual = value[key]
        if type(actual) is not type(expected_value) or actual != expected_value:
            raise ReceiptError(f"{label}.{key} must be exactly {expected_value!r}")


def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise ReceiptError(f"{label} must be one lowercase SHA-256")
    return value


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReceiptError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def validate(receipt: Any) -> None:
    if not isinstance(receipt, dict):
        raise ReceiptError("receipt root must be an object")
    exact_keys(
        receipt,
        {
            "schemaVersion",
            "kind",
            "result",
            "scope",
            "sourceRevision",
            "sourceTree",
            "sourceClean",
            "gradle",
            "toolchains",
            "bootBomCells",
            "pilotGraphSha256",
            "artifact",
            "targetGraphUnchangedWhenPilotEnabled",
            "routeContractAbsentFromTargetGraph",
            "isolation",
            "externalTarget",
            "externalRepositoryExecuted",
            "adoptionClaim",
            "springBootRuntimeCompatibilityClaim",
            "springBootStarterCompatibilityClaim",
            "representativeDatabaseOperationExecuted",
            "baselineApproved",
            "candidateChecked",
        },
        "receipt",
    )
    exact_scalars = {
        "schemaVersion": 1,
        "kind": "routecontract-gradle95-build-shape-receipt",
        "result": "PASS",
        "scope": "dependency-management-build-shape-only",
        "sourceClean": True,
        "targetGraphUnchangedWhenPilotEnabled": True,
        "routeContractAbsentFromTargetGraph": True,
        "externalTarget": False,
        "externalRepositoryExecuted": False,
        "adoptionClaim": False,
        "springBootRuntimeCompatibilityClaim": False,
        "springBootStarterCompatibilityClaim": False,
        "representativeDatabaseOperationExecuted": False,
        "baselineApproved": False,
        "candidateChecked": False,
    }
    for key, expected in exact_scalars.items():
        if type(receipt[key]) is not type(expected) or receipt[key] != expected:
            raise ReceiptError(f"{key} must be exactly {expected!r}")
    for key in ("sourceRevision", "sourceTree"):
        if not isinstance(receipt[key], str) or GIT_OBJECT.fullmatch(receipt[key]) is None:
            raise ReceiptError(f"{key} must be one lowercase Git object ID")
    repository_root = Path(__file__).resolve().parents[1]
    try:
        actual_revision = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
        actual_tree = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD^{tree}"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        raise ReceiptError("validator must run from its Git source checkout") from error
    if receipt["sourceRevision"] != actual_revision:
        raise ReceiptError("sourceRevision does not match this checkout HEAD")
    if receipt["sourceTree"] != actual_tree:
        raise ReceiptError("sourceTree does not match this checkout HEAD tree")

    gradle = receipt["gradle"]
    exact_mapping(gradle, {
        "version": "9.5.1",
        "distributionSha256": (
            "bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f"
        ),
        "wrapperJarSha256": (
            "497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7"
        ),
        "runtimeJdkFeature": 21,
    }, "gradle")

    toolchains = receipt["toolchains"]
    expected_toolchains = {
        "mainCompiler": 21,
        "mainBytecodeRelease": 17,
        "targetTestLauncher": 21,
        "pilotCompiler": 17,
        "pilotBytecodeRelease": 17,
        "pilotTestLauncher": 17,
        "measuredMainClassMajor": 61,
        "measuredPilotClassMajor": 61,
    }
    exact_mapping(toolchains, expected_toolchains, "toolchains")

    cells = receipt["bootBomCells"]
    if not isinstance(cells, dict):
        raise ReceiptError("bootBomCells must be an object")
    exact_keys(cells, {"3.5.16", "4.1.0"}, "bootBomCells")
    target_digests: list[str] = []
    for version in ("3.5.16", "4.1.0"):
        cell = cells[version]
        if not isinstance(cell, dict):
            raise ReceiptError(f"Boot BOM {version} cell must be an object")
        exact_keys(cell, {"targetGraphSha256"}, f"Boot BOM {version} cell")
        target_digests.append(
            require_digest(cell["targetGraphSha256"], f"Boot BOM {version} graph")
        )
    if target_digests[0] == target_digests[1]:
        raise ReceiptError("the two selected BOM families must have distinct target graphs")
    require_digest(receipt["pilotGraphSha256"], "pilot graph")

    artifact = receipt["artifact"]
    exact_mapping(artifact, {
        "coordinate": (
            "io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.2"
        ),
        "jarSha256": (
            "d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc"
        ),
        "pomSha256": (
            "70b5d4161d1532e9f9cb699071790a7806d87658511d931477544fa06037b85d"
        ),
        "origin": "exact-local-release-repository",
    }, "artifact")

    isolation = receipt["isolation"]
    exact_mapping(isolation, {
        "caseGradleUserHomes": 10,
        "uniqueInitiallyAbsent": True,
        "dependencyCachesShared": False,
        "wrapperDistributionSeedOnly": True,
    }, "isolation")


def run(path: Path) -> None:
    if not path.is_absolute():
        raise ReceiptError("receipt path must be absolute")
    if path.is_symlink() or not path.is_file():
        raise ReceiptError("receipt must be a regular non-symlink file")
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_BYTES:
        raise ReceiptError("receipt size is outside the accepted boundary")
    try:
        text = raw.decode("utf-8")
        value = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReceiptError(f"receipt is not strict UTF-8 JSON: {error}") from error
    validate(value)
    canonical = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if text != canonical:
        raise ReceiptError("receipt bytes are not canonical sorted JSON")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: validate-gradle95-build-shape-receipt.py ABSOLUTE_RECEIPT", file=sys.stderr)
        return 64
    try:
        run(Path(argv[0]))
    except (OSError, ReceiptError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("ROUTECONTRACT_GRADLE95_BUILD_SHAPE_RECEIPT VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
