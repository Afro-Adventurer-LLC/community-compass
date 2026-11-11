variable "aws_region" {
  description = "AWS region for every resource. The live stack runs in us-east-1."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Prefix for every resource name and for DDB_TABLE_PREFIX. Use abw-connect-staging for staging so nothing collides with the live abw-connect-* resources."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,30}$", var.name_prefix))
    error_message = "name_prefix must be 3-31 chars: lowercase letters, digits and hyphens, starting with a letter."
  }

  # Guard rail: the hand-built live app owns every name that starts with plain "abw-connect"
  # (abw-connect-api, abw-connect-lambda-role, ...). A pipeline environment must never reuse it.
  validation {
    condition     = var.name_prefix != "abw-connect"
    error_message = "name_prefix \"abw-connect\" is the hand-built live app's prefix. Use abw-connect-staging or abw-connect-prod. To import the live app on purpose, remove this check in a reviewed change."
  }
}

variable "environment" {
  description = "Environment label used in tags (staging or prod)."
  type        = string
  default     = "staging"
}

# ---------------------------------------------------------------- Lambda

variable "lambda_zip_path" {
  description = "Path to the Lambda zip built by scripts/package_lambda.sh (git archive of backend/app + dependencies)."
  type        = string
  default     = "../lambda-dist/abw-connect-backend.zip"
}

variable "lambda_runtime" {
  type    = string
  default = "python3.13"
}

variable "lambda_handler" {
  type    = string
  default = "app.lambda_handler.handler"
}

variable "lambda_memory_mb" {
  type    = number
  default = 1024
}

variable "lambda_timeout_s" {
  type    = number
  default = 60
}

variable "lambda_log_retention_days" {
  description = "CloudWatch log retention. 0 keeps logs forever (matches the live log group)."
  type        = number
  default     = 0
}

variable "bedrock_model_id" {
  description = "Converse model used by the generator (BEDROCK_MODEL_ID)."
  type        = string
  default     = "amazon.nova-lite-v1:0"
}

variable "abw_event_year" {
  type    = string
  default = "2026"
}

variable "abw_min_score" {
  description = "Bedrock 0-1 support floor (ABW_MIN_SCORE)."
  type        = string
  default     = "0.25"
}

variable "abw_off_topic_score" {
  description = "Below this score maybe-off-topic questions are refused (ABW_OFF_TOPIC_SCORE)."
  type        = string
  default     = "0.15"
}

variable "generator_mode" {
  type    = string
  default = "auto"
}

variable "llm_timeout_s" {
  type    = string
  default = "15"
}

variable "extra_cors_origins" {
  description = "Extra origins appended to the Lambda CORS_ORIGINS (the Amplify origin is added automatically)."
  type        = list(string)
  default     = ["http://localhost:3000", "http://127.0.0.1:3000"]
}

variable "frontend_origin" {
  description = "Frontend origin to allow when create_amplify is false."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------- API Gateway

variable "api_cors_allow_origins" {
  description = "HTTP API CORS allow-origins. The live API uses [\"*\"]."
  type        = list(string)
  default     = ["*"]
}

variable "api_integration_timeout_ms" {
  type    = number
  default = 30000
}

# ---------------------------------------------------------------- Knowledge base

variable "kb_source_dir" {
  description = "Local directory with the knowledge-base documents and their *.metadata.json sidecars."
  type        = string
  default     = "../kb"
}

variable "upload_kb" {
  description = "Upload kb_source_dir to the KB bucket under kb/ with Terraform."
  type        = bool
  default     = true
}

variable "start_ingestion" {
  description = "Start a Bedrock ingestion job after the documents change (needs the AWS CLI on the machine running Terraform)."
  type        = bool
  default     = true
}

variable "kb_bucket_name" {
  description = "Override the KB bucket name. Default: <name_prefix>-kb-<account id>, like the live bucket."
  type        = string
  default     = ""
}

variable "embedding_model_id" {
  type    = string
  default = "amazon.titan-embed-text-v2:0"
}

variable "embedding_dimensions" {
  type    = number
  default = 1024
}

variable "chunk_max_tokens" {
  type    = number
  default = 512
}

variable "chunk_overlap_percentage" {
  type    = number
  default = 20
}

variable "kb_force_destroy" {
  description = "Allow terraform destroy to delete a non-empty KB bucket and vector bucket (set true for staging only)."
  type        = bool
  default     = false
}

# ---------------------------------------------------------------- Amplify (frontend)

variable "create_amplify" {
  description = "Create the (repository-less) Amplify app and main branch. The frontend zip is deployed outside Terraform (see README)."
  type        = bool
  default     = true
}

# ---------------------------------------------------------------- IAM

variable "permissions_boundary_name" {
  description = "Name of an IAM managed policy used as the permissions boundary of the two roles this stack creates (Lambda and Bedrock KB). The CI deploy roles may only create roles with this boundary. Empty means no boundary. The policy is created by bootstrap/github-oidc."
  type        = string
  default     = ""
}
