pipeline {
    agent any

    parameters {
        booleanParam(name: 'DEPLOY_TO_EC2', defaultValue: false, description: 'Deploy the backend to EC2 after validation and security scanning.')
        string(name: 'EC2_HOST', defaultValue: '', description: 'EC2 public DNS name or IP. Required only when deployment is enabled.')
        string(name: 'EC2_USER', defaultValue: 'ec2-user', description: 'SSH user for the deployment host.')
        string(name: 'EC2_PROJECT_DIR', defaultValue: '/home/ec2-user/cloudpulse-sentinel', description: 'Remote directory containing the deployment .env file.')
        string(name: 'EC2_CREDENTIALS_ID', defaultValue: 'cloudpulse-ec2-ssh', description: 'Jenkins SSH credential ID.')
    }

    environment {
        DOCKER_IMAGE = "cloudpulse-backend:ci-${BUILD_NUMBER}"
    }

    stages {

        stage('Clean Workspace') {
            steps {
                deleteDir()
            }
        }

        stage('Checkout') {
            steps {
                checkout([
                    $class: 'GitSCM',
                    branches: [[name: '*/main']],
                    userRemoteConfigs: [[
                        url: 'https://github.com/AkashMinj/cloudpulse-sentinel.git'
                    ]]
                ])
            }
        }

        stage('Validate Python') {
            steps {
                sh '''
                    set -eu
                    python3 --version
                    python3 -m compileall -q app tests
                '''
            }
        }

        stage('Run Tests') {
            steps {
                sh '''
                    set -eu
                    python3 -m venv .venv
                    .venv/bin/python -m pip install --upgrade pip
                    .venv/bin/pip install -r requirements-dev.txt

                    PYTHONPATH="$WORKSPACE" \
                        .venv/bin/pytest -q
                '''
            }
        }

        stage('Security Audit') {
            steps {
                sh '''
                    set -eu
                    .venv/bin/pip-audit
                '''
            }
        }

        stage('Build Lambda Package') {
            steps {
                sh '''
                    set -eu

                    rm -rf build/lambda
                    mkdir -p build/lambda

                    docker run --rm \
                        --user "$(id -u):$(id -g)" \
                        -v "$PWD:/workspace" \
                        -w /workspace \
                        python:3.12-slim \
                        bash -c "
                            set -e
                            pip install --no-cache-dir \
                                -r app/lambda-requirements.txt \
                                -t build/lambda

                            cp app/incident_processor_lambda.py build/lambda/
                            cp app/incident_engine.py build/lambda/
                        "

                    python3 - <<'PY'
import os
import zipfile

root = os.path.abspath("build/lambda")
output = os.path.abspath("build/incident-processor.zip")

with zipfile.ZipFile(
    output,
    "w",
    compression=zipfile.ZIP_DEFLATED,
    compresslevel=9,
) as archive:
    for base, dirs, files in os.walk(root):
        dirs[:] = [
            directory
            for directory in dirs
            if directory not in {"__pycache__", "tests", "test"}
        ]

        for name in files:
            if name.endswith(".pyc") or name == "RECORD":
                continue

            path = os.path.join(base, name)
            archive.write(path, os.path.relpath(path, root))

print(
    f"Created {output}: "
    f"{os.path.getsize(output) / 1024 / 1024:.2f} MB"
)
PY

                    # Terraform expects the ZIP at the repository root.
                    cp build/incident-processor.zip incident_processor.zip

                    ls -lh incident_processor.zip
                '''
            }
        }

        stage('Validate Terraform') {
            steps {
                sh '''
                    set -eu
                    terraform -chdir=infrastructure/terraform fmt -check -recursive
                    terraform -chdir=infrastructure/terraform init -backend=false
                    terraform -chdir=infrastructure/terraform validate
                '''
            }
        }

        stage('Dashboard Checks') {
            steps {
                sh '''
                    set -eu

                    JENKINS_UID="$(id -u)"
                    JENKINS_GID="$(id -g)"

                    docker run --rm \
                        --user "${JENKINS_UID}:${JENKINS_GID}" \
                        -e HOME=/tmp \
                        -e npm_config_cache=/tmp/.npm \
                        -v "$PWD/cloudpulse-dashboard:/workspace" \
                        -w /workspace \
                        node:22-alpine \
                        sh -c "npm ci && npm run lint && npm run build"
                '''
            }
        }


        stage('Docker Build') {
            steps {
                sh '''
                    set -eu
                    docker build \
                        -t "${DOCKER_IMAGE}" \
                        .
                '''
            }
        }


        stage('Container Security Scan') {
            steps {
                sh '''
                    set -eu
                    mkdir -p reports

                    # Preserve the report even when vulnerabilities are found.
                    /usr/bin/trivy image \
                        --scanners vuln \
                        --severity HIGH,CRITICAL \
                        --format json \
                        --output reports/trivy-report.json \
                        "${DOCKER_IMAGE}"

                    # Fail only on CRITICAL findings.
                    /usr/bin/trivy image \
                        --scanners vuln \
                        --severity CRITICAL \
                        --exit-code 1 \
                        "${DOCKER_IMAGE}"

                    # Display HIGH findings for review without blocking.
                    /usr/bin/trivy image \
                        --scanners vuln \
                        --severity HIGH \
                        --exit-code 0 \
                        "${DOCKER_IMAGE}"
                '''
            }
        }


        stage('Deploy Backend to EC2') {
            when {
                expression { params.DEPLOY_TO_EC2 }
            }
            steps {
                script {
                    if (!params.EC2_HOST?.trim()) {
                        error('Set EC2_HOST when DEPLOY_TO_EC2 is enabled.')
                    }
                    sshagent(credentials: [params.EC2_CREDENTIALS_ID]) {
                        withEnv([
                            "EC2_HOST=${params.EC2_HOST}",
                            "EC2_USER=${params.EC2_USER}",
                            "EC2_PROJECT_DIR=${params.EC2_PROJECT_DIR}"
                        ]) {
                            sh '''
                                set -eu

                                docker save "${DOCKER_IMAGE}" | gzip -1 | ssh -o StrictHostKeyChecking=yes \\
                                    "${EC2_USER}@${EC2_HOST}" 'gunzip | docker load'

                                ssh -o StrictHostKeyChecking=yes \\
                                    "${EC2_USER}@${EC2_HOST}" \\
                                    "set -e
                                     docker tag ${DOCKER_IMAGE} cloudpulse-backend:latest
                                     docker stop cloudpulse-backend 2>/dev/null || true
                                     docker rm cloudpulse-backend 2>/dev/null || true
                                     docker run -d \\\\
                                         --name cloudpulse-backend \\\\
                                         --restart unless-stopped \\\\
                                         --env-file ${EC2_PROJECT_DIR}/.env \\\\
                                         -p 8000:8000 \\\\
                                         ${DOCKER_IMAGE}
                                     docker ps --filter name=cloudpulse-backend"
                            '''
                        }
                    }
                }
            }
        }

        stage('Health Check') {
            when {
                expression { params.DEPLOY_TO_EC2 }
            }
            steps {
                script {
                    sshagent(credentials: [params.EC2_CREDENTIALS_ID]) {
                        withEnv([
                            "EC2_HOST=${params.EC2_HOST}",
                            "EC2_USER=${params.EC2_USER}"
                        ]) {
                            sh '''
                                set -eu

                                for attempt in 1 2 3 4 5; do
                                    if ssh -o StrictHostKeyChecking=yes \\
                                        "${EC2_USER}@${EC2_HOST}" \\
                                        'curl -fsS http://localhost:8000/health && curl -fsS http://localhost:8000/api/v1/db/health'; then
                                        echo "Application and database health checks passed."
                                        exit 0
                                    fi

                                    echo "Health check attempt ${attempt} failed. Retrying..."
                                    sleep 5
                                done

                                ssh -o StrictHostKeyChecking=yes \\
                                    "${EC2_USER}@${EC2_HOST}" \\
                                    'docker logs --tail 100 cloudpulse-backend' || true

                                echo "Health check failed after 5 attempts."
                                exit 1
                            '''
                        }
                    }
                }
            }
        }
    }

    post {
        success {
            echo 'CloudPulse Sentinel CI/CD pipeline completed successfully.'
        }

        failure {
            echo 'CloudPulse Sentinel CI/CD pipeline failed.'
        }

        always {
            echo "Build #${BUILD_NUMBER} completed."
            archiveArtifacts artifacts: 'reports/trivy-report.json',
                             allowEmptyArchive: true
        }
    }
}
