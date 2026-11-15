# Implementation status — uploaded source upgrade

This status describes source-level implementation. It does not claim that the AWS account, SMTP server, Slack workspace or live EC2 fleet has been configured or tested.

| Capability | Source status | Live verification still needed |
|---|---|---|
| CPU, memory, disk metrics | Implemented for local collector and authenticated periodic remote agent | Confirm host agent reports each intended EC2 instance |
| Historical charts and refresh | Implemented in dashboard; 10/15/30-second polling selector | Browser demo with incoming samples |
| Multi-instance inventory/filter | Implemented via instance inventory and filtered history/summary APIs | Report from at least two agents |
| Configurable thresholds | Persistent CPU/memory/disk warning/critical settings; admin-only updates | Change threshold and trigger/recover a test incident |
| Incident workflow | Severity list, details, acknowledgement, resolution and timeline UI/API | Verify analyst/admin login and event timeline |
| Notifications | SNS, SMTP email for critical incidents, Slack webhook, delivery-history table/API/UI | Configure providers and verify actual delivery |
| S3 metrics archive | Optional encrypted S3 uploader | Configure bucket/IAM, verify object exists |
| S3 ML model storage | Optional S3 load/save; local persistent fallback | Configure bucket/IAM and validate load/save |
| SQS/Lambda | Metric event publisher, thresholds included in message, Lambda consumer and Terraform event mapping | Verify queue, Lambda mapping, DLQ and DB connectivity in AWS |
| ML transparency | Status, training sample metadata, score history, normal/anomaly labels and authorized retraining | Retrain on varied data; explain score is not probability |
| Cost intelligence | Historical CPU/memory utilization recommendations | No dollar savings claimed without pricing/billing integration |
| Docker Compose | Backend, Postgres, local collector and dashboard | Rebuild on user's machine; preserve `postgres_data` and `ml_models` |
| Security/CI | JWT/RBAC, non-root container, Jenkins/Trivy scaffolding | Rerun pipeline and review dependency audit |
| HTTPS ingress/secrets manager | Not included end-to-end | Required before public production exposure |

## Important operational notes

- `METRICS_INGEST_TOKEN` must be at least 32 characters. The backend uses constant-time comparison and the remote agent sends it in `X-Metrics-Token`.
- The new runtime migrations are additive and idempotent. They do not delete or recreate user data.
- Email, Slack, SNS, S3 and SQS outcomes are explicitly represented as `sent`, `failed` or `skipped`; a skipped outcome means provider settings are absent.
- Local Docker collection is not EC2 monitoring. EC2 monitoring requires deploying `scripts/instance_agent.py` on each monitored host.
