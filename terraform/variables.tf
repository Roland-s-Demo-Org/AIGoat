variable "vpc_cidr" {
  default = "10.0.0.0/16"
}

#variable "profile" {
#  description = "AWS Profile Name"
#  default = "ofir_demo_profile"
#}

variable "region" {
  description = "AWS Region Name"
  default = "us-east-1"
}

variable "ssh_public_key" {
  description = "SSH public key for EC2 instance access. Must be provided via environment variable (TF_VAR_ssh_public_key) or terraform.tfvars. Never commit this to version control."
  type        = string
  sensitive   = true
}

variable "ssh_allowed_cidr_blocks" {
  description = "CIDR blocks allowed to SSH to the EC2 instance. Leave empty to disable SSH access entirely. Restrict to known IP ranges for security."
  type        = list(string)
  default     = []
}

variable "backend_deployment_bucket" {
  description = "S3 bucket containing the backend application code archive (backend.zip). If not provided, backend code must be baked into the AMI."
  type        = string
  default     = ""
}

variable "backend_deployment_key" {
  description = "S3 key for the backend application code archive"
  type        = string
  default     = "backend.zip"
}