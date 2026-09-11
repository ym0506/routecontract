#!/usr/bin/env python3
"""Render the first-project rehearsal from verified stages, including partial failures."""

import json
import os
from pathlib import Path
import sys


STAGES = (
    ("match", "1. Normal query", "MATCH", 1),
    ("range", "2. Same-result range query", "POLICY_VIOLATION", 2),
    ("restored", "3. Normal query restored", "MATCH", 1),
)
PUBLIC_JAR_SHA256 = "9e883e618eb09d9ecf30814151bb4b0a43eba02c78d288cc582fa7e57e6edba2"


def verified_direct_runtime(evidence, outcome, build_tool, java_feature):
    """Cross-check the producer's completed direct/runtime verification with this job."""
    if (outcome != "success" or build_tool not in ("Maven", "Gradle")
            or type(java_feature) is not int or java_feature not in (17, 21)):
        return False
    try:
        path = evidence / "direct-assertions" / build_tool.lower() / "summary.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        if (report["buildTool"] != build_tool or report["libraryVersion"] != "0.1.3"
                or report["publicJarSha256"] != PUBLIC_JAR_SHA256):
            return False
        for field, expected in (("javaFeature", java_feature),
                                ("exampleClassMajor", java_feature + 44), ("libraryClassMajor", 61)):
            if type(report[field]) is not int or report[field] != expected:
                return False
        stages = report["stages"]
        if not isinstance(stages, list) or len(stages) != 3:
            return False
        expected_stages = (("match", "equality", 0, 1), ("range", "range", 1, 2),
                           ("restored", "equality", 0, 1))
        for stage, (name, query, exit_code, count) in zip(stages, expected_stages):
            if (stage["stage"] != name or stage["query"] != query
                    or stage["businessAssertionPassed"] is not True
                    or stage["manifestFilesUnchanged"] is not True):
                return False
            for field, expected in (("exitCode", exit_code), ("observedAttempts", count),
                                    ("observedDataSources", count)):
                if type(stage[field]) is not int or stage[field] != expected:
                    return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def verified_observation(path, status, count):
    """Only return fixture counts; never copy free-form input into the summary."""
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        candidate = report["candidate"]
        matched = status == "MATCH"
        if (report["status"] != status or report["matched"] is not matched
                or type(report["strictExitCode"]) is not int
                or report["strictExitCode"] != (0 if matched else 1)
                or candidate["captureStatus"] != "COMPLETE"):
            return None
        for field in ("observedPhysicalAttemptCount", "distinctObservedDataSourceNameCount"):
            if type(candidate[field]) is not int or candidate[field] != count:
                return None
        codes = [finding["code"] for finding in report["findings"]]
        if sorted(codes) != (["RCM000"] if matched else ["RCM201", "RCM202"]):
            return None
        return count
    except (OSError, ValueError, KeyError, TypeError):
        return None


def render(evidence, outcomes, build_tool="Maven", java_feature=17):
    direct_verified = verified_direct_runtime(
        evidence, outcomes.get("direct"), build_tool, java_feature)
    context_valid = (build_tool in ("Maven", "Gradle") and type(java_feature) is int
                     and java_feature in (17, 21))
    artifact = (f"first-project-{build_tool}" + ("-java21" if java_feature == 21 else "")
                if context_valid else None)
    runtime = (f"Verified test runtime: **Java {java_feature}**; consumer classfile "
               f"**{java_feature + 44}**, public library classfile **61**."
               if direct_verified else
               "Test runtime: **Not verified**; inspect the direct/runtime verification step.")
    lines = [
        "# RouteContract: same result, different execution", "",
        "Public **0.1.3** · ShardingSphere-JDBC **5.5.3** · MySQL **8.4.11**", "",
        runtime, "",
        "Each verified stage checks the same synthetic order: **201 / user 3 / PAID**.", "",
        "| Stage | Verification | Contract | Physical JDBC attempts | Observed aliases |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    complete = outcomes.get("capture") == "success" and direct_verified
    range_verified = False
    for key, label, status, count in STAGES:
        observed = verified_observation(evidence / key / "review.json", status, count)
        verified = outcomes.get(key) == "success" and observed is not None
        complete = complete and verified
        if key == "range":
            range_verified = verified
        if verified:
            lines.append(f"| {label} | Verified | {status} | {observed} | {observed} |")
        else:
            lines.append(f"| {label} | Not verified; inspect the step | — | — | — |")
    lines += ["", "Direct Java assertions (pass → expected failure → pass; manifest files unchanged): "
              + ("**Verified**." if direct_verified else "**Not verified**."), "", (
        "**Demonstration complete.** The range-query test failed with the expected "
        "RouteContract assertion (**RCM201 / RCM202**), then the normal test passed again. "
        "All required demonstration stages verified that rejection and recovery. "
        "Capture did not approve a baseline; the supplied synthetic baseline stayed unchanged."
        if complete else
        "**Demonstration incomplete.** Inspect the failed or skipped steps above. "
        "A missing report, dependency, compiler or Docker failure does not demonstrate "
        "contract rejection. Earlier successful stages do not establish a completed run."
    ), "", (f"Download **{artifact}** from this run's " if artifact else "Inspect this run's ") +
        "Artifacts section. Under `build/lifecycle-evidence/`, `match/`, `range/` and "
        "`restored/` retain the verified candidate and JSON/Markdown reports. "
        "`range/review.md` explains the rejection.", "",
        "Next: follow **docs/first-project.md → Adapt one existing test** in your fork. "
        "Start with direct Java assertions for one operation; use a reviewed baseline when "
        "you need stored structural comparisons.", "",
        "Counts describe hook-reported physical JDBC execution attempts and observed aliases; "
        "they are not physical-table counts, a complete route plan or performance measurements. "
        "This synthetic rehearsal does not establish adoption in a real application.", ""]
    review = evidence / "range" / "review.md"
    if range_verified and review.is_file():
        lines += ["<details>", "<summary>Inspect the verified rejection report</summary>",
                  "", review.read_text(encoding="utf-8"), "", "</details>", ""]
    return "\n".join(lines), complete


if __name__ == "__main__":
    evidence = Path(sys.argv[1])
    outcomes = {key: os.environ.get(f"{key.upper()}_OUTCOME", "")
                for key in ("capture", "match", "range", "restored", "direct")}
    selected_java = os.environ.get("ROUTECONTRACT_EXAMPLE_JAVA_VERSION", "")
    summary, complete = render(evidence, outcomes, os.environ.get("BUILD_TOOL", ""),
                              int(selected_java) if selected_java in ("17", "21") else None)
    print(summary)
    sys.exit(0 if complete else 1)
