# Independent release-candidate installation study

## Purpose and evidence boundary

This protocol asks a participant to self-attest that they are a human non-author and records
their first attempt to follow an exact public
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
- the version-specific Issue Form required by that exact tag;
- a successful `release-evidence` run whose head SHA is that tag commit;
- the workflow artifact ID and GitHub-reported `sha256:` artifact digest for
  its exact 17-file flat allowlist;
- exactly eleven project payloads and one `SHA256SUMS` Release asset;
- a locally computed SHA-256 of the `SHA256SUMS` file;
- repository release immutability currently reported as `enabled:true`, and the published Release
  independently reported as immutable. The release procedure requires the setting before tag
  creation, but the activation validator does not claim to reconstruct that earlier timing.

For version `0.1.0-rc2`, the eleven checksummed payloads are exactly:

```text
routecontract-0.1.0-rc2-source.zip
routecontract-shardingsphere-5.5-0.1.0-rc2.jar
routecontract-shardingsphere-5.5-0.1.0-rc2-sources.jar
routecontract-shardingsphere-5.5-0.1.0-rc2-javadoc.jar
routecontract-shardingsphere-5.5.pom
routecontract-shardingsphere-5.5-cyclonedx.json
routecontract-shardingsphere-5.5-cyclonedx.xml
routecontract-aggregate-cyclonedx.json
routecontract-aggregate-cyclonedx.xml
supply-chain-evidence.json
test-summary.txt
```

For another candidate, replace `0.1.0-rc2` with that exact activated version in
the source ZIP, three JAR filenames and installed coordinate. The other seven
payload filenames stay unchanged. Never mix different RC filenames, source roots
or POM coordinates in one attempt; the
verifier's version-derived checks reject those inconsistencies. Those checks
cannot authenticate an earlier RC's JAR bytes merely renamed and re-checksummed
as a later RC. The fixed activation record's `SHA256SUMS` hash and the
revision-bound workflow artifact identity/digest provide that byte-provenance
binding.

`SHA256SUMS` declares those eleven files and does not declare itself. GitHub-generated automatic
source archives are not project Release assets and are not substituted for the checksummed source
ZIP.

The Issue Form filename is derived only from the strict tag's final `rcN` suffix:

```text
v0.1.0-rc1 -> independent-rc1-install.yml
v0.1.0-rc2 -> independent-rc2-install.yml
```

The closed activation schema records that derived filename, its source permalink at the full
`tagCommit`, and its exact interactive `issues/new?template=...` URL. The validator independently
derives all three values from `tag` and rejects a generic filename, another RC's filename, or any
URL mismatch. It also requires the active tag's derived path to be one ordinary non-executable Git
blob. This generic validator binds only the active `rcN` form; it does not prove preservation of an
earlier RC form. Distinct filenames prevent a later form from overwriting the earlier path, while
byte preservation remains a separate reviewed tag-history and owner gate for that version line.
This `0.1.0-rc2` source preserves the reviewed RC1 form byte-for-byte and adds the reviewed
`independent-rc2-install.yml`; the active package gate binds each filename to its own approved
SHA-256. Before a future `rc3` tag, its candidate must retain both reviewed forms, add and review
`independent-rc3-install.yml`, and add a version-line-specific preservation check. The interactive
URL is safe only while public `main` remains the validated activation-record commit; it is not an
immutable permalink and must never be substituted for the pinned form source.

After the prerelease exists, copy
`docs/evidence/independent-rc-activation.example.json` to
`docs/evidence/independent-rc-activation-vMAJOR.MINOR.PATCH-rcN.json`. Replace each occurrence of
`[[STRICT_RC_TAG]]` with the complete `vMAJOR.MINOR.PATCH-rcN` tag, `[[RC_VERSION_WITHOUT_V]]` with
the same version without `v`, and `[[VERSION_DERIVED_ISSUE_FORM_FILENAME]]` with exactly
`independent-rcN-install.yml` using the tag's suffix. Replace every other string `[[...]]` field
only with its complete observed value; the artifact-digest placeholder consumes the complete GitHub
`sha256:` value. Replace the two integer `0` sentinels at
`releaseEvidence.artifactId` and `releaseEvidence.runId` with positive unquoted JSON integers, and
set `releaseImmutability.enforcedByOwner` to the observed unquoted JSON boolean. Do not edit the
example into an apparent result. Confirm that `issueFormFilename`, `issueFormPermalink`, and
`issueFormUrl` all contain the same version-derived filename. Open one pull request into `main` and
squash-merge it so the activation-record commit's direct parent is the tag commit, and its only tree change
is adding that ordinary JSON file; do not change the validator, installer, protocol,
version-specific issue form, `.gitmodules`, or any other tagged byte. Then do not
advance public `main` while validating or recruiting. The activation validator and final package gate bind GitHub's
server-side pull-request `merged_at` after the RC prerequisites and before recruitment/cutoff;
author-controlled Git commit dates do not substitute for that publication timestamp. The gate also
verifies that the repository is public now; it does not reconstruct historical repository
visibility or branch protection at `merged_at`, which remains an owner-reviewed boundary rather
than an automated claim. From a clean checkout at that exact commit and all twelve directly
downloaded Release assets, run:

