resource "aws_sqs_queue" "cloudpulse_events_dlq" {
  name                      = "cloudpulse-events-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true

  tags = {
    Name    = "cloudpulse-events-dlq"
    Project = "CloudPulse Sentinel"
  }
}

resource "aws_sqs_queue" "cloudpulse_events" {
  name                       = "cloudpulse-events"
  visibility_timeout_seconds = 180
  message_retention_seconds  = 86400
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.cloudpulse_events_dlq.arn
    maxReceiveCount     = 5
  })

  tags = {
    Name    = "cloudpulse-events"
    Project = "CloudPulse Sentinel"
  }
}

resource "aws_iam_role" "cloudpulse_ec2_role" {
  name = "cloudpulse-ec2-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
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
    Statement = [{
      Effect   = "Allow"
      Action   = ["sqs:SendMessage"]
      Resource = aws_sqs_queue.cloudpulse_events.arn
    }]
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

output "cloudpulse_events_dlq_url" {
  description = "CloudPulse dead-letter queue URL"
  value       = aws_sqs_queue.cloudpulse_events_dlq.url
}
