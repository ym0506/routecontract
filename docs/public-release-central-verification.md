# Public Central verification for the single-artifact 0.1 release

This post-publication check supports only stable `0.1.x` releases from `0.1.3`
onwards, using `io.github.ym0506.routecontract:routecontract-shardingsphere-5.5`.
It does not accept the separate 0.2 core/adapters. Preparing or testing these
commands does not establish publication. Public installation of the candidate
remains **unverified** until the real checks complete.

Before networking, `scripts/verify-public-release-central-readback.py` invokes
the existing schema-1 `prepare-central-upload-bundle.py` verifier against the
signed staging repository, reviewed five-payload manifest, exact bundle receipt
and public-key-only GnuPG home. It snapshots verified bundle and receipt bytes,
rejecting changes after verification. A receipt's `VERIFIED` string alone is
insufficient.

The command compares all 30 uploaded files: five payloads, their five detached
signatures and twenty payload checksum sidecars. URLs come only from this
verified inventory under `https://repo.maven.apache.org/maven2/`. Requests use
no authentication, cookies, configured proxy, redirects or repository fallback.
TLS verification stays enabled. Each HTTP 200 identity response must match the
reviewed file byte for byte. Missing, changed, truncated, oversized or encoded
content, redirects and transport errors stop the check. A 600-second monotonic
budget is checked before connections and between single body reads, with socket
waits of at most 20 seconds. This checked budget is not a hard process deadline
covering operating-system DNS calls or a socket wait already in progress.

A new private evidence directory retains minimized partial results. Only after
all 30 files match does the command write a three-payload `consumer-receipt.json`
for the main JAR, POM and Gradle Module Metadata. The shared
`scripts/public_release_artifacts.py` loader accepts exactly those three files,
rejecting unsupported versions, ambiguous JSON, substituted paths, duplicate or
missing payloads, invalid hashes and symlink leaves. This checks receipt shape
and expected bytes; it is not independent publisher authentication.

Invoke the command after publication with canonical absolute input paths:

```bash
python scripts/verify-public-release-central-readback.py \
  --repository /absolute/path/to/signed-staging \
  --bundle /absolute/path/to/routecontract-shardingsphere-5.5-0.1.3-central-upload.zip \
  --receipt /absolute/path/to/routecontract-shardingsphere-5.5-0.1.3-central-upload-receipt.json \
  --reviewed-payload-manifest /absolute/path/to/reviewed-payloads.json \
  --public-gpg-home /absolute/path/to/public-key-only-gnupg \
  --expected-primary-fingerprint REVIEWED_40_CHARACTER_UPPERCASE_FINGERPRINT \
  --evidence-directory /absolute/path/to/new-public-readback-evidence
```

Readback alone keeps `availabilityClaim` and `consumerExecutionVerified` false.
Fresh independent public Gradle and Maven consumers must subsequently use the
reviewed receipt and exercise the supported exact ShardingSphere-JDBC 5.5.3
real-MySQL boundary before announcing availability. They must retain business
assertions and confirm the loaded JAR matches the reviewed release. Local
staging checks remain separate evidence.

The signed-fixture tests use a disposable test key and synthetic transport to
exercise the real local verifier plus readback success/failure paths. These are
**verified - unit** evidence only. They establish neither public Central
availability nor public MySQL consumption.

Run the focused checks with:

```bash
python -m unittest \
  scripts.tests.test_public_release_artifacts \
  scripts.tests.test_verify_public_release_central_readback
```

Local macOS runs on 2026-09-07 passed all 21 tests with Python 3.12.14 and
3.13.0, with no skips. They include genuine schema-1 signature verification,
signature corruption, bundle/receipt changes after verification, rejection
before networking on invalid local inputs, ambiguous duplicate HTTP body
headers, partial failures and the checked read budget. These runs used
synthetic artifact contents and transport; they do not prove release JAR
behavior, public installation or external user adoption.
