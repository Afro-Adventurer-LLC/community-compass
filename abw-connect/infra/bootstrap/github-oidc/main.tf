# GitHub Actions -> AWS through OIDC (no long-lived keys in GitHub).
#
# Creates, per environment, a deploy role that can only manage resources whose names start
# with that environment's prefix, plus a permissions boundary that caps the IAM roles the
# stack itself creates. Also one read-only role used by pull-request `terraform plan`.
#
#   abw-gha-plan             pull requests        sub  repo:<repo>:pull_request          read only
#   abw-gha-staging-deploy   environment staging  sub  repo:<repo>:environment:staging
#   abw-gha-prod-deploy      environment production  sub  repo:<repo>:environment:production
#
# Two `sub` formats are trusted, as an exact list (StringEquals, no wildcards):
#   legacy     repo:<owner>/<name>:<suffix>
#   immutable  repo:<owner>@<owner id>/<name>@<repo id>:<suffix>
# Repositories (and all new ones) with "immutable subject" turned on get the second form in their tokens.
# The numeric ids are public (https://api.github.com/repos/<owner>/<name>) and are not secrets. They also make
# the trust survive a repository being deleted and re-created under the same name.
#
# These role names deliberately do NOT start with either stack prefix, so a deploy role can
# never edit itself. None of this touches the hand-built live app or its deploy role
# (abw-connect-github-deploy); the existing OIDC provider is only read.

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "abw-connect"
      ManagedBy = "terraform"
      Purpose   = "github-actions-oidc"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  region     = var.aws_region
  oidc_host  = "token.actions.githubusercontent.com"

  repo_owner        = split("/", var.github_repo)[0]
  repo_name         = split("/", var.github_repo)[1]
  sub_prefix_legacy = "repo:${var.github_repo}"
  # Empty when the ids are not given: then only the legacy format is trusted.
  sub_prefix_immutable = (var.github_owner_id != "" && var.github_repo_id != "" ?
  "repo:${local.repo_owner}@${var.github_owner_id}/${local.repo_name}@${var.github_repo_id}" : "")
  # Additional repositories (e.g. the team repo Afro-Adventurer-LLC/community-compass): immutable form only.
  sub_prefixes_additional = [
    for r in var.additional_github_repos :
    "repo:${split("/", r.repo)[0]}@${r.owner_id}/${split("/", r.repo)[1]}@${r.repo_id}"
  ]
  sub_prefixes = concat(compact([local.sub_prefix_legacy, local.sub_prefix_immutable]), local.sub_prefixes_additional)

  envs = {
    staging = {
      prefix      = var.staging_prefix
      role_name   = "abw-gha-staging-deploy"
      boundary    = "abw-gha-staging-boundary"
      sub_suffix  = "environment:staging"
      state_key   = "abw-connect/staging/terraform.tfstate"
      description = "Deploys the staging stack (${var.staging_prefix}-*) from the staging GitHub environment."
    }
    prod = {
      prefix      = var.prod_prefix
      role_name   = "abw-gha-prod-deploy"
      boundary    = "abw-gha-prod-boundary"
      sub_suffix  = "environment:production"
      state_key   = "abw-connect/prod/terraform.tfstate"
      description = "Deploys the NEW production copy (${var.prod_prefix}-*) from the production GitHub environment (required reviewers)."
    }
  }

  # Explicit Deny targets: the live app's ids.
  protected_apigw_arns = flatten([
    for id in var.protected_api_ids : [
      "arn:${local.partition}:apigateway:${local.region}::/apis/${id}",
      "arn:${local.partition}:apigateway:${local.region}::/apis/${id}/*",
    ]
  ])
  protected_amplify_arns = flatten([
    for id in var.protected_amplify_app_ids : [
      "arn:${local.partition}:amplify:${local.region}:${local.account_id}:apps/${id}",
      "arn:${local.partition}:amplify:${local.region}:${local.account_id}:apps/${id}/*",
    ]
  ])
  protected_kb_arns = [
    for id in var.protected_kb_ids : "arn:${local.partition}:bedrock:${local.region}:${local.account_id}:knowledge-base/${id}"
  ]

  state_bucket_arn = "arn:${local.partition}:s3:::${var.state_bucket_name}"
}

# ------------------------------------------------------------------ OIDC provider
resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 1 : 0

  url            = "https://${local.oidc_host}"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 0 : 1

  url = "https://${local.oidc_host}"
}

locals {
  oidc_provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
}

# ------------------------------------------------------------------ trust policies
data "aws_iam_policy_document" "trust" {
  for_each = merge(
    { for k, v in local.envs : k => v.sub_suffix },
    { plan = "pull_request" },
  )

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = [for p in local.sub_prefixes : "${p}:${each.value}"]
    }
  }
}

