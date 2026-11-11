# ABW Connect infrastructure (Terraform)

Infrastructure as code for the ABW Connect stack: the Lambda API, the HTTP API in front of it,
the DynamoDB tables, the Bedrock knowledge base with its S3 source bucket and S3 Vectors store,
the IAM roles and the Amplify frontend app. It mirrors the stack that is live today (the F19
deploy, commit `8e88e93`) so a new environment can be created from code.

**Status.** Staging (`abw-connect-staging`) is applied from this code and its state lives in S3.
The hand-built live app is **not imported** and nothing in this folder or in the workflows touches it.
`envs/prod.tfvars` describes a **new** production copy (`abw-connect-prod`), not the live app.

## How changes reach staging and production (plain version)

```
  pull request ──► CI checks ─────────────► review ─► merge to main
                   (tests, build,                          │
                    terraform fmt/validate,                ▼
                    optional read-only plan)      Deploy staging (automatic)
                                                  tests → terraform apply → Lambda + KB
                                                  → Amplify frontend → smoke test
                                                           │  (same commit, same Lambda zip)
                                                           ▼
                              Promote to production (you click it, a reviewer approves)
                              → new abw-connect-prod copy → same steps → smoke test
```

1. **Open a pull request.** `CI checks` runs the Python tests, the mock evals, the frontend tests and static build,
   `terraform fmt` / `validate`, a `shellcheck` and an `actionlint` pass. It cannot change AWS. If you enable it, it also posts a
   read-only `terraform plan` of staging to the run summary.
2. **Merge to `main`.** `Deploy staging` runs the same checks again, then deploys to **staging**: `terraform apply`
   (infrastructure, Lambda code, knowledge-base documents and re-ingestion), the frontend zip to Amplify, and a smoke
   test (health shows the exact commit, CORS, one real chat call, the site answers). If anything fails, it stops there.
3. **Look at staging, then promote.** Run `Promote to production` from the Actions tab with the commit SHA and the
   run id of the green staging run. It checks that the commit is on `main`, that staging passed for exactly that commit,
   and that the staging Lambda zip is still available. Then it **waits for the required reviewers** of the
   `production` GitHub environment. After approval it deploys the same commit, with the **same Lambda zip** that ran on
   staging, to the new production copy and smoke tests it. `plan_only` shows the plan without changing anything.

Staging and production use the same workflow file (`deploy-env.yml`), so they cannot drift apart in how they deploy.
Their differences are only data: `envs/staging.tfvars` vs `envs/prod.tfvars`, the state file, the AWS role.

### What the pipeline never does

* It never touches the hand-built live app (its Amplify app, API, Lambda `abw-connect-api`, knowledge base, tables and roles).
  `variables.tf` rejects the plain `abw-connect` prefix, `scripts/check_env.sh` checks the tfvars before every deploy, and the
  AWS roles are limited to `abw-connect-staging-*` / `abw-connect-prod-*` names, with an explicit Deny on the live ids.
* It never uses access keys. GitHub gets a short-lived token from AWS through OIDC.
* It never prints secrets and never manages Basic Auth (see below).

### Files

| Path | What it is |
| --- | --- |
| `.github/workflows/ci-checks.yml` | Pull request checks; also called before a staging deploy |
| `.github/workflows/deploy-staging.yml` | Merge to `main` → staging |
| `.github/workflows/promote-production.yml` | Manual promotion with a reviewer gate |
| `.github/workflows/deploy-env.yml` | The shared deploy steps (reusable, not started by itself) |
| `backend.tf` | Remote state in S3 with native locking; bucket and key are passed at init |
| `bootstrap/state/` | One-time: creates the state bucket (versioned, encrypted, private, HTTPS only) |
| `bootstrap/github-oidc/` | One-time, admin: OIDC roles and permission boundaries for the pipeline |
| `scripts/check_env.sh`, `deploy_frontend.sh`, `smoke_test.sh` | Pipeline helpers (shellchecked) |

## One-time setup (an AWS admin and a repo admin)

### 1. State bucket (done once, already applied for this account)

```bash
cd infra/bootstrap/state
terraform init && terraform apply          # creates abw-tfstate-<account id>; prints it as `bucket`
```

