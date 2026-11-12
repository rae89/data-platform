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
  description = "SSM SecureString holding a Tailscale auth key, e.g. /data-platform/tailscale-auth-key. The instance reads it at boot, so the key stays out of state. Null: no Tailscale; use SSM port forwarding."
  type        = string
  default     = null
}