# ------------------------------------------------------------------ permissions boundary
# Upper limit for the Lambda role and the Bedrock KB role that the stack creates.
# It is the union of what those two roles legitimately need (see infra/iam.tf), scoped to the prefix.
data "aws_iam_policy_document" "boundary" {
  for_each = local.envs

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${each.value.prefix}-*:*"]
  }

  statement {
    sid       = "BedrockRetrieve"
    actions   = ["bedrock:Retrieve"]
    resources = ["arn:${local.partition}:bedrock:${local.region}:${local.account_id}:knowledge-base/*"]
  }

  # bedrock:InvokeModel also authorizes the Converse API. (The Lambda policy in iam.tf lists
  # "bedrock:Converse" like live does; that action does not exist, so nothing is lost here.)
  statement {
    sid     = "BedrockModels"
    actions = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = [
      "arn:${local.partition}:bedrock:${local.region}::foundation-model/${var.bedrock_model_id}",
      "arn:${local.partition}:bedrock:${local.region}::foundation-model/${var.embedding_model_id}",
      "arn:${local.partition}:bedrock:${local.region}:${local.account_id}:inference-profile/*",
    ]
  }

  statement {
    sid = "DynamoDB"
    actions = [
      "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
      "dynamodb:Query", "dynamodb:Scan", "dynamodb:DeleteItem",
    ]
    resources = [
      "arn:${local.partition}:dynamodb:${local.region}:${local.account_id}:table/${each.value.prefix}-*",
      "arn:${local.partition}:dynamodb:${local.region}:${local.account_id}:table/${each.value.prefix}-*/index/*",
    ]
  }

  statement {
    sid     = "KbSourceBucket"
    actions = ["s3:ListBucket", "s3:GetObject"]
    resources = [
      "arn:${local.partition}:s3:::${each.value.prefix}-kb-*",
      "arn:${local.partition}:s3:::${each.value.prefix}-kb-*/*",
    ]
  }

  statement {
    sid = "VectorStore"
    actions = [
      "s3vectors:QueryVectors", "s3vectors:GetVectors", "s3vectors:GetIndex", "s3vectors:GetVectorBucket",
      "s3vectors:ListIndexes", "s3vectors:PutVectors", "s3vectors:DeleteVectors",
    ]
    resources = [
      "arn:${local.partition}:s3vectors:${local.region}:${local.account_id}:bucket/${each.value.prefix}-vectors",
      "arn:${local.partition}:s3vectors:${local.region}:${local.account_id}:bucket/${each.value.prefix}-vectors/*",
    ]
  }
}

resource "aws_iam_policy" "boundary" {
  for_each = local.envs

  name        = each.value.boundary
  description = "Permissions boundary for the roles created by the ${each.key} stack (${each.value.prefix}-*)."
  policy      = data.aws_iam_policy_document.boundary[each.key].json
}

