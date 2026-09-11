package io.github.ym0506.routecontract.examples.maven;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

/** Representative application operation shared by the default and opt-in fixture tests. */
public final class OrderQueryService {

    private final DataSource dataSource;

    public OrderQueryService(final DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long countByUserId(final long userId) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT COUNT(*) FROM t_order WHERE user_id = ?")) {
            statement.setLong(1, userId);
            try (ResultSet resultSet = statement.executeQuery()) {
                if (!resultSet.next()) {
                    throw new SQLException("COUNT query returned no row");
                }
                return resultSet.getLong(1);
            }
        }
    }
}
