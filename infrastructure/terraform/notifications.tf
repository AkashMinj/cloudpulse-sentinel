resource "aws_sns_topic" "cloudpulse_alerts" {
  name = "cloudpulse-alerts"
  tags = {
    Name    = "cloudpulse-alerts"
    Project = "CloudPulse Sentinel"
  }
}

resource "aws_iam_role_policy" "cloudpulse_sns_publish_policy" {
  name = "cloudpulse-sns-publish-policy"
  role = aws_iam_role.cloudpulse_ec2_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sns:Publish"]
      Resource = aws_sns_topic.cloudpulse_alerts.arn
    }]
  })
}

output "cloudpulse_alerts_topic_arn" {
  description = "SNS topic ARN for CloudPulse incident notifications"
  value       = aws_sns_topic.cloudpulse_alerts.arn
}
