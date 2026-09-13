# Compare the official ShardingSphere Agent on the same MySQL calls

This opt-in experiment compares **released RouteContract 0.1.3** and official
**ShardingSphere Agent/JDBC 5.5.3**, with inner datasource-proxy listeners as an
independent observation point. It does not change RouteContract's product API,
normal test tasks, or release artifacts. [Acceptance specification](ACCEPTANCE.md).

The question is what the Agent exports, and what additional work turns that
telemetry into an operation contract. The classifier accepts both complete
fan-out exports and reduced child counts; it does not prescribe a winning tool.

## Run locally

Prerequisites: Java 17 (`JAVA_HOME` must point to it), Maven, Python 3.11 or later,
curl, and a running Docker daemon. Maven 3.9.14 is pinned in the manual workflow.
The first run downloads dependencies, the official 45 MB Agent archive, and the
pinned MySQL image. It uses only disposable databases.

```sh
cd experiments/agent-comparison
python3 -m unittest -v
python3 run.py
```

The runner verifies the exact SHA-512 published by
[ASF](https://archive.apache.org/dist/shardingsphere/5.5.3/apache-shardingsphere-5.5.3-shardingsphere-agent-bin.tar.gz.sha512)
before using the archive. An existing archive may be supplied with
`--archive /path/to/archive.tar.gz`; the same size and hash checks apply.

Maven compiles a standalone consumer and resolves its classpath. Only the
subsequent, dedicated JUnit Console JVM receives `-javaagent`. No agent is
attached to Maven or Gradle. The POM inherits the first-project example's
explicit dependency overrides; it is not an unmodified transitive dependency
graph. The runner rejects non-5.5.3 ShardingSphere JARs and any RouteContract
runtime other than the single 0.1.3 artifact.

## What is measured

Twenty sequential, caller-named operations each perform an equality read and a
same-value range read. Both must return the complete order `(201, 3, PAID)`.
The datasource-proxy listener must observe `1 + 2` backing JDBC callbacks, and
RouteContract must record three complete hook-reported physical JDBC execution
attempts. All twenty normalized RouteContract signatures must agree.

A two-party barrier holds the backing fan-out calls until both have entered.
Twenty completed barriers establish physical callback overlap in this fixture.
This does not establish arbitrary async support or timing behavior elsewhere.

The Agent uses always-on sampling, a queue capacity of 2,048 spans, and an
in-memory Zipkin receiver bound only to `127.0.0.1`. The verifier requires forty
root statements, valid execute-parent links, unique span identities, classified
SQL/bind shapes, and normal-success execute status. Each equality root must have
one child; each fan-out root is separately classified as having one or two
children. Missing roots, missing all children, duplicate spans, orphan spans,
unknown SQL shapes, or unexpected status invalidate the measurement.

The synthetic Python tests verify full, reduced, and mixed export outcomes plus
invalid evidence and receiver limits. They are not native Agent measurements.

## Outputs and privacy

Only `target/comparison/summary.json` and `junit-sanitized.xml` are intended for
publication. The JSON includes aggregate measurements, reviewed `left`/`right`
aliases, exact versions and hashes, source identity, and actual JUnit Console
counts. The XML is a **sanitized projection of the successful console result**,
not an original raw JUnit XML report. No native report writer is enabled.

Raw telemetry and JVM output remain in bounded memory and are discarded. The
receiver limits requests, compressed/decompressed bodies, total memory, and
workers. Agent logging/metrics plugins are not enabled. No raw SQL, bind values,
connection endpoints, trace IDs, or raw data-source names are published.

## Evidence status and interpretation

The [opt-in workflow](../../.github/workflows/agent-comparison.yml) is separate
from required CI. Run it manually in Actions, or apply the `run-agent-comparison`
label to a pull request. Public comparison evidence still requires a successful run
bound to this source revision and its digest-identified artifact. Local results
are author-run evidence; they do not establish external adoption. Historical
closed PRs [15](https://github.com/ym0506/routecontract/pull/15) and
[17](https://github.com/ym0506/routecontract/pull/17) are not evidence for this run.

Agent/OTel telemetry can be assembled into a contract. An Agent-only workflow
must select and relate root/child spans to a named operation, minimize values,
map identities to stable aliases, normalize observations, store/review a
baseline, and assert the intended budgets or structural differences. This
experiment implements collection, classification, aliasing, and assertions; it
does **not** implement a complete Agent-only baseline product or estimate a
general engineering cost. RouteContract's proposed benefit is packaging that
ShardingSphere-specific workflow.

Any reduced export count is an observation for this forced-overlap fixture;
it is not by itself a diagnosis, universal loss rate, or superiority claim.
There is no performance conclusion, cross-version generalization, batch claim,
transaction/commit proof, or arbitrary application async claim.

The Java fixture and bounded receiver were adapted from closed PR15 at
`788b4684cef53d9377582540a8f266c61b6c22e7`; the replacement verifies full business
rows, uses public 0.1.3, and classifies fan-out outcomes without fixing them in
advance. The official Agent remains an external Apache-2.0 test input. Codex
materially assisted the experiment and documentation.
