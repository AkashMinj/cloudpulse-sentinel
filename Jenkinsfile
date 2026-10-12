pipeline {
    agent any

    environment {
        EC2_HOST = '18.214.224.132'
        EC2_USER = 'ec2-user'
        EC2_PROJECT_DIR = '/home/ec2-user/cloudpulse-sentinel'
        EC2_CREDENTIALS = 'cloudpulse-ec2-ssh'
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
                    /usr/bin/trivy image \
                        --severity HIGH,CRITICAL \
                        --exit-code 0 \
                        "${DOCKER_IMAGE}"
                '''
            }
        }

        stage('Deploy to EC2') {
            steps {
                sshagent(credentials: [env.EC2_CREDENTIALS]) {
                    sh '''
                        set -eu

                        ssh -o StrictHostKeyChecking=yes \
                            "${EC2_USER}@${EC2_HOST}" \
                            "set -e

                             cd ${EC2_PROJECT_DIR}

                             git fetch origin
                             git reset --hard origin/main

                             docker build \
                                 -t cloudpulse-backend:latest \
                                 .

                             docker stop cloudpulse-backend 2>/dev/null || true
                             docker rm cloudpulse-backend 2>/dev/null || true

                             docker run -d \
                                 --name cloudpulse-backend \
                                 --restart unless-stopped \
                                 --env-file .env \
                                 -e ML_MODEL_BUCKET=cloudpulse-ml-models-306005334008 \
                                 -p 8000:8000 \
                                 cloudpulse-backend:latest

                             docker ps --filter name=cloudpulse-backend"
                    '''
                }
            }
        }

        stage('Health Check') {
            steps {
                sshagent(credentials: [env.EC2_CREDENTIALS]) {
                    sh '''
                        set -eu

                        ssh -o StrictHostKeyChecking=yes \
                            "${EC2_USER}@${EC2_HOST}" \
                            "set -e

                             for i in 1 2 3 4 5; do
                                 if curl -fsS http://localhost:8000/health; then
                                     echo
                                     exit 0
                                 fi

                                 echo 'Health check attempt \$i failed. Retrying...'
                                 sleep 5
                             done

                             echo 'Health check failed.'
                             docker logs --tail 100 cloudpulse-backend
                             exit 1"
                    '''
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
        }
    }
}
