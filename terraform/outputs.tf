output "instance_id" {
  description = "Use with: aws ssm start-session --target <id>"
  value       = aws_instance.host.id
}

output "data_volume_id" {
  description = "EBS volume that backs /data."
  value       = aws_ebs_volume.data.id
}

output "data_device_hint" {
  description = "Device path to pass to scripts/volume.sh on a Nitro instance."
  value       = "/dev/nvme1n1"
}
