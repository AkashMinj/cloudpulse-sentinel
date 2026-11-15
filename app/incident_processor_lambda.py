import json
import os

import psycopg2
from psycopg2.extras import Json

try:
    from incident_engine import detect_incidents
except ModuleNotFoundError as exc:
    if exc.name != "incident_engine":
        raise
    from app.incident_engine import detect_incidents

def get_db_connection():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def process_message(record):
    body = json.loads(record["body"])

    if body.get("event_type") != "metric_collected":
        print(
            f"Skipping unsupported event type: "
            f"{body.get('event_type')}"
        )
        return

    metrics = body["metrics"]

    incidents = detect_incidents(metrics, thresholds=body.get("thresholds"))

    metric_id = metrics.get("metric_id")
    if metric_id is None:
        raise ValueError("metric_collected event is missing metrics.metric_id")

    if not incidents:
        print(f"No incidents detected for metric_id={metric_id}")
        return

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        for incident in incidents:
            duplicate_check_query = """
                SELECT id
                FROM incidents
                WHERE instance_id = %s
                  AND incident_type = %s
                  AND status = 'open'
                LIMIT 1;
            """

            cursor.execute(
                duplicate_check_query,
                (
                    incident["instance_id"],
                    incident["incident_type"],
                ),
            )

            existing = cursor.fetchone()
            if existing is not None:
                cursor.execute(
                    """
                    INSERT INTO incident_events (
                        incident_id, event_type, event_message, metadata, event_timestamp
                    )
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP);
                    """,
                    (
                        existing[0],
                        "async_processor_confirmed",
                        "SQS/Lambda processor evaluated the metric and confirmed an existing open incident",
                        Json({"metric_id": metric_id, "incident_type": incident["incident_type"]}),
                    ),
                )
                continue

            incident_query = """
                INSERT INTO incidents (
                    instance_id,
                    metric_id,
                    incident_type,
                    severity,
                    title,
                    description,
                    metric_value,
                    threshold_value,
                    detected_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                RETURNING id;
            """

            cursor.execute(
                incident_query,
                (
                    incident["instance_id"],
                    metric_id,
                    incident["incident_type"],
                    incident["severity"],
                    incident["title"],
                    incident["description"],
                    incident["metric_value"],
                    incident["threshold_value"],
                    incident["detected_at"],
                ),
            )
            incident_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO incident_events (
                    incident_id, event_type, event_message, metadata, event_timestamp
                )
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP);
                """,
                (
                    incident_id,
                    "async_incident_created",
                    "Incident created by the asynchronous SQS/Lambda processor",
                    Json({"metric_id": metric_id, "incident_type": incident["incident_type"]}),
                ),
            )

        connection.commit()

        print(
            f"Processed metric_id={metrics['metric_id']}, "
            f"incidents_detected={len(incidents)}"
        )

    except Exception:
        if connection is not None:
            connection.rollback()
        raise

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


def lambda_handler(event, context):
    batch_item_failures = []

    for record in event.get("Records", []):
        message_id = record.get("messageId", "unknown")

        try:
            process_message(record)

        except Exception as e:
            print(
                f"ERROR processing message {message_id}: "
                f"{type(e).__name__}: {e}"
            )

            batch_item_failures.append({
                "itemIdentifier": message_id
            })

    return {
        "batchItemFailures": batch_item_failures
    }
