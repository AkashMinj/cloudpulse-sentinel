resource "aws_security_group" "cloudpulse_rds_sg" {
  name        = "cloudpulse-rds-sg"
  description = "Security group for CloudPulse PostgreSQL RDS"
  vpc_id      = aws_vpc.cloudpulse_vpc.id

  ingress {
    description     = "PostgreSQL access from EC2"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.cloudpulse_ec2_sg.id]
  }

  egress {
    description = "Allow outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "cloudpulse-rds-sg"
    Project     = "CloudPulse Sentinel"
    Environment = "development"
  }
}
