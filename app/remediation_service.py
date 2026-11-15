"""Controlled remediation for CloudPulse Sentinel."""
from datetime import datetime, timezone
import os
import re

import boto3
from psycopg2.extras import Json

ALLOWED_ACTIONS = {
    "reboot_instance": "Reboot the affected EC2 instance (causes brief downtime)",
}
FORBIDDEN_ACTIONS = {
    "terminate_instance", "delete_database", "delete_snapshot", "detach_volume",
    "delete_iam_role", "delete_iam_user", "delete_s3_bucket", "delete_security_group",
}


class RemediationService:
    def __init__(self, ec2_client=None):
        self._ec2_client = ec2_client

    @property
    def ec2(self):
        if self._ec2_client is None:
            self._ec2_client = boto3.client(
                "ec2", region_name=os.getenv("AWS_REGION", "us-east-1")
            )
        return self._ec2_client

    def execute_remediation(self, connection, incident_id: int, action: str, approved_by: str) -> dict:
        if action in FORBIDDEN_ACTIONS:
            raise ValueError(f"Action {action} is forbidden (destructive).")
        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"Action {action} is not allowed or implemented.")
        if not approved_by or not approved_by.strip():
            raise ValueError("Authenticated approver identity is required.")

        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT instance_id, status FROM incidents WHERE id = %s FOR UPDATE;",
                (incident_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Incident {incident_id} not found.")
            instance_id, incident_status = row
            if incident_status != "open":
                raise ValueError("Remediation is only allowed for open incidents.")
            if action == "reboot_instance" and not re.fullmatch(r"i-[0-9a-f]{8,17}", str(instance_id)):
                raise ValueError("Incident does not reference a valid EC2 instance ID.")

            try:
                if action == "reboot_instance":
                    self.ec2.reboot_instances(InstanceIds=[instance_id])
                result = {
                    "status": "success",
                    "message": ALLOWED_ACTIONS[action],
                    "details": f"Requested {action} for {instance_id}",
                }
                audit_status = "success"
            except Exception as exc:
                result = {
                    "status": "failed",
                    "message": "AWS rejected or could not complete the remediation request.",
                    "error_type": type(exc).__name__,
                }
                audit_status = "failed"

            cursor.execute(
                """
                INSERT INTO remediation_actions
                    (incident_id, action, approved_by, executed_at, result, status)
                VALUES (%s, %s, %s, %s, %s, %s);
                """,
                (incident_id, action, approved_by.strip(), datetime.now(timezone.utc),
                 Json(result), audit_status),
            )
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
