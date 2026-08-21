# Changelog

RouteContract follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) for public version identifiers.

## Unreleased

No changes yet.

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
- Canonical approved manifests, semantic diff, and deterministic CI assertions.
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
