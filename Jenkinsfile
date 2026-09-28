pipeline {
    agent any

    environment {
        EC2_HOST  = '18.214.224.132'
        EC2_USER  = 'ec2-user'
        EC2_DIR   = '/home/ec2-user/cloudpulse-sentinel'

        IMAGE     = 'cloudpulse-backend'
        CONTAINER = 'cloudpulse-backend'
    }

    stages {

        stage('Clean Workspace') {
            steps {
                deleteDir()
            }
        }

        stage('Checkout') {
            steps {
                git branch: 'main',
                    url: 'https://github.com/AkashMinj/cloudpulse-sentinel.git'
            }
        }

        stage('Validate Python') {
            steps {
                sh '''
                    set -e

                    python3 --version
                    python3 -m compileall -q app

                    echo "Python validation passed."
                '''
            }
        }
    stage('Run Tests') {
        steps {
        sh '''
                    set -e

                   python3 -m venv .venv
                    .venv/bin/python -m pip install --upgrade pip
                .venv/bin/python -m pip install -r app/requirements.txt

                .venv/bin/python -m pytest -q

                  echo "Automated tests passed."
                  '''
        }
    }
        stage('Build Lambda Package') {
            steps {
                sh '''
                    set -e

                    rm -rf lambda_build incident_processor.zip
                    mkdir -p lambda_build

                    cp app/incident_processor_lambda.py lambda_build/
                    cp app/incident_engine.py lambda_build/

                    docker run --rm \
                        --user "$(id -u):$(id -g)" \
                        --entrypoint /bin/sh \
                        -v "$PWD/lambda_build:/var/task" \
                        public.ecr.aws/lambda/python:3.12 \
                        -c "pip install psycopg2-binary -t /var/task"

                    cd lambda_build
                    zip -qr ../incident_processor.zip .

                    cd ..

                    ls -lh incident_processor.zip

                    echo "Lambda package built successfully."
                '''
            }
        }

        stage('Validate Terraform') {
            steps {
                dir('infrastructure/terraform') {
                    sh '''
                        set -e

                        terraform fmt -check
                        terraform init -backend=false
                        terraform validate

                        echo "Terraform validation passed."
                    '''
                }
            }
        }

        stage('Docker Build') {
            steps {
                sh '''
                    set -e

                    docker build \
                        -t ${IMAGE}:ci-${BUILD_NUMBER} \
                        .

                    echo "Docker image built successfully."
                '''
            }
        }

        stage('Deploy to EC2') {
            steps {
                sshagent(credentials: ['cloudpulse-ec2-ssh']) {
                    sh '''
                        set -e

                        ssh -o StrictHostKeyChecking=yes \
                            ${EC2_USER}@${EC2_HOST} \
                            "cd ${EC2_DIR} && \
                             git fetch origin && \
                             git reset --hard origin/main && \
                             docker build -t ${IMAGE}:latest . && \
                             docker stop ${CONTAINER} || true && \
                             docker rm ${CONTAINER} || true && \
                             docker run -d \
                               --name ${CONTAINER} \
                               --restart unless-stopped \
                               --env-file .env \
                               -p 8000:8000 \
                               ${IMAGE}:latest"

                        echo "Deployment to EC2 completed."
                    '''
                }
            }
        }

        stage('Health Check') {
            steps {
                sshagent(credentials: ['cloudpulse-ec2-ssh']) {
                    sh '''
                        set -e

                        ssh -o StrictHostKeyChecking=yes \
                            ${EC2_USER}@${EC2_HOST} \
                            "for i in 1 2 3 4 5; do \
                                curl -fsS http://localhost:8000/health && exit 0; \
                                echo 'Health check attempt failed. Retrying...'; \
                                sleep 3; \
                             done; \
                             exit 1"

                        echo "Health check passed."
                    '''
                }
            }
        }
    }

    post {
        success {
            echo '========================================'
            echo 'CloudPulse Sentinel CI/CD SUCCESS'
            echo '========================================'
            echo "Deployment: ${EC2_HOST}"
            echo "Build: ${BUILD_NUMBER}"
        }

        failure {
            echo '========================================'
            echo 'CloudPulse Sentinel CI/CD FAILED'
            echo '========================================'
            echo "Build: ${BUILD_NUMBER}"
        }

        always {
            echo "Pipeline completed: ${currentBuild.currentResult}"
        }
    }
}
