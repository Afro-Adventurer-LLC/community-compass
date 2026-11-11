variable "aws_region" {
  description = "Region for the state bucket. Keep it the same as the stack."
  type        = string
  default     = "us-east-1"
}

variable "bucket_name" {
  description = "Name of the state bucket. Empty means abw-tfstate-<account id>."
  type        = string
  default     = ""
}

variable "noncurrent_version_expiration_days" {
  description = "Old state versions are kept this long, then deleted. State is small, so this is cheap insurance."
  type        = number
  default     = 90
}
