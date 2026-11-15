from unittest.mock import Mock

import pytest

from app.remediation_service import RemediationService


class FakeCursor:
    def __init__(self, incident=("i-0123456789abcdef0", "open")):
        self.incident = incident
        self.executed = []
        self.closed = False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self.incident

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, incident=("i-0123456789abcdef0", "open")):
        self.fake_cursor = FakeCursor(incident)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_reboot_requires_open_incident_and_writes_authenticated_approver():
    ec2 = Mock()
    connection = FakeConnection()
    result = RemediationService(ec2_client=ec2).execute_remediation(
        connection, 12, "reboot_instance", "verified-admin"
    )
    assert result["status"] == "success"
    ec2.reboot_instances.assert_called_once_with(InstanceIds=["i-0123456789abcdef0"])
    audit = [item for item in connection.fake_cursor.executed if "INSERT INTO remediation_actions" in item[0]]
    assert len(audit) == 1
    assert audit[0][1][2] == "verified-admin"
    assert connection.committed


def test_closed_incident_cannot_be_remediated():
    connection = FakeConnection(("i-0123456789abcdef0", "resolved"))
    with pytest.raises(ValueError, match="open incidents"):
        RemediationService(ec2_client=Mock()).execute_remediation(
            connection, 12, "reboot_instance", "verified-admin"
        )
    assert connection.rolled_back


def test_unimplemented_action_is_rejected():
    connection = FakeConnection()
    with pytest.raises(ValueError, match="not allowed or implemented"):
        RemediationService(ec2_client=Mock()).execute_remediation(
            connection, 12, "scale_up_demo", "verified-admin"
        )
