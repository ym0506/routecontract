# Governance

RouteContract currently has one public maintainer account. This describes the repository state,
not the participant's student status or the contest-team composition. Decisions are made in public
issues and focused pull requests; local or AI review is not presented as independent community
approval.

## Decision process

1. Start non-trivial behavior with a reproducible issue and acceptance boundary.
2. Discuss compatibility, privacy, failure semantics, and prior art before widening scope.
3. Require unit evidence and real MySQL/ShardingSphere evidence for SPI-path changes.
4. Keep an approved manifest change separate and human-reviewed; tooling never self-approves it.
5. Record rejected alternatives and limitations in the specification or pull request.

The maintainer may merge after CI and self-review while the public history has one maintainer
account. As the community grows, maintainership will be based on sustained review-quality
contributions rather than commit count. Security disclosures follow [SECURITY.md](SECURITY.md).
