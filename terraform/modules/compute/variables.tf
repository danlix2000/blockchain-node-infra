variable "project_name" {
  type        = string
  description = "Project name prefix"
}

variable "key_name" {
  type        = string
  description = "EC2 key pair name"
}

variable "vpc_security_group_ids" {
  type        = map(list(string))
  description = "Security group IDs per node (key = node key from var.nodes)"
}

variable "nodes" {
  type = map(object({
    name                   = string
    role                   = string
    node_type              = optional(string, "full")
    execution_client       = optional(string, "geth")
    consensus_client       = optional(string, "prysm")
    instance_type          = string
    root_volume_size_gb    = number
    data_volume_size_gb    = number
    data_volume_type       = string
    data_volume_iops       = number
    data_volume_throughput = number
    data_device_name       = string
    associate_public_ip    = bool
    associate_eip          = optional(bool, false)
    subnet_id              = string
    domain                 = optional(string, "")
  }))

  description = "Node definitions"
}

variable "route53_zone_id" {
  type        = string
  description = "Route 53 hosted zone ID. Used to scope Certbot IAM permissions."
  default     = ""
}

variable "tags" {
  type        = map(string)
  description = "Global tags"
  default     = {}
}
