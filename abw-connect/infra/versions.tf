terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # The S3 Vectors resources and the S3_VECTORS knowledge-base storage type
      # need a recent 6.x provider.
      version = ">= 6.20.0, < 7.0.0"
    }
    time = {
      source  = "hashicorp/time"
      version = ">= 0.12.0"
    }
  }
}
