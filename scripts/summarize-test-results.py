#!/usr/bin/env python3
"""Create the fixed, privacy-minimized RouteContract release test summary.

The release workflow already fails when ``clean check`` fails.  This script
adds a second, deliberately narrow gate: all and only the expected JUnit
suites of one published artifact must be present (nine for the 5.5 artifact),
every expected test must have run, and every result count must be zero.  Only suite identities and aggregate counts are emitted;
JUnit timestamps, hostnames, durations, test names and captured output are not
copied into the release evidence.
"""

from __future__ import annotations

import argparse
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


SUMMARY_FORMAT = "routecontract-test-summary-v1"
REVISION_RE = re.compile(r"[0-9a-f]{40}")
INTEGER_RE = re.compile(r"0|[1-9][0-9]*")
MAX_XML_BYTES = 4 * 1024 * 1024

EXPECTED_SUITES = {
    "io.github.ym0506.routecontract.RouteContractTest": 18,
    "io.github.ym0506.routecontract.example.DataSourceProxyComparisonMySqlTest": 1,
    "io.github.ym0506.routecontract.example.FailureBoundaryMySqlTest": 1,
    "io.github.ym0506.routecontract.example.ObservedExecutionRegressionCorpusMySqlTest": 7,
    "io.github.ym0506.routecontract.example.OperationCorrelationMySqlTest": 5,
    "io.github.ym0506.routecontract.internal.MutableAttemptTest": 2,
    "io.github.ym0506.routecontract.internal.ShardingSphere553PreflightTest": 3,
    "io.github.ym0506.routecontract.manifest.ManifestReviewReportTest": 10,
    "io.github.ym0506.routecontract.manifest.ObservedExecutionManifestTest": 17,
}
DEFAULT_PROFILE = "routecontract-shardingsphere-5.5"
# The 5.4.1-5.5.2 artifact runs the same suite classes in several Gradle test tasks, so its
# suites are keyed by the result directory name (the task name) as well as the suite class.
_RUNTIME_TASKS = ("testShardingSphere541", "testShardingSphere550", "testShardingSphere551",
                  "testShardingSphere552")
PROFILES = {
    DEFAULT_PROFILE: EXPECTED_SUITES,
    "routecontract-shardingsphere-5.4.1-5.5.2": {
        "test/io.github.ym0506.routecontract.RouteContractTest": 18,
        "test/io.github.ym0506.routecontract.internal.MutableAttemptTest": 2,
        "test/io.github.ym0506.routecontract.internal.ShardingSphere541To552PreflightTest": 5,
        "test/io.github.ym0506.routecontract.manifest.ManifestReviewReportTest": 10,
        "test/io.github.ym0506.routecontract.manifest.ObservedExecutionManifestTest": 17,
        **{
            f"{task}/io.github.ym0506.routecontract.example.{suite}": tests
            for task in _RUNTIME_TASKS
            for suite, tests in (("FailureBoundaryMySqlTest", 1), ("OperationCorrelationMySqlTest", 5))
        },
    },
}