```bash
python3 scripts/validate-rc-activation-record.py \
  --record docs/evidence/independent-rc-activation-v0.1.0-rc2.json \
  --release-assets-dir /absolute/path/to/downloaded-release-assets
```

The command rejects templates, uncommitted bytes, a checkout or public `main` not equal to the
single-file direct-child record commit, a direct push or record commit without one exact closed,
merged `main` pull request whose merge SHA is that commit, tagged symlinks or `.gitmodules`, non-RC or lightweight
tags, local/public tag mismatches, a tag/version mismatch, a failed or wrong-revision run, wrong workflow artifact,
missing or mutable prerelease, repository immutability mismatch, any asset/checksum mismatch,
unsafe GitHub CLI, failed Release attestation, or failed per-asset attestation. It prints
`ROUTECONTRACT_RC_ACTIVATION_VERIFIED` and `ACTIVATION_RECORD_PERMALINK` only after every gate
passes. Only that fixed permalink and complete success marker activate recruitment. A source-tree
version, template, anticipated URL, command example, or partial output is not activation evidence.

The participant copies the validated record identity into the exact version-specific form selected
by the record's `issueFormUrl`. Do not use the default Issue chooser, a generic form URL, a moving
branch URL as the record of identity, or an editable Issue comment as the record of identity.
Corrections require a new activation-record commit and, if any release identity or byte changes, a
new RC. Before recruitment, the Release API must report `draft:false`, `prerelease:true`,
`immutable:true`, the exact tag, and exactly twelve uploaded assets. `gh release verify` and
`gh release verify-asset` for each downloaded project asset must all succeed through the validator.

Do not replace assets or retag after recruitment starts. Any change requires a new commit,
annotated `rcN+1` tag, Release, evidence run, activation record, and fresh attempt. GitHub-generated
automatic source downloads are outside the twelve-asset verification set.

