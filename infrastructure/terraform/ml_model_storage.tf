data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "ml_models" {
  bucket = "cloudpulse-ml-models-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name        = "cloudpulse-ml-models"
    Project     = "CloudPulse Sentinel"
    Environment = "development"
  }
}

resource "aws_s3_bucket_public_access_block" "ml_models" {
  bucket = aws_s3_bucket.ml_models.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "ml_models" {
  bucket = aws_s3_bucket.ml_models.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "ml_models" {
  bucket = aws_s3_bucket.ml_models.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_iam_role_policy" "cloudpulse_ml_model_s3_policy" {
  name = "cloudpulse-ml-model-s3-policy"
  role = aws_iam_role.cloudpulse_ec2_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ListModelBucket"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = aws_s3_bucket.ml_models.arn
      },
      {
        Sid    = "ManageModelArtifacts"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.ml_models.arn}/models/*"
      }
    ]
  })
}

output "ml_model_bucket_name" {
  description = "S3 bucket storing CloudPulse ML model artifacts"
  value       = aws_s3_bucket.ml_models.bucket
}
