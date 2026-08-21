## Problem and scope

- Resolves:
- User-visible route regression or invariant:
- Explicit non-scope:

## Evidence

- [ ] Specification or acceptance test changed before implementation where applicable.
- [ ] Unit tests pass.
- [ ] Real MySQL/ShardingSphere-JDBC 5.5.3 test passes where behavior crosses the SPI boundary.
- [ ] Clean same-checkout generated-publication consumer still passes when packaging changes.
- [ ] Exact command, versions, repetitions, and limitations are recorded.

## Claim and privacy review

- [ ] Claims say “ShardingSphere 5.5.3 `SQLExecutionHook`-reported physical JDBC execution attempt,” not complete route plan, shard count, or commit.
- [ ] No raw SQL values, credentials, connection properties, customer identifiers, or private topology were added.
- [ ] New dependency/license/SBOM effects were reviewed.
- [ ] Detected callback failure, incompleteness, interruption, provider/version mismatch, and attempt-limit paths fail closed; other out-of-scope paths are not presented as automatically rejected.

## AI assistance and owner verification

- AI-assisted scope and tools, or `none`:
- Owner verification performed:
- [ ] I recorded the exact AI-assisted scope, if any (for example research, design, code, tests, documentation, or commands), without presenting AI review as independent human review.
- [ ] I personally traced the changed behavior through every relevant callback, correlation, snapshot, manifest, and verification path and can explain the submitted change without relying on generated prose.
- [ ] I personally ran or inspected the evidence listed above and linked its exact command, revision, environment, result, and limitations; generated output by itself is not treated as proof.
- [ ] Owner-authored decisions and retrospectives describe my actual reasoning and do not contain AI-invented motives, actions, test results, or community feedback.

## Self-review

- [ ] I reviewed the diff line by line and removed unrelated changes.
- [ ] I documented intentional behavior changes and remaining limitations.
