resource "aws_security_group" "cloudpulse_lambda_sg" {
  name        = "cloudpulse-lambda-sg"
  description = "Security group for CloudPulse Lambda processor"
  vpc_id      = aws_vpc.cloudpulse_vpc.id

  egress {
    description = "Allow outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "cloudpulse-lambda-sg"
    Project     = "CloudPulse Sentinel"
    Environment = "development"
  }
}

resource "aws_security_group_rule" "rds_from_lambda" {
  type                     = "ingress"
  description              = "Allow PostgreSQL from Lambda processor"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.cloudpulse_rds_sg.id
  source_security_group_id = aws_security_group.cloudpulse_lambda_sg.id
}

resource "aws_iam_role" "cloudpulse_lambda_processor_role" {
  name = "cloudpulse-lambda-processor-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Principal = {
          Service = "lambda.amazonaws.com"
        }

        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name    = "cloudpulse-lambda-processor-role"
    Project = "CloudPulse Sentinel"
  }
}

resource "aws_iam_role_policy" "cloudpulse_lambda_processor_policy" {
  name = "cloudpulse-lambda-processor-policy"
  role = aws_iam_role.cloudpulse_lambda_processor_role.id

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]

        Resource = aws_sqs_queue.cloudpulse_events.arn
      },
      {
        Effect = "Allow"

        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]

        Resource = "*"
      },
      {
        Effect = "Allow"

        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface"
        ]

        Resource = "*"
      }
    ]
  })
}

resource "aws_lambda_function" "cloudpulse_incident_processor" {
  function_name = "cloudpulse-incident-processor"

  role = aws_iam_role.cloudpulse_lambda_processor_role.arn

  filename = "${path.module}/../../incident_processor.zip"

  source_code_hash = filebase64sha256(
    "${path.module}/../../incident_processor.zip"
  )

  handler = "incident_processor_lambda.lambda_handler"

  runtime = "python3.12"

  timeout     = 30
  memory_size = 256

  vpc_config {
    subnet_ids = [
      aws_subnet.private_subnet_a.id,
      aws_subnet.private_subnet_b.id
    ]

    security_group_ids = [
      aws_security_group.cloudpulse_lambda_sg.id
    ]
  }

  environment {
    variables = {
      DB_HOST = aws_db_instance.cloudpulse_postgres.address

      DB_PORT = "5432"

      DB_NAME = aws_db_instance.cloudpulse_postgres.db_name

      DB_USER = var.db_username

      DB_PASSWORD = var.db_password
    }
  }

  tags = {
    Name        = "cloudpulse-incident-processor"
    Project     = "CloudPulse Sentinel"
    Environment = "development"
  }
}

resource "aws_lambda_event_source_mapping" "cloudpulse_sqs_trigger" {
  event_source_arn = aws_sqs_queue.cloudpulse_events.arn

  function_name = aws_lambda_function.cloudpulse_incident_processor.arn

  batch_size = 1

  function_response_types = [
    "ReportBatchItemFailures"
  ]

  enabled = true
}

output "cloudpulse_lambda_processor_name" {
  description = "CloudPulse incident processor Lambda name"

  value = aws_lambda_function.cloudpulse_incident_processor.function_name
}

output "cloudpulse_lambda_processor_arn" {
  description = "CloudPulse incident processor Lambda ARN"

  value = aws_lambda_function.cloudpulse_incident_processor.arn
}
