from unittest.mock import Mock

import pytest

from app.anomaly_detector import AnomalyResult
from app.ml_anomaly_service import (
    MLAnomalyService,
    ML_INCIDENT_CONFIRMATIONS,
)
import pickle

from app.anomaly_detector import ResourceAnomalyDetector

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

def test_save_model_uploads_artifact_to_s3():
    service = MLAnomalyService()
    service.model_bucket = "test-model-bucket"
    service.s3_client = Mock()

    detector = ResourceAnomalyDetector()
    detector.fit(
        [
            {
                "cpu_usage_percent": i,
                "memory_usage_percent": 50 + i,
                "disk_usage_percent": 30 + i,
            }
            for i in range(20)
        ]
    )

    service._save_model(detector)

    kwargs = service.s3_client.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "test-model-bucket"
    assert kwargs["Key"] == "models/isolation-forest.pkl"

    artifact = pickle.loads(kwargs["Body"])
    assert artifact["model_version"] == service.model_version
    assert isinstance(artifact["detector"], ResourceAnomalyDetector)
    assert artifact["detector"]._trained


def test_load_model_restores_saved_detector():
    service = MLAnomalyService()
    service.model_bucket = "test-model-bucket"

    detector = ResourceAnomalyDetector()
    detector.fit(
        [
            {
                "cpu_usage_percent": i,
                "memory_usage_percent": 50 + i,
                "disk_usage_percent": 30 + i,
            }
            for i in range(20)
        ]
    )

    artifact = pickle.dumps(
        {
            "model_version": service.model_version,
            "detector": detector,
        }
    )
    service.s3_client = Mock()
    service.s3_client.get_object.return_value = {
        "Body": Mock(read=Mock(return_value=artifact))
    }

    assert service.load_model() is True
    assert service.is_trained is True
    assert service.detector._trained is True


def test_load_model_returns_false_when_artifact_is_missing():
    from botocore.exceptions import ClientError

    service = MLAnomalyService()
    service.model_bucket = "test-model-bucket"
    service.s3_client = Mock()
    service.s3_client.get_object.side_effect = ClientError(
        {
            "Error": {
                "Code": "NoSuchKey",
                "Message": "Not found",
            }
        },
        "GetObject",
    )

    assert service.load_model() is False
    assert service.is_trained is False


def test_training_upload_failure_preserves_active_detector():
    service = MLAnomalyService()
    service.model_bucket = "test-model-bucket"

    active_detector = service.detector
    service.is_trained = False
    service.s3_client = Mock()
    service.s3_client.put_object.side_effect = RuntimeError("S3 unavailable")

    connection = FakeConnection(
        [
            (20 + i, 50 + i, 30 + i)
            for i in range(20)
        ]
    )

    with pytest.raises(RuntimeError, match="S3 unavailable"):
        service.train_model(connection)

    assert service.detector is active_detector
    assert service.is_trained is False
    assert connection.fake_cursor.closed
