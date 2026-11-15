# CloudPulse Sentinel API Reference

Interactive OpenAPI documentation: `http://localhost:8000/docs`.

The dashboard reads telemetry and incident data without a user session. State-changing actions require a JWT. Remote agents use a separate ingest token.

## Monitoring and inventory

| Method | Endpoint | Purpose | Access |
|---|---|---|---|
| GET | `/health` | Liveness check | Public |
| GET | `/api/v1/db/health` | Database readiness | Public |
| GET | `/api/v1/instance` | EC2 metadata when available; local fallback otherwise | Public |
| GET | `/api/v1/metrics` | Current host metrics | Public |
| POST | `/api/v1/metrics/collect` | Collect and persist backend/container metrics | Local collector/demo; restrict network exposure in production |
| POST | `/api/v1/metrics/ingest` | Persist telemetry sent by a remote instance agent | `X-Metrics-Token` header |
| GET | `/api/v1/metrics/history?limit=120&instance_id=<id>` | Historical metrics; optional instance filter | Read-only |
| GET | `/api/v1/instances` | Latest telemetry and incident counts grouped by instance | Read-only |
| GET | `/api/v1/dashboard/summary?instance_id=<id>` | Dashboard KPIs; optional instance filter | Read-only |

Remote ingest is disabled unless `METRICS_INGEST_TOKEN` is configured with at least 32 characters. Configure the same token on the backend and each remote agent. `scripts/instance_agent.py` collects host-level metrics and sends them to the ingest endpoint.

## Incidents and notifications

| Method | Endpoint | Purpose | Access |
|---|---|---|---|
| GET | `/api/v1/incidents?limit=100&severity=critical&status=open&instance_id=<id>` | Incident list and filters | Read-only |
| GET | `/api/v1/incidents/{id}/replay` | Incident and event timeline | Read-only (optional JWT accepted) |
| GET | `/api/v1/incidents/{id}/events` | Incident event list | Read-only (optional JWT accepted) |
| PATCH | `/api/v1/incidents/{id}/acknowledge` | Acknowledge an open incident and add timeline event | Analyst or higher |
| PATCH | `/api/v1/incidents/{id}/resolve` | Resolve an open incident and add timeline event | Analyst or higher |
| GET | `/api/v1/notifications?limit=30` | Provider delivery attempts and status | Read-only |

## Settings, ML and cost analysis

| Method | Endpoint | Purpose | Access |
|---|---|---|---|
| GET | `/api/v1/settings/thresholds` | Current CPU, memory and disk warning/critical thresholds | Read-only |
| PUT | `/api/v1/settings/thresholds` | Update six threshold values | Admin only |
| POST | `/api/v1/ml/train` | Train model from stored metrics | Analyst or higher |
| GET | `/api/v1/ml/status` | Model status, version, sample count, training time and detection counts | Read-only |
| GET | `/api/v1/anomalies?limit=30&instance_id=<id>&is_anomaly=true` | Recent anomaly predictions and scores | Read-only |
| GET | `/api/v1/cost/recommendations` | Utilization-based cost recommendations | Read-only |
| POST | `/api/v1/remediate?incident_id=123&action=reboot_instance&confirm=true` | Explicitly confirmed EC2 remediation | Admin only |

Threshold update body:

```json
{
  "cpu_warning": 80,
  "cpu_critical": 95,
  "memory_warning": 80,
  "memory_critical": 95,
  "disk_warning": 80,
  "disk_critical": 95
}
```

Each warning threshold must be lower than its corresponding critical threshold. All values are percentages from 1 to 100.

## Authentication

Obtain a JWT with `POST /api/v1/auth/login` using a JSON body containing `username` and `password`. Send protected requests with `Authorization: Bearer <JWT>`. `GET /api/v1/auth/me` returns the active user's profile. The dashboard keeps its session token in browser `sessionStorage` and clears it on logout.

## Notification configuration

- AWS SNS: `CLOUDPULSE_SNS_TOPIC_ARN` and `AWS_REGION`.
- Email: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TO`, `SMTP_STARTTLS`.
- Slack: `SLACK_WEBHOOK_URL`.

Email is sent for critical incidents only. Unconfigured providers are recorded as `skipped`; provider failures are recorded as `failed`. Delivery history never stores SMTP passwords or Slack webhook URLs.

## Remediation warning

Only EC2 reboot is implemented. It can cause downtime. Do not expose the endpoint publicly; use an admin account and require an explicit confirmation.
