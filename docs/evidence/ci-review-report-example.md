# RouteContract review

**POLICY_VIOLATION** · Strict check exit: 1

| Observation | Baseline | Candidate | Baseline limit |
| --- | ---: | ---: | ---: |
| Physical JDBC execution attempts | 1 | 2 | 1 |
| Distinct observed data-source aliases | 1 | 2 | 1 |
| Callback failures | 0 | 0 | 0 |
| Unknown outcomes | 0 | 0 | 0 |

Baseline capture: COMPLETE. Candidate capture: COMPLETE. Baseline requires exact signatures: true.

## Findings and next steps

- **RCM201 · BLOCKING · ATTEMPT_BUDGET_EXCEEDED** — Inspect changed sharding predicates, rewritten SQL shape and repeated executions; verify whether the increase is intentional.
- **RCM202 · BLOCKING · DATA_SOURCE_BUDGET_EXCEEDED** — Review the observed alias set and sharding predicates against the baseline's data-source budget.

Findings: 2 total; 0 omitted from this bounded report.

Findings show the verifier's highest-precedence failing level; later checks may not have run.

## Evidence identity

- Baseline canonical SHA-256: `a082ca797ebe40be5b8c9409893de7d9a861086d8d4b760cbc00e925b2436a60`
- Candidate canonical SHA-256: `be65fe9b0c6469aaabcb4aefebb95ce7790c74ac0c0b3b229df1b228da9f4738`

Canonical digests identify manifest content, not original file bytes, freshness or human approval. Operation IDs, aliases, type names and free-form diff details are omitted; inspect the minimized manifests locally.

ShardingSphere SQLExecutionHook-reported physical JDBC execution attempts; not a complete route plan, transaction commit, business success or performance measurement. Keep the business-result assertion and review intentional baseline changes.
