#!/usr/bin/env python3
"""Run both real-MySQL commands; accept only the documented failure reason."""

import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CLASS = "io.github.ym0506.routecontract.experiments.shadow.ShadowInsertSelectTest"
METHOD = "insertSelectReturnsOneButWritesToShadow"
MESSAGE = (
    "Route contract violation for operation 'insert-select-nonmatching': "
    "expected observed data-source names [primary], but observed [shadow]"
)
EXPECTED_RESULTS = {
    "RESULT case=values-nonmatching affected=1 attempts=1 dataSources=[primary] primaryRows=1 shadowRows=0",
    "RESULT case=values-matching affected=1 attempts=1 dataSources=[shadow] primaryRows=0 shadowRows=1",
    "RESULT case=insert-select-nonmatching affected=1 attempts=1 dataSources=[shadow] primaryRows=0 shadowRows=1",
}


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def run(enforce):
    # Logs are outside target because `mvn clean` removes that directory.
    output = ROOT / "build" / "verification"
    output.mkdir(parents=True, exist_ok=True)
    name = "enforced" if enforce else "characterization"
    command = ["mvn", "-B", "-ntp", "clean", "test"]
    if enforce:
        command += ["-Dshadow.enforceProduction=true", f"-Dtest=ShadowInsertSelectTest#{METHOD}"]
    for stale in (ROOT / "target" / "surefire-reports").glob("TEST-*.xml"):
        stale.unlink()
    with (output / f"{name}.log").open("w") as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                timeout=600, check=False)
    require(result.returncode == (1 if enforce else 0), f"Unexpected {name} Maven exit; inspect build/verification/{name}.log")
    reports = ROOT / "target" / "surefire-reports"
    xml_files = list(reports.glob("TEST-*.xml"))
    require(len(xml_files) == 1, f"Expected one fresh JUnit suite for {name}")
    suite = ET.parse(xml_files[0]).getroot()
    require(suite.get("name") == CLASS, "Unexpected JUnit class")
    totals = tuple(suite.get(k) for k in ("tests", "failures", "errors", "skipped"))
    require(totals == (("1", "1", "0", "0") if enforce else ("3", "0", "0", "0")),
            f"Unexpected {name} JUnit totals: {totals}")
    cases = suite.findall("testcase")
    require(len(cases) == (1 if enforce else 3), "JUnit count does not match actual test cases")
    if enforce:
        require(cases[0].get("name") == METHOD, "Unexpected enforcing test")
        failure = cases[0].find("failure")
        require(failure is not None, "Missing expected failure")
        require(failure.get("type") == "io.github.ym0506.routecontract.RouteContractViolationException",
                "The enforcing test failed with a different exception")
        require(failure.get("message") == MESSAGE, "The contract failed for a different reason")
    else:
        require({case.get("name") for case in cases} == {
            METHOD, "matchingValuesUseShadow", "nonMatchingValuesUsePrimary"
        }, "Characterization controls are missing")
    lines = (reports / f"{CLASS}-output.txt").read_text().splitlines()
    results = [line for line in lines if line.startswith("RESULT ")]
    expected = {line for line in EXPECTED_RESULTS if "insert-select-nonmatching" in line} if enforce else EXPECTED_RESULTS
    require(set(results) == expected and len(results) == len(expected), "Physical destination evidence differs")
    properties = {prop.get("name"): prop.get("value") for prop in suite.findall("properties/property")
                  if prop.get("name") in ("java.version", "java.vendor", "os.name", "os.arch")}
    require(properties.get("java.version", "").startswith("17."), "This reproduction verifies Java 17")
    return {
        "command": command, "exitCode": result.returncode,
        "tests": int(totals[0]), "failures": int(totals[1]), "errors": int(totals[2]), "skipped": int(totals[3]),
        "testRuntime": properties, "results": sorted(results),
        "expectedFailure": MESSAGE if enforce else None,
    }


def main():
    output = ROOT / "build" / "verification"
    # Never leave an earlier success report behind if a fresh run fails.
    (output / "evidence.json").unlink(missing_ok=True)
    report = {"characterization": run(False), "enforcedContract": run(True)}
    (output / "evidence.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Verified: three real-MySQL controls; primary-only contract rejects the shadow destination.")
    print("Selected evidence: build/verification/evidence.json")


if __name__ == "__main__":
    main()
