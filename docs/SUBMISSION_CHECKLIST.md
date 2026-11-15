# CloudPulse Sentinel — Submission Checklist

## Before packaging

- [ ] Confirm `.env`, AWS credentials, Slack webhooks, SMTP passwords, private keys and Terraform state are not included.
- [ ] Keep `.env.example` as a template and generate unique local secrets.
- [ ] Confirm `README.md`, `docs/API_REFERENCE.md`, `docs/ARCHITECTURE.md`, `docs/DEMO_RUNBOOK.md` and `docs/IMPLEMENTATION_STATUS.md` are included.
- [ ] Confirm the uploaded ZIP is the latest source tree and contains no virtualenv, `node_modules`, `.next` or cache directories.

## Local verification

- [ ] `python -m compileall -q app scripts tests`
- [ ] `python -m pytest -q`
- [ ] `pip-audit -r app/requirements.txt`
- [ ] `cd cloudpulse-dashboard && npm ci && npm run lint && npm run build`
- [ ] `docker compose config`
- [ ] `docker compose up -d --build` and `docker compose ps`
- [ ] Verify dashboard at `http://localhost:3001`, API docs at `http://localhost:8000/docs` and health at `/health`.
- [ ] Verify the metrics collector writes samples and the dashboard chart refreshes.
- [ ] Verify analyst/admin login, incident acknowledgement/resolution and timeline.
- [ ] Verify threshold update as admin and restore the intended demo values.
- [ ] Verify model status and retraining after at least 10 stored metric samples.

## Optional provider/cloud verification

- [ ] Configure remote-agent ingest token and verify one or more real EC2 agents report distinct instance IDs.
- [ ] Verify SNS subscription delivery, S3 archive writes, S3 model load/save, SQS messages, Lambda processing and DLQ behavior in the intended AWS account.
- [ ] Verify SMTP email and Slack delivery with test destinations.
- [ ] Build `incident_processor.zip` with `scripts/build_lambda_package.sh`, then run `terraform fmt -check -recursive`, `terraform validate` and review `terraform plan` before any apply.
- [ ] Rebuild the current backend image and review a fresh Trivy report.
- [ ] Capture real dashboard screenshots and test output; do not present skipped providers or local Docker metrics as live AWS evidence.

## Safety

- [ ] Keep `.env` out of Git and screenshots.
- [ ] Do not use `docker compose down -v` on a database containing project data.
- [ ] Do not expose the API publicly without TLS, network restrictions, strong secrets and reviewed IAM permissions.
- [ ] Only test EC2 reboot remediation on a disposable instance with explicit approval.
- [ ] Stop billable AWS resources after evidence capture when they are no longer needed.

## Known limitations to disclose

- Local Compose samples reflect the backend container/runtime, not an EC2 host. The per-instance agent must be installed to monitor remote hosts.
- The agent reports CPU, memory and disk using `psutil`; CloudWatch metrics are not currently collected.
- Cost insights are utilization-based recommendations, not a live AWS bill forecast or guaranteed savings estimate.
- Isolation Forest anomaly scores are decision-function scores, not probabilities; a small training dataset is only a demo.
- SNS, S3, SQS, Lambda, SMTP and Slack require live provider configuration and verification.
- The remote agent currently uses one shared ingest token; production deployments should use per-agent identity/credentials.
