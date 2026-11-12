output "instance_id" {
  value = aws_instance.this.id
}

output "tailscale_hostname" {
  description = "With Tailscale: open the portal at http://<this>:3002."
  value       = var.tailscale_auth_key_parameter != null ? "data-platform-${var.env}" : null
}

output "ssm_shell" {
  description = "Shell on the instance (needs the Session Manager plugin for the AWS CLI)."
  value       = "aws ssm start-session --region ${var.region} --target ${aws_instance.this.id}"
}

output "port_forward" {
  description = "Forward one service to localhost (portal shown); change both port numbers for others."
  value       = "aws ssm start-session --region ${var.region} --target ${aws_instance.this.id} --document-name AWS-StartPortForwardingSession --parameters portNumber=3002,localPortNumber=3002"
}

output "urls" {
  description = "Public URLs, behind Google sign-in."
  value       = { for name, host in local.hostnames : name => "https://${host}" }
}

output "cf_access" {
  description = "Superset's CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD (.env on the server), to sign in with Access."
  value = local.public ? {
    team_domain = regex("^https://([^/]+)/", cloudflare_zero_trust_access_identity_provider.google[0].config.redirect_url)[0]
    aud         = cloudflare_zero_trust_access_application.this[0].aud
  } : null
}
