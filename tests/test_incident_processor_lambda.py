import json
from unittest.mock import MagicMock, patch

from app.incident_processor_lambda import process_message


def make_metric_record(metric_id=999, cpu=85):
    return {
        "body": json.dumps({
            "event_type": "metric_collected",
            "metrics": {
                "metric_id": metric_id,
                "instance_id": "test-instance",
                "cpu_usage_percent": cpu,
                "memory_usage_percent": 40,
                "disk_usage_percent": 30,
            },
        })
    }


def test_incident_uses_metric_id_from_event():
    connection = MagicMock()
    cursor = connection.cursor.return_value

    # No existing open incident.
    cursor.fetchone.return_value = None

    with patch(
        "app.incident_processor_lambda.get_db_connection",
        return_value=connection,
    ):
        process_message(make_metric_record(metric_id=999, cpu=85))

    insert_calls = [
        call
        for call in cursor.execute.call_args_list
        if "INSERT INTO incidents" in call.args[0]
    ]

    assert len(insert_calls) == 1

    params = insert_calls[0].args[1]

    # SQL parameter order:
    # instance_id, metric_id, incident_type, severity, ...
    assert params[0] == "test-instance"
    assert params[1] == 999
    assert params[2] == "high_cpu"
    assert params[3] == "warning"
    assert params[6] == 85.0
    assert params[7] == 80


def test_no_incident_means_no_database_connection():
    with patch(
        "app.incident_processor_lambda.get_db_connection"
    ) as get_connection:
        process_message(make_metric_record(metric_id=123, cpu=50))

    get_connection.assert_not_called()