# ------------------------------------------------------------------ deploy roles
data "aws_iam_policy_document" "deploy" {
  for_each = local.envs

  # --- Terraform state: this environment's key only
  # Listing shows key names only. Terraform's S3 backend lists the bucket during init.
  statement {
    sid       = "StateList"
    actions   = ["s3:ListBucket"]
    resources = [local.state_bucket_arn]
  }

  statement {
    sid       = "StateObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${local.state_bucket_arn}/${each.value.state_key}", "${local.state_bucket_arn}/${each.value.state_key}.tflock"]
  }

  # --- Lambda
  statement {
    sid       = "Lambda"
    actions   = ["lambda:*"]
    resources = ["arn:${local.partition}:lambda:${local.region}:${local.account_id}:function:${each.value.prefix}-*"]
  }

  # --- CloudWatch Logs
  statement {
    sid       = "LogGroup"
    actions   = ["logs:*"]
    resources = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${each.value.prefix}-*", "arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${each.value.prefix}-*:*"]
  }

  statement {
    sid       = "LogGroupDescribe"
    actions   = ["logs:DescribeLogGroups", "logs:ListTagsForResource"]
    resources = ["*"]
  }

  # --- DynamoDB
  statement {
    sid     = "DynamoDB"
    actions = ["dynamodb:*"]
    resources = [
      "arn:${local.partition}:dynamodb:${local.region}:${local.account_id}:table/${each.value.prefix}-*",
      "arn:${local.partition}:dynamodb:${local.region}:${local.account_id}:table/${each.value.prefix}-*/index/*",
    ]
  }

  # --- S3 (KB source bucket) and S3 Vectors
  statement {
    sid     = "KbBucket"
    actions = ["s3:*"]
    resources = [
      "arn:${local.partition}:s3:::${each.value.prefix}-kb-*",
      "arn:${local.partition}:s3:::${each.value.prefix}-kb-*/*",
    ]
  }

  statement {
    sid     = "VectorBucket"
    actions = ["s3vectors:*"]
    resources = [
      "arn:${local.partition}:s3vectors:${local.region}:${local.account_id}:bucket/${each.value.prefix}-vectors",
      "arn:${local.partition}:s3vectors:${local.region}:${local.account_id}:bucket/${each.value.prefix}-vectors/*",
    ]
  }

  # --- IAM: only roles named <prefix>-*, only with the boundary attached
  statement {
    sid = "IamRolesCreateWithBoundary"
    actions = [
      "iam:CreateRole",
      "iam:PutRolePermissionsBoundary",
    ]
    resources = ["arn:${local.partition}:iam::${local.account_id}:role/${each.value.prefix}-*"]

    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [aws_iam_policy.boundary[each.key].arn]
    }
  }

  statement {
    sid = "IamRolesManage"
    actions = [
      "iam:GetRole", "iam:DeleteRole", "iam:UpdateRole", "iam:UpdateAssumeRolePolicy",
      "iam:TagRole", "iam:UntagRole", "iam:ListRoleTags",
      "iam:PutRolePolicy", "iam:GetRolePolicy", "iam:DeleteRolePolicy",
      "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole",
    ]
    resources = ["arn:${local.partition}:iam::${local.account_id}:role/${each.value.prefix}-*"]
  }

  statement {
    sid       = "IamPassRoleToServices"
    actions   = ["iam:PassRole"]
    resources = ["arn:${local.partition}:iam::${local.account_id}:role/${each.value.prefix}-*"]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com", "bedrock.amazonaws.com"]
    }
  }

  statement {
    sid       = "IamReadBoundary"
    actions   = ["iam:GetPolicy", "iam:GetPolicyVersion"]
    resources = [aws_iam_policy.boundary[each.key].arn]
  }

  # --- API Gateway v2 (ARNs contain the generated api id, so they cannot be scoped by name;
  # --- the live API is protected by the explicit Deny below)
  statement {
    sid = "ApiGatewayV2"
    # TagResource/UntagResource: with provider default_tags, CreateStage (and later updates) tag the stage and need
    # apigateway:TagResource on /apis/<id>/stages. It is a separate action from apigateway:PUT on /tags/*.
    actions = [
      "apigateway:GET", "apigateway:POST", "apigateway:PUT", "apigateway:PATCH", "apigateway:DELETE",
      "apigateway:TagResource", "apigateway:UntagResource",
    ]
    resources = [
      "arn:${local.partition}:apigateway:${local.region}::/apis",
      "arn:${local.partition}:apigateway:${local.region}::/apis/*",
      "arn:${local.partition}:apigateway:${local.region}::/tags/*",
    ]
  }

  # --- Amplify (same: app ids are generated)
  statement {
    sid       = "AmplifyCreateApp"
    actions   = ["amplify:CreateApp", "amplify:ListApps"]
    resources = ["*"]
  }

  # Precaution: CreateApp tags the new app (default_tags) and checks amplify:TagResource. Allowed on "*" in case that
  # check happens before the app has an ARN. Tagging only; the explicit Deny below still blocks the live app.
  statement {
    sid       = "AmplifyTagOnCreate"
    actions   = ["amplify:TagResource"]
    resources = ["*"]
  }

  statement {
    sid       = "AmplifyApps"
    actions   = ["amplify:*"]
    resources = ["arn:${local.partition}:amplify:${local.region}:${local.account_id}:apps/*"]
  }

  # --- Bedrock knowledge base (ids are generated; the live KB is protected by the Deny below)
  statement {
    sid = "BedrockKnowledgeBase"
    actions = [
      "bedrock:CreateKnowledgeBase", "bedrock:GetKnowledgeBase", "bedrock:UpdateKnowledgeBase", "bedrock:DeleteKnowledgeBase",
      "bedrock:CreateDataSource", "bedrock:GetDataSource", "bedrock:UpdateDataSource", "bedrock:DeleteDataSource",
      "bedrock:ListDataSources", "bedrock:StartIngestionJob", "bedrock:GetIngestionJob", "bedrock:ListIngestionJobs",
      "bedrock:TagResource", "bedrock:UntagResource", "bedrock:ListTagsForResource",
    ]
    resources = ["arn:${local.partition}:bedrock:${local.region}:${local.account_id}:knowledge-base/*"]
  }

  statement {
    sid     = "BedrockEmbeddingModelCheck"
    actions = ["bedrock:InvokeModel", "bedrock:GetFoundationModel"]
    resources = [
      "arn:${local.partition}:bedrock:${local.region}::foundation-model/${var.embedding_model_id}",
    ]
  }

  # --- Never touch the live app
  statement {
    sid       = "DenyLiveApp"
    effect    = "Deny"
    actions   = ["apigateway:*"]
    resources = local.protected_apigw_arns
  }

  statement {
    sid       = "DenyLiveAmplify"
    effect    = "Deny"
    actions   = ["amplify:*"]
    resources = local.protected_amplify_arns
  }

  statement {
    sid       = "DenyLiveKnowledgeBase"
    effect    = "Deny"
    actions   = ["bedrock:*"]
    resources = local.protected_kb_arns
  }
}

