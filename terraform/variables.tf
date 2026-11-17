variable "region" {
  description = "AWS region for the lab host."
  type        = string
  default     = "ap-south-1"
}

variable "owner" {
  description = "Owner tag value."
  type        = string
  default     = "shubhamkhedkar"
}

variable "vpc_id" {
  description = "Existing VPC to place the host in."
  type        = string
}

variable "subnet_id" {
  description = "Private subnet for the host (reach it with SSM Session Manager, not SSH)."
  type        = string
}

variable "egress_cidrs" {
  description = "CIDRs the host may reach on 443 (VPC endpoints or a NAT egress range)."
  type        = list(string)

  validation {
    condition     = length(var.egress_cidrs) > 0 && alltrue([for c in var.egress_cidrs : can(cidrnetmask(c))])
    error_message = "egress_cidrs must be a non-empty list of valid IPv4 CIDRs."
  }
}

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "t3.micro"
}

variable "data_volume_size_gib" {
  description = "Size of the dedicated /data EBS volume."
  type        = number
  default     = 5

  validation {
    condition     = var.data_volume_size_gib >= 1 && var.data_volume_size_gib <= 1024
    error_message = "data_volume_size_gib must be between 1 and 1024."
  }
}

variable "data_device_name" {
  description = "Attachment device name. On Nitro instances it shows up as /dev/nvme1n1."
  type        = string
  default     = "/dev/sdf"
}
