"""Public document ids must not include s3:// URIs or the AWS account id."""
from __future__ import annotations

import json
import re

from app.services.index import canonical_doc_id, public_doc_ref, scrub_s3_uris
from app.services.retrieval import BedrockRetriever, LocalRetriever
from app.services.store import MemoryStore
# Built at runtime so this file never contains a 12-digit literal.
ACCOUNT = "9" * 12
BUCKET = f"abw-connect-staging-kb-{ACCOUNT}"
S3_DOC = f"s3://{BUCKET}/kb/official/2026/abw-terms.md"
S3_PASSAGE = f"{S3_DOC}#4"
PUBLIC_DOC = "kb/official/2026/abw-terms.md"
PUBLIC_PASSAGE = "kb/official/2026/abw-terms.md#4"

TWELVE_DIGIT = re.compile(r"(?<![\d.])\d{12}(?![\d.])")
SOURCE_URL = "https://aws.amazon.com/events/reinvent/experiences/all-builders-welcome/all-builders-welcome-terms/"


def _assert_public(obj, *, allow_empty=False):
    """No string in the JSON-like object may contain s3:// or a 12-digit number."""
    blob = json.dumps(obj, default=str)
    assert "s3://" not in blob.lower(), blob[:500]
    leaked = TWELVE_DIGIT.findall(blob)
    assert not leaked, f"12-digit number(s) in response: {leaked}"
    if not allow_empty:
        assert obj is not None


def test_public_doc_ref_strips_bucket_keeps_key_and_fragment():
    assert public_doc_ref(S3_PASSAGE) == PUBLIC_PASSAGE
    assert public_doc_ref(S3_DOC) == PUBLIC_DOC
    assert public_doc_ref(PUBLIC_PASSAGE) == PUBLIC_PASSAGE
    assert public_doc_ref("official/2026/abw-terms") == "official/2026/abw-terms"
    assert public_doc_ref("kb/official/2026/abw-terms.md") == "kb/official/2026/abw-terms.md"
    assert public_doc_ref(f"s3://{BUCKET}") == ""
    assert public_doc_ref("") == ""
    assert public_doc_ref("  ") == ""


def test_canonical_doc_id_accepts_public_refs():
    assert canonical_doc_id(public_doc_ref(S3_PASSAGE)) == canonical_doc_id(S3_PASSAGE)
    assert canonical_doc_id(PUBLIC_PASSAGE) == "official/2026/abw-terms"
    assert canonical_doc_id(PUBLIC_DOC) == "official/2026/abw-terms"


def test_local_index_doc_text_accepts_public_ref(index):
    text = index.doc_text(PUBLIC_DOC)
    assert "21 years of age" in text
    assert "Hotel accommodations" in text
    assert index.doc_text(PUBLIC_PASSAGE) == text


def test_scrub_drops_s3_source_url_and_rewrites_ids():
    dirty = {
        "citation": {"doc_id": S3_DOC, "source_url": S3_DOC},
        "passages": [{"id": S3_PASSAGE}],
        "notes": "see " + S3_PASSAGE,
    }
    clean = scrub_s3_uris(dirty)
    assert clean["citation"]["doc_id"] == PUBLIC_DOC
    assert clean["citation"]["source_url"] == ""
    assert clean["passages"][0]["id"] == PUBLIC_PASSAGE
    assert clean["notes"] == "see " + PUBLIC_PASSAGE
    _assert_public(clean)


class _FakeBedrock:
    def __init__(self, results):
        self.results = results
        self.calls = 0

    def retrieve(self, **kwargs):
        self.calls += 1
        return {"retrievalResults": self.results}


def _terms_chunk(index):
    return index.doc_text("official/2026/abw-terms")


def _bedrock_retriever(index, results):
    client = _FakeBedrock(results)
    ret = BedrockRetriever(kb_id="kb-test", fallback=LocalRetriever(index))
    ret._client = client
    return ret


def test_bedrock_retrieve_returns_public_ids(index):
    text = _terms_chunk(index)
    results = [
        {
            "content": {"text": text},
            "location": {"s3Location": {"uri": S3_PASSAGE}},
            "metadata": {
                "title": "All Builders Welcome Grant Terms and Conditions",
                "section": "Terms and conditions",
                "source_url": SOURCE_URL,
                "event_year": 2026,
                "source_type": "official",
                "retrieval_date": "2026-11-04",
            },
            "score": 0.71,
        },
        {
            # No HTTP source_url and an s3:// title: those must not leak.
            "content": {"text": "A full conference pass to the Event you applied for."},
            "location": {"s3Location": {"uri": f"s3://{BUCKET}/kb/official/2026/abw-grant.md#1"}},
            "metadata": {
                "doc_id": f"s3://{BUCKET}/kb/official/2026/abw-grant.md",
                "id": f"s3://{BUCKET}/kb/official/2026/abw-grant.md#1",
                "title": f"s3://{BUCKET}/kb/official/2026/abw-grant.md",
                "section": "All Builders Welcome Grant",
                "event_year": 2026,
                "source_type": "official",
            },
            "score": 0.65,
        },
    ]
    ret = _bedrock_retriever(index, results)
    passages = ret.retrieve("What does the ABW grant cover?", event_year=2026, include_alumni=True, k=8)
    assert len(passages) == 2
    assert passages[0].id == PUBLIC_PASSAGE
    assert passages[0].doc_id == PUBLIC_PASSAGE  # location URI included the fragment; no meta.doc_id
    assert passages[0].source_url == SOURCE_URL
    assert passages[0].title == "All Builders Welcome Grant Terms and Conditions"
    assert passages[1].id == "kb/official/2026/abw-grant.md#1"
    assert passages[1].doc_id == "kb/official/2026/abw-grant.md"
    assert passages[1].source_url == ""
    assert not passages[1].title.lower().startswith("s3://")
    for p in passages:
        _assert_public(p.as_dict())
    # Verifier lookups still resolve the local document from the public id.
    page = ret.document_text(passages[0].doc_id)
    assert "Hotel accommodations" in page


