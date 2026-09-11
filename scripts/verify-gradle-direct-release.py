#!/usr/bin/env python3
"""Isolated black-box verifier for the immutable v0.1.2 Gradle consumer lane."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "gradle-direct-release"
WRAPPER_SOURCE = ROOT / "examples" / "gradle95-build-shape"
WRAPPER_ROOT = FIXTURE
ROUTECONTRACT_SHA256 = (
    "d25cd2699629890db7195e871461b25861991fe20abd776d702c690a292b72fc"
)
TTL_POM_SHA256 = (
    "a8937cb6bd4b9a352de014d7ed3e856b01faacc92e6146ef9a88a354b62d135a"
)
WRONG_SHA256 = "0" * 64
GRADLE_DISTRIBUTION_SHA256 = (
    "bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f"
)
WRAPPER_HASHES = {
    "gradlew": "ab5c0cad16305af2e619c159c1f58dd68d07fab9c11e36701e109c0277407f7a",
    "gradlew.bat": "475c4f08cd57cf2faa819e7f36d72aa93f0ad646ea23a8f7fa3ef54dee1cbc52",
    "gradle/wrapper/gradle-wrapper.jar": (
        "497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7"
    ),
    "gradle/wrapper/gradle-wrapper.properties": (
        "9caeb142fade370957e5e9cd95a83441bbe41f73a1863398dd5467695853332e"
    ),
}
SUCCESS_MARKERS = (
    "ROUTECONTRACT_DIRECT_RELEASE_ARTIFACT_VERIFIED",
    "ROUTECONTRACT_DIRECT_RELEASE_RUNTIME_CLASSPATH_VERIFIED",
    "ROUTECONTRACT_DIRECT_RELEASE_RUNTIME_PROBE_VERIFIED",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_wrapper() -> None:
    for relative, expected in WRAPPER_HASHES.items():
        path = WRAPPER_ROOT / relative
        source = WRAPPER_SOURCE / relative
        require(path.is_file() and not path.is_symlink(), f"invalid wrapper file: {path}")
        require(source.is_file() and not source.is_symlink(), f"invalid wrapper source: {source}")
        require(sha256(path) == expected, f"wrapper hash changed: {relative}")
        require(path.read_bytes() == source.read_bytes(), f"wrapper copy differs: {relative}")
        expected_mode = 0o755 if relative == "gradlew" else 0o644
        require(
            stat.S_IMODE(path.stat().st_mode) == expected_mode,
            f"wrapper mode changed: {relative}",
        )
    properties = (WRAPPER_ROOT / "gradle/wrapper/gradle-wrapper.properties").read_text(
        encoding="utf-8"
    )
    require(
        "distributionUrl=https\\://services.gradle.org/distributions/gradle-9.5.1-bin.zip"
        in properties,
        "wrapper is not pinned to Gradle 9.5.1",
    )
    require(
        "distributionSha256Sum="
        "bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f"
        in properties,
        "wrapper distribution checksum changed",
    )


def verify_java_home(java_home: Path) -> None:
    java = java_home / "bin" / "java"
    require(java.is_file(), f"JDK java executable is missing: {java}")
    result = subprocess.run(
        [str(java), "-version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    require(result.returncode == 0, "unable to run configured JDK")
    require('version "17.' in result.stdout, "configured JAVA_HOME is not JDK 17")


def assert_fixture_clean() -> None:
    forbidden = (
        FIXTURE / ".gradle",
        FIXTURE / "build",
        FIXTURE / "gradle-user-home",
        FIXTURE / "project-cache",
        FIXTURE / "test-results",
    )
    present = [str(path.relative_to(ROOT)) for path in forbidden if path.exists()]
    require(not present, f"generated state exists in source example: {present}")
    logs = list(FIXTURE.rglob("*.log"))
    require(not logs, f"generated logs exist in source example: {logs}")


def copy_fixture(destination: Path) -> Path:
    project = destination / "project"
    shutil.copytree(FIXTURE, project, symlinks=True)
    return project


def seed_wrapper_distribution(source: Path | None, gradle_home: Path) -> None:
    if source is None:
        return
    expected_name = "gradle-9.5.1-bin"
    require(source.is_absolute(), "wrapper distribution cache must be absolute")
    require(source.name == expected_name, f"cache basename must be {expected_name}")
    require(source.is_dir() and not source.is_symlink(), "invalid wrapper distribution cache")
    archives = list(source.glob("*/gradle-9.5.1-bin.zip"))
    require(len(archives) == 1, "cache must contain one Gradle 9.5.1 distribution ZIP")
    archive = archives[0]
    require(archive.is_file() and not archive.is_symlink(), "invalid distribution ZIP")
    require(
        sha256(archive) == GRADLE_DISTRIBUTION_SHA256,
        "cached Gradle distribution ZIP failed the wrapper-pinned SHA-256",
    )
    relative = archive.relative_to(source)
    target = gradle_home / "wrapper" / "dists" / expected_name / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archive, target)
    require(not target.with_suffix(target.suffix + ".ok").exists(),
            "seeded wrapper ZIP must be revalidated and extracted by the wrapper")


def fresh_cache_precondition(gradle_home: Path, project_cache: Path) -> None:
    require(not (gradle_home / "caches" / "modules-2").exists(),
            "dependency module cache was not fresh")
    require(not project_cache.exists(), "project cache was not fresh")
    matches = list(gradle_home.rglob("routecontract-shardingsphere-5.5-0.1.2.jar"))
    require(not matches, "RouteContract JAR existed before the online negative")


def invoke(
    project: Path,
    gradle_home: Path,
    project_cache: Path,
    java_home: Path,
    arguments: list[str],
) -> subprocess.CompletedProcess[str]:
    scenario_home = gradle_home / "home"
    scenario_tmp = gradle_home.parent / "tmp"
    scenario_home.mkdir(parents=True, exist_ok=True)
    scenario_tmp.mkdir(parents=True, exist_ok=True)
    environment = {
        "JAVA_HOME": str(java_home),
        "GRADLE_USER_HOME": str(gradle_home),
        "HOME": str(scenario_home),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
        "TMPDIR": str(scenario_tmp),
        "LANG": "C",
        "LC_ALL": "C",
    }
    for proxy_name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    ):
        if proxy_name in os.environ:
            environment[proxy_name] = os.environ[proxy_name]
    command = [
        str(project / "gradlew"),
        "-p",
        str(project),
        "--no-daemon",
        "--no-build-cache",
        "--console=plain",
        "--dependency-verification=strict",
        "--project-cache-dir",
        str(project_cache),
        "-Dorg.gradle.java.installations.auto-detect=false",
        f"-Dorg.gradle.java.installations.paths={java_home}",
        *arguments,
    ]
    return subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def verify_wrapper_launch(
    project: Path, gradle_home: Path, java_home: Path
) -> None:
    probe_cache = gradle_home.parent / "version-project-cache"
    result = invoke(project, gradle_home, probe_cache, java_home, ["--version"])
    require(result.returncode == 0, "Gradle wrapper --version failed:\n" + result.stdout)
    require("Gradle 9.5.1" in result.stdout, "wrapper did not launch exact Gradle 9.5.1")
    require(
        not (gradle_home / "caches" / "modules-2").exists(),
        "wrapper version probe populated a dependency module cache",
    )


def require_failure(
    result: subprocess.CompletedProcess[str], marker: str, scenario: str
) -> None:
    require(result.returncode != 0, f"{scenario} unexpectedly succeeded")
    require(marker in result.stdout, f"{scenario} missed failure marker {marker!r}")
    for success_marker in SUCCESS_MARKERS:
        require(
            success_marker not in result.stdout,
            f"{scenario} emitted success marker {success_marker}",
        )


def replace_exact(path: Path, old: str, new: str, scenario: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    require(count == 1, f"{scenario}: expected one substitution target, found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--java-home",
        type=Path,
        default=Path(os.environ["JAVA_HOME"]) if os.environ.get("JAVA_HOME") else None,
        help="absolute JDK 17 home (or set JAVA_HOME)",
    )
    parser.add_argument(
        "--wrapper-distribution-cache",
        type=Path,
        help=(
            "optional gradle-9.5.1-bin wrapper cache directory containing the exact "
            "distribution ZIP; its pinned SHA-256 is checked and only the ZIP is copied, "
            "never extracted files, .ok markers, or dependency caches"
        ),
    )
    arguments = parser.parse_args()
    require(arguments.java_home is not None, "set --java-home or JAVA_HOME to JDK 17")
    java_home = arguments.java_home.resolve(strict=True)
    require(java_home.is_absolute(), "JAVA_HOME must be absolute")

    verify_wrapper()
    verify_java_home(java_home)
    assert_fixture_clean()

    with tempfile.TemporaryDirectory(
        prefix="routecontract-gradle-direct-release-verifier-"
    ) as temporary_text:
        temporary = Path(temporary_text)

        # This is deliberately the first dependency-resolution case. The dependency cache
        # and project cache begin absent; --refresh-dependencies forces an online read.
        wrong_verification_root = temporary / "01-wrong-verification-sha"
        wrong_verification_project = copy_fixture(wrong_verification_root)
        metadata = wrong_verification_project / "gradle" / "verification-metadata.xml"
        replace_exact(
            metadata,
            f'<sha256 value="{ROUTECONTRACT_SHA256}" origin="Generated by Gradle"/>',
            f'<sha256 value="{WRONG_SHA256}" origin="intentional verifier negative"/>',
            "wrong-verification-sha",
        )
        wrong_verification_home = wrong_verification_root / "gradle-home"
        wrong_verification_cache = wrong_verification_root / "project-cache"
        seed_wrapper_distribution(
            arguments.wrapper_distribution_cache, wrong_verification_home
        )
        verify_wrapper_launch(
            wrong_verification_project, wrong_verification_home, java_home
        )
        if wrong_verification_cache.exists():
            shutil.rmtree(wrong_verification_cache)
        fresh_cache_precondition(wrong_verification_home, wrong_verification_cache)
        wrong_verification = invoke(
            wrong_verification_project,
            wrong_verification_home,
            wrong_verification_cache,
            java_home,
            ["--refresh-dependencies", "verifyRouteContractArtifact"],
        )
        require_failure(
            wrong_verification,
            "Dependency verification failed",
            "wrong-verification-sha",
        )
        require(
            "routecontract-shardingsphere-5.5-0.1.2.jar" in wrong_verification.stdout,
            "wrong-verification-sha did not identify the first-party JAR",
        )
        require(
            not (wrong_verification_project / "build" / "verified-routecontract").exists(),
            "wrong-verification-sha staged an unverified JAR",
        )
        require(
            "> Task :compileJava" not in wrong_verification.stdout
            and "ROUTECONTRACT_DIRECT_RELEASE_RUNTIME_PROBE_VERIFIED"
            not in wrong_verification.stdout,
            "wrong-verification-sha reached compilation or runtime",
        )

        # Independently prove the fixed application-level SHA gate from another fresh cache.
        wrong_stage_root = temporary / "02-wrong-staging-sha"
        wrong_stage_project = copy_fixture(wrong_stage_root)
        build_file = wrong_stage_project / "build.gradle.kts"
        replace_exact(
            build_file,
            f'val routeContractSha256 =\n    "{ROUTECONTRACT_SHA256}"',
            f'val routeContractSha256 =\n    "{WRONG_SHA256}"',
            "wrong-staging-sha",
        )
        wrong_stage_home = wrong_stage_root / "gradle-home"
        wrong_stage_cache = wrong_stage_root / "project-cache"
        seed_wrapper_distribution(arguments.wrapper_distribution_cache, wrong_stage_home)
        fresh_cache_precondition(wrong_stage_home, wrong_stage_cache)
        wrong_stage = invoke(
            wrong_stage_project,
            wrong_stage_home,
            wrong_stage_cache,
            java_home,
            ["--refresh-dependencies", "verifyRouteContractArtifact"],
        )
        require_failure(
            wrong_stage,
            "ROUTECONTRACT_ARTIFACT_SHA256_MISMATCH",
            "wrong-staging-sha",
        )
        require(
            not (wrong_stage_project / "build" / "verified-routecontract"
                 / "routecontract-shardingsphere-5.5-0.1.2.jar").exists(),
            "wrong-staging-sha retained a staged JAR",
        )
        require(
            "> Task :compileJava" not in wrong_stage.stdout
            and "ROUTECONTRACT_DIRECT_RELEASE_RUNTIME_PROBE_VERIFIED"
            not in wrong_stage.stdout,
            "wrong-staging-sha reached compilation or runtime",
        )

        wrong_metadata_root = temporary / "03-wrong-maven-metadata"
        wrong_metadata_project = copy_fixture(wrong_metadata_root)
        wrong_metadata_file = wrong_metadata_project / "gradle" / "verification-metadata.xml"
        replace_exact(
            wrong_metadata_file,
            f'<sha256 value="{TTL_POM_SHA256}" origin="Generated by Gradle"/>',
            f'<sha256 value="{WRONG_SHA256}" origin="intentional verifier negative"/>',
            "wrong-maven-metadata",
        )
        wrong_metadata_home = wrong_metadata_root / "gradle-home"
        wrong_metadata_cache = wrong_metadata_root / "project-cache"
        seed_wrapper_distribution(arguments.wrapper_distribution_cache, wrong_metadata_home)
        fresh_cache_precondition(wrong_metadata_home, wrong_metadata_cache)
        wrong_metadata = invoke(
            wrong_metadata_project,
            wrong_metadata_home,
            wrong_metadata_cache,
            java_home,
            ["--refresh-dependencies", "verifyRuntimeClasspath"],
        )
        require(wrong_metadata.returncode != 0, "wrong-maven-metadata unexpectedly succeeded")
        require(
            "Dependency verification failed" in wrong_metadata.stdout,
            "wrong-maven-metadata missed Gradle's strict verification failure",
        )
        require(
            "transmittable-thread-local-2.14.2.pom" in wrong_metadata.stdout,
            "wrong-maven-metadata did not identify the exact Maven POM",
        )
        require(
            "ROUTECONTRACT_DIRECT_RELEASE_RUNTIME_CLASSPATH_VERIFIED"
            not in wrong_metadata.stdout
            and "> Task :compileJava" not in wrong_metadata.stdout
            and "ROUTECONTRACT_DIRECT_RELEASE_RUNTIME_PROBE_VERIFIED"
            not in wrong_metadata.stdout,
            "wrong-maven-metadata reached runtime verification or compilation",
        )

        positive_root = temporary / "04-positive"
        positive_project = copy_fixture(positive_root)
        positive_home = positive_root / "gradle-home"
        positive_cache = positive_root / "project-cache"
        seed_wrapper_distribution(arguments.wrapper_distribution_cache, positive_home)
        fresh_cache_precondition(positive_home, positive_cache)
        positive = invoke(
            positive_project,
            positive_home,
            positive_cache,
            java_home,
            ["--refresh-dependencies", "clean", "check"],
        )
        require(positive.returncode == 0, "positive run failed:\n" + positive.stdout)
        for marker in SUCCESS_MARKERS:
            require(marker in positive.stdout, f"positive run missed {marker}")
        require(
            "routecontractRuntimeJdk=17" in positive.stdout,
            "positive run did not prove JDK 17",
        )
        require(
            "routecontractRuntimeShardingSphereVersion=5.5.3" in positive.stdout,
            "positive run did not prove the ShardingSphere 5.5.3 graph",
        )
        require(
            "routecontractJavaProviderTypeOriginVerifiedBeforeInstantiation=true"
            in positive.stdout,
            "positive run did not prove Java Provider.type origin ordering",
        )
        require(
            "routecontractShardingSphereLoaderRole=post-verification-compatibility"
            in positive.stdout,
            "positive run overstated the ShardingSphere loader boundary",
        )

        offline = invoke(
            positive_project,
            positive_home,
            positive_cache,
            java_home,
            ["--offline", "clean", "check"],
        )
        require(offline.returncode == 0, "offline repeat failed:\n" + offline.stdout)
        for marker in SUCCESS_MARKERS:
            require(marker in offline.stdout, f"offline repeat missed {marker}")

    assert_fixture_clean()
    print("gradleWrapper=examples/gradle-direct-release/gradlew")
    print("gradleVersion=9.5.1")
    print("runtimeJdk=17")
    print("dependencyVerification=strict-full-resolved-closure-and-metadata")
    print("wrongShaFirstResolution=fresh-online-cache-rejected")
    print("ROUTECONTRACT_GRADLE_DIRECT_RELEASE_VERIFIER_PASSED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, subprocess.SubprocessError) as exception:
        print(f"ERROR: {exception}", file=sys.stderr)
        raise SystemExit(1)
