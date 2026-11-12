output "instance_id" {
  value = aws_instance.this.id
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
