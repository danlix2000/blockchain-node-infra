variable "project_id" {
  type        = string
  description = "Latitude.sh project ID"
}

variable "ssh_key_ids" {
  type        = list(string)
  description = "Latitude.sh SSH key IDs (from dashboard: Account > SSH Keys)"
}

variable "nodes" {
  type = map(object({
    name             = string
    role             = string
    node_type        = optional(string, "full")
    execution_client = optional(string, "geth")
    consensus_client = optional(string, "prysm")
    latitude_id      = string
    latitude_label   = string
    plan             = string
    site             = string
    operating_system = optional(string, "ubuntu_24_04_x64_lts")
    billing          = optional(string, "hourly")
    raid             = optional(string)
    data_device      = optional(string, "/dev/md127")
  }))

  description = "Pre-ordered Latitude.sh bare metal servers to import and manage"
  default     = {}
}

variable "tags" {
  type        = map(string)
  description = "Global tags"
  default     = {}
}
