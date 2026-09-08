package example;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.List;

/** The application code whose business result is already covered by the test. */
final class OrderRepository {
    private final DataSource dataSource;

    OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    List<Order> findPaidOrders(String query) throws Exception {
        // BETWEEN 3 AND 3 returns the same business row. The configured INLINE algorithm allows
        // range queries, so ShardingSphere observes a wider execution in this synthetic fixture.
        boolean range = query.equals("range");
        String sql = range
                ? "SELECT order_id, user_id, status FROM t_order WHERE user_id BETWEEN ? AND ? AND status = ?"
                : "SELECT order_id, user_id, status FROM t_order WHERE user_id = ? AND status = ?";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, 3L);
            if (range) {
                statement.setLong(2, 3L);
            }
            statement.setString(range ? 3 : 2, "PAID");
            List<Order> rows = new ArrayList<>();
            try (ResultSet results = statement.executeQuery()) {
                while (results.next()) {
                    rows.add(new Order(results.getLong("order_id"), results.getLong("user_id"),
                            results.getString("status")));
                }
            }
            return List.copyOf(rows);
        }
    }

    record Order(long orderId, long userId, String status) {
    }
}
