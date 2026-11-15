
import os
from contextlib import asynccontextmanager
import time
import logging
from collections import deque
from threading import Lock
import urllib.request
from datetime import datetime, timedelta, timezone

import psycopg2
import psutil
from app.incident_engine import detect_incidents
from app.sqs_publisher import publish_metric_event
from app.notification_service import NotificationService
from app.cost_analyzer import build_utilization_recommendations
from app.metrics_archive_service import MetricsArchiveService
from app.incident_replay import IncidentReplay
from app.ml_anomaly_service import MLAnomalyService
from app.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    require_auth,
    require_role,
    get_password_hash,
)
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from psycopg2.extras import Json
from app.migrations import apply_runtime_migrations

logger = logging.getLogger("cloudpulse")

# Initialize services before creating the FastAPI lifespan handler.
ml_service = MLAnomalyService()
notification_service = NotificationService()
metrics_archive_service = MetricsArchiveService()


@asynccontextmanager
async def app_lifespan(_app):
    try:
        migration_connection = get_db_connection()
        try:
            apply_runtime_migrations(migration_connection)
        finally:
            migration_connection.close()
    except Exception:
        # Keep the API process observable if the database is temporarily unavailable.
        # Database-backed endpoints will return a clear service error until it recovers.
        logger.exception("CloudPulse runtime database migrations failed")

    try:
        loaded = ml_service.load_model()
        if loaded:
            logger.info("ML model loaded successfully from persistent storage.")
        else:
            logger.info("No saved ML model found; training is required.")
    except Exception:
        logger.exception("Failed to load ML model")
    yield


app = FastAPI(
    title="CloudPulse Sentinel",
    version="0.9.0",
    lifespan=app_lifespan,
)

# Request telemetry
REQUEST_WINDOW_SECONDS = 300
_request_lock = Lock()
_request_events = deque()


def record_request(status_code: int, latency_ms: float):
    now = time.time()

    with _request_lock:
        _request_events.append((now, status_code, latency_ms))

        cutoff = now - REQUEST_WINDOW_SECONDS

        while _request_events and _request_events[0][0] < cutoff:
            _request_events.popleft()


def get_request_metrics():
    now = time.time()
    cutoff = now - REQUEST_WINDOW_SECONDS

    with _request_lock:
        while _request_events and _request_events[0][0] < cutoff:
            _request_events.popleft()

        events = list(_request_events)

    if not events:
        return {
            "latency_ms": None,
            "error_rate_percent": 0.0,
            "request_rate": 0.0,
        }

    total_requests = len(events)
    error_requests = sum(
        1 for _, status_code, _ in events
        if status_code >= 400
    )

    average_latency = sum(
        latency for _, _, latency in events
    ) / total_requests

    request_rate = total_requests / REQUEST_WINDOW_SECONDS

    return {
        "latency_ms": round(average_latency, 2),
        "error_rate_percent": round(
            (error_requests / total_requests) * 100,
            2,
        ),
        "request_rate": round(request_rate, 4),
    }

@app.middleware("http")
async def request_telemetry(request: Request, call_next):
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        latency_ms = (time.perf_counter() - start_time) * 1000
        record_request(500, latency_ms)
        raise

    latency_ms = (time.perf_counter() - start_time) * 1000
    record_request(response.status_code, latency_ms)

    return response

# -------------------------
# EC2 METADATA FUNCTIONS
# -------------------------

def get_metadata_token():
    request = urllib.request.Request(
        "http://169.254.169.254/latest/api/token",
        method="PUT",
        headers={
            "X-aws-ec2-metadata-token-ttl-seconds": "21600"
        },
    )

    with urllib.request.urlopen(request, timeout=2) as response:
        return response.read().decode()


def get_instance_metadata(path, token):
    request = urllib.request.Request(
        f"http://169.254.169.254/latest/meta-data/{path}",
        headers={
            "X-aws-ec2-metadata-token": token
        },
    )

    with urllib.request.urlopen(request, timeout=2) as response:
        return response.read().decode()


# -------------------------
# DATABASE CONNECTION
# -------------------------

def get_db_connection():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=5,
    )


DEFAULT_THRESHOLDS = {
    "cpu": {"warning": 80.0, "critical": 95.0},
    "memory": {"warning": 80.0, "critical": 95.0},
    "disk": {"warning": 80.0, "critical": 95.0},
}


class ThresholdRequest(BaseModel):
    cpu_warning: float = Field(default=80, ge=1, le=99)
    cpu_critical: float = Field(default=95, ge=2, le=100)
    memory_warning: float = Field(default=80, ge=1, le=99)
    memory_critical: float = Field(default=95, ge=2, le=100)
    disk_warning: float = Field(default=80, ge=1, le=99)
    disk_critical: float = Field(default=95, ge=2, le=100)


class MetricsIngestRequest(BaseModel):
    instance_id: str = Field(min_length=1, max_length=255)
    cpu_usage_percent: float = Field(ge=0, le=100)
    memory_usage_percent: float = Field(ge=0, le=100)
    disk_usage_percent: float = Field(ge=0, le=100)
    cpu_count: int = Field(default=1, ge=1)
    memory_total_gb: float = Field(default=0, ge=0)
    memory_available_gb: float = Field(default=0, ge=0)
    disk_total_gb: float = Field(default=0, ge=0)
    disk_free_gb: float = Field(default=0, ge=0)
    latency_ms: float | None = Field(default=None, ge=0)
    error_rate_percent: float | None = Field(default=None, ge=0, le=100)
    request_rate: float | None = Field(default=None, ge=0)
    timestamp: datetime | None = None


