"""Central configuration. Everything is overridable by environment variables.

Default is mock/offline mode so the app and tests run with no AWS credentials.
Set ABW_USE_AWS=true (and provide a profile/region) to call Bedrock and DynamoDB.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]

KB_DIR = Path(os.environ.get("ABW_KB_DIR", ROOT / "kb")).resolve()

GENERATOR_MODE = os.environ.get("GENERATOR_MODE", "auto")  # auto | extractive | llm
LLM_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "15"))
REWRITE_TIMEOUT_S = float(os.environ.get("REWRITE_TIMEOUT_S", "4"))
CHAT_HISTORY_TURNS = int(os.environ.get("CHAT_HISTORY_TURNS", "6"))
DEFAULT_EVENT_YEAR = int(os.environ.get("ABW_EVENT_YEAR", "2026"))
RETRIEVE_K = int(os.environ.get("ABW_RETRIEVE_K", "12"))

# Support threshold on the best local/Bedrock retrieval score.
MIN_SCORE = float(os.environ.get("ABW_MIN_SCORE", "1.5"))
OFF_TOPIC_SCORE = float(os.environ.get("ABW_OFF_TOPIC_SCORE", "4.0"))

AWS_REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
BEDROCK_KB_ID = os.environ.get("BEDROCK_KB_ID", "")
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID",
    "amazon.nova-lite-v1:0",
)
DDB_TABLE_PREFIX = os.environ.get("DDB_TABLE_PREFIX", "abw-connect")
S3_KB_BUCKET = os.environ.get("S3_KB_BUCKET", "")
S3_KB_PREFIX = os.environ.get("S3_KB_PREFIX", "kb/")
DATA_DIR = Path(os.environ.get("ABW_DATA_DIR", BACKEND_ROOT / "data")).resolve()

CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if o.strip()
]


def use_aws() -> bool:
    """Real AWS is opt-in. Tests and local MVP stay on the mock retriever/store/LLM."""
    return os.environ.get("ABW_USE_AWS", "").strip().lower() in {"1", "true", "yes", "on"}


def _ok_git_sha(value: str) -> bool:
    return bool(value) and all(c in "0123456789abcdefABCDEF" for c in value) and 7 <= len(value) <= 40


def deploy_git_sha() -> str | None:
    """Commit identity for /api/health. Never a secret.

    Prefer ABW_GIT_SHA (plain hex, set at deploy). Else a file stamped into the
    Lambda zip by scripts/package_lambda.sh. Missing is allowed — live QA then
    cannot prove the running SHA from the API alone.
    """
    raw = (os.environ.get("ABW_GIT_SHA") or "").strip()
    if _ok_git_sha(raw):
        return raw[:40]
    try:
        from . import _build_meta  # stamped at package time; absent in git

        stamped = str(getattr(_build_meta, "GIT_SHA", "") or "").strip()
        if _ok_git_sha(stamped):
            return stamped[:40]
    except Exception:
        pass
    return None
