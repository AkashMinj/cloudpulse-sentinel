
import os
import urllib.request
from datetime import datetime, timezone

import psycopg2
import psutil
from incident_engine import detect_incidents
from sqs_publisher import publish_metric_event
from fastapi import FastAPI, HTTPException, Query

app = FastAPI(
    title="CloudPulse Sentinel",
    version="0.8.0",
)


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
                disk_free_gb
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
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
                );
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
        connection.commit()

        publish_metric_event({
            **metrics,
            "metric_id": metric_id,
        })

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
                "created_at": row[11].isoformat(),
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
                "timestamp": latest_metrics[4].isoformat(),
            },
            "incidents": {
                "open": open_incidents,
                "total": total_incidents,
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

@app.get("/api/v1/metrics/history")
def metrics_history(limit: int = Query(default=20, ge=1, le=200)):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        query = """
            SELECT
                timestamp,
                cpu_usage_percent,
                memory_usage_percent,
                disk_usage_percent
            FROM system_metrics
            ORDER BY timestamp DESC
            LIMIT %s;
        """

        cursor.execute(query, (limit,))
        rows = cursor.fetchall()

        metrics = []

        for row in reversed(rows):
            metrics.append({
                "timestamp": row[0].isoformat(),
                "cpu_usage_percent": float(row[1]),
                "memory_usage_percent": float(row[2]),
                "disk_usage_percent": float(row[3]),
            })

        return {
            "count": len(metrics),
            "metrics": metrics,
        }

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Unable to retrieve metrics history"
        )

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()
