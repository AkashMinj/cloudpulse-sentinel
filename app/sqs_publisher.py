import json
import os

import boto3


QUEUE_URL = os.getenv(
    "CLOUDPULSE_SQS_QUEUE_URL",
    "https://sqs.us-east-1.amazonaws.com/306005334008/cloudpulse-events",
)

sqs = boto3.client("sqs", region_name="us-east-1")


def publish_metric_event(metrics: dict) -> dict:
    message = {
        "event_type": "metric_collected",
        "source": "metrics-service",
        "metrics": metrics,
    }

    response = sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(message, default=str),
    )

    return {
        "message_id": response["MessageId"],
    }
