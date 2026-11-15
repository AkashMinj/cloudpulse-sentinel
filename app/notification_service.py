"""Optional SNS, SMTP email and Slack incident notifications."""

import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage


class NotificationService:
    def __init__(self, sns_client=None, topic_arn=None):
        self.topic_arn = (
            topic_arn if topic_arn is not None
            else os.getenv("CLOUDPULSE_SNS_TOPIC_ARN")
        )
        self._sns_client = sns_client

    def notify_incident(self, incident: dict) -> dict:
        """Publish the incident to SNS. Kept compatible with the original API."""
        if not self.topic_arn:
            return {"status": "skipped", "reason": "SNS topic is not configured."}
        try:
            if self._sns_client is None:
                import boto3
                self._sns_client = boto3.client(
                    "sns", region_name=os.getenv("AWS_REGION", "us-east-1")
                )
            title = str(incident.get("title", "CloudPulse incident"))[:100]
            payload = self._payload(incident)
            response = self._sns_client.publish(
                TopicArn=self.topic_arn,
                Subject=f"[CloudPulse] {title}"[:100],
                Message=json.dumps(payload, default=str),
            )
            return {"status": "sent", "message_id": response.get("MessageId")}
        except Exception as exc:
            return {"status": "failed", "error_type": type(exc).__name__}

    def notify_email(self, incident: dict) -> dict:
        """Send email when SMTP settings and at least one recipient are configured."""
        host = os.getenv("SMTP_HOST")
        recipients = [item.strip() for item in os.getenv("SMTP_TO", "").split(",") if item.strip()]
        sender = os.getenv("SMTP_FROM")
        if not host or not recipients or not sender:
            return {"status": "skipped", "reason": "SMTP is not fully configured."}
        try:
            message = EmailMessage()
            message["Subject"] = f"[CloudPulse {str(incident.get('severity', 'info')).upper()}] {incident.get('title', 'Incident')}"[:180]
            message["From"] = sender
            message["To"] = ", ".join(recipients)
            message.set_content(self._format_text(incident))

            port = int(os.getenv("SMTP_PORT", "587"))
            timeout = float(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))
            with smtplib.SMTP(host, port, timeout=timeout) as smtp:
                if os.getenv("SMTP_STARTTLS", "true").lower() in {"1", "true", "yes"}:
                    smtp.starttls()
                username = os.getenv("SMTP_USERNAME")
                password = os.getenv("SMTP_PASSWORD")
                if username:
                    smtp.login(username, password or "")
                smtp.send_message(message)
            return {"status": "sent", "recipient_count": len(recipients)}
        except Exception as exc:
            return {"status": "failed", "error_type": type(exc).__name__}

    def notify_slack(self, incident: dict) -> dict:
        """Post an incident summary to an incoming Slack webhook."""
        webhook = os.getenv("SLACK_WEBHOOK_URL")
        if not webhook:
            return {"status": "skipped", "reason": "Slack webhook is not configured."}
        try:
            payload = {
                "text": self._format_text(incident),
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"*CloudPulse {str(incident.get('severity', 'info')).upper()}*\n"
                                f"*{incident.get('title', 'Incident')}*\n"
                                f"{incident.get('description', '')}\n"
                                f"Instance: `{incident.get('instance_id', 'unknown')}`"
                            )[:2900],
                        },
                    }
                ],
            }
            body = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                webhook,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"Slack returned HTTP {response.status}")
            return {"status": "sent"}
        except Exception as exc:
            return {"status": "failed", "error_type": type(exc).__name__}

    @staticmethod
    def _payload(incident: dict) -> dict:
        return {
            "event": "incident_created",
            "incident_id": incident.get("id"),
            "instance_id": incident.get("instance_id"),
            "incident_type": incident.get("incident_type"),
            "severity": incident.get("severity"),
            "title": str(incident.get("title", "CloudPulse incident"))[:100],
            "description": incident.get("description"),
            "detected_at": str(incident.get("detected_at")),
        }

    @staticmethod
    def _format_text(incident: dict) -> str:
        return (
            f"CloudPulse {str(incident.get('severity', 'info')).upper()} incident\n"
            f"{incident.get('title', 'Incident')}\n"
            f"{incident.get('description', '')}\n"
            f"Instance: {incident.get('instance_id', 'unknown')}\n"
            f"Metric: {incident.get('metric_value', 'n/a')} / "
            f"{incident.get('threshold_value', 'n/a')}\n"
            f"Detected: {incident.get('detected_at', 'unknown')}"
        )
