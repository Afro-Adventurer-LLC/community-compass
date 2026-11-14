"""Persistence for conversations, feedback, and unanswered questions.

Default is an in-memory store so tests and local mock mode need no AWS.
When ABW_USE_AWS=true, DynamoDB tables are used (see docs/AWS_DEPLOY.md).
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Protocol

from ..config import DDB_TABLE_PREFIX, AWS_REGION, use_aws
from .index import scrub_s3_uris


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id() -> str:
    return uuid.uuid4().hex


class ConversationNotFound(LookupError):
    pass


class ConversationForbidden(PermissionError):
    pass


class Store(Protocol):
    def create_conversation(self, profile_key: str) -> str: ...
    def check(self, cid: str, profile_key: str) -> dict: ...
    def add_turn(self, cid, question, standalone, turn_type, answer: dict, rewrite: dict | None) -> int: ...
    def history(self, cid: str, n: int = 6) -> list: ...
    def turns(self, cid: str) -> list: ...
    def add_feedback(self, rec: dict) -> str: ...
    def list_feedback(self) -> list: ...
    def add_unanswered(self, rec: dict) -> str: ...
    def list_unanswered(self) -> list: ...


class MemoryStore:
    def __init__(self):
        self._lock = threading.Lock()
        self.conversations: dict[str, dict] = {}
        self.turns: dict[str, list] = {}
        self.feedback: list[dict] = []
        self.unanswered: list[dict] = []

    def create_conversation(self, profile_key: str) -> str:
        cid = _id()
        with self._lock:
            self.conversations[cid] = dict(
                id=cid, profile_key=profile_key, created_at=_now(), updated_at=_now()
            )
            self.turns[cid] = []
        return cid

    def check(self, cid: str, profile_key: str) -> dict:
        with self._lock:
            rec = self.conversations.get(cid)
        if rec is None:
            raise ConversationNotFound(cid)
        if rec["profile_key"] != profile_key:
            raise ConversationForbidden(cid)
        return rec

    def add_turn(self, cid, question, standalone, turn_type, answer: dict, rewrite: dict | None) -> int:
        cited = sorted(
            {
                (cit.get("doc_id"), cit.get("section"))
                for cl in answer.get("claims") or []
                for cit in (cl.get("citations") or ([cl["citation"]] if cl.get("citation") else []))
            }
        )
        with self._lock:
            seq = self.turns.setdefault(cid, [])
            turn_no = len(seq) + 1
            rec = dict(
                conversation_id=cid,
                turn_no=turn_no,
                question=question,
                standalone_question=standalone,
                turn_type=turn_type,
                kind=answer.get("kind", "answer"),
                refused=bool(answer.get("refused")),
                answer=answer,
                cited=cited,
                rewrite=rewrite,
                topic=answer.get("topic"),
                latency_ms=answer.get("latency_ms"),
                created_at=_now(),
            )
            seq.append(rec)
            if cid in self.conversations:
                self.conversations[cid]["updated_at"] = _now()
        return turn_no

    def history(self, cid: str, n: int = 6) -> list:
        with self._lock:
            rows = list(reversed(self.turns.get(cid) or []))
        seg = []
        for rec in rows:
            if rec.get("kind") != "answer":
                continue
            claims = (rec.get("answer") or {}).get("claims") or []
            summary = (rec.get("answer") or {}).get("summary")
            short = summary or " ".join(cl.get("text", "") for cl in claims[:2])
            seg.append(
                dict(
                    turn_no=rec["turn_no"],
                    question=rec["question"],
                    standalone=rec["standalone_question"],
                    turn_type=rec["turn_type"],
                    refused=rec["refused"],
                    answer=(short or ("(no answer found)" if rec["refused"] else ""))[:400],
                    cited=rec.get("cited") or [],
                    topic=rec.get("topic"),
                )
            )
            if rec["turn_type"] == "new_topic" or len(seg) >= n:
                break
        return list(reversed(seg))

    def turns(self, cid: str) -> list:
        with self._lock:
            return [scrub_s3_uris(t["answer"]) for t in (self.turns.get(cid) or [])]

    def add_feedback(self, rec: dict) -> str:
        item = dict(id=_id(), created_at=_now(), **rec)
        with self._lock:
            self.feedback.append(item)
        return item["id"]

    def list_feedback(self) -> list:
        with self._lock:
            return list(reversed(self.feedback))

    def add_unanswered(self, rec: dict) -> str:
        item = dict(id=_id(), created_at=_now(), status="open", **rec)
        with self._lock:
            self.unanswered.append(item)
        return item["id"]

    def list_unanswered(self) -> list:
        with self._lock:
            return list(reversed(self.unanswered))


class DynamoStore:
    """Minimal DynamoDB adapter. Tables are created out of band (see docs/AWS_DEPLOY.md)."""

    def __init__(self, prefix: str | None = None, region: str | None = None):
        import boto3

        self.prefix = prefix or DDB_TABLE_PREFIX
        self.db = boto3.resource("dynamodb", region_name=region or AWS_REGION)
        self.t_conv = self.db.Table(f"{self.prefix}-conversations")
        self.t_turn = self.db.Table(f"{self.prefix}-turns")
        self.t_fb = self.db.Table(f"{self.prefix}-feedback")
        self.t_uq = self.db.Table(f"{self.prefix}-unanswered")

    def create_conversation(self, profile_key: str) -> str:
        cid = _id()
        self.t_conv.put_item(
            Item={"id": cid, "profile_key": profile_key, "created_at": _now(), "updated_at": _now()}
        )
        return cid

    def check(self, cid: str, profile_key: str) -> dict:
        r = self.t_conv.get_item(Key={"id": cid}).get("Item")
        if not r:
            raise ConversationNotFound(cid)
        if r["profile_key"] != profile_key:
            raise ConversationForbidden(cid)
        return r

    def add_turn(self, cid, question, standalone, turn_type, answer: dict, rewrite: dict | None) -> int:
        # Scan is avoided: turn_no is stored as conversation_id + monotonic timestamp fallback.
        # We count existing turns with a query on the conversation_id index.
        from boto3.dynamodb.conditions import Key
        import json as _json

        existing = self.t_turn.query(KeyConditionExpression=Key("conversation_id").eq(cid)).get("Items") or []
        turn_no = len(existing) + 1
        cited = sorted(
            {
                f"{cit.get('doc_id')}::{cit.get('section')}"
                for cl in answer.get("claims") or []
                for cit in (cl.get("citations") or ([cl["citation"]] if cl.get("citation") else []))
            }
        )
        self.t_turn.put_item(
            Item={
                "conversation_id": cid,
                "turn_no": turn_no,
                "question": question,
                "standalone_question": standalone,
                "turn_type": turn_type,
                "kind": answer.get("kind", "answer"),
                "refused": bool(answer.get("refused")),
                "answer_json": _json.dumps(answer, default=str),
                "cited": cited,
                "rewrite_json": _json.dumps(rewrite, default=str) if rewrite else "",
                "topic": answer.get("topic") or "",
                "latency_ms": int(answer.get("latency_ms") or 0),
                "created_at": _now(),
                "sk": f"{turn_no:06d}",
            }
        )
        self.t_conv.update_item(
            Key={"id": cid},
            UpdateExpression="SET updated_at = :u",
            ExpressionAttributeValues={":u": _now()},
        )
        return turn_no

    def history(self, cid: str, n: int = 6) -> list:
        import json as _json
        from boto3.dynamodb.conditions import Key

        items = self.t_turn.query(KeyConditionExpression=Key("conversation_id").eq(cid)).get("Items") or []
        items.sort(key=lambda r: int(r.get("turn_no") or 0), reverse=True)
        seg = []
        for rec in items:
            if rec.get("kind") != "answer":
                continue
            answer = _json.loads(rec.get("answer_json") or "{}")
            claims = answer.get("claims") or []
            summary = answer.get("summary")
            short = summary or " ".join(cl.get("text", "") for cl in claims[:2])
            seg.append(
                dict(
                    turn_no=int(rec["turn_no"]),
                    question=rec.get("question"),
                    standalone=rec.get("standalone_question"),
                    turn_type=rec.get("turn_type"),
                    refused=bool(rec.get("refused")),
                    answer=(short or ("(no answer found)" if rec.get("refused") else ""))[:400],
                    cited=rec.get("cited") or [],
                    topic=rec.get("topic") or None,
                )
            )
            if rec.get("turn_type") == "new_topic" or len(seg) >= n:
                break
        return list(reversed(seg))

    def turns(self, cid: str) -> list:
        import json as _json
        from boto3.dynamodb.conditions import Key

        items = self.t_turn.query(KeyConditionExpression=Key("conversation_id").eq(cid)).get("Items") or []
        items.sort(key=lambda r: int(r.get("turn_no") or 0))
        return [scrub_s3_uris(_json.loads(r.get("answer_json") or "{}")) for r in items]

    def add_feedback(self, rec: dict) -> str:
        import json as _json

        fid = _id()
        self.t_fb.put_item(Item={"id": fid, "created_at": _now(), **{k: _json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in rec.items()}})
        return fid

    def list_feedback(self) -> list:
        items = self.t_fb.scan().get("Items") or []
        items.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return items

    def add_unanswered(self, rec: dict) -> str:
        uid = _id()
        self.t_uq.put_item(Item={"id": uid, "created_at": _now(), "status": "open", **rec})
        return uid

    def list_unanswered(self) -> list:
        items = self.t_uq.scan().get("Items") or []
        items.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return items


_store: Store | None = None
_lock = threading.Lock()


def get_store() -> Store:
    global _store
    with _lock:
        if _store is None:
            _store = DynamoStore() if use_aws() else MemoryStore()
        return _store


def reset_store() -> None:
    global _store
    with _lock:
        _store = None
