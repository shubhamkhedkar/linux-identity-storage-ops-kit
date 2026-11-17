terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "linux-identity-storage-ops-kit"
      ManagedBy = "terraform"
      Owner     = var.owner
    }
  }
}
