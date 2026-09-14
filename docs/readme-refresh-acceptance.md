# README refresh acceptance

The GitHub landing page should let a first-time Java developer understand the problem, check fit and find a published installation without reading maintainer release machinery. README.md is English; README.ko.md provides the Korean landing page.

- Show public v0.1.4 Central coordinates, test scope, Java 17 or 21 and exact ShardingSphere-JDBC 5.5.3 next to installation. Describe synchronous non-batch PreparedStatement capture and retain the business assertion.
- Lead with a concise product explanation, restrained original header, a small usage example and the observed 1-to-2 MySQL example. Visuals must use the reviewed fixture counts and RCM201/RCM202; they are illustrations, not new evidence.
- Keep release 0.1.4, historical v0.1.2 demonstrations and unreleased 0.2 work distinct. No production-readiness, benchmark, adopter or broad-version claims.
- Preserve detailed former README content in reference-guide.md and reference-guide.ko.md, including exact immutable v0.1.2 commands and their validation. Do not change release assets or submission images.
- In both detailed guides, the initial navigation must lead to the current public 0.1.4 example and optional Java assertions. Put the historical 0.1.2 demonstration and integration commands behind an explicitly dated/versioned disclosure, retaining their anchors and exact shell blocks for old links.
- The detailed support section must agree with the current Java 17/21 release support. Distinguish historical dependency/classifier evidence from current consumer installation. Historical videos and release machinery are not the recommended first-use path.
- Preserve published install-013 and quick-start anchors; README.en.md retains useful compatibility anchors. Internal current-install links point to the English landing page.
- Verify local links/anchors, Markdown rendering in light/dark and narrow layouts, asset dimensions/size, published API snippet compilation, and affected existing documentation contract tests. Runtime code is unchanged, so a new database experiment is not required for this documentation change; the linked published MySQL evidence remains the source of claims.

References: official [Testcontainers Java](https://github.com/testcontainers/testcontainers-java/blob/main/README.md), [ArchUnit](https://github.com/TNG/ArchUnit/blob/main/README.md) and [HikariCP](https://github.com/brettwooldridge/HikariCP/blob/dev/README.md) READMEs. Adapt information hierarchy only; do not copy their prose, branding or unsupported claims.

## Public documentation review — 2026-09-14

- The first screen states the user problem and exact released fit; the first code example shows the existing business assertion together with the execution assertion.
- Keep one English landing page and an equivalent Korean page. Explain Korean concepts in Korean; preserve public API identifiers, commands and historical anchors.
- The README links to a short task-based documentation index rather than making every reader choose among historical evidence records. Include a path for inspecting design decisions and their code/tests.
- Historical application experiments retain their original 0.1.3/JDK/database conditions. Current installation links and support statements point to 0.1.4 and Java 17/21. Never upgrade historical evidence by editing its version label.
- Explain count changes and unchanged-count destination changes. State that an observed difference requires interpretation; it does not establish production latency, a transaction commit or an upstream application's defect.
- Keep support, data handling and independent-use status visible. No hiring, popularity, enterprise adoption or production-readiness claim is inferred from presentation quality.
- Validation: existing documentation contract tests, both Python test roots where affected, local targets/anchors, unchanged runnable code blocks and rendered light/dark/narrow views. No new runtime claim or database rerun is required for a prose-only change.
