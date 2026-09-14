package io.github.ym0506.routecontract.manifest;

import tools.jackson.core.JsonEncoding;
import tools.jackson.core.JsonGenerator;
import tools.jackson.core.ObjectWriteContext;
import tools.jackson.core.json.JsonFactory;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/** Deterministic, minimized CI presentation of the existing manifest verifier's decision. */
public final class ManifestReviewReport {
    private static final int MAX_DISPLAYED_FINDINGS = 100;
    private static final String BOUNDARY = "ShardingSphere SQLExecutionHook-reported physical JDBC execution attempts; "
            + "not a complete route plan, transaction commit, business success or performance measurement.";
    private final ObservedExecutionManifest approved;
    private final ObservedExecutionManifest candidate;
    private final ManifestVerificationResult verification;
    private final String approvedDigest;
    private final String candidateDigest;

    private ManifestReviewReport(final ObservedExecutionManifest approved,
            final ObservedExecutionManifest candidate) {
        this.verification = new ManifestVerifier().verify(approved, candidate);
        this.approved = approved;
        this.candidate = candidate;
        this.approvedDigest = digest(approved);
        this.candidateDigest = digest(candidate);
    }

    /**
     * Compares validated manifests without changing either input or approving any baseline.
     * @param approved caller-selected baseline whose approval is established outside this API
     * @param candidate candidate evidence
     * @return a report backed by the single authoritative verifier
     */
    public static ManifestReviewReport compare(final ObservedExecutionManifest approved,
            final ObservedExecutionManifest candidate) {
        return new ManifestReviewReport(approved, candidate);
    }

    /** @return the original verifier result, with its precedence and severity intact */
    public ManifestVerificationResult verification() {
        return verification;
    }

    /** @return zero only for MATCH, one for every other valid verification result */
    public int strictExitCode() {
        return verification.matched() ? 0 : 1;
    }

    /** @return SHA-256 of the canonical baseline encoding; not proof of approval or origin */
    public String approvedCanonicalSha256() {
        return approvedDigest;
    }

    /** @return SHA-256 of the canonical candidate encoding; not the original input file hash */
    public String candidateCanonicalSha256() {
        return candidateDigest;
    }

    /** @return deterministic Markdown using only fixed text, enumerations, counts and digests */
    public String toMarkdown() {
        StringBuilder output = new StringBuilder("# RouteContract review\n\n");
        output.append("**").append(verification.status()).append("** · Strict check exit: ")
                .append(strictExitCode()).append("\n\n")
                .append("| Observation | Baseline | Candidate | Baseline limit |\n")
                .append("| --- | ---: | ---: | ---: |\n");
        row(output, "Physical JDBC execution attempts", approved.counts().observedPhysicalAttemptCount(),
                candidate.counts().observedPhysicalAttemptCount(), approved.policy().maxObservedPhysicalAttempts());
        row(output, "Distinct observed data-source aliases", approved.counts().distinctObservedDataSourceNameCount(),
                candidate.counts().distinctObservedDataSourceNameCount(), approved.policy().maxDistinctObservedDataSourceNames());
        row(output, "Callback failures", approved.counts().callbackFailureCount(), candidate.counts().callbackFailureCount(), 0);
        row(output, "Unknown outcomes", approved.counts().unknownOutcomeCount(), candidate.counts().unknownOutcomeCount(), 0);
        output.append("\nBaseline capture: ").append(approved.captureStatus())
                .append(". Candidate capture: ").append(candidate.captureStatus())
                .append(". Baseline requires exact signatures: ")
                .append(approved.policy().requireExactExecutionSignatures()).append(".\n\n")
                .append("## Findings and next steps\n\n");
        for (ManifestDiff diff : verification.diffs().stream().limit(MAX_DISPLAYED_FINDINGS).toList()) {
            output.append("- **").append(diff.code().stableCode()).append(" · ")
                    .append(diff.severity()).append(" · ").append(diff.code()).append("** — ")
                    .append(guidance(diff.code())).append('\n');
        }
        output.append("\nFindings: ").append(verification.diffs().size())
                .append(" total; ").append(omittedFindingCount()).append(" omitted from this bounded report.\n")
                .append("\nFindings show the verifier's highest-precedence failing level; later checks may not have run.\n\n")
                .append("## Evidence identity\n\n")
                .append("- Baseline canonical SHA-256: `").append(approvedDigest).append("`\n")
                .append("- Candidate canonical SHA-256: `").append(candidateDigest).append("`\n\n")
                .append("Canonical digests identify manifest content, not original file bytes, freshness or human approval. ")
                .append("Operation IDs, aliases, type names and free-form diff details are omitted; inspect the minimized manifests locally.\n\n")
                .append(BOUNDARY).append(" Keep the business-result assertion and review intentional baseline changes.\n");
        return output.toString();
    }

