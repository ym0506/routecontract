# 0.1.3 Central publication record

Status: **published on GitHub and Maven Central**. The immutable
[v0.1.3 GitHub Release](https://github.com/ym0506/routecontract/releases/tag/v0.1.3)
and its twelve assets passed [public readback and release verification](evidence/release-0.1.3-github.md).
The [Central evidence record](evidence/release-0.1.3-central.md) records the signed bundle,
Portal deployment, public readback and consumer results, including the prepublication
Portal candidate-byte download exception. It does not claim every prepublication gate passed.
The [publication tracking issue](https://github.com/ym0506/routecontract/issues/36) retains the sequence.
This release uses the existing single
`io.github.ym0506.routecontract:routecontract-shardingsphere-5.5` artifact and
exact ShardingSphere-JDBC 5.5.3 support. Its Markdown/JSON report API is included
in the GitHub release and the same library is available through Central.
The core split and 5.5.2 adapter remain separate unreleased 0.2 work.

The immutable v0.1.2 release, its installer pins and contest evidence remain
historical release evidence. Existing local-install and assisted-pilot instructions
remain pinned to v0.1.2; the [released report example](ci-review-report.md) uses v0.1.3.
Use the [ordinary Central dependency](../README.md#install-013) for current installation.
This release does not activate a new contest recruitment window.

Original acceptance requirements, retained for audit; completion evidence and exceptions
are recorded separately above:

1. Existing Java/MySQL, Python, source-archive, public-asset consumer and official
   SBOM checks pass for the final clean revision using the documented exact JDK.
2. Refresh the existing pinned OSV input and rerun its policy without adding
   vulnerability exceptions or weakening the policy.
3. The annotated tag, public main, release workflow revision and recorded
   candidate files agree. Retain the exact main/sources/Javadoc JARs, POM and
   Gradle Module Metadata as a separate Actions artifact. Its generated receipt
   records observed bytes; it is not an approval or a signature.
4. Independently review those five payloads, bind the reviewed manifest to the
   tag/run, sign with the protected publisher primary key using SHA-384, and
   verify the existing schema-1 deterministic 30-file Central upload bundle.
   Verify the expected public key retrieved from a supported keyserver.
5. Implement and review the single-coordinate public readback and fresh Gradle
   and Maven MySQL consumer commands before uploading. Their successful live
   execution is required after publication, not before the version exists.
6. Use the documented deliberate Portal upload/validation/publish procedure.
   Retain exact deployment identity and reconcile ambiguous responses without
   repeating publication blindly.
7. After publication, compare every public file with the signed bundle and run
   both fresh consumers against the reviewed first-party hashes. Only after
   those checks pass may the README advertise Central availability.

The existing twelve GitHub Release assets keep their established contract.
The separate Central candidate artifact adds metadata evidence without changing
that asset set or granting a signing/upload operation to CI. No release claim,
independent adoption or production outcome follows from preparing these files.
