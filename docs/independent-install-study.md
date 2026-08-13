# Independent release-candidate installation study

## Purpose and evidence boundary

This protocol records the first attempt by a human non-author to follow an exact public
RouteContract release candidate. It is not a benchmark, security audit, endorsement, publisher
authentication, performance result, or evidence of broad adoption. A failed or stopped attempt is
useful feedback and remains in the record.

The project must not count an AI run, the maintainer's second computer or VM, a same-checkout
packaging test, an unpublished artifact, or a person who helped prepare the tested release as
independent-install evidence.

Task A is the primary clean-Quick-Start study. Task B is optional evidence for the exact RC's public
asset installation path. The two first outcomes are always classified separately.

## Activation gate — do not recruit early

The maintainer may recruit a participant only after all of the following are public and mutually
consistent:

- an annotated `vMAJOR.MINOR.PATCH-rcN` tag and its full 40-character commit;
- a non-draft GitHub prerelease created from that exact tag;
- this protocol and the README at exact-tag permalinks;
- a successful `release-evidence` run whose head SHA is that tag commit;
- the workflow artifact ID and GitHub-reported `sha256:` artifact digest;
- exactly ten project payloads and one `SHA256SUMS` Release asset;
- a locally computed SHA-256 of the `SHA256SUMS` file;
- repository release immutability verified as `enabled:true` before the RC tag and Release exist.

For version `0.1.0-rc1`, the ten checksummed payloads are exactly:

```text
routecontract-0.1.0-rc1-source.zip
routecontract-shardingsphere-5.5-0.1.0-rc1.jar
routecontract-shardingsphere-5.5-0.1.0-rc1-sources.jar
routecontract-shardingsphere-5.5-0.1.0-rc1-javadoc.jar
routecontract-shardingsphere-5.5.pom
routecontract-shardingsphere-5.5-cyclonedx.json
routecontract-shardingsphere-5.5-cyclonedx.xml
routecontract-aggregate-cyclonedx.json
routecontract-aggregate-cyclonedx.xml
test-summary.txt
```

`SHA256SUMS` declares those ten files and does not declare itself. GitHub-generated automatic
source archives are not project Release assets and are not substituted for the checksummed source
ZIP.

After the prerelease exists, commit one fixed activation-record file containing the tag, commit,
Release URL, tagged protocol and README URLs, a full-commit permalink to the issue-form source, run
URL/head SHA, workflow artifact ID/digest, the eleven exact asset names, and `SHA256SUMS`'s own
SHA-256. The participant copies that record into
the issue form together with a full-commit permalink to that file. Do not use a moving branch URL or
an editable Issue comment as the record of identity. Corrections require a new activation-record
commit and, if any release identity or byte changes, a new RC. Before recruitment, the Release API
must report `draft:false`, `prerelease:true`,
`immutable:true`, the exact tag, and exactly eleven uploaded assets. `gh release verify` and
`gh release verify-asset` for each downloaded project asset must all succeed. The activation record
must link those checks or the public evidence that records them.

Do not replace assets or retag after recruitment starts. Any change requires a new commit,
annotated `rcN+1` tag, Release, evidence run, activation record, and fresh attempt. GitHub-generated
automatic source downloads are outside the eleven-asset verification set.

