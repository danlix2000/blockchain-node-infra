variable "project_name" {
  type        = string
  description = "Project name prefix"
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR"
}

variable "subnet_cidrs" {
  type        = list(string)
  description = "Subnet CIDRs for node deployment"
}

variable "azs" {
  type        = list(string)
  description = "Availability zones"
}

variable "allowed_ssh_cidrs" {
  type        = list(string)
  description = "Allowed CIDRs for SSH (VPN egress IPs)"
}

variable "p2p_allowed_cidrs" {
  type        = list(string)
  description = "Allowed CIDRs for P2P ports"
}

variable "tags" {
  type        = map(string)
  description = "Global tags"
  default     = {}
}
