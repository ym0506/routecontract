#!/usr/bin/env python3
"""Run the public example's direct assertions and verify their failure and recovery."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET


EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "first-project"
TEST_NAME = "paidOrdersKeepTheirBusinessResultAndExecutionContract"
CLASS_NAME = "io.github.ym0506.routecontract.examples.firstproject.OrderContractTest"
VIOLATION = "io.github.ym0506.routecontract.RouteContractViolationException"
PUBLIC_JAR_SHA256 = "9e883e618eb09d9ecf30814151bb4b0a43eba02c78d288cc582fa7e57e6edba2"


def manifest_files():
    """Include existing reports so direct mode cannot quietly remove or replace them."""
    return {
        str(path.relative_to(EXAMPLE)): hashlib.sha256(path.read_bytes()).hexdigest()
        for directory in (EXAMPLE / "baselines", EXAMPLE / "build/routecontract")
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("Maven", "Gradle"):
        raise SystemExit("usage: verify_first_project_direct_assertions.py Maven|Gradle")
    build = sys.argv[1]
    expected_java = int(os.environ.get("ROUTECONTRACT_EXAMPLE_JAVA_VERSION", "17"))
    if expected_java not in (17, 21):
        raise SystemExit("ROUTECONTRACT_EXAMPLE_JAVA_VERSION must be 17 or 21")
    evidence = EXAMPLE / "build/lifecycle-evidence/direct-assertions" / build.lower()
    evidence.mkdir(parents=True, exist_ok=True)
    for name in ("summary.json", "match.log", "match.xml", "range.log", "range.xml",
                 "restored.log", "restored.xml"):
        (evidence / name).unlink(missing_ok=True)
    if build == "Maven":
        command = ["mvn", "-B", "test", "-Droutecontract.mode=assert",
                   "-Droutecontract.baseline=build/routecontract/candidate.json"]
        query_option = "-Droutecontract.query="
        junit = EXAMPLE / "target/surefire-reports" / f"TEST-{CLASS_NAME}.xml"
    else:
        command = [str(EXAMPLE.parents[1] / "gradlew"), "-p", ".", "test", "--rerun-tasks",
                   "-ProutecontractMode=assert",
                   "-ProutecontractBaseline=build/routecontract/candidate.json"]
        query_option = "-ProutecontractQuery="
        junit = EXAMPLE / "build/test-results/test" / f"TEST-{CLASS_NAME}.xml"

    before = manifest_files()
    stages = []
    for stage, query, count in (("match", "equality", 1), ("range", "range", 2),
                                ("restored", "equality", 1)):
        # A setup failure must not pass by reusing the previous command's test report.
        junit.unlink(missing_ok=True)
        args = command + [query_option + query]
        log = evidence / f"{stage}.log"
        with log.open("w", encoding="utf-8") as output:
            result = subprocess.run(args, cwd=EXAMPLE, stdout=output, stderr=subprocess.STDOUT,
                                    timeout=600, check=False)
        assert manifest_files() == before, "Direct mode changed manifest/baseline/report files"
        suite = ET.parse(junit).getroot()
        (evidence / f"{stage}.xml").write_bytes(junit.read_bytes())
        failures = "1" if query == "range" else "0"
        assert tuple(suite.get(key) for key in ("tests", "failures", "errors", "skipped")) == (
            "1", failures, "0", "0"), f"Unexpected JUnit outcome: {stage}; see {log}"
        cases = suite.findall("testcase")
        assert len(cases) == 1 and cases[0].get("name") in (TEST_NAME, TEST_NAME + "()")
        output = log.read_text(encoding="utf-8")
        runtime_marker = (f"ROUTECONTRACT_RUNTIME java={expected_java} classMajor={expected_java + 44} "
                          f"libraryClassMajor=61 jarSha256={PUBLIC_JAR_SHA256}")
        assert runtime_marker in output, f"Actual JVM/classfile/public artifact not verified: {stage}"
        assert "Business assertion passed: the exact expected order was returned." in output
        assert f"Direct assertions: observed attempts={count}, data sources={count};" in output
        if query == "range":
            failure = cases[0].find("failure")
            assert result.returncode != 0 and failure is not None
            assert failure.get("type") == VIOLATION
            assert "expected at most 1 observed physical attempts, but observed 2" in (
                failure.get("message", "") + "".join(failure.itertext()))
        else:
            assert result.returncode == 0
            assert "Direct assertions passed. No JSON baseline or report was used." in output
        stages.append({"stage": stage, "query": query, "exitCode": result.returncode,
                       "businessAssertionPassed": True, "observedAttempts": count,
                       "observedDataSources": count, "manifestFilesUnchanged": True})
        print(f"{build}: direct {stage} verified ({count} attempts / {count} data sources)", flush=True)

    (evidence / "summary.json").write_text(json.dumps({
        "buildTool": build, "libraryVersion": "0.1.3", "javaFeature": expected_java,
        "exampleClassMajor": expected_java + 44, "libraryClassMajor": 61,
        "publicJarSha256": PUBLIC_JAR_SHA256, "stages": stages,
        "protectedFiles": before, "baselineArgumentIgnored": command[-1],
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
