# AWS deployment notes

Local mock mode is the default. This document records the **safe, reproducible** Amplify + Lambda + API Gateway + DynamoDB + Bedrock path used for the deployed MVP. It does not contain credentials, account ids, knowledge-base ids, or Amplify app ids.

Do not treat a mock-green suite as production-valid under model variation.

Do not set access keys in Lambda environment variables. Use the function execution role.

## Frontend — Amplify Hosting (static export)

The frontend is a static Next.js export. Amplify should **not** use the Next.js SSR compute hosting option for this app.

- App root: `frontend/`
- Build: `npm ci && npm run build`
- Artifact directory: `out/` (from `output: "export"` in `frontend/next.config.mjs`)
- Images: unoptimized (required for static export)
- Environment: `NEXT_PUBLIC_API_URL=https://YOUR_API_GATEWAY_DOMAIN`
- Connect the GitHub repo; branch deploys and HTTPS are managed by Amplify.
- Optional: Route 53 custom domain.

Local development still uses `npm run dev` (see [LOCAL_SETUP.md](./LOCAL_SETUP.md)). Do not commit `frontend/out/` or `.next/`.

## Backend — Lambda + API Gateway

The FastAPI app is Lambda-ready via Mangum:

- Handler: `app.lambda_handler.handler` (or `app.main.handler`)
- Runtime: Python 3.12
- Package `backend/` (install `requirements.txt` into the bundle or a Lambda layer). Local zip, gitignored:

      bash scripts/package_lambda.sh

  That writes `lambda-dist/abw-connect-backend.zip` from **`git archive HEAD backend/app`** (committed tree only) plus `app/_build_manifest.txt` (git blob ids). Dirty worktree files are not packed. `/api/health` `git_sha` labels the packing commit; it is not by itself proof a previous zip matched git. Do not commit the zip.
- API Gateway HTTP API (recommended) with a catch-all `$default` or `/api/{proxy+}` route, payload format 2.0
- Memory 1024 MB, timeout ≥ 29 s (Bedrock Retrieve + Converse must fit in one request)

### Lambda environment

Set these on the function. **Do not** add a custom `AWS_REGION` environment variable; the runtime/role default region is used.

Use placeholders for ids and origins. Values below match the deployed MVP knobs (Bedrock Retrieve scores are 0–1). Do **not** copy these into local mock `.env` — local lexical scores stay at the code defaults (`ABW_MIN_SCORE=1.5`, `ABW_OFF_TOPIC_SCORE=4.0`).

| Name | Deployed value | Notes |
| --- | --- | --- |
| `ABW_USE_AWS` | `true` | Opt-in for Bedrock + DynamoDB. Never commit as a repo default. |
| `ABW_MIN_SCORE` | `0.25` | Bedrock 0–1 support floor. |
| `ABW_OFF_TOPIC_SCORE` | `0.15` | Below this, maybe-off-topic questions refuse. |
| `BEDROCK_KB_ID` | `YOUR_KB_ID` | Knowledge base id from the Bedrock console. |
| `BEDROCK_MODEL_ID` | `amazon.nova-lite-v1:0` | Converse model. |
| `ABW_EVENT_YEAR` | `2026` | Default event year. |
| `DDB_TABLE_PREFIX` | `abw-connect` | Table names `abw-connect-*`. |
| `GENERATOR_MODE` | `auto` | Backend stays auto; the UI defaults to LLM and POSTs `mode: llm`. |
| `LLM_TIMEOUT_S` | `15` | Then extractive fallback. |
| `CORS_ORIGINS` | `https://YOUR_AMPLIFY_DOMAIN` | Comma-separated if more than one origin. |
| `ABW_GIT_SHA` | packing commit hex | Optional. `/api/health` `git_sha`. Not a secret. `scripts/package_lambda.sh` also stamps `_build_meta.py` into the zip. No IAM change. |

Optional (only if you override defaults): `REWRITE_TIMEOUT_S`, `ABW_RETRIEVE_K`, `S3_KB_BUCKET`, `S3_KB_PREFIX`, `BEDROCK_DATA_SOURCE_ID`.

Skip secrets: no `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, Cognito client secrets, or account ids in env or git.

## DynamoDB tables

Prefix defaults to `abw-connect`. On-demand billing is enough for the MVP.

| Table | Keys | Purpose |
| --- | --- | --- |
| `abw-connect-conversations` | PK `id` (S) | Conversation metadata (`profile_key`, timestamps) |
| `abw-connect-turns` | PK `conversation_id` (S), SK `turn_no` (N) | Turns (`answer_json`, `cited`, `kind`) |
| `abw-connect-feedback` | PK `id` (S) | Thumbs and comments |
| `abw-connect-unanswered` | PK `id` (S) | System refusals and user flags for advisors |

Optional GSI on `abw-connect-unanswered`: `status` + `created_at` for the advisor view.

## S3 + Bedrock Knowledge Base

1. Bucket for `kb/` objects (block public access).
2. Bedrock Knowledge Base with an S3 data source on `s3://YOUR_KB_BUCKET/kb/`.
3. Metadata filters: sidecar files `*.md.metadata.json` with `event_year` (NUMBER) and `source_type` (STRING). Sidecars must be **≤ 1024 bytes**.
4. Slim before upload (rewrites compact JSON; drops optional keys if still over the limit):

       python scripts/slim_kb_metadata.py
       python scripts/slim_kb_metadata.py --check

5. Ingest: `python scripts/upload_kb.py` (uploads then `StartIngestionJob`). The upload script refuses oversize sidecars.
6. Runtime uses **Retrieve**, not RetrieveAndGenerate. Application code still runs support check, resolver, generation, and verification.

Do not commit staging copies of the bucket, ingestion zips, or generated `out/` builds.

## IAM (Lambda execution role)

Minimum actions (tighten resources to the specific KB, bucket, tables, and model):

- `bedrock:Retrieve` on the knowledge base
- `bedrock:InvokeModel` / `bedrock:Converse` on `BEDROCK_MODEL_ID`
- `s3:GetObject` on the KB bucket (only if the app reads objects directly; Retrieve usually does not need this)
- `dynamodb:GetItem`, `PutItem`, `UpdateItem`, `Query`, `Scan` on the four tables
- `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`

Bedrock KB itself needs a separate service role for S3 read + embedding model invoke (created in the Bedrock console).

## Cognito (later)

Not wired in the MVP. When added: Amplify Auth, API Gateway JWT authorizer, and a `sub` on conversation `profile_key`. Until then, conversations are scoped to `role:event_year:include_alumni`.

## Checklist

- [ ] Amplify app pointed at `frontend/`, artifact `out/`, `NEXT_PUBLIC_API_URL` set
- [ ] Lambda packaged from `scripts/package_lambda.sh` (or equivalent) and HTTP API deployed
- [ ] Lambda env matches the table above; no custom `AWS_REGION`; no access keys
- [ ] CORS matches the Amplify origin
- [ ] Four DynamoDB tables created
- [ ] Sidecars slimmed (`python scripts/slim_kb_metadata.py --check`) and S3 + Bedrock KB ingested
- [ ] Lambda role can Retrieve, Converse, and read/write DynamoDB
- [ ] `ABW_USE_AWS=true` only on the deployed function, never in git
- [ ] Smoke `/api/health`, then grant coverage and the Nov 13 vs November 14th accessibility question