def load_thresholds(cursor):
    """Read configured warning/critical resource thresholds."""
    result = {
        name: values.copy() for name, values in DEFAULT_THRESHOLDS.items()
    }
    cursor.execute(
        "SELECT metric_name, warning_threshold, critical_threshold FROM monitoring_thresholds;"
    )
    for metric_name, warning_threshold, critical_threshold in cursor.fetchall():
        if metric_name in result:
            result[metric_name] = {
                "warning": float(warning_threshold),
                "critical": float(critical_threshold),
            }
    return result


def store_notification_result(connection, incident: dict, channel: str, result: dict) -> None:
    """Persist channel outcome without recording credentials or webhook URLs."""
    details = {
        key: result[key]
        for key in ("reason", "error_type", "recipient_count")
        if key in result
    }
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO notification_history
                (incident_id, instance_id, channel, status, provider_reference, details)
            VALUES (%s, %s, %s, %s, %s, %s);
            """,
            (
                incident.get("id"),
                incident.get("instance_id"),
                channel,
                result.get("status", "unknown"),
                result.get("message_id"),
                Json(details),
            ),
        )
        connection.commit()
    finally:
        cursor.close()


# -------------------------
# SYSTEM METRICS COLLECTION
# -------------------------


def collect_system_metrics():
    # Use a configured instance ID when running locally or in a
    # non-EC2 environment. Otherwise, discover the EC2 instance ID.
    instance_id = os.getenv("INSTANCE_ID")

    if not instance_id:
        try:
            token = get_metadata_token()
            instance_id = get_instance_metadata("instance-id", token)
        except Exception:
            if os.getenv("ENVIRONMENT", "local").lower() == "aws":
                raise
            instance_id = "local-docker"

    disk_usage = psutil.disk_usage("/")
    memory_usage = psutil.virtual_memory()
    cpu_usage = psutil.cpu_percent(interval=1)

    timestamp = datetime.now(timezone.utc)

    return {
        "instance_id": instance_id,
        "timestamp": timestamp,
        "cpu_usage_percent": cpu_usage,
        "cpu_count": psutil.cpu_count(),
        "memory_usage_percent": memory_usage.percent,
        "memory_total_gb": round(
            memory_usage.total / (1024 ** 3), 2
        ),
        "memory_available_gb": round(
            memory_usage.available / (1024 ** 3), 2
        ),
        "disk_usage_percent": disk_usage.percent,
        "disk_total_gb": round(
            disk_usage.total / (1024 ** 3), 2
        ),
        "disk_free_gb": round(
            disk_usage.free / (1024 ** 3), 2
        ),
    }


# -------------------------
# BASIC ENDPOINTS
# -------------------------

@app.get("/")
def root():
    return {
        "service": "CloudPulse Sentinel",
        "status": "running",
        "version": "0.9.0",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
    }


# -------------------------
# EC2 INSTANCE ENDPOINT
# -------------------------

@app.get("/api/v1/instance")
def instance_info():
    try:
        token = get_metadata_token()

        return {
            "instance_id": get_instance_metadata(
                "instance-id", token
            ),
            "instance_type": get_instance_metadata(
                "instance-type", token
            ),
            "availability_zone": get_instance_metadata(
                "placement/availability-zone", token
            ),
            "private_ip": get_instance_metadata(
                "local-ipv4", token
            ),
        }

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Unable to retrieve instance metadata",
        )


# -------------------------
# DATABASE HEALTH ENDPOINT
# -------------------------

@app.get("/api/v1/db/health")
def db_health():
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("SELECT 1;")
        result = cursor.fetchone()

        return {
            "status": "healthy",
            "database": "postgresql",
            "check": result[0] == 1,
        }

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        )

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


# -------------------------
# LIVE SYSTEM METRICS
# -------------------------

@app.get("/api/v1/metrics")
def system_metrics():
    try:
        return collect_system_metrics()

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Unable to collect system metrics",
        )


# -------------------------
# COLLECT AND STORE METRICS
# -------------------------

@app.post("/api/v1/metrics/collect")
def collect_and_store_metrics():
    connection = None
    cursor = None

    try:
        metrics = collect_system_metrics()
        request_metrics = get_request_metrics()
        metrics.update(request_metrics)

        connection = get_db_connection()
        cursor = connection.cursor()

        insert_query = """
            INSERT INTO system_metrics (
                instance_id,
                timestamp,
                cpu_usage_percent,
                cpu_count,
                memory_usage_percent,
                memory_total_gb,
                memory_available_gb,
                disk_usage_percent,
                disk_total_gb,
                disk_free_gb,
                latency_ms,
                error_rate_percent,
                request_rate
            )
            VALUES(
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s
            )
            RETURNING id;
        """

        cursor.execute(
            insert_query,
            (
                metrics["instance_id"],
                metrics["timestamp"],
                metrics["cpu_usage_percent"],
                metrics["cpu_count"],
                metrics["memory_usage_percent"],
                metrics["memory_total_gb"],
                metrics["memory_available_gb"],
                metrics["disk_usage_percent"],
                metrics["disk_total_gb"],
                metrics["disk_free_gb"],
                metrics.get("latency_ms"),
                metrics.get("error_rate_percent"),
                metrics.get("request_rate"),
            ),
        )

        metric_id = cursor.fetchone()[0]
        created_incidents = []
        configured_thresholds = load_thresholds(cursor)

        # Automatically resolve incidents when metrics return below the warning threshold.
        resolution_checks = [
            {
                "incident_type": "high_cpu",
                "value": metrics["cpu_usage_percent"],
                "threshold": configured_thresholds["cpu"]["warning"],
            },
            {
                "incident_type": "high_memory",
                "value": metrics["memory_usage_percent"],
                "threshold": configured_thresholds["memory"]["warning"],
            },
            {
                "incident_type": "high_disk",
                "value": metrics["disk_usage_percent"],
                "threshold": configured_thresholds["disk"]["warning"],
            },
        ]

        for check in resolution_checks:
            if float(check["value"]) < check["threshold"]:
                resolve_query = """
                    UPDATE incidents
                    SET
                        status = 'resolved',
                        resolved_at = CURRENT_TIMESTAMP
                    WHERE instance_id = %s
                      AND incident_type = %s
                      AND status = 'open'
                    RETURNING id;
                """

                cursor.execute(
                    resolve_query,
                    (
                        metrics["instance_id"],
                        check["incident_type"],
                    ),
                )
                for (resolved_incident_id,) in cursor.fetchall():
                    IncidentReplay.record_event(
                        connection,
                        resolved_incident_id,
                        "incident_resolved",
                        "Metrics returned below the configured threshold",
                        {
                            "metric_id": metric_id,
                            "metric_value": float(check["value"]),
                            "threshold": check["threshold"],
                        },
                    )

        # Detect incidents from collected metrics
        incidents = detect_incidents(metrics, configured_thresholds)

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

            existing_incident = cursor.fetchone()

            if existing_incident is not None:
                existing_incident_id = existing_incident[0]

                cursor.execute(
                    """
                    SELECT severity
                    FROM incidents
                    WHERE id = %s
                      AND status = 'open';
                    """,
                    (existing_incident_id,),
                )
                existing_details = cursor.fetchone()

                if existing_details is not None:
                    previous_severity = existing_details[0]

                    cursor.execute(
                        """
                        UPDATE incidents
                        SET
                            metric_id = %s,
                            severity = %s,
                            title = %s,
                            description = %s,
                            metric_value = %s,
                            threshold_value = %s
                        WHERE id = %s
                          AND status = 'open';
                        """,
                        (
                            metric_id,
                            incident["severity"],
                            incident["title"],
                            incident["description"],
                            incident["metric_value"],
                            incident["threshold_value"],
                            existing_incident_id,
                        ),
                    )

                    if previous_severity != incident["severity"]:
                        IncidentReplay.record_event(
                            connection,
                            existing_incident_id,
                            "incident_severity_changed",
                            (
                                f"Incident severity changed from "
                                f"{previous_severity} to "
                                f"{incident['severity']}"
                            ),
                            {
                                "previous_severity": previous_severity,
                                "new_severity": incident["severity"],
                                "metric_value": incident["metric_value"],
                                "threshold": incident["threshold_value"],
                            },
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

            IncidentReplay.record_event(
                connection,
                incident_id,
                "threshold_breach",
                f"{incident['incident_type']} crossed threshold",
                {
                    "metric_value": incident["metric_value"],
                    "threshold": incident["threshold_value"],
                },
            )

            IncidentReplay.record_event(
                connection,
                incident_id,
                "incident_created",
                f"Incident created: {incident['title']}",
                {
                    "severity": incident["severity"],
                },
            )
            created_incidents.append({
                **incident,
                "id": incident_id,
            })

        # ML anomaly detection
        try:
            cursor.execute("SAVEPOINT ml_anomaly_detection")

            if ml_service.is_trained:
                anomaly_result = ml_service.detect_anomaly(
                    connection,
                    metrics,
                    metric_id,
                )

                if anomaly_result:
                    if anomaly_result.is_anomaly:
                        anomaly_incident_id = ml_service.create_anomaly_incident(
                            connection,
                            metrics,
                            anomaly_result,
                            metric_id,
                        )

                        if anomaly_incident_id:
                            if anomaly_result.anomaly_score >= -0.3:
                                ml_severity = "info"
                            elif anomaly_result.anomaly_score >= -0.5:
                                ml_severity = "warning"
                            else:
                                ml_severity = "critical"

                            IncidentReplay.record_event(
                                connection,
                                anomaly_incident_id,
                                "incident_created",
                                "ML anomaly incident created",
                                {
                                    "severity": ml_severity,
                                    "metric_id": metric_id,
                                },
                            )

                            IncidentReplay.record_event(
                                connection,
                                anomaly_incident_id,
                                "ml_anomaly_detected",
                                (
                                    "ML model detected anomaly with "
                                    f"score {anomaly_result.anomaly_score:.4f}"
                                ),
                                {
                                    "anomaly_score": anomaly_result.anomaly_score,
                                    "signals": ml_service.get_anomaly_signals(
                                        metrics
                                    ),
                                },
                            )
                            created_incidents.append({
                                "id": anomaly_incident_id,
                                "instance_id": metrics["instance_id"],
                                "incident_type": "ml_anomaly",
                                "severity": ml_severity,
                                "title": "ML anomaly detected",
                                "description": "Isolation Forest detected an unusual resource pattern.",
                                "detected_at": metrics["timestamp"],
                            })

                    else:
                        cursor.execute(
                            """
                            UPDATE incidents
                            SET
                                status = 'resolved',
                                resolved_at = CURRENT_TIMESTAMP
                            WHERE instance_id = %s
                              AND incident_type = 'ml_anomaly'
                              AND status = 'open'
                            RETURNING id;
                            """,
                            (metrics["instance_id"],),
                        )

                        resolved_incidents = cursor.fetchall()

                        for (resolved_incident_id,) in resolved_incidents:
                            IncidentReplay.record_event(
                                connection,
                                resolved_incident_id,
                                "incident_resolved",
                                "ML anomaly returned to normal",
                                {
                                    "metric_id": metric_id,
                                    "anomaly_score": anomaly_result.anomaly_score,
                                },
                            )

            cursor.execute("RELEASE SAVEPOINT ml_anomaly_detection")

        except Exception:
            cursor.execute("ROLLBACK TO SAVEPOINT ml_anomaly_detection")
            cursor.execute("RELEASE SAVEPOINT ml_anomaly_detection")
            logger.exception("ML anomaly detection failed")

        connection.commit()

        # Deliver notifications after the incident transaction commits so a provider
        # outage can never roll back the metric or incident records.
        for incident_notice in created_incidents:
            deliveries = (
                ("sns", notification_service.notify_incident),
                ("email", notification_service.notify_email),
                ("slack", notification_service.notify_slack),
            )
            for channel, sender in deliveries:
                try:
                    if channel == "email" and incident_notice.get("severity") != "critical":
                        notification_result = {
                            "status": "skipped",
                            "reason": "Email alerts are configured for critical incidents only.",
                        }
                    else:
                        notification_result = sender(incident_notice)
                    store_notification_result(
                        connection, incident_notice, channel, notification_result
                    )
                    if channel == "sns" and notification_result.get("status") == "sent":
                        IncidentReplay.record_event(
                            connection,
                            incident_notice["id"],
                            "notification_sent",
                            "Incident notification published to the configured SNS topic",
                            {"message_id": notification_result.get("message_id")},
                        )
                        connection.commit()
                    elif notification_result.get("status") == "failed":
                        logger.error(
                            "%s notification failed for incident %s (%s)",
                            channel,
                            incident_notice["id"],
                            notification_result.get("error_type"),
                        )
                except Exception:
                    connection.rollback()
                    logger.exception(
                        "Could not process %s notification for incident %s",
                        channel,
                        incident_notice["id"],
                    )

        # The Lambda processor requires the persisted metric ID for traceability.
        event_metrics = {**metrics, "metric_id": metric_id}
        try:
            archive_result = metrics_archive_service.archive_metric(event_metrics)
            if archive_result.get("status") == "archived":
                logger.info(
                    "Archived metric %s to s3://%s/%s",
                    metric_id,
                    archive_result["bucket"],
                    archive_result["key"],
                )
        except Exception:
            logger.exception("Metric %s could not be archived to S3", metric_id)

        try:
            publish_metric_event(event_metrics, thresholds=configured_thresholds)
        except Exception:
            logger.exception("Metric event could not be published to SQS")

        return {
            "status": "success",
            "message": "Metrics collected and stored",
            "metric_id": metric_id,
            "instance_id": metrics["instance_id"],
            "timestamp": metrics["timestamp"].isoformat(),
        }

    except Exception as e:
        if connection is not None:
            connection.rollback()

        print(f"METRICS COLLECTION ERROR: {type(e).__name__}: {e}", flush=True)

        raise HTTPException(
            status_code=503,
            detail="Unable to collect and store metrics",
        )

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


# -------------------------
# MULTI-INSTANCE METRIC INGESTION
# -------------------------

@app.post("/api/v1/metrics/ingest")
def ingest_instance_metrics(
    request: MetricsIngestRequest,
    x_metrics_token: str | None = Header(default=None, alias="X-Metrics-Token"),
):
    """Accept telemetry from remote per-instance agents using a shared ingest token."""
    import hmac

    configured_token = os.getenv("METRICS_INGEST_TOKEN", "")
    if len(configured_token) < 32:
        raise HTTPException(
            status_code=503,
            detail="Remote metric ingestion is disabled until METRICS_INGEST_TOKEN is configured.",
        )
    if not x_metrics_token or not hmac.compare_digest(x_metrics_token, configured_token):
        raise HTTPException(status_code=401, detail="Invalid metrics ingestion token")

    metrics = request.model_dump()
    timestamp = metrics.get("timestamp") or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    metrics["timestamp"] = timestamp

    connection = None
    cursor = None
    created_incidents = []
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        thresholds = load_thresholds(cursor)
        cursor.execute(
            """
            INSERT INTO system_metrics (
                instance_id, timestamp, cpu_usage_percent, cpu_count,
                memory_usage_percent, memory_total_gb, memory_available_gb,
                disk_usage_percent, disk_total_gb, disk_free_gb,
                latency_ms, error_rate_percent, request_rate
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                metrics["instance_id"], timestamp,
                metrics["cpu_usage_percent"], metrics["cpu_count"],
                metrics["memory_usage_percent"], metrics["memory_total_gb"],
                metrics["memory_available_gb"], metrics["disk_usage_percent"],
                metrics["disk_total_gb"], metrics["disk_free_gb"],
                metrics["latency_ms"], metrics["error_rate_percent"], metrics["request_rate"],
            ),
        )
        metric_id = cursor.fetchone()[0]
        metrics["metric_id"] = metric_id

        # Resolve threshold incidents when this instance returns below its warning level.
        resolution_checks = (
            ("high_cpu", metrics["cpu_usage_percent"], thresholds["cpu"]["warning"]),
            ("high_memory", metrics["memory_usage_percent"], thresholds["memory"]["warning"]),
            ("high_disk", metrics["disk_usage_percent"], thresholds["disk"]["warning"]),
        )
        for incident_type, value, warning_threshold in resolution_checks:
            if float(value) < warning_threshold:
                cursor.execute(
                    """
                    UPDATE incidents
                    SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP
                    WHERE instance_id = %s AND incident_type = %s AND status = 'open'
                    RETURNING id;
                    """,
                    (metrics["instance_id"], incident_type),
                )
                for (resolved_id,) in cursor.fetchall():
                    IncidentReplay.record_event(
                        connection,
                        resolved_id,
                        "incident_resolved",
                        "Remote instance metrics returned below the configured threshold",
                        {
                            "metric_id": metric_id,
                            "metric_value": float(value),
                            "threshold": warning_threshold,
                        },
                    )

        for incident in detect_incidents(metrics, thresholds):
            cursor.execute(
                """
                SELECT id FROM incidents
                WHERE instance_id = %s AND incident_type = %s AND status = 'open'
                LIMIT 1;
                """,
                (incident["instance_id"], incident["incident_type"]),
            )
            existing = cursor.fetchone()
            if existing:
                cursor.execute(
                    """
                    UPDATE incidents
                    SET metric_id = %s, severity = %s, metric_value = %s,
                        threshold_value = %s, title = %s, description = %s
                    WHERE id = %s;
                    """,
                    (
                        metric_id, incident["severity"], incident["metric_value"],
                        incident["threshold_value"], incident["title"],
                        incident["description"], existing[0],
                    ),
                )
                continue

            cursor.execute(
                """
                INSERT INTO incidents (
                    instance_id, metric_id, incident_type, severity, title,
                    description, metric_value, threshold_value, detected_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    incident["instance_id"], metric_id, incident["incident_type"],
                    incident["severity"], incident["title"], incident["description"],
                    incident["metric_value"], incident["threshold_value"], incident["detected_at"],
                ),
            )
            incident_id = cursor.fetchone()[0]
            incident_notice = {**incident, "id": incident_id}
            IncidentReplay.record_event(
                connection, incident_id, "incident_created",
                "Incident created from remote instance telemetry",
                {"metric_id": metric_id, "source": "remote_agent"},
            )
            created_incidents.append(incident_notice)

        # Run the same ML anomaly workflow for remote instances as for the local collector.
        try:
            cursor.execute("SAVEPOINT remote_ml_detection")
            if ml_service.is_trained:
                anomaly_result = ml_service.detect_anomaly(connection, metrics, metric_id)
                if anomaly_result and anomaly_result.is_anomaly:
                    anomaly_incident_id = ml_service.create_anomaly_incident(
                        connection, metrics, anomaly_result, metric_id
                    )
                    if anomaly_incident_id:
                        ml_severity = (
                            "critical" if anomaly_result.anomaly_score < -0.5
                            else "warning" if anomaly_result.anomaly_score < -0.3
                            else "info"
                        )
                        IncidentReplay.record_event(
                            connection,
                            anomaly_incident_id,
                            "incident_created",
                            "ML anomaly incident created from remote instance telemetry",
                            {"severity": ml_severity, "metric_id": metric_id},
                        )
                        IncidentReplay.record_event(
                            connection,
                            anomaly_incident_id,
                            "ml_anomaly_detected",
                            f"ML model detected anomaly with score {anomaly_result.anomaly_score:.4f}",
                            {
                                "anomaly_score": anomaly_result.anomaly_score,
                                "signals": ml_service.get_anomaly_signals(metrics),
                            },
                        )
                        created_incidents.append({
                            "id": anomaly_incident_id,
                            "instance_id": metrics["instance_id"],
                            "incident_type": "ml_anomaly",
                            "severity": ml_severity,
                            "title": "ML anomaly detected",
                            "description": "Isolation Forest detected an unusual resource pattern.",
                            "detected_at": timestamp,
                        })
                elif anomaly_result:
                    cursor.execute(
                        """
                        UPDATE incidents
                        SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP
                        WHERE instance_id = %s AND incident_type = 'ml_anomaly' AND status = 'open'
                        RETURNING id;
                        """,
                        (metrics["instance_id"],),
                    )
                    for (resolved_id,) in cursor.fetchall():
                        IncidentReplay.record_event(
                            connection,
                            resolved_id,
                            "incident_resolved",
                            "Remote instance ML prediction returned to normal",
                            {"metric_id": metric_id, "anomaly_score": anomaly_result.anomaly_score},
                        )
            cursor.execute("RELEASE SAVEPOINT remote_ml_detection")
        except Exception:
            cursor.execute("ROLLBACK TO SAVEPOINT remote_ml_detection")
            cursor.execute("RELEASE SAVEPOINT remote_ml_detection")
            logger.exception("Remote instance ML anomaly detection failed")

        connection.commit()

        for incident_notice in created_incidents:
            for channel, sender in (
                ("sns", notification_service.notify_incident),
                ("email", notification_service.notify_email),
                ("slack", notification_service.notify_slack),
            ):
                try:
                    if channel == "email" and incident_notice.get("severity") != "critical":
                        delivery = {
                            "status": "skipped",
                            "reason": "Email alerts are configured for critical incidents only.",
                        }
                    else:
                        delivery = sender(incident_notice)
                    store_notification_result(
                        connection, incident_notice, channel, delivery
                    )
                except Exception:
                    connection.rollback()
                    logger.exception("Remote-agent %s notification failed", channel)

        try:
            metrics_archive_service.archive_metric(metrics)
        except Exception:
            logger.exception("Remote metric %s could not be archived", metric_id)
        try:
            publish_metric_event(metrics, thresholds=thresholds)
        except Exception:
            logger.exception("Remote metric %s could not be published to SQS", metric_id)

        return {
            "status": "success",
            "metric_id": metric_id,
            "instance_id": metrics["instance_id"],
            "incidents_created": len(created_incidents),
            "timestamp": timestamp.isoformat(),
        }
    except HTTPException:
        if connection is not None:
            connection.rollback()
        raise
    except Exception:
        if connection is not None:
            connection.rollback()
        logger.exception("Remote metric ingestion failed")
        raise HTTPException(status_code=503, detail="Unable to ingest remote instance metrics")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


# -------------------------
# METRICS HISTORY
# -------------------------

@app.get("/api/v1/metrics/history")
def metrics_history(
    limit: int = Query(default=20, ge=1, le=500),
    instance_id: str | None = Query(default=None, min_length=1, max_length=255),
):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        query = """
            SELECT
                id,
                instance_id,
                timestamp,
                cpu_usage_percent,
                cpu_count,
                memory_usage_percent,
                memory_total_gb,
                memory_available_gb,
                disk_usage_percent,
                disk_total_gb,
                disk_free_gb,
                latency_ms,
                error_rate_percent,
                request_rate,
                created_at
            FROM system_metrics
        """
        parameters = []
        if instance_id:
            query += " WHERE instance_id = %s"
            parameters.append(instance_id)
        query += " ORDER BY timestamp DESC LIMIT %s;"
        parameters.append(limit)

        cursor.execute(query, tuple(parameters))
        rows = cursor.fetchall()

        metrics = []

        for row in rows:
            metrics.append({
                "id": row[0],
                "instance_id": row[1],
                "timestamp": row[2].isoformat(),
                "cpu_usage_percent": float(row[3]),
                "cpu_count": row[4],
                "memory_usage_percent": float(row[5]),
                "memory_total_gb": float(row[6]),
                "memory_available_gb": float(row[7]),
                "disk_usage_percent": float(row[8]),
                "disk_total_gb": float(row[9]),
                "disk_free_gb": float(row[10]),
                "latency_ms": float(row[11]) if row[11] is not None else None,
                "error_rate_percent": float(row[12]) if row[12] is not None else None,
                "request_rate": float(row[13]) if row[13] is not None else None,
                "created_at": row[14].isoformat(),
            })

        return {
            "count": len(metrics),
            "metrics": metrics,
        }

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Unable to retrieve metric history",
        )

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

# -------------------------
# INCIDENTS
# -------------------------

@app.get("/api/v1/incidents")
def get_incidents(
    limit: int = Query(default=20, ge=1, le=100),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    instance_id: str | None = Query(default=None, min_length=1, max_length=255),
):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        query = """
            SELECT
                id,
                instance_id,
                metric_id,
                incident_type,
                severity,
                title,
                description,
                metric_value,
                threshold_value,
                status,
                detected_at,
                resolved_at,
                created_at,
                acknowledged_at,
                acknowledged_by
            FROM incidents
        """

        conditions = []
        parameters = []

        if severity is not None:
            conditions.append("severity = %s")
            parameters.append(severity)

        if status is not None:
            conditions.append("status = %s")
            parameters.append(status)
        if instance_id is not None:
            conditions.append("instance_id = %s")
            parameters.append(instance_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY detected_at DESC LIMIT %s;"
        parameters.append(limit)

        cursor.execute(query, tuple(parameters))
        rows = cursor.fetchall()

        incidents = []

        for row in rows:
            incidents.append({
                "id": row[0],
                "instance_id": row[1],
                "metric_id": row[2],
                "incident_type": row[3],
                "severity": row[4],
                "title": row[5],
                "description": row[6],
                "metric_value": float(row[7]),
                "threshold_value": float(row[8]),
                "status": row[9],
                "detected_at": row[10].isoformat(),
                "resolved_at": row[11].isoformat() if row[11] else None,
                "created_at": row[12].isoformat(),
                "acknowledged_at": row[13].isoformat() if row[13] else None,
                "acknowledged_by": row[14],
            })

        return {
            "count": len(incidents),
            "incidents": incidents,
        }

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Unable to retrieve incidents",
        )

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


# -------------------------
# RESOLVE INCIDENT
# -------------------------

@app.patch("/api/v1/incidents/{incident_id}/resolve")
def resolve_incident(
    incident_id: int,
    current_user: dict = Depends(require_role("analyst")),
):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        query = """
            UPDATE incidents
            SET
                status = 'resolved',
                resolved_at = CURRENT_TIMESTAMP
            WHERE id = %s
              AND status = 'open'
            RETURNING
                id,
                instance_id,
                incident_type,
                severity,
                title,
                status,
                detected_at,
                resolved_at;
        """

        cursor.execute(query, (incident_id,))
        row = cursor.fetchone()

        if row is None:
            connection.rollback()
            raise HTTPException(
                status_code=404,
                detail="Open incident not found",
            )

        IncidentReplay.record_event(
            connection,
            incident_id,
            "incident_resolved",
            "Incident manually resolved by an authorized user",
            {"resolved_by": current_user["username"]},
        )
        connection.commit()

        return {
            "status": "success",
            "message": "Incident resolved successfully",
            "incident": {
                "id": row[0],
                "instance_id": row[1],
                "incident_type": row[2],
                "severity": row[3],
                "title": row[4],
                "status": row[5],
                "detected_at": row[6].isoformat(),
                "resolved_at": row[7].isoformat(),
            },
        }

    except HTTPException:
        raise

    except Exception:
        if connection is not None:
            connection.rollback()

        raise HTTPException(
            status_code=503,
            detail="Unable to resolve incident",
        )

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


# -------------------------
# INCIDENT ACKNOWLEDGEMENT
# -------------------------

@app.patch("/api/v1/incidents/{incident_id}/acknowledge")
def acknowledge_incident(
    incident_id: int,
    current_user: dict = Depends(require_role("analyst")),
):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE incidents
            SET acknowledged_at = CURRENT_TIMESTAMP, acknowledged_by = %s
            WHERE id = %s AND status = 'open' AND acknowledged_at IS NULL
            RETURNING id, instance_id, severity, title, acknowledged_at, acknowledged_by;
            """,
            (current_user["username"], incident_id),
        )
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                "SELECT id, status, acknowledged_at, acknowledged_by FROM incidents WHERE id = %s;",
                (incident_id,),
            )
            existing = cursor.fetchone()
            if existing is None:
                raise HTTPException(status_code=404, detail="Incident not found")
            if existing[1] != "open":
                raise HTTPException(status_code=409, detail="Resolved incidents cannot be acknowledged")
            return {
                "status": "already_acknowledged",
                "incident_id": incident_id,
                "acknowledged_at": existing[2].isoformat() if existing[2] else None,
                "acknowledged_by": existing[3],
            }

        IncidentReplay.record_event(
            connection,
            incident_id,
            "incident_acknowledged",
            "Incident acknowledged by an authorized user",
            {"acknowledged_by": current_user["username"]},
        )
        connection.commit()
        return {
            "status": "success",
            "incident": {
                "id": row[0],
                "instance_id": row[1],
                "severity": row[2],
                "title": row[3],
                "acknowledged_at": row[4].isoformat(),
                "acknowledged_by": row[5],
            },
        }
    except HTTPException:
        if connection is not None:
            connection.rollback()
        raise
    except Exception:
        if connection is not None:
            connection.rollback()
        logger.exception("Incident acknowledgement failed")
        raise HTTPException(status_code=503, detail="Unable to acknowledge incident")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


