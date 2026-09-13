# Terraform + AWS provider setup for the bank-platform deployment target
# (AWS EC2, Phase 7's real Linux Docker host - see CLAUDE.md's "Deploying"
# section). State is local (terraform.tfstate, gitignored) - a single
# instance managed by one person doesn't warrant a remote S3/DynamoDB
# backend; revisit only if this becomes a team-managed setup.

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Credentials come from the environment / ~/.aws/credentials (same as the
# aws CLI already configured on this machine) - never hardcoded here, same
# spirit as .env never being committed.
provider "aws" {
  region = var.region
}
