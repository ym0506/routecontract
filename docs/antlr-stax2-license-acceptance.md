# Exact ANTLR and Stax2 SBOM license records

The copied twelve-document inventory after the H2 correction contains sixteen distinct license
records. Two still lack an accepted interpretation: ANTLR runtime 4.10.1 is reported as
`BSD-4-Clause`, and Stax2 API 4.2.2 is reported as `BSD-2-Clause`. No other unmatched license
record was found; the pinned MySQL OCI package retains its existing explicit review boundary.

## ANTLR runtime 4.10.1

The [publisher's exact LICENSE](https://github.com/antlr/antlr4/blob/44d87bc1d130c88aa452894aa5f7e2f710f68253/LICENSE.txt)
specifies BSD 3-Clause. Its runtime POM repeats that license in its header and inherits a parent
whose generic license name is `The BSD License`. The binary has no embedded LICENSE file;
its manifest links to the publisher's license page. The separate JavaScript MIT notice in the
publisher source does not describe files in this Java runtime JAR.

CycloneDX Gradle plugin 3.4.0 resolves the generic name before the URL. Its pinned
cyclonedx-core-java 13.0.0 [mapping](https://github.com/CycloneDX/cyclonedx-core-java/blob/333da9e1f99fe561a77aeabd333ef0e20cf58154/src/main/resources/license-mapping.json)
maps `The BSD License` to BSD-4-Clause. This explains the producer error without treating the
publisher's actual license as BSD-4-Clause.

- Exact coordinate: `org.antlr:antlr4-runtime:4.10.1`.
- JAR SHA-256: `da66be0c98acfb29bc708300d05f1a3269c40f9984a4cb9251cf2ba1898d1334`.
- POM SHA-256: `29ce054c9d2f0c5c80602ac38d110890949c80097de847bf42f57085837118a7`.
- Publisher LICENSE SHA-256: `b1b379fcaf3219593a4c433feb1b35c780bed23fafaae440b1ae2771a9521e3a`.

Normalize only that coordinate/version and JAR hash, and only the observed BSD-4-Clause record
or its canonical BSD-3-Clause replacement. Both JSON and XML must agree. Preserve all scope
properties: the component is non-test in the published 5.5.2 adapter and test-scoped in the
aggregate/MySQL 5.5.2 profiles. BSD-4-Clause gains no identifier recognition or policy allowance;
the corrected BSD-3-Clause identifier is already allowed.

The same inventory also includes ANTLR 4.13.2 for the 5.5.3 graph. Other versions remain
unchanged and cannot use this normalization. Exact 4.10.1 identity contradictions still fail;
coexistence with a separate valid version must not make the finalizer reject the entire graph.

## Stax2 API 4.2.2

The [publisher's exact license](https://github.com/FasterXML/stax2-api/blob/6bd3896d64a0bab3321586edcbc85e2c21c8012d/src/main/resources/META-INF/LICENSE)
and the JAR's `META-INF/LICENSE` bytes are identical and identify BSD 2-Clause. Its POM declares
the same license. The producer's BSD-2-Clause record is accurate and requires no normalization.

- Exact coordinate: `org.codehaus.woodstox:stax2-api:4.2.2`.
- JAR SHA-256: `a61c48d553efad78bc01fffc4ac528bebbae64cbaec170b2a5e39cf61eb51abe`.
- POM SHA-256: `4e902ec556fc6598b41c2952ec1573edc815037e7330ec4922eab619422686e2`.
- Publisher/embedded LICENSE SHA-256: `b3e969d18f690ab8783e4ec77729c9fea85691b8090c550bb3c626dda5e837a7`.

Recognize the SPDX identifier, then add only the exact Stax2 API 4.2.2 `test-runtime` exception.
The component appears only in the aggregate/MySQL 5.5.2 test graphs. The global allowed-license
list remains unchanged, and this exception does not authorize published runtime use.

## Finite acceptance

Add failing acceptance before implementation. Reject normalization of other versions, unknown or changed license
records, a wrong ANTLR JAR hash, contradictory JSON/XML, and Stax2 without proven test scope.
Verify ANTLR scope preservation in both runtime and test profiles. Retain the existing H2,
first-party, dependency, unknown-license and pinned-container guards.

Run the focused finalizer/policy suites and re-finalize the same copied twelve local SBOMs,
then inspect the complete derived inventory. Retain earlier failed outputs. This does not
rebuild Java artifacts or prove CI byte identity, a full exact-source OSV scan, publication or
release approval. The clean-source scan runs after the reviewed fix is integrated.

## Local result on 2026-09-08

Python 3.12.14: the policy suite passed 127 tests; the finalizer suite passed 64 tests with
one existing optional official-CLI check skipped. The initial focused ANTLR tests failed before
the correction; an additional two failing coexistence cases reproduced the actual mixed-version
input before the selector was narrowed. All nine final ANTLR-focused methods pass.

All twelve retained SBOM documents finalize successfully. All six roles pass the license,
JSON/XML and root-graph checks. ANTLR 4.10.1 changes only its license record; ANTLR 4.13.2 and
Stax2 records remain unchanged, including runtime/test scope. All eighteen copied SBOM, POM
and lock inputs retain their recorded hashes.

The complete inventory remains failed at a separate published-dependency check: it expects
the first-party core dependency to have a third-party `type=jar` PURL qualifier, while the
producer correctly emits `project_path`. The failure and the preceding mixed-version failure
are retained. No full inventory, exact-source OSV scan or CI success is claimed by this result.
