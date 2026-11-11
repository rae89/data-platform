# One EC2 instance runs the whole stack with `docker compose` (DuckDB wants one machine).
# No inbound ports: the public reaches services through Cloudflare Access (public.tf);
# admins also have Tailscale, and a shell via SSM Session Manager.

data "aws_ec2_instance_type" "this" {
  instance_type = var.instance_type
}

locals {
  # Canonical names the x86 build "amd64".
  arch = contains(data.aws_ec2_instance_type.this.supported_architectures, "arm64") ? "arm64" : "amd64"
}

data "aws_ssm_parameter" "ubuntu_ami" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/${local.arch}/hvm/ebs-gp3/ami-id"
}

# Default VPC: a public subnet with an internet gateway, so outbound traffic needs no
# NAT gateway (about $32/month).
data "aws_vpc" "default" {
  default = true
}

data "aws_ssm_parameter" "tailscale_auth_key" {
  name            = var.tailscale_auth_key_parameter
  with_decryption = false # only checks it exists and gets its ARN; the value stays out of state
}

resource "aws_security_group" "this" {
  name        = "data-platform-${var.env}"
  description = "data-platform: outbound only; services are reached over Tailscale"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_iam_role" "this" {
  name = "data-platform-${var.env}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Session Manager shell: the fallback when Tailscale isn't up (e.g. a failed boot script).
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "boot_secrets" {
  name = "read-boot-secrets"
  role = aws_iam_role.this.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "ssm:GetParameter"
      Resource = concat([data.aws_ssm_parameter.tailscale_auth_key.arn], aws_ssm_parameter.tunnel_token[*].arn)
    }]
  })
}

resource "aws_iam_instance_profile" "this" {
  name = "data-platform-${var.env}"
  role = aws_iam_role.this.name
}

resource "aws_instance" "this" {
  ami                         = data.aws_ssm_parameter.ubuntu_ami.value
  instance_type               = var.instance_type
  vpc_security_group_ids      = [aws_security_group.this.id]
  iam_instance_profile        = aws_iam_instance_profile.this.name
  associate_public_ip_address = true # outbound internet without a NAT gateway; no ports are open
  user_data = templatefile("${path.module}/user_data.sh", {
    region              = var.region
    tailscale_key_param = var.tailscale_auth_key_parameter
    tailscale_hostname  = "data-platform-${var.env}"
    tunnel_token_param  = one(aws_ssm_parameter.tunnel_token[*].name) # null without a domain
  })

  dynamic "instance_market_options" {
    for_each = var.spot ? [1] : []
    content {
      market_type = "spot"
      spot_options {
        # Persistent + stop: the disk survives an interruption and the instance starts
        # again when capacity returns. "terminate" would delete the data.
        spot_instance_type             = "persistent"
        instance_interruption_behavior = "stop"
      }
    }
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.disk_gb
    encrypted   = true
  }

  metadata_options {
    http_tokens = "required" # IMDSv2 only
  }

  tags = {
    Name = "data-platform-${var.env}"
  }

  lifecycle {
    # New Ubuntu AMIs are published often; don't replace the server (and its data) for one.
    ignore_changes = [ami, user_data]
  }
}
