from unittest.mock import MagicMock

from app.migrations import apply_runtime_migrations


def test_runtime_migrations_are_additive_and_committed():
    connection = MagicMock()
    cursor = connection.cursor.return_value

    apply_runtime_migrations(connection)

    executed = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("ADD COLUMN IF NOT EXISTS acknowledged_at" in statement for statement in executed)
    assert any("CREATE TABLE IF NOT EXISTS monitoring_thresholds" in statement for statement in executed)
    assert any("CREATE TABLE IF NOT EXISTS notification_history" in statement for statement in executed)
    connection.commit.assert_called_once()
    cursor.close.assert_called_once()
