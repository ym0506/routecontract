#!/usr/bin/env python3
"""Compile and run the printed install snippets in three fresh-cache consumers.

The input is an already checked local v0.1.2 repository. This command does not
install, rebuild or publish RouteContract and does not exercise SQL capture.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SUITE = "io.github.ym0506.routecontract.installsmoke.InstalledManifestTest"
JAVA_TEST = (ROOT / "examples/local-install-smoke/src/test/java/io/github/ym0506/routecontract"
             / "installsmoke/InstalledManifestTest.java")
FORMATS = ("gradle", "gradle-kotlin", "maven")
WRAPPER_FILES = (
    "gradlew", "gradlew.bat", "gradle/wrapper/gradle-wrapper.jar",
    "gradle/wrapper/gradle-wrapper.properties",
)


def load_renderer():
    spec = importlib.util.spec_from_file_location(
        "routecontract_local_install", ROOT / "scripts/install-local.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_fixture(project: Path) -> None:
    source = project / "src/test/java/io/github/ym0506/routecontract/installsmoke"
    resources = project / "src/test/resources"
    source.mkdir(parents=True)
    resources.mkdir(parents=True)
    shutil.copyfile(JAVA_TEST, source / JAVA_TEST.name)
    for role in ("approved", "candidate"):
        name = f"find-paid-orders-by-user.{role}.json"
        shutil.copyfile(ROOT / "examples/manifests" / name, resources / name)


def write_gradle(project: Path, repository: Path, renderer, *, kotlin: bool) -> None:
    for relative in WRAPPER_FILES:
        destination = project / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    suffix = ".gradle.kts" if kotlin else ".gradle"
    (project / f"settings{suffix}").write_text(
        'rootProject.name = "routecontract-local-install-smoke"\n', encoding="utf-8")
    if kotlin:
        prelude = 'plugins { java }\n'
        configuration = '''
java { toolchain { languageVersion.set(JavaLanguageVersion.of(17)) } }
tasks.test { useJUnitPlatform() }
'''
    else:
        prelude = 'plugins { id("java") }\n'
        configuration = '''
java { toolchain { languageVersion = JavaLanguageVersion.of(17) } }
test { useJUnitPlatform() }
'''
    # These are the same bytes users receive from install-local.py. The fixture
    # adds only its Java/JUnit test harness; runtime libraries come from the POM.
    (project / f"build{suffix}").write_text(
        prelude + renderer.gradle_configuration(repository) + '''

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.14.3"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
''' + configuration, encoding="utf-8")


def write_maven(project: Path, repository: Path, renderer) -> None:
    # Maven requires one dependencies element, so add the fixture dependency
    # inside the rendered block while retaining its original RouteContract XML.
    fragment = renderer.maven_configuration(repository).replace(
        "</dependencies>", '''  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>5.14.3</version>
    <scope>test</scope>
  </dependency>
</dependencies>''')
    (project / "pom.xml").write_text('''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>io.github.ym0506.routecontract.examples</groupId>
  <artifactId>local-install-smoke</artifactId>
  <version>1.0.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
''' + fragment + '''
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.4</version>
      </plugin>
    </plugins>
  </build>
</project>
''', encoding="utf-8")
    (project / "settings.xml").write_text(
        '<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"/>\n', encoding="utf-8")


def run_command(command: list[str], project: Path, environment: dict[str, str], log: Path) -> None:
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run(command, cwd=project, env=environment,
                                stdin=subprocess.DEVNULL, stdout=output,
                                stderr=subprocess.STDOUT, timeout=1200, check=False)
    if result.returncode:
        raise RuntimeError(f"consumer command exited {result.returncode}; inspect {log}")


def junit_counts(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    if root.tag != "testsuite" or root.get("name") != SUITE:
        raise RuntimeError(f"unexpected JUnit suite in {path}")
    counts = {field: int(root.attrib[field]) for field in ("tests", "failures", "errors", "skipped")}
    if counts != {"tests": 3, "failures": 0, "errors": 0, "skipped": 0}:
        raise RuntimeError(f"consumer did not run three passing tests: {counts}; inspect {path}")
    if len(root.findall("testcase")) != 3:
        raise RuntimeError(f"consumer JUnit testcase count differs: {path}")
    return counts


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path,
                        help="already installed checked v0.1.2 Maven repository")
    parser.add_argument("--work-dir", required=True, type=Path,
                        help="new absolute output directory; all three caches begin absent")
    args = parser.parse_args(argv)
    repository = args.repository.resolve(strict=True)
    if not repository.is_dir():
        parser.error("--repository must be an existing directory")
    work = args.work_dir
    if not work.is_absolute() or work.exists() or work.is_symlink():
        parser.error("--work-dir must be a new absent absolute directory")
    if not work.parent.is_dir():
        parser.error("--work-dir parent must already exist")
    if work.resolve().is_relative_to(repository):
        parser.error("--work-dir must be outside the installed repository")
    maven = shutil.which("mvn")
    if maven is None:
        parser.error("mvn is required")
    work.mkdir(mode=0o700)
    renderer = load_renderer()
    results = []
    for format_name in FORMATS:
        print(f"LOCAL_INSTALL_CONSUMER format={format_name} state=RUNNING", flush=True)
        project = work / format_name
        write_fixture(project)
        environment = os.environ.copy()
        if format_name.startswith("gradle"):
            write_gradle(project, repository, renderer, kotlin=format_name == "gradle-kotlin")
            environment["GRADLE_USER_HOME"] = str(project / "gradle-user-home")
            common = [str(project / "gradlew"), "--no-daemon", "--no-build-cache",
                      "--no-configuration-cache", "--console=plain"]
            version_command = [*common, "--version"]
            command = [*common, "--refresh-dependencies", "clean", "test"]
            report = project / "build/test-results/test" / f"TEST-{SUITE}.xml"
        else:
            write_maven(project, repository, renderer)
            common = [maven, "--batch-mode", "--no-transfer-progress",
                      "--settings", str(project / "settings.xml"),
                      "--global-settings", str(project / "settings.xml"),
                      f"-Dmaven.repo.local={project / 'maven-local'}"]
            version_command = [maven, "--version"]
            command = [*common, "clean", "test"]
            report = project / "target/surefire-reports" / f"TEST-{SUITE}.xml"
        run_command(version_command, project, environment, project / "versions.log")
        run_command(command, project, environment, project / "build.log")
        counts = junit_counts(report)
        results.append({"format": format_name, "command": command, "junit": str(report),
                        "versions": str(project / "versions.log"), **counts})
        print(f"LOCAL_INSTALL_CONSUMER format={format_name} state=VERIFIED tests=3", flush=True)
    summary = {"scope": "published v0.1.2 manifest API and POM transitive dependencies; no SQL execution",
               "repository": str(repository), "consumers": results}
    (work / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"LOCAL_INSTALL_CONSUMERS_VERIFIED formats=3 tests=9 summary={work / 'summary.json'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run(sys.argv[1:]))
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f"Local install consumer verification failed: {error}") from error
