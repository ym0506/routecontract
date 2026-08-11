package io.github.ym0506.routecontract.manifest;

import io.github.ym0506.routecontract.AttemptOutcome;
import io.github.ym0506.routecontract.CaptureStatus;
import tools.jackson.core.JacksonException;
import tools.jackson.core.JsonEncoding;
import tools.jackson.core.JsonGenerator;
import tools.jackson.core.JsonParser;
import tools.jackson.core.JsonToken;
import tools.jackson.core.ObjectReadContext;
import tools.jackson.core.ObjectWriteContext;
import tools.jackson.core.StreamReadFeature;
import tools.jackson.core.json.JsonFactory;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/** Strict streaming JSON codec with deterministic UTF-8, fixed field order, and one trailing LF. */
public final class ManifestCodec {

    static final int MAX_MANIFEST_BYTES = 1024 * 1024;
    private static final JsonFactory JSON_FACTORY = JsonFactory.builder()
            .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
            .build();

    /**
     * Encodes a manifest in its canonical byte representation.
     *
     * @param manifest validated manifest to encode
     * @return compact UTF-8 JSON in fixed field order with exactly one trailing line feed
     * @throws IllegalArgumentException when the encoded document exceeds one MiB
     * @throws IllegalStateException when an otherwise validated manifest cannot be encoded
     */
    public byte[] encode(final ObservedExecutionManifest manifest) {
        Objects.requireNonNull(manifest, "manifest");
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (JsonGenerator generator = JSON_FACTORY.createGenerator(
                ObjectWriteContext.empty(), output, JsonEncoding.UTF8)) {
            writeManifest(generator, manifest);
        } catch (JacksonException exception) {
            throw new IllegalStateException("Could not encode validated manifest", exception);
        }
        output.write('\n');
        byte[] encoded = output.toByteArray();
        if (encoded.length > MAX_MANIFEST_BYTES) {
            throw new IllegalArgumentException("Encoded manifest exceeds " + MAX_MANIFEST_BYTES + " bytes");
        }
        return encoded;
    }

    /**
     * Decodes and strictly validates one UTF-8 manifest document.
     *
     * @param utf8Json manifest bytes, limited to one MiB
     * @return validated manifest value
     * @throws ManifestFormatException when JSON is malformed, ambiguous, too large, or inconsistent
     */
    public ObservedExecutionManifest decode(final byte[] utf8Json) throws ManifestFormatException {
        Objects.requireNonNull(utf8Json, "utf8Json");
        if (utf8Json.length > MAX_MANIFEST_BYTES) {
            throw new ManifestFormatException("Manifest exceeds " + MAX_MANIFEST_BYTES + " bytes");
        }
        try (JsonParser parser = JSON_FACTORY.createParser(ObjectReadContext.empty(), utf8Json)) {
            ObservedExecutionManifest result = readManifest(parser);
            if (parser.nextToken() != null) {
                throw format("Trailing JSON content is not allowed");
            }
            return result;
        } catch (ManifestFormatException exception) {
            throw exception;
        } catch (JacksonException | IllegalArgumentException | ArithmeticException exception) {
            throw new ManifestFormatException("Invalid observed-execution manifest", exception);
        }
    }

    /**
     * Reads at most one MiB from a caller-owned stream, leaving stream lifecycle to the caller.
     *
     * @param input stream positioned at one UTF-8 manifest document
     * @return validated manifest value
     * @throws ManifestFormatException when the document is malformed, ambiguous, too large, or inconsistent
     * @throws IOException when the stream cannot be read
     */
    public ObservedExecutionManifest decode(final InputStream input) throws IOException {
        Objects.requireNonNull(input, "input");
        byte[] bytes = input.readNBytes(MAX_MANIFEST_BYTES + 1);
        if (bytes.length > MAX_MANIFEST_BYTES) {
            throw new ManifestFormatException("Manifest exceeds " + MAX_MANIFEST_BYTES + " bytes");
        }
        return decode(bytes);
    }

