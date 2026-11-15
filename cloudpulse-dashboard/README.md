# CloudPulse Sentinel Dashboard

Responsive Next.js operations console for CloudPulse Sentinel.

## Setup

```bash
npm ci
cp .env.example .env.local
vim .env.local
npm run dev
```

Set `BACKEND_URL` to the FastAPI service URL. For local development, use `http://localhost:8000` while the backend is reachable locally or through an SSH tunnel. Docker Compose publishes the dashboard at `http://localhost:3001`.

## Dashboard sections

- **Overview:** health indicator, active incidents, monitored instances, historical CPU/memory/disk charts, refresh controls and instance filtering.
- **Incidents:** severity/status filters, event timeline, acknowledgement and resolution actions.
- **ML & Cost:** model version/state, training metadata, anomaly score history and utilization recommendations.
- **Settings:** admin-managed resource thresholds and SNS/email/Slack delivery history.

Read-only views work without signing in. Incident actions and model retraining require an analyst/admin session. Threshold editing requires an admin session.

## Checks

```bash
npm run lint
npm run build
```

The dashboard displays API-backed data. A missing provider integration is shown as skipped/unconfigured rather than simulated as a successful notification.
