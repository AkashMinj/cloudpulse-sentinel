from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from app.metrics_archive_service import MetricsArchiveService


def test_archive_skips_without_bucket():
    result = MetricsArchiveService(bucket="").archive_metric({"metric_id": 1})
    assert result["status"] == "skipped"


def test_archive_writes_partitioned_encrypted_json():
    s3 = Mock()
    service = MetricsArchiveService(s3_client=s3, bucket="metrics-bucket")
    result = service.archive_metric({
        "metric_id": 42,
        "instance_id": "i-0123456789abcdef0",
        "timestamp": datetime(2026, 11, 15, tzinfo=timezone.utc),
        "cpu_usage_percent": 25.0,
    })
    assert result["status"] == "archived"
    assert "year=2026/month=11/day=15" in result["key"]
    kwargs = s3.put_object.call_args.kwargs
    assert kwargs["ServerSideEncryption"] == "AES256"
    assert kwargs["ContentType"] == "application/json"


def test_archive_requires_metric_id():
    with pytest.raises(ValueError, match="metric_id"):
        MetricsArchiveService(s3_client=Mock(), bucket="metrics-bucket").archive_metric({
            "instance_id": "i-0123456789abcdef0",
            "timestamp": datetime.now(timezone.utc),
        })
