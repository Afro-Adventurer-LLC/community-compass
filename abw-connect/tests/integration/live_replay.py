"""Replay real Bedrock Retrieve results captured for the live d55b08d failures.

The deployed Lambda has no local kb/ copy, so `document_text()` is empty there and
verification sees only retrieved chunk text. The replay retriever mirrors that:
it serves the captured chunks per query and returns "" for document_text().
Unknown queries return [] and are recorded in `misses` so tests can assert the
fixture still covers every retrieve the pipeline makes.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.retrieval import Passage

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "live_d55b08d" / "bedrock_retrieve.json"


def replay_key(query: str, event_year, include_alumni, k) -> str:
    return json.dumps([query, event_year, bool(include_alumni), int(k)])


class ReplayRetriever:
    name = "bedrock-replay"

    def __init__(self, path: Path = FIXTURE):
        self.calls = json.loads(Path(path).read_text())
        self.misses: list[str] = []

    def retrieve(self, query, *, event_year=None, include_alumni=True, k=12):
        key = replay_key(query, event_year, include_alumni, k)
        rows = self.calls.get(key)
        if rows is None:
            self.misses.append(key)
            return []
        return _from(rows)

    def document_text(self, doc_id: str) -> str:
        return ""


class RecordingRetriever:
    """Capture helper (used offline with real Bedrock credentials, never in tests)."""

    name = "bedrock"

    def __init__(self, inner, calls: dict | None = None):
        self.inner = inner
        self.calls = calls if calls is not None else {}

    def retrieve(self, query, *, event_year=None, include_alumni=True, k=12):
        key = replay_key(query, event_year, include_alumni, k)
        if key not in self.calls:
            ps = self.inner.retrieve(query, event_year=event_year, include_alumni=include_alumni, k=k)
            self.calls[key] = [
                dict(
                    id=p.id, doc_id=p.doc_id, title=p.title, section=p.section, text=p.text,
                    source_url=p.source_url, event_year=p.event_year, source_type=p.source_type,
                    retrieval_date=p.retrieval_date, topic=p.topic, score=p.score,
                    units=[list(u) for u in (p.units or [])], applies_to=p.applies_to,
                )
                for p in ps
            ]
        return _from(self.calls[key])

    def document_text(self, doc_id: str) -> str:
        return ""


def _from(rows):
    out = []
    for r in rows:
        r = dict(r)
        r["units"] = [tuple(u) for u in (r.get("units") or [])] or None
        out.append(Passage(**r))
    return out



# --- Scripted Nova replaying the live d55b08d outputs ---------------------------------

import re as _re

_UNIT_LINE = _re.compile(r"^\s*\[P(\d+)\.U(\d+)\]\s(.*)$", _re.M)


def find_unit(user: str, quote: str) -> str:
    """P-id of the first prompt unit that contains `quote` (as the live model cited it)."""
    for m in _UNIT_LINE.finditer(user or ""):
        if quote and quote in m.group(3):
            return f"P{m.group(1)}.U{m.group(2)}"
    return "P1.U0"


def is_answer_only(system: str) -> bool:
    return (system or "").startswith("You write a short user-visible answer")


def must_include_block(user: str) -> str:
    m = _re.search(r"left out these verified facts that answer the question:\n(.*?)(?:\nRejected draft:|\nWrite a new answer)", user or "", _re.S)
    return m.group(1) if m else ""


class TraceNova:
    """Claims call: cite `claims` [(text, quote)] with the answer `answer` (or `raw` JSON).
    short_answer calls: `shorts` in order (live drafts); afterwards `after(user)`.
    """

    name = "trace-nova"

    def __init__(self, answer="", claims=(), shorts=(), after=None, raw=None):
        self.answer = answer
        self.claims = list(claims)
        self.shorts = list(shorts)
        self.after = after
        self.raw = raw
        self.short_users: list[str] = []
        self.claim_users: list[str] = []

    def complete(self, system, user, **k):
        if is_answer_only(system):
            self.short_users.append(user)
            if self.shorts:
                return json.dumps({"answer": self.shorts.pop(0)})
            out = self.after(user) if self.after else None
            return json.dumps({"answer": out or ""})
        self.claim_users.append(user)
        if self.raw is not None:
            return self.raw(user) if callable(self.raw) else self.raw
        cl = [dict(text=t, source=find_unit(user, q), quote=q) for t, q in self.claims]
        return json.dumps({"answer": self.answer, "claims": cl})


def _repair_bit(line: str) -> str:
    low = line.lower()
    mm = _re.search(r"(\d+) to (\d+) minutes between venues", line)
    if mm:
        return f"allow {mm.group(1)} to {mm.group(2)} minutes between venues"
    if "university student" in low:
        s = "university students preparing for a career in technology can apply"
        if "limited number" in low:
            s += ", and a limited number of grants go to them"
        elif "first 5 years" in low:
            s += ", as can applicants within their first 5 years in tech"
        return s
    if "21" in low:
        return "applicants must be at least 21"
    if "previously accepted" in low:
        return "you must not have previously accepted a grant for the event"
    if "employee" in low or "affiliat" in low:
        return "you must not be an AWS employee or affiliate"
    if "additional time" in low:
        return "build in additional time for travel between properties"
    if "ten minutes" in low:
        return "arrive at your session room at least ten minutes early or your reserved seat may be released"
    # Otherwise Nova restates the listed verified fact briefly.
    return _re.sub(r"^(?:[A-I]\.|[-•*])\s+", "", line).strip().rstrip(".;")


def repair_answer(user: str) -> str | None:
    """What a compliant Nova does with the F19 coverage-repair prompt: keep the rejected
    draft and add each listed verified fact in its own words. Test double; it only states
    facts the prompt lists as verified. None when there is no repair block."""
    block = must_include_block(user)
    if not block:
        return None
    m = _re.search(r"Rejected draft: (.*)\n", user or "")
    prev = (m.group(1) if m else "").strip().rstrip(".")
    bits = []
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("- "):
            line = line[2:]
        if not line:
            continue
        b = _repair_bit(line)
        if b and b not in bits:
            bits.append(b)
    if not bits:
        return None
    return (prev + ". Also, " if prev else "") + "; ".join(bits) + "."
