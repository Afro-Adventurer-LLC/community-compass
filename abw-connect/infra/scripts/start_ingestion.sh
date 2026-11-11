#!/usr/bin/env bash
# Start a Bedrock KB ingestion job and wait for it. Used by terraform_data.ingestion.
# Needs the AWS CLI and credentials in the environment. Prints no secrets.
set -euo pipefail
: "${KB_ID:?}" "${DATA_SOURCE_ID:?}" "${AWS_REGION:?}"

JOB_ID="$(aws bedrock-agent start-ingestion-job --region "$AWS_REGION" \
  --knowledge-base-id "$KB_ID" --data-source-id "$DATA_SOURCE_ID" \
  --query 'ingestionJob.ingestionJobId' --output text)"
echo "ingestion job started: $JOB_ID"

for _ in $(seq 1 60); do
  STATUS="$(aws bedrock-agent get-ingestion-job --region "$AWS_REGION" \
    --knowledge-base-id "$KB_ID" --data-source-id "$DATA_SOURCE_ID" \
    --ingestion-job-id "$JOB_ID" --query 'ingestionJob.status' --output text)"
  echo "ingestion status: $STATUS"
  case "$STATUS" in
    COMPLETE) exit 0 ;;
    FAILED | STOPPED)
      aws bedrock-agent get-ingestion-job --region "$AWS_REGION" \
        --knowledge-base-id "$KB_ID" --data-source-id "$DATA_SOURCE_ID" \
        --ingestion-job-id "$JOB_ID" --query 'ingestionJob.failureReasons' --output text >&2
      exit 1
      ;;
  esac
  sleep 10
done
echo "ingestion did not finish within 10 minutes" >&2
exit 1
