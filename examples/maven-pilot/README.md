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

Run it from the RouteContract repository root with Java 17, exact Apache Maven 3.9.14, Python
3.10 or newer, Docker, `curl`, and network access:

```bash
./scripts/verify-maven-pilot.sh
```

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
