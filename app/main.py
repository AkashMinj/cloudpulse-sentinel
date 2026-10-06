
import os
import time
from collections import deque
from threading import Lock
import urllib.request
from datetime import datetime, timedelta, timezone

import psycopg2
import psutil
from app.incident_engine import detect_incidents
from app.sqs_publisher import publish_metric_event
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
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel

app = FastAPI(
    title="CloudPulse Sentinel",
    version="0.8.0",
)

# Initialize ML service
ml_service = MLAnomalyService()
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


# -------------------------
# SYSTEM METRICS COLLECTION
# -------------------------

def collect_system_metrics():
    token = get_metadata_token()

    instance_id = get_instance_metadata(
        "instance-id", token
    )

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
        "version": "0.8.0",
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
                # Automatically resolve incidents when metrics return to normal
        resolution_checks = [
            {
                "incident_type": "high_cpu",
                "value": metrics["cpu_usage_percent"],
                "threshold": 80,
            },
            {
                "incident_type": "high_memory",
                "value": metrics["memory_usage_percent"],
                "threshold": 80,
            },
            {
                "incident_type": "high_disk",
                "value": metrics["disk_usage_percent"],
                "threshold": 80,
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
                      AND status = 'open';
                """

                cursor.execute(
                    resolve_query,
                    (
                        metrics["instance_id"],
                        check["incident_type"],
                    ),
                )

        # Detect incidents from collected metrics
        incidents = detect_incidents(metrics)

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

        except Exception as ml_error:
            cursor.execute("ROLLBACK TO SAVEPOINT ml_anomaly_detection")
            cursor.execute("RELEASE SAVEPOINT ml_anomaly_detection")
            print(f"ML detection error: {ml_error}", flush=True)

        connection.commit()
        publish_metric_event(metrics)
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
# METRICS HISTORY
# -------------------------

@app.get("/api/v1/metrics/history")
def metrics_history(
    limit: int = Query(default=20, ge=1, le=100)
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
            ORDER BY timestamp DESC
            LIMIT %s;
        """

        cursor.execute(query, (limit,))
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
    status: str | None = Query(default=None)
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
                created_at
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
def resolve_incident(incident_id: int):
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
# DASHBOARD SUMMARY
# -------------------------

@app.get("/api/v1/dashboard/summary")
def dashboard_summary():
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                instance_id,
                cpu_usage_percent,
                memory_usage_percent,
                disk_usage_percent,
                latency_ms,
                error_rate_percent,
                request_rate,
                timestamp
            FROM system_metrics
            ORDER BY timestamp DESC
            LIMIT 1;
        """)

        latest_metrics = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*)
            FROM incidents
            WHERE status = 'open';
        """)

        open_incidents = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*)
            FROM incidents;
        """)

        total_incidents = cursor.fetchone()[0]
        cursor.execute("""
            SELECT
                metric_id,
                is_anomaly,
                anomaly_score,
                model_version,
                detected_at
            FROM anomaly_detections
            ORDER BY detected_at DESC
            LIMIT 1;
        """)

        latest_anomaly = cursor.fetchone()

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
        raise HTTPException(
            status_code=503,
            detail="Unable to retrieve dashboard summary",
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
)

register_auth_routes(app, ml_service)
register_incident_replay_routes(app)
register_ml_routes(app, ml_service)