This directory keeps its own small local state file (git-ignored); back it up. Versioning is on and old versions
are kept 90 days. Locking uses Terraform's native S3 lock file, so there is no DynamoDB table.

Staging state was moved there with:

```bash
cd infra
terraform init -migrate-state -backend-config="bucket=<state bucket>" -backend-config="key=abw-connect/staging/terraform.tfstate"
terraform plan -var-file=envs/staging.tfvars     # must say: No changes
```

Production gets its own key, `abw-connect/prod/terraform.tfstate`, the first time the promote workflow runs.

### 2. AWS roles for GitHub (admin; not applied yet)

```bash
cd infra/bootstrap/github-oidc
terraform init
terraform apply \
  -var state_bucket_name=<state bucket> \
  -var 'protected_api_ids=["<live API id>"]' \
  -var 'protected_amplify_app_ids=["<live Amplify app id>"]' \
  -var 'protected_kb_ids=["<live knowledge base id>"]' \
  -var github_owner_id=<owner id> -var github_repo_id=<repo id>
terraform output          # the three role ARNs, for step 3
```

The three `protected_*` variables are required on purpose: they become explicit Deny statements so the pipeline
roles cannot touch the live app even by mistake. The existing GitHub OIDC provider is only read, not changed.

`github_owner_id` and `github_repo_id` (see `bootstrap/github-oidc/example.tfvars`) are public GitHub ids. Repositories
with immutable OIDC subjects send `sub` as `repo:<owner>@<owner id>/<name>@<repo id>:<suffix>` instead of
`repo:<owner>/<name>:<suffix>`. With the ids set, each role trusts both forms as an exact list (no wildcards); with
them empty, only the legacy form. Check yours with `gh api repos/<owner>/<repo>/actions/oidc/customization/sub`: if it
shows `use_immutable_subject: true`, you need the ids, otherwise AWS answers `Not authorized to perform sts:AssumeRoleWithWebIdentity`.

| Role | Who can assume it (OIDC `sub`) | Can do |
| --- | --- | --- |
| `abw-gha-plan` | pull requests of this repo | read-only; staging state + describe calls |
| `abw-gha-staging-deploy` | `environment:staging` | create/update/delete only `abw-connect-staging-*` resources; only its own state key |
| `abw-gha-prod-deploy` | `environment:production` | the same for `abw-connect-prod-*`; only the prod state key |

Both deploy roles can create IAM roles only with a permissions boundary (`abw-gha-<env>-boundary`) attached, which caps
what the app's Lambda and Bedrock roles can ever do, and only under their own prefix. They cannot edit themselves.
Limit that cannot be removed: API Gateway, Amplify and Bedrock knowledge-base ARNs contain generated ids, so those
permissions are service-wide inside the account except for the live ids that are denied. Restrict the `staging` and
`production` environments to the `main` branch (step 3) so that a branch cannot borrow the role.

### 3. GitHub settings (repo admin)

| Where | Name | Value |
| --- | --- | --- |
| Environment `staging` | deployment branches | `main` only; no reviewers needed |
| Environment `staging` | secret `AWS_ROLE_ARN` | output `staging_deploy_role_arn` |
| Environment `production` | deployment branches | `main` only |
| Environment `production` | required reviewers | optional: needs a public repo or GitHub Enterprise (a private repo on Pro/Team cannot set it). Without it, anyone with write access can run Promote, so limit who has write access |
| Environment `production` | secret `AWS_ROLE_ARN` | output `prod_deploy_role_arn` |
| Repository variables | `TF_STATE_BUCKET` | the state bucket name |
| Repository variables (optional) | `AWS_REGION` | defaults to `us-east-1` |
| Repository variable, optional | `ENABLE_TF_PLAN` = `true` | turns on the pull-request plan job |
| Repository secret, optional | `AWS_PLAN_ROLE_ARN` | output `plan_role_arn` |

Role ARNs go into GitHub secrets, never into the repository. Workflow files can only be pushed with a token that has the
`workflow` scope. If branch protection is on for `main`, require the `CI checks` jobs.

