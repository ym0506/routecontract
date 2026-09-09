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


def render(evidence, outcomes):
    lines = [
        "# RouteContract: same result, different execution", "",
        "Public **0.1.3** · Java **17** · ShardingSphere-JDBC **5.5.3** · MySQL **8.4.11**", "",
        "Each verified stage checks the same synthetic order: **201 / user 3 / PAID**.", "",
        "| Stage | Verification | Contract | Physical JDBC attempts | Observed aliases |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    complete = outcomes.get("capture") == "success"
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
    lines += ["", (
        "**Demonstration complete.** The range-query test failed with the expected "
        "RouteContract assertion (**RCM201 / RCM202**), then the normal test passed again. "
        "The workflow is green because it verified that rejection and recovery. "
        "Capture did not approve a baseline; the supplied synthetic baseline stayed unchanged."
        if complete else
        "**Demonstration incomplete.** Inspect the failed or skipped steps above. "
        "A missing report, dependency, compiler or Docker failure does not demonstrate "
        "contract rejection. Earlier successful stages do not establish a completed run."
    ), "", "Download **first-project-Maven** or **first-project-Gradle** from this run's "
        "Artifacts section. Under `build/lifecycle-evidence/`, `match/`, `range/` and "
        "`restored/` retain the verified candidate and JSON/Markdown reports. "
        "`range/review.md` explains the rejection.", "",
        "Next: follow **docs/first-project.md → Adapt one existing test** in your fork. "
        "Review your own operation, aliases and budget before approving its baseline.", "",
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
                for key in ("capture", "match", "range", "restored")}
    summary, complete = render(evidence, outcomes)
    print(summary)
    sys.exit(0 if complete else 1)
