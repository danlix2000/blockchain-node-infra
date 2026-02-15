# -----------------------------------------------------------------------------
# Compute Outputs
# -----------------------------------------------------------------------------

output "server_info" {
  description = "Bare metal server details"
  value       = module.compute.servers
}

output "server_ids" {
  description = "Server IDs"
  value       = { for k, v in module.compute.servers : k => v.server_id }
}

# -----------------------------------------------------------------------------
# Ansible Outputs
# -----------------------------------------------------------------------------

output "ansible_inventory_file" {
  description = "Path to generated Ansible inventory file"
  value       = local_file.ansible_inventory.filename
}