class SummaryError(ValueError):
    """Raised when the JUnit result set is not the exact release test set."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True, help="40-character Git commit SHA")
    parser.add_argument(
        "--results-dir",
        action="append",
        type=Path,
        required=True,
        help="JUnit XML directory; repeat for each Gradle test task",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default=DEFAULT_PROFILE,
        help="published artifact whose expected suites are required",
    )
    return parser.parse_args()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _required_count(root: ET.Element, key: str, suite: str) -> int:
    raw = root.get(key)
    if raw is None or INTEGER_RE.fullmatch(raw) is None:
        raise SummaryError(f"suite {suite} has an invalid {key} count")
    return int(raw)


def _read_suite(path: Path, allowed_suites: set[str]) -> tuple[str, dict[str, int]]:
    if path.is_symlink() or not path.is_file():
        raise SummaryError("JUnit input must be a regular non-symlink file")
    if path.stat().st_size > MAX_XML_BYTES:
        raise SummaryError("JUnit input exceeds the 4 MiB safety limit")
    raw = path.read_bytes()
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise SummaryError("JUnit input must not contain a DTD or entity declaration")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise SummaryError(f"invalid JUnit XML: {error}") from error
    if _local_name(root.tag) != "testsuite":
        raise SummaryError("JUnit XML root must be testsuite")
    suite = root.get("name")
    if suite not in allowed_suites:
        raise SummaryError(f"unexpected JUnit suite: {suite!r}")
    if path.name != f"TEST-{suite}.xml":
        raise SummaryError(f"JUnit filename does not match suite {suite}")

    counts = {
        key: _required_count(root, key, suite)
        for key in ("tests", "failures", "errors", "skipped")
    }
    testcases = [child for child in root if _local_name(child.tag) == "testcase"]
    if len(testcases) != counts["tests"]:
        raise SummaryError(f"suite {suite} test count does not match its testcase elements")
    status_elements = {
        key: sum(
            1
            for testcase in testcases
            for child in testcase
            if _local_name(child.tag) == key.removesuffix("s")
        )
        for key in ("failures", "errors", "skipped")
    }
    if status_elements != {
        key: counts[key] for key in ("failures", "errors", "skipped")
    }:
        raise SummaryError(f"suite {suite} result counts do not match testcase elements")
    return suite, counts


def build_summary(
    revision: str, results_dirs: list[Path], profile: str = DEFAULT_PROFILE
) -> str:
    if REVISION_RE.fullmatch(revision) is None:
        raise SummaryError("revision must be a lowercase 40-character Git commit SHA")
    if profile not in PROFILES:
        raise SummaryError(f"unknown summary profile: {profile!r}")
    expected_suites = PROFILES[profile]
    keyed_by_task = profile != DEFAULT_PROFILE
    allowed_suites = {key.rpartition("/")[2] for key in expected_suites}

    observed: dict[str, dict[str, int]] = {}
    for directory in results_dirs:
        if directory.is_symlink() or not directory.is_dir():
            raise SummaryError("each JUnit results path must be a non-symlink directory")
        for path in sorted(directory.glob("TEST-*.xml")):
            suite, counts = _read_suite(path, allowed_suites)
            key = f"{directory.name}/{suite}" if keyed_by_task else suite
            if key in observed:
                raise SummaryError(f"duplicate JUnit suite: {key}")
            observed[key] = counts

    if set(observed) != set(expected_suites):
        missing = sorted(set(expected_suites) - set(observed))
        unexpected = sorted(set(observed) - set(expected_suites))
        raise SummaryError(
            f"JUnit suite set mismatch; missing={missing}, unexpected={unexpected}"
        )

    for suite, expected_tests in expected_suites.items():
        counts = observed[suite]
        if counts["tests"] != expected_tests:
            raise SummaryError(
                f"suite {suite} test count changed: expected {expected_tests}, "
                f"found {counts['tests']}"
            )
        if any(counts[key] != 0 for key in ("failures", "errors", "skipped")):
            raise SummaryError(f"suite {suite} is not an all-passing, non-skipped result")

    lines = [
        f"format={SUMMARY_FORMAT}",
        *([f"artifact={profile}"] if keyed_by_task else []),
        f"revision={revision}",
        f"suite_count={len(observed)}",
        f"test_count={sum(counts['tests'] for counts in observed.values())}",
        f"failure_count={sum(counts['failures'] for counts in observed.values())}",
        f"error_count={sum(counts['errors'] for counts in observed.values())}",
        f"skipped_count={sum(counts['skipped'] for counts in observed.values())}",
    ]
    lines.extend(
        f"suite={suite}|tests={observed[suite]['tests']}|"
        f"failures={observed[suite]['failures']}|errors={observed[suite]['errors']}|"
        f"skipped={observed[suite]['skipped']}"
        for suite in sorted(observed)
    )
    return "\n".join(lines) + "\n"


def write_summary(output: Path, content: str) -> None:
    if output.is_symlink():
        raise SummaryError("summary output must not be a symlink")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=output.parent,
        prefix=f".{output.name}.",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, output)


def main() -> int:
    args = parse_args()
    try:
        content = build_summary(args.revision, args.results_dir, args.profile)
        write_summary(args.output, content)
    except (OSError, SummaryError) as error:
        raise SystemExit(f"test summary generation failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
