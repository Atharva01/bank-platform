variable "region" {
  description = "AWS region for the deployment. Matches the region already configured in ~/.aws/config on the dev machine."
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type. t4g.small (Graviton/ARM, 2 vCPU/2GB) is cheaper than the x86 t3.small equivalent for this workload - nothing in the stack requires x86."
  type        = string
  default     = "t4g.small"
}

variable "root_volume_size" {
  description = "Root EBS volume size in GB. AL2023's default (8GB) is too small once Docker images, Postgres data, and Traefik's ACME certificate storage are all on the same volume."
  type        = number
  default     = 30
}

# No defaults for domain/acme_email - must be supplied via terraform.tfvars
# (see terraform.tfvars.example), mirroring .env.example's placeholders.
variable "domain" {
  description = "The real domain this deployment serves (used only for tagging/output convenience - Traefik itself reads DOMAIN from the app's own .env, not from Terraform)."
  type        = string
}

variable "acme_email" {
  description = "Email for Let's Encrypt ACME registration (used only for tagging/output convenience - Traefik itself reads ACME_EMAIL from the app's own .env, not from Terraform)."
  type        = string
}
