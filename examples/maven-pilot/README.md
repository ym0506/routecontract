# Isolated Maven pilot fixture

This internal fixture exercises the narrow reference Maven path intended for adaptation in
external repositories. It is a
two-module reactor with a normal business test and an inactive
`routecontract-pilot` profile. With the profile absent, the local RouteContract repository,
dependency, pilot source, Jackson/Calcite/minidev convergence, and graph exclusions are all
inactive; the default test sources do not contain the pilot, its class is not compiled, and the
candidate and provider are absent. The verifier checks that boundary in Maven's generated effective
POM as well as in the source POM and resolved tree. With the profile active, a consumer cache that
began absent and was seeded by a profile-off reactor install—while the exact RouteContract
coordinate remained absent—must resolve the exact installed JAR and POM through
`checksumPolicy=fail`, run one ShardingSphere-JDBC 5.5.3/MySQL 8.4.11 operation, preserve the
business assertion, and write a candidate. Maven may also download ordinary plugins and project
dependencies during the seed.

The verifier deliberately exercises two outcomes:

1. the first opt-in run writes a candidate and fails only because no human-approved baseline
   exists;
2. an ephemeral test-harness copy of those exact candidate bytes is used to prove the mechanical
   candidate-match path.

The second step is test scaffolding, not human approval. This fixture, its synthetic baseline copy,
and maintainer-run CI are not external-user or adoption evidence.

Run it from the RouteContract repository root with exact Apache Maven 3.9.14, Python 3.10 or
newer, Docker, `curl`, and network access. The no-argument command keeps the Java 17 default. The
explicit second command runs the same complete fixture with Maven on Java 21 and compiles the
fixture's main and test classes to Java 21 classfile major 65:

```bash
./scripts/verify-maven-pilot.sh
./scripts/verify-maven-pilot.sh --java 21
```

Both cells retain exactly ShardingSphere-JDBC 5.5.3 and the digest-pinned MySQL 8.4.11 image. The
Java 21 cell is narrow same-checkout compatibility evidence for the immutable v0.1.2 JAR; it does
not broaden the separate external assisted runner or starter generator below, which remain Java 17
only. Neither cell is a human-approved external baseline, external adoption, or endorsement.

## One-command runner for an adapted external Maven pilot

After the target repository has the reviewed inactive `routecontract-pilot` profile and its two
tests, copy the [six-field JSON](assisted-pilot.example.json), replace every example value, and
keep the config at an absolute canonical path. Run the first candidate check from the
RouteContract checkout that contains the wrapper:

```bash
python3 -I scripts/run-assisted-maven-pilot.py \
  --config /absolute/path/to/routecontract-assisted-maven-pilot.json \
  --expected-outcome review
```

The wrapper derives the existing external verifier's twelve exact inputs. `reactorSelector` is the
owning POM path relative to `projectRoot` (for example, `integration-tests/pom.xml`, or `pom.xml`
for the reactor root), which avoids ambiguous duplicate Maven coordinates. The wrapper rejects
duplicate or unknown JSON keys, a selector that differs from that exact path, unsafe test
selectors, path escapes, symlinks in selected input/evidence paths, stale selected evidence,
ambient `ROUTECONTRACT_*` variables, and reviewed execution-bundle bytes whose SHA-256 differs
from the pins. It stages those verified bytes in the private temporary directory immediately
before execution. Project `.mvn`, if present, must be a real directory; `.mvn/maven.config`,
`.mvn/jvm.config`, and `.mvn/extensions.xml` are outside this isolated lane and make it stop before
Maven runs.

