data "aws_caller_identity" "metrics_archive" {}

resource "aws_s3_bucket" "metrics_archive" {
  bucket = "cloudpulse-metrics-archive-${data.aws_caller_identity.metrics_archive.account_id}"

  tags = {
    Name        = "cloudpulse-metrics-archive"
    Project     = "CloudPulse Sentinel"
    Environment = "development"
  }
}

resource "aws_s3_bucket_public_access_block" "metrics_archive" {
  bucket                  = aws_s3_bucket.metrics_archive.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "metrics_archive" {
  bucket = aws_s3_bucket.metrics_archive.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "metrics_archive" {
  bucket = aws_s3_bucket.metrics_archive.id

  rule {
    id     = "expire-raw-metrics-after-90-days"
    status = "Enabled"

    filter {
      prefix = "raw-metrics/"
    }

    expiration {
      days = 90
    }
  }
}

resource "aws_iam_role_policy" "cloudpulse_metrics_archive_policy" {
  name = "cloudpulse-metrics-archive-policy"
  role = aws_iam_role.cloudpulse_ec2_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject"]
      Resource = "${aws_s3_bucket.metrics_archive.arn}/raw-metrics/*"
    }]
  })
}

output "metrics_archive_bucket_name" {
  description = "S3 bucket for raw metric event archives"
  value       = aws_s3_bucket.metrics_archive.bucket
}
