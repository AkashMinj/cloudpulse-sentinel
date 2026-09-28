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
                    python3 --version
                    python3 -m compileall -q app tests
                '''
            }
        }

        stage('Run Tests') {
            steps {
                sh '''
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
                    .venv/bin/pip-audit
                '''
            }
        }

        stage('Build Lambda Package') {
            steps {
                sh '''
                    rm -rf build/lambda
                    mkdir -p build/lambda

                    docker run --rm \
                        --user "$(id -u):$(id -g)" \
                        -v "$PWD:/workspace" \
                        -w /workspace \
                        python:3.12-slim \
                        bash -c "
                            pip install \
                                -r app/requirements.txt \
                                -t build/lambda
                            cp app/incident_processor_lambda.py build/lambda/
                            cp app/incident_engine.py build/lambda/
                        "

                    cd build/lambda
                    zip -r ../incident-processor.zip .
                '''
            }
        }

        stage('Validate Terraform') {
            steps {
                sh '''
                    terraform fmt -check -recursive
                    terraform init -backend=false
                    terraform validate
                '''
            }
        }

        stage('Docker Build') {
            steps {
                sh '''
                    docker build \
                        -t ${DOCKER_IMAGE} \
                        .
                '''
            }
        }

        stage('Container Security Scan') {
            steps {
                sh '''
                    /usr/bin/trivy image \
                        --severity HIGH,CRITICAL \
                        --exit-code 0 \
                        ${DOCKER_IMAGE}
                '''
            }
        }

        stage('Deploy to EC2') {
            steps {
                sshagent(credentials: [env.EC2_CREDENTIALS]) {
                    sh '''
                        ssh -o StrictHostKeyChecking=yes \
                            ${EC2_USER}@${EC2_HOST} \
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
                        ssh -o StrictHostKeyChecking=yes \
                            ${EC2_USER}@${EC2_HOST} \
                            "set -e

                             for i in 1 2 3 4 5; do
                                 if curl -fsS http://localhost:8000/health; then
                                     echo
                                     exit 0
                                 fi

                                 echo 'Health check attempt $i  failed. Retrying...'
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
