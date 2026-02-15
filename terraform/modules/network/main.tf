resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(var.tags, {
    Name = "${var.project_name}-vpc"
  })
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id

  tags = merge(var.tags, {
    Name = "${var.project_name}-igw"
  })
}

resource "aws_subnet" "main" {
  for_each = { for idx, cidr in var.subnet_cidrs : idx => cidr }

  vpc_id                  = aws_vpc.main.id
  cidr_block              = each.value
  availability_zone       = var.azs[each.key]
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name = "${var.project_name}-subnet-${each.key}"
  })
}

resource "aws_route_table" "main" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-rt"
  })
}

resource "aws_route_table_association" "main" {
  for_each = aws_subnet.main

  subnet_id      = each.value.id
  route_table_id = aws_route_table.main.id
}

resource "aws_security_group" "ssh" {
  name        = "${var.project_name}-ssh"
  description = "SSH access from bastion hosts"
  vpc_id      = aws_vpc.main.id

  dynamic "ingress" {
    for_each = var.allowed_ssh_cidrs
    content {
      description = "SSH"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-ssh"
  })
}

# -----------------------------------------------------------------------------
# P2P Security Groups (per-client)
# -----------------------------------------------------------------------------
# Each client gets its own SG with only the ports it needs.
# Nodes are assigned SGs based on their execution_client and consensus_client.

resource "aws_security_group" "p2p_execution" {
  name        = "${var.project_name}-p2p-execution"
  description = "Execution layer P2P (30303 tcp/udp) - all EL clients"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Execution P2P TCP (eth/68)"
    from_port   = 30303
    to_port     = 30303
    protocol    = "tcp"
    cidr_blocks = var.p2p_allowed_cidrs
  }

  ingress {
    description = "Execution P2P UDP (eth/68)"
    from_port   = 30303
    to_port     = 30303
    protocol    = "udp"
    cidr_blocks = var.p2p_allowed_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-p2p-execution"
  })
}

resource "aws_security_group" "p2p_erigon" {
  name        = "${var.project_name}-p2p-erigon"
  description = "Erigon+Caplin extra P2P (30304, 42069, 4000, 4001)"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Erigon eth/69 TCP"
    from_port   = 30304
    to_port     = 30304
    protocol    = "tcp"
    cidr_blocks = var.p2p_allowed_cidrs
  }

  ingress {
    description = "Erigon eth/69 UDP"
    from_port   = 30304
    to_port     = 30304
    protocol    = "udp"
    cidr_blocks = var.p2p_allowed_cidrs
  }

  ingress {
    description = "Erigon torrent/snap TCP"
    from_port   = 42069
    to_port     = 42069
    protocol    = "tcp"
    cidr_blocks = var.p2p_allowed_cidrs
  }

  ingress {
    description = "Erigon torrent/snap UDP"
    from_port   = 42069
    to_port     = 42069
    protocol    = "udp"
    cidr_blocks = var.p2p_allowed_cidrs
  }

  ingress {
    description = "Caplin CL discovery UDP"
    from_port   = 4000
    to_port     = 4000
    protocol    = "udp"
    cidr_blocks = var.p2p_allowed_cidrs
  }

  ingress {
    description = "Caplin CL discovery TCP"
    from_port   = 4001
    to_port     = 4001
    protocol    = "tcp"
    cidr_blocks = var.p2p_allowed_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-p2p-erigon"
  })
}

resource "aws_security_group" "p2p_lighthouse" {
  name        = "${var.project_name}-p2p-lighthouse"
  description = "Lighthouse CL P2P (9000 tcp/udp, 9001 udp QUIC)"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Lighthouse P2P TCP"
    from_port   = 9000
    to_port     = 9000
    protocol    = "tcp"
    cidr_blocks = var.p2p_allowed_cidrs
  }

  ingress {
    description = "Lighthouse P2P UDP"
    from_port   = 9000
    to_port     = 9000
    protocol    = "udp"
    cidr_blocks = var.p2p_allowed_cidrs
  }

  ingress {
    description = "Lighthouse QUIC UDP"
    from_port   = 9001
    to_port     = 9001
    protocol    = "udp"
    cidr_blocks = var.p2p_allowed_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-p2p-lighthouse"
  })
}

resource "aws_security_group" "p2p_prysm" {
  name        = "${var.project_name}-p2p-prysm"
  description = "Prysm CL P2P (13000 tcp, 12000 udp)"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Prysm P2P TCP"
    from_port   = 13000
    to_port     = 13000
    protocol    = "tcp"
    cidr_blocks = var.p2p_allowed_cidrs
  }

  ingress {
    description = "Prysm P2P UDP"
    from_port   = 12000
    to_port     = 12000
    protocol    = "udp"
    cidr_blocks = var.p2p_allowed_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-p2p-prysm"
  })
}

resource "aws_security_group" "haproxy" {
  name        = "${var.project_name}-haproxy"
  description = "HAProxy HTTP/HTTPS (public)"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP (redirect to HTTPS)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS (TLS + API key auth)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-haproxy"
  })
}
