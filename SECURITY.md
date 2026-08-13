# Security policy

RouteContract processes rewritten SQL metadata in application tests. A report can reveal database topology even when parameter values are removed.

An unsalted SQL SHA-256 fingerprint is pseudonymous, not anonymous. A party that can guess a low-entropy statement can reproduce its hash. Keep manifests in repositories whose readers are permitted to learn the corresponding operation and topology, and use deterministic `PreparedStatement` SQL without confidential inline literals in v0.1.

## Supported versions

Only the latest tagged `0.1.x` release will receive security fixes during the initial project phase.

## Reporting a vulnerability

Report a vulnerability through a [GitHub private security advisory](https://github.com/ym0506/routecontract/security/advisories/new).
Do not open a public issue containing credentials, SQL parameter values,
connection URLs, production topology or an unredacted scanner result.

## Experimental local dependency review boundary

An optional local audit rejects existing final-scan evidence, then regenerates
the enumerated aggregate, published-module and MySQL-example CycloneDX JSON/XML
SBOM pairs plus the generated publication POM from the exact clean revision. It
checks them with a checksum-pinned OSV-Scanner 2.5.0 binary and a
generation-pinned Maven vulnerability database. Network downloads and checksum
verification finish before the scanner runs offline with an explicit tracked,
empty configuration. A strict local policy then rejects an unreviewed finding,
an expired or unused exception, an unexpected package set, or
missing/ambiguous license metadata. The aggregate dependency set must equal the
union of both direct profiles. Test-only policy scopes must match the example
BOM and must be absent from the complete published-module profile; the
publication POM is cross-checked against the published BOM's dependency graph.
The pinned MySQL fixture must additionally be an excluded container with the
explicit `routecontract:usage=test-only` property.

The policy has only these three vulnerability exceptions, each expiring on
**2026-08-27**:

- `commons-lang:commons-lang:2.4` — `GHSA-j288-q9x7-2f5v`;
- `net.minidev:json-smart:2.5.0` — `GHSA-pq2g-wx69-c263`;
- `org.apache.calcite:calcite-core:1.40.0` — `GHSA-c2rv-hwqm-wjpg`.

All three are confined to the repository's test/example dependency graph
reached through ShardingSphere 5.5.3's SQL Federation modules. SQL Federation
coverage remains outside v0.1 scope. None of these coordinates is declared in
RouteContract's published POM, and the exceptions are not a claim that those
dependencies are safe for production use. Upgrading or removing them requires
ShardingSphere-compatible test evidence; otherwise the exception must expire
and fail the local audit.

The raw OSV JSON and sanitized summary are local development outputs and must
not be published or uploaded. The v0.1 Release evidence workflow and final
package allowlist do not run or retain this audit. Consequently it must not be
presented as public, immutable, release-bound or contest evidence. A future
integration must update the workflow artifact schema and packaging verifier in
the same reviewed change.

The local audit assumes a cooperative release process in a trusted,
access-restricted checkout with no concurrent writer. Its path, checksum and
before/after checks detect stale, redirected and ordinarily mutated artifacts;
they are not an OS sandbox or a guarantee against a malicious same-UID process
that can change files or process state during execution.

## Data-handling boundary targeted by v0.1

RouteContract does not retain parameter values, connection properties, exception messages or raw
SQL. The remaining metadata is minimized, not anonymous, and differs by surface:

- An in-memory `RouteSnapshot` retains the clear-text caller-supplied `operationId`, raw
  hook-reported data-source names, SQL fingerprints, parameter counts and ordered Java type names,
  trunk/worker flags, callback outcomes, collector diagnostics and the exception class name for a
  callback-reported failure.
- A canonical manifest replaces raw hook-reported data-source names with caller-defined aliases. It
  retains the clear-text `operationId`, aliases, SQL fingerprints, parameter counts and Java type
  names, callback outcomes, multiplicities, counts and policy values. It does not retain the
  trunk/worker flag or reported exception class.
- Direct `RouteAssertions` failure messages can print the clear-text `operationId` and raw
  hook-reported data-source names. Manifest verification output can print operation IDs, aliases,
  fingerprints, Java type names, outcomes and finding details. Those strings can reach local test
  output or CI logs.

Use static, non-sensitive operation IDs and aliases. v0.1 rejects blank values but does not reject or
escape every control character in caller-supplied operation IDs, aliases or hook-reported names; it
therefore makes no log-injection or one-line-log safety claim. Do not source those labels from
untrusted request data. Java type names can reveal internal package structure, aliases can reveal
topology by convention, exception classes can reveal implementation choices, and low-entropy SQL
fingerprints can be guessed.

Treat snapshots, manifests, candidate diffs and CI logs as internal engineering artifacts. Install
RouteContract as a test-scoped dependency and do not attach real production topology or customer
identifiers to contest evidence. These boundaries describe retained fields; they are not a general
privacy, anonymization or log-sanitization guarantee.
