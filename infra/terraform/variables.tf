variable "aws_region" {
  description = "AWS region for all resources. It must match the Region of the AWS project."
  type        = string
  default     = "eu-north-1"
}

variable "aws_profile" {
  description = "Local AWS CLI profile that Terraform uses for credentials."
  type        = string
  default     = "sessionly"
}

variable "instance_type" {
  description = "EC2 instance type. t3.small (2 GiB memory) fits the frontend, backend, database and proxy."
  type        = string
  default     = "t3.small"
}

variable "root_volume_size_gb" {
  description = "Size of the encrypted root disk in GiB."
  type        = number
  default     = 20
}

variable "ssh_public_key_path" {
  description = "Path to the public SSH key that is allowed to log in as the ubuntu user."
  type        = string
  default     = "~/.ssh/sessionly.pub"
}

variable "ssh_allowed_cidr" {
  description = "CIDR block allowed to connect over SSH, normally your own IP address with /32."
  type        = string

  validation {
    condition     = can(cidrhost(var.ssh_allowed_cidr, 0)) && var.ssh_allowed_cidr != "0.0.0.0/0"
    error_message = "ssh_allowed_cidr must be a valid CIDR block and must not open SSH to the whole internet."
  }
}
