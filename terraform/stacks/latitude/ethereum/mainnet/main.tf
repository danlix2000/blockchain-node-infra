# -----------------------------------------------------------------------------
# Ethereum Node Infrastructure (Latitude.sh Bare Metal)
# -----------------------------------------------------------------------------

# Transform nodes variable to include computed values
locals {
  # Ansible inventory file naming
  inventory_filename  = "${var.chain}_${var.network}_${var.platform}_terraform_state.yml"
  inventory_directory = "${path.module}/../../../../../ansible/inventory"

  # Instance naming: {site}-{chain}-{network}-{node_key}
  # Example: chi-ethereum-mainnet-full
  nodes_with_config = {
    for k, v in var.nodes : k => {
      name             = "${lower(v.site)}-${var.chain}-${var.network}-${k}"
      role             = try(v.role, var.chain)
      node_type        = try(v.node_type, k == "archive" ? "archive" : "full")
      execution_client = try(v.execution_client, (try(v.node_type, k == "archive" ? "archive" : "full") == "archive" ? "reth" : "geth"))
      consensus_client = try(v.consensus_client, (try(v.node_type, k == "archive" ? "archive" : "full") == "archive" ? "lighthouse" : "prysm"))
      latitude_id      = v.latitude_id
      latitude_label   = v.latitude_label
      plan             = v.plan
      site             = v.site
      operating_system = v.operating_system
      billing          = v.billing
      raid             = v.raid
      data_device      = v.data_device
    }
  }
}

# Import pre-ordered servers into Terraform state
import {
  for_each = local.nodes_with_config
  to       = module.compute.latitudesh_server.node[each.key]
  id       = each.value.latitude_id
}

module "compute" {
  source = "../../../../modules/compute-latitude"

  project_id  = var.project_id
  ssh_key_ids = var.ssh_key_ids
  nodes       = local.nodes_with_config
  tags        = var.tags
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
  for_each = module.compute.servers

  name = each.value.name
  # Note: Do NOT add bare var.chain here. The chain name "ethereum" collides with
  # the Docker role name "ethereum", causing group_vars/ethereum/ to override
  # group_vars/erigon/ on Erigon nodes (Ansible alphabetical precedence).
  # Use chain_${var.chain} for chain-level grouping instead.
  groups = distinct(compact([
    "chain_${var.chain}",
    "network_${var.network}",
    "platform_${var.platform}",
    "node_${local.nodes_with_config[each.key].node_type}",
    "execution_${local.nodes_with_config[each.key].execution_client}",
    "consensus_${local.nodes_with_config[each.key].consensus_client}",
    local.nodes_with_config[each.key].role
  ]))
  variables = merge(
    {
      ansible_host     = each.value.primary_ipv4
      node_type        = local.nodes_with_config[each.key].node_type
      execution_client = local.nodes_with_config[each.key].execution_client
      consensus_client = local.nodes_with_config[each.key].consensus_client
      data_device      = local.nodes_with_config[each.key].data_device
      instance_name    = each.value.name
      site             = each.value.site
      plan             = each.value.plan
      server_id        = each.value.server_id
      latitude_label   = each.value.latitude_label
      chain            = var.chain
      network          = var.network
      platform         = var.platform
    },
    { for k, v in var.tags : "tag_${k}" => v }
  )
}
