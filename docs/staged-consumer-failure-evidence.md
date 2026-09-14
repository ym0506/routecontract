# Staged consumer failure evidence

When an installation check fails before its tests start, a contributor should
still be able to distinguish a failed process from a timeout and see which
diagnostic signals were present. A path to a deleted CI runner is not enough.

## Acceptance

- A failed staged Gradle process remains a failed check. A timeout remains a
  timeout; neither produces a successful consumer summary.
- Both lanes share a 13-minute native-command deadline, leaving two minutes
  before the CI step's 15-minute limit for diagnostic output and cleanup.
  Each lane receives only the remaining time.
- Before propagating a nonzero exit or timeout, retain `gradle-failure.json`
  beside the lane's local `gradle.log`.
- The JSON contains only a fixed schema: format version, outcome, native exit
  code (null on timeout), timeout flag, complete log byte count and SHA-256,
  and signal names from a fixed allowlist. Unrecognized output is `UNKNOWN`.
- Signal names describe text observed in the log, not a proven root cause.
  Multiple signals may be present. A wrapper frame alone does not establish
  that the wrapper caused the failure.
- Do not copy log excerpts, SQL, parameters, connection properties, command
  arguments, URLs, filesystem paths or arbitrary exception messages into this
  diagnostic. The original log remains local to the runner.
- Print the same safe JSON before attempting to store it. If diagnostic I/O
  fails, emit a fixed unavailable marker and preserve the original command
  failure or timeout. Disk exhaustion must not replace the original outcome.
- The always-run staged-consumer artifact step includes the JSON even when
  the second lane fails before producing JUnit or report files. It does not
  upload the raw Gradle log.
- A successful process does not create a failure diagnostic. Missing required
  success markers or JUnit evidence still fail their existing validation.

## Verification boundary

The acceptance tests invoke a real child process that emits synthetic private
values and exits unsuccessfully. They verify that the retained diagnostic has
the exact allowed fields and labels, hashes every original log byte, and
contains none of those values. Timeout tests verify that already-written output
is retained before the same exception is propagated. Workflow assertions check
the artifact selection independently of the diagnostic writer.

Reproduce from the repository root:

```sh
python3 -m unittest discover -s scripts/tests -p test_verify_staged_split_artifact_consumer.py
```

Evidence label: **verified - unit**. All 17 focused cases passed locally on
2026-09-14, including in the complete suite on Python 3.12.14. These checks do
not prove that a previous CI failure has been repaired, identify the cause of an earlier
missing log, or add a MySQL execution claim. The normal CI staged-consumer job
continues to require both exact-version lanes and their existing real MySQL
evidence.
