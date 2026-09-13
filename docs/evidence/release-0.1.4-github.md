# v0.1.4 GitHub release evidence

The immutable [GitHub release](https://github.com/ym0506/routecontract/releases/tag/v0.1.4)
was published on 2026-09-13 at 19:37:21 UTC. Its twelve assets were then downloaded
anonymously and compared byte for byte with the reviewed tagged-workflow outputs.
All twelve comparisons, `gh release verify`, and all twelve `gh release verify-asset`
checks passed. The [readback record](release-0.1.4-github/public-readback.json) records
the observed asset names, sizes, SHA-256 values and URLs.

## Source and build binding

| Record | Identity |
| --- | --- |
| Source commit | `a1eb22087eaf3a49e894d12ba56516efac99343f` |
| Annotated tag object | `829bec53753c349ae40938fb9ff41a1676563969` |
| Source tree | `9f4998a51e1077512c45f7d526f0bc4c0ab36bf4` |
| Tagged workflow | [34681713954, attempt 1](https://github.com/ym0506/routecontract/actions/runs/34681713954) |
| Source ZIP SHA-256 | `848e9e6b85ad8a53ec3742823b12818147c8411ee5ece6077b66970a9e45d4be` |
| Main JAR SHA-256 | `b912725183a982ccddbfd4fa73ebe6a274590a674c0d72d94b0e1883d22b2816` |

The tagged workflow passed the existing 64-test summary gate, real-MySQL final-asset
consumer and supply-chain checks. The six CycloneDX JSON/XML documents, source ZIP,
JARs and publication metadata were checked against their tagged inputs. A pinned
OSV scan of 154 Maven packages reported zero findings at its recorded database
snapshot. That result is time-bound; it is not a guarantee of future vulnerability
status. The separate MySQL test-container license review remains recorded.

## What this establishes

**verified - unit**, **verified - MySQL**, **verified - ShardingSphere-JDBC 5.5.3**
refer to the tests in the linked workflow. Public download comparisons establish
artifact-byte identity; they do not constitute another runtime test or independent
external-user adoption. The source/artifact reviews included automated and agent
inspection and are not described as independent human approval.

The patch preserves diagnostics when failure callbacks overlap capture closure.
The scheduling defect was reproduced at the unit boundary. The MySQL suite
qualifies existing behavior, not a direct database reproduction of that race.
Support remains Java 17/21, Java 17 library bytecode, exact ShardingSphere-JDBC 5.5.3
and synchronous non-batch PreparedStatement operations.

The readback JSON's `centralPublished: false` records the situation when GitHub
was verified. Maven Central publication and public-consumer verification have a
separate [record](release-0.1.4-central.md).
