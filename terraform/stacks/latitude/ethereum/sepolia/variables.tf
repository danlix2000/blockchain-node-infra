# -----------------------------------------------------------------------------
# Latitude Configuration
# -----------------------------------------------------------------------------

variable "project_id" {
  type        = string
  description = "Latitude.sh project ID (from dashboard)"
}

variable "project_name" {
  type        = string
  description = "Latitude.sh project name (from dashboard: Projects)"
}

variable "chain" {
  type        = string
  description = "Blockchain chain name (ethereum, arbitrum, base, etc.)"
  default     = "ethereum"
}

variable "network" {
  type        = string
  description = "Network name (mainnet, sepolia, etc.)"
  default     = "sepolia"
}

variable "platform" {
  type        = string
  description = "Cloud platform (aws, latitude, ovh, etc.)"
  default     = "latitude"
}

variable "ssh_key_ids" {
  type        = list(string)
  description = "Latitude.sh SSH key IDs (from dashboard: Account > SSH Keys)"
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to all resources"
  default = {
    ManagedBy = "terraform"
  }
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
    role             = optional(string)
    node_type        = optional(string)
    execution_client = optional(string)
    consensus_client = optional(string)
    latitude_id      = string
    latitude_label   = string
    plan             = string
    site             = string
    operating_system = optional(string, "ubuntu_24_04_x64_lts")
    billing          = optional(string, "hourly")
    raid             = optional(string)
    data_device      = optional(string, "/dev/md127")
  }))
  description = "Pre-ordered Latitude.sh bare metal servers. Key = node name"
  default     = {}
}
