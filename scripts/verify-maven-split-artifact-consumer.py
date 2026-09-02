#!/usr/bin/env python3
"""Verify both Maven 0.2 split-artifact lanes from one atomic local staging tree."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile


EXPECTED_MAVEN_VERSION = "3.9.14"
COMMAND_TIMEOUT_SECONDS = 900
GROUP_PATH = Path("io/github/ym0506/routecontract")
LANES = {
    "553": {
        "profile": "routecontract-553",
        "version": "5.5.3",
        "adapter": "routecontract-shardingsphere-5.5",
        "opposite": "routecontract-shardingsphere-5.5.2",
        "wrong": "5.5.2",
    },
    "552": {
        "profile": "routecontract-552",
        "version": "5.5.2",
        "adapter": "routecontract-shardingsphere-5.5.2",
        "opposite": "routecontract-shardingsphere-5.5",
        "wrong": "5.5.3",
    },
}


class VerificationError(RuntimeError):
    """The isolated Maven consumer gate did not produce unambiguous evidence."""


def run(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    expect_success: bool,
) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if expect_success != (result.returncode == 0):
        expectation = "success" if expect_success else "failure"
        raise VerificationError(
            f"command did not produce expected {expectation} (rc={result.returncode}): "
            + " ".join(command)
            + "\n"
            + result.stdout
        )
    return result.stdout


def require_exact_output_line(output: str, expected: str, label: str) -> None:
    if expected not in output.splitlines():
        raise VerificationError(f"{label} omitted exact output line: {expected}")


def regular_executable(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise VerificationError(f"{label} must be an absolute path")
    try:
        status = os.lstat(path)
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise VerificationError(f"cannot inspect {label}: {error}") from error
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
        raise VerificationError(f"{label} must be a regular non-symlink file")
    if not os.access(resolved, os.X_OK):
        raise VerificationError(f"{label} must be executable")
    return resolved


def clean_environment(java_home: Path) -> dict[str, str]:
    environment = dict(os.environ)
    for name in (
        "JAVA_TOOL_OPTIONS",
        "JDK_JAVA_OPTIONS",
        "_JAVA_OPTIONS",
        "MAVEN_ARGS",
        "MAVEN_CONFIG",
        "MAVEN_OPTS",
    ):
        environment.pop(name, None)
    environment["JAVA_HOME"] = str(java_home)
    environment["MAVEN_SKIP_RC"] = "true"
    return environment


def verify_toolchain(
    maven: Path, java_home: Path, root: Path, environment: dict[str, str]
) -> None:
    java = regular_executable(java_home / "bin/java", "JAVA_HOME/bin/java")
    java_output = run(
        [str(java), "-version"], cwd=root, environment=environment, expect_success=True
    )
    if re.search(r'version "17(?:[.]|\")', java_output) is None:
        raise VerificationError("JAVA_HOME must identify JDK 17")
    maven_output = run(
        [str(maven), "-version"], cwd=root, environment=environment, expect_success=True
    )
    if not maven_output.startswith(f"Apache Maven {EXPECTED_MAVEN_VERSION} "):
        raise VerificationError(
            f"Apache Maven {EXPECTED_MAVEN_VERSION} is required\n{maven_output}"
        )
    if "Java version: 17." not in maven_output:
        raise VerificationError("Maven must run on the supplied JDK 17")


def maven_command(
    maven: Path,
    pom: Path,
    settings: Path,
    local_repository: Path,
    staged_repository: Path,
    profiles: str,
    goals: list[str],
) -> list[str]:
    return [
        str(maven),
        "--batch-mode",
        "--no-transfer-progress",
        "--strict-checksums",
        "--settings",
        str(settings),
        "--global-settings",
        str(settings),
        "--file",
        str(pom),
        f"-Dmaven.repo.local={local_repository}",
        f"-Droutecontract.repositoryUrl={staged_repository.as_uri()}",
        f"-P{profiles}",
        *goals,
    ]


def assert_staged_origin(local_repository: Path, module: str) -> None:
    directory = local_repository / GROUP_PATH / module / "0.2.0"
    marker = directory / "_remote.repositories"
    expected = {
        f"{module}-0.2.0.jar>routecontract-staged=",
        f"{module}-0.2.0.pom>routecontract-staged=",
    }
    try:
        status = os.lstat(marker)
        if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
            raise VerificationError(
                f"Maven origin marker must be a regular non-symlink file: {marker}"
            )
        lines = set(marker.read_text(encoding="utf-8").splitlines())
    except OSError as error:
        raise VerificationError(f"cannot read Maven origin marker {marker}: {error}") from error
    artifact_prefixes = (
        f"{module}-0.2.0.jar>",
        f"{module}-0.2.0.pom>",
    )
    observed = {line for line in lines if line.startswith(artifact_prefixes)}
    if observed != expected:
        missing = expected - observed
        unexpected = observed - expected
        raise VerificationError(
            f"Maven did not resolve {module} JAR/POM unambiguously from "
            f"routecontract-staged: missing={sorted(missing)} "
            f"unexpected={sorted(unexpected)}"
        )


def verify_lane(
    lane_name: str,
    lane: dict[str, str],
    *,
    maven: Path,
    pom: Path,
    settings: Path,
    staged_repository: Path,
    temporary_root: Path,
    root: Path,
    environment: dict[str, str],
) -> None:
    local_repository = temporary_root / f"m2-{lane_name}"
    positive = run(
        maven_command(
            maven,
            pom,
            settings,
            local_repository,
            staged_repository,
            lane["profile"],
            ["clean", "verify"],
        ),
        cwd=root,
        environment=environment,
        expect_success=True,
    )
    expected_marker = (
        "ROUTECONTRACT_MAVEN_SPLIT_RUNTIME_VERIFIED "
        f"version={lane['version']} adapter={lane['adapter']}"
    )
    require_exact_output_line(
        positive, expected_marker, f"positive {lane_name} lane"
    )
    assert_staged_origin(local_repository, "routecontract-core")
    assert_staged_origin(local_repository, lane["adapter"])

    wrong = run(
        maven_command(
            maven,
            pom,
            settings,
            local_repository,
            staged_repository,
            f"{lane['profile']},wrong-non-anchor",
            ["validate"],
        ),
        cwd=root,
        environment=environment,
        expect_success=False,
    )
    if (
        "BannedDependencies failed" not in wrong
        or f"shardingsphere-sharding-core:jar:{lane['wrong']}" not in wrong
    ):
        raise VerificationError(
            f"wrong non-anchor {lane_name} lane did not fail through BannedDependencies"
        )

    dual = run(
        maven_command(
            maven,
            pom,
            settings,
            local_repository,
            staged_repository,
            f"{lane['profile']},dual-adapter",
            ["validate"],
        ),
        cwd=root,
        environment=environment,
        expect_success=False,
    )
    if (
        "BannedDependencies failed" not in dual
        or f"{lane['opposite']}:jar:0.2.0" not in dual
    ):
        raise VerificationError(
            f"dual-adapter {lane_name} lane did not name and reject the opposite adapter"
        )

    print(
        "ROUTECONTRACT_MAVEN_SPLIT_LANE_VERIFIED "
        f"version={lane['version']} adapter={lane['adapter']}"
    )


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    fixture = root / "examples/maven-split-artifact-consumer"
    pom = fixture / "pom.xml"
    settings = fixture / "settings.xml"
    wrapper = regular_executable(root / "gradlew", "Gradle wrapper")

    maven_value = os.environ.get("MAVEN_BIN") or shutil.which("mvn")
    if not maven_value:
        raise VerificationError("MAVEN_BIN or mvn on PATH is required")
    maven = regular_executable(Path(maven_value).expanduser().absolute(), "Maven executable")
    java_home_value = os.environ.get("JAVA_HOME")
    if not java_home_value:
        raise VerificationError("JAVA_HOME must identify an existing JDK 17")
    java_home = Path(java_home_value).expanduser().absolute().resolve(strict=True)
    environment = clean_environment(java_home)
    verify_toolchain(maven, java_home, root, environment)

    with tempfile.TemporaryDirectory(prefix="routecontract-maven-split-") as temporary:
        temporary_root = Path(temporary).resolve(strict=True)
        os.chmod(temporary_root, 0o700)
        staged_repository = temporary_root / "staging"
        staging_output = run(
            [
                str(wrapper),
                "--no-daemon",
                "--no-build-cache",
                f"-ProutecontractCentralStagingDirectory={staged_repository}",
                "-ProutecontractCentralSigning=false",
                "publishRouteContractCentralStaging",
            ],
            cwd=root,
            environment=environment,
            expect_success=True,
        )
        if "BUILD SUCCESSFUL" not in staging_output:
            raise VerificationError("coordinated local staging omitted Gradle success marker")
        for lane_name, lane in LANES.items():
            verify_lane(
                lane_name,
                lane,
                maven=maven,
                pom=pom,
                settings=settings,
                staged_repository=staged_repository,
                temporary_root=temporary_root,
                root=root,
                environment=environment,
            )

    print("ROUTECONTRACT_MAVEN_SPLIT_FIXTURE_VERIFIED lanes=2 negativeCases=4")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.SubprocessError, VerificationError) as error:
        print(f"MAVEN_SPLIT_FIXTURE_FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
