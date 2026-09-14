#!/usr/bin/env python3
"""Require Java 21 workers for all five modules and the complete release corpus."""

import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "release_test_summary", ROOT / "scripts/summarize-test-results.py")
release_summary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_summary)

MODULES = (
    ("core", "routecontract-core"),
    ("adapter553", "routecontract-shardingsphere-5.5"),
    ("adapter552", "routecontract-shardingsphere-5.5.2"),
    ("mysql553", "examples/mysql"),
    ("mysql552", "examples/mysql-5.5.2"),
)
LIBRARY_ENTRIES = (
    "io/github/ym0506/routecontract/RouteContract.class",
    "io/github/ym0506/routecontract/shardingsphere553/internal/RouteContract553SqlExecutionHook.class",
    "io/github/ym0506/routecontract/shardingsphere552/internal/RouteContract552SqlExecutionHook.class",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: summarize_java_runtime.py GRADLE_LOG JAVA_HOME OUTPUT_JSON")
    log = Path(sys.argv[1]).read_text(encoding="utf-8")
    java = Path(sys.argv[2]).resolve() / "bin/java"
    runtime = subprocess.run([str(java), "-XshowSettings:properties", "-version"],
                             capture_output=True, text=True, check=True)
    details = runtime.stdout + runtime.stderr
    feature = re.search(r"(?m)^\s*java\.specification\.version = (\d+)\s*$", details)
    require(feature is not None and feature.group(1) == "21", "Expected an actual Java 21 runtime")
    version = re.search(r"(?m)^\s*java\.version = (\S+)\s*$", details)
    require(version is not None, "Missing actual Java runtime version")
    workers = [line for line in log.splitlines() if "Starting process 'Gradle Test Executor" in line]
    directories = [(name, (ROOT / relative).resolve()) for name, relative in MODULES]
    worker_markers = {name: f"Working directory: {directory} Command: {java} "
                      for name, directory in directories}
    for name, marker in worker_markers.items():
        require(any(marker in line for line in workers),
                f"Missing actual Java 21 test-worker launch for {name}; up-to-date tasks are insufficient")
    require(all(any(marker in line for marker in worker_markers.values()) for line in workers),
            "A test worker used a different JVM or an unexpected module directory")

    observed = release_summary.read_verified_results([
        directory / "build/test-results/test" for _, directory in directories])

    library_classes = []
    for (name, directory), entry in zip(directories[:3], LIBRARY_ENTRIES):
        classes = directory / "build/classes/java/main"
        require((classes / entry).is_file(), f"Missing production entry class for {name}")
        compiled = sorted(classes.rglob("*.class"))
        for path in compiled:
            require(path.is_file() and not path.is_symlink(), f"Invalid production class: {path}")
            with path.open("rb") as stream:
                header = stream.read(8)
            require(len(header) == 8, f"Truncated class header: {path}")
            magic, _, major = struct.unpack(">IHH", header)
            require(magic == 0xCAFEBABE and major == 61,
                    f"Library must retain Java 17 class compatibility: {path}")
        library_classes.append({"module": name, "classFiles": len(compiled), "major": 61})

    modules = []
    projections = []
    evidence_dir = Path(sys.argv[3]).parent / "java21-runtime-junit"
    for name, directory in directories:
        reports = sorted((directory / "build/test-results/test").glob("TEST-*.xml"))
        require(bool(reports), f"Missing {name} JUnit results")
        totals = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
        minimized = ET.Element("testsuite", {"name": f"routecontract-{name}-java21"})
        for report in reports:
            suite = ET.parse(report).getroot()
            for key in totals:
                totals[key] += observed[suite.get("name")][key]
            for case in suite.findall("testcase"):
                clean_case = ET.SubElement(minimized, "testcase", {
                    key: case.get(key, "") for key in ("name", "classname", "time")})
                for status in ("failure", "error", "skipped"):
                    child = case.find(status)
                    if child is not None:
                        ET.SubElement(clean_case, status, {"type": child.get("type", status)})
        minimized.attrib.update({key: str(value) for key, value in totals.items()})
        # Preserve outcomes and case identities without framework stdout/stderr,
        # host properties, connection details or failure payloads.
        projections.append((evidence_dir / f"{name}.xml", minimized))
        modules.append({"module": name, "reportFiles": len(reports), **totals})

    summary = {"javaFeature": 21, "javaVersion": version.group(1), "javaExecutable": str(java),
               "workerLaunches": len(workers), "libraryClassMajor": 61,
               "libraryClasses": library_classes, "modules": modules,
               "junitEvidence": "Minimized case/outcome projection; original stdout/stderr and failure payloads omitted",
               "scope": "Existing unit and synthetic MySQL corpora; not arbitrary async/virtual-thread or adoption evidence"}
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for destination, minimized in projections:
        ET.ElementTree(minimized).write(destination, encoding="utf-8", xml_declaration=True)
    Path(sys.argv[3]).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
