output "bucket" {
  description = "Value for the TF_STATE_BUCKET GitHub variable and for -backend-config=bucket=..."
  value       = aws_s3_bucket.state.bucket
}

output "region" {
  value = var.aws_region
}
