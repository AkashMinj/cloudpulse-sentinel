# Security and Operations Notes

## Secrets and configuration

- Copy `.env.example` to `.env`; never commit `.env`.
- Generate a unique `JWT_SECRET_KEY` and a separate random `METRICS_INGEST_TOKEN` (at least 32 characters).
- Keep SMTP passwords, Slack webhooks, AWS credentials and private keys outside source control.
- Use least-privilege IAM permissions for EC2, S3, SNS and SQS.
- Treat the locally persisted scikit-learn pickle artifact as trusted input only. Restrict write access to the model volume and S3 object prefix.

## Network exposure

- Keep PostgreSQL on the private Compose network; do not publish port 5432 to the internet.
- Restrict `/api/v1/metrics/collect` to the local collector or trusted network in production.
- Remote agent ingestion requires `X-Metrics-Token`; rotate the shared token if an instance is compromised.
- Put the dashboard and API behind TLS and an authenticated reverse proxy before internet exposure.
- State-changing incident, threshold, retraining and remediation actions use JWT role checks.

## Persistence and recovery

- PostgreSQL uses the existing `cloudpulse-sentinel_postgres_data` volume and model artifacts use `cloudpulse-sentinel_ml_models`. The Compose project name is pinned to preserve these volume names.
- Routine rebuilds use `docker compose up -d --build`; do not run `docker compose down -v` because it deletes persistent volumes.
- Back up PostgreSQL and the ML model volume before changing deployment infrastructure.
- Runtime migrations are additive and idempotent. Review them before production rollout.

## Monitoring limitations

- The bundled local collector reports the backend container/runtime view and labels it `local-docker` when no EC2 instance identity is available.
- Run `scripts/instance_agent.py` under a process supervisor on each remote VM/EC2 instance for periodic per-instance host telemetry (30-second default; minimum 10 seconds).
- The agent currently reports CPU, memory and disk from `psutil`; it is not a CloudWatch agent and does not collect every AWS metric.
- ML anomaly scores are Isolation Forest decision scores, not probabilities. A minimum of three consecutive anomalies is required before an ML anomaly incident is opened.
- AWS, SMTP and Slack delivery require valid provider configuration and must be tested in the target account/environment.
