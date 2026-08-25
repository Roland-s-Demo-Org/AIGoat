variable "vpc_id" {}
variable "subd_public" {}
variable "subnet_group_id" {}
variable "output_integrity_api_endpoint" {}
variable "supply_chain_api_endpoint" {}
variable "supply_chain_bucket_name" {}
variable "data_poisoning_api_endpoint" {}
variable "data_poisoning_bucket_name" {}

# Security Note: Removed aws_key_pair resource that was previously used with a repository-committed
# private key. SSH key pairs should not be managed in Terraform when the private key must be
# committed to source control. For emergency access, use AWS Systems Manager Session Manager instead.
#
# resource "aws_key_pair" "key-auth" {
#   key_name   = "webserver-key"
#   public_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDPmOyEJHVMpDOsay5XD87y/ul6qFD2Wg+vnwswZNl22Yql9FNKTM7+h5vWdj8wXp+wgB0J/xyrfc4Bwyd7DUxFHHJibN5MS2eCspA3jMBNC//QrKbmCvTLq/laH57Jg78wdQKUtCRKctDU0/7BCVT7/QW613EQMRLuAYr+G+RkZHBwgVA06DOH3k1kMhFg+x8IQqfzpJJ4dWy64eRcayNEWD+DgTuXqGobNxP9dLBMdHx8MY74d8zOVq3LsTwpOUHDTW0U9e5FP27pvBWm01EPj0vaOfG5HaAvdco0AhZsW5JVz0gjrFQuCpfjZC4aow4du3GSIIq+bLHMqxC1jztP1jgzazXuvaGMiqy9HjolD3yyEsvk5FfTMSsTeGVQYyQLce/6jUS/mYYB/Y6JqLZbN7RU5UL/ME89U20eot/7BhYynqf6fgSgPI5HGhwvTC/YrED8ZzpwKDwMM1m8qmXp96A2URbQrIPYfmk638+t5VgNRHH/AjGKf0UDvox5mMD/KLnsqphwdiYXpvFdtuL/xndMqYH4v8TqIC+r+ZgHLYBeTIoQ78ftwD/7J4DN2y8WXSk/aL84k/LvoipWrEAPhhN6xfMiVCavk7v8zn/X6iE4EEDn+tX1Mp3PuMsjcVRSGNx78dxLcMziY+jKkdP3OzVYWG8V941GquS1gv1bQQ== ofir.yakobi@orca.security"
# }


data aws_iam_policy_document "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

data aws_iam_policy_document "s3_read_access" {
  statement {
    actions = ["s3:Get*", "s3:List*", "s3:PutObject"]

    resources = ["arn:aws:s3:::*"]
  }
}

data aws_iam_policy_document "sagemaker_access" {
  statement {
    actions = ["sagemaker:DescribeEndpoint", "sagemaker:InvokeEndpoint"]
    resources = ["*"]
  }
}

# Security Note: Added SSM policy to enable AWS Systems Manager Session Manager
# as a secure alternative to SSH access without requiring inbound ports or SSH keys
data aws_iam_policy_document "ssm_access" {
  statement {
    actions = [
      "ssm:UpdateInstanceInformation",
      "ssmmessages:CreateControlChannel",
      "ssmmessages:CreateDataChannel",
      "ssmmessages:OpenControlChannel",
      "ssmmessages:OpenDataChannel"
    ]
    resources = ["*"]
  }
}


resource "aws_iam_role_policy" "sagemaker_policy" {
  depends_on = ["aws_iam_role.ec2_iam_role"]
  name       = "sagemaker_policy"
  role       = aws_iam_role.ec2_iam_role.name

  policy = data.aws_iam_policy_document.sagemaker_access.json
}

resource "aws_iam_role_policy" "ssm_policy" {
  depends_on = ["aws_iam_role.ec2_iam_role"]
  name       = "ssm_policy"
  role       = aws_iam_role.ec2_iam_role.name

  policy = data.aws_iam_policy_document.ssm_access.json
}

