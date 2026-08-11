# Governance

RouteContract is currently maintained by one student contributor. Decisions are made in public
issues and focused pull requests; local or AI review is not
presented as independent community approval.

## Decision process

1. Start non-trivial behavior with a reproducible issue and acceptance boundary.
2. Discuss compatibility, privacy, failure semantics, and prior art before widening scope.
3. Require unit evidence and real MySQL/ShardingSphere evidence for SPI-path changes.
4. Keep an approved manifest change separate and human-reviewed; tooling never self-approves it.
5. Record rejected alternatives and limitations in the specification or pull request.

The maintainer may merge after CI and self-review while the project has one contributor. As the
community grows, maintainership will be based on sustained review-quality contributions rather
than commit count. Security disclosures follow [SECURITY.md](SECURITY.md).
