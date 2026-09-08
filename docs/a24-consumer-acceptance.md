# Staged consumer acceptance across build tools

Status: the existing Gradle A-24 matrix is complete on final staged source
`86a0be5d2e444f3b73925122fa448d9d1a324edd` for Groovy/Kotlin,
Java 17 and exact ShardingSphere-JDBC 5.5.2/5.5.3. All 28 cases passed in one
complete execution and received a final independent retained-evidence audit;
see the [final-candidate result](evidence/a24-gradle-final-86a0be5-2026-09-08.md).
Its eight positive phases executed 24 MySQL JUnit tests; the other 20 cases
were 16 rejections and four disabled-origin controls. All passed, with zero
JUnit failures/errors/skips and no matrix or internal MySQL startup retries.

Maven Java 17/21 is [reported separately](evidence/a24-maven-final-86a0be5-2026-09-08.md).
This Gradle run alone does not establish full cross-tool A-24 acceptance,
Gradle Java 21, public 0.2 availability or external adoption. The authentic
human review of the 14 expected 5.5.2 corpus manifests remains unrecorded
(`humanReview: null`). Installed 0.1.2 and older 4e06694 execution evidence
remain historical and do not substitute for these final staged bytes.

Required profiles are Gradle Groovy/Java 17, Gradle Kotlin/Java 17, Maven/Java 17,
and the bounded Maven/Java 21 profile. Each profile runs separately against exact
ShardingSphere-JDBC 5.5.2 and 5.5.3. The Java 21 profile verifies its actual Maven
runtime, compilation target and executed class version; it does not establish a
Gradle/Java 21 or broader Java support claim.

The inputs are a reviewed nine-payload local staging receipt, its production
source revision, strict dependency verification and the unchanged representative
business fixture and reviewed baselines. Source/composite substitution, unchecked
cache seeds and rebuilding first-party code inside a consumer are disallowed.
Existing local and CI module metadata receipts are not interchangeable.
The receipt SHA-256 must be supplied separately from the receipt file, and all
production inputs must match the declared source revision. The finite Gradle plan
is exactly Groovy/Kotlin × 5.5.2/5.5.3 × seven cases = 28 executions on Java 17 and
the checked-in Gradle 8.14.4 wrapper. There is no extra JDK cross-product.

For every profile/runtime pair, retain these distinct executions:

1. **Online.** Start with an absent dependency/plugin cache. Resolve the reviewed
   core and one adapter, compile, and run the complete representative MySQL
   business/capture/report fixture. Check selected and executing JAR hashes and
   the whole ShardingSphere version closure. Do not run policy negatives in this
   cache before freezing its successful state.
2. **Offline after that prime.** Preserve a complete immutable cache snapshot and
   inventory, then copy it to a disposable offline cache. Launch a new process
   with native offline mode and an independently checked OS network restriction.
   Deny external outbound connections; permit only loopback and the exact local
   Docker Unix socket needed for the local database. Run the same positive
   compile/MySQL/report tasks, without build-cache or test-result reuse. Verify
   graph/artifact identity and that the preserved cache snapshot is unchanged.
   Offline configuration or `help` alone is insufficient.
   Prime first-party artifacts through one controlled HTTP endpoint, close and
   verify its TCP refusal before offline replay, and retain the identical URL.
   A reachable `file:` repository cannot prove frozen-cache-only behavior. Pin
   the same local MySQL/Ryuk image manifest across both executions; the fixed
   fixture must invoke the public no-pull policy for both images. The exact
   selected JDK must pass the compiled kernel-egress/loopback control. Strip
   inherited proxy/JVM/Testcontainers configuration, set trusted IPv4 for all
   Java descendants, isolate HOME/DOCKER_CONFIG, and verify the actual test JVM
   feature/property and compiled classfile version. The boundary covers direct
   build-process egress and this fixed fixture's no-pull behavior, not Docker
   daemon/container networking or unrelated host loopback proxies.
3. **Corrupted checksum.** Use a new empty cache and a controlled invalid checksum
   in copied trust metadata or repository sidecars. Require the build tool's
   actual checksum-verification failure naming the expected payload. A harness
   precheck failure or missing artifact is not this result.
   For Gradle, alter only the core JAR's trust pin, leave its actual reviewed
   bytes unchanged, and enable the native verbose verification report. Bind the
   artifact coordinate, repository name, incorrect expected pin and actual
   reviewed SHA-256 in one native failure section, with the exact successful
   JAR GET and recorded endpoint/command. Generic checksum text plus a core
   filename elsewhere cannot count as proof.
