# Public Maven split-artifact consumer

Status: acceptance specification for the post-publication `0.2.x` Maven gate. Positive live
Central consumption is unverified until all checks below run against published candidate bytes.

## Acceptance contract

- Accept a reviewed nine-payload receipt (`jar`, `pom`, `module` for core and both adapters),
  validated by `public_split_artifacts.load_consumer_receipt`. Only strict stable `0.2.x` versions
  are supported; the receipt identifies expected bytes, not approval provenance by itself.
- Use Maven 3.9.14 and Java 17, with a fresh external consumer directory and absent Maven cache
  for each exact ShardingSphere runtime, 5.5.2 and 5.5.3.
- Supply explicit user and global settings whose sole mirror has `mirrorOf=*` and the fixed
  unauthenticated URL `https://repo.maven.apache.org/maven2`. No local staging endpoint, alternate
  repository, credentials, reactor, source dependency, existing cache, or repository override is
  accepted. Pin Maven's native Resolver transport and disable HTTP redirects. Clear inherited
  Maven/JVM command injection variables and pin the base directory for every invocation so
  ancestor `.mvn` configuration cannot change the run.
- Reuse the Maven POM and Java fixture by copying them into the temporary consumer. Bind the
  receipt version in the copied POM and Enforcer rule; keep Java and approved manifests unchanged.
  The adapter is the only direct first-party request, and core must resolve transitively.
- Check both selected first-party JAR/POM hashes against the receipt and require Maven origin
  records for the fixed Central mirror. Every selected ShardingSphere component must match the
  exact runtime. The loaded Java classes and unique hook provider must match expected JAR hashes.
- Require all three real-MySQL tests per lane: exact business rows, reviewed schema-2 MATCH, and
  same-result physical attempts increasing from 1 to 2 rejected by candidate assertions and both
  CLI report formats with entry-point return code 1.
- Execute ordinary wrong-runtime, wrong-non-anchor with correct anchors, and both adapter-order
  negative dependencies. Preserve the selected graphs and require the offending GAV in explicit
  `BannedDependencies` rejection output. Download failures are not policy passes.
- Retain the reviewed receipt, copied inputs, settings, logs, downloaded first-party artifacts,
  Maven origin records, JUnit, reports and partial summary on failures/timeouts. Mark public
  consumption verified only after both complete lanes pass. An unpublished coordinate must fail.

## Command

```sh
python3 scripts/verify-public-maven-artifact-consumer.py --receipt /absolute/reviewed-receipt.json --evidence-directory /absolute/new/public-maven-evidence --java-home /absolute/jdk17/home
```

`--maven` optionally selects Maven 3.9.14; otherwise `MAVEN_BIN` or `mvn` on PATH is used.
The evidence directory must be new, outside the source checkout and separate from the receipt.
Docker and network access are required. This command does not publish any artifacts or alter a
release guard. The reviewed receipt must first correspond to the intended release's staged bytes.

## Verification boundary

Implementation/command tests can verify preparation and failure behavior before publication.
They do not establish successful anonymous Central installation. Until live positive execution
succeeds, downloaded-byte provenance, real-MySQL results and eight policy rejection cases through
this public path remain unverified. Prior local staged MySQL evidence remains a separate claim.
