# Contributing

## Development prerequisites

- JDK 17
- Docker for MySQL integration tests
- Git, Python 3, Bash or equivalent POSIX tooling, and network access for public release checks

## Change workflow

1. Open an issue that states the user-visible route regression or missing capability.
2. Add or update a specification and a failing test.
3. Keep the implementation focused on one contract or invariant.
4. Run unit and MySQL integration tests.
5. Document exact versions, evidence and limitations in the pull request.

## Claims and privacy

Use the terminology in [docs/specification.md](docs/specification.md). Never include real credentials, production or sensitive parameter values, customer identifiers, or production topology in fixtures, logs, or issues. Synthetic, non-sensitive test values are allowed; RouteContract snapshots and manifests must not retain their raw values.

## Verification

Run the complete unit, real-MySQL integration and SBOM checks with:

```bash
./gradlew --no-daemon --no-build-cache clean check validateOfficialCycloneDxSbom
```

Verify that a standalone consumer can resolve and run this checkout's generated Maven publication
from an isolated temporary repository rather than use an in-repository Gradle project dependency with:

```bash
./scripts/verify-standalone-consumer.sh
```

This is same-checkout packaging evidence, not proof of a public Release, registry publication,
external installation, or adoption. After a Release exists, use
`scripts/verify-release-assets-consumer.sh` for its downloaded assets.

A change is not complete until it passes the appropriate real-MySQL test, not only an in-memory
substitute.

## Release feedback

For a current or stable release, use the Route regression, Product bug, or Feature proposal Issue
Form and include the exact version, environment, minimized reproduction, and documented claim
boundary. First failures and later assistance must remain visible.

The [independent installation study](docs/independent-install-study.md) and its RC1/RC2 forms are
retained as version-bound evidence contracts. Use a dedicated RC form only while that candidate's
activation gate and recruitment window are active and public `main` remains its activation-record
commit. After that lifecycle ends, do not present ordinary stable feedback, same-checkout tests, or
AI runs as counted independent-install evidence.
