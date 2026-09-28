from app.incident_engine import detect_incidents


def make_metrics(cpu=10, memory=10, disk=10):
    return {
        "instance_id": "test-instance",
        "cpu_usage_percent": cpu,
        "memory_usage_percent": memory,
        "disk_usage_percent": disk,
    }


def test_no_incidents_below_thresholds():
    incidents = detect_incidents(
        make_metrics(cpu=50, memory=60, disk=70)
    )

    assert incidents == []


def test_cpu_warning_incident():
    incidents = detect_incidents(
        make_metrics(cpu=80)
    )

    assert len(incidents) == 1
    assert incidents[0]["incident_type"] == "high_cpu"
    assert incidents[0]["severity"] == "warning"
    assert incidents[0]["metric_value"] == 80
    assert incidents[0]["threshold_value"] == 80


def test_cpu_critical_incident():
    incidents = detect_incidents(
        make_metrics(cpu=95)
    )

    assert len(incidents) == 1
    assert incidents[0]["incident_type"] == "high_cpu"
    assert incidents[0]["severity"] == "critical"
    assert incidents[0]["metric_value"] == 95
    assert incidents[0]["threshold_value"] == 95


def test_memory_warning_incident():
    incidents = detect_incidents(
        make_metrics(memory=80)
    )

    assert len(incidents) == 1
    assert incidents[0]["incident_type"] == "high_memory"
    assert incidents[0]["severity"] == "warning"


def test_disk_critical_incident():
    incidents = detect_incidents(
        make_metrics(disk=95)
    )

    assert len(incidents) == 1
    assert incidents[0]["incident_type"] == "high_disk"
    assert incidents[0]["severity"] == "critical"


def test_multiple_incidents_are_detected():
    incidents = detect_incidents(
        make_metrics(cpu=95, memory=80, disk=95)
    )

    assert len(incidents) == 3

    incident_types = {
        incident["incident_type"]
        for incident in incidents
    }

    assert incident_types == {
        "high_cpu",
        "high_memory",
        "high_disk",
    }


def test_incident_contains_required_fields():
    incidents = detect_incidents(
        make_metrics(cpu=90)
    )

    incident = incidents[0]

    assert incident["instance_id"] == "test-instance"
    assert incident["incident_type"] == "high_cpu"
    assert incident["severity"] == "warning"
    assert incident["title"] == "CPU usage is high"
    assert incident["metric_value"] == 90
    assert incident["threshold_value"] == 80
    assert "description" in incident
    assert "detected_at" in incident
