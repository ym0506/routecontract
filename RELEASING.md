# Release checklist

This checklist produces reviewable release evidence; it does not publish to a
package repository or create a GitHub Release automatically. Publication must
remain a deliberate maintainer action until repository ownership, signing and
credentials have been verified.

## Prepare

1. Work from a clean revision on `main` and close or document every release
   blocker.
2. Replace `0.1.0-SNAPSHOT` with the intended release version and update the
   changelog, compatibility statement, limitations and evidence results.
3. Reconcile `THIRD_PARTY.md` with `gradle.properties`, the module build files,
   and the generated CycloneDX SBOM.
4. Confirm the checked-in Gradle Wrapper JAR and distribution checksums against
   Gradle's official checksum page.
5. Run on a clean machine with JDK 17 and Docker available:

   ```bash
   ./gradlew --no-daemon --no-build-cache clean check prepareVerifiedSbom \
     :routecontract-shardingsphere-5.5:assemble \
     :routecontract-shardingsphere-5.5:generatePomFileForMavenJavaPublication
   ```

6. Inspect the main, sources and Javadoc JARs; generated POM; direct library
   SBOM; aggregate repository SBOM; `LICENSE`; `NOTICE`; and third-party
   notices. Verify that no fixture credentials, raw SQL parameters or private
   paths are present.
7. Record the source revision, JDK/Gradle/Docker versions, exact command, test
   result, CI URL and SHA-256 checksums. A passing build alone is not evidence
   of transaction commit or a complete ShardingSphere route plan.

## Tag and collect evidence

Create an annotated tag matching the Gradle project version, including the
leading `v` (for example, project version `0.1.0-rc1` uses tag `v0.1.0-rc1`,
and `0.1.0` uses `v0.1.0`). The release installer accepts only these stable or
strict `-rcN` forms and rejects snapshots. The final contest package still
requires the immutable stable `v0.1.0` release. Pushing a matching tag runs the
read-only `Release evidence` workflow. The workflow:

- validates the Wrapper and tag/version match;
- runs unit and real MySQL integration tests without reusing cached task results;
- generates `test-summary.txt` from the resulting JUnit XML and fails unless
  the exact seven expected suites contain 50 passing, non-skipped tests; the
  fixed summary records the Git revision and per-suite counts but deliberately
  omits test names, timings, hostnames, paths, ports, SQL and captured output;
- builds reproducible-order JARs and the generated Maven POM;
- generates direct and aggregate CycloneDX JSON/XML SBOMs and fails unless
  every first-party component declares Apache-2.0, Connector/J includes its
  Universal FOSS Exception and MySQL example BOMs contain the digest-pinned,
  test-only MySQL container component in both formats;
- creates a revision-bound source archive with one `routecontract-VERSION/`
  root; this archive is release evidence and a GitHub Release asset, not a
  separate contest-upload file;
- validates that source archive's bounded and unambiguous ZIP structure, exact
  versioned root, required project/hook sources, every Java path/package pair
  under conventional `src/main/java` and `src/test/java` roots, canonical
  `ym0506` provider namespace and absence of declared
  private/generated or credential-like paths before installing any binary
  artifact;
- stages the exact public Release payload set and creates `SHA256SUMS` over
  those payloads only;
- installs that checksummed set into an explicit empty file Maven repository,
  then verifies a standalone real-MySQL consumer against the installed final
  JAR/POM rather than `publishToMavenLocal` or a Gradle project dependency;
- records runner architecture and the resolved MySQL image ID, architecture
  and repository digests;
- uploads the public payloads and checksum together with workflow-only
  environment, MySQL-image and final-asset-consumer logs as one workflow
  artifact.

Before creating a public tag, verify through the repository API that release
immutability is enabled; an HTTP success alone is insufficient, and the parsed
response must contain `enabled: true`. After the annotated tag's exact revision
has a green release-evidence run, download and inspect that run's artifact.

Create a **draft** GitHub Release with `--verify-tag`. For an `-rcN` tag, mark
that draft as a prerelease. While it is still a draft, attach an explicit list
of exactly these eleven assets: the checksummed source archive,
main/sources/Javadoc JARs, generated POM, direct and aggregate JSON/XML SBOMs,
`test-summary.txt`, and `SHA256SUMS`. Do not use a broad filesystem glob. Before
publication, verify all of the following against the tagged revision and the
release-evidence run:

- the annotated tag peels to the intended full commit and the run uses that
  same `head_sha`;
- the Release is still `draft: true`, has the intended prerelease flag, and
  exposes exactly the eleven expected asset names, each fully uploaded;
- every one of the ten payload hashes matches `SHA256SUMS`, and the separately
  recorded SHA-256 of `SHA256SUMS` itself matches;
- the source archive, SBOMs, test summary, POM/JAR identity, and standalone
  release-asset consumer pass their documented verification gates.

Only after every draft check passes may the draft be published. Immediately
after publication, require the Release API to report `immutable: true`, run
`gh release verify`, and run `gh release verify-asset` successfully for each of
the eleven downloaded assets. If any prepublication or postpublication check
fails, stop and create a new `-rcN` tag after fixing the cause; never replace an
asset or retag an immutable public Release.

The environment record, resolved MySQL image record and standalone-consumer
log remain only in the revision-bound workflow artifact. The test summary is
present in both places; `SHA256SUMS` declares exactly the other public payloads
(not itself) and never the three workflow-only logs. The gate checks the public
checksum set separately, then protects the entire public-plus-private evidence
directory through the Actions artifact ID/digest, byte-identical extraction
and exact flat-file allowlist. The immutable final `v0.1.0` Release must be a
new stable tag/revision/evidence run with `prerelease=false`; never retag or
promote RC assets as if they were the final stable evidence.
The v0.1 packaging gate requires no signature assets because no signing
workflow or key-management policy is implemented. Add signing only in a future
release with an explicit design and verification path. Do not imply SLSA
provenance or reproducible builds unless those properties have been separately
implemented and verified.

## Known supply-chain boundaries

- Maven and Gradle artifacts are resolved over HTTPS, the Wrapper distribution
  is SHA-256 pinned, and checked-in dependency checksums must be reviewed when
  dependencies change. Checksums establish artifact integrity, not publisher
  identity or vulnerability status.
- The MySQL Testcontainers fixture pins the verified multi-architecture digest
  for `mysql:8.4.11`. Release evidence must also record the resolved platform
  image ID and runner architecture; a multi-architecture tag digest alone does
  not make the entire environment byte-for-byte reproducible.
- Dependabot proposes updates; CI and human review still decide whether an
  update preserves compatibility and the project's evidence claims.
- The release installer proves the downloaded source ZIP's checksum, bounded
  structure, required paths, Java packages and provider namespace. It does not
  by itself prove Git-tree identity; the final submission packaging gate
  recreates `git archive` from the final commit and compares tracked paths,
  content and executable permissions before accepting it.
