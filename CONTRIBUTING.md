# Contributing

## Development prerequisites

- JDK 17
- Docker for MySQL integration tests

## Change workflow

1. Open an issue that states the user-visible route regression or missing capability.
2. Add or update a specification and a failing test.
3. Keep the implementation focused on one contract or invariant.
4. Run unit and MySQL integration tests.
5. Document exact versions, evidence and limitations in the pull request.

## Claims and privacy

Use the terminology in [docs/specification.md](docs/specification.md). Never include real credentials, parameter values, customer identifiers or production topology in fixtures, logs or issues.

## Verification

Run the complete unit, real-MySQL integration and SBOM checks with:

```bash
./gradlew --no-daemon --no-build-cache clean check prepareVerifiedSbom
```

Verify that a consumer can resolve and run the published JAR rather than an in-repository project
dependency with:

```bash
./scripts/verify-standalone-consumer.sh
```

A change is not complete until it passes the appropriate real-MySQL test, not only an in-memory
substitute.
