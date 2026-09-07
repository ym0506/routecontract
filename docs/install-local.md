# Install v0.1.2 in an existing test project

Use a small local Maven repository while RouteContract is not yet on Maven Central.
The same repository works with Gradle Groovy, Gradle Kotlin DSL and Maven. This
installs the released **v0.1.2** library, not unreleased features from `main`.

## Install once

You need Git, Python **3.10+**, curl and a POSIX environment (Linux or macOS).
Downloading the release needs public HTTPS access. Artifact installation does not
start Java, Docker, your application or its build.

```sh
git clone --depth 1 https://github.com/ym0506/routecontract.git routecontract-tools
cd routecontract-tools
python3 -I scripts/install-local.py
```

The last command installs into a new `.routecontract-v0.1.2` directory in the
current directory and prints a repository block and test dependency to copy into
your project. Keep that directory: your build will resolve the library from it.

Choose Maven output with `--format maven`. Choose a different **new** target with
`--repository /absolute/path/to/new-repository`; its parent must already exist.
An existing target is never replaced. If an installation fails, keep its output
directory and use a new destination on the next attempt.

```sh
python3 -I scripts/install-local.py --format maven --repository /absolute/path/to/new-repository
```

The frontend uses the existing fixed-hash public installer and tag-pinned release
assets. It retains the full release, archive, POM, checksum, destination and
evidence-review-expiry checks. There is no GitHub login, token or API requirement.
For the exact pinned bootstrap and supply-chain procedure, see the
[detailed installation reference](first-integration.md#2-install-the-exact-v012-release-assets).

## Add it to the test build

Add the printed configuration to your existing build; keep your project's current
ShardingSphere dependency and business assertions. The Gradle output works in
both `build.gradle` and `build.gradle.kts` and limits the local repository to the
RouteContract module. The Maven output uses a file repository and a normal
test-scoped dependency. Neither uses a system JAR path or adds the dependency to
your application's production runtime.

For Maven, merge the `<repository>` and `<dependency>` entries into your existing
`<repositories>` and `<dependencies>` elements. Create either outer element only
if it is absent; duplicating it makes `pom.xml` invalid.

The generated file URI names your local directory. For CI, install into a new
directory on that runner and use its URI; do not commit another person's local
path. Existing company repository policies may require adding the repository in
`settings.gradle(.kts)` or Maven settings instead of the project file.

## Check one operation

Released support is **Java 17 + exact ShardingSphere-JDBC 5.5.3**, synchronous
non-batch `PreparedStatement` operations. Successful installation does not prove
that a project's operation fits that boundary.

Start with an existing normally returning test and keep its result assertion:

```java
RouteSnapshot snapshot = RouteContract.capture("orders.find-by-user-id", () -> {
    Order actual = orderQueryService.findByUserId(3L);
    assertEquals(201L, actual.id());
});

RouteAssertions.assertThat(snapshot)
        .hasCompleteCapture()
        .hasNoReportedExecutionFailures()
        .hasExactlyObservedPhysicalAttempts(1);
```

The operation and expected count are examples: select your own representative
operation and review its expected count. Import `RouteContract`, `RouteSnapshot`
and `RouteAssertions` from `io.github.ym0506.routecontract`.

For a stored baseline and comparison on subsequent changes, continue with
[the manifest example](../README.en.md#approved-manifests-and-structural-manifest-diffs)
or the [integration reference](first-integration.md). Baseline review remains
explicit; installing the library does not approve an observed execution shape.
Framework-specific test classloaders may need their own dependency visibility configuration;
if capture cannot discover the provider, check the integration reference for that build lane.

## Acceptance and verification scope

The frontend must delegate to the existing verified installer and print usable
build configuration only after it succeeds. Relative destinations must become
absolute without hiding an existing target. Invalid arguments, an existing
destination, missing parents and installer rejection must fail without changing
existing contents or printing a successful dependency configuration. File URIs
must preserve paths containing spaces or non-ASCII characters.

Consumer verification must resolve the released thin POM and its dependencies in
an independent test project; a generated string alone is not installation
evidence. The existing real-MySQL standalone consumer separately checks physical
JDBC capture and contract rejection. This is maintainer verification, not an
independent user adoption claim.

The [consumer fixture](../examples/local-install-smoke/README.md) runs the exact
printed configuration in Gradle Groovy, Kotlin DSL and Maven with separate empty
caches. It checks published-JAR identity, POM runtime dependencies and manifest
acceptance/rejection (three tests per build format). CI runs this fixture alongside
the separate real-MySQL integration tests.
