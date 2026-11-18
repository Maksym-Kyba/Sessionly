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

variable "ssh_allowed_cidrs" {
  description = "CIDR blocks allowed to connect over SSH, normally each administrator's own IP address with /32."
  type        = list(string)

  validation {
    condition     = length(var.ssh_allowed_cidrs) > 0
    error_message = "ssh_allowed_cidrs must contain at least one CIDR block."
  }

  # cidrnetmask accepts IPv4 prefixes only, so IPv6 blocks such as ::/0 are rejected.
  validation {
    condition = alltrue([
      for cidr in var.ssh_allowed_cidrs : can(cidrnetmask(cidr)) && cidr != "0.0.0.0/0"
    ])
    error_message = "ssh_allowed_cidrs must contain IPv4 CIDR blocks only and must not open SSH to the whole internet."
  }

  # A canonical block has no host bits set, for example 203.0.113.0/24 rather than 203.0.113.7/24.
  validation {
    condition = alltrue([
      for cidr in var.ssh_allowed_cidrs : try(cidrsubnet(cidr, 0, 0) == cidr, false)
    ])
    error_message = "ssh_allowed_cidrs must use canonical network addresses, for example 203.0.113.7/32 or 203.0.113.0/24."
  }

  validation {
    condition     = length(distinct(var.ssh_allowed_cidrs)) == length(var.ssh_allowed_cidrs)
    error_message = "ssh_allowed_cidrs must not contain duplicate entries."
  }
}
