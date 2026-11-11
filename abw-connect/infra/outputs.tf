output "api_endpoint" {
  description = "Base URL of the HTTP API (NEXT_PUBLIC_API_URL for the frontend build)."
  value       = aws_apigatewayv2_api.http.api_endpoint
}

output "lambda_function_name" {
  value = aws_lambda_function.api.function_name
}

output "knowledge_base_id" {
  value = aws_bedrockagent_knowledge_base.this.id
}

output "data_source_id" {
  value = aws_bedrockagent_data_source.s3.data_source_id
}

output "kb_bucket" {
  value = aws_s3_bucket.kb.bucket
}

output "dynamodb_tables" {
  value = [
    aws_dynamodb_table.conversations.name,
    aws_dynamodb_table.turns.name,
    aws_dynamodb_table.feedback.name,
    aws_dynamodb_table.unanswered.name,
  ]
}

output "amplify_app_id" {
  value = var.create_amplify ? aws_amplify_app.frontend[0].id : null
}

output "frontend_url" {
  value = var.create_amplify ? local.frontend_origin : null
}
