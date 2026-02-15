# -----------------------------------------------------------------------------
# AWS Configuration
# -----------------------------------------------------------------------------

variable "aws_region" {
  type        = string
  description = "AWS region for deployment"
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Project name prefix for all resources"
  default     = "blockchain"
}

variable "chain" {
  type        = string
  description = "Blockchain chain name (ethereum, arbitrum, base, etc.)"
  default     = "ethereum"
}

variable "network" {
  type        = string
  description = "Network name (mainnet, sepolia, etc.)"
  default     = "mainnet"
}

variable "platform" {
  type        = string
  description = "Cloud platform (aws, latitude, ovh, etc.)"
  default     = "aws"
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to all resources"
  default = {
    ManagedBy = "terraform"
  }
}

# -----------------------------------------------------------------------------
# Network Configuration
# -----------------------------------------------------------------------------

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block"
  default     = "10.10.0.0/16"
}

variable "subnet_cidrs" {
  type        = list(string)
  description = "Subnet CIDR blocks for node deployment"
  default     = ["10.10.0.0/24"]
}

variable "azs" {
  type        = list(string)
  description = "Availability zones"
  default     = ["us-east-1a"]
}

# -----------------------------------------------------------------------------
# Security Configuration
# -----------------------------------------------------------------------------

variable "allowed_ssh_cidrs" {
  type        = list(string)
  description = "CIDR blocks allowed for SSH access (e.g., VPN IP ranges)"
  default     = []
}

variable "p2p_allowed_cidrs" {
  type        = list(string)
  description = "CIDR blocks allowed for P2P traffic"
  default     = ["0.0.0.0/0"]
}

variable "key_name" {
  type        = string
  description = "EC2 key pair name for SSH access"
}

# -----------------------------------------------------------------------------
# Node Configuration
# -----------------------------------------------------------------------------
# Define nodes as a map. Each node specifies its own configuration.
# The key becomes the hostname in Ansible inventory.
# The 'role' attribute determines the Ansible group.
# -----------------------------------------------------------------------------

variable "nodes" {
  type = map(object({
    role                   = optional(string)
    node_type              = optional(string)
    execution_client       = optional(string)
    consensus_client       = optional(string)
    instance_type          = string
    root_volume_size_gb    = number
    data_volume_size_gb    = number
    data_volume_type       = optional(string, "gp3")
    data_volume_iops       = optional(number, 3000)
    data_volume_throughput = optional(number, 125)
    data_device_name       = optional(string, "/dev/sdf")
    subnet_index           = optional(number, 0)
    associate_eip          = optional(bool, false)
    domain                 = optional(string, "")
  }))
  description = "Map of nodes to deploy. Key = hostname"
  default     = {}
}

# -----------------------------------------------------------------------------
# DNS Configuration (Route 53)
# -----------------------------------------------------------------------------

variable "route53_zone_id" {
  type        = string
  description = "Route 53 hosted zone ID for HAProxy A records. Required if any node has a domain."
  default     = ""

  validation {
    condition     = var.route53_zone_id == "" || can(regex("^Z[A-Z0-9]+$", var.route53_zone_id))
    error_message = "route53_zone_id must be a valid Route 53 hosted zone ID like Z0123456789ABCDEF."
  }
}
