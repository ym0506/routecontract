# Maven OSV database refresh — 2026-09-07

Scope: refresh only the official Maven database snapshot used by the existing release policy.
Scanner executable/version pins, dependencies, policy and zero-exception configuration stay fixed.

Acceptance: query official object metadata, download its immutable generation URL, compare the
response generation, byte count and official object checksums, calculate SHA-256, verify ZIP
integrity, and validate the resulting lock with the repository's existing validator. Retain raw
metadata, response headers and the verified database outside the repository.

The final clean-candidate OSV scan is pending. A verified database download is not a scan result
and does not establish zero findings for version 0.1.3.

## Observed download

The [official OSV data documentation](https://google.github.io/osv.dev/data/#data-dumps) identifies
the OSV-maintained `osv-vulnerabilities` bucket and per-ecosystem `all.zip` exports. The
[official Maven object metadata](https://storage.googleapis.com/storage/v1/b/osv-vulnerabilities/o/Maven%2Fall.zip)
returned the following latest generation when queried on 2026-09-07 at 11:07 UTC:

| Field | Verified value |
| --- | --- |
| Generation | `1788523358826365` |
| Object updated | `2026-09-04T12:02:38.956Z` |
| Bytes | `10285259` |
| SHA-256 | `bc2546e64b47af11125e1c35a07ef66afa28716de2cf48f28bf50aa66a0fcf7d` |
| Official object MD5 (base64) | `oKaYRDL1zKAOVVJTvYv+Bg==` |
| Official object CRC32C (base64) | `sZM45Q==` |
| ZIP entries | 7065; archive CRC check passed |

The generation-pinned HTTPS download returned HTTP 200 at the same URL, with matching
`x-goog-generation`. Downloaded size, MD5 and CRC32C matched official metadata. SHA-256 was
calculated from the verified bytes; OSV did not supply a separate SHA-256 attestation.

```sh
curl --fail --location --retry 3 --silent --show-error --max-time 120 --proto '=https' --proto-redir '=https' --output all.zip -- 'https://osv-vulnerabilities.storage.googleapis.com/Maven/all.zip?generation=1788523358826365'
shasum -a 256 all.zip
wc -c < all.zip
```

Raw metadata, response headers, download result and `verified-download.json` are retained at
`/private/tmp/routecontract-osv-refresh-20260907/`. The reusable verified cache file is:

`/private/tmp/routecontract-osv-refresh-20260907/database-bc2546e64b47af11125e1c35a07ef66afa28716de2cf48f28bf50aa66a0fcf7d/osv-scalibr/Maven/all.zip`

The release runner will recheck size and SHA-256 before using any cache copy. Its expected local
cache prefix is `build/security-tools/final-scan/` followed by the same `database-<sha256>` path.

The existing lock validator and its timestamp/generation rejection regression passed. Scanner
2.5.0, its executable hashes, SCALIBR 0.4.5, dependency selection and zero-exception policy are
unchanged. New database findings remain pending the final clean-candidate scan; no raw OSV scan
was generated or staged by this refresh.
