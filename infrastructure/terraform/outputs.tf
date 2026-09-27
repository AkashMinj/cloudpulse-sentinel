output "vpc_id" {
  description = "CloudPulse Sentinel VPC ID"
  value       = aws_vpc.cloudpulse_vpc.id
}

output "public_subnet_ids" {
  description = "CloudPulse Sentinel public subnet IDs"
  value = [
    aws_subnet.public_subnet_a.id,
    aws_subnet.public_subnet_b.id
  ]
}

output "private_subnet_ids" {
  description = "CloudPulse Sentinel private subnet IDs"
  value = [
    aws_subnet.private_subnet_a.id,
    aws_subnet.private_subnet_b.id
  ]
}

output "internet_gateway_id" {
  description = "CloudPulse Sentinel Internet Gateway ID"
  value       = aws_internet_gateway.cloudpulse_igw.id
}

output "ec2_instance_id" {
  description = "CloudPulse Sentinel EC2 instance ID"
  value       = aws_instance.cloudpulse_ec2.id
}

output "ec2_public_ip" {
  description = "CloudPulse Sentinel EC2 public IP"
  value       = aws_eip.cloudpulse_ec2.public_ip
}

output "ec2_public_dns" {
  description = "CloudPulse Sentinel EC2 public DNS"
  value       = aws_instance.cloudpulse_ec2.public_dns
}
