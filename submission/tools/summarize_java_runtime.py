#!/usr/bin/env python3
"""Require actual Java 21 worker launches and successful existing test corpora."""

import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: summarize_java_runtime.py GRADLE_LOG JAVA_HOME OUTPUT_JSON")
    log = Path(sys.argv[1]).read_text(encoding="utf-8")
    java = Path(sys.argv[2]).resolve() / "bin/java"
    runtime = subprocess.run([str(java), "-XshowSettings:properties", "-version"],
                             capture_output=True, text=True, check=True)
    details = runtime.stdout + runtime.stderr
    feature = re.search(r"(?m)^\s*java\.specification\.version = (\d+)\s*$", details)
    assert feature is not None and feature.group(1) == "21", "Expected an actual Java 21 runtime"
    version = re.search(r"(?m)^\s*java\.version = (\S+)\s*$", details)
    assert version is not None
    workers = [line for line in log.splitlines() if "Starting process 'Gradle Test Executor" in line]
    assert len(workers) >= 2, "Missing actual core/MySQL test-worker launches; up-to-date tasks are insufficient"
    assert all(f"Command: {java} " in line for line in workers), "A test worker used a different JVM"

    modules = []
    evidence_dir = Path(sys.argv[3]).parent / "java21-runtime-junit"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for name, directory in (("core", ROOT / "routecontract-shardingsphere-5.5"),
                            ("mysql", ROOT / "examples/mysql")):
        reports = sorted((directory / "build/test-results/test").glob("TEST-*.xml"))
        assert reports, f"Missing {name} JUnit results"
        totals = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
        minimized = ET.Element("testsuite", {"name": f"routecontract-{name}-java21"})
        for report in reports:
            suite = ET.parse(report).getroot()
            for key in totals:
                totals[key] += int(suite.get(key, "0"))
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
        ET.ElementTree(minimized).write(evidence_dir / f"{name}.xml", encoding="utf-8",
                                        xml_declaration=True)
        assert totals["tests"] > 0, f"No {name} tests ran"
        assert all(totals[key] == 0 for key in ("failures", "errors", "skipped")), totals
        modules.append({"module": name, "reportFiles": len(reports), **totals})

    library_class = (ROOT / "routecontract-shardingsphere-5.5/build/classes/java/main"
                     / "io/github/ym0506/routecontract/RouteContract.class")
    magic, _, major = struct.unpack(">IHH", library_class.read_bytes()[:8])
    assert magic == 0xCAFEBABE and major == 61, "Library must retain Java 17 class compatibility"
    summary = {"javaFeature": 21, "javaVersion": version.group(1), "javaExecutable": str(java),
               "workerLaunches": len(workers), "libraryClassMajor": major, "modules": modules,
               "junitEvidence": "Minimized case/outcome projection; original stdout/stderr and failure payloads omitted",
               "scope": "Existing unit and synthetic MySQL corpora; not arbitrary async/virtual-thread or adoption evidence"}
    Path(sys.argv[3]).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
