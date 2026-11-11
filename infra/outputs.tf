output "instance_id" {
  value = aws_instance.this.id
}

output "tailscale_hostname" {
  description = "Open the portal at http://<this>:3002 once the instance has joined your tailnet."
  value       = "data-platform-${var.env}"
}

output "ssm_shell" {
  description = "Shell without Tailscale (needs the Session Manager plugin for the AWS CLI)."
  value       = "aws ssm start-session --region ${var.region} --target ${aws_instance.this.id}"
}

output "urls" {
  description = "Public URLs, behind Google sign-in."
  value       = { for name, host in local.hostnames : name => "https://${host}" }
}
