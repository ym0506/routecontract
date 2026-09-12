# 0.1.4 patch candidate

Status: **source preparation; not published**. Current installation instructions still use the
immutable `0.1.3` release. This candidate uses the existing single artifact
`io.github.ym0506.routecontract:routecontract-shardingsphere-5.5`; it is independent of the
unreleased 0.2 core/adapter split.

## Developer problem and scope

A developer inspecting a caught database failure can lose the diagnostic snapshot if another
failure callback overlaps capture closure. The old collector can combine an earlier outcome
with a later failure class and throw an internal validation exception.

This candidate delivers the [atomic attempt-state correction](atomic-attempt-snapshot.md).
The outcome and failure class are published together and frozen from one state. First terminal
callback ownership, diagnostic-only failure captures and the public snapshot schema stay the same.
The old defect was reproduced at the unit boundary; the MySQL suite verifies existing behavior,
not a direct database reproduction of that scheduling race.

Changes since public 0.1.3 also include:

- `tools.jackson.core:jackson-core` 3.1.5 to 3.1.6, already qualified on the main branch;
- the ShardingSphere compatibility/test graph's Jackson 2.x BOM alignment from 2.18.9 to 2.18.10;
- explicit Java 17/21 test launchers, current wrapper/tooling maintenance, regression tests and
  clearer contributor/release instructions. These do not turn old consumer results into evidence
  for new candidate bytes.

The support boundary remains exact ShardingSphere-JDBC 5.5.3, Java 17 or 21, synchronous non-batch
`PreparedStatement` operations. Library bytecode remains Java 17. No new ShardingSphere version,
arbitrary application async, Proxy, batch, topology discovery or production-performance claim is
part of this patch.

## Acceptance before publication

1. Rebase the candidate onto the merged correction and review the full source delta from the
   published 0.1.3 tag. Require clean source and consistent 0.1.4 generated artifact coordinates.
2. Run the current Java/MySQL, Python/packaging, isolated generated-publication consumer and six
   official SBOM checks. Use exact release JDK Temurin 17.0.20.1+1 for release artifacts and verify
   the Java 21 runtime separately. Preserve the existing result-green/contract-red examples.
3. Refresh the pinned official Maven OSV database and run the existing policy against this exact
   candidate without adding vulnerability exceptions or relaxing the policy. Findings require
   investigation and correction, not an inferred waiver.
4. Bind an annotated `v0.1.4` tag, final public main commit and new release-evidence run. Retain
   the established twelve GitHub payload/checksum assets and the separate five Central payloads
   with their observed names, sizes and SHA-256 values. A local build is preparation, not final
   tagged evidence.
5. Review those exact payloads and record what was actually reviewed. Obtain valid publisher
   signatures through an authorized signing path and verify the deterministic 30-file bundle.
   An unsigned candidate or automated inspection is not an independent human review or signature.
6. Follow the existing GitHub draft and Central `USER_MANAGED` validation/publication procedure.
   Verify the submitted candidate bytes before publication; the recorded 0.1.3 download exception
   is not automatically available for this candidate.
7. After publication, perform anonymous byte-for-byte readback and fresh Maven/Gradle MySQL
   consumption of 0.1.4 on Java 17/21. Only then switch current installation instructions and
   report the patch as publicly available.

Exact procedures and historical evidence boundaries remain in [RELEASING.md](../RELEASING.md).
No tag, signed bundle, public deployment, independent adoption or production result is implied
by this preparation record. Version selection and existing author authorization do not fabricate
the still-required artifact, review, signing or publication evidence.
