# A-09 manual mixed-anchor matrix: reviewed 86a0be5 candidate

**All 14 cases passed** against independently reviewed, unsigned local RouteContract
0.2.0 staging from source `86a0be5d2e444f3b73925122fa448d9d1a324edd`.
The frozen runner revision was `3ad510a0af972231fbd074607936ee52be3cad1f`;
all launches used OpenJDK **17.0.15** and Gradle **8.14.4**.
The [minimized receipt](mixed-anchor-final-candidate-2026-09-08.json) binds every case to exact artifact and raw-evidence hashes.

| Group | Result | Observation |
| --- | --- | --- |
| Six nominal mixed tuples, both anchor orders | 12/12 | Direct top-level `RC_MIXED_SHARDINGSPHERE_RUNTIME`, real adapter guard, zero action entries, no capture linkage failure |
| Clean exact 5.5.2 and 5.5.3 controls | 2/2 | One action entry, INCOMPLETE schema-2 snapshot, zero attempts, `RC_NO_START_CALLBACK_OBSERVED`, exact identity with boolean `supported: true` |

The matrix physically assembles the official executor, SPI and database-owner JARs.
The adapter follows the database-owner ABI. Both complete anchor sequences are tested
for every mixed tuple; every case runs in a distinct fresh JVM. The public capture is
the first product call. Anchor reflection runs afterward to retain the actual loaded
origin and version, or the precise missing/unlinkable class observation.

All six nominal tuples remain represented. Official 5.5.2 SPI lacks `ShardingSphereSPI`,
which the 5.5.3 executor requires. Six cells therefore retain eight expected later
anchor-load failures. Those observations do not become capture linkage errors:
the passive guard rejects the mixed JAR versions first. No fabricated or relabeled
ShardingSphere class bytes are used.

**The original 4e06694 execution remains FAILED (6/14).** Six cells originally
violated the mixed diagnostic contract. Two otherwise correct clean controls were
rejected by a harness schema omission of Jackson's derived `supported: true` field.
The production guard now checks passive JAR resources before linking the hook ABI,
and the strict classifier requires that boolean alongside every identity component.
This is a new reviewed-candidate run; the original result is not rewritten.

The independent audit reconstructed all 14 commands and observations without using
the runner's PASS labels. It found zero discrepancies and verified **347 JAR paths,
2 compiled probe classes, 69 production/publication source files, 19 fixtures and
90 staged files**, including the reviewed receipt payloads. The six anchor hashes
match the earlier independent comparison with official Maven Central bytes. Both
runtime graphs used initially absent dependency caches and strict checksum verification.
No first-party production artifact was rebuilt during this consumer run.

Retained evidence digests:

- New raw summary: `9b1647b73559461c5420eb9e53fae5e5f011b63819eefa5469e028b1e47b080b`
- New reviewed staging receipt: `1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e`
- Independent raw/input audit: `1d4c14142258b64279e417fb31cce01e9f0c6b323d2f0492720ed07603a5a7b1`
- Original failed raw summary: `8fa55131e2aba991cbfa37af0e02235cd1a189ec652b962f65c025c55ff5d25e`

This verifies the finite **manual 14-case matrix**. Whole-group resolver rejection
remains separate A-24 evidence; this receipt keeps `fullA09Acceptance: false`.
The clean controls run no SQL. No MySQL workload, arbitrary non-anchor compatibility,
public 0.2 release, independent rebuild or user adoption is established here.
The three uncached manifest reads per verification/capture have an unmeasured cost.

Raw paths, process IDs, full messages and logs remain local. These public files and
the acceptance-status copy were prepared after execution and the independent audit;
the frozen runner's execution-time fingerprints remain unchanged.
