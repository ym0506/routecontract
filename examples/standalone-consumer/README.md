# Standalone published-artifact consumer

This Gradle build is intentionally outside RouteContract's multi-project build. It has its own
`settings.gradle`, resolves RouteContract only by the published Maven coordinate, and uses an
exclusive repository rule for the RouteContract group. The test verifies that:

1. `RouteContract` was loaded from a JAR rather than a Gradle project output directory;
2. the JAR supplies the ShardingSphere `SQLExecutionHook` service descriptor;
3. ShardingSphere's service loader discovers the provider during `RouteContract.captureResult`;
4. one real ShardingSphere-JDBC 5.5.3 query reaches MySQL 8.4.11 and produces a complete,
   one-attempt observed execution snapshot.

This standalone build has its own dependency lockfile and SHA-256 verification metadata because it
does not inherit the root build's dependency controls.

The verification metadata trusts only a stable RouteContract first-party
group/artifact pattern because `install-release-assets.py` has already checked
that JAR and POM against the public Release `SHA256SUMS`. Third-party
dependencies remain checksum-verified; this exception does not disable Gradle
dependency verification globally.

Run the repository-level verifier, which publishes to an isolated temporary Maven repository first:

```bash
./scripts/verify-standalone-consumer.sh
```

That command is same-checkout packaging evidence. It proves that the generated
Maven publication can be consumed without a Gradle project dependency; it is
not an external-user installation or adoption claim.

After a stable GitHub Release exists, a fresh checkout can instead consume the
exact final Release assets without Maven Central hosting. Download every public
asset from that Release—including the main/sources/Javadoc JARs, POM, source
archive, direct and aggregate SBOMs, `test-summary.txt`, and `SHA256SUMS`—into
one flat directory. Then use an explicit empty Maven repository:

```bash
python3 ../../scripts/install-release-assets.py \
  --release-assets-dir /absolute/path/to/downloaded-release-assets \
  --repository /absolute/path/to/routecontract-maven
```

The offline installer verifies every downloaded public asset against
`SHA256SUMS`, validates the stable POM coordinate and JAR structure, and copies
the JARs plus versioned POM into the Maven layout. `SHA256SUMS` must list
exactly the other public payloads (not itself) and no workflow-only logs. The installer does not
read or modify `~/.m2`, and it refuses to overwrite an existing coordinate. A
checksum does not authenticate the publisher, so the input directory must
come from the final public GitHub Release.

To run this consumer directly, point it at a Maven repository containing the
same RouteContract group and version as the root build:

```bash
ROUTECONTRACT_REPOSITORY=/absolute/path/to/maven-repository \
ROUTECONTRACT_GROUP=io.github.ym0506.routecontract \
ROUTECONTRACT_VERSION=0.1.0 \
  ../../gradlew --no-daemon --refresh-dependencies -p . clean test
```

The repository-level verifier supplies these values from the root
`build.gradle`; this fixture does not pin an obsolete owner or snapshot
coordinate into release evidence.

For a one-command final-asset check, use a different empty target repository:

```bash
../../scripts/verify-release-assets-consumer.sh \
  /absolute/path/to/downloaded-release-assets \
  /absolute/path/to/empty-verification-maven
```

This command installs the checksummed final assets, gives the standalone build
an isolated temporary Gradle user home, and runs the real MySQL test with an
exclusive repository rule for the validated RouteContract group. Maven Central
is still used for third-party dependencies, so the consumer phase can require
network access; Java 17 and a running Docker daemon are required.
