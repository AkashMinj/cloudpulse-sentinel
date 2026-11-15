from app.notification_service import NotificationService


class FakeSNS:
    def publish(self, **kwargs):
        self.kwargs = kwargs
        return {"MessageId": "message-123"}


def test_notification_skips_when_topic_missing():
    assert NotificationService(topic_arn="").notify_incident({"id": 1})["status"] == "skipped"


def test_notification_publishes_incident():
    client = FakeSNS()
    result = NotificationService(
        sns_client=client, topic_arn="arn:aws:sns:us-east-1:123:alerts"
    ).notify_incident({"id": 7, "title": "CPU high", "severity": "critical"})
    assert result == {"status": "sent", "message_id": "message-123"}
    assert '"incident_id": 7' in client.kwargs["Message"]


def test_email_skips_without_smtp_configuration(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_TO", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    result = NotificationService(topic_arn="").notify_email({"id": 3})
    assert result["status"] == "skipped"


def test_slack_skips_without_webhook(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    result = NotificationService(topic_arn="").notify_slack({"id": 3})
    assert result["status"] == "skipped"