# -------------------------
# CONFIGURABLE THRESHOLDS
# -------------------------

@app.get("/api/v1/settings/thresholds")
def get_threshold_settings():
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        thresholds = load_thresholds(cursor)
        return {"thresholds": thresholds}
    except Exception:
        logger.exception("Threshold settings could not be loaded")
        raise HTTPException(status_code=503, detail="Unable to retrieve threshold settings")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


@app.put("/api/v1/settings/thresholds")
def update_threshold_settings(
    request: ThresholdRequest,
    current_user: dict = Depends(require_role("admin")),
):
    values = request.model_dump()
    for metric in ("cpu", "memory", "disk"):
        if values[f"{metric}_warning"] >= values[f"{metric}_critical"]:
            raise HTTPException(
                status_code=422,
                detail=f"{metric.title()} warning threshold must be below its critical threshold.",
            )
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        for metric in ("cpu", "memory", "disk"):
            cursor.execute(
                """
                INSERT INTO monitoring_thresholds
                    (metric_name, warning_threshold, critical_threshold, updated_at, updated_by)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s)
                ON CONFLICT (metric_name) DO UPDATE SET
                    warning_threshold = EXCLUDED.warning_threshold,
                    critical_threshold = EXCLUDED.critical_threshold,
                    updated_at = CURRENT_TIMESTAMP,
                    updated_by = EXCLUDED.updated_by;
                """,
                (
                    metric,
                    values[f"{metric}_warning"],
                    values[f"{metric}_critical"],
                    current_user["username"],
                ),
            )
        connection.commit()
        return {"status": "success", "thresholds": load_thresholds(cursor)}
    except HTTPException:
        if connection is not None:
            connection.rollback()
        raise
    except Exception:
        if connection is not None:
            connection.rollback()
        logger.exception("Threshold settings could not be saved")
        raise HTTPException(status_code=503, detail="Unable to save threshold settings")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


