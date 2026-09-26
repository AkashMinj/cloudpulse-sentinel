resource "aws_sqs_queue" "cloudpulse_events" {
  name = "cloudpulse-events"

  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400

  tags = {
    Name        = "cloudpulse-events"
    Project     = "CloudPulse Sentinel"
    Environment = "development"
  }
}


resource "aws_iam_role" "cloudpulse_ec2_role" {
  name = "cloudpulse-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Principal = {
          Service = "ec2.amazonaws.com"
        }

        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name    = "cloudpulse-ec2-role"
    Project = "CloudPulse Sentinel"
  }
}


resource "aws_iam_role_policy" "cloudpulse_sqs_policy" {
  name = "cloudpulse-sqs-send-policy"
  role = aws_iam_role.cloudpulse_ec2_role.id

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Action = [
          "sqs:SendMessage"
        ]

        Resource = aws_sqs_queue.cloudpulse_events.arn
      }
    ]
  })
}


resource "aws_iam_instance_profile" "cloudpulse_ec2_profile" {
  name = "cloudpulse-ec2-profile"
  role = aws_iam_role.cloudpulse_ec2_role.name

  tags = {
    Name    = "cloudpulse-ec2-profile"
    Project = "CloudPulse Sentinel"
  }
}


output "cloudpulse_events_queue_url" {
  description = "CloudPulse event queue URL"
  value       = aws_sqs_queue.cloudpulse_events.url
}


output "cloudpulse_events_queue_arn" {
  description = "CloudPulse event queue ARN"
  value       = aws_sqs_queue.cloudpulse_events.arn
}
resource "aws_iam_role" "cloudpulse_processor_role" {
  name = "cloudpulse-processor-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name    = "cloudpulse-processor-role"
    Project = "CloudPulse Sentinel"
  }
}

resource "aws_iam_role_policy" "cloudpulse_processor_sqs_policy" {
  name = "cloudpulse-processor-sqs-policy"
  role = aws_iam_role.cloudpulse_processor_role.id

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
      }
    ]
  })
}
