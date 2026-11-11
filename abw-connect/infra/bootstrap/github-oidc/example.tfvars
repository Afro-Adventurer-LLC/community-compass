# Copy to terraform.tfvars (git-ignored) and fill in. The bucket name and the protected_* ids name your own
# AWS account and live app, so keep your filled-in copy out of git. The two GitHub ids below are public.
state_bucket_name         = "abw-tfstate-<account id>"
protected_api_ids         = ["<live API id>"]
protected_amplify_app_ids = ["<live Amplify app id>"]
protected_kb_ids          = ["<live knowledge base id>"]

github_repo     = "DotBion/abw-connect"
github_owner_id = "23533170"   # gh api users/DotBion --jq .id
github_repo_id  = "1446202922" # gh api repos/DotBion/abw-connect --jq .id