    /** @return deterministic schema-versioned JSON with the same status, counts and guidance */
    public String toJson() {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (JsonGenerator generator = new JsonFactory().createGenerator(
                ObjectWriteContext.empty(), output, JsonEncoding.UTF8)) {
            generator.writeStartObject();
            generator.writeNumberProperty("reportSchemaVersion", 1);
            generator.writeStringProperty("status", verification.status().name());
            generator.writeBooleanProperty("matched", verification.matched());
            generator.writeBooleanProperty("passesBlockingChecks", verification.passesBlockingChecks());
            generator.writeNumberProperty("strictExitCode", strictExitCode());
            generator.writeNumberProperty("findingCount", verification.diffs().size());
            generator.writeNumberProperty("omittedFindingCount", omittedFindingCount());
            generator.writeStringProperty("approvedCanonicalSha256", approvedDigest);
            generator.writeStringProperty("candidateCanonicalSha256", candidateDigest);
            generator.writeName("baselinePolicy");
            generator.writeStartObject();
            generator.writeNumberProperty("maxObservedPhysicalAttempts", approved.policy().maxObservedPhysicalAttempts());
            generator.writeNumberProperty("maxDistinctObservedDataSourceNames", approved.policy().maxDistinctObservedDataSourceNames());
            generator.writeBooleanProperty("requireNoCallbackFailures", approved.policy().requireNoCallbackFailures());
            generator.writeBooleanProperty("requireExactExecutionSignatures", approved.policy().requireExactExecutionSignatures());
            generator.writeEndObject();
            writeObservation(generator, "baseline", approved);
            writeObservation(generator, "candidate", candidate);
            generator.writeName("findings");
            generator.writeStartArray();
            for (ManifestDiff diff : verification.diffs().stream().limit(MAX_DISPLAYED_FINDINGS).toList()) {
                generator.writeStartObject();
                generator.writeStringProperty("code", diff.code().stableCode());
                generator.writeStringProperty("kind", diff.code().name());
                generator.writeStringProperty("severity", diff.severity().name());
                generator.writeStringProperty("nextStep", guidance(diff.code()));
                generator.writeEndObject();
            }
            generator.writeEndArray();
            generator.writeStringProperty("findingScope", "highest-precedence-level");
            generator.writeStringProperty("digestScope", "canonical-manifest-content-not-approval-or-origin");
            generator.writeStringProperty("evidenceBoundary", BOUNDARY);
            generator.writeEndObject();
        }
        return output.toString(StandardCharsets.UTF_8) + "\n";
    }

    private int omittedFindingCount() {
        return Math.max(0, verification.diffs().size() - MAX_DISPLAYED_FINDINGS);
    }

    private static void writeObservation(final JsonGenerator generator, final String name,
            final ObservedExecutionManifest manifest) {
        generator.writeName(name);
        generator.writeStartObject();
        generator.writeNumberProperty("manifestSchemaVersion", manifest.schemaVersion());
        generator.writeStringProperty("captureStatus", manifest.captureStatus().name());
        generator.writeNumberProperty("observedPhysicalAttemptCount", manifest.counts().observedPhysicalAttemptCount());
        generator.writeNumberProperty("distinctObservedDataSourceNameCount", manifest.counts().distinctObservedDataSourceNameCount());
        generator.writeNumberProperty("callbackReturnedCount", manifest.counts().callbackReturnedCount());
        generator.writeNumberProperty("callbackFailureCount", manifest.counts().callbackFailureCount());
        generator.writeNumberProperty("unknownOutcomeCount", manifest.counts().unknownOutcomeCount());
        generator.writeEndObject();
    }

    private static void row(final StringBuilder output, final String label,
            final int baseline, final int candidate, final int limit) {
        output.append("| ").append(label).append(" | ").append(baseline).append(" | ")
                .append(candidate).append(" | ").append(limit).append(" |\n");
    }

    private static String digest(final ObservedExecutionManifest manifest) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(new ManifestCodec().encode(manifest)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("Required SHA-256 implementation is unavailable", exception);
        }
    }

    private static String guidance(final ManifestDiffCode code) {
        return switch (code) {
            case MATCH -> "No contract change was observed. Retain the separate business-result assertion.";
            case UNSUPPORTED_SCHEMA -> "Align the manifest schema and verifier version before comparison.";
            case UNSUPPORTED_RUNTIME_IDENTITY -> "Use a supported exact adapter and runtime pair; unsupported identity evidence cannot establish a baseline match.";
            case RUNTIME_IDENTITY_MISMATCH -> "Compare evidence from the same exact runtime; after an intentional version migration, recapture and separately review the baseline.";
            case OPERATION_ID_MISMATCH -> "Select the baseline for this exact operation; do not compare unrelated operations.";
            case APPROVED_MANIFEST_NOT_ELIGIBLE -> "Recover complete, callback-failure-free baseline evidence and review it before use.";
            case CAPTURE_INCOMPLETE -> "Inspect missing terminal callbacks, interruption and collector diagnostics locally; rerun before judging budgets.";
            case CALLBACK_FAILURE_NOT_ELIGIBLE -> "Investigate the callback-reported failure and rerun; a partial count cannot justify a pass.";
            case ATTEMPT_BUDGET_EXCEEDED -> "Inspect changed sharding predicates, rewritten SQL shape and repeated executions; verify whether the increase is intentional.";
            case DATA_SOURCE_BUDGET_EXCEEDED -> "Review the observed alias set and sharding predicates against the baseline's data-source budget.";
            case POLICY_CHANGED -> "Review the policy change explicitly; candidate budgets do not override baseline budgets.";
            case STRUCTURAL_ATTEMPT_REMOVED, STRUCTURAL_ATTEMPT_ADDED -> "Compare fingerprint, parameter-type shape, alias, outcome and multiplicity in the minimized manifests.";
            case OBSERVED_ATTEMPT_COUNT_CHANGED -> "Inspect repeated or missing executions even when both counts fit the budget.";
            case OBSERVED_DATA_SOURCE_SET_CHANGED -> "Review which observed aliases changed; the alias count alone can remain equal.";
            case OUTCOME_COUNTS_CHANGED -> "Inspect callback outcome changes; callback return is not transaction commit.";
        };
    }
}
