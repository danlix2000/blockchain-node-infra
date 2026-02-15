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
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
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

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}