# -------------------------
# INSTANCE INVENTORY
# -------------------------

@app.get("/api/v1/instances")
def list_instances():
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                latest.instance_id,
                latest.timestamp,
                latest.cpu_usage_percent,
                latest.memory_usage_percent,
                latest.disk_usage_percent,
                (SELECT COUNT(*) FROM system_metrics sm WHERE sm.instance_id = latest.instance_id) AS sample_count,
                (SELECT COUNT(*) FROM incidents i WHERE i.instance_id = latest.instance_id AND i.status = 'open') AS open_incidents
            FROM (
                SELECT DISTINCT ON (instance_id)
                    instance_id, timestamp, cpu_usage_percent,
                    memory_usage_percent, disk_usage_percent
                FROM system_metrics
                ORDER BY instance_id, timestamp DESC
            ) AS latest
            ORDER BY latest.instance_id;
            """
        )
        instances = [
            {
                "instance_id": row[0],
                "last_seen": row[1].isoformat(),
                "cpu_usage_percent": float(row[2]),
                "memory_usage_percent": float(row[3]),
                "disk_usage_percent": float(row[4]),
                "sample_count": int(row[5]),
                "open_incidents": int(row[6]),
            }
            for row in cursor.fetchall()
        ]
        return {"count": len(instances), "instances": instances}
    except Exception:
        logger.exception("Instance inventory could not be loaded")
        raise HTTPException(status_code=503, detail="Unable to retrieve instances")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


# -------------------------
# NOTIFICATION DELIVERY HISTORY
# -------------------------

@app.get("/api/v1/notifications")
def get_notification_history(limit: int = Query(default=30, ge=1, le=100)):
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT id, incident_id, instance_id, channel, status,
                   provider_reference, details, created_at
            FROM notification_history
            ORDER BY created_at DESC
            LIMIT %s;
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return {
            "count": len(rows),
            "notifications": [
                {
                    "id": row[0],
                    "incident_id": row[1],
                    "instance_id": row[2],
                    "channel": row[3],
                    "status": row[4],
                    "provider_reference": row[5],
                    "details": row[6] or {},
                    "created_at": row[7].isoformat(),
                }
                for row in rows
            ],
        }
    except Exception:
        logger.exception("Notification history could not be loaded")
        raise HTTPException(status_code=503, detail="Unable to retrieve notification history")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


# -------------------------
# DASHBOARD SUMMARY
# -------------------------

@app.get("/api/v1/dashboard/summary")
def dashboard_summary(
    instance_id: str | None = Query(default=None, min_length=1, max_length=255),
):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        metrics_query = """
            SELECT
                instance_id, cpu_usage_percent, memory_usage_percent,
                disk_usage_percent, latency_ms, error_rate_percent,
                request_rate, timestamp
            FROM system_metrics
        """
        query_params = ()
        if instance_id:
            metrics_query += " WHERE instance_id = %s"
            query_params = (instance_id,)
        metrics_query += " ORDER BY timestamp DESC LIMIT 1;"
        cursor.execute(metrics_query, query_params)
        latest_metrics = cursor.fetchone()

        if instance_id:
            cursor.execute(
                "SELECT COUNT(*) FROM incidents WHERE status = 'open' AND instance_id = %s;",
                (instance_id,),
            )
        else:
            cursor.execute("SELECT COUNT(*) FROM incidents WHERE status = 'open';")
        open_incidents = cursor.fetchone()[0]

        if instance_id:
            cursor.execute("SELECT COUNT(*) FROM incidents WHERE instance_id = %s;", (instance_id,))
        else:
            cursor.execute("SELECT COUNT(*) FROM incidents;")
        total_incidents = cursor.fetchone()[0]
        latest_anomaly = None
        cursor.execute("SAVEPOINT dashboard_anomaly_query")
        try:
            anomaly_query = """
                SELECT metric_id, is_anomaly, anomaly_score, model_version, detected_at
                FROM anomaly_detections
            """
            anomaly_params = ()
            if instance_id:
                anomaly_query += " WHERE instance_id = %s"
                anomaly_params = (instance_id,)
            anomaly_query += " ORDER BY detected_at DESC LIMIT 1;"
            cursor.execute(anomaly_query, anomaly_params)
            latest_anomaly = cursor.fetchone()
            cursor.execute("RELEASE SAVEPOINT dashboard_anomaly_query")
        except Exception:
            cursor.execute("ROLLBACK TO SAVEPOINT dashboard_anomaly_query")
            cursor.execute("RELEASE SAVEPOINT dashboard_anomaly_query")
            logger.exception(
                "Could not read anomaly_detections; returning dashboard summary without latest ML result"
            )

        if latest_metrics is None:
            raise HTTPException(
                status_code=404,
                detail="No metrics available"
            )

        return {
            "instance_id": latest_metrics[0],
            "latest_metrics": {
                "cpu_usage_percent": float(latest_metrics[1]),
                "memory_usage_percent": float(latest_metrics[2]),
                "disk_usage_percent": float(latest_metrics[3]),
                "latency_ms": float(latest_metrics[4]) if latest_metrics[4] is not None else None,
                "error_rate_percent": float(latest_metrics[5]) if latest_metrics[5] is not None else None,
                "request_rate": float(latest_metrics[6]) if latest_metrics[6] is not None else None,
                "timestamp": latest_metrics[7].isoformat(),
            },
            "incidents": {
                "open": open_incidents,
                "total": total_incidents,
            },
            "ml_detection": {
                "is_trained": ml_service.is_trained,
                "model_version": ml_service.model_version,
                "model_type": "IsolationForest",
                "latest": (
                    {
                        "metric_id": latest_anomaly[0],
                        "is_anomaly": latest_anomaly[1],
                        "anomaly_score": float(latest_anomaly[2]),
                        "detected_at": latest_anomaly[4].isoformat(),
                    }
                    if latest_anomaly is not None
                    else None
                ),
            },

        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Dashboard summary query failed")
        raise HTTPException(
            status_code=503,
            detail="Unable to retrieve dashboard summary",
        )

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


# -------------------------
# COST / RESOURCE UTILIZATION RECOMMENDATIONS
# -------------------------

@app.get("/api/v1/cost/recommendations")
def cost_recommendations(
    days: int = Query(default=7, ge=1, le=30),
    cpu_threshold: float = Query(default=10.0, ge=0, le=100),
    memory_threshold: float = Query(default=50.0, ge=0, le=100),
):
    """Identify consistently underutilized instances from stored metric history."""
    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                instance_id,
                COUNT(*) AS sample_count,
                AVG(cpu_usage_percent) AS average_cpu,
                MAX(cpu_usage_percent) AS peak_cpu,
                AVG(memory_usage_percent) AS average_memory,
                MAX(memory_usage_percent) AS peak_memory
            FROM system_metrics
            WHERE timestamp >= NOW() - (%s * INTERVAL '1 day')
            GROUP BY instance_id
            ORDER BY instance_id;
            """,
            (days,),
        )
        recommendations = build_utilization_recommendations(
            cursor.fetchall(),
            cpu_threshold=cpu_threshold,
            memory_threshold=memory_threshold,
        )
        return {
            "window_days": days,
            "cpu_threshold_percent": cpu_threshold,
            "memory_threshold_percent": memory_threshold,
            "recommendations": recommendations,
            "pricing_note": (
                "Dollar savings are not estimated because live AWS pricing data "
                "and resource purchase terms are not configured."
            ),
        }
    except Exception:
        logger.exception("Cost recommendation query failed")
        raise HTTPException(
            status_code=503,
            detail="Unable to calculate resource utilization recommendations",
        )
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


# ============================
# PRIORITY 1 FEATURES
# ============================

from app.main_extensions import (
    register_auth_routes,
    register_incident_replay_routes,
    register_ml_routes,
    register_remediation_routes,
)

register_auth_routes(app, ml_service)
register_incident_replay_routes(app)
register_ml_routes(app, ml_service)

register_remediation_routes(app)
