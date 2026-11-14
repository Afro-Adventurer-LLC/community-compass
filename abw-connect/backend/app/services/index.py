"""Local lexical index over kb/ markdown + metadata sidecars.

Used by the mock retriever so the app and tests run with no AWS credentials.
Chunks are heading-bounded sections; quote verification uses the full document text.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..config import KB_DIR
from .textnorm import tokenize, topic_of

STOP = {
    "the", "a", "an", "is", "are", "was", "were", "be", "to", "of", "in", "on", "at", "for",
    "and", "or", "my", "me", "i", "we", "you", "your", "our", "do", "does", "did", "can",
    "what", "when", "where", "who", "how", "which", "why", "with", "from", "this", "that",
    "it", "if", "not", "no", "yes", "please", "need", "get", "got",
}

EXPAND = {
    "eligible": ["eligibility", "21", "participation", "years"],
    "eligibility": ["eligible", "21", "participation"],
    "old": ["years", "age", "21"],
    "deadline": ["received", "november", "request", "accommodations"],
    "accommodations": ["accessibility", "request", "asl", "deadline"],
    "accessibility": ["accommodations", "asl", "caption", "request"],
    "travel": ["flight", "agency", "arrangements", "14"],
    "booked": ["travel", "agency", "arrangements"],
    "cover": ["pass", "flight", "hotel", "benefits", "covers", "include", "pay"],
    "covers": ["pass", "flight", "hotel", "benefits", "cover", "include", "pay"],
    "coverage": ["cover", "covers", "benefits", "pass", "flight", "hotel"],
    "summarize": ["cover", "covers", "benefits", "include"],
    "buffer": ["time", "travel", "allow", "properties"],
    "moving": ["travel", "venues", "properties"],
    "include": ["cover", "covers", "benefits", "pass", "flight", "hotel"],
    "included": ["cover", "covers", "benefits", "pass", "flight", "hotel"],
    "includes": ["cover", "covers", "benefits", "pass", "flight", "hotel"],
    "inclusions": ["include", "benefits", "pass", "flight", "hotel"],
    "pay": ["cover", "covers", "benefits", "flight", "hotel", "pass"],
    "pays": ["cover", "covers", "benefits", "flight", "hotel", "pass"],
    "costs": ["cover", "pay", "benefits", "pass", "flight", "hotel"],
    "airfare": ["flight", "roundtrip"],
    "lodging": ["hotel", "accommodations"],
    "ticket": ["pass", "conference"],
    "badge": ["pass", "conference"],
    "package": ["benefits", "grant"],
    "components": ["benefits", "pass", "flight", "hotel"],
    "outline": ["cover", "covers", "benefits"],
    "receive": ["benefits", "cover", "pass"],
    "receives": ["benefits", "cover", "pass"],
    "scholarship": ["grant", "program"],
    "time": ["minutes", "hours"],
    "leave": ["allow"],
    "venues": ["properties", "venue"],
    "properties": ["venues", "venue"],
    "long": ["minutes", "time"],
    "student": ["university", "eligibility", "career", "21"],
    "students": ["university", "eligibility", "career", "21"],
    "undergrad": ["student", "students", "university", "eligibility", "21"],
    "undergrads": ["student", "students", "university", "eligibility", "21"],
    "undergraduate": ["student", "students", "university", "eligibility", "21"],
    "college": ["university", "student", "students"],
    "qualify": ["eligible", "eligibility", "21"],
    "qualifies": ["eligible", "eligibility", "21"],
    "campus": ["venues", "properties", "venue"],
    "campuses": ["venues", "properties", "venue"],
    "transit": ["travel", "venues", "properties", "time"],
    "across": ["between", "venues", "properties"],
    "reapply": ["subsequent", "cohorts", "selected"],
    "rejected": ["selected", "reapply", "subsequent"],
}

HEADING = re.compile(r"^(#{2,4})\s+(.*)$")


def canonical_doc_id(doc_id: str) -> str:
    """Map Bedrock S3 URIs (s3://bucket/kb/official/2026/foo.md#0) onto local doc ids."""
    s = (doc_id or "").strip()
    if not s:
        return ""
    s = s.split("#", 1)[0]
    if "://" in s:
        s = s.split("://", 1)[-1]
        s = s.split("/", 1)[-1] if s else s
    if "/kb/" in s:
        s = s.split("/kb/", 1)[1]
    elif s.startswith("kb/"):
        s = s[3:]
    s = s.lstrip("/")
    if s.endswith(".md"):
        s = s[:-3]
    return s


_S3_URI = re.compile('s3://[^\\s\\"\']+', re.I)


def public_doc_ref(value: str) -> str:
    """Strip the `s3://bucket/` prefix; keep the object key and optional #fragment.

    `s3://abw-connect-staging-kb-<account-id>/kb/official/2026/abw-terms.md#4`
    becomes `kb/official/2026/abw-terms.md#4`. Already-relative keys and local
    doc ids are returned unchanged. A bare `s3://bucket` (no key) becomes "".
    """
    s = (value or "").strip()
    if not s:
        return ""
    m = re.match(r"s3://([^/]+)(?:/(.*))?$", s, re.I)
    if not m:
        return s
    return m.group(2) or ""


def _rewrite_s3_uris(text: str, *, drop_if_source_url: bool = False) -> str:
    if not text:
        return text
    if drop_if_source_url and text.lower().startswith("s3://"):
        return ""
    return _S3_URI.sub(lambda m: public_doc_ref(m.group(0)), text)


def scrub_s3_uris(obj, *, _key: str | None = None):
    """Rewrite any `s3://bucket/key` strings in a JSON-like object to `key`.

    Used as a safety net on API answers and stored turns so older conversations
    do not leak the Knowledge Base bucket name (which includes the account id).
    An S3 URI in `source_url` is dropped rather than turned into a non-URL key.
    """
    if isinstance(obj, str):
        return _rewrite_s3_uris(obj, drop_if_source_url=_key == "source_url")
    if isinstance(obj, list):
        return [scrub_s3_uris(x) for x in obj]
    if isinstance(obj, tuple):
        return type(obj)(scrub_s3_uris(x) for x in obj)
    if isinstance(obj, dict):
        return {k: scrub_s3_uris(v, _key=k if isinstance(k, str) else None) for k, v in obj.items()}
    return obj


META_LINE = re.compile(r"^(-|\*)\s+(Source|Section|Event year|Source type|Retrieved):", re.I)


def _body_of(text: str) -> str:
    """Drop the YAML-like source header so event year / URL lines do not dominate retrieval."""
    lines = text.splitlines()
    i = 0
    if lines and lines[0].startswith("# "):
        i = 1
    while i < len(lines) and (not lines[i].strip() or META_LINE.match(lines[i])):
        i += 1
    rest = "\n".join(lines[i:]).strip()
    return rest or text


@dataclass
class Document:
    doc_id: str
    path: str
    title: str
    source_url: str
    section: str
    event_year: int
    source_type: str
    retrieval_date: str
    text: str


@dataclass
class Chunk:
    id: str
    doc_id: str
    title: str
    section: str
    source_url: str
    event_year: int
    source_type: str
    retrieval_date: str
    text: str
    topic: str | None
    tokens: list[str] = field(default_factory=list)


def _read_sidecar(md_path: Path) -> dict:
    side = Path(str(md_path) + ".metadata.json")
    if not side.exists():
        return {}
    try:
        data = json.loads(side.read_text())
    except json.JSONDecodeError:
        return {}
    attrs = data.get("metadataAttributes") or {}
    out = {}
    for k, spec in attrs.items():
        val = (spec or {}).get("value") or {}
        if "stringValue" in val:
            out[k] = val["stringValue"]
        elif "numberValue" in val:
            out[k] = val["numberValue"]
    return out


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, body) pairs on ## / ### / #### headings."""
    lines = text.splitlines()
    sections: list[list[str]] = []
    current = ["Introduction"]
    body: list[str] = []

    def flush():
        blob = "\n".join(body).strip()
        if blob:
            sections.append([current[-1], blob])

    for line in lines:
        m = HEADING.match(line)
        if m:
            flush()
            current.append(m.group(2).strip())
            body = [line]
        else:
            body.append(line)
    flush()
    if not sections:
        return [("Document", text.strip())]
    return [(h, b) for h, b in sections]