The wrapper downloads the exact [Apache Maven 3.9.14 binary archive](https://archive.apache.org/dist/maven/maven-3/3.9.14/binaries/apache-maven-3.9.14-bin.tar.gz),
requires SHA-512
`d50af8ab5e6005b46a07f0ce9d3719e67cfdf898da988a84871304cd59fb1af0fef2f99dea709e6e66f21f732f905979b5c2dce6b6860406f60a70e84d9cf0b8`,
rejects unsafe archive members, and runs it with a private home, temporary directory, empty user
and global settings/toolchains, and a clean environment. Ambient Maven/JVM settings, shell startup
files, proxy variables, and non-default Docker endpoint variables are not inherited. If a target
needs one of those inputs, this lane is not compatible; stop rather than weakening the evidence
boundary. The Java 17 runtime is selected from the caller's `PATH` and version-checked by the
verifier; its bytes are not pinned.

The wrapper never creates, copies, replaces, or deletes the approved baseline. A successful
`review` run therefore leaves the candidate in the target repository and still requires a person
to inspect it.

For the example values, those two paths are:

- candidate: `integration-tests/target/routecontract/orders.find-by-user-id.candidate.json`
- approved: `integration-tests/src/routeContractPilot/resources/route-contracts/orders.find-by-user-id.json`

Only after a person has copied the reviewed candidate bytes to the exact approved path, remove
exactly those of the three selected `target` evidence files that exist: that candidate and the two
Surefire XML reports named `TEST-<fully-qualified-class>.xml` from `profileOffTest` and
`pilotTest`. An earlier verifier clean may have
already removed one report. Never remove the approved
`src/routeContractPilot/...` file. This cleanup is explicit because the wrapper neither deletes
evidence nor treats a stale file as a fresh result. The same config can then be checked in
`matched` mode:

```bash
python3 -I scripts/run-assisted-maven-pilot.py \
  --config /absolute/path/to/routecontract-assisted-maven-pilot.json \
  --expected-outcome matched
```

The wrapper requires the approved file's hard-link count to be exactly one and snapshots its
device, inode, mode, owner, group, link count, size, modification/change times, and SHA-256 before
execution. It runs the staged verifier in a new process group, accepts and replays at most 1 MiB
of combined stdout/stderr from private temporary files, kills the group when it observes the
limit exceeded, drains same-group descendants, and then requires the
same baseline identity, including when the verifier fails or receives `INT`, `TERM`, or `HUP`.
It also rejects a candidate or report that shares the baseline inode and requires the verifier's
exact success marker before printing the wrapper marker. It does not rerun or repair a failed
invocation. The six fields do not require SQL, bind values, JDBC URLs, topology, credentials, or
an approval statement; do not put those values in the config.

This is strict environment and same-process-group isolation, not a security sandbox. It cannot
guarantee cleanup after `SIGKILL` or power loss, stop descendants that deliberately escape the
group with `setsid`/`setpgid`, or defend against privileged or concurrent writers changing the
repository while the command runs. Run it only in a reviewed checkout without concurrent writers,
and inspect the repository afterward if the host or process is forcibly terminated.

The external integration guide must continue to require a person to review and approve a real
repository's candidate. Never reuse this fixture's candidate, alias, policy, or synthetic copy as
another repository's baseline.

## Review-only starter bundle

`scripts/render-maven-pilot-starter.py` reduces the mechanical first-pass work for a narrow Maven
target without touching that target. It supports only a clean Git worktree at an exact commit,
Java 17, Apache Maven 3.9.14, exactly ShardingSphere-JDBC 5.5.3, and the existing isolated
`routecontract-pilot` semantics. It is not a general POM merger or operation detector.

Copy [`starter.example.json`](starter.example.json) outside the target repository, replace the
target-specific paths, commit/POM digests, test and Java identifiers, operation, budgets, aliases,
and dependency scope, and bind `expectedTargetCommit` and `expectedPomSha256` to the clean target
checkout. Preserve `schemaVersion`, `profileOffTestShape`, and the four exact tool/dependency
version fields; the renderer rejects any drift in those fixed boundary values.
The target root and owning module must both have tracked, mode-`100644` POMs. The strict JSON rejects
duplicate or unknown keys, unsupported versions, unsafe Java/path identifiers, alias collisions,
ambiguous or pre-existing pilot configuration, symlink traversal, a dirty/moved target, and stale
candidate, test, or baseline paths.

Choose a new absent output directory outside the target under an existing canonical directory that
you own, that is not group- or other-writable, and that has no macOS extended ACL, then run from
this RouteContract checkout:

```bash
python3 -I scripts/render-maven-pilot-starter.py \
  --config /absolute/path/to/routecontract-maven-starter.json \
  --output /absolute/path/to/new-routecontract-review-bundle
```

The exact success marker is:

```text
ROUTECONTRACT_MAVEN_PILOT_STARTER targetCommit=<40-hex> manifestSha256=<64-hex> files=5 VERIFIED
```

The mode-`0700` bundle contains five mode-`0600` files:

- `routecontract-pilot.patch`: a deterministic two-path review patch for the owning POM and one new
  pilot test;
- `assisted-pilot.json`: the existing six-field runner input; it is host-local because it retains
  the target's absolute `projectRoot`, so do not commit it or copy it to another checkout;
- `pilot-spec.json`: normalized review inputs, including sorted aliases and explicit budgets; it
  retains the same host-local absolute `projectRoot`, so review it but do not commit or copy it;
- `NEXT-STEPS.md`: the candidate → human review → matched-check sequence;
- `bundle-manifest.json`: a generation-time target record, template hashes, output hashes, and an
  explicit `baselineGenerated: false` statement. It is not a consume-time guard: immediately
  before review or application, require the same clean commit and owning-POM SHA-256 or rerun the
  generator.

Retain the success marker separately from the bundle. Before consuming the output, require the
SHA-256 of `bundle-manifest.json` to equal its `manifestSha256` field and verify every byte count and
SHA-256 under `generatedFiles`. This detects a named output directory replaced after rendering.

The generated Java test contains `ROUTECONTRACT_STARTER_REVIEW_REQUIRED` inside its capture block.
It therefore cannot create a candidate or accidentally pass until a target maintainer replaces that
single fail-closed statement with one supported operation and preserves the operation's existing
business assertion. The generator never applies the patch, runs target code, creates or copies a
baseline, claims approval, or changes the target repository's Git status. Review the bundle's
`NEXT-STEPS.md` before any manual target action. A successful render is `verified - unit` evidence about bundle generation,
not MySQL evidence, an external integration, adoption, or endorsement.

The selected `profileOffTest` is restricted to one ordinary, non-parameterized Surefire testcase;
declare that shape explicitly in the strict config. The isolated profile pins JUnit Jupiter,
test compilation at Java 17, and the default XML report path/name expected by the existing runner.
The reactor and owning POMs must not customize the build directory or Surefire report directory,
report suffix, or XML-report setting. Their effective inherited model must likewise preserve the
default `target/surefire-reports/TEST-<fully-qualified-class>.xml` layout; if the wrapper cannot
observe that exact layout, stop instead of treating a missing report as evidence. The generator
checks every canonical tracked local parent POM between the owning module and reactor root. An
external parent above the reactor root remains an explicit consume-time compatibility boundary;
the wrapper's exact report requirement is the final fail-closed check.
Any nonzero renderer exit makes every file at the requested output path invalid; never use a
partial or concurrently changed directory.