resource "aws_iam_role" "deploy" {
  for_each = local.envs

  name                 = each.value.role_name
  description          = each.value.description
  assume_role_policy   = data.aws_iam_policy_document.trust[each.key].json
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "deploy" {
  for_each = local.envs

  name   = "${each.value.role_name}-policy"
  role   = aws_iam_role.deploy[each.key].id
  policy = data.aws_iam_policy_document.deploy[each.key].json
}

# ------------------------------------------------------------------ pull-request plan role (read only)
# `terraform plan -lock=false` against the STAGING state. Reads state and describes resources; cannot write.
data "aws_iam_policy_document" "plan" {
  statement {
    sid       = "StateRead"
    actions   = ["s3:GetObject"]
    resources = ["${local.state_bucket_arn}/${local.envs.staging.state_key}"]
  }

  statement {
    sid       = "StateList"
    actions   = ["s3:ListBucket"]
    resources = [local.state_bucket_arn]
  }

  # Read APIs the AWS provider calls while refreshing the staging stack
  # (measured with TF_LOG=debug on a real plan; API Gateway, Amplify and Bedrock ids are generated, so those are service-wide reads).
  statement {
    sid = "ReadStagingStack"
    actions = [
      "lambda:Get*", "lambda:List*",
      "dynamodb:Describe*", "dynamodb:ListTagsOfResource",
      "s3:GetBucket*", "s3:GetObject", "s3:GetObjectTagging", "s3:GetObjectAttributes", "s3:GetAccelerateConfiguration",
      "s3:GetEncryptionConfiguration", "s3:GetLifecycleConfiguration", "s3:GetReplicationConfiguration",
      "s3:GetBucketPublicAccessBlock", "s3:GetBucketTagging", "s3:ListBucket",
      "s3vectors:Get*", "s3vectors:List*",
      "iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListRoleTags",
      "iam:GetPolicy", "iam:GetPolicyVersion",
    ]
    resources = [
      "arn:${local.partition}:lambda:${local.region}:${local.account_id}:function:${var.staging_prefix}-*",
      "arn:${local.partition}:dynamodb:${local.region}:${local.account_id}:table/${var.staging_prefix}-*",
      "arn:${local.partition}:s3:::${var.staging_prefix}-kb-*",
      "arn:${local.partition}:s3:::${var.staging_prefix}-kb-*/*",
      "arn:${local.partition}:s3vectors:${local.region}:${local.account_id}:bucket/${var.staging_prefix}-vectors",
      "arn:${local.partition}:s3vectors:${local.region}:${local.account_id}:bucket/${var.staging_prefix}-vectors/*",
      "arn:${local.partition}:iam::${local.account_id}:role/${var.staging_prefix}-*",
      aws_iam_policy.boundary["staging"].arn,
    ]
  }

  statement {
    sid = "ReadGeneratedIdServices"
    actions = [
      "apigateway:GET",
      "amplify:GetApp", "amplify:GetBranch", "amplify:ListTagsForResource", "amplify:ListBranches",
      "bedrock:GetKnowledgeBase", "bedrock:GetDataSource", "bedrock:ListTagsForResource",
      "logs:DescribeLogGroups", "logs:ListTagsForResource", "logs:ListTagsLogGroup",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "DenyLiveApp"
    effect    = "Deny"
    actions   = ["apigateway:*"]
    resources = local.protected_apigw_arns
  }

  statement {
    sid       = "DenyLiveAmplify"
    effect    = "Deny"
    actions   = ["amplify:*"]
    resources = local.protected_amplify_arns
  }

  statement {
    sid       = "DenyLiveKnowledgeBase"
    effect    = "Deny"
    actions   = ["bedrock:*"]
    resources = local.protected_kb_arns
  }
}

resource "aws_iam_role" "plan" {
  name                 = "abw-gha-plan"
  description          = "Read-only terraform plan of the staging stack for pull requests."
  assume_role_policy   = data.aws_iam_policy_document.trust["plan"].json
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "plan" {
  name   = "abw-gha-plan-policy"
  role   = aws_iam_role.plan.id
  policy = data.aws_iam_policy_document.plan.json
}
