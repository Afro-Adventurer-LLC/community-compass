"""Repaired-schema / unknown-source recovery from live F1 and cover_06 samples."""
from pathlib import Path

from app.services.ask import _collect_verified
import json

from app.services.generator import (
    BedrockGenerator,
    assign_source_from_meta,
    assign_source_from_quote,
    bind_claim_source,
    normalize_generated_claim,
    parse_llm_json,
    source_passage_id,
)

ROOT = Path(__file__).resolve().parents[2]
TERMS_PAGE = (ROOT / "kb/official/2026/abw-terms.md").read_text()

# Live q1-run10 (pre-ecfa QA): json_repair nested the claim into `source` as a
# Python-repr dict; quote was empty; verifier dropped every claim as unknown source.
F1_PASS = {
    "text": "The grant covers a full conference pass to the event you applied for.",
    "source": str(
        {
            "text": 'Participants of the Program will receive the following benefits ("Program Benefits"): - A full conference pass to the Event you applied for;',
            "source": "P4.U0",
            "quote": 'Participants of the Program will receive the following benefits ("Program Benefits"): - A full conference pass to the Event you applied for;',
        }
    ),
    "quote": "",
}
F1_FLIGHT = {
    "text": "The grant covers roundtrip flight between an airport near (within 50 miles of) the address you list in your application and the city of the event.",
    "source": str(
        {
            "text": 'Roundtrip flight between an airport near (within 50 miles of) the address you list in your application and the city of the Event ("Event Location");',
            "source": "P4.U0",
            "quote": 'Roundtrip flight between an airport near (within 50 miles of) the address you list in your application and the city of the Event ("Event Location");',
        }
    ),
    "quote": "",
}
F1_HOTEL = {
    "text": "The grant covers hotel accommodations in the event location during the event.",
    "source": str(
        {
            "text": "Hotel accommodations in Event Location during the Event.",
            "source": "P4.U0",
            "quote": "Hotel accommodations in Event Location during the Event.",
        }
    ),
    "quote": "",
}

BENEFITS = (
    'Participants of the Program will receive the following benefits ("Program Benefits"): '
    "- A full conference pass to the Event you applied for; "
    '- Roundtrip flight between an airport near (within 50 miles of) the address you list in your application and the city of the Event ("Event Location"); and '
    "- Hotel accommodations in Event Location during the Event."
)


def _chunk(text, doc_id="official/2026/abw-terms"):
    return dict(
        id=f"{doc_id}#0",
        doc_id=doc_id,
        title="Terms",
        section="1.4 Program Benefits",
        text=text,
        source_url="https://example",
        event_year=2026,
        source_type="official",
    )


class _Doc:
    def document_text(self, doc_id):
        return TERMS_PAGE


def test_normalize_recovers_passage_id_and_quote_from_stringified_dict():
    cl = normalize_generated_claim(F1_PASS)
    assert cl["source"] == "P4.U0"
    assert "conference pass" in cl["quote"]
    assert cl["text"].startswith("The grant covers")


def test_source_passage_id_from_nested_dict_and_repr():
    assert source_passage_id("P4.U0") == "P4.U0"
    assert source_passage_id({"source": "P2.U3", "quote": ""}) == "P2.U3"
    assert source_passage_id(F1_HOTEL["source"]) == "P4.U0"
    assert source_passage_id("not a passage") is None
    assert source_passage_id("P1") == "P1.U0"
    assert source_passage_id("[P3.U2]") == "P3.U2"


def test_parse_llm_json_normalizes_nested_source_object():
    raw = (
        '{"answer":"x","claims":[{"text":"The grant covers a conference pass.",'
        '"source":{"text":"A full conference pass to the Event you applied for;",'
        '"source":"P1.U2","quote":"A full conference pass to the Event you applied for;"},'
        '"quote":""}]}'
    )
    data, how = parse_llm_json(raw)
    assert how == "json"
    assert data["claims"][0]["source"] == "P1.U2"
    assert "conference pass" in data["claims"][0]["quote"]


def test_parse_llm_json_repair_does_not_drop_complete_last_claim():
    """Live grant-02/05/17: repaired JSON must not drop a complete hotel claim."""
    trailing = (
        '{"answer":"The grant covers a full conference pass, roundtrip flight, and hotel accommodations.",'
        '"claims":['
        '{"text":"The grant covers a full conference pass.","source":"P1.U0",'
        '"quote":"A full conference pass to the Event you applied for"},'
        '{"text":"The grant covers roundtrip flight.","source":"P1.U0",'
        '"quote":"Roundtrip flight between an airport near the event"},'
        '{"text":"The grant covers hotel accommodations.","source":"P1.U0",'
        '"quote":"Hotel accommodations in Event Location during the Event"}'
        "]} trailing tokens from a truncated decode"
    )
    data, how = parse_llm_json(trailing)
    assert how in {"json", "repaired"}
    assert len(data["claims"]) == 3
    assert "hotel" in data["claims"][-1]["quote"].lower()

    truncated = (
        '{"answer":"The grant covers a full conference pass, roundtrip flight, and hotel accommodations.",'
        '"claims":['
        '{"text":"The grant covers a full conference pass.","source":"P1.U0",'
        '"quote":"A full conference pass to the Event you applied for"},'
        '{"text":"The grant covers roundtrip flight.","source":"P1.U0",'
        '"quote":"Roundtrip flight between an airport near the event"},'
        '{"text":"The grant covers hotel accommodations.","source":"P1.U0",'
        '"quote":"Hotel accommodations in Event Location during the Event"}'
        "]"
    )
    data, how = parse_llm_json(truncated)
    assert how == "repaired"
    assert len(data["claims"]) == 3
    assert "hotel" in data["claims"][-1]["quote"].lower()


