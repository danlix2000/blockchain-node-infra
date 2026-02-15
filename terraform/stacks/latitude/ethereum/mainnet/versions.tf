# =============================================================================
# Terraform Configuration
# =============================================================================
# Remote State: Copy cloud.tf.example to cloud.tf and configure your
# HCP Terraform (Terraform Cloud) organization and workspace.
# See: https://developer.hashicorp.com/terraform/cli/cloud/settings
# =============================================================================

terraform {
  required_version = ">= 1.10"

  required_providers {
    latitudesh = {
      source  = "latitudesh/latitudesh"
      version = "~> 2.5.0"
    }
    ansible = {
      source  = "ansible/ansible"
      version = "~> 1.3.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}

# Auth via LATITUDESH_AUTH_TOKEN environment variable
provider "latitudesh" {}