The `production` environment name is also what the older live-deploy workflow (open PR 2, `deploy-production.yml`) and its
role `abw-connect-github-deploy` trust. That role is separate and still points only at the live app. The new workflows use
the secret name `AWS_ROLE_ARN`; PR 2 uses `AWS_DEPLOY_ROLE_ARN`. Keep them apart when both exist.

## Known pipeline limits

* The Lambda zip is not byte-reproducible (pip timestamps), so every staging run shows one in-place Lambda update. That is
  expected and harmless. Promotion reuses the staging zip, so production runs exactly what staging ran.
* The smoke test checks that the system is up and answers, not that answers are good. Answer quality is the evals' job.
* Amplify frontends are redeployed by zip on every run. A staging Basic Auth password, if you add one by hand, makes the
  frontend check return 401, which the smoke test accepts.
* Terraform and the actions are pinned to a version/major tag, not a commit SHA.

## What it creates

| File | Resources |
| --- | --- |
| `main.tf` | AWS provider, default tags, shared locals |
| `lambda.tf` | `<prefix>-api` function (python3.13, x86_64, 1024 MB, 60 s, handler `app.lambda_handler.handler`), its log group |
| `api_gateway.tf` | HTTP API with a single `$default` route, AWS_PROXY integration (payload 2.0, 30 s), `$default` auto-deploy stage, CORS, invoke permission |
| `dynamodb.tf` | `<prefix>-conversations`, `-turns`, `-feedback`, `-unanswered` (on demand, with the `status-created_at-index` index) |
| `iam.tf` | Lambda execution role and policy, Bedrock knowledge-base role and policy |
| `s3_kb.tf` | KB source bucket (private, AES256), the `kb/` documents and their `*.metadata.json` sidecars |
| `bedrock_kb.tf` | S3 Vectors bucket and index, knowledge base, S3 data source, ingestion trigger |
| `amplify.tf` | Repository-less Amplify app and `main` branch (optional, `create_amplify`) |
| `outputs.tf` | API endpoint, ids, table names, frontend URL |

Knowledge-base settings (same as live): Titan Text Embeddings v2, 1024 dimensions, float32, vector store
**Amazon S3 Vectors** (cosine), fixed-size chunking 512 tokens with 20% overlap, data source prefix `kb/`.
There is no OpenSearch Serverless collection, so nothing here bills by the hour.

## Variables

Everything environment-specific is a variable. See `variables.tf`; the ones you will change:

| Variable | Meaning |
| --- | --- |
| `name_prefix` | Prefix for every name and for `DDB_TABLE_PREFIX`. `abw-connect-staging` for staging, `abw-connect` for live. |
| `lambda_zip_path` | Zip built by `scripts/package_lambda.sh` |
| `kb_source_dir` | Folder with the KB documents (the repo `kb/`) |
| `upload_kb`, `start_ingestion` | Let Terraform upload the documents and start the ingestion job |
| `create_amplify` | Create the Amplify app and branch |
| `permissions_boundary_name` | Boundary policy for the two IAM roles this stack creates (created by `bootstrap/github-oidc`) |
| `kb_force_destroy` | Let `terraform destroy` empty and delete the buckets (staging only) |

No secrets are stored in the code or in the state. Account id, region, knowledge-base id and the API URL
come from the provider, data sources and resource attributes at plan time.

## Create a staging environment

You need Terraform 1.9 or newer, the AWS CLI, and AWS credentials with rights to create these resources.
Bedrock model access for `amazon.nova-lite-v1:0` and `amazon.titan-embed-text-v2:0` must already be enabled.

```bash
# 1. Build the Lambda zip from the committed backend/app tree.
#    PIP_CONSTRAINT pins the dependencies to the versions inside the live zip.
PIP_CONSTRAINT=infra/lambda-constraints.txt bash scripts/package_lambda.sh      # writes lambda-dist/abw-connect-backend.zip

# 2. Plan and apply by hand (normally the pipeline does this; see "State backend" for the init line).
cd infra
terraform init -backend-config="bucket=<state bucket>" -backend-config="key=abw-connect/staging/terraform.tfstate"
terraform fmt -check -recursive && terraform validate
terraform plan  -var-file=envs/staging.tfvars -out=staging.tfplan      # drop the permissions_boundary_name line until bootstrap/github-oidc exists
terraform apply staging.tfplan
```

