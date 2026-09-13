# Official Amazon-owned AL2023 AMI, looked up by name filter rather than a
# hardcoded AMI ID that goes stale as AWS publishes new AL2023 releases.
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-kernel-*-arm64"]
  }

  filter {
    name   = "architecture"
    values = ["arm64"]
  }
}

# Only 80/443 reachable from the internet - Traefik is the sole public
# entry point, exactly matching docker-compose.prod.yml (backend/db
# publish no ports at all). No inbound 22 - see the SSM instance role
# below; AWS's own security-group guidance recommends against leaving SSH
# open to 0.0.0.0/0.
resource "aws_security_group" "app" {
  name        = "bank-platform-app"
  description = "bank-platform: HTTP/HTTPS in via Traefik, no SSH"

  ingress {
    description = "HTTP (Traefik redirects to HTTPS)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS (Traefik)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound (dnf, ACME, docker pull, LLM provider API)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "bank-platform-app"
  }
}

# Session Manager instead of SSH: zero inbound ports, no key pair to
# provision or lose, full session logging via CloudTrail. See
# https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html
data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app_instance" {
  name               = "bank-platform-app-instance"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.app_instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "app_instance" {
  name = "bank-platform-app-instance"
  role = aws_iam_role.app_instance.name
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.app_instance.name
  user_data              = file("${path.module}/bootstrap.sh")

  root_block_device {
    volume_size = var.root_volume_size
    volume_type = "gp3"
  }

  # Tags the root volume too, so backup.tf's DLM policy can target it by
  # tag rather than a hardcoded volume ID.
  volume_tags = {
    Backup = "bank-platform"
  }

  tags = {
    Name   = "bank-platform"
    Domain = var.domain
    Backup = "bank-platform"
  }
}
