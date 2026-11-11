provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "abw-connect"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition

  lambda_name = "${var.name_prefix}-api"

  permissions_boundary_arn = var.permissions_boundary_name != "" ? "arn:${local.partition}:iam::${local.account_id}:policy/${var.permissions_boundary_name}" : null

  kb_bucket_name = var.kb_bucket_name != "" ? var.kb_bucket_name : "${var.name_prefix}-kb-${local.account_id}"

  frontend_origin = var.create_amplify ? "https://main.${aws_amplify_app.frontend[0].default_domain}" : var.frontend_origin
  cors_origins    = compact(concat([local.frontend_origin], var.extra_cors_origins))

  # Document files are uploaded as-is; the same extensions as scripts/upload_kb.py.
  kb_files = var.upload_kb ? toset([
    for f in fileset(var.kb_source_dir, "**") : f
    if contains([".md", ".json", ".txt", ".html", ".pdf"], lower(try(regex("\\.[^.]+$", f), "")))
  ]) : toset([])
}
