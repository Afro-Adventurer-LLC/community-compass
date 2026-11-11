# PRODUCTION copy managed by Terraform and promoted by .github/workflows/promote-production.yml.
#
# This is a NEW environment with its own name prefix, state file and Amplify app. It is NOT the
# hand-built live app: that one keeps the plain "abw-connect" prefix, is not imported into
# Terraform, and is not touched by any pipeline in this folder. variables.tf refuses the plain
# "abw-connect" prefix on purpose.
name_prefix = "abw-connect-prod"
environment = "prod"

lambda_zip_path = "../lambda-dist/abw-connect-backend.zip"
kb_source_dir   = "../kb"

# A brand-new knowledge base has to be filled and ingested by the first apply.
upload_kb       = true
start_ingestion = true

# Production data is not disposable.
kb_force_destroy = false

permissions_boundary_name = "abw-gha-prod-boundary"
