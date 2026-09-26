variable "admin_cidr" {
  description = "Public IP address allowed to access EC2 through SSH"
  type        = string
  default     = "0.0.0.0/0"
}

resource "aws_security_group" "cloudpulse_ec2_sg" {
  name        = "cloudpulse-ec2-sg"
  description = "Security group for CloudPulse Sentinel EC2"
  vpc_id      = aws_vpc.cloudpulse_vpc.id

  ingress {
    description = "SSH from administrator IP"
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