4. **Wrong origin.** Make correct reviewed payload bytes available through an
   unintended repository. Demonstrate the consumer's exclusive-origin policy or
   origin verifier rejects that route. Changing payload bytes alone does not
   establish origin protection. Keep any deliberately disabled-policy control
   separate from the protected result.
   The protected and disabled-policy control use separate consumers and caches.
   Retain finalized HTTP method/path/status logs for both the empty reviewed
   endpoint and the populated unintended endpoint. The protected execution must
   fail for the exact first-party coordinate after the reviewed endpoint is
   queried, with no unintended endpoint request; the control must actually GET
   and resolve the same reviewed JAR bytes from the unintended endpoint.
5. **Wrong runtime anchor.** Start another empty cache and require actual
   whole-group policy rejection before compilation/tests.
6. **Wrong non-anchor.** Start another empty cache, retain the selected adapter and
   all three correct exact-runtime anchors, and inject one wrong-version
   `shardingsphere-infra-common`. Require the whole-group rule itself to reject
   it and retain the correct selected anchors as evidence.
   Retain structured observed unresolved selectors and their actual causal
   messages, the selected adapter, and all three correct anchors for the
   non-anchor case. No compilation or MySQL execution is allowed in negatives.
   The actual non-anchor task must also finish writing its text and JSON
   evidence and emit its unique completion marker. A policy rejection followed
   by a Groovy report-formatting exception is a failed case, not acceptance.

Each negative has its own process, consumer directory, cache, request set and
failure validator. An unrelated download/checksum failure cannot count as a
version-policy rejection. Partial runs never produce a complete A-24 receipt.

The first OS-network experiment on macOS confirmed an unrestricted public
0.1.3 POM HEAD returns 200, the restricted process can reach a controlled
loopback HTTP server and the local Docker Unix socket, and a connection to the
same public endpoint is rejected by the OS with `EPERM`. This is only network
isolation preparation, not an offline consumer result. Other operating systems
must supply and prove their own isolation mechanism; silently falling back to
the build tool's offline flag is prohibited.

Retain raw commands, toolchains, cache inventories, source/fixture hashes,
positive JUnit/report evidence and specific negative reasons privately. Public
notes contain minimized case results and hashes, with the exact tested profile,
runtime, repetition count and remaining limitations. None of these maintainer
executions establishes external adoption or public 0.2 availability.

## Historical preparation and 4e06694 execution evidence

The following unit/configuration/preparation and corrected-matrix observations
belong to the prior 4e06694 work. They were not rerun as part of the final86
matrix, and their executions are not included in the new totals.

`verified - unit`: 32 focused Gradle harness tests passed, including exact native
checksum-section/GET/byte binding, protected/control origin distinctions, exact
runtime cause sets and anchors, immutable-input checks, and finite-plan boundaries.
Both final Groovy and Kotlin build scripts passed Gradle 8.14.4 / Java 17
configuration-only checks with every dependency configuration still unresolved.

The historical source `4e066942f6e244345fe908970b81446f9e08f64e` and separately reviewed
nine-payload receipt SHA-256
`38b2269eca162f121fd3996c56df8b894ae2f43cedeb08fcc627032cf70eaa43` produced an explicit
28-case preparation manifest. Its output is `PREPARED_ONLY`, with zero executed
cases and `completeGradleA24Matrix=false`. The generated consumer sources, metadata,
case identities and input fingerprints are available for review before execution.

The first actual Gradle run passed six Groovy / 5.5.2 cases, including three
real MySQL tests in each online/offline case, then failed at the non-anchor
task's Groovy text formatting. Its complete receipt remains false. A minimal
parenthesized string-expression fix passed a fresh actual non-anchor diagnostic
and the same 32 focused tests. The original failed run and executed source
fingerprints are retained. The offline positive included one Testcontainers
internal MySQL startup retry after a local JDBC EOF; its three tests then passed
under the unchanged network barrier.

`verified - MySQL`, `verified - ShardingSphere-JDBC 5.5.2`, and
`verified - ShardingSphere-JDBC 5.5.3`: the corrected Gradle 8.14.4 / Java 17
matrix completed all 28 planned cases on local macOS. Its eight online/offline
positive cases ran 24 actual JUnit tests with zero failures, errors or skips;
the remaining 20 checksum/origin/control/runtime cases passed their specific
validators. An independent raw audit checked every case, all four frozen prime
caches, all 23 executed source fingerprints and the nine reviewed payloads.
No MySQL startup retry occurred in this corrected complete run.

