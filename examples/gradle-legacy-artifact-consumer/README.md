# Gradle legacy ownership resolver fixture

This independent consumer is driven by
`scripts/verify-gradle-legacy-artifact-consumer.py`. It consumes pinned published
pre-0.2 JAR/POM bytes (and the public 0.1.3 `.module`) alongside a reviewed local
nine-payload 0.2.0 staging receipt. It does not build RouteContract from source.

`legacy-core-ownership.gradle` is the consumer-owned rule needed when an old
all-in-one artifact and the extracted core are both selected. Copy the script
into a consumer and apply it before dependency resolution:

```groovy
apply from: 'legacy-core-ownership.gradle'
```

For Kotlin DSL, the same Groovy script can be applied with:

```kotlin
apply(from = "legacy-core-ownership.gradle")
```

The script assigns `routecontract-core-owner:1` to pre-0.2 all-in-one component
metadata. The current core publishes that same capability, causing an actual
Gradle conflict. A normal request for old and current versions of the same GA
still mediates to 0.2.0. This is complementary to exact ShardingSphere version
constraints, which a real application must retain.

Run from the source checkout with Java 17 and Python 3.12:

```sh
python3 -I scripts/verify-gradle-legacy-artifact-consumer.py \
  --repository /absolute/reviewed-staging/repository \
  --staged-receipt /absolute/reviewed-staging/staged-receipt.json \
  --staged-source-revision FULL_REVIEWED_SOURCE_COMMIT \
  --evidence-directory /absolute/absent-evidence-directory \
  --java-home /absolute/jdk-17
```

The source revision must have identical production/publication inputs, including
embedded LICENSE/NOTICE, to the checkout under test. Each of 37 cases gets a
copied build and fresh dependency/project caches. Only the checksum-pinned
Gradle 8.14.4 distribution is seeded. `--gradle-distribution-zip` accepts an
already downloaded ZIP after checking the wrapper's exact SHA-256;
`--legacy-payload-directory` accepts `<version>/<canonical-filename>` inputs
after checking every registry pin and JAR/POM/module layout. Without that option
the runner downloads the registered public URLs over HTTPS.

Use repeated `--case CASE_ID` arguments for a diagnostic subset. Such a run is
always marked `PARTIAL_VERIFIED`; only the default complete matrix may set
`fullGradleA27Matrix: true`. `--workers` accepts 1–4 independent concurrent cases.

The evidence includes the rule-disabled legacy+core control, request orders,
applied capabilities, selected dependency graphs, actual selected first-party
JAR hashes, conflict reasons, commands, logs, source binding, and tool versions.
The resolver inspects transitive third-party metadata but only materializes
first-party JARs. This is not SQL, MySQL, runtime/classpath A-28, Maven, or public
0.2 publication evidence. See `docs/legacy-resolver-acceptance.md` for the boundary.
