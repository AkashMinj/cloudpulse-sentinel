"""
Incident Replay module for CloudPulse Sentinel.
Records and replays incident timelines with detailed event tracking.
"""

from datetime import datetime, timezone
from typing import List, Dict, Optional
import psycopg2
from psycopg2.extras import Json

class IncidentReplay:
    """Handles incident event recording and replay functionality."""

    @staticmethod
    def record_event(
        connection,
        incident_id: int,
        event_type: str,
        event_message: str,
        metadata: Optional[dict] = None,
    ) -> int:
        """
        Record an event in the incident timeline.

        Args:
            connection: Database connection
            incident_id: ID of the incident
            event_type: Type of event (e.g., 'threshold_breach', 'anomaly_detected', 'incident_created')
            event_message: Human-readable event message
            metadata: Optional JSON metadata

        Returns:
            Event ID
        """
        cursor = connection.cursor()

        try:
            query = """
                INSERT INTO incident_events (
                    incident_id,
                    event_type,
                    event_message,
                    metadata,
                    event_timestamp
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
            """

            cursor.execute(
                query,
                (
                    incident_id,
                    event_type,
                    event_message,
                    Json(metadata) if metadata else None,
                    datetime.now(timezone.utc),
                ),
            )

            event_id = cursor.fetchone()[0]
            return event_id

        finally:
            cursor.close()

    @staticmethod
    def get_incident_timeline(connection, incident_id: int) -> List[Dict]:
        """
        Retrieve the complete timeline of events for an incident.

        Args:
            connection: Database connection
            incident_id: ID of the incident

        Returns:
            List of events in chronological order
        """
        cursor = connection.cursor()

        try:
            query = """
                SELECT
                    id,
                    event_type,
                    event_message,
                    metadata,
                    event_timestamp,
                    created_at
                FROM incident_events
                WHERE incident_id = %s
                ORDER BY event_timestamp ASC;
            """

            cursor.execute(query, (incident_id,))
            rows = cursor.fetchall()

            events = []
            for row in rows:
                events.append({
                    "id": row[0],
                    "event_type": row[1],
                    "event_message": row[2],
                    "metadata": row[3],
                    "event_timestamp": row[4].isoformat(),
                    "created_at": row[5].isoformat(),
                })

            return events

        finally:
            cursor.close()

    @staticmethod
    def get_incident_with_timeline(connection, incident_id: int) -> Optional[Dict]:
        """
        Get complete incident details with timeline.

        Args:
            connection: Database connection
            incident_id: ID of the incident

        Returns:
            Incident data with timeline or None if not found
        """
        cursor = connection.cursor()

        try:
            # Get incident details
            incident_query = """
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
                WHERE id = %s;
            """

            cursor.execute(incident_query, (incident_id,))
            incident_row = cursor.fetchone()

            if not incident_row:
                return None

            incident = {
                "id": incident_row[0],
                "instance_id": incident_row[1],
                "metric_id": incident_row[2],
                "incident_type": incident_row[3],
                "severity": incident_row[4],
                "title": incident_row[5],
                "description": incident_row[6],
                "metric_value": float(incident_row[7]),
                "threshold_value": float(incident_row[8]),
                "status": incident_row[9],
                "detected_at": incident_row[10].isoformat(),
                "resolved_at": incident_row[11].isoformat() if incident_row[11] else None,
                "created_at": incident_row[12].isoformat(),
                "timeline": IncidentReplay.get_incident_timeline(connection, incident_id),
            }

            return incident

        finally:
            cursor.close()

    @staticmethod
    def create_incident_with_events(
        connection,
        incident_data: dict,
        initial_events: List[Dict],
    ) -> int:
        """
        Create an incident and record initial events atomically.

        Args:
            connection: Database connection
            incident_data: Incident data dictionary
            initial_events: List of initial events to record

        Returns:
            Incident ID
        """
        cursor = connection.cursor()

        try:
            # Create incident
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
                    incident_data["instance_id"],
                    incident_data.get("metric_id"),
                    incident_data["incident_type"],
                    incident_data["severity"],
                    incident_data["title"],
                    incident_data["description"],
                    incident_data["metric_value"],
                    incident_data["threshold_value"],
                    incident_data["detected_at"],
                ),
            )

            incident_id = cursor.fetchone()[0]

            # Record initial events
            for event in initial_events:
                IncidentReplay.record_event(
                    connection,
                    incident_id,
                    event["event_type"],
                    event["event_message"],
                    event.get("metadata"),
                )

            return incident_id

        finally:
            cursor.close()
