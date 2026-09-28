from fastapi.testclient import TestClient
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.main import app


client = TestClient(app)


def test_root():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "CloudPulse Sentinel",
        "status": "running",
        "version": "0.8.0",
    }


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
    }


def test_metrics_history_limit_validation():
    response = client.get("/api/v1/metrics/history?limit=0")

    assert response.status_code == 422


def test_metrics_history_limit_upper_bound():
    response = client.get("/api/v1/metrics/history?limit=201")

    assert response.status_code == 422

def test_db_health_success():
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1,)

    mock_connection = MagicMock()
    mock_connection.cursor.return_value = mock_cursor

    with patch(
        "app.main.get_db_connection",
        return_value=mock_connection,
    ):
        response = client.get("/api/v1/db/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "database": "postgresql",
        "check": True,
    }

    mock_cursor.execute.assert_called_once_with("SELECT 1;")
    mock_cursor.close.assert_called_once()
    mock_connection.close.assert_called_once()


def test_db_health_failure():
    with patch(
        "app.main.get_db_connection",
        side_effect=Exception("database unavailable"),
    ):
        response = client.get("/api/v1/db/health")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Database connection failed",
    }


def test_metrics_collect_success():
    metrics = {
        "instance_id": "test-instance",
        "timestamp": datetime.now(timezone.utc),
        "cpu_usage_percent": 50.0,
        "cpu_count": 4,
        "memory_usage_percent": 60.0,
        "memory_total_gb": 8.0,
        "memory_available_gb": 3.2,
        "disk_usage_percent": 40.0,
        "disk_total_gb": 50.0,
        "disk_free_gb": 30.0,
    }

    mock_cursor = MagicMock()

    # First database INSERT returns metric ID 123.
    mock_cursor.fetchone.return_value = (123,)

    mock_connection = MagicMock()
    mock_connection.cursor.return_value = mock_cursor

    with patch(
        "app.main.collect_system_metrics",
        return_value=metrics,
    ), patch(
        "app.main.get_db_connection",
        return_value=mock_connection,
    ), patch(
        "app.main.publish_metric_event"
    ) as mock_publish:

        response = client.post("/api/v1/metrics/collect")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "success"
    assert body["message"] == "Metrics collected and stored"
    assert body["metric_id"] == 123
    assert body["instance_id"] == "test-instance"
    assert body["timestamp"] == metrics["timestamp"].isoformat()

    mock_connection.commit.assert_called_once()
    mock_publish.assert_called_once()

    mock_cursor.close.assert_called_once()
    mock_connection.close.assert_called_once()


def test_metrics_collect_database_failure():
    metrics = {
        "instance_id": "test-instance",
        "timestamp": datetime.now(timezone.utc),
        "cpu_usage_percent": 50.0,
        "cpu_count": 4,
        "memory_usage_percent": 60.0,
        "memory_total_gb": 8.0,
        "memory_available_gb": 3.2,
        "disk_usage_percent": 40.0,
        "disk_total_gb": 50.0,
        "disk_free_gb": 30.0,
    }

    mock_connection = MagicMock()
    mock_cursor = MagicMock()
    mock_connection.cursor.return_value = mock_cursor

    mock_cursor.execute.side_effect = Exception("database write failed")

    with patch(
        "app.main.collect_system_metrics",
        return_value=metrics,
    ), patch(
        "app.main.get_db_connection",
        return_value=mock_connection,
    ), patch(
        "app.main.publish_metric_event"
    ):

        response = client.post("/api/v1/metrics/collect")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Unable to collect and store metrics",
    }

    mock_connection.rollback.assert_called_once()
