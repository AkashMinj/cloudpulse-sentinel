from unittest.mock import Mock

import pytest

from app.anomaly_detector import AnomalyResult
from app.ml_anomaly_service import (
    MLAnomalyService,
    ML_INCIDENT_CONFIRMATIONS,
)


INSTANCE_ID = "i-test-instance"


class FakeCursor:
    def __init__(self, detections):
        self.detections = detections
        self.last_query = ""
        self.closed = False

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        if "FROM incidents" in self.last_query:
            return None

        if "INSERT INTO incidents" in self.last_query:
            return (123,)

        raise AssertionError(f"Unexpected query: {self.last_query}")

    def fetchall(self):
        return self.detections

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, detections):
        self.fake_cursor = FakeCursor(detections)

    def cursor(self):
        return self.fake_cursor


def make_detection(metric_id, is_anomaly):
    return (metric_id, is_anomaly)


def make_metrics():
    return {
        "instance_id": INSTANCE_ID,
        "cpu_usage_percent": 20,
        "memory_usage_percent": 60,
        "disk_usage_percent": 48,
    }


def make_anomaly_result():
    return AnomalyResult(
        is_anomaly=True,
        anomaly_score=-0.4,
    )


def test_confirmation_threshold_is_three():
    assert ML_INCIDENT_CONFIRMATIONS == 3


@pytest.mark.parametrize(
    "detections",
    [
        [],
        [make_detection(101, True)],
        [
            make_detection(102, True),
            make_detection(101, True),
        ],
    ],
)
def test_fewer_than_three_detections_do_not_create_incident(detections):
    connection = FakeConnection(detections)
    service = MLAnomalyService()

    incident_id = service.create_anomaly_incident(
        connection,
        make_metrics(),
        make_anomaly_result(),
        metric_id=103,
    )

    assert incident_id is None
    assert connection.fake_cursor.closed


def test_normal_detection_breaks_anomaly_streak():
    connection = FakeConnection(
        [
            make_detection(103, True),
            make_detection(102, False),
            make_detection(101, True),
        ]
    )
    service = MLAnomalyService()

    incident_id = service.create_anomaly_incident(
        connection,
        make_metrics(),
        make_anomaly_result(),
        metric_id=103,
    )

    assert incident_id is None


def test_three_consecutive_anomalies_create_incident_without_sequential_ids():
    connection = FakeConnection(
        [
            make_detection(900, True),
            make_detection(850, True),
            make_detection(802, True),
        ]
    )
    service = MLAnomalyService()

    incident_id = service.create_anomaly_incident(
        connection,
        make_metrics(),
        make_anomaly_result(),
        metric_id=900,
    )

    assert incident_id == 123
    assert connection.fake_cursor.closed


def test_existing_open_incident_prevents_duplicate():
    connection = FakeConnection(
        [
            make_detection(103, True),
            make_detection(102, True),
            make_detection(101, True),
        ]
    )
    connection.fake_cursor.fetchone = Mock(return_value=(77,))
    service = MLAnomalyService()

    incident_id = service.create_anomaly_incident(
        connection,
        make_metrics(),
        make_anomaly_result(),
        metric_id=103,
    )

    assert incident_id is None