def load_corpus(kb_dir: Path | None = None) -> tuple[list[Document], list[Chunk]]:
    root = Path(kb_dir or KB_DIR)
    docs: list[Document] = []
    chunks: list[Chunk] = []
    if not root.exists():
        return docs, chunks
    for md in sorted(root.rglob("*.md")):
        if md.name.lower() == "readme.md":
            continue
        meta = _read_sidecar(md)
        rel = md.relative_to(root).as_posix()
        doc_id = rel[: -len(md.suffix)] if md.suffix else rel
        raw = md.read_text(encoding="utf-8")
        text = _body_of(raw)
        title = meta.get("title") or md.stem.replace("-", " ").title()
        source_url = meta.get("source_url") or ""
        section = meta.get("section") or ""
        event_year = int(meta.get("event_year") or 0) or None
        source_type = meta.get("source_type") or "official"
        retrieval_date = meta.get("retrieval_date") or ""
        docs.append(
            Document(
                doc_id=doc_id,
                path=str(md),
                title=title,
                source_url=source_url,
                section=section,
                event_year=event_year or 0,
                source_type=source_type,
                retrieval_date=retrieval_date,
                text=raw,
            )
        )
        for i, (heading, body) in enumerate(_split_sections(text)):
            cid = f"{doc_id}#s{i}"
            chunks.append(
                Chunk(
                    id=cid,
                    doc_id=doc_id,
                    title=title,
                    section=heading or section,
                    source_url=source_url,
                    event_year=event_year or 0,
                    source_type=source_type,
                    retrieval_date=retrieval_date,
                    text=body,
                    topic=topic_of(heading + "\n" + body),
                    tokens=tokenize(body),
                )
            )
    return docs, chunks


