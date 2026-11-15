"""Optional S3 archival for raw metric events."""
from datetime import datetime, timezone
import json
import os
import re


class MetricsArchiveService:
    def __init__(self, s3_client=None, bucket=None):
        self.bucket = bucket if bucket is not None else os.getenv("METRICS_ARCHIVE_BUCKET")
        self._s3_client = s3_client

    def archive_metric(self, metrics: dict) -> dict:
        if not self.bucket:
            return {"status": "skipped", "reason": "Metrics archive bucket is not configured."}

        metric_id = metrics.get("metric_id")
        if metric_id is None:
            raise ValueError("metric_id is required to archive a metric")

        timestamp = metrics.get("timestamp")
        if isinstance(timestamp, datetime):
            parsed = timestamp
        else:
            parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)

        instance_id = re.sub(r"[^A-Za-z0-9._=-]", "_", str(metrics.get("instance_id", "unknown")))
        key = (
            f"raw-metrics/year={parsed:%Y}/month={parsed:%m}/day={parsed:%d}/"
            f"instance_id={instance_id}/metric_id={int(metric_id)}.json"
        )

        if self._s3_client is None:
            import boto3
            self._s3_client = boto3.client(
                "s3", region_name=os.getenv("AWS_REGION", "us-east-1")
            )

        self._s3_client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(metrics, default=str).encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        return {"status": "archived", "bucket": self.bucket, "key": key}
