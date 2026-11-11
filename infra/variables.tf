variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "env" {
  description = "Environment name; tags every resource and becomes PLATFORM_ENV."
  type        = string
  default     = "prod"
}

variable "instance_type" {
  description = "EC2 type. 8 GB RAM fits the stack. The AMI follows its architecture (arm64 or x86_64); Lightdash only ships amd64."
  type        = string
  default     = "t4g.large"
}

variable "spot" {
  description = "Run as a persistent spot instance that stops (not terminates) on interruption. About a third of on-demand; expect occasional outages."
  type        = bool
  default     = true
}

variable "disk_gb" {
  description = "Root volume size. Images take about 8 GB; data and volumes about 1 GB today."
  type        = number
  default     = 40
}

variable "tailscale_auth_key_parameter" {
  description = "SSM SecureString holding a Tailscale auth key, e.g. /data-platform/tailscale-auth-key. The instance reads it at boot, so the key stays out of Terraform state. Null: no Tailscale; use SSM port forwarding."
  type        = string
  default     = null
}

# Public access (public.tf). Leave `domain` unset for a Tailscale-only deploy; the
# rest is then unused. With a domain, set CLOUDFLARE_API_TOKEN in the environment.

variable "domain" {
  description = "Cloudflare zone (e.g. example.com). Services get <prefix><name>.<domain>. Null: no public access."
  type        = string
  default     = null
}

variable "hostname_prefix" {
  description = "Prefix for every hostname, e.g. \"dp-\" gives dp-dagster.example.com."
  type        = string
  default     = ""
}

variable "cloudflare_account_id" {
  description = "Cloudflare account that owns the zone and Zero Trust."
  type        = string
  default     = null
}

variable "allowed_emails" {
  description = "Google accounts allowed to sign in."
  type        = list(string)
  default     = []
}

variable "google_client_id" {
  description = "OAuth client ID of a Google Cloud \"Web application\" client."
  type        = string
  default     = null
}

variable "google_client_secret" {
  description = "Its secret. Pass with TF_VAR_google_client_secret (e.g. from 1Password via op run)."
  type        = string
  default     = null
  sensitive   = true
}
