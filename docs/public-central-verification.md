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
