"""Idempotent runtime schema upgrades for CloudPulse Sentinel."""

import logging

logger = logging.getLogger("cloudpulse.migrations")

MIGRATIONS = (
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ",
    "ALTER TABLE incidents ADD COLUMN IF NOT EXISTS acknowledged_by VARCHAR(100)",
    """
    CREATE TABLE IF NOT EXISTS monitoring_thresholds (
        metric_name VARCHAR(20) PRIMARY KEY CHECK (metric_name IN ('cpu', 'memory', 'disk')),
        warning_threshold NUMERIC(5,2) NOT NULL,
        critical_threshold NUMERIC(5,2) NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_by VARCHAR(100),
        CHECK (warning_threshold >= 1 AND warning_threshold <= 99),
        CHECK (critical_threshold >= 2 AND critical_threshold <= 100),
        CHECK (warning_threshold < critical_threshold)
    )
    """,
    """
    INSERT INTO monitoring_thresholds (metric_name, warning_threshold, critical_threshold)
    VALUES ('cpu', 80, 95), ('memory', 80, 95), ('disk', 80, 95)
    ON CONFLICT (metric_name) DO NOTHING
    """,
    """
    CREATE TABLE IF NOT EXISTS notification_history (
        id BIGSERIAL PRIMARY KEY,
        incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
        instance_id VARCHAR(255),
        channel VARCHAR(30) NOT NULL,
        status VARCHAR(20) NOT NULL,
        provider_reference VARCHAR(255),
        details JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_notification_history_created_at ON notification_history(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_notification_history_incident_id ON notification_history(incident_id)",
    "CREATE INDEX IF NOT EXISTS idx_incidents_acknowledged_at ON incidents(acknowledged_at)",
)


def apply_runtime_migrations(connection) -> None:
    """Apply additive, non-destructive schema upgrades in one transaction."""
    cursor = connection.cursor()
    try:
        for statement in MIGRATIONS:
            cursor.execute(statement)
        connection.commit()
        logger.info("CloudPulse runtime schema migrations are up to date.")
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
