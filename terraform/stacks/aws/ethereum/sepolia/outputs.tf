# -----------------------------------------------------------------------------
# Network Outputs
# -----------------------------------------------------------------------------

output "vpc_id" {
  description = "VPC ID"
  value       = module.network.vpc_id
}

output "subnet_ids" {
  description = "Subnet IDs"
  value       = module.network.subnet_ids
}

# -----------------------------------------------------------------------------
# Compute Outputs
# -----------------------------------------------------------------------------

output "instance_info" {
  description = "EC2 instance details"
  value       = module.compute.instances
}

output "instance_ids" {
  description = "EC2 instance IDs"
  value       = { for k, v in module.compute.instances : k => v.instance_id }
}

# -----------------------------------------------------------------------------
# Ansible Outputs
# -----------------------------------------------------------------------------

output "ansible_inventory_file" {
  description = "Path to generated Ansible inventory file"
  value       = local_file.ansible_inventory.filename
}

# -----------------------------------------------------------------------------
# DNS Outputs
# -----------------------------------------------------------------------------

output "dns_records" {
  description = "Route 53 A records created for nodes with domains"
  value = {
    for k, v in aws_route53_record.node : k => {
      fqdn = v.fqdn
      ip   = tolist(v.records)[0]
    }
  }
}
