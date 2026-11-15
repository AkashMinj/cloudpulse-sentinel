resource "aws_instance" "cloudpulse_ec2" {
  ami                         = data.aws_ami.amazon_linux.id
  instance_type               = "t3.micro"
  subnet_id                   = aws_subnet.public_subnet_a.id
  vpc_security_group_ids      = [aws_security_group.cloudpulse_ec2_sg.id]
  key_name                    = "cloudpulse-key"
  associate_public_ip_address = true

  iam_instance_profile = aws_iam_instance_profile.cloudpulse_ec2_profile.name

  root_block_device {
    volume_size           = 8
    volume_type           = "gp3"
    delete_on_termination = true
  }

  tags = {
    Name        = "cloudpulse-ec2"
    Project     = "CloudPulse Sentinel"
    Environment = "development"
  }
}

resource "aws_eip" "cloudpulse_ec2" {
  domain = "vpc"

  tags = {
    Name        = "cloudpulse-ec2-eip"
    Project     = "CloudPulse Sentinel"
    Environment = "development"
  }
}

resource "aws_eip_association" "cloudpulse_ec2" {
  instance_id   = aws_instance.cloudpulse_ec2.id
  allocation_id = aws_eip.cloudpulse_ec2.id
}
