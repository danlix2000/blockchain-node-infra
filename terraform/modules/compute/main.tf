data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

locals {
  route53_zone_arn = var.route53_zone_id != "" ? "arn:aws:route53:::hostedzone/${trimspace(var.route53_zone_id)}" : "arn:aws:route53:::hostedzone/*"
}

# -----------------------------------------------------------------------------
# IAM Instance Profile - Route 53 access for Certbot DNS-01 challenge
# Permissions are scoped to route53_zone_id when provided.
# -----------------------------------------------------------------------------

resource "aws_iam_role" "node" {
  name = "${var.project_name}-node"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_policy" "route53_certbot" {
  name        = "${var.project_name}-route53-certbot"
  description = "Certbot DNS-01 challenge via Route 53"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["route53:GetChange"]
        Resource = "arn:aws:route53:::change/*"
      },
      {
        Effect   = "Allow"
        Action   = ["route53:ListHostedZones", "route53:ListHostedZonesByName"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["route53:ChangeResourceRecordSets"]
        Resource = local.route53_zone_arn
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "route53_certbot" {
  role       = aws_iam_role.node.name
  policy_arn = aws_iam_policy.route53_certbot.arn
}

resource "aws_iam_instance_profile" "node" {
  name = "${var.project_name}-node"
  role = aws_iam_role.node.name
  tags = var.tags
}

# -----------------------------------------------------------------------------
# EC2 Instances
# -----------------------------------------------------------------------------

resource "aws_instance" "node" {
  for_each = var.nodes

  ami                         = data.aws_ami.ubuntu.id
  instance_type               = each.value.instance_type
  subnet_id                   = each.value.subnet_id
  vpc_security_group_ids      = var.vpc_security_group_ids[each.key]
  key_name                    = var.key_name
  associate_public_ip_address = each.value.associate_public_ip
  iam_instance_profile        = aws_iam_instance_profile.node.name
  ebs_optimized               = true

  root_block_device {
    volume_size = each.value.root_volume_size_gb
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = merge(var.tags, {
    Name            = each.value.name
    Role            = each.value.role
    NodeType        = each.value.node_type
    ExecutionClient = each.value.execution_client
    ConsensusClient = each.value.consensus_client
  })
}

resource "aws_eip" "node" {
  for_each = {
    for k, v in var.nodes : k => v
    if v.associate_eip
  }

  domain = "vpc"

  tags = merge(var.tags, {
    Name = "${each.value.name}-eip"
    Role = each.value.role
  })
}

resource "aws_eip_association" "node" {
  for_each = aws_eip.node

  instance_id   = aws_instance.node[each.key].id
  allocation_id = each.value.id
}

resource "aws_ebs_volume" "data" {
  for_each = var.nodes

  availability_zone = aws_instance.node[each.key].availability_zone
  size              = each.value.data_volume_size_gb
  type              = each.value.data_volume_type
  iops              = each.value.data_volume_iops
  throughput        = each.value.data_volume_throughput
  encrypted         = true

  tags = merge(var.tags, {
    Name = "${each.value.name}-data"
    Role = each.value.role
  })
}

resource "aws_volume_attachment" "data" {
  for_each = var.nodes

  device_name = each.value.data_device_name
  volume_id   = aws_ebs_volume.data[each.key].id
  instance_id = aws_instance.node[each.key].id
}
