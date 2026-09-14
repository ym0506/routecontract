package io.github.ym0506.routecontract.lifecycle;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Small strict JDK-only codec for the harness's input pins and minimized result. */
final class ProbeJson {
    private final String text;
    private int cursor;

    private ProbeJson(final String text) {
        this.text = text;
    }

    static Object parse(final String text) {
        ProbeJson parser = new ProbeJson(text);
        Object result = parser.value();
        parser.space();
        if (parser.cursor != text.length()) {
            throw new IllegalArgumentException("Trailing JSON input");
        }
        return result;
    }

    private Object value() {
        space();
        if (cursor >= text.length()) {
            throw new IllegalArgumentException("Missing JSON value");
        }
        if (text.charAt(cursor) == '"') {
            return string();
        }
        if (text.charAt(cursor) == '{') {
            cursor++;
            Map<String, Object> result = new LinkedHashMap<>();
            space();
            if (take('}')) {
                return result;
            }
            do {
                space();
                String key = string();
                space();
                expect(':');
                if (result.containsKey(key)) {
                    throw new IllegalArgumentException("Duplicate JSON key");
                }
                result.put(key, value());
                space();
            } while (take(','));
            expect('}');
            return result;
        }
        if (text.charAt(cursor) == '[') {
            cursor++;
            List<Object> result = new ArrayList<>();
            space();
            if (take(']')) {
                return result;
            }
            do {
                result.add(value());
                space();
            } while (take(','));
            expect(']');
            return result;
        }
        for (String keyword : List.of("true", "false", "null")) {
            if (text.startsWith(keyword, cursor)) {
                cursor += keyword.length();
                return keyword.equals("null") ? null : Boolean.valueOf(keyword);
            }
        }
        throw new IllegalArgumentException("Input pins permit JSON objects, arrays, strings and booleans only");
    }

    private String string() {
        expect('"');
        StringBuilder result = new StringBuilder();
        while (cursor < text.length()) {
            char ch = text.charAt(cursor++);
            if (ch == '"') {
                return result.toString();
            }
            if (ch < 0x20) {
                throw new IllegalArgumentException("Control character in JSON string");
            }
            if (ch == '\\') {
                if (cursor >= text.length()) {
                    throw new IllegalArgumentException("Incomplete JSON escape");
                }
                ch = text.charAt(cursor++);
                switch (ch) {
                    case '"', '\\', '/' -> result.append(ch);
                    case 'b' -> result.append('\b');
                    case 'f' -> result.append('\f');
                    case 'n' -> result.append('\n');
                    case 'r' -> result.append('\r');
                    case 't' -> result.append('\t');
                    case 'u' -> {
                        if (cursor + 4 > text.length()) {
                            throw new IllegalArgumentException("Incomplete JSON unicode escape");
                        }
                        result.append((char) Integer.parseInt(text.substring(cursor, cursor + 4), 16));
                        cursor += 4;
                    }
                    default -> throw new IllegalArgumentException("Invalid JSON escape");
                }
            } else {
                result.append(ch);
            }
        }
        throw new IllegalArgumentException("Unterminated JSON string");
    }

    private void space() {
        while (cursor < text.length() && " \r\n\t".indexOf(text.charAt(cursor)) >= 0) {
            cursor++;
        }
    }

    private boolean take(final char expected) {
        if (cursor < text.length() && text.charAt(cursor) == expected) {
            cursor++;
            return true;
        }
        return false;
    }

    private void expect(final char expected) {
        if (!take(expected)) {
            throw new IllegalArgumentException("Unexpected JSON token");
        }
    }

    static String write(final Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String string) {
            StringBuilder result = new StringBuilder("\"");
            for (int i = 0; i < string.length(); i++) {
                char ch = string.charAt(i);
                switch (ch) {
                    case '"' -> result.append("\\\"");
                    case '\\' -> result.append("\\\\");
                    case '\n' -> result.append("\\n");
                    case '\r' -> result.append("\\r");
                    case '\t' -> result.append("\\t");
                    default -> {
                        if (ch < 0x20) {
                            result.append(String.format("\\u%04x", (int) ch));
                        } else {
                            result.append(ch);
                        }
                    }
                }
            }
            return result.append('"').toString();
        }
        if (value instanceof Boolean || value instanceof Number) {
            return value.toString();
        }
        if (value instanceof Map<?, ?> map) {
            List<String> entries = new ArrayList<>();
            map.forEach((key, entry) -> entries.add(write(key.toString()) + ":" + write(entry)));
            return "{" + String.join(",", entries) + "}";
        }
        if (value instanceof Iterable<?> values) {
            List<String> entries = new ArrayList<>();
            values.forEach(entry -> entries.add(write(entry)));
            return "[" + String.join(",", entries) + "]";
        }
        throw new IllegalArgumentException("Unsupported JSON result value");
    }
}
