"""Retriever interface: Bedrock Knowledge Bases Retrieve, plus a local mock index.

Callers always go through retrieve(); generation is never done by the knowledge base
(RetrieveAndGenerate is not used).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..config import BEDROCK_KB_ID, AWS_REGION, RETRIEVE_K, use_aws
from .index import Chunk, LocalIndex, public_doc_ref
from .textnorm import topic_of


@dataclass
class Passage:
    id: str
    doc_id: str
    title: str
    section: str
    text: str
    source_url: str
    event_year: int
    source_type: str
    retrieval_date: str = ""
    topic: str | None = None
    score: float = 0.0
    primary: bool = False
    units: list[tuple[int, int]] | None = None
    applies_to: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "doc_id": self.doc_id,
            "title": self.title,
            "section": self.section,
            "text": self.text,
            "source_url": self.source_url,
            "event_year": self.event_year,
            "source_type": self.source_type,
            "retrieval_date": self.retrieval_date,
            "topic": self.topic,
            "score": self.score,
            "rrf": self.score,
            "primary": self.primary,
            "units": self.units or _units_for(self.text),
            "kind": "section",
            "applies_to": self.applies_to or {"source_type": self.source_type, "event_year": self.event_year},
        }


def _units_for(text: str) -> list[tuple[int, int]]:
    """Paragraph / bullet spans in `text` for the extractive generator."""
    units = []
    start = 0
    for para in text.split("\n"):
        end = start + len(para)
        blob = para.strip()
        if blob and not blob.startswith("#"):
            # skip very short headings leftover
            units.append((start, end))
        start = end + 1
    if not units:
        units = [(0, len(text))]
    return units


class Retriever(Protocol):
    name: str

    def retrieve(
        self,
        query: str,
        *,
        event_year: int | None = None,
        include_alumni: bool = True,
        k: int = RETRIEVE_K,
    ) -> list[Passage]: ...

    def document_text(self, doc_id: str) -> str: ...


class LocalRetriever:
    """Lexical retriever over kb/. Default for local-dev and tests."""

    name = "local"

    def __init__(self, index: LocalIndex | None = None):
        self.index = index or LocalIndex()

    def retrieve(
        self,
        query: str,
        *,
        event_year: int | None = None,
        include_alumni: bool = True,
        k: int = RETRIEVE_K,
    ) -> list[Passage]:
        hits = self.index.search(query, event_year=event_year, include_alumni=include_alumni, k=k)
        out = []
        for chunk, score in hits:
            out.append(_chunk_to_passage(chunk, score))
        return out

    def document_text(self, doc_id: str) -> str:
        return self.index.doc_text(doc_id)


def _chunk_to_passage(chunk: Chunk, score: float) -> Passage:
    return Passage(
        id=chunk.id,
        doc_id=chunk.doc_id,
        title=chunk.title,
        section=chunk.section,
        text=chunk.text,
        source_url=chunk.source_url,
        event_year=chunk.event_year,
        source_type=chunk.source_type,
        retrieval_date=chunk.retrieval_date,
        topic=chunk.topic or topic_of(chunk.text),
        score=score,
        units=_units_for(chunk.text),
        applies_to={"source_type": chunk.source_type, "event_year": chunk.event_year},
    )


class BedrockRetriever:
    """Amazon Bedrock Knowledge Bases Retrieve API (not RetrieveAndGenerate)."""

    name = "bedrock"

    def __init__(self, kb_id: str | None = None, region: str | None = None, fallback: LocalRetriever | None = None):
        self.kb_id = kb_id or BEDROCK_KB_ID
        self.region = region or AWS_REGION
        self.fallback = fallback or LocalRetriever()
        self._client = None

    def _client_get(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-agent-runtime", region_name=self.region)
        return self._client

    def retrieve(
        self,
        query: str,
        *,
        event_year: int | None = None,
        include_alumni: bool = True,
        k: int = RETRIEVE_K,
    ) -> list[Passage]:
        if not self.kb_id:
            return self.fallback.retrieve(
                query, event_year=event_year, include_alumni=include_alumni, k=k
            )
        filt = _metadata_filter(event_year, include_alumni)
        kwargs = {
            "knowledgeBaseId": self.kb_id,
            "retrievalQuery": {"text": query},
            "retrievalConfiguration": {
                "vectorSearchConfiguration": {
                    "numberOfResults": k,
                    **({"filter": filt} if filt else {}),
                }
            },
        }
        resp = self._client_get().retrieve(**kwargs)
        passages = []
        for i, item in enumerate(resp.get("retrievalResults") or []):
            content = (item.get("content") or {}).get("text") or ""
            loc = item.get("location") or {}
            s3 = (loc.get("s3Location") or {}).get("uri") or ""
            meta = item.get("metadata") or {}
            source_type = str(meta.get("source_type") or "official")
            year = meta.get("event_year")
            try:
                year = int(year) if year is not None else 0
            except (TypeError, ValueError):
                year = 0
            if source_type == "alumni_experience" and not include_alumni:
                continue
            # Public ids are the bucket-relative key; never the s3://bucket/... URI
            # (the bucket name includes the AWS account id).
            doc_id = public_doc_ref(str(meta.get("doc_id") or s3 or f"bedrock-{i}"))
            raw_id = meta.get("id")
            if raw_id:
                passage_id = public_doc_ref(str(raw_id))
            elif s3:
                # The S3 location often already includes a #chunk; don't append another.
                passage_id = public_doc_ref(s3)
                if "#" not in passage_id:
                    passage_id = f"{passage_id}#{i}"
            else:
                passage_id = f"{doc_id}#{i}" if doc_id else f"bedrock-{i}"
            title_raw = str(meta.get("title") or "")
            title = public_doc_ref(title_raw) if title_raw.lower().startswith("s3://") else (title_raw or doc_id)
            src = str(meta.get("source_url") or "")
            if src.lower().startswith("s3://"):
                src = ""
            passages.append(
                Passage(
                    id=passage_id,
                    doc_id=doc_id,
                    title=title,
                    section=str(meta.get("section") or ""),
                    text=content,
                    source_url=src,
                    event_year=year,
                    source_type=source_type,
                    retrieval_date=str(meta.get("retrieval_date") or ""),
                    topic=topic_of(content),
                    score=float(item.get("score") or 0.0),
                    units=_units_for(content),
                    applies_to={"source_type": source_type, "event_year": year},
                )
            )
        return passages

    def document_text(self, doc_id: str) -> str:
        # Bedrock Retrieve returns chunk text; verification uses that chunk (and local corpus if present).
        local = self.fallback.document_text(doc_id)
        return local


def _metadata_filter(event_year: int | None, include_alumni: bool) -> dict | None:
    """Bedrock KB metadata filter. Official docs are scoped to event_year; alumni may be any year."""
    if not event_year:
        return None
    official = {
        "andAll": [
            {"equals": {"key": "source_type", "value": "official"}},
            {"equals": {"key": "event_year", "value": event_year}},
        ]
    }
    if not include_alumni:
        return official
    return {
        "orAll": [
            official,
            {"equals": {"key": "source_type", "value": "alumni_experience"}},
        ]
    }


_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        local = LocalRetriever()
        _retriever = BedrockRetriever(fallback=local) if use_aws() else local
    return _retriever


def reset_retriever() -> None:
    global _retriever
    _retriever = None
