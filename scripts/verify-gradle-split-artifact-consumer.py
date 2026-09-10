#!/usr/bin/env python3
"""Verify both local Gradle split-artifact lanes with real strict trust metadata."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


EXPECTED_GRADLE_VERSION = "8.14.4"
EXPECTED_ROUTE_CONTRACT_VERSION = "0.2.0"
COMMAND_TIMEOUT_SECONDS = 1200
VERIFICATION_NAMESPACE = "https://schema.gradle.org/dependency-verification"
XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"
FIXTURE_ENTRIES = (
    ".gitignore",
    "README.md",
    "build.gradle.kts",
    "settings.gradle.kts",
    "src",
)
LANES = {
    "552": {
        "version": "5.5.2",
        "adapter": "routecontract-shardingsphere-5.5.2",
        "other": "5.5.3",
        "components": 48,
    },
    "553": {
        "version": "5.5.3",
        "adapter": "routecontract-shardingsphere-5.5",
        "other": "5.5.2",
        "components": 26,
    },
}


class VerificationError(RuntimeError):
    """The isolated Gradle consumer gate did not produce unambiguous evidence."""


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


def regular_file(path: Path, label: str, *, executable: bool = False) -> Path:
    if not path.is_absolute():
        raise VerificationError(f"{label} must be an absolute path")
    try:
        status = os.lstat(path)
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise VerificationError(f"cannot inspect {label}: {error}") from error
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
        raise VerificationError(f"{label} must be a regular non-symlink file")
    if executable and not os.access(resolved, os.X_OK):
        raise VerificationError(f"{label} must be executable")
    return resolved


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fixture_snapshot(fixture: Path, metadata: Path) -> dict[str, str]:
    snapshot = {"gradle/verification-metadata.xml": sha256(metadata)}
    for entry in FIXTURE_ENTRIES:
        source = fixture / entry
        try:
            status = os.lstat(source)
        except OSError as error:
            raise VerificationError(f"cannot inspect fixture entry {source}: {error}") from error
        if stat.S_ISLNK(status.st_mode):
            raise VerificationError(f"fixture entry must not be a symlink: {source}")
        paths = [source] if stat.S_ISREG(status.st_mode) else sorted(source.rglob("*"))
        for path in paths:
            status = os.lstat(path)
            if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
                if stat.S_ISDIR(status.st_mode):
                    continue
                raise VerificationError(f"fixture contains a non-regular entry: {path}")
            relative = path.relative_to(fixture).as_posix()
            snapshot[f"fixture/{relative}"] = sha256(path)
    return snapshot


def copy_fixture(fixture: Path, destination: Path, metadata: Path) -> Path:
    if destination.exists():
        raise VerificationError(f"temporary fixture destination must start absent: {destination}")
    destination.mkdir(mode=0o700)
    for entry in FIXTURE_ENTRIES:
        source = fixture / entry
        target = destination / entry
        if source.is_dir():
            shutil.copytree(source, target, symlinks=False)
        else:
            shutil.copy2(source, target, follow_symlinks=False)
    copied_metadata = destination / "gradle/verification-metadata.xml"
    copied_metadata.parent.mkdir(mode=0o700)
    shutil.copy2(metadata, copied_metadata, follow_symlinks=False)
    if sha256(copied_metadata) != sha256(metadata):
        raise VerificationError("strict verification metadata changed while being copied")
    return copied_metadata


def clean_environment(java_home: Path, gradle_user_home: Path) -> dict[str, str]:
    environment = dict(os.environ)
    for name in tuple(environment):
        if name.startswith("ORG_GRADLE_PROJECT_"):
            environment.pop(name, None)
    for name in (
        "GRADLE_OPTS",
        "JAVA_OPTS",
        "JAVA_TOOL_OPTIONS",
        "JDK_JAVA_OPTIONS",
        "_JAVA_OPTIONS",
    ):
        environment.pop(name, None)
    environment["JAVA_HOME"] = str(java_home)
    environment["GRADLE_USER_HOME"] = str(gradle_user_home)
    return environment


def verify_toolchain(root: Path, java_home: Path) -> None:
    java = regular_file(java_home / "bin/java", "JAVA_HOME/bin/java", executable=True)
    result = subprocess.run(
        [str(java), "-version"],
        cwd=root,
        env=clean_environment(java_home, root / ".unused-gradle-home"),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=30,
    )
    if result.returncode != 0 or re.search(r'version "17(?:[.]|\")', result.stdout) is None:
        raise VerificationError("JAVA_HOME must identify a working JDK 17")

    properties = regular_file(
        root / "gradle/wrapper/gradle-wrapper.properties",
        "Gradle wrapper properties",
    ).read_text(encoding="utf-8")
    expected_url = f"gradle-{EXPECTED_GRADLE_VERSION}-bin.zip"
    if expected_url not in properties or "distributionSha256Sum=" not in properties:
        raise VerificationError(
            f"wrapper must pin Gradle {EXPECTED_GRADLE_VERSION} and its distribution SHA-256"
        )


def prepare_wrapper_seed(
    root: Path,
    wrapper: Path,
    java_home: Path,
    seed_home: Path,
) -> None:
    output = run(
        [str(wrapper), "--no-daemon", "--version"],
        cwd=root,
        environment=clean_environment(java_home, seed_home),
        expect_success=True,
    )
    if f"Gradle {EXPECTED_GRADLE_VERSION}" not in output:
        raise VerificationError(f"wrapper did not launch Gradle {EXPECTED_GRADLE_VERSION}")
    if re.search(r"Launcher JVM:\s+17(?:[.]|\s)", output) is None:
        raise VerificationError("Gradle wrapper must run on the supplied JDK 17")
    distributions = seed_home / "wrapper/dists"
    if not distributions.is_dir():
        raise VerificationError("wrapper seed omitted its verified distribution cache")


def seed_wrapper_distribution(seed_home: Path, gradle_home: Path) -> None:
    source = seed_home / "wrapper/dists"
    target = gradle_home / "wrapper/dists"
    if target.exists():
        raise VerificationError("fresh Gradle home unexpectedly contains a wrapper distribution")
    target.parent.mkdir(mode=0o700)
    shutil.copytree(source, target, symlinks=False)


def gradle_command(
    wrapper: Path,
    fixture: Path,
    project_cache: Path,
    version: str,
    tasks: list[str],
) -> list[str]:
    return [
        str(wrapper),
        "--no-daemon",
        "--no-build-cache",
        "--no-configuration-cache",
        "--rerun-tasks",
        "--dependency-verification=strict",
        "--console=plain",
        "--project-dir",
        str(fixture),
        "--project-cache-dir",
        str(project_cache),
        f"-ProutecontractAdapterVersion={version}",
        *tasks,
    ]


def require_exactly_once(output: str, marker: str, label: str) -> None:
    count = output.count(marker)
    if count != 1:
        raise VerificationError(f"{label} marker count must be 1, found {count}: {marker}")


def validate_lane_output(output: str, lane: dict[str, str]) -> None:
    version = lane["version"]
    adapter = lane["adapter"]
    graph_marker = (
        "ROUTECONTRACT_GRADLE_SPLIT_GRAPH_VERIFIED "
        f"adapter={adapter} routeContractVersion={EXPECTED_ROUTE_CONTRACT_VERSION} "
        f"shardingSphereVersion={version} shardingSphereComponents={lane['components']}"
    )
    wrong_marker = (
        "ROUTECONTRACT_GRADLE_WRONG_NON_ANCHOR_REJECTED "
        f"module=shardingsphere-infra-common requested={lane['other']} expected={version}"
    )
    markers = (
        (graph_marker, "selected graph"),
        (wrong_marker, "wrong non-anchor rejection"),
        (
            "ROUTECONTRACT_GRADLE_DUAL_ADAPTER_REJECTED "
            "order=5.5.2-then-5.5.3 "
            "capability=io.github.ym0506.routecontract:"
            "routecontract-shardingsphere-hook-adapter:1",
            "5.5.2-first dual-adapter rejection",
        ),
        (
            "ROUTECONTRACT_GRADLE_DUAL_ADAPTER_REJECTED "
            "order=5.5.3-then-5.5.2 "
            "capability=io.github.ym0506.routecontract:"
            "routecontract-shardingsphere-hook-adapter:1",
            "5.5.3-first dual-adapter rejection",
        ),
        (
            f"ROUTECONTRACT_GRADLE_SPLIT_RUNTIME_VERIFIED version={version}",
            "runtime preflight",
        ),
    )
    for marker, label in markers:
        require_exactly_once(output, marker, label)
    if "Dependency verification failed" in output:
        raise VerificationError("positive lane reported a dependency-verification failure")
    if "BUILD SUCCESSFUL" not in output:
        raise VerificationError("positive lane omitted Gradle's success marker")


def corrupt_executor_checksum(metadata: Path, version: str) -> str:
    ET.register_namespace("", VERIFICATION_NAMESPACE)
    ET.register_namespace("xsi", XSI_NAMESPACE)
    tree = ET.parse(metadata)
    namespace = {"v": VERIFICATION_NAMESPACE}
    matches = []
    for component in tree.findall("v:components/v:component", namespace):
        if component.attrib != {
            "group": "org.apache.shardingsphere",
            "name": "shardingsphere-infra-executor",
            "version": version,
        }:
            continue
        for artifact in component.findall("v:artifact", namespace):
            if artifact.attrib.get("name") == f"shardingsphere-infra-executor-{version}.jar":
                checksums = artifact.findall("v:sha256", namespace)
                if len(checksums) == 1:
                    matches.append(checksums[0])
    if len(matches) != 1:
        raise VerificationError(
            f"expected one reviewed infra-executor {version} JAR checksum, found {len(matches)}"
        )
    original = matches[0].attrib.get("value", "")
    if re.fullmatch(r"[0-9a-f]{64}", original) is None:
        raise VerificationError("reviewed checksum is not an exact lower-case SHA-256")
    matches[0].set("value", "0" * 64)
    tree.write(metadata, encoding="utf-8", xml_declaration=True)
    return original


def verify_checksum_rejection(
    *,
    root: Path,
    wrapper: Path,
    fixture: Path,
    metadata: Path,
    java_home: Path,
    wrapper_seed: Path,
    lane: dict[str, str],
) -> None:
    examples = root / "examples"
    with tempfile.TemporaryDirectory(
        prefix=f".routecontract-gradle-split-wrong-{lane['version']}-",
        dir=examples,
    ) as fixture_name, tempfile.TemporaryDirectory(
        prefix=f"routecontract-gradle-split-home-wrong-{lane['version']}-"
    ) as home_name, tempfile.TemporaryDirectory(
        prefix=f"routecontract-gradle-split-cache-wrong-{lane['version']}-"
    ) as cache_name:
        fixture_copy = Path(fixture_name).resolve(strict=True)
        fixture_copy.rmdir()
        copied_metadata = copy_fixture(fixture, fixture_copy, metadata)
        corrupt_executor_checksum(copied_metadata, lane["version"])
        gradle_home = Path(home_name).resolve(strict=True)
        project_cache = Path(cache_name).resolve(strict=True)
        os.chmod(gradle_home, 0o700)
        os.chmod(project_cache, 0o700)
        seed_wrapper_distribution(wrapper_seed, gradle_home)
        output = run(
            gradle_command(
                wrapper,
                fixture_copy,
                project_cache,
                lane["version"],
                ["run"],
            ),
            cwd=root,
            environment=clean_environment(java_home, gradle_home),
            expect_success=False,
        )
        artifact = f"shardingsphere-infra-executor-{lane['version']}.jar"
        if "Dependency verification failed" not in output or artifact not in output:
            raise VerificationError(
                f"wrong-checksum {lane['version']} lane did not fail through strict verification"
            )
        if "ROUTECONTRACT_GRADLE_SPLIT_RUNTIME_VERIFIED" in output:
            raise VerificationError("wrong-checksum lane reached the runtime success marker")


def verify_lane(
    *,
    root: Path,
    wrapper: Path,
    fixture: Path,
    metadata: Path,
    java_home: Path,
    wrapper_seed: Path,
    lane: dict[str, str],
) -> None:
    examples = root / "examples"
    with tempfile.TemporaryDirectory(
        prefix=f".routecontract-gradle-split-{lane['version']}-",
        dir=examples,
    ) as fixture_name, tempfile.TemporaryDirectory(
        prefix=f"routecontract-gradle-split-home-{lane['version']}-"
    ) as home_name, tempfile.TemporaryDirectory(
        prefix=f"routecontract-gradle-split-cache-{lane['version']}-"
    ) as cache_name:
        fixture_copy = Path(fixture_name).resolve(strict=True)
        fixture_copy.rmdir()
        copy_fixture(fixture, fixture_copy, metadata)
        gradle_home = Path(home_name).resolve(strict=True)
        project_cache = Path(cache_name).resolve(strict=True)
        os.chmod(gradle_home, 0o700)
        os.chmod(project_cache, 0o700)
        seed_wrapper_distribution(wrapper_seed, gradle_home)
        output = run(
            gradle_command(
                wrapper,
                fixture_copy,
                project_cache,
                lane["version"],
                ["clean", "check"],
            ),
            cwd=root,
            environment=clean_environment(java_home, gradle_home),
            expect_success=True,
        )
        validate_lane_output(output, lane)
    print(
        "ROUTECONTRACT_GRADLE_SPLIT_LANE_VERIFIED "
        f"version={lane['version']} adapter={lane['adapter']} "
        f"dependencyVerification=strict-fresh-cache"
    )


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    fixture = root / "examples/gradle-split-artifact-consumer"
    metadata = regular_file(
        root / "gradle/verification-metadata.xml",
        "reviewed dependency-verification metadata",
    )
    wrapper = regular_file(root / "gradlew", "Gradle wrapper", executable=True)
    java_home_value = os.environ.get("JAVA_HOME")
    if not java_home_value:
        raise VerificationError("JAVA_HOME must identify an existing JDK 17")
    java_home = Path(java_home_value).expanduser().absolute().resolve(strict=True)
    verify_toolchain(root, java_home)

    before = fixture_snapshot(fixture, metadata)
    with tempfile.TemporaryDirectory(
        prefix="routecontract-gradle-split-wrapper-seed-"
    ) as seed_name:
        wrapper_seed = Path(seed_name).resolve(strict=True)
        os.chmod(wrapper_seed, 0o700)
        prepare_wrapper_seed(root, wrapper, java_home, wrapper_seed)
        for lane in LANES.values():
            verify_lane(
                root=root,
                wrapper=wrapper,
                fixture=fixture,
                metadata=metadata,
                java_home=java_home,
                wrapper_seed=wrapper_seed,
                lane=lane,
            )
            verify_checksum_rejection(
                root=root,
                wrapper=wrapper,
                fixture=fixture,
                metadata=metadata,
                java_home=java_home,
                wrapper_seed=wrapper_seed,
                lane=lane,
            )
    after = fixture_snapshot(fixture, metadata)
    if after != before:
        raise VerificationError("source fixture or reviewed trust metadata changed during verification")

    print(
        "ROUTECONTRACT_GRADLE_SPLIT_FIXTURE_VERIFIED "
        "lanes=2 negativeCases=8 dependencyVerification=strict-fresh-cache "
        "evidence=local-composite-runtime-preflight"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.SubprocessError, VerificationError, ET.ParseError) as error:
        print(f"GRADLE_SPLIT_FIXTURE_FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
