package io.github.ym0506.routecontract.manifest;

import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

/** Read-only manifest comparison with a newly created Markdown or JSON report and strict CI exit. */
public final class ManifestReviewCli {
    private static final Set<String> OPTIONS = Set.of("--baseline", "--candidate", "--format", "--output");
    private static final String USAGE = "Usage: --baseline PATH --candidate PATH --format markdown|json --output NEW_PATH";

    private ManifestReviewCli() {
    }

    /**
     * Runs the CLI and terminates with 0 for MATCH, 1 for non-match, or 2 for an input/output error.
     * @param args exactly the four named options documented by the usage message
     */
    public static void main(final String[] args) {
        System.exit(run(args, System.err));
    }

    /**
     * Runs without terminating the hosting JVM. Diagnostics contain no input data or local paths.
     * @param args CLI options
     * @param errors caller-owned diagnostic stream
     * @return strict comparison exit, or 2 when no valid complete report could be written
     */
    public static int run(final String[] args, final PrintStream errors) {
        Map<String, String> options = new HashMap<>();
        if (args.length != 8) {
            errors.println(USAGE);
            return 2;
        }
        for (int index = 0; index < args.length; index += 2) {
            if (!OPTIONS.contains(args[index]) || args[index + 1].isBlank()
                    || options.putIfAbsent(args[index], args[index + 1]) != null) {
                errors.println(USAGE);
                return 2;
            }
        }
        String format = options.get("--format");
        if (!Set.of("markdown", "json").contains(format)) {
            errors.println(USAGE);
            return 2;
        }
        try {
            ManifestStore store = new ManifestStore();
            ManifestReviewReport report = ManifestReviewReport.compare(
                    store.read(Path.of(options.get("--baseline"))),
                    store.read(Path.of(options.get("--candidate"))));
            String rendered = format.equals("json") ? report.toJson() : report.toMarkdown();
            Files.writeString(Path.of(options.get("--output")), rendered, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            return report.strictExitCode();
        } catch (IOException | IllegalArgumentException exception) {
            errors.println("RC_REPORT_ERROR: cannot read valid manifests or create a new report; inspect inputs and output path locally.");
            return 2;
        }
    }
}
