
# CloudPulse Sentinel - VPC

resource "aws_vpc" "cloudpulse_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name        = "cloudpulse-vpc"
    Project     = "CloudPulse-Sentinel"
    Environment = "dev"
  }
}


# Internet Gateway

resource "aws_internet_gateway" "cloudpulse_igw" {
  vpc_id = aws_vpc.cloudpulse_vpc.id

  tags = {
    Name    = "cloudpulse-igw"
    Project = "CloudPulse-Sentinel"
  }
}


# Public Subnets

resource "aws_subnet" "public_subnet_a" {
  vpc_id                  = aws_vpc.cloudpulse_vpc.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = var.availability_zones[0]
  map_public_ip_on_launch = true

  tags = {
    Name    = "cloudpulse-public-a"
    Tier    = "public"
    Project = "CloudPulse-Sentinel"
  }
}

resource "aws_subnet" "public_subnet_b" {
  vpc_id                  = aws_vpc.cloudpulse_vpc.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = var.availability_zones[1]
  map_public_ip_on_launch = true

  tags = {
    Name    = "cloudpulse-public-b"
    Tier    = "public"
    Project = "CloudPulse-Sentinel"
  }
}


# Private Subnets

resource "aws_subnet" "private_subnet_a" {
  vpc_id            = aws_vpc.cloudpulse_vpc.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = var.availability_zones[0]

  tags = {
    Name    = "cloudpulse-private-a"
    Tier    = "private"
    Project = "CloudPulse-Sentinel"
  }
}

resource "aws_subnet" "private_subnet_b" {
  vpc_id            = aws_vpc.cloudpulse_vpc.id
  cidr_block        = "10.0.12.0/24"
  availability_zone = var.availability_zones[1]

  tags = {
    Name    = "cloudpulse-private-b"
    Tier    = "private"
    Project = "CloudPulse-Sentinel"
  }
}


# Public Route Table

resource "aws_route_table" "public_route_table" {
  vpc_id = aws_vpc.cloudpulse_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.cloudpulse_igw.id
  }

  tags = {
    Name    = "cloudpulse-public-rt"
    Project = "CloudPulse-Sentinel"
  }
}


# Public Route Associations

resource "aws_route_table_association" "public_a_association" {
  subnet_id      = aws_subnet.public_subnet_a.id
  route_table_id = aws_route_table.public_route_table.id
}

resource "aws_route_table_association" "public_b_association" {
  subnet_id      = aws_subnet.public_subnet_b.id
  route_table_id = aws_route_table.public_route_table.id
}


# Private Route Tables

resource "aws_route_table" "private_route_table_a" {
  vpc_id = aws_vpc.cloudpulse_vpc.id

  tags = {
    Name    = "cloudpulse-private-rt-a"
    Project = "CloudPulse-Sentinel"
  }
}

resource "aws_route_table" "private_route_table_b" {
  vpc_id = aws_vpc.cloudpulse_vpc.id

  tags = {
    Name    = "cloudpulse-private-rt-b"
    Project = "CloudPulse-Sentinel"
  }
}


# Private Route Associations

resource "aws_route_table_association" "private_a_association" {
  subnet_id      = aws_subnet.private_subnet_a.id
  route_table_id = aws_route_table.private_route_table_a.id
}

resource "aws_route_table_association" "private_b_association" {
  subnet_id      = aws_subnet.private_subnet_b.id
  route_table_id = aws_route_table.private_route_table_b.id
}
