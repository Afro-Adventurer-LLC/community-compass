#!/usr/bin/env python3
"""Rewrite kb/*.metadata.json sidecars so each is <= 1024 bytes.

Bedrock Knowledge Bases rejects oversize metadata sidecars. This keeps the
filter fields (event_year, source_type) plus title/source_url, drops optional
keys if needed, and writes compact JSON. No AWS credentials required.

    python scripts/slim_kb_metadata.py           # rewrite in place
    python scripts/slim_kb_metadata.py --check   # exit 1 if any file is over the limit
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB_DIR = Path(ROOT / "kb")
MAX_BYTES = 1024
KEEP = ("title", "source_url", "event_year", "source_type", "section", "retrieval_date")
DROP_ORDER = ("retrieval_date", "section")


def _attr(spec: dict) -> dict:
    val = (spec or {}).get("value") or {}
    include = bool((spec or {}).get("includeForEmbedding", True))
    if "numberValue" in val:
        return {
            "value": {"type": "NUMBER", "numberValue": val["numberValue"]},
            "includeForEmbedding": include,
        }
    return {
        "value": {"type": "STRING", "stringValue": str(val.get("stringValue") or "")},
        "includeForEmbedding": include,
    }


def _dump(attrs: dict) -> bytes:
    payload = {"metadataAttributes": attrs}
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def slim_doc(data: dict) -> bytes:
    raw = data.get("metadataAttributes") or {}
    attrs = {k: _attr(raw[k]) for k in KEEP if k in raw}
    blob = _dump(attrs)
    for key in DROP_ORDER:
        if len(blob) <= MAX_BYTES:
            break
        if key in attrs:
            attrs.pop(key)
            blob = _dump(attrs)
    if len(blob) > MAX_BYTES and "title" in attrs:
        title = str(attrs["title"]["value"].get("stringValue") or "")
        attrs["title"]["value"]["stringValue"] = title[:80]
        blob = _dump(attrs)
    return blob


def iter_sidecars(root: Path):
    return sorted(root.rglob("*.metadata.json"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="only verify size, do not write")
    parser.add_argument("--kb-dir", default=str(KB_DIR))
    args = parser.parse_args()
    root = Path(args.kb_dir)
    files = iter_sidecars(root)
    if not files:
        print(f"no sidecars under {root}", file=sys.stderr)
        return 1
    failed = 0
    for path in files:
        original = path.read_bytes()
        data = json.loads(original.decode("utf-8"))
        blob = slim_doc(data)
        size = len(blob if not args.check else original)
        over = size > MAX_BYTES
        if over:
            failed += 1
        status = "OVER" if over else "ok"
        print(f"{status:4} {size:4}B  {path.relative_to(root)}")
        if args.check:
            continue
        if blob != original:
            path.write_bytes(blob)
    if failed:
        print(f"{failed} sidecar(s) exceed {MAX_BYTES} bytes", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
