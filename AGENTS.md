# RouteContract contributor instructions

## Purpose

RouteContract records physical JDBC execution attempts reported by Apache ShardingSphere-JDBC 5.5.3 `SQLExecutionHook` during a named application operation, then verifies explicit budgets and an approved manifest in CI.

## Claim boundary

- Say `SQLExecutionHook`-reported `physical JDBC execution attempt`, never `complete route plan`.
- Describe `finishSuccess` only as the hook report made after the wrapped physical `executeSQL` call returned; do not infer completion of the enclosing JDBC operation, transaction commit or business success.
- Do not claim automatic full-route detection without a caller-supplied target universe.
- Do not call hook event count a physical-table count; one execution may contain a rewritten `UNION ALL` over multiple tables.
- Do not publish raw SQL parameters or connection properties.
- Qualify concurrency claims by the exact repeated MySQL integration test and supported synchronous PreparedStatement boundary.

## Workflow

For non-trivial changes:

1. Update the specification or acceptance test first.
2. Establish a business-green/route-red failing case before the fix.
3. Implement the smallest coherent product behavior.
4. Run unit tests and real ShardingSphere-JDBC/MySQL integration tests.
5. Record exact versions, repetitions, raw result path, limitations and evidence label.
6. Keep commits and pull requests focused and reviewable.

Tests passing alone is not completion. A claim also needs a reproducible command, an environment label and a stated limitation.

## Evidence labels

- `verified - unit`
- `verified - H2`
- `verified - MySQL`
- `verified - ShardingSphere-JDBC 5.5.3`
- `reasoned hypothesis`
- `unverified`
- `planned`

These labels describe the environment and verification boundary of a technical claim. Artifact
maturity terms in `docs/evidence-matrix.md` (for example `artifact-ready` or `pending`) are a
separate axis and must not replace the applicable evidence label.

H2 evidence never proves MySQL behavior.

## v0.1 non-scope

- ShardingSphere-Proxy
- batch semantics
- arbitrary application async propagation
- SQL Federation coverage
- automatic topology discovery
- multiple ShardingSphere versions
- dashboard, Java Agent, Spring Boot starter or AI features
