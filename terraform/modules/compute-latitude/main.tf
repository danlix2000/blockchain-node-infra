# =============================================================================
# Latitude.sh Bare Metal Servers
# =============================================================================
# Servers are pre-ordered via the Latitude.sh dashboard, then imported into
# Terraform state using the latitude_id field from each node definition.
#
# Workflow:
#   1. Order servers on Latitude.sh dashboard (OS, site, plan; no RAID)
#   2. Copy server IDs (sv_xxx) from dashboard into nodes.tfvars
#   3. Run: terraform init && terraform apply -var-file=nodes.tfvars
#      (Terraform imports existing servers and creates Ansible inventory)
# =============================================================================

resource "latitudesh_server" "node" {
  for_each = var.nodes

  hostname         = each.value.name
  project          = var.project_id
  plan             = each.value.plan
  site             = each.value.site
  operating_system = each.value.operating_system
  ssh_keys         = var.ssh_key_ids
  billing          = each.value.billing
  raid             = each.value.raid

  lifecycle {
    # Prevent SSH key changes from triggering server reinstall.
    # SSH keys should be managed via Ansible after initial provisioning.
    ignore_changes = [ssh_keys]
  }
}
