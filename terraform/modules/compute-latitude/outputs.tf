output "servers" {
  description = "Map of server details keyed by node name"
  value = {
    for k, srv in latitudesh_server.node : k => {
      server_id      = srv.id
      name           = var.nodes[k].name
      primary_ipv4   = srv.primary_ipv4
      site           = srv.site
      plan           = srv.plan
      latitude_label = var.nodes[k].latitude_label
      data_device    = var.nodes[k].data_device
    }
  }
}

output "server_ids" {
  description = "List of server IDs"
  value       = [for srv in latitudesh_server.node : srv.id]
}
