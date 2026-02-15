output "instances" {
  description = "Map of instance details keyed by node name"
  value = {
    for k, inst in aws_instance.node : k => {
      instance_id         = inst.id
      name                = inst.tags["Name"]
      role                = var.nodes[k].role
      node_type           = try(var.nodes[k].node_type, null)
      execution_client    = try(var.nodes[k].execution_client, null)
      consensus_client    = try(var.nodes[k].consensus_client, null)
      public_ip           = inst.public_ip
      eip_public_ip       = try(aws_eip.node[k].public_ip, "")
      effective_public_ip = try(aws_eip.node[k].public_ip, inst.public_ip)
      private_ip          = inst.private_ip
      availability_zone   = inst.availability_zone
      data_device         = var.nodes[k].data_device_name
    }
  }
}

output "instance_ids" {
  description = "List of instance IDs"
  value       = [for inst in aws_instance.node : inst.id]
}