def test_parse_llm_json_repair_path_recovers_python_repr_claims():
    raw = (
        "{'answer': 'The grant covers a conference pass.', 'claims': ["
        "{'text': 'The grant covers a conference pass.', "
        "'source': {'text': 'A full conference pass to the Event you applied for;', "
        "'source': 'P4.U0', 'quote': 'A full conference pass to the Event you applied for;'}, "
        "'quote': ''}]}"
    )
    data, how = parse_llm_json(raw)
    assert how == "repaired"
    assert data["claims"][0]["source"] == "P4.U0"
    assert "conference pass" in data["claims"][0]["quote"]


def test_collect_verified_recovers_f1_claims_when_p_index_is_out_of_range():
    """cover_06 / F1: P4.U0 with only the matching Terms chunk still verifies via quote."""
    active = [_chunk(BENEFITS)]
    claims, dropped = _collect_verified([F1_PASS, F1_FLIGHT, F1_HOTEL], active, _Doc())
    reasons = [d.get("reason") for d in dropped]
    assert not any(r == "unknown source passage" for r in reasons), dropped
    blob = " ".join(c["quote"] for c in claims)
    assert "conference pass" in blob
    assert "Roundtrip flight" in blob
    assert "Hotel accommodations" in blob
    assert len(claims) == 3


class _TitleSourceNova:
    name = "fake-title-source"

    def complete(self, system, user, **k):
        return json.dumps(
            {
                "answer": "Allow 30 to 45 minutes between venues.",
                "claims": [
                    {
                        "text": "Allow 30 to 45 minutes between venues.",
                        "source": "Know before you go",
                        "quote": "allow 30 to 45 minutes between venues",
                    }
                ],
            }
        )


def test_title_source_does_not_discard_the_whole_llm_attempt():
    """Live venue_04: every retry used a document title as source; keep the claims."""
    page = (
        "Sessions run across multiple Las Vegas properties, so check where yours are held "
        "and allow 30 to 45 minutes between venues."
    )
    gen = BedrockGenerator(client=_TitleSourceNova())
    out = gen.claims(
        "How much time should I leave between re:Invent venues?",
        {"event_year": 2026, "role": "grantee"},
        [_chunk(page, doc_id="official/2026/know-before-you-go")],
    )
    assert out, gen.attempts
    assert source_passage_id(out[0]["source"]) == "P1.U0"
    assert gen.summary
    assert "30" in gen.summary
    assert all(a.get("ok") for a in gen.attempts)


def test_bind_claim_source_recovers_url_and_doc_id():
    chunk = _chunk(BENEFITS)
    chunk["title"] = "All Builders Welcome Grant Terms and Conditions"
    chunk["source_url"] = (
        "https://aws.amazon.com/events/reinvent/experiences/all-builders-welcome/"
        "all-builders-welcome-terms/"
    )
    chunk["doc_id"] = "s3://abw-connect-kb-000000000000/kb/official/2026/abw-terms.md"
    url_cl = bind_claim_source(
        {"text": "The grant covers a conference pass.", "source": chunk["source_url"], "quote": ""},
        [chunk],
    )
    assert url_cl["source"] == "P1.U0"
    title_cl = bind_claim_source(
        {
            "text": "The grant covers a conference pass.",
            "source": chunk["title"],
            "quote": "",
        },
        [chunk],
    )
    assert title_cl["source"] == "P1.U0"
    doc_cl = bind_claim_source(
        {"text": "The grant covers a conference pass.", "source": chunk["doc_id"], "quote": ""},
        [chunk],
    )
    assert doc_cl["source"] == "P1.U0"
    assert assign_source_from_meta(chunk["source_url"], [chunk]) == "P1.U0"


def test_bind_claim_source_recovers_passage_id_from_document_title():
    """Live venue_04: Nova used the doc title as source; quote still in the passage."""
    chunk = _chunk(
        "Sessions run across multiple Las Vegas properties, so check where yours are held "
        "and allow 30 to 45 minutes between venues.",
        doc_id="official/2026/know-before-you-go",
    )
    chunk["title"] = "Know before you go"
    cl = bind_claim_source(
        {
            "text": "Allow 30 to 45 minutes between venues.",
            "source": "Know before you go",
            "quote": "allow 30 to 45 minutes between venues",
        },
        [chunk],
    )
    assert cl["source"] == "P1.U0"
    assert assign_source_from_quote("allow 30 to 45 minutes between venues", [chunk]) == "P1.U0"


def test_collect_verified_recovers_unknown_source_by_aligning_quote():
    raw = [
        {
            "text": "A full conference pass to the Event you applied for;",
            "source": "not-a-passage-id",
            "quote": "A full conference pass to the Event you applied for;",
        }
    ]
    claims, dropped = _collect_verified(raw, [_chunk(BENEFITS)], _Doc())
    assert claims, dropped
    assert not any(d.get("reason") == "unknown source passage" for d in dropped)
    assert "conference pass" in claims[0]["quote"]
