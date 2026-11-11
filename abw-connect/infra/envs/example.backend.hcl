# Copy to envs/<env>.backend.hcl (git-ignored), fill in, and run:
#   terraform init -backend-config=envs/<env>.backend.hcl
# The bucket is printed by `terraform output bucket` in bootstrap/state.
bucket       = "REPLACE_WITH_STATE_BUCKET"
key          = "abw-connect/REPLACE_ENV/terraform.tfstate" # staging or prod
region       = "us-east-1"
encrypt      = true
use_lockfile = true
