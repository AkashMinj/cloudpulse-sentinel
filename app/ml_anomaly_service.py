"""
ML Anomaly Service - Integrates ML anomaly detection with incident engine.
"""

from datetime import datetime, timezone
from typing import Optional, Dict
import psycopg2
from psycopg2.extras import Json
from app.anomaly_detector import ResourceAnomalyDetector, AnomalyResult


class MLAnomalyService:
    """Service for ML-based anomaly detection and integration."""

    def __init__(self):
        self.detector = ResourceAnomalyDetector(contamination=0.05, random_state=42)
        self.is_trained = False
        self.model_version = "1.0.0"

    def train_model(self, connection) -> Dict:
        """
        Train the anomaly detection model using historical metrics.

        Args:
            connection: Database connection

        Returns:
            Training summary
        """
        cursor = connection.cursor()

        try:
            # Fetch historical metrics for training
            query = """
                SELECT
                    cpu_usage_percent,
                    memory_usage_percent,
                    disk_usage_percent
                FROM system_metrics
                WHERE timestamp > NOW() - INTERVAL '7 days'
                ORDER BY timestamp DESC
                LIMIT 1000;
            """

            cursor.execute(query)
            rows = cursor.fetchall()

            if len(rows) < 10:
                return {
                    "status": "insufficient_data",
                    "message": "Need at least 10 samples for training",
                    "samples": len(rows),
                }

            # Convert to list of dicts
            metrics = [
                {
                    "cpu_usage_percent": float(row[0]),
                    "memory_usage_percent": float(row[1]),
                    "disk_usage_percent": float(row[2]),
                }
                for row in rows
            ]

            # Train the model
            self.detector.fit(metrics)
            self.is_trained = True

            return {
                "status": "success",
                "message": "Model trained successfully",
                "samples": len(metrics),
                "model_version": self.model_version,
            }

        finally:
            cursor.close()

    def detect_anomaly(
        self,
        connection,
        metrics: dict,
        metric_id: Optional[int] = None,
    ) -> Optional[AnomalyResult]:
        """
        Detect anomaly in current metrics and store result.

        Args:
            connection: Database connection
            metrics: Current metric values
            metric_id: ID of the metric record

        Returns:
            AnomalyResult or None if model not trained
        """
        if not self.is_trained:
            return None

        cursor = connection.cursor()

        try:
            # Predict anomaly
            result = self.detector.predict({
                "cpu_usage_percent": metrics["cpu_usage_percent"],
                "memory_usage_percent": metrics["memory_usage_percent"],
                "disk_usage_percent": metrics["disk_usage_percent"],
            })

            # Store anomaly detection result
            query = """
                INSERT INTO anomaly_detections (
                    instance_id,
                    metric_id,
                    is_anomaly,
                    anomaly_score,
                    model_version,
                    features,
                    detected_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """

            features = {
                "cpu_usage_percent": metrics["cpu_usage_percent"],
                "memory_usage_percent": metrics["memory_usage_percent"],
                "disk_usage_percent": metrics["disk_usage_percent"],
            }

            cursor.execute(
                query,
                (
                    metrics["instance_id"],
                    metric_id,
                    result.is_anomaly,
                    result.anomaly_score,
                    self.model_version,
                    Json(features),
                    datetime.now(timezone.utc),
                ),
            )

            return result

        finally:
            cursor.close()

    def get_anomaly_signals(self, metrics: dict) -> list:
        """
        Generate human-readable anomaly signals.

        Args:
            metrics: Current metric values

        Returns:
            List of signal descriptions
        """
        signals = []

        if metrics.get("cpu_usage_percent", 0) > 80:
            signals.append("High CPU usage")

        if metrics.get("memory_usage_percent", 0) > 80:
            signals.append("High memory usage")

        if metrics.get("disk_usage_percent", 0) > 80:
            signals.append("High disk usage")

        if metrics.get("latency_ms") and metrics["latency_ms"] > 500:
            signals.append("Elevated latency")

        if metrics.get("error_rate_percent") and metrics["error_rate_percent"] > 5:
            signals.append("Increased error rate")

        return signals

    def create_anomaly_incident(
        self,
        connection,
        metrics: dict,
        anomaly_result: AnomalyResult,
        metric_id: int,
    ) -> Optional[int]:
        """
        Create an incident from ML-detected anomaly.

        Args:
            connection: Database connection
            metrics: Current metrics
            anomaly_result: Anomaly detection result
            metric_id: ID of the metric

        Returns:
            Incident ID or None
        """
        if not anomaly_result.is_anomaly:
            return None

        cursor = connection.cursor()

        try:
            # Check if anomaly incident already exists
            duplicate_check = """
                SELECT id
                FROM incidents
                WHERE instance_id = %s
                  AND incident_type = 'ml_anomaly'
                  AND status = 'open'
                LIMIT 1;
            """

            cursor.execute(duplicate_check, (metrics["instance_id"],))

            if cursor.fetchone():
                return None  # Already have an open anomaly incident

            # Create anomaly incident
            signals = self.get_anomaly_signals(metrics)

            # Calculate severity based on anomaly score
            # More negative score = more anomalous
            if anomaly_result.anomaly_score < -0.5:
                severity = "critical"
            elif anomaly_result.anomaly_score < -0.3:
                severity = "warning"
            else:
                severity = "info"

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

            description = f"ML model detected anomalous behavior. Anomaly score: {anomaly_result.anomaly_score:.4f}."
            if signals:
                description += f" Signals: {', '.join(signals)}."

            cursor.execute(
                incident_query,
                (
                    metrics["instance_id"],
                    metric_id,
                    "ml_anomaly",
                    severity,
                    "ML Anomaly Detected",
                    description,
                    abs(anomaly_result.anomaly_score * 100),  # Convert to 0-100 scale
                    0.0,  # No specific threshold for ML anomaly
                    datetime.now(timezone.utc),
                ),
            )

            incident_id = cursor.fetchone()[0]

            return incident_id

        finally:
            cursor.close()
