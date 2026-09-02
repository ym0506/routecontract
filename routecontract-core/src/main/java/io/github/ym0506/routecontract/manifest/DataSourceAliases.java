package io.github.ym0506.routecontract.manifest;

import java.util.Collection;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.TreeSet;

/**
 * Explicit mapping from environment-specific observed data-source names to stable manifest aliases.
 *
 * <p>The mapping itself is never written to a manifest. This keeps environment-specific names out of
 * the approved contract while still requiring every observed name to be intentionally classified.
 * The mapping is trusted, reviewable contract configuration: silently remapping a different observed
 * name to an existing alias can conceal target drift, so callers must version and review it with the
 * approved manifest.</p>
 */
public final class DataSourceAliases {

    private final Map<String, String> aliasesByObservedName;

    private DataSourceAliases(final Map<String, String> aliasesByObservedName) {
        this.aliasesByObservedName = Map.copyOf(aliasesByObservedName);
    }

    /**
     * Creates a collision-free alias mapping.
     *
     * @param aliasesByObservedName observed data-source name to stable alias
     * @return validated aliases
     */
    public static DataSourceAliases of(final Map<String, String> aliasesByObservedName) {
        Objects.requireNonNull(aliasesByObservedName, "aliasesByObservedName");
        Map<String, String> sorted = new TreeMap<>();
        Collection<String> aliases = new TreeSet<>();
        for (Map.Entry<String, String> entry : aliasesByObservedName.entrySet()) {
            String observedName = requireNonBlank(entry.getKey(), "observed data-source name");
            String alias = requireNonBlank(entry.getValue(), "data-source alias");
            if (!aliases.add(alias)) {
                throw new IllegalArgumentException("Data-source alias collision: " + alias);
            }
            sorted.put(observedName, alias);
        }
        return new DataSourceAliases(sorted);
    }

    /**
     * Resolves one observed name, rejecting implicit or missing aliases.
     *
     * @param observedDataSourceName callback-reported data-source name
     * @return stable manifest alias configured for that name
     * @throws IllegalArgumentException when the name is blank or has no configured alias
     */
    public String resolve(final String observedDataSourceName) {
        String name = requireNonBlank(observedDataSourceName, "observedDataSourceName");
        String alias = aliasesByObservedName.get(name);
        if (alias == null) {
            throw new IllegalArgumentException("No manifest alias configured for observed data-source name: " + name);
        }
        return alias;
    }

    private static String requireNonBlank(final String value, final String label) {
        Objects.requireNonNull(value, label);
        if (value.isBlank()) {
            throw new IllegalArgumentException(label + " must not be blank");
        }
        return value;
    }
}
