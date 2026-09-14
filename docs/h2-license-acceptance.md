# Exact H2 2.2.224 test-runtime license metadata

The coordinated CI preparation for PR head `30267337aa97f5f057b731628afbff575fffe66d`
stopped during supply-chain inventory, after all twelve CycloneDX documents passed official
schema validation. The reported license identifier was `MPL-2.0`. The already-generated local
aggregate's matching component is `com.h2database:h2:2.2.224`, used only by the exact 5.5.2
MySQL test graph. CI did not upload its SBOM after that failure; the local component observation
is corroborating evidence, not a downloaded CI SBOM.

The publisher's [version 2.2.224 license](https://github.com/h2database/h2database/blob/19b770ec010a621989a980bf166a10ac10072a61/LICENSE.txt)
states that H2 is available under either MPL 2.0 or EPL 1.0. The pinned POM lists both licenses;
the CycloneDX producer emits separate MPL and legacy-named EPL records. Preserve the publisher's
choice as the exact SPDX expression `MPL-2.0 OR EPL-1.0` in both finalized JSON and XML.

Reviewed input SHA-256 values:

- H2 2.2.224 JAR: `b9d8f19358ada82a4f6eb5b174c6cfe320a375b5a9cb5a4fe456d623e6e55497`.
- H2 2.2.224 POM: `0d4503a01a4c7a62f91ae1a6271339cf806f2a462defe0beff5effd5a611e398`.
- Publisher LICENSE.txt at commit `19b770ec010a621989a980bf166a10ac10072a61`:
  `827b84bb8f84dbd60d1a8955cefab142d65cc17d267e32996db400138a1e0fcf`.

Acceptance is limited to that exact coordinate/version and existing test-runtime scope:

1. The finalizer emits the same dual-license expression for the reviewed H2 JSON/XML pair.
2. The policy recognizes `MPL-2.0` as an SPDX identifier and approves only the exact H2
   expression through a `test-runtime` exception. The global allowed-license list is unchanged.
3. Missing or production scope, another H2 version, unknown SPDX identifiers, unexpected
   license expressions and contradictory JSON/XML metadata remain rejected.
4. Existing license, dependency, first-party Apache-2.0 and pinned-container guards remain active.

Add failing acceptance before implementation. Run the focused finalizer and policy tests;
retain the failing and passing results. Any check against existing generated SBOMs must record
their source/toolchain binding and must not be represented as a new Java build or a successful
CI preparation. The complete pinned scan still requires its original clean-source preconditions.
No runtime dependency, published artifact, signing guard or publication hold changes here.

## Bounded verification on 2026-09-08

The new H2 acceptance failed before implementation. After the fix, all seven finalizer H2
methods and all seven policy H2 methods passed. The complete finalizer suite reported 55 passes
and one existing optional official-CLI skip; the policy suite reported 120 passes. These are
`verified - unit` observations, not database-execution evidence.

Re-finalization of twelve copied local Gradle SBOM documents passed without a Java rebuild.
The subsequent inventory remained **FAILED** at the separate ANTLR runtime 4.10.1
`BSD-4-Clause` identifier. That component also appears in the published exact-5.5.2 adapter
profile; this H2 test-runtime exception does not authorize it. No complete inventory, license
policy scan or CI preparation pass is claimed from this partial check.

The pending edits cannot satisfy the scan runner's clean exact-revision precondition. The full
source-bound scan therefore remains unverified until the reviewed fix is integrated and CI runs
it normally. Existing raw inputs, the original CI failure and the later inventory failure are
retained separately.
