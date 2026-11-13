# Vector store: Amazon S3 Vectors (same as live; no OpenSearch Serverless, so no
# always-on collection cost).
resource "aws_s3vectors_vector_bucket" "kb" {
  vector_bucket_name = "${var.name_prefix}-vectors"
  force_destroy      = var.kb_force_destroy

  encryption_configuration {
    sse_type = "AES256"
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3vectors_index" "kb" {
  vector_bucket_name = aws_s3vectors_vector_bucket.kb.vector_bucket_name
  index_name         = "${var.name_prefix}-kb-index"
  data_type          = "float32"
  dimension          = var.embedding_dimensions
  distance_metric    = "cosine"

  # Bedrock stores chunk text and its own bookkeeping as non-filterable metadata.
  metadata_configuration {
    non_filterable_metadata_keys = [
      "AMAZON_BEDROCK_TEXT",
      "AMAZON_BEDROCK_METADATA",
      "x-amz-bedrock-kb-source-uri",
      "x-amz-bedrock-kb-data-source-id",
      "x-amz-bedrock-kb-chunk-id",
      "x-amz-bedrock-kb-document-page-number",
    ]
  }

  encryption_configuration {
    sse_type = "AES256"
  }
  lifecycle {
    prevent_destroy = true
  }
}

# IAM changes need a moment to propagate before Bedrock can assume the role.
resource "time_sleep" "kb_role_propagation" {
  create_duration = "30s"

  depends_on = [aws_iam_role_policy.kb]
}

resource "aws_bedrockagent_knowledge_base" "this" {
  name        = "${var.name_prefix}-kb"
  description = "ABW Connect official + alumni knowledge base"
  role_arn    = aws_iam_role.kb.arn

  knowledge_base_configuration {
    type = "VECTOR"

    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:${local.partition}:bedrock:${var.aws_region}::foundation-model/${var.embedding_model_id}"

      embedding_model_configuration {
        bedrock_embedding_model_configuration {
          dimensions          = var.embedding_dimensions
          embedding_data_type = "FLOAT32"
        }
      }
    }
  }

  storage_configuration {
    type = "S3_VECTORS"

    s3_vectors_configuration {
      index_arn = aws_s3vectors_index.kb.index_arn
    }
  }

  depends_on = [time_sleep.kb_role_propagation]
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_bedrockagent_data_source" "s3" {
  knowledge_base_id    = aws_bedrockagent_knowledge_base.this.id
  name                 = "${var.name_prefix}-s3"
  description          = "S3 kb/ prefix"
  data_deletion_policy = "RETAIN"

  data_source_configuration {
    type = "S3"

    s3_configuration {
      bucket_arn         = aws_s3_bucket.kb.arn
      inclusion_prefixes = ["kb/"]
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"

      fixed_size_chunking_configuration {
        max_tokens         = var.chunk_max_tokens
        overlap_percentage = var.chunk_overlap_percentage
      }
    }
  }
  lifecycle {
    prevent_destroy = true
  }
}

# Re-run ingestion whenever a document or sidecar changes. Bedrock has no Terraform
# resource for ingestion jobs, so this calls the AWS CLI and waits for COMPLETE.
resource "terraform_data" "ingestion" {
  count = var.start_ingestion && var.upload_kb ? 1 : 0

  triggers_replace = {
    documents = sha256(join(",", [for k in sort(keys(aws_s3_object.kb)) : "${k}=${aws_s3_object.kb[k].etag}"]))
    data_src  = aws_bedrockagent_data_source.s3.data_source_id
  }

  provisioner "local-exec" {
    command = "bash ${path.module}/scripts/start_ingestion.sh"
    environment = {
      KB_ID          = aws_bedrockagent_knowledge_base.this.id
      DATA_SOURCE_ID = aws_bedrockagent_data_source.s3.data_source_id
      AWS_REGION     = var.aws_region
    }
  }
}