    private static void writeManifest(
            final JsonGenerator generator,
            final ObservedExecutionManifest manifest) {
        generator.writeStartObject();
        generator.writeNumberProperty("schemaVersion", manifest.schemaVersion());
        generator.writeStringProperty("operationId", manifest.operationId());
        generator.writeStringProperty("captureStatus", manifest.captureStatus().name());
        generator.writeObjectPropertyStart("policy");
        generator.writeNumberProperty(
                "maxObservedPhysicalAttempts", manifest.policy().maxObservedPhysicalAttempts());
        generator.writeNumberProperty(
                "maxDistinctObservedDataSourceNames",
                manifest.policy().maxDistinctObservedDataSourceNames());
        generator.writeBooleanProperty(
                "requireNoCallbackFailures", manifest.policy().requireNoCallbackFailures());
        generator.writeBooleanProperty(
                "requireExactExecutionSignatures",
                manifest.policy().requireExactExecutionSignatures());
        generator.writeEndObject();
        generator.writeObjectPropertyStart("counts");
        generator.writeNumberProperty(
                "observedPhysicalAttemptCount", manifest.counts().observedPhysicalAttemptCount());
        generator.writeNumberProperty("callbackReturnedCount", manifest.counts().callbackReturnedCount());
        generator.writeNumberProperty("callbackFailureCount", manifest.counts().callbackFailureCount());
        generator.writeNumberProperty("unknownOutcomeCount", manifest.counts().unknownOutcomeCount());
        generator.writeNumberProperty(
                "distinctObservedDataSourceNameCount",
                manifest.counts().distinctObservedDataSourceNameCount());
        generator.writeEndObject();
        generator.writeArrayPropertyStart("attempts");
        for (ManifestAttempt attempt : manifest.attempts()) {
            generator.writeStartObject();
            generator.writeStringProperty("observedDataSourceAlias", attempt.observedDataSourceAlias());
            generator.writeStringProperty("sqlFingerprint", attempt.sqlFingerprint());
            generator.writeNumberProperty("parameterCount", attempt.parameterCount());
            generator.writeArrayPropertyStart("parameterTypes");
            for (String parameterType : attempt.parameterTypes()) {
                generator.writeString(parameterType);
            }
            generator.writeEndArray();
            generator.writeStringProperty("outcome", attempt.outcome().name());
            generator.writeNumberProperty("multiplicity", attempt.multiplicity());
            generator.writeEndObject();
        }
        generator.writeEndArray();
        generator.writeEndObject();
    }

    private static ObservedExecutionManifest readManifest(final JsonParser parser)
            throws ManifestFormatException {
        expect(parser.nextToken(), JsonToken.START_OBJECT, "manifest object");
        Integer schemaVersion = null;
        String operationId = null;
        CaptureStatus captureStatus = null;
        ManifestPolicy policy = null;
        ManifestCounts counts = null;
        List<ManifestAttempt> attempts = null;
        while (parser.nextToken() != JsonToken.END_OBJECT) {
            expect(parser.currentToken(), JsonToken.PROPERTY_NAME, "manifest property name");
            String property = parser.currentName();
            JsonToken valueToken = parser.nextToken();
            switch (property) {
                case "schemaVersion" -> schemaVersion = readInt(parser, valueToken, property);
                case "operationId" -> operationId = readString(parser, valueToken, property);
                case "captureStatus" -> captureStatus = parseEnum(
                        CaptureStatus.class, readString(parser, valueToken, property), property);
                case "policy" -> policy = readPolicy(parser, valueToken);
                case "counts" -> counts = readCounts(parser, valueToken);
                case "attempts" -> attempts = readAttempts(parser, valueToken);
                default -> throw format("Unknown manifest property: " + property);
            }
        }
        return new ObservedExecutionManifest(
                required(schemaVersion, "schemaVersion"),
                required(operationId, "operationId"),
                required(captureStatus, "captureStatus"),
                required(policy, "policy"),
                required(counts, "counts"),
                required(attempts, "attempts"));
    }

    private static ManifestPolicy readPolicy(final JsonParser parser, final JsonToken token)
            throws ManifestFormatException {
        expect(token, JsonToken.START_OBJECT, "policy object");
        Integer maxAttempts = null;
        Integer maxDataSources = null;
        Boolean noFailures = null;
        Boolean exactSignatures = null;
        while (parser.nextToken() != JsonToken.END_OBJECT) {
            expect(parser.currentToken(), JsonToken.PROPERTY_NAME, "policy property name");
            String property = parser.currentName();
            JsonToken valueToken = parser.nextToken();
            switch (property) {
                case "maxObservedPhysicalAttempts" -> maxAttempts = readInt(parser, valueToken, property);
                case "maxDistinctObservedDataSourceNames" ->
                        maxDataSources = readInt(parser, valueToken, property);
                case "requireNoCallbackFailures" -> noFailures = readBoolean(parser, valueToken, property);
                case "requireExactExecutionSignatures" ->
                        exactSignatures = readBoolean(parser, valueToken, property);
                default -> throw format("Unknown policy property: " + property);
            }
        }
        return new ManifestPolicy(
                required(maxAttempts, "maxObservedPhysicalAttempts"),
                required(maxDataSources, "maxDistinctObservedDataSourceNames"),
                required(noFailures, "requireNoCallbackFailures"),
                required(exactSignatures, "requireExactExecutionSignatures"));
    }

