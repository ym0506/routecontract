# Public Central verification contract

This is the maintainer's post-publication check for stable 0.2.x coordinates.
Preparing or testing the verifier does not establish that a version is published.
The current candidate's public installation remains **unverified**.

Before networking, the readback command must run the existing local bundle
verifier against the signed staging repository, reviewed manifest, exact bundle
receipt and public-key-only GnuPG home. It snapshots the verified bundle bytes
and receipt, rejecting changes after verification. A receipt's `VERIFIED` string
alone is insufficient.

The command requests all 90 uploaded files, including the fifteen payloads,
their detached signatures and four payload checksum sidecars. URLs are derived
only from this verified inventory under
`https://repo.maven.apache.org/maven2/`. Requests have no authentication,
cookies, configured proxy, redirect following or repository fallback. TLS
verification stays enabled. Each response must be HTTP 200 with an identity
body matching the reviewed file byte for byte. A size mismatch, extra byte,
missing file, redirect, timeout or transport error stops the check.
Each socket wait is limited to 20 seconds. A 600-second monotonic budget is
checked before requests and between single response-body reads; this is not
a separate process-level watchdog for DNS resolution or response headers.

A fresh private evidence directory retains a minimized result on partial
failure. A nine-payload `consumer-receipt.json` is produced only when all 90
files match; it binds the main JAR, POM and Gradle Module Metadata for core and
both adapters. The shared loader rejects coordinates outside stable 0.2.x,
ambiguous JSON, unexpected paths, duplicate/missing payloads and invalid hashes.
This receipt verifies expected-byte shape; it is not independent publisher
provenance.

Public readback alone leaves `availabilityClaim` false. Both independent public
Gradle and Maven consumers must subsequently pass for exact ShardingSphere
5.5.2 and 5.5.3, using fresh caches and the reviewed nine-payload receipt. They
must check transitive core, exact whole-group dependencies, loaded JAR hashes,
real-MySQL MATCH and policy rejection, and incompatible adapter/runtime graphs.
The existing local staging lanes remain distinct evidence.

Unit tests may supply a synthetic HTTP transport to exercise successful and
failed responses. That is **verified - unit** evidence only, and must never be
reported as public Central availability or a successful public MySQL run.

## Maintainer commands

After Portal reports the reviewed version published, supply the same signed
staging repository, reviewed manifest, public-only keyring and bundle receipt
used for local upload verification. Use an absent evidence directory outside
the checkout; the receipt keeps hashes and coordinate paths without credentials.

```bash
python3 -I scripts/verify-public-central-readback.py \
  --repository /absolute/path/to/signed-staging/repository \
  --bundle /absolute/path/to/bundle/routecontract-VERSION-central-upload.zip \
  --receipt /absolute/path/to/bundle/routecontract-VERSION-central-upload-receipt.json \
  --reviewed-payload-manifest /absolute/path/to/reviewed-payloads.json \
  --public-gpg-home /absolute/path/to/public-only-gnupg-home \
  --expected-primary-fingerprint REPLACE_WITH_40_UPPERCASE_HEX \
  --evidence-directory /absolute/path/to/new-public-readback

python3 -I scripts/verify-public-gradle-artifact-consumer.py \
  --receipt /absolute/path/to/new-public-readback/consumer-receipt.json \
  --evidence-directory /absolute/path/to/new-public-gradle

python3 -I scripts/verify-public-maven-artifact-consumer.py \
  --receipt /absolute/path/to/new-public-readback/consumer-receipt.json \
  --evidence-directory /absolute/path/to/new-public-maven \
  --java-home /absolute/path/to/jdk17
```

Run the consumers only after readback exits zero. Set `JAVA_HOME` to Java 17
for Gradle; Maven requires 3.9.14. Docker and public dependency downloads are
required for both. Read the separate [Gradle](public-gradle-consumer.md) and
[Maven](public-maven-consumer.md) contracts for graph, runtime and transport
limits. A failure requires inspection and a fresh evidence directory for a
later attempt; it never authorizes overwriting a published coordinate.

## Preparatory evidence

The new receipt/readback checks passed 17 tests on local Python 3.13.0, including
the existing bundle verifier's real GPG-signed synthetic release fixture.
Transport responses in the successful readback tests were synthetic. Review
found and fixed a filling body-read deadline gap and normalization of Python's
oversized JSON integer error. The tests cover partial 404 evidence, wrong bytes,
truncation, excess bytes, response encoding, redirects, proxy isolation, checked
body deadlines and ambiguous receipt inputs. No public readback success is
claimed. Public consumer preparation and the actual unpublished-candidate
failures are recorded in the separate consumer evidence notes.

The integrated Python 3.12.14 helper run discovered 637 tests: 634 passed and
three optional checks were skipped, with no failures or errors. Two subsequent
checkout-containment tests were added with the Gradle guard fix; all sixteen
affected Gradle wrapper tests then passed on both Python 3.12.14 and 3.13.0.
This is not a claim that a single 639-test run was performed.

The updated shared Gradle fixture also passed its ordinary local staging entry
point on both runtimes (six MySQL tests and ten graph rejection cases). A
separate disposable-copy experiment exercised the **public-mode task logic**
while substituting only its repository block with exclusive local first-party
staging plus Central for third-party dependencies. Both fresh-cache lanes
passed six MySQL tests and ten rejection cases, including the new non-anchor
case retaining all three correct anchors. Java, settings, locks, wrappers,
verification metadata and task assertions were unchanged. This is local-staged
simulation evidence, not an execution of the fixed public endpoint; its result
explicitly leaves public consumption and availability false.
