#!/usr/bin/env python3
"""Upload kb/ to S3 and start a Bedrock Knowledge Base ingestion job.

Requires ABW_USE_AWS=true (or just valid AWS credentials), S3_KB_BUCKET, and BEDROCK_KB_ID.
Never prints secret values. Data source id is looked up from the knowledge base unless
BEDROCK_DATA_SOURCE_ID is set.

    python scripts/upload_kb.py --dry-run
    python scripts/upload_kb.py
"""
from __future__ import annotations

import argparse
import mimetypes
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB_DIR = Path(os.environ.get("ABW_KB_DIR", ROOT / "kb"))
SIDECAR_MAX_BYTES = 1024


def iter_files():
    for p in sorted(KB_DIR.rglob("*")):
        if p.is_file() and p.suffix.lower() in {".md", ".json", ".txt", ".html", ".pdf"}:
            yield p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--bucket", default=os.environ.get("S3_KB_BUCKET", ""))
    parser.add_argument("--prefix", default=os.environ.get("S3_KB_PREFIX", "kb/"))
    parser.add_argument("--kb-id", default=os.environ.get("BEDROCK_KB_ID", ""))
    parser.add_argument("--data-source-id", default=os.environ.get("BEDROCK_DATA_SOURCE_ID", ""))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")))
    args = parser.parse_args()
    prefix = args.prefix.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    files = list(iter_files())
    if not files:
        print(f"no files under {KB_DIR}", file=sys.stderr)
        sys.exit(1)
    over = [p for p in files if p.name.endswith(".metadata.json") and p.stat().st_size > SIDECAR_MAX_BYTES]
    if over:
        for p in over:
            print(f"sidecar {p} is {p.stat().st_size} bytes; limit is {SIDECAR_MAX_BYTES}", file=sys.stderr)
        print("run: python scripts/slim_kb_metadata.py", file=sys.stderr)
        sys.exit(1)
    print(f"{len(files)} files under {KB_DIR}")
    if args.dry_run or not args.bucket:
        for p in files:
            key = prefix + p.relative_to(KB_DIR).as_posix()
            print(f"  s3://{args.bucket or 'BUCKET'}/{key}")
        if not args.bucket:
            print("set S3_KB_BUCKET (or --bucket) to upload", file=sys.stderr)
            sys.exit(0 if args.dry_run else 1)
        if args.dry_run:
            return

    import boto3

    s3 = boto3.client("s3", region_name=args.region)
    for p in files:
        key = prefix + p.relative_to(KB_DIR).as_posix()
        ctype, _ = mimetypes.guess_type(p.name)
        extra = {"ContentType": ctype or "text/plain; charset=utf-8"}
        s3.upload_file(str(p), args.bucket, key, ExtraArgs=extra)
        print(f"uploaded s3://{args.bucket}/{key}")

    if not args.kb_id:
        print("uploaded objects; set BEDROCK_KB_ID to start an ingestion job")
        return

    agent = boto3.client("bedrock-agent", region_name=args.region)
    ds_id = args.data_source_id
    if not ds_id:
        kb = agent.get_knowledge_base(knowledgeBaseId=args.kb_id)
        # Data sources are listed separately.
        listed = agent.list_data_sources(knowledgeBaseId=args.kb_id).get("dataSourceSummaries") or []
        if not listed:
            print("no data sources on this knowledge base; create one pointing at the bucket/prefix")
            return
        ds_id = listed[0]["dataSourceId"]
        print(f"using data source {ds_id}")
    job = agent.start_ingestion_job(knowledgeBaseId=args.kb_id, dataSourceId=ds_id)
    info = job.get("ingestionJob") or {}
    print(f"ingestion job {info.get('ingestionJobId')} status={info.get('status')}")


if __name__ == "__main__":
    main()