    private static ManifestCounts readCounts(final JsonParser parser, final JsonToken token)
            throws ManifestFormatException {
        expect(token, JsonToken.START_OBJECT, "counts object");
        Integer attempts = null;
        Integer returned = null;
        Integer failures = null;
        Integer unknown = null;
        Integer distinctDataSources = null;
        while (parser.nextToken() != JsonToken.END_OBJECT) {
            expect(parser.currentToken(), JsonToken.PROPERTY_NAME, "counts property name");
            String property = parser.currentName();
            JsonToken valueToken = parser.nextToken();
            switch (property) {
                case "observedPhysicalAttemptCount" -> attempts = readInt(parser, valueToken, property);
                case "callbackReturnedCount" -> returned = readInt(parser, valueToken, property);
                case "callbackFailureCount" -> failures = readInt(parser, valueToken, property);
                case "unknownOutcomeCount" -> unknown = readInt(parser, valueToken, property);
                case "distinctObservedDataSourceNameCount" ->
                        distinctDataSources = readInt(parser, valueToken, property);
                default -> throw format("Unknown counts property: " + property);
            }
        }
        return new ManifestCounts(
                required(attempts, "observedPhysicalAttemptCount"),
                required(returned, "callbackReturnedCount"),
                required(failures, "callbackFailureCount"),
                required(unknown, "unknownOutcomeCount"),
                required(distinctDataSources, "distinctObservedDataSourceNameCount"));
    }

    private static List<ManifestAttempt> readAttempts(final JsonParser parser, final JsonToken token)
            throws ManifestFormatException {
        expect(token, JsonToken.START_ARRAY, "attempts array");
        List<ManifestAttempt> result = new ArrayList<>();
        while (parser.nextToken() != JsonToken.END_ARRAY) {
            expect(parser.currentToken(), JsonToken.START_OBJECT, "attempt object");
            result.add(readAttempt(parser));
        }
        return List.copyOf(result);
    }

    private static ManifestAttempt readAttempt(final JsonParser parser) throws ManifestFormatException {
        String alias = null;
        String fingerprint = null;
        Integer parameterCount = null;
        List<String> parameterTypes = null;
        AttemptOutcome outcome = null;
        Integer multiplicity = null;
        while (parser.nextToken() != JsonToken.END_OBJECT) {
            expect(parser.currentToken(), JsonToken.PROPERTY_NAME, "attempt property name");
            String property = parser.currentName();
            JsonToken valueToken = parser.nextToken();
            switch (property) {
                case "observedDataSourceAlias" -> alias = readString(parser, valueToken, property);
                case "sqlFingerprint" -> fingerprint = readString(parser, valueToken, property);
                case "parameterCount" -> parameterCount = readInt(parser, valueToken, property);
                case "parameterTypes" -> parameterTypes = readStringArray(parser, valueToken, property);
                case "outcome" -> outcome = parseEnum(
                        AttemptOutcome.class, readString(parser, valueToken, property), property);
                case "multiplicity" -> multiplicity = readInt(parser, valueToken, property);
                default -> throw format("Unknown attempt property: " + property);
            }
        }
        return new ManifestAttempt(
                required(alias, "observedDataSourceAlias"),
                required(fingerprint, "sqlFingerprint"),
                required(parameterCount, "parameterCount"),
                required(parameterTypes, "parameterTypes"),
                required(outcome, "outcome"),
                required(multiplicity, "multiplicity"));
    }

    private static List<String> readStringArray(
            final JsonParser parser,
            final JsonToken token,
            final String property) throws ManifestFormatException {
        expect(token, JsonToken.START_ARRAY, property + " array");
        List<String> result = new ArrayList<>();
        while (parser.nextToken() != JsonToken.END_ARRAY) {
            result.add(readString(parser, parser.currentToken(), property + " entry"));
        }
        return List.copyOf(result);
    }

    private static int readInt(
            final JsonParser parser,
            final JsonToken token,
            final String property) throws ManifestFormatException {
        expect(token, JsonToken.VALUE_NUMBER_INT, property + " integer");
        return parser.getIntValue();
    }

    private static boolean readBoolean(
            final JsonParser parser,
            final JsonToken token,
            final String property) throws ManifestFormatException {
        if (token != JsonToken.VALUE_TRUE && token != JsonToken.VALUE_FALSE) {
            throw format("Expected boolean for " + property + ", got " + token);
        }
        return parser.getBooleanValue();
    }

    private static String readString(
            final JsonParser parser,
            final JsonToken token,
            final String property) throws ManifestFormatException {
        expect(token, JsonToken.VALUE_STRING, property + " string");
        return parser.getString();
    }

    private static <E extends Enum<E>> E parseEnum(
            final Class<E> enumClass,
            final String value,
            final String property) throws ManifestFormatException {
        try {
            return Enum.valueOf(enumClass, value);
        } catch (IllegalArgumentException exception) {
            throw new ManifestFormatException("Unknown " + property + " value: " + value, exception);
        }
    }

    private static void expect(
            final JsonToken actual,
            final JsonToken expected,
            final String label) throws ManifestFormatException {
        if (actual != expected) {
            throw format("Expected " + label + " (" + expected + "), got " + actual);
        }
    }

    private static <T> T required(final T value, final String property) throws ManifestFormatException {
        if (value == null) {
            throw format("Missing required property: " + property);
        }
        return value;
    }

    private static ManifestFormatException format(final String message) {
        return new ManifestFormatException(message);
    }
}