The complete Gradle summary SHA-256 is
`b9b8afedffaf2312ac9fcdd446f1728ee0d08e47f7b6070de81e0d8d7670b2d7`;
the independent audit SHA-256 is
`5a1dcbba757143581495ac354c5d835a49b1d6328b5e823a8670a5aaf46899dd`.
That historical run closed its Gradle portion only; Maven has its own acceptance gate. These
are local unsigned staged-byte results, not public 0.2 availability or external
adoption. No old `008e125` result substitutes for the new API bytes. A repeat
execution must pass its reviewed `fixture-inputs.json` as
`--expected-input-manifest` and retain the independently supplied receipt hash;
changed inputs require renewed review.

## Final staged-byte execution and reproduction

The final run used consumer checkout
`3ad510a0af972231fbd074607936ee52be3cad1f`, whose 69 production/publication
inputs match staged source `86a0be5d2e444f3b73925122fa448d9d1a324edd`.
The reviewed nine-payload receipt SHA-256 is
`1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e`.
The Groovy build SHA-256 `7f465d3ed2bf656853bf1afe913468e5aaa5c1505e9f8cabf9bc248411dc835f`
is unchanged from the corrected historical Gradle run. Of the 23 runner
fingerprints, only the imported Maven harness changed; the four directly
invoked helper functions, their inventory dependency and test-name constant
retain identical ASTs. Its newly imported Central response-cache helper is
not activated by this Gradle runner and was bound separately before/after
execution. The reviewed expected-input manifest SHA-256 is
`f115fc28b0042e039ad807b3a0ba82c332ab96ec596a6f0919f3f853f0b83b79`.

The independent final audit rehashed all four retained cache snapshots and all
28 case records after the final case, together with the copied and original
inputs, artifacts and raw test/report evidence. The final raw summary SHA-256
is `11c06fb9b79f08b98ffb3422174df9b2d24bfe2c2873f29d41fa3b0bb37ffdf4`; independent audit
SHA-256 is `19031ef87d89eae6f434b91dfe8c3c4726ba7ac559c66cb2aff46963197e553c`.
No source, fixture, golden, original staging file or first-party build was
changed for this run. The historical 4e06694 preparation, failure and successful
run remain retained separately.

The executed command below replaces only private paths with named inputs.
`REVIEWED_INPUT_MANIFEST` is the separately reviewed 23-entry manifest for this
checkout; `REVIEWED_RECEIPT` is the reviewed receipt, not a newly computed
approval. Use an absent evidence directory. Preserve the supplied receipt and
manifest pins; changed bytes require renewed review. The wrapper ZIP is
Gradle 8.14.4 with SHA-256
`f1771298a70f6db5a29daf62378c4e18a17fc33c9ba6b14362e0cdf40610380d`.

```sh
PYTHONDONTWRITEBYTECODE=1 SSL_CERT_FILE=/etc/ssl/cert.pem \
  "$PYTHON" -B scripts/verify-a24-gradle-consumer.py \
  --repository "$REVIEWED_STAGING_REPOSITORY" \
  --staged-receipt "$REVIEWED_RECEIPT" \
  --staged-receipt-sha256 1f4bb21b430a03a44d89e6daddc1fbdede1886250637ef83cecedfd71e350c7e \
  --staged-source-revision 86a0be5d2e444f3b73925122fa448d9d1a324edd \
  --evidence-directory "$NEW_EVIDENCE_DIRECTORY" \
  --java-home "$JAVA17_HOME" \
  --gradle-distribution-zip "$GRADLE_8_14_4_ZIP" \
  --expected-input-manifest "$REVIEWED_INPUT_MANIFEST"
```

The finite plan remains Groovy/Kotlin × 5.5.2/5.5.3 × seven cases on Java 17.
The three unchanged representative MySQL methods in each positive phase are
not the separate 28-test packaged-corpus gate. CLI assertions execute
`ManifestReviewCli.run` in process. Exact wrong-runtime diagnostics exit 0
only after recording and validating their expected policy rejection, with no
compilation or test execution in those cases. Scope remains local unsigned
staged-byte acceptance; artifact signing, release approval, broader JDK/platform
support and external-user adoption are not established here.
