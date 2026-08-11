# Security policy

RouteContract processes rewritten SQL metadata in application tests. A report can reveal database topology even when parameter values are removed.

An unsalted SQL SHA-256 fingerprint is pseudonymous, not anonymous. A party that can guess a low-entropy statement can reproduce its hash. Keep manifests in repositories whose readers are permitted to learn the corresponding operation and topology, and use deterministic `PreparedStatement` SQL without confidential inline literals in v0.1.

## Supported versions

Only the latest tagged `0.1.x` release will receive security fixes during the initial project phase.

## Reporting a vulnerability

Until a dedicated private reporting channel is published, do not open a public issue containing credentials, SQL parameter values, connection URLs or production topology. Contact the repository owner privately through the verified contact method on the public repository profile.

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