The strict `-rcN` installer, consumer, source-archive validation, activation validator,
version-derived `independent-rcN-install.yml`, and annotated-tag workflow gates must be present in
the tested tag. The validator checks those tagged paths;
[PR #13](https://github.com/ym0506/routecontract/pull/13) records earlier implementation history but
is not itself activation evidence.

## Participant eligibility

The participant must be a human who:

- is not the RouteContract author and does not operate the maintainer's machine or VM;
- did not author, review, privately pretest, or prepare code, documentation, workflow, installer,
  or Release assets in the tested tag, and did not create or publish its tag or Release or prepare
  its activation record;
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

The contest-report predicate is deliberately limited to exactly one eligible Task A Issue. Close
the report evidence window after the first eligible Issue; two countable Issues make the branch
ambiguous and stop packaging instead of selecting a favorable result. A later study may seek two
participants on materially different environments outside that frozen report window. One honest
participant remains qualitative evidence, not a statistical usability study. Do not report an
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
5. Run the following copy-paste block. At its two prompts, paste the exact `tag` and `tagCommit`
   values from the fixed record named by `ACTIVATION_RECORD_PERMALINK`. The block rejects a
   malformed tag, malformed SHA, or all-zero SHA before cloning:

   ```bash
   routecontract_exact_checkout() {
     local study_tag study_sha tag_type peeled_sha head_sha tracked_state ignored_state
     read -r -p 'Activation-record tag: ' study_tag || return 2
     read -r -p 'Activation-record tagCommit: ' study_sha || return 2
     [[ "$study_tag" =~ ^v(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})-rc[1-9][0-9]{0,5}$ ]] || return 2
     [[ "$study_sha" =~ ^[0-9a-f]{40}$ ]] || return 2
     [[ "$study_sha" =~ [1-9a-f] ]] || return 2
     git clone https://github.com/ym0506/routecontract.git routecontract-study || return 2
     cd routecontract-study || return 2
     tag_type="$(git cat-file -t "refs/tags/$study_tag")" || return 2
     peeled_sha="$(git rev-parse "$study_tag^{commit}")" || return 2
     printf 'tagObject=%s\npeeledCommit=%s\n' "$tag_type" "$peeled_sha"
     test "$tag_type" = tag || return 2
     test "$peeled_sha" = "$study_sha" || return 2
     git checkout --detach "$study_tag" || return 2
     head_sha="$(git rev-parse HEAD)" || return 2
     tracked_state="$(git status --porcelain)" || return 2
     ignored_state="$(git clean -ndx)" || return 2
     printf 'headCommit=%s\ntrackedState=%s\nignoredBuildState=%s\n' \
       "$head_sha" "${tracked_state:-EMPTY}" "${ignored_state:-EMPTY}"
     test "$head_sha" = "$study_sha" || return 2
     test -z "$tracked_state" || return 2
     test -z "$ignored_state" || return 2
   }
   routecontract_exact_checkout
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

1. Download the twelve exact project assets directly from the same GitHub prerelease into a new
   flat directory. Do not use a workflow artifact, local build, automatic GitHub source archive, or
   file sent by the maintainer.
2. Confirm the eleven payload names and `SHA256SUMS` match the activation record, and independently
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
   ROUTECONTRACT_RELEASE_ASSET_CONSUMER coordinate=io.github.ym0506.routecontract:routecontract-shardingsphere-5.5:0.1.0-rc2 result=VERIFIED_MYSQL
   ```

   For another RC, the marker must contain that exact activated version, not the
   `rc2` example above.

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
retry. Copy the exact `PUBLIC_RECRUITMENT_RECORD_PERMALINK` line from the
superseding Issue #9 opening comment into the fixed identity. Do not edit the
title or body afterward: the packaging gate requires GitHub's authenticated
Issue edit-history fields to show no editor, no last edit, and no retained content edit. Record each
later attempt as a timestamped issue comment with the exact new tag (if any), public help used,
changes, and one recovery status: `NOT_ATTEMPTED`, `ASSISTED_PASS`, or `ASSISTED_FAIL`.

If a deviation makes any required eligibility statement false, do not lie to submit the
version-specific Issue Form. Preserve only a privacy-minimized account in an ordinary issue or
comment when safe. A form-shaped Issue whose Task A result is `PROTOCOL_DEVIATION` or `NOT_RUN`
is contextual evidence and is deliberately excluded from the report's qualified-result count.

If a genuine product or documentation defect exists, preserve the first failure, open a focused
issue/PR, publish a new RC, and rerun. A same-participant rerun confirms that fix; a new eligible
participant provides stronger fresh-usability evidence. If no genuine defect exists, record
`no fix required`. Never invent a defect or PR to manufacture project history.

## Public report and authorship

Use only the record's exact `issueFormUrl`, and only while public `main` still equals the validated
activation-record commit; otherwise stop and require a fresh activation record. First confirm that
the URL's `template` query equals the record's version-derived `issueFormFilename`, then compare the
form source at the fixed `issueFormPermalink` with the form offered by that exact interactive URL.
Stop on any missing form, redirect to the default chooser, or content difference. Never replace
this process with a generic or manually selected Issue Form.
For the narrow automated report predicate, a non-owner `User` account files the Issue and checks
the first-person statement that the participant is a non-author. REST/GraphQL can bind that account,
the visible body and the absence of a retained edit; it cannot prove the person's private identity
or independence. A maintainer-transcribed note may preserve contextual feedback in a normal issue
or comment, but it does not satisfy this account/self-attestation predicate and must not use this
form by pretending the maintainer is the participant.

The issue asks four neutral questions:

1. Why is the intentional inner CI exit `1` expected while outer Quick Start exit `0` is success?
2. What does this attempt prove, and what does it not prove?
3. Would RouteContract help a real testing problem the participant has? `No` is valid.
4. Which step was least clear, and what exact documentation change is suggested?

## Evidence promotion and contest rubric boundary

- A Task A `UNASSISTED_PASS` in an Issue that satisfies the documented account, checked-statement
  and API-visible no-edit predicate can support the clean-Quick-Start portion of E08 and a limited
  participant-self-attested RC-usability statement in E10. Automation does not grade the remaining
  free-text answers or prove private independence.
- A Task B `UNASSISTED_PASS` under the same boundary can support only the exact-RC asset-install
  portion of E09.
  It does not satisfy stable-release E09.
- A real public blocker followed by a focused fix PR and new RC can support E13 project-management
  and community evidence. No defect means `no fix required`, not a fabricated PR.

These records may strengthen first-round OSS growth/documentation/management evidence and
final-round utility/community evidence. They do not prove innovation, license correctness,
upstream acceptance, security, performance, production suitability, broad adoption, or any contest
score.

Both tasks passing is required only for the narrow phrase “the participant account reported that
both the RC Quick Start and RC asset-install attempt passed.” Task A alone may be reported as Task A
only; Task B alone may be reported as Task B only. Never collapse partial outcomes into a combined
pass or turn the account's self-attestation into automated proof of human independence.

RC evidence cannot be promoted to final `v0.1.0`. The present form and protocol are RC-specific;
the final-stable report branch remains fail-closed until a distinct reviewed stable form, protocol
and body predicate exist and a new run targets the final annotated tag, Release, assets and
documentation. The project may separately report final maintainer CI/package verification, but it
must not label RC participant evidence as final independent-install validation.