The strict `-rcN` installer, consumer, source-archive validation, and annotated-tag workflow gates
must be present in the tested tag. Their implementation is tracked by
[PR #13](https://github.com/ym0506/routecontract/pull/13); the study remains inactive until that PR
or an equivalent reviewed change is merged and included in the RC.

## Participant eligibility

The participant must be a human who:

- is not the RouteContract author and does not operate the maintainer's machine or VM;
- did not author, review, privately pretest, or prepare code, documentation, workflow, installer,
  or Release assets in the tested tag;
- uses their own workspace, Gradle home, Maven target, Docker daemon, and downloaded assets;
- has no private or unpublished artifact;
- receives no RouteContract-specific AI/search advice, private explanation, screen share, or
  maintainer help before both first outcomes are recorded;
- was not offered money, a gift, a reciprocal favor, contest support, or another benefit for this
  attempt; was not asked to star or follow the project; and was not asked or expected to pass,
  endorse, report a positive result, or use favorable wording;
- records every started eligible attempt instead of repeating privately until one passes.

General prerequisite help before the first outcome is limited to public official documentation for
Java, Docker, Git, Bash/POSIX tools, the operating system, or the shell; Python documentation is
also allowed when Task B is attempted. Record each URL and its purpose. Public tagged RouteContract
documentation is allowed. Prior exposure, a personal relationship, or compensation must be
disclosed in non-identifying terms. Prior exposure or a personal relationship does not automatically
make the result invalid, but hidden involvement does.
Any money, gift, reciprocal favor, contest support, or other benefit offered for this attempt makes
it ineligible as independent-install evidence even when disclosed; preserve the result only as
contextual feedback.

A private invitation may contain only neutral logistics: the fixed activation-record permalink,
general prerequisites and administrative time limit, and the statement that refusal, failure,
withdrawal, or a negative usefulness assessment is acceptable. It must not restate RouteContract
commands, expected output, classifications, setup guidance, or troubleshooting. Those details must
come only from the fixed public activation record and exact-tag public documentation.

A public recruitment announcement may explain the high-level problem and supported scope and link
the same fixed activation record. It must not provide a second set of commands, expected-output
answers, result classifications, or troubleshooting outside the fixed public record. A participant
records that announcement as prior public exposure; it is not private setup help.

Preferred coverage is two eligible participants on materially different environments. One honest
participant is useful qualitative evidence, not a statistical usability study. Do not report an
average, success rate, or “five-minute install” claim from one or two participants.

## Prerequisites and environment record

Record the following without publishing a hostname or absolute path:

- operating system/version and CPU architecture;
- for Task A: Git, Bash, the required POSIX tools, network availability, Java 17, and a usable Docker
  daemon;
- for optional Task B: the Task A prerequisites plus Python 3 and direct Release-asset download;
- JDK vendor and complete Java 17 version;
- Docker client and server versions and usable daemon state;
- Task A's new `GRADLE_USER_HOME` and whether the pinned MySQL image cache was cold or warm;
- Task B's new flat download directory and initially empty target Maven repository;
- passive download/wait time separately from active execution or troubleshooting time.

Use an administrative limit of at most 60 minutes per task or 90 minutes total. Hitting the limit is
`TIMEOUT_OR_WITHDRAWN`, not a hidden retry. A participant may stop earlier.

## Security stop rule

Do not create a public study issue if the attempt may expose a credential, raw SQL or bind value,
customer data, private topology, an absolute private path, or a possible vulnerability. Stop and
follow [SECURITY.md](../SECURITY.md) first. Even through private vulnerability reporting, begin
with the minimum information and do not request, send, or retain full logs, diagnostic output, or
data dumps. Exchange any additional information only through the minimal-data procedure in
`SECURITY.md`. After a safety review, only a minimized classification may be made public.

Never upload a file or screenshot. Do not publish full stdout/stderr, JDBC URLs, hostnames,
container IDs, trace/span IDs, data-source names, or local paths. Remove unnecessary personal or
machine metadata: real name, email, school, employer, city, account/home-directory name, IP/device
identifier, Docker context/registry/proxy, environment dump, and Git configuration. The allowlisted
fields below are sufficient.

## Task A — exact-tag Quick Start

1. Verify the tag is annotated and resolve it to the activation record's full commit.
2. Clone into a new directory, check out the exact tag, and verify `HEAD` equals that commit.
3. Run `git status --porcelain` before the task; it must be empty.
4. Do not modify source, scripts, or documentation. Create a new task-specific Gradle home.
5. The following is the expected copy-paste shape. Replace the tag and SHA only with the fixed
   activation-record values:

   ```bash
   study_tag='v0.1.0-rc1'
   study_sha='0000000000000000000000000000000000000000'
   git clone https://github.com/ym0506/routecontract.git routecontract-study
   cd routecontract-study
   tag_type="$(git cat-file -t "refs/tags/$study_tag")"
   peeled_sha="$(git rev-parse "$study_tag^{commit}")"
   printf 'tagObject=%s\npeeledCommit=%s\n' "$tag_type" "$peeled_sha"
   test "$tag_type" = tag
   test "$peeled_sha" = "$study_sha"
   git checkout --detach "$study_tag"
   head_sha="$(git rev-parse HEAD)"
   tracked_state="$(git status --porcelain)"
   ignored_state="$(git clean -ndx)"
   printf 'headCommit=%s\ntrackedState=%s\nignoredBuildState=%s\n' \
     "$head_sha" "${tracked_state:-EMPTY}" "${ignored_state:-EMPTY}"
   test "$head_sha" = "$study_sha"
   test -z "$tracked_state"
   test -z "$ignored_state"
   ```

   Expected results are `tagObject=tag`, the exact activation SHA for `peeledCommit` and
   `headCommit`, plus `trackedState=EMPTY` and `ignoredBuildState=EMPTY`. A
   lightweight tag, SHA mismatch, or nonempty status is `PROTOCOL_DEVIATION` or a documented
   blocker; do not repair it by moving the tag.

6. Follow only the tagged README and run:

   ```bash
   routecontract_study_gradle_home="$(mktemp -d)"
   GRADLE_USER_HOME="$routecontract_study_gradle_home" \
     ./scripts/quickstart-demo.sh
   ```

7. Run `git status --porcelain` again; it must remain empty.
8. Record the process exit, elapsed times, and only these output fields:

   ```text
   [ROUTECONTRACT QUICKSTART VERIFIED]
   businessResult         UNCHANGED (one row in both captures)
   observedAttempts       1 -> 2
   observedDataSources    1 -> 2
   RCM201                 ATTEMPT_BUDGET_EXCEEDED: maximum=1, observed=2
   RCM202                 DATA_SOURCE_BUDGET_EXCEEDED: maximum=1, observed=2
   realMysqlDemoExit      0
   intentionalCiGateExit  1 (expected build rejection)
   quickstartExit         0
   ```

Task A is `UNASSISTED_PASS` only when the exact tagged instructions lead to outer process exit `0`
and all fields agree. The inner intentional CI task must exit `1`; catching that expected contract
rejection is part of the successful outer Quick Start.

For a Task A failure, publish only the outer exit code and the script's single minimized line:

```text
QUICKSTART_ERROR phase=<safe-phase> check=<safe-check> expected=<safe-value> observed=<safe-value>
```

Do not publish the child output. If that marker is unavailable, publish only
`TASK_A_BLOCKER category=<PRODUCT_OR_DOC|PREREQUISITE|TIMEOUT|PROTOCOL> check=<short-safe-label>`.

## Task B — checksummed exact-RC assets (optional)

1. Download the eleven exact project assets directly from the same GitHub prerelease into a new
   flat directory. Do not use a workflow artifact, local build, automatic GitHub source archive, or
   file sent by the maintainer.
2. Confirm the ten payload names and `SHA256SUMS` match the activation record, and independently
   hash `SHA256SUMS` itself.
3. Create a separate, initially empty target Maven repository.
4. From the exact tagged checkout, without source/script/document edits, run:

   ```bash
   ./scripts/verify-release-assets-consumer.sh \
     /absolute/path/to/downloaded-release-assets \
     /absolute/path/to/empty-verification-maven
   ```

5. Record the exit, exact installed coordinate, elapsed times, and only the complete final marker:

   ```text
   ROUTECONTRACT_RELEASE_ASSET_CONSUMER coordinate=io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0-rc1 result=VERIFIED_MYSQL
   ```

The verifier checks the public checksum/allowlist, release coordinate, selected JAR/POM/manifest
constraints, bounded source-ZIP structure and conventional Java path/package constraints, isolated
file-Maven installation, SPI discovery, and the supplied real-MySQL consumer. It does **not** prove
publisher identity, equality with the tagged Git tree, a final stable release, arbitrary external
application compatibility, security, performance, or adoption.

Task B may be `NOT_RUN`; it must never be inferred from Task A. An RC asset result applies only to
that exact RC.

For a Task B failure, publish only the outer exit code and one manually minimized line:

```text
TASK_B_BLOCKER phase=<download|checksum|install|consumer> category=<PRODUCT_OR_DOC|PREREQUISITE|TIMEOUT|PROTOCOL> check=<short-safe-label>
```

Do not paste installer, Gradle, Docker, or test output into the public issue.

## First-result classifications

Classify each task exactly once before rescue, retry, or RouteContract-specific help:

- `UNASSISTED_PASS`: exact tagged public instructions completed with all required evidence;
- `PRODUCT_OR_DOC_BLOCKED`: RouteContract code, public assets, or tagged instructions blocked it;
- `PREREQUISITE_BLOCKED`: a documented general prerequisite blocked it before RouteContract ran;
- `TIMEOUT_OR_WITHDRAWN`: the participant stopped or reached the administrative cap;
- `PROTOCOL_DEVIATION`: private/RouteContract-specific help, source changes, asset substitution, or
  another protocol violation occurred before the first outcome;
- `NOT_RUN`: the task did not start. This is expected to remain available for optional Task B.

Submit the issue after the two first statuses and evidence fields are filled, but before rescue or
retry. Do not edit the first-result fields afterward. Record each later attempt as a timestamped
issue comment with the exact new tag (if any), public help used, changes, and one recovery status:
`NOT_ATTEMPTED`, `ASSISTED_PASS`, or `ASSISTED_FAIL`.

If a genuine product or documentation defect exists, preserve the first failure, open a focused
issue/PR, publish a new RC, and rerun. A same-participant rerun confirms that fix; a new eligible
participant provides stronger fresh-usability evidence. If no genuine defect exists, record
`no fix required`. Never invent a defect or PR to manufacture project history.

## Public report and authorship

Use the
[Independent RC installation issue form](https://github.com/ym0506/routecontract/issues/new?template=independent-rc-install.yml).
To qualify as non-author evidence, the participant files it from their own account and personally
checks the first-person attestations. A maintainer-transcribed note may preserve contextual feedback
in a normal issue or comment, but it is not an eligible independent-install result and must not use
this form by pretending the maintainer is the participant.

The issue asks four neutral questions:

1. Why is the intentional inner CI exit `1` expected while outer Quick Start exit `0` is success?
2. What does this attempt prove, and what does it not prove?
3. Would RouteContract help a real testing problem the participant has? `No` is valid.
4. Which step was least clear, and what exact documentation change is suggested?

## Evidence promotion and contest rubric boundary

- An eligible Task A `UNASSISTED_PASS` can support the clean-Quick-Start portion of E08 and a
  limited non-author RC usability claim in E10.
- An eligible Task B `UNASSISTED_PASS` can support only the exact-RC asset-install portion of E09.
  It does not satisfy stable-release E09.
- A real public blocker followed by a focused fix PR and new RC can support E13 project-management
  and community evidence. No defect means `no fix required`, not a fabricated PR.

These records may strengthen first-round OSS growth/documentation/management evidence and
final-round utility/community evidence. They do not prove innovation, license correctness,
upstream acceptance, security, performance, production suitability, broad adoption, or any contest
score.

Both tasks passing is required only for the narrow phrase “an independent RC Quick Start and RC
asset-install attempt both passed.” Task A alone may be reported as Task A only; Task B alone may be
reported as Task B only. Never collapse partial outcomes into a combined pass.

RC evidence cannot be promoted to final `v0.1.0`. A final-release non-author claim requires a new
eligible run against the final annotated tag, Release, assets, and documentation. The project may
separately report final maintainer CI/package verification, but it must not label RC
independent-install evidence as final independent-install validation.
