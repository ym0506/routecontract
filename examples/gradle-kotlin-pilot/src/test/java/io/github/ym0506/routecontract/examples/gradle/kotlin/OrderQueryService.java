package io.github.ym0506.routecontract.examples.gradle.kotlin;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

final class OrderQueryService {

    private final DataSource dataSource;

    OrderQueryService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    long countByUserId(long userId) throws Exception {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT COUNT(*) FROM t_order WHERE user_id = ?")) {
            statement.setLong(1, userId);
            try (ResultSet resultSet = statement.executeQuery()) {
                if (!resultSet.next()) {
                    throw new IllegalStateException("count query returned no row");
                }
                return resultSet.getLong(1);
            }
        }
    }
}
