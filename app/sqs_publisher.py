"""Optional SQS event publishing for asynchronous incident processing."""

import json
import logging
import os

import boto3

logger = logging.getLogger("cloudpulse.events")


def publish_metric_event(metrics: dict, thresholds: dict | None = None) -> dict:
    queue_url = os.getenv("CLOUDPULSE_SQS_QUEUE_URL")
    if not queue_url:
        logger.warning("CLOUDPULSE_SQS_QUEUE_URL is not configured; event publishing skipped")
        return {"status": "skipped", "reason": "SQS queue URL is not configured"}

    sqs = boto3.client("sqs", region_name=os.getenv("AWS_REGION", "us-east-1"))
    message = {
        "event_type": "metric_collected",
        "source": "metrics-service",
        "metrics": metrics,
    }
    if thresholds:
        message["thresholds"] = thresholds
    response = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(message, default=str),
    )
    return {"status": "sent", "message_id": response["MessageId"]}
