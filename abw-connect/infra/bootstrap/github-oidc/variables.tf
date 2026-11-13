variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "github_repo" {
  description = "GitHub repository allowed to assume the roles, as owner/name."
  type        = string
  default     = "DotBion/abw-connect"
}

variable "github_owner_id" {
  description = "Numeric id of the GitHub owner (user or org). Public, not a secret: `gh api users/<owner> --jq .id`. Needed because the repository uses immutable OIDC subjects (repo:<owner>@<owner id>/<name>@<repo id>). Empty trusts only the legacy subject format."
  type        = string
  default     = ""

  validation {
    condition     = can(regex("^[0-9]*$", var.github_owner_id))
    error_message = "github_owner_id must be digits only."
  }
}

variable "github_repo_id" {
  description = "Numeric id of the repository. Public, not a secret: `gh api repos/<owner>/<name> --jq .id`. Empty trusts only the legacy subject format."
  type        = string
  default     = ""

  validation {
    condition     = can(regex("^[0-9]*$", var.github_repo_id)) && (var.github_owner_id == "") == (var.github_repo_id == "")
    error_message = "Set github_owner_id and github_repo_id together, digits only (or leave both empty)."
  }
}

variable "additional_github_repos" {
  description = "Other repositories (owner/name plus their public numeric ids) trusted by the same roles with the same subject suffixes. Only the immutable subject form is trusted for these."
  type = list(object({
    repo     = string
    owner_id = string
    repo_id  = string
  }))
  default = []

  validation {
    condition = alltrue([for r in var.additional_github_repos :
    can(regex("^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$", r.repo)) && can(regex("^[0-9]+$", r.owner_id)) && can(regex("^[0-9]+$", r.repo_id))])
    error_message = "Each entry needs repo = owner/name and digits-only owner_id and repo_id."
  }
}

variable "state_bucket_name" {
  description = "Terraform state bucket created by bootstrap/state (its `bucket` output)."
  type        = string
}

variable "create_oidc_provider" {
  description = "Create the GitHub OIDC identity provider. Leave false when the account already has token.actions.githubusercontent.com (it does: the live-app deploy stack created it). The provider is then only read, never changed."
  type        = bool
  default     = false
}

variable "staging_prefix" {
  type    = string
  default = "abw-connect-staging"
}

variable "prod_prefix" {
  description = "Name prefix of the NEW production copy. Never the live app's plain `abw-connect`."
  type        = string
  default     = "abw-connect-prod"
}

# ---- Live-app protection. Required on purpose (no defaults): the person applying this
# ---- directory must name the live resources so they get an explicit Deny.
variable "protected_api_ids" {
  description = "HTTP API ids of the hand-built live app. The deploy roles get an explicit Deny on them."
  type        = list(string)

  validation {
    condition     = length(var.protected_api_ids) > 0
    error_message = "List the live API id(s). The pipeline roles are denied on them."
  }
}

variable "protected_amplify_app_ids" {
  description = "Amplify app ids of the hand-built live app. Explicit Deny for the deploy roles."
  type        = list(string)

  validation {
    condition     = length(var.protected_amplify_app_ids) > 0
    error_message = "List the live Amplify app id(s). The pipeline roles are denied on them."
  }
}

variable "protected_kb_ids" {
  description = "Bedrock knowledge base ids of the hand-built live app. Explicit Deny for the deploy roles."
  type        = list(string)

  validation {
    condition     = length(var.protected_kb_ids) > 0
    error_message = "List the live knowledge base id(s). The pipeline roles are denied on them."
  }
}

variable "embedding_model_id" {
  type    = string
  default = "amazon.titan-embed-text-v2:0"
}

variable "bedrock_model_id" {
  type    = string
  default = "amazon.nova-lite-v1:0"
}
