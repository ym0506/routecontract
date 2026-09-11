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
    "io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.2"
)
JAR_SHA256 = "d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc"
POM_SHA256 = "70b5d4161d1532e9f9cb699071790a7806d87658511d931477544fa06037b85d"
DIGEST = re.compile(r"[0-9a-f]{64}")
GIT_OBJECT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
COORDINATE_PATH = Path(
    "io/github/ym0506/routecontract/routecontract-shardingsphere-5.5/0.1.2"
)
WRAPPER_DISTRIBUTION_URL = (
    "https://services.gradle.org/distributions/gradle-8.14.4-bin.zip"
)
WRAPPER_DISTRIBUTION_SHA256 = (
    "f1771298a70f6db5a29daf62378c4e18a17fc33c9ba6b14362e0cdf40610380d"
)
WRAPPER_JAR_SHA256 = (
    "7d3a4ac4de1c32b59bc6a4eb8ecb8e612ccd0cf1ae1e99f66902da64df296172"
)


class ProvenanceError(RuntimeError):
    """An exact provenance contract failure."""


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProvenanceError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


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


def exact_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or DIGEST.fullmatch(value) is None:
        raise ProvenanceError(f"{label} must be 64 lowercase hex characters")
    return value


def exact_git_object_id(value: object, label: str) -> str:
    if not isinstance(value, str) or GIT_OBJECT_ID.fullmatch(value) is None:
        raise ProvenanceError(
            f"{label} must be a 40- or 64-character lowercase Git object ID"
        )
    return value


def exact_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise ProvenanceError(f"{label} must be boolean")
    return value


def exact_int(value: object, label: str) -> int:
    if type(value) is not int:
        raise ProvenanceError(f"{label} must be an integer")
    return value


def validate_receipt(document: object) -> dict[str, object]:
    root = exact_keys(
        document,
        {
            "schemaVersion",
            "coordinate",
            "source",
            "toolchain",
            "artifacts",
            "verification",
            "claimBoundary",
        },
        "receipt",
    )
    if type(root["schemaVersion"]) is not int or root["schemaVersion"] != 2:
        raise ProvenanceError("receipt schema version must be the integer 2")
    if root["coordinate"] != COORDINATE:
        raise ProvenanceError("receipt schema and coordinate must be exact")

    source = exact_keys(
        root["source"], {"revision", "tree", "clean", "binding"}, "source"
    )
    clean = exact_bool(source["clean"], "source.clean")
    if clean:
        revision = exact_git_object_id(source["revision"], "source.revision")
        tree = exact_git_object_id(source["tree"], "source.tree")
        if len(revision) != len(tree):
            raise ProvenanceError("source revision and tree object formats must match")
        if source["binding"] != "exact-clean-checkout":
            raise ProvenanceError("clean source must have an exact checkout binding")
    elif source["binding"] == "head-only-dirty-worktree":
        revision = exact_git_object_id(source["revision"], "source.revision")
        tree = exact_git_object_id(source["tree"], "source.tree")
        if len(revision) != len(tree):
            raise ProvenanceError("source revision and tree object formats must match")
    elif source["binding"] == "unbound-source-copy":
        if source["revision"] is not None or source["tree"] is not None:
            raise ProvenanceError("unbound source must not claim a revision or tree")
    else:
        raise ProvenanceError("non-clean source must disclose its limited binding")

    toolchain = exact_keys(
        root["toolchain"],
        {
            "gradleVersion",
            "javaMajor",
            "wrapperDistributionUrl",
            "wrapperDistributionSha256",
            "wrapperJarSha256",
        },
        "toolchain",
    )
    exact_int(toolchain["javaMajor"], "toolchain.javaMajor")
    if (
        toolchain["gradleVersion"] != "8.14.4"
        or toolchain["javaMajor"] != 17
        or toolchain["wrapperDistributionUrl"] != WRAPPER_DISTRIBUTION_URL
        or toolchain["wrapperDistributionSha256"]
        != WRAPPER_DISTRIBUTION_SHA256
        or toolchain["wrapperJarSha256"] != WRAPPER_JAR_SHA256
    ):
        raise ProvenanceError("toolchain version and wrapper identities must be exact")
    exact_digest(toolchain["wrapperJarSha256"], "toolchain.wrapperJarSha256")

    artifacts = exact_keys(root["artifacts"], {"jar", "pom"}, "artifacts")
    expected_artifacts = {
        "jar": ("routecontract-shardingsphere-5.5-0.1.2.jar", JAR_SHA256),
        "pom": ("routecontract-shardingsphere-5.5-0.1.2.pom", POM_SHA256),
    }
    for label, expected in expected_artifacts.items():
        entry = exact_keys(
            artifacts[label], {"fileName", "sha256", "retained"}, label
        )
        retained = exact_bool(entry["retained"], f"{label}.retained")
        if (
            entry["fileName"] != expected[0]
            or entry["sha256"] != expected[1]
            or retained is not False
        ):
            raise ProvenanceError(f"{label} receipt identity must be exact and non-retained")

    verification = exact_keys(
        root["verification"],
        {
            "environmentIsolation",
            "caseCount",
            "cachePairsUnique",
            "decoyFallback",
            "runtimePreflight",
            "pathsEphemeral",
            "missingBaseline",
            "matched",
        },
        "verification",
    )
    exact_int(verification["caseCount"], "verification.caseCount")
    cache_pairs_unique = exact_bool(
        verification["cachePairsUnique"], "verification.cachePairsUnique"
    )
    paths_ephemeral = exact_bool(
        verification["pathsEphemeral"], "verification.pathsEphemeral"
    )
    if (
        verification["environmentIsolation"] != "env-i-allowlist"
        or verification["caseCount"] != 14
        or cache_pairs_unique is not True
        or verification["decoyFallback"]
        != "designated-exclusive-repository-only"
        or verification["runtimePreflight"]
        != "before-mysql-and-routecontract-operation"
        or paths_ephemeral is not True
    ):
        raise ProvenanceError("receipt verification boundary must be exact")

    outcomes: dict[str, dict[str, object]] = {}
    for label, expected_counts in (
        ("missingBaseline", (1, 1, 0, 0)),
        ("matched", (1, 0, 0, 0)),
    ):
        outcome = exact_keys(
            verification[label],
            {
                "outcome",
                "candidateSha256",
                "candidateBytes",
                "junitSha256",
                "junitBytes",
                "tests",
                "failures",
                "errors",
                "skipped",
                "runtimeObservationSha256",
            },
            label,
        )
        expected_outcome = (
            "EXPECTED_MISSING_HUMAN_BASELINE"
            if label == "missingBaseline"
            else "SYNTHETIC_MATCH_PASS"
        )
        if outcome["outcome"] != expected_outcome:
            raise ProvenanceError(f"{label}.outcome is not exact")
        for digest_label in (
            "candidateSha256",
            "junitSha256",
            "runtimeObservationSha256",
        ):
            exact_digest(outcome[digest_label], f"{label}.{digest_label}")
        for size_label in ("candidateBytes", "junitBytes"):
            exact_int(outcome[size_label], f"{label}.{size_label}")
            if outcome[size_label] <= 0:
                raise ProvenanceError(f"{label}.{size_label} must be positive")
        count_values = tuple(
            exact_int(outcome[key], f"{label}.{key}")
            for key in ("tests", "failures", "errors", "skipped")
        )
        if count_values != expected_counts:
            raise ProvenanceError(f"{label} JUnit counts are not exact")
        outcomes[label] = outcome
    if outcomes["missingBaseline"]["candidateSha256"] \
            != outcomes["matched"]["candidateSha256"]:
        raise ProvenanceError("missing and matched candidates must be byte-identical")
    if outcomes["missingBaseline"]["candidateBytes"] \
            != outcomes["matched"]["candidateBytes"]:
        raise ProvenanceError("missing and matched candidate sizes must be identical")

    claim = exact_keys(
        root["claimBoundary"],
        {"externalUser", "humanApprovedBaseline", "adoption", "endorsement"},
        "claimBoundary",
    )
    for label, value in claim.items():
        if exact_bool(value, f"claimBoundary.{label}") is not False:
            raise ProvenanceError("receipt must preserve the exact non-adoption boundary")
    if set(claim) != {
        "externalUser",
        "humanApprovedBaseline",
        "adoption",
        "endorsement",
    }:
        raise ProvenanceError("receipt must preserve the exact non-adoption boundary")
    return root


