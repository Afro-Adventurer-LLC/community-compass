# Source documents for the knowledge base (data source prefix kb/).
resource "aws_s3_bucket" "kb" {
  bucket        = local.kb_bucket_name
  force_destroy = var.kb_force_destroy
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "kb" {
  bucket = aws_s3_bucket.kb.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "kb" {
  bucket                  = aws_s3_bucket.kb.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "kb" {
  bucket = aws_s3_bucket.kb.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# kb/ is uploaded with the same layout as scripts/upload_kb.py:
# kb/official/2026/*.md, kb/alumni/*.md and a *.metadata.json sidecar per document.
resource "aws_s3_object" "kb" {
  for_each = local.kb_files

  bucket       = aws_s3_bucket.kb.id
  key          = "kb/${each.value}"
  source       = "${var.kb_source_dir}/${each.value}"
  etag         = filemd5("${var.kb_source_dir}/${each.value}")
  content_type = endswith(each.value, ".json") ? "application/json" : (endswith(each.value, ".md") ? "text/markdown" : "text/plain; charset=utf-8")
}
