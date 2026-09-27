from datetime import datetime, timezone


# -------------------------
# INCIDENT THRESHOLDS
# -------------------------

THRESHOLDS = {
    "cpu": {
        "warning": 80,
        "critical": 95,
    },
    "memory": {
        "warning": 80,
        "critical": 95,
    },
    "disk": {
        "warning": 80,
        "critical": 95,
    },
}


# -------------------------
# INCIDENT DETECTION
# -------------------------

def detect_incidents(metrics):
    """
    Evaluate system metrics and return detected incidents.
    """

    incidents = []

    checks = [
        {
            "type": "high_cpu",
            "metric_name": "CPU usage",
            "value": metrics["cpu_usage_percent"],
            "thresholds": THRESHOLDS["cpu"],
        },
        {
            "type": "high_memory",
            "metric_name": "Memory usage",
            "value": metrics["memory_usage_percent"],
            "thresholds": THRESHOLDS["memory"],
        },
        {
            "type": "high_disk",
            "metric_name": "Disk usage",
            "value": metrics["disk_usage_percent"],
            "thresholds": THRESHOLDS["disk"],
        },
    ]

    for check in checks:
        value = float(check["value"])
        thresholds = check["thresholds"]

        if value >= thresholds["critical"]:
            severity = "critical"
            threshold = thresholds["critical"]

        elif value >= thresholds["warning"]:
            severity = "warning"
            threshold = thresholds["warning"]

        else:
            continue

        incidents.append({
            "instance_id": metrics["instance_id"],
            "incident_type": check["type"],
            "severity": severity,
            "title": f"{check['metric_name']} is high",
            "description": (
                f"{check['metric_name']} reached "
                f"{value:.2f}%, exceeding the "
                f"{threshold}% threshold."
            ),
            "metric_value": value,
            "threshold_value": threshold,
            "detected_at": datetime.now(timezone.utc),
        })

    return incidents
