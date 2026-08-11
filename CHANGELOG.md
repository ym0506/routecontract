# Changelog

RouteContract follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and intends to use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) after the first public release.

## Unreleased

### Added

- Operation-scoped ShardingSphere-JDBC 5.5.3 `SQLExecutionHook` capture.
- Fail-closed runtime/SPI preflight and callback lifecycle diagnostics.
- Attempt and data-source budgets with value-minimized snapshots.
- Canonical approved manifests, semantic diff, and deterministic CI assertions.
- Real MySQL regression, determinism, concurrency, failure-boundary, and privacy fixtures.
- Standalone published-JAR consumer, SBOM generation, and release-evidence workflow with a
  strict revision-bound, privacy-minimized full-suite test summary.
- Fail-closed no-registry installation from the exact checksummed public Release assets into an
  explicit file Maven repository, plus a real-MySQL final-asset consumer gate.

### Security

- Raw SQL, parameter values, connection properties, and exception messages are not retained.
- Callback failures, interruptions, unsupported runtimes, excessive attempts, and collector faults
  cannot pass a route contract.

No public version has been released yet.