resource "aws_iam_role" "ec2_iam_role" {
  name = "ec2_iam_role"

  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

resource "aws_iam_role_policy" "join_policy" {
  depends_on = ["aws_iam_role.ec2_iam_role"]
  name       = "join_policy"
  role       = aws_iam_role.ec2_iam_role.name

  policy = data.aws_iam_policy_document.s3_read_access.json
}


resource "aws_iam_instance_profile" "ec2_profile" {
  name = "instance_profile"
  role = aws_iam_role.ec2_iam_role.name
}


resource "aws_instance" "backend" {
  depends_on = [aws_db_instance.rds, aws_security_group.rds_sg, aws_security_group.ec2-sg]
  ami           = "ami-0c94855ba95c71c99"
  subnet_id                   = var.subd_public
  iam_instance_profile = aws_iam_instance_profile.ec2_profile.name  # Attach IAM role
  instance_type = "t2.micro"
  
  # Security Note: Removed SSH file provisioner that required a repository-committed private key.
  # Backend application files should be deployed via one of these secure methods:
  # - Pre-baked into a custom AMI
  # - Downloaded from S3 using the instance IAM role
  # - Deployed via AWS Systems Manager (SSM) Session Manager
  # - Retrieved from a secure artifact repository
  # The user_data script below expects files to be available via one of these methods.
  
  user_data = <<-EOF
  #cloud-config
  write_files:
    - path: /home/ec2-user/setup.sh
      permissions: "0755"
      content: |
        #!/bin/bash
        sudo yum update -y
        sudo yum install -y amazon-linux-extras
        sudo amazon-linux-extras install postgresql10
        sudo yum install -y python3-pip python3-devel
        sudo yum install -y gcc
        sudo yum install -y postgresql postgresql-devel
        sudo touch sensitive_data.txt
        sudo chmod 777 sensitive_data.txt
        sudo echo "{"user_recommendations_dataset": "${var.data_poisoning_bucket_name}"}" >> /home/ec2-user/sensitive_data.txt
        cd /home/ec2-user/backend
        sudo pip3 install --upgrade pip setuptools
        pip3 install -r requirements.txt
        export PYTHONPATH=$PYTHONPATH:$(python3 -m site --user-site)
        python3 migrate_data.py --db_user=pos_user --db_password=password123 --db_host=${aws_db_instance.rds.address} --db_name=postgres
        sudo nohup python3 app.py --db_user=pos_user --db_password=password123 --db_host=${aws_db_instance.rds.address} --db_name=postgres --comments_api_gateway=${var.output_integrity_api_endpoint} --similar_images_api_gateway=${var.supply_chain_api_endpoint} --similar_images_bucket=${var.supply_chain_bucket_name} --get_recs_api_gateway=${var.data_poisoning_api_endpoint} --data_poisoning_bucket=${var.data_poisoning_bucket_name} &
  runcmd:
    - mkdir -p /home/ec2-user/backend
    # TODO: Replace with secure deployment method. Examples:
    # S3: aws s3 cp s3://your-deployment-bucket/backend.tar.gz /tmp/ && tar -xzf /tmp/backend.tar.gz -C /home/ec2-user/backend
    # Git: git clone https://github.com/your-org/backend.git /home/ec2-user/backend
    # For now, this will fail gracefully - implement proper deployment before use
    - /home/ec2-user/setup.sh
            EOF

  tags = {
    Name = "backend-server"
  }

  vpc_security_group_ids = [aws_security_group.ec2-sg.id]
  # Removed key_name assignment - SSH key pair no longer needed without SSH provisioner
  # For emergency access, use AWS Systems Manager Session Manager instead
}

resource "aws_security_group" "rds_sg" {
  name        = "rds_sg"
  description = "AWS RDS Security Group"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    self        = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ec2-sg" {
  name        = "ec2-sg"
  description = "Allow inbound access to RDS"
  vpc_id      = var.vpc_id


  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.rds_sg.id]
    # cidr_blocks = [aws_security_group.allow_http.id]
  }
  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    # cidr_blocks = [aws_security_group.allow_http.id]
  }
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  # Security Note: Removed world-open SSH ingress rule (port 22 from 0.0.0.0/0).
  # SSH access should not be exposed to the Internet. For emergency access, use:
  # - AWS Systems Manager Session Manager (no inbound ports required)
  # - VPN or bastion host with restricted source IP ranges
  # - Temporary security group rules with specific IP addresses when absolutely necessary
  #
  # ingress {
  #   description = "SSH"
  #   from_port   = 22
  #   to_port     = 22
  #   protocol    = "tcp"
  #   cidr_blocks = ["0.0.0.0/0"]
  # }


  egress {
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

data "aws_rds_engine_version" "postgres" {
  engine = "postgres"
}

resource "aws_db_instance" "rds" {
  engine                = "postgres"
  instance_class        = "db.t3.micro"
  identifier           = "rds-database"
  allocated_storage    =  10
  engine_version       = data.aws_rds_engine_version.postgres.version
  username             = "pos_user"
  password             = ****123"
  vpc_security_group_ids = ["${aws_security_group.rds_sg.id}"]
  db_subnet_group_name   = var.subnet_group_id
  skip_final_snapshot  = true
  publicly_accessible =  true
}
