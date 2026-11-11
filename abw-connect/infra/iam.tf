# ------------------------------------------------------------------ Lambda execution role
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name                 = "${var.name_prefix}-lambda-role"
  assume_role_policy   = data.aws_iam_policy_document.lambda_assume.json
  permissions_boundary = local.permissions_boundary_arn
}

data "aws_iam_policy_document" "lambda" {
  # Least privilege vs live: logs are limited to this function's own log group
  # (live allows logs:* actions on every log group in the account).
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  statement {
    sid       = "BedrockRetrieve"
    actions   = ["bedrock:Retrieve"]
    resources = [aws_bedrockagent_knowledge_base.this.arn]
  }

  statement {
    sid     = "BedrockConverse"
    actions = ["bedrock:InvokeModel", "bedrock:Converse"]
    resources = [
      "arn:${local.partition}:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}",
      "arn:${local.partition}:bedrock:${var.aws_region}:${local.account_id}:inference-profile/*",
    ]
  }

  statement {
    sid = "DynamoDB"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:DeleteItem",
    ]
    resources = [
      aws_dynamodb_table.conversations.arn,
      aws_dynamodb_table.turns.arn,
      aws_dynamodb_table.feedback.arn,
      aws_dynamodb_table.unanswered.arn,
      "${aws_dynamodb_table.unanswered.arn}/index/*",
    ]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${var.name_prefix}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

# ------------------------------------------------------------------ Bedrock knowledge-base role
data "aws_iam_policy_document" "kb_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:bedrock:${var.aws_region}:${local.account_id}:knowledge-base/*"]
    }
  }
}

resource "aws_iam_role" "kb" {
  name                 = "${var.name_prefix}-bedrock-kb-role"
  assume_role_policy   = data.aws_iam_policy_document.kb_assume.json
  permissions_boundary = local.permissions_boundary_arn
}

data "aws_iam_policy_document" "kb" {
  statement {
    sid       = "S3ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.kb.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [local.account_id]
    }
  }

  statement {
    sid       = "S3GetObject"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.kb.arn}/*"]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [local.account_id]
    }
  }

  statement {
    sid       = "BedrockEmbed"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:${local.partition}:bedrock:${var.aws_region}::foundation-model/${var.embedding_model_id}"]
  }

  statement {
    sid = "S3Vectors"
    actions = [
      "s3vectors:QueryVectors",
      "s3vectors:GetVectors",
      "s3vectors:GetIndex",
      "s3vectors:GetVectorBucket",
      "s3vectors:ListIndexes",
      "s3vectors:PutVectors",
      "s3vectors:DeleteVectors",
    ]
    resources = [
      aws_s3vectors_vector_bucket.kb.vector_bucket_arn,
      "${aws_s3vectors_vector_bucket.kb.vector_bucket_arn}/*",
      aws_s3vectors_index.kb.index_arn,
    ]
  }
}

resource "aws_iam_role_policy" "kb" {
  name   = "${var.name_prefix}-bedrock-kb-policy"
  role   = aws_iam_role.kb.id
  policy = data.aws_iam_policy_document.kb.json
}
