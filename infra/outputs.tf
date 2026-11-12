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
