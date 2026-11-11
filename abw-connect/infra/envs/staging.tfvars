# Staging: every name starts with abw-connect-staging so nothing collides with live.
# Deployed automatically by .github/workflows/deploy-staging.yml on every merge to main.
name_prefix = "abw-connect-staging"
environment = "staging"

# Built by scripts/package_lambda.sh (run it from the repo root first).
lambda_zip_path = "../lambda-dist/abw-connect-backend.zip"
kb_source_dir   = "../kb"

# Staging only: let terraform destroy remove the buckets with their contents.
kb_force_destroy = true

# Created by bootstrap/github-oidc. The CI deploy role can only create roles that carry it.
# Until that directory has been applied, leave this line out when planning by hand.
permissions_boundary_name = "abw-gha-staging-boundary"
