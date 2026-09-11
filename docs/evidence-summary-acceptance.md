# First-project evidence summary acceptance

## Problem observed on main `fec96d1`

The first-project workflow has Java 17 and Java 21 jobs, but its summary always
labels the runtime Java 17 and links only the Java 17 artifact names. Its
completion decision also ignores the direct-assertion step added later: all
manifest stages can pass while a failed, skipped or cancelled direct/runtime
verification is still headed “Demonstration complete” with a claim of a green
workflow. The actual workflow can be red in that situation.

## Required behavior

1. A Java 21 job must identify Java 21 and its actual artifact name. A selected
   runtime is not reported as verified until the existing direct-assertion
   verifier's summary matches the job's Java/build-tool context.
2. Completion requires successful capture, match, range, restoration and direct
   verification. A failed/skipped/cancelled direct step must not reuse a leftover
   summary, and missing/malformed/mismatched runtime evidence means incomplete.
3. Validate the direct summary's library/hash/classfile identity and the three
   pass/fail/restore stages, including result assertions and unchanged manifest
   files. Reject boolean-as-integer values, unknown/missing/duplicated stages,
   wrong counts or success exits in the intentionally failing stage.
4. Keep the existing manifest-stage findings visible after partial failure, but
   do not infer overall workflow success from those earlier stages.
5. Only fixed/allowlisted text and validated numbers are rendered from runtime
   inputs. Preserve the generated summary as an artifact so its exact contents
   can be inspected for each of the four public consumer jobs.
6. Show failures on the unchanged summary before the fix. Then run focused
   negative controls and real MySQL first-project CI on Maven/Gradle and Java
   17/21. Record exact revisions and distinguish unit/synthetic evidence from
   actual runtime evidence. The released 0.1.3 library is unchanged.

This summary consumes evidence produced inside the trusted workflow. It is not
an authenticity proof for arbitrary self-submitted JSON or an adoption claim.

## Local verification

- `verified - unit`: Python 3 on macOS/aarch64,
  `python3 -m unittest discover -s submission/tools/tests -p test_first_project_summary.py -v`.
- Before the fix: 10 tests ran and 7 assertions/subcases failed, including a Java
  21 mislabel and success exits after missing/failed direct evidence. These are
  synthetic summary inputs, not failed database executions.
- After the fix: 13 test methods pass, covering both build tools and JDKs,
  partial failures, malformed identity/stages, stale evidence and unsafe labels.
- Real MySQL/public consumer CI remains required before accepting the change.

Raw local failure output is retained outside the repository at
`growth/evidence/summary-hardening-red-20260911.log`; it is not published evidence
of an actual Java 21 database run.
