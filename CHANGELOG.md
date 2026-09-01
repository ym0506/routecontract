# Changelog

RouteContract follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) for public version identifiers.

## Unreleased

### Added

- Add an inactive-by-default Gradle Kotlin DSL assisted-pilot lane with exact `v0.1.2` local
  repository provenance, real MySQL verification, missing-baseline failure, and a separate
  synthetic match check.
- Add a separate Java 21 Maven compatibility cell that compiles the checked-in fixture to classfile
  major 65 and runs its full exact ShardingSphere-JDBC 5.5.3/MySQL 8.4.11 candidate workflow.

### Boundaries

- The fixture, CI result, and synthetic match are maintainer-side verification only. They do not
  establish a human-approved external baseline, adoption, production use, or endorsement.
- Java 21 evidence is limited to the checked-in same-checkout Maven fixture. The external assisted
  runner and starter remain Java 17 only. This 5.5.3-specific adapter does not add support for any
  other ShardingSphere version; the audited 5.5.0/5.5.2 variants require separate adapters.

## [0.1.2]

This section records the narrow recovery source delta prepared for stable version `0.1.2`. Its
presence alone does not prove that an annotated tag, public immutable non-prerelease Release,
same-revision release-evidence run, Maven Central publication, or external-user result exists.

### Changed

- Refresh the pinned official Maven OSV database generation after the `v0.1.1` exact-tag evidence
  attempt stopped before Release creation because its pinned official generation returned HTTP 404.
- Advance only the release-target source identity and its corresponding README declarations from
  `0.1.1` / `v0.1.1` to `0.1.2` / `v0.1.2`; runtime and API behavior are unchanged.

### Boundaries

- The annotated `v0.1.1` tag is preserved and unmoved, and no `v0.1.1` GitHub Release was published.
- This recovery refreshes the external OSV evidence input and source identity only; it makes no claim
  of Maven Central availability, external users, adoption, production use, or endorsement.

## [0.1.1]

This section records the source delta prepared for stable version `0.1.1`. Its presence alone does not prove
that an annotated tag, public immutable non-prerelease Release, same-revision release-evidence run,
Maven Central publication, or external-user result exists.

### Added

- Add a neutral stable-feedback form and assisted-pilot onboarding for one representative operation.
- Add isolated Gradle Groovy and Maven 3.9.14 first-integration lanes, provenance verification, and
  checked-in Quarkiverse compatibility-pilot reproduction materials.
- Add local Maven publication metadata, signing/staging checks, and maintainer procedures for a future
  Maven Central deployment.

### Changed

- Harden CI, release-evidence, SBOM, supply-chain, isolated-consumer, and submission-package checks,
  and surface the public demonstration and onboarding paths in both READMEs.

### Boundaries

- Runtime/API behavior and the supported Java 17, ShardingSphere-JDBC 5.5.3, synchronous non-batch
  `PreparedStatement` boundary are unchanged from `0.1.0`.
- The immutable `v0.1.0` GitHub Release remains the verified public installation path until any
  `0.1.1` registry publication passes anonymous postpublication verification.
- Feedback, pilot fixtures, CI success, and maintainer-local reproduction do not by themselves establish
  external adoption, production use, or endorsement.

## [0.1.0]

This section records the source delta for stable version `0.1.0`. Its presence alone does not prove
that an annotated tag, public immutable non-prerelease Release, same-revision release-evidence run,
or final contest package exists.

### Changed

- Finalize the Maven coordinate and generated artifact/SBOM version identity as `0.1.0`.
- Clarify the product, maintainer, and contest-only boundaries and the structural-manifest-diff
  problem statement.
- Pin stable release evidence to Temurin 17.0.20.1+1 and disclose, inventory, and verify the
  OpenJDK `GPL-2.0-only WITH Classpath-exception-2.0` and jQuery MIT assets in the Javadoc
  classifier.
- Make the opt-in built-asset/MySQL acceptance test fail fast unless it is run with that exact
  release toolchain, while keeping ordinary development builds on the documented Java 17 boundary.

### Boundaries

- Runtime/API behavior and the supported Java 17, ShardingSphere-JDBC 5.5.3, synchronous non-batch
  `PreparedStatement` boundary are unchanged from `0.1.0-rc2`.
- RC assets and RC-only participant evidence are not promoted to stable validation or adoption.

## [0.1.0-rc2]

This corrective prerelease candidate follows the preserved `v0.1.0-rc1` tag. RC1's
release-evidence run failed before workflow-artifact upload because a digest-qualified MySQL pull
did not necessarily retain the mutable `mysql:8.4.11` local tag; no RC1 Release was created.

### Fixed

- Resolve the staged MySQL image by its pinned repository digest and require one exact image ID,
  then verify the observed `RepoDigests` field rather than trusting an echoed expected value.

### Added

- Add the reviewed, version-specific `independent-rc2-install.yml` while preserving the RC1 form
  byte-for-byte, and extend the final package allowlist to bind either form to its own reviewed hash.

### Boundaries

- RC2 changes release evidence, version identity, and activation-form provenance only; it does not
  expand the RouteContract runtime or supported ShardingSphere boundary.

## [0.1.0-rc1]

This section defines the source contents of prerelease candidate `0.1.0-rc1`. It does not assert
that its annotated tag, GitHub prerelease, immutable asset set, release-evidence run, or independent
non-author result exists. Those event-dependent facts belong in a validated fixed activation record
created only after publication.

### Added

- Operation-scoped ShardingSphere-JDBC 5.5.3 `SQLExecutionHook` capture.
- Fail-closed runtime/SPI preflight and callback lifecycle diagnostics.
- Attempt and data-source budgets with value-minimized snapshots.
- Canonical approved manifests, deterministic structural manifest/attempt diff with stable RCM
  codes, and CI assertions.
- Real MySQL regression, determinism, concurrency, failure-boundary, and privacy fixtures.
- Standalone generated-Maven-publication consumer, SBOM generation, and release-evidence workflow with a
  strict revision-bound, privacy-minimized full-suite test summary.
- Fail-closed no-registry installation from the exact checksummed public Release assets into an
  explicit file Maven repository, plus a real-MySQL final-asset consumer gate.
- A template-only independent-RC activation record and fail-closed validator that require real
  annotated-tag, immutable-prerelease, release-evidence, checksum, and attestation identities.

### Security

- Raw SQL, parameter values, connection properties, and exception messages are not retained.
- Callback failures, interruptions, unsupported runtimes, excessive attempts, and collector faults
  cannot pass a route contract.

### Boundaries

- Hook-reported physical JDBC execution attempts are not a complete route plan, physical-table
  count, enclosing JDBC completion, transaction commit, or business-success signal.
- v0.1 does not cover batch execution, arbitrary async/reactive propagation, SQL Federation,
  ShardingSphere-Proxy, automatic topology discovery, or ShardingSphere versions other than 5.5.3.
