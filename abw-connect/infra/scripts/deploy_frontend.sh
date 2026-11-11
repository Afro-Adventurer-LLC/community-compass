#!/usr/bin/env bash
# Deploy a static-export zip to a repository-less Amplify app (zip deployment) and wait for it.
#   deploy_frontend.sh <amplify-app-id> <branch> <frontend.zip>
# Needs the AWS CLI with credentials for the TARGET environment. Prints no secrets
# (the pre-signed upload URL is never printed).
set -euo pipefail

APP_ID="${1:?amplify app id}"
BRANCH="${2:?branch name}"
ZIP="${3:?path to frontend.zip}"
[[ -s "$ZIP" ]] || { echo "deploy_frontend: $ZIP is missing or empty" >&2; exit 1; }

DEPLOYMENT="$(aws amplify create-deployment --app-id "$APP_ID" --branch-name "$BRANCH" --output json)"
JOB_ID="$(jq -r '.jobId' <<<"$DEPLOYMENT")"
UPLOAD_URL="$(jq -r '.zipUploadUrl' <<<"$DEPLOYMENT")"
# In GitHub Actions this line hides the pre-signed URL from the logs; outside Actions it is skipped.
[[ "${GITHUB_ACTIONS:-}" == "true" ]] && echo "::add-mask::${UPLOAD_URL}"
echo "amplify deployment job: ${JOB_ID}"

curl --fail --silent --show-error --max-time 300 -X PUT \
  -H 'Content-Type: application/zip' --data-binary "@${ZIP}" "$UPLOAD_URL" >/dev/null
echo "zip uploaded"

aws amplify start-deployment --app-id "$APP_ID" --branch-name "$BRANCH" --job-id "$JOB_ID" >/dev/null

for _ in $(seq 1 60); do
  STATUS="$(aws amplify get-job --app-id "$APP_ID" --branch-name "$BRANCH" --job-id "$JOB_ID" \
    --query 'job.summary.status' --output text)"
  echo "amplify job status: ${STATUS}"
  case "$STATUS" in
    SUCCEED) exit 0 ;;
    FAILED | CANCELLED)
      echo "amplify deployment ${STATUS}" >&2
      exit 1
      ;;
  esac
  sleep 5
done
echo "amplify deployment did not finish within 5 minutes" >&2
exit 1
