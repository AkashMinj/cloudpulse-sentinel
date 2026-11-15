# Validation Results for the Submission Candidate

These checks were performed against the upgraded source tree in the file-processing runtime. They do not prove the application has been deployed or connected to a live AWS account.

| Check | Result | Notes |
|---|---|---|
| Python compileall | Passed | `python -m compileall -q app tests scripts` completed successfully. |
| Pytest suite | Passed with test-runtime stubs | **64 passed**. This runtime lacks the real `psycopg2-binary` and `passlib` packages, so temporary test-only stubs were supplied for import/collection. No live PostgreSQL integration was performed. |
| YAML / Compose structure parse | Passed | `docker-compose.yml` parsed; project name is pinned to `cloudpulse-sentinel`; services are `postgres`, `backend`, `metrics-collector`, and `dashboard`; collector healthcheck is disabled. |
| FastAPI OpenAPI route smoke check | Passed | New monitoring, incident, notification, threshold and ML routes are present; ML training POST is registered exactly once. |
| Lambda packaging script syntax | Passed | `bash -n scripts/build_lambda_package.sh` completed successfully. |
| Dashboard TSX syntax transpile | Passed | TypeScript `transpileModule` parsed the dashboard source. This is not a full Next.js typecheck or production build. |
| Frontend npm install/lint/build | Not run | `node_modules` is not part of the source archive and external package downloads are unavailable in this runtime. |
| Docker build / Compose startup | Not run | Docker CLI/daemon is not available in this runtime. Run the commands in the project README on the target machine. |
| Terraform fmt/validate/plan | Not run | Terraform CLI is not installed in this runtime. Review the plan before any apply. |
| Trivy scan | Not run | Trivy CLI is not installed in this runtime. |
| Live AWS / SNS / S3 / SQS / EC2 agent | Not run | No AWS credentials or live infrastructure actions were used. These paths require the user's AWS account, IAM permissions, Terraform outputs and environment configuration. |
| SMTP / Slack delivery | Not run | Provider credentials/webhook were not supplied; configure them locally and trigger a test incident. |

## Required checks in WSL before submission

```bash
source .venv/bin/activate
python -m compileall -q app tests scripts
python -m pytest -q
pip-audit -r app/requirements.txt

cd cloudpulse-dashboard
npm ci
npm run lint
npm run build

cd ../
docker compose config
docker compose up -d --build
docker compose ps
```

Build the Lambda artifact with `scripts/build_lambda_package.sh` before Terraform validation because the Lambda resource references that ZIP. For Terraform validation, use the commands in `README.md` and inspect the generated plan. Do not run `terraform apply` unless the target AWS account, region, permissions, resources and expected costs have been reviewed.

For this project, local Docker metrics represent the local container/runtime environment. Multiple real instances appear only after installing `scripts/instance_agent.py` on those instances and configuring the shared ingest token. Do not present local data as live EC2 data.
