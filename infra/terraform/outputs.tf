output "public_ip" {
  description = "Static public IP address of the application server."
  value       = aws_eip.app.public_ip
}

output "site_domain" {
  description = "Free sslip.io hostname that resolves to the server; use it as SITE_DOMAIN."
  value       = "${replace(aws_eip.app.public_ip, ".", "-")}.sslip.io"
}

output "ssh_command" {
  description = "Command for connecting to the server."
  value       = "ssh -i ~/.ssh/sessionly ubuntu@${aws_eip.app.public_ip}"
}
