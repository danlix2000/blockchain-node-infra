# -----------------------------------------------------------------------------
# Ethereum Node Infrastructure
# -----------------------------------------------------------------------------

module "network" {
  source = "../../../../modules/network"

  project_name      = var.project_name
  vpc_cidr          = var.vpc_cidr
  subnet_cidrs      = var.subnet_cidrs
  azs               = var.azs
  allowed_ssh_cidrs = var.allowed_ssh_cidrs
  p2p_allowed_cidrs = var.p2p_allowed_cidrs
  tags              = var.tags
}

# Transform nodes variable to include computed values
locals {
  # Ansible inventory file naming
  inventory_filename  = "${var.chain}_${var.network}_${var.platform}_terraform_state.yml"
  inventory_directory = "${path.module}/../../../../../ansible/inventory"

  # Instance naming: {region}-{chain}-{network}-{node_key}
  # Example: us-east-1-ethereum-mainnet-full
  nodes_with_config = {
    for k, v in var.nodes : k => {
      name                   = "${var.aws_region}-${var.chain}-${var.network}-${k}"
      role                   = try(v.role, var.chain)
      node_type              = try(v.node_type, k == "archive" ? "archive" : "full")
      execution_client       = try(v.execution_client, (try(v.node_type, k == "archive" ? "archive" : "full") == "archive" ? "reth" : "geth"))
      consensus_client       = try(v.consensus_client, (try(v.node_type, k == "archive" ? "archive" : "full") == "archive" ? "lighthouse" : "prysm"))
      instance_type          = v.instance_type
      root_volume_size_gb    = v.root_volume_size_gb
      data_volume_size_gb    = v.data_volume_size_gb
      data_volume_type       = v.data_volume_type
      data_volume_iops       = v.data_volume_iops
      data_volume_throughput = v.data_volume_throughput
      data_device_name       = v.data_device_name
      associate_public_ip    = true
      associate_eip          = try(v.associate_eip, false)
      subnet_id              = module.network.subnet_ids[v.subnet_index]
      domain                 = try(v.domain, "")
    }
  }

  # Per-node security group assignment based on client types
  base_sg_ids = [module.network.ssh_sg_id, module.network.haproxy_sg_id, module.network.p2p_sg_ids["execution"]]

  node_sg_ids = {
    for k, v in local.nodes_with_config : k => distinct(concat(
      local.base_sg_ids,
      v.execution_client == "erigon" ? [module.network.p2p_sg_ids["erigon"]] : [],
      v.consensus_client == "lighthouse" ? [module.network.p2p_sg_ids["lighthouse"]] : [],
      v.consensus_client == "prysm" ? [module.network.p2p_sg_ids["prysm"]] : [],
    ))
  }
}

module "compute" {
  source = "../../../../modules/compute"

  project_name           = var.project_name
  key_name               = var.key_name
  vpc_security_group_ids = local.node_sg_ids
  nodes                  = local.nodes_with_config
  route53_zone_id        = var.route53_zone_id
  tags                   = var.tags
}

# -----------------------------------------------------------------------------
# Route 53 DNS Records
# -----------------------------------------------------------------------------
# Creates A records for nodes with a domain configured.
# Points to effective_public_ip (EIP if attached, else dynamic public IP).

resource "aws_route53_record" "node" {
  for_each = {
    for k, v in local.nodes_with_config : k => v
    if v.domain != ""
  }

  zone_id = var.route53_zone_id
  name    = each.value.domain
  type    = "A"
  ttl     = 300
  records = [module.compute.instances[each.key].effective_public_ip]
}

check "route53_zone_id_required_when_domains_used" {
  assert {
    condition     = length([for n in values(local.nodes_with_config) : n.domain if n.domain != ""]) == 0 || trimspace(var.route53_zone_id) != ""
    error_message = "route53_zone_id must be set when any node has a non-empty domain."
  }
}

# -----------------------------------------------------------------------------
# Ansible Inventory Plugin Configuration
# -----------------------------------------------------------------------------
# Auto-generates the terraform_provider inventory YAML so Ansible can read
# ansible_host resources directly from Terraform state via `terraform show`.

resource "local_file" "ansible_inventory" {
  content = templatefile("${path.module}/ansible_inventory.tmpl.yml", {
    chain    = var.chain
    network  = var.network
    platform = var.platform
  })
  filename        = "${local.inventory_directory}/${local.inventory_filename}"
  file_permission = "0644"
}

resource "ansible_host" "node" {
  for_each = module.compute.instances

  name = each.value.name
  # Note: Do NOT add bare var.chain here. The chain name "ethereum" collides with
  # the Docker role name "ethereum", causing group_vars/ethereum/ to override
  # group_vars/erigon/ on Erigon nodes (Ansible alphabetical precedence).
  # Use chain_${var.chain} for chain-level grouping instead.
  groups = distinct(compact([
    "chain_${var.chain}",
    "network_${var.network}",
    "platform_aws",
    "node_${local.nodes_with_config[each.key].node_type}",
    "execution_${local.nodes_with_config[each.key].execution_client}",
    "consensus_${local.nodes_with_config[each.key].consensus_client}",
    local.nodes_with_config[each.key].role
  ]))
  variables = merge(
    {
      ansible_host      = each.value.effective_public_ip != "" ? each.value.effective_public_ip : each.value.private_ip
      private_ip        = each.value.private_ip
      node_type         = local.nodes_with_config[each.key].node_type
      execution_client  = local.nodes_with_config[each.key].execution_client
      consensus_client  = local.nodes_with_config[each.key].consensus_client
      data_device       = local.nodes_with_config[each.key].data_device_name
      instance_name     = each.value.name
      availability_zone = each.value.availability_zone
      chain             = var.chain
      network           = var.network
      platform          = "aws"
    },
    local.nodes_with_config[each.key].domain != "" ? {
      haproxy_domain = local.nodes_with_config[each.key].domain
    } : {},
    { for k, v in var.tags : "tag_${k}" => v }
  )
}
