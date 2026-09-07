# Public Gradle split-artifact consumer

Status: implemented post-publication verification command. Public 0.2 artifacts
have not been verified as available. This document is not a publication, support, or adoption claim.

## Acceptance contract

- Require a separately reviewed receipt for exactly the nine JAR/POM/Gradle-module payloads in
  the coordinated core/5.5.3-adapter/5.5.2-adapter release. Accept only strict stable `0.2.x`
  versions. Receipt validation belongs to the shared public-artifact validator.
- Copy the existing real-MySQL consumer outside the checkout and use an absent/new Gradle user
  home for each exact 5.5.2 and 5.5.3 lane. Configure exactly one anonymous dependency repository:
  `https://repo.maven.apache.org/maven2`. No local repository, Maven Local, composite build,
  project source, account credentials, caller-supplied repository URL or fallback is permitted.
- Request only the selected adapter directly. Require its published dependency to provide core
  transitively, and verify both selected first-party JAR names and SHA-256 against the reviewed
  receipt. Retain strict artifact/metadata verification and existing reviewed third-party locks;
  adjust only the coordinated first-party lock coordinates for the receipt's stable version.
- Preserve exact whole-group ShardingSphere selection and the unchanged MySQL/CLI fixture:
  the exact business row and a one-attempt baseline MATCH; the same business row with two
  physical JDBC execution attempts rejected as POLICY_VIOLATION with RCM201/RCM202. Retain all
  three raw JUnit cases and minimized manifest/review evidence separately per runtime.
- Retain wrong-anchor and wrong-non-anchor runtime rejection, both ordinary dual-adapter
  declaration orders, and legacy-request rejection. The non-anchor negative retains the selected
  adapter and all three correct exact-runtime anchors while rejecting one wrong nontransitive
  `infra-common` request; selected anchors are retained in its evidence. Do not require capabilities explicitly to
  manufacture the dual-adapter result; the published metadata must cause ordinary conflict.
- Missing versions, checksum mismatch, incomplete/skipped tests, absent evidence, or changed
  expected receipt coordinates/hashes must fail. No local build, credential fallback or verification bypass may turn
  an unavailable public coordinate into success. A 404 is negative availability evidence only.

Staged mode remains the default of the shared Gradle fixture and keeps its existing repository
contract. Public mode is opt-in. No unchanged staged/MySQL test result is relabeled as a live
public-consumer result.

## Command

After publishing the coordinated release and completing the independent public-byte readback, run
from the source checkout with Java 17 (`JAVA_HOME`), Python 3.10+, Docker and network access:

```sh
python3 -I scripts/verify-public-gradle-artifact-consumer.py \
  --receipt /absolute/path/to/reviewed-consumer-receipt.json \
  --evidence-directory /absolute/path/to/new-public-gradle-evidence
```

The receipt is the closed format-1 document accepted by `public_split_artifacts.py`: one stable
`routeContractVersion` and exactly one `.jar`, `.pom`, and `.module` payload for each of the three
coordinated modules, with its exact relative path and SHA-256. Its expected hashes must already
have been reviewed; the wrapper never learns or approves them from the bytes it downloads.
Validation uses the shared bounded regular-file loader before any consumer/cache/network work.
The saved normalized `reviewed-receipt.json` hash identifies the expected document used by the run.
A receipt proves expectations, not publication or independent publisher authentication.

Both exact-runtime lanes use fresh temporary Gradle homes and copied consumer projects. The
Gradle 8.14.4 wrapper distribution is obtained from its existing checksum-pinned distribution URL;
all **dependency repositories** in public mode are fixed to the single Maven Central endpoint.
The wrapper accepts no repository or credential option and clears the inherited
`GRADLE_RO_DEP_CACHE` read-only cache as well as using a new Gradle user home. Gradle's transport
redirect behavior is not independently constrained by this fixture: a fixed configured repository
is not proof of every final HTTP response origin. Require the separate redirect-rejecting public
byte readback before consumption; reviewed hashes still bind the selected consumer bytes. Temporary consumer/cache directories are
removed when the run ends. Evidence, lockfiles, verification metadata and logs remain for review.

A successful `summary.json` requires both exact lanes, all six MySQL test executions and all ten
negative graph cases. It is written only after the expected receipt still matches. The Java
fixture retains its historical `STAGED_SPLIT_MYSQL` internal marker because its source is reused
unchanged; the wrapper requires separate public graph/negative markers and reports the actual
public distribution scope in its own final summary.

Raw framework logs/JUnit may contain synthetic SQL or JDBC URLs. Keep those raw files local, or
sanitize a derivative before public sharing. Minimized manifests and review reports are retained
separately. The fixture observes `SQLExecutionHook`-reported physical JDBC execution attempts;
callback return is not a transaction commit or a business-success guarantee.

## Implemented versus executed

The preparation path supports reviewed stable patch versions by rewriting only the two selected
first-party lock coordinates and their exact nine receipt hashes. Third-party locks/hashes are
preserved; any dependency change needs its own review. The existing staged path remains pinned to
its original 0.2.0 candidate.

Positive anonymous public 0.2 consumption, both real-MySQL public lanes, public module-capability
conflicts and public checksum/origin checks remain **unverified until the coordinated artifacts
exist and this full command passes**. Passing preparation tests or local staged consumers cannot
satisfy that publication-dependent requirement. No release guard is removed by this implementation.

## Local preparation evidence, 2026-09-07

`verified - unit`: 14 public-wrapper preparation/failure tests and 8 existing staged-helper tests
pass. They cover unchanged fixture bytes, receipt-version metadata, first-party-only lock edits,
shared receipt rejection before network/cache creation, evidence retention, changed expected hashes
and removal of the independent `GRADLE_RO_DEP_CACHE` cache.

Gradle 8.14.4 configured both public runtime branches and the staged 5.5.3 branch successfully in
offline `help` runs. This proves build-script configuration only, not resolution or MySQL behavior.
Local logs: `/private/tmp/routecontract-public-gradle-configuration-20260907`.

The actual candidate `0.2.0` was then requested through the public wrapper using the existing
reviewed nine-payload staging receipt. Gradle failed to find the 5.5.2 adapter's `.module`/`.pom` at
the configured official Maven Central URLs. The wrapper exited 1, retained diagnostics and wrote
no success summary; no public MySQL test or second runtime lane ran. This is negative availability
evidence for that attempt, not a failure waived into release readiness. The run used a new
Gradle home; `GRADLE_RO_DEP_CACHE` was not set in its environment.

Local negative evidence:
`/private/tmp/routecontract-public-gradle-missing-0.2.0-20260907/5.5.2/gradle.log`.
The final public cache sanitizer and mixed non-anchor graph received targeted independent review.
The strengthened **public** non-anchor and dual-adapter cases still require published metadata;
a successful local staged regression cannot establish that public result.
