resource "aws_db_subnet_group" "cloudpulse_rds_subnet_group" {
  name = "cloudpulse-rds-subnet-group"

  subnet_ids = [
    aws_subnet.private_subnet_a.id,
    aws_subnet.private_subnet_b.id
  ]

  tags = {
    Name        = "cloudpulse-rds-subnet-group"
    Project     = "CloudPulse Sentinel"
    Environment = "development"
  }
}

resource "aws_db_instance" "cloudpulse_postgres" {
  identifier = "cloudpulse-postgres"

  engine         = "postgres"
  engine_version = "17"

  instance_class        = "db.t3.micro"
  allocated_storage     = 20
  max_allocated_storage = 50
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "cloudpulse"
  username = var.db_username
  password = var.db_password
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.cloudpulse_rds_subnet_group.name
  vpc_security_group_ids = [aws_security_group.cloudpulse_rds_sg.id]

  publicly_accessible     = false
  skip_final_snapshot     = true
  deletion_protection     = false
  backup_retention_period = 1

  tags = {
    Name        = "cloudpulse-postgres"
    Project     = "CloudPulse Sentinel"
    Environment = "development"
  }
}
