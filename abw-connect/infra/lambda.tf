resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.lambda_name}"
  retention_in_days = var.lambda_log_retention_days == 0 ? null : var.lambda_log_retention_days
}

resource "aws_lambda_function" "api" {
  function_name = local.lambda_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Zip"
  runtime       = var.lambda_runtime
  handler       = var.lambda_handler
  architectures = ["x86_64"]
  memory_size   = var.lambda_memory_mb
  timeout       = var.lambda_timeout_s

  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  ephemeral_storage {
    size = 512
  }

  tracing_config {
    mode = "PassThrough"
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.lambda.name
  }

  # Same variable names as live. No AWS_REGION (reserved by Lambda) and no secrets.
  environment {
    variables = {
      ABW_USE_AWS         = "true"
      ABW_EVENT_YEAR      = var.abw_event_year
      ABW_MIN_SCORE       = var.abw_min_score
      ABW_OFF_TOPIC_SCORE = var.abw_off_topic_score
      BEDROCK_KB_ID       = aws_bedrockagent_knowledge_base.this.id
      BEDROCK_MODEL_ID    = var.bedrock_model_id
      CORS_ORIGINS        = join(",", local.cors_origins)
      DDB_TABLE_PREFIX    = var.name_prefix
      GENERATOR_MODE      = var.generator_mode
      LLM_TIMEOUT_S       = var.llm_timeout_s
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda,
    aws_cloudwatch_log_group.lambda,
  ]
}
