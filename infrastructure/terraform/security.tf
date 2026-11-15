variable "admin_cidr" {
  description = "Administrator public IPv4 CIDR allowed to SSH (for example, 203.0.113.10/32)"
  type        = string
  nullable    = false

  validation {
    condition     = can(cidrhost(var.admin_cidr, 0)) && var.admin_cidr != "0.0.0.0/0"
    error_message = "admin_cidr must be a valid restricted CIDR and must not be 0.0.0.0/0."
  }
}

resource "aws_security_group" "cloudpulse_ec2_sg" {
  name        = "cloudpulse-ec2-sg"
  description = "Security group for CloudPulse Sentinel EC2"
  vpc_id      = aws_vpc.cloudpulse_vpc.id

  ingress {
    description = "SSH from administrator IP only"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.admin_cidr]
  }

  egress {
    description = "Allow outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "cloudpulse-ec2-sg"
    Project     = "CloudPulse Sentinel"
    Environment = "development"
  }
}