class LocalIndex:
    """In-memory BM25-ish index over KB chunks."""

    def __init__(self, kb_dir: Path | None = None):
        self.docs, self.chunks = load_corpus(kb_dir)
        self.by_doc = {d.doc_id: d for d in self.docs}
        self.by_chunk = {c.id: c for c in self.chunks}
        self.df: dict[str, int] = {}
        for c in self.chunks:
            for tok in set(c.tokens):
                self.df[tok] = self.df.get(tok, 0) + 1
        self.n = max(len(self.chunks), 1)
        self.avgdl = (sum(len(c.tokens) for c in self.chunks) / self.n) if self.chunks else 1.0

    def idf(self, tok: str) -> float:
        df = self.df.get(tok, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def query_tokens(self, query: str) -> list[str]:
        base = [t for t in tokenize(query) if t not in STOP]
        extra: list[str] = []
        for t in list(base):
            extra.extend(EXPAND.get(t, []))
        return base + extra

    def score(self, query: str, chunk: Chunk) -> float:
        q_tokens = self.query_tokens(query)
        if not q_tokens:
            return 0.0
        tf: dict[str, int] = {}
        for t in chunk.tokens:
            tf[t] = tf.get(t, 0) + 1
        k1, b = 1.4, 0.75
        dl = len(chunk.tokens) or 1
        s = 0.0
        for tok in q_tokens:
            f = tf.get(tok, 0)
            if not f:
                continue
            s += self.idf(tok) * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / self.avgdl))
        qset = set(q_tokens)
        heading_toks = set(tokenize(chunk.section + " " + chunk.title))
        s += 0.55 * len(qset & heading_toks)
        # Prefer official passages when the lexical evidence is otherwise similar.
        if chunk.source_type == "official":
            s *= 1.15
        return s

    def search(
        self,
        query: str,
        *,
        event_year: int | None = None,
        include_alumni: bool = True,
        k: int = 12,
    ) -> list[tuple[Chunk, float]]:
        scored: list[tuple[Chunk, float]] = []
        for c in self.chunks:
            if c.source_type == "alumni_experience" and not include_alumni:
                continue
            if (
                event_year
                and c.source_type == "official"
                and c.event_year
                and c.event_year != event_year
            ):
                continue
            s = self.score(query, c)
            if s > 0:
                scored.append((c, s))
        scored.sort(key=lambda x: -x[1])
        return scored[:k]

    def doc_text(self, doc_id: str) -> str:
        d = self.by_doc.get(doc_id)
        if d:
            return d.text
        alt = canonical_doc_id(doc_id)
        if alt and alt != doc_id:
            d = self.by_doc.get(alt)
            if d:
                return d.text
        return ""
