output "instance_id" {
  description = "EC2 instance ID - useful for aws ssm start-session --target <id>."
  value       = aws_instance.app.id
}

output "public_ip" {
  description = "The Elastic IP - point the domain's A record at this."
  value       = aws_eip.app.public_ip
}