def validate(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise ProvenanceError("provenance must be a regular non-symlink file")
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProvenanceError(f"provenance is not exact UTF-8 JSON: {error}") from error
    if isinstance(document, dict) and document.get("schemaVersion") == 2:
        return validate_receipt(document)
    root = exact_keys(
        document,
        {
            "schemaVersion",
            "coordinate",
            "resolvedComponent",
            "pathsEphemeral",
            "repositoryRoot",
            "jar",
            "pom",
            "origins",
            "claimBoundary",
        },
        "provenance",
    )
    if type(root["schemaVersion"]) is not int or root["schemaVersion"] != 1:
        raise ProvenanceError("schemaVersion must be exactly the integer 1")
    if root["coordinate"] != COORDINATE or root["resolvedComponent"] != COORDINATE:
        raise ProvenanceError("requested and selected RouteContract GAV must both be exact")
    if exact_bool(root["pathsEphemeral"], "pathsEphemeral") is not True:
        raise ProvenanceError("pathsEphemeral must disclose temporary verifier paths")

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
    if jar != expected_directory / "routecontract-shardingsphere-5.5-0.1.2.jar":
        raise ProvenanceError("jar.path is not the canonical coordinate path")
    if pom != expected_directory / "routecontract-shardingsphere-5.5-0.1.2.pom":
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
    exact_int(origins["serviceDescriptorCount"], "origins.serviceDescriptorCount")
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
    for label in ("externalUser", "humanApprovedBaseline", "adoption"):
        if exact_bool(claim[label], f"claimBoundary.{label}") is not False:
            raise ProvenanceError("claimBoundary must preserve the exact non-adoption boundary")
    if claim["dependencyVerification"] != (
        "selected-invariant-graph-and-pre-operation-runtime-origin"
    ):
        raise ProvenanceError("claimBoundary must preserve the exact non-adoption boundary")
    return root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("provenance", type=Path)
    args = parser.parse_args()
    try:
        validated = validate(args.provenance)
    except (OSError, ProvenanceError) as error:
        print(f"ROUTECONTRACT_GRADLE_PROVENANCE_ERROR {error}")
        return 2
    evidence = (
        "runtimeOriginEvidence=HASHED_EPHEMERAL_OBSERVATIONS"
        if validated["schemaVersion"] == 2
        else "origins=EXACT"
    )
    print(
        "ROUTECONTRACT_GRADLE_PROVENANCE "
        f"coordinate={COORDINATE} jarSha256={JAR_SHA256} "
        f"pomSha256={POM_SHA256} {evidence} claim=SELECTED_INVARIANTS_ONLY"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
