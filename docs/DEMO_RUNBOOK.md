# CloudPulse Sentinel — demo runbook

## 1. Start the local environment

```bash
cp .env.example .env
openssl rand -hex 32
vim .env
# Set DB_PASSWORD and JWT_SECRET_KEY. Set METRICS_INGEST_TOKEN if remote agents will be used.
docker compose up -d --build
docker compose ps
docker compose logs -f metrics-collector
```

Open the dashboard at `http://localhost:3001` and the API docs at `http://localhost:8000/docs`.

## 2. Show monitoring

1. Wait for the local collector to add samples, or use **Collect now**.
2. Show the 10–30 second dashboard refresh control.
3. Show CPU, memory and disk history and the monitored instance inventory.
4. Select an instance to scope the summary, chart, incidents and anomaly history.

For a multi-instance demo, configure a secure `METRICS_INGEST_TOKEN` on the backend and run `scripts/instance_agent.py` on a second host using its own `INSTANCE_ID` only when testing outside EC2.

## 3. Show incidents

1. In the dashboard, sign in with the development `analyst` account for acknowledgement/resolution.
2. Open an incident and show its metric value, threshold and timeline.
3. Acknowledge the incident and verify the timeline event.
4. Resolve the incident and confirm the status changes.

Use the admin account for threshold editing. For a controlled threshold demo, lower a warning threshold, collect a new high metric sample, and then restore the original setting.

## 4. Show ML analytics

1. Open ML & Cost.
2. Show model state, training samples, training timestamp and detection counts.
3. If fewer than 10 historical samples exist, wait for collection or add test metrics before retraining.
4. Sign in as analyst/admin and select retrain.
5. Explain that the anomaly score is a decision-function score, not a probability, and that more varied training data is needed for production claims.

## 5. Show provider status

Open Settings and show notification attempts. `skipped` means a provider is not configured; do not present it as a successful live delivery. Configure SMTP, Slack and/or SNS only when credentials and destinations are available.

## Safety

Do not expose `.env`, ingest tokens, SMTP passwords, Slack webhook URLs, AWS credentials or Terraform state in screenshots. Keep the demo local unless the AWS plan and expected cost have been reviewed. The Compose project name is pinned to reuse the existing project volumes; never override it with `-p` and never run `docker compose down -v` on a database with data to preserve.
