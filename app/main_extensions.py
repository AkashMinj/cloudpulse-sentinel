"""
Extended API endpoints for CloudPulse Sentinel.
This module contains authentication, ML, and incident replay endpoints.
Import and include these in main.py after testing.
"""

from datetime import datetime, timezone
from typing import Optional

import psycopg2
from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    require_auth,
    require_role,
)
from app.incident_replay import IncidentReplay
from app.ml_anomaly_service import MLAnomalyService


def get_db_connection():
    """Get database connection."""
    import os
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=5,
    )


# ============================
# AUTHENTICATION ENDPOINTS
# ============================

class LoginRequest(BaseModel):
    username: str
    password: str


def register_auth_routes(app, ml_service):
    """Register authentication routes."""

    @app.post("/api/v1/auth/login")
    def login(request: LoginRequest):
        """Authenticate user and return JWT token."""
        user = authenticate_user(request.username, request.password)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        access_token = create_access_token(
            data={"sub": user["username"], "user_id": user["id"]}
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "full_name": user["full_name"],
                "role": user["role"],
            },
        }

    @app.get("/api/v1/auth/me")
    def get_current_user_info(current_user: dict = Depends(require_auth)):
        """Get current authenticated user information."""
        return {
            "id": current_user["id"],
            "username": current_user["username"],
            "email": current_user["email"],
            "full_name": current_user["full_name"],
            "role": current_user["role"],
        }


def register_incident_replay_routes(app):
    """Register incident replay routes."""

    @app.get("/api/v1/incidents/{incident_id}/replay")
    def get_incident_replay(
        incident_id: int,
        current_user: Optional[dict] = Depends(get_current_user)
    ):
        """Get complete incident timeline for replay."""
        connection = None

        try:
            connection = get_db_connection()
            incident = IncidentReplay.get_incident_with_timeline(connection, incident_id)

            if not incident:
                raise HTTPException(status_code=404, detail="Incident not found")

            return incident

        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Unable to retrieve incident replay",
            )
        finally:
            if connection:
                connection.close()

    @app.get("/api/v1/incidents/{incident_id}/events")
    def get_incident_events(
        incident_id: int,
        current_user: Optional[dict] = Depends(get_current_user)
    ):
        """Get all events for an incident."""
        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute("SELECT id FROM incidents WHERE id = %s;", (incident_id,))

            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Incident not found")

            events = IncidentReplay.get_incident_timeline(connection, incident_id)

            return {
                "incident_id": incident_id,
                "event_count": len(events),
                "events": events,
            }

        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Unable to retrieve incident events",
            )
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()


def register_ml_routes(app, ml_service):
    """Register ML anomaly detection routes."""

    @app.post("/api/v1/ml/train")
    def train_ml_model(current_user: dict = Depends(require_role("analyst"))):
        """Train the ML anomaly detection model on historical data."""
        connection = None
        try:
            connection = get_db_connection()
            result = ml_service.train_model(connection)
            if result.get("status") == "insufficient_data":
                raise HTTPException(status_code=400, detail=result)
            return result
        except HTTPException:
            raise
        except Exception:
            import logging
            logging.getLogger("cloudpulse").exception("ML model training failed")
            raise HTTPException(
                status_code=503,
                detail="Unable to train ML model. Check backend logs.",
            )
        finally:
            if connection:
                connection.close()

    @app.get("/api/v1/ml/status")
    def get_ml_status():
        """Get model state, persisted training metadata and detection counts."""
        connection = None
        cursor = None
        result = {
            "is_trained": ml_service.is_trained,
            "model_version": ml_service.model_version,
            "model_type": "IsolationForest",
            "training_samples": ml_service.training_samples,
            "trained_at": ml_service.trained_at,
            "features": [
                "cpu_usage_percent",
                "memory_usage_percent",
                "disk_usage_percent",
            ],
            "detection_count": 0,
            "anomaly_count": 0,
            "latest": None,
        }
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE is_anomaly) FROM anomaly_detections;")
            counts = cursor.fetchone()
            result["detection_count"] = int(counts[0] or 0)
            result["anomaly_count"] = int(counts[1] or 0)
            cursor.execute(
                """
                SELECT instance_id, metric_id, is_anomaly, anomaly_score, model_version, detected_at
                FROM anomaly_detections ORDER BY detected_at DESC LIMIT 1;
                """
            )
            latest = cursor.fetchone()
            if latest:
                result["latest"] = {
                    "instance_id": latest[0],
                    "metric_id": latest[1],
                    "is_anomaly": latest[2],
                    "anomaly_score": float(latest[3]),
                    "model_version": latest[4],
                    "detected_at": latest[5].isoformat(),
                }
        except Exception:
            import logging
            logging.getLogger("cloudpulse").exception("ML status query failed")
            # Status remains useful even when the detection table is unavailable.
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
        return result

    @app.get("/api/v1/anomalies")
    def get_anomalies(
        limit: int = Query(default=20, ge=1, le=100),
        instance_id: Optional[str] = Query(default=None, min_length=1, max_length=255),
        is_anomaly: Optional[bool] = None,
    ):
        """Get recent anomaly detections."""
        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            query = """
                SELECT
                    id, instance_id, metric_id, is_anomaly,
                    anomaly_score, model_version, features, detected_at
                FROM anomaly_detections
            """
            conditions = []
            parameters = []
            if instance_id:
                conditions.append("instance_id = %s")
                parameters.append(instance_id)
            if is_anomaly is not None:
                conditions.append("is_anomaly = %s")
                parameters.append(is_anomaly)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY detected_at DESC LIMIT %s;"
            parameters.append(limit)
            cursor.execute(query, tuple(parameters))
            rows = cursor.fetchall()

            anomalies = []
            for row in rows:
                anomalies.append({
                    "id": row[0],
                    "instance_id": row[1],
                    "metric_id": row[2],
                    "is_anomaly": row[3],
                    "anomaly_score": float(row[4]),
                    "model_version": row[5],
                    "features": row[6],
                    "detected_at": row[7].isoformat(),
                })

            return {"count": len(anomalies), "anomalies": anomalies}

        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Unable to retrieve anomaly data",
            )
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()


# ============================
# REMEDIATION ENDPOINTS
# ============================

from app.remediation_service import RemediationService

remediation_service = RemediationService()


def register_remediation_routes(app):
    """Register remediation routes."""

    @app.post("/api/v1/remediate")
    def execute_remediation(
        incident_id: int,
        action: str,
        confirm: bool = False,
        current_user: dict = Depends(require_role("admin")),
    ):
        """Execute a confirmed remediation action as the authenticated admin."""
        if not confirm:
            raise HTTPException(status_code=400, detail="Explicit confirmation is required (confirm=true).")
        connection = None
        try:
            connection = get_db_connection()
            result = remediation_service.execute_remediation(
                connection, incident_id, action, current_user["username"]
            )
            return result
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            raise HTTPException(
                status_code=503, detail="Unable to execute remediation"
            )
        finally:
            if connection:
                connection.close()