def test_chat_api_response_has_no_s3_or_account_id(index, store, client, monkeypatch):
    text = _terms_chunk(index)
    results = [
        {
            "content": {"text": text},
            "location": {"s3Location": {"uri": S3_PASSAGE}},
            "metadata": {
                "doc_id": S3_DOC,
                "id": S3_PASSAGE,
                "title": "All Builders Welcome Grant Terms and Conditions",
                "section": "Terms and conditions",
                "source_url": SOURCE_URL,
                "event_year": 2026,
                "source_type": "official",
                "retrieval_date": "2026-11-04",
            },
            "score": 0.8,
        }
    ]
    retriever = _bedrock_retriever(index, results)
    from app.services import retrieval as retmod
    from app.routes import api as apimod
    from app.services import store as storemod

    monkeypatch.setattr(retmod, "_retriever", retriever)
    monkeypatch.setattr(apimod, "get_retriever", lambda: retriever)
    monkeypatch.setattr(storemod, "_store", store)
    monkeypatch.setattr(apimod, "get_store", lambda: store)

    r = client.post(
        "/api/chat",
        json={"question": "What does the ABW grant cover?", "mode": "extractive"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    _assert_public(body)

    # Named fields the leak was found in, plus dropped / notes / traces.
    for claim in body.get("claims") or []:
        cit = claim.get("citation") or {}
        assert cit.get("doc_id", "").startswith("kb/") or not cit.get("doc_id")
        assert not (cit.get("source_url") or "").lower().startswith("s3://")
        for extra in claim.get("citations") or []:
            assert extra.get("doc_id", "").startswith("kb/") or not extra.get("doc_id")
    for p in body.get("passages") or []:
        assert p.get("id", "").startswith("kb/") or not p.get("id")
    for dropped in body.get("dropped") or []:
        _assert_public(dropped)
    for note in body.get("notes") or []:
        _assert_public(note)
        for cit in note.get("citations") or []:
            assert "s3://" not in (cit.get("doc_id") or "")

    # Stored turns are also clean. (MemoryStore.turns as a method is shadowed by the
    # instance dict of the same name, so call it unbound; DynamoStore.turns is a method.)
    cid = body["conversation_id"]
    stored = {"conversation_id": cid, "turns": MemoryStore.turns(store, cid)}
    _assert_public(stored)
    assert stored["turns"]

    # Advisor lists do not include document ids; still walk them.
    fb = client.get("/api/advisor/feedback")
    uq = client.get("/api/advisor/unanswered")
    assert fb.status_code == 200 and uq.status_code == 200
    _assert_public(fb.json())
    _assert_public(uq.json())


def test_stored_turn_from_before_the_fix_is_masked_on_read(store, client, monkeypatch):
    from app.services import store as storemod
    from app.routes import api as apimod

    monkeypatch.setattr(storemod, "_store", store)
    monkeypatch.setattr(apimod, "get_store", lambda: store)

    cid = store.create_conversation("grantee:2026:1")
    dirty = {
        "question": "What does the ABW grant cover?",
        "kind": "answer",
        "refused": False,
        "summary": "The grant covers a pass, flight, and hotel.",
        "claims": [
            {
                "text": "The grant covers a full conference pass.",
                "quote": "A full conference pass",
                "citation": {
                    "doc_id": S3_DOC,
                    "title": "Terms",
                    "section": "Terms and conditions",
                    "source_url": S3_DOC,
                },
                "citations": [{"doc_id": S3_DOC, "source_url": S3_DOC}],
            }
        ],
        "dropped": [{"reason": "see " + S3_PASSAGE, "source": S3_PASSAGE}],
        "notes": [{"kind": "info", "citations": [{"doc_id": S3_PASSAGE}]}],
        "passages": [{"id": S3_PASSAGE, "title": "Terms", "section": "Terms and conditions"}],
        "generator_error": None,
    }
    store.add_turn(cid, dirty["question"], dirty["question"], "new_topic", dirty, None)
    body = {"conversation_id": cid, "turns": MemoryStore.turns(store, cid)}
    _assert_public(body)
    turn = body["turns"][0]
    assert turn["claims"][0]["citation"]["doc_id"] == PUBLIC_DOC
    assert turn["claims"][0]["citation"]["source_url"] == ""
    assert turn["claims"][0]["citations"][0]["doc_id"] == PUBLIC_DOC
    assert turn["passages"][0]["id"] == PUBLIC_PASSAGE
    assert turn["notes"][0]["citations"][0]["doc_id"] == PUBLIC_PASSAGE
    assert PUBLIC_PASSAGE in turn["dropped"][0]["reason"]
    assert "s3://" not in json.dumps(turn)
