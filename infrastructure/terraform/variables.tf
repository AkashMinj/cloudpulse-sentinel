variable "aws_region" {
  description = "AWS region for CloudPulse Sentinel"
  type        = string
  default     = "us-east-1"
}

variable "availability_zones" {
  description = "Availability zones for CloudPulse Sentinel"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}
