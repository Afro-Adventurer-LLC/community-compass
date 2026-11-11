# Remote state in S3 with native S3 locking (Terraform >= 1.10, no DynamoDB table).
#
# The block is intentionally empty ("partial configuration"): the bucket and the key are
# passed at init time so nothing account-specific is committed and every environment
# gets its own state file:
#
#   terraform init \
#     -backend-config="bucket=<state bucket>" \
#     -backend-config="key=abw-connect/<env>/terraform.tfstate"
#
# Or put the same lines in envs/<env>.backend.hcl (git-ignored, see example.backend.hcl)
# and run: terraform init -backend-config=envs/<env>.backend.hcl
#
# The state bucket is created by bootstrap/state (see README.md). Keys in use:
#   abw-connect/staging/terraform.tfstate
#   abw-connect/prod/terraform.tfstate     (a NEW production copy; not the hand-built live app)
terraform {
  backend "s3" {
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