Apply uploads `kb/`, creates the knowledge base and runs the ingestion job (the AWS CLI must be on the PATH).
A second `terraform plan` should report no changes.

### Deploy the frontend (outside Terraform)

Live uses a repository-less Amplify app with zip deployments. Terraform cannot upload a zip, so after apply:

```bash
API=$(terraform output -raw api_endpoint); APP=$(terraform output -raw amplify_app_id)
( cd ../frontend && npm ci && NEXT_PUBLIC_API_URL="$API" npm run build )       # static export in frontend/out
( cd ../frontend/out && zip -qr ../../frontend.zip . )
aws amplify create-deployment --app-id "$APP" --branch-name main                # returns jobId and zipUploadUrl
curl -X PUT -H 'Content-Type: application/zip' --data-binary @../frontend.zip "<zipUploadUrl>"
aws amplify start-deployment --app-id "$APP" --branch-name main --job-id <jobId>
```

Basic Auth is not managed by Terraform on purpose: `aws_amplify_branch` would store the credentials in
the Terraform state. Enable it outside Terraform if the environment needs it.

## State backend

State is remote: S3 bucket from `bootstrap/state`, key `abw-connect/<env>/terraform.tfstate`, encrypted, versioned,
native lock file. `backend.tf` is a partial configuration, so pass the bucket and key at init:

```bash
terraform init -backend-config="bucket=<state bucket>" -backend-config="key=abw-connect/staging/terraform.tfstate"
# or keep them in envs/<env>.backend.hcl (git-ignored; see envs/example.backend.hcl) and use -backend-config=envs/<env>.backend.hcl
```

Never commit a state file; it can contain resource details. A pre-migration copy of the first local staging state was kept
off-repo as a backup.

## Known differences from live

The staging parity check found these. Everything else (runtime, handler, memory, timeout, environment variable
names and values, API routes, integration, stage, CORS allow-lists, DynamoDB keys and indexes, KB embedding and
chunking settings, vector index settings, S3 encryption and public-access block, Amplify rules) matched.

| Item | Live | Terraform | Why |
| --- | --- | --- | --- |
| Lambda log permissions | `logs:*` actions on all log groups in the account | `CreateLogStream` and `PutLogEvents` on the function's own log group | Least privilege; Terraform creates the log group |
| KB role, vector index resource | `index/*` | the one index | Least privilege |
| Tags | `ManagedBy=abw-deploy` | `ManagedBy=terraform`, plus `Environment` | Provenance |
| API CORS `AllowCredentials` | not set | `false` | Provider default |
| Amplify Basic Auth | on | off | Not managed in Terraform (see above) |
| Lambda `CodeSha256` | hash of the live zip | hash of a rebuilt zip | Rebuilt zip has the same Python files; only console-script shebangs and `RECORD` files differ |
| KB sidecars | The live bucket's `*.metadata.json` files have no `retrieval_date` | The repo's sidecars include it | The repo and the live bucket have diverged; it has `includeForEmbedding: false` |

## The live app is not managed here (and the pipeline never changes it)

The hand-built live app keeps the plain `abw-connect` prefix and is not in any Terraform state. `variables.tf` rejects that
prefix. If you decide to bring it under Terraform one day, that is a separate, reviewed change:

1. Remove the prefix guard in `variables.tf` in that change, create `envs/live.tfvars` with `upload_kb = false`
   and `start_ingestion = false`, and `terraform import` each resource into its own state key.
2. `terraform plan` must show only the intentional differences listed above. Fix the code, not the live resource.
3. Only then give a pipeline role access, and keep the existing Basic Auth.

## Cost and teardown

Nothing in this stack is provisioned by the hour. Idle cost is small: on-demand DynamoDB, a small S3 Vectors
index, a few S3 objects, Lambda, HTTP API and Amplify hosting are all pay-per-use. Estimates are not verified
against the AWS Price List. Bedrock calls (Nova Lite, Titan embeddings) are billed per token.

```bash
cd infra
terraform destroy -var-file=envs/staging.tfvars
```

`kb_force_destroy = true` (set in `envs/staging.tfvars`) lets destroy remove the non-empty buckets.
