"""Live 68dd830 recovery: Bedrock-shaped retrieve vs mock-local gaps.

Mocks exercise the post-verifier path (salvage, sibling/missing-fact bind,
conflict date injection) under fat chunks and S3 doc ids. They do not
require a canned user-facing sentence.
"""
from __future__ import annotations

import json
import re

from app.services.ask import ask, _atomic_units
from app.services.generator import BedrockGenerator
from app.services.present import is_canned_conflict_lead
from app.services.retrieval import Passage
from tests.integration.test_pipeline import (
    PROFILE_GRANTEE_2026,
    _Dec4NoiseNova,
    _EmptyClaimsNova,
    _PassOnlyCoverageNova,
    _RegistrationSessionNova,
    _StudentWrongQuoteNova,
    _VenueEmptyNova,
)


def _as_passage(p: Passage, **over) -> Passage:
    d = p.as_dict()
    d.update(over)
    units = d.get("units") or [(0, len(d.get("text") or ""))]
    return Passage(
        id=d["id"],
        doc_id=d["doc_id"],
        title=d.get("title") or "",
        section=d.get("section") or "",
        text=d.get("text") or "",
        source_url=d.get("source_url") or "",
        event_year=int(d.get("event_year") or 0),
        source_type=d.get("source_type") or "official",
        retrieval_date=d.get("retrieval_date") or "",
        topic=d.get("topic"),
        score=float(d.get("score") or 0),
        units=units,
    )


class _S3DocRetriever:
    """Live Bedrock metadata uses s3://…/kb/official/…md, not local doc ids."""

    def __init__(self, inner):
        self.inner = inner
        self.name = "s3-wrap"

    def retrieve(self, query, **kw):
        out = []
        for p in self.inner.retrieve(query, **kw):
            s3 = f"s3://abw-connect-kb/kb/{p.doc_id}.md"
            out.append(_as_passage(p, doc_id=s3, id=f"{s3}#0"))
        return out

    def document_text(self, doc_id):
        return self.inner.document_text(doc_id)


class _FatChunkRetriever:
    """One oversized unit per official doc — live salvage skipped units >400."""

    def __init__(self, inner):
        self.inner = inner
        self.name = "fat-wrap"

    def retrieve(self, query, **kw):
        grouped: dict[str, list] = {}
        order = []
        for p in self.inner.retrieve(query, **kw):
            grouped.setdefault(p.doc_id, []).append(p)
            if p.doc_id not in order:
                order.append(p.doc_id)
        out = []
        for doc_id in order:
            parts = grouped[doc_id]
            blob = "\n".join(x.text for x in parts)
            first = parts[0]
            out.append(
                _as_passage(
                    first,
                    text=blob,
                    id=f"{doc_id}#fat",
                    units=[(0, len(blob))],
                )
            )
        return out

    def document_text(self, doc_id):
        return self.inner.document_text(doc_id)


class _SplitBenefitsRetriever:
    """Pass bullet in one terms slice, hotel in another (live grant_02 harvest miss)."""

    def __init__(self, inner):
        self.inner = inner
        self.name = "split-benefits"

    def retrieve(self, query, **kw):
        hits = list(self.inner.retrieve(query, **kw))
        extra = []
        for p in hits:
            if "abw-terms" not in (p.doc_id or ""):
                continue
            extra.append(
                _as_passage(
                    p,
                    id=p.doc_id + "#pass",
                    text="- A full conference pass to the Event you applied for;",
                    units=[(0, 56)],
                )
            )
            extra.append(
                _as_passage(
                    p,
                    id=p.doc_id + "#hotel",
                    text="- Hotel accommodations in Event Location during the Event.",
                    units=[(0, 58)],
                )
            )
            extra.append(
                _as_passage(
                    p,
                    id=p.doc_id + "#flight",
                    text="- Roundtrip flight between an airport near (within 50 miles of) the address you list in your application and the city of the Event;",
                    units=[(0, 130)],
                )
            )
            break
        return extra + hits

    def document_text(self, doc_id):
        return self.inner.document_text(doc_id)


class _NoAgendaFirstRetriever:
    """Live venue_02: getting-around / sessions first; agenda ranked out."""

    def __init__(self, inner):
        self.inner = inner
        self.name = "no-agenda-first"
        self.calls = 0

    def retrieve(self, query, **kw):
        self.calls += 1
        hits = list(self.inner.retrieve(query, **kw))
        if self.calls == 1:
            kept = [h for h in hits if "agenda" not in (h.doc_id or "")]
            return kept or hits[:1]
        return hits

    def document_text(self, doc_id):
        return self.inner.document_text(doc_id)


class _NoTermsFirstRetriever:
    """First retrieve is registration/session FAQs; second query can include Terms."""

    def __init__(self, inner):
        self.inner = inner
        self.name = "no-terms-first"
        self.calls = 0

    def retrieve(self, query, **kw):
        self.calls += 1
        hits = list(self.inner.retrieve(query, **kw))
        if self.calls == 1:
            kept = [
                h
                for h in hits
                if "abw-terms" not in (h.doc_id or "") and "abw-grant" not in (h.doc_id or "")
            ]
            return kept or hits[:1]
        return hits

    def document_text(self, doc_id):
        return self.inner.document_text(doc_id)


class _ListQuestionNova:
    name = "fake-nova-list-q"

    def complete(self, system, user, **k):
        if "Verified claims" in (user or ""):
            return json.dumps(
                {"answer": "The grant covers a conference pass, roundtrip flight, and hotel."}
            )
        return json.dumps(
            {
                "answer": "The ABW Grant covers a full conference pass.",
                "claims": [
                    {
                        "text": "The ABW Grant covers a full conference pass.",
                        "source": "P1.U0",
                        "quote": "A full conference pass to the Event you applied for",
                    }
                ],
            }
        )


class _MalformedThenEmptyNova:
    name = "fake-nova-malformed"

    def complete(self, system, user, **k):
        if "Verified claims" in (user or ""):
            m = re.search(r"quote: (.+)", user or "")
            return json.dumps({"answer": (m.group(1) if m else "See the official guidance.")[:400]})
        return "not json at all"


def test_atomic_units_split_lettered_eligibility():
    blob = (
        "You are eligible to apply if you meet the following criteria:\n"
        "A. you are at least 21 years of age;\n"
        "B. you are within the first 5 years of your technology career, or you are a university student preparing for a career in technology.\n"
        "D. you have not previously accepted a grant to the Event you are applying for;"
    )
    units = _atomic_units(blob)
    joined = " ".join(units)
    assert "21 years of age" in joined
    assert "university student" in joined
    assert all(len(u) <= 400 for u in units)


def test_atomic_units_keep_non_bullet_travel_buffer():
    blob = (
        "- Favoriting a catalog entry adds sessions to your list.\n"
        "Please note the venue where your session will take place and allow for additional travel time between venues.\n"
        "- You may not reserve seats in multiple sessions that occur at the same time."
    )
    units = _atomic_units(blob)
    joined = " ".join(units)
    assert "additional travel time" in joined


def test_s3_doc_id_still_verifies_terms_quotes(retriever, store):
    a = ask(
        "What does the All Builders Welcome Grant cover?",
        PROFILE_GRANTEE_2026,
        retriever=_S3DocRetriever(retriever),
        store=store,
        generator=BedrockGenerator(client=_EmptyClaimsNova()),
    )
    joined = ((a.get("summary") or "") + " " + " ".join(c.get("quote") or "" for c in a.get("claims") or [])).lower()
    assert a.get("refused") is False
    assert "pass" in joined
    assert "flight" in joined or "hotel" in joined


def test_fat_chunk_student_is_conditional_not_blanket(retriever, store):
    a = ask(
        "Can students apply for the All Builders Welcome Grant?",
        PROFILE_GRANTEE_2026,
        retriever=_FatChunkRetriever(retriever),
        store=store,
        generator=BedrockGenerator(client=_StudentWrongQuoteNova()),
    )
    joined = ((a.get("summary") or "") + " " + " ".join(
        (c.get("text") or "") + " " + (c.get("quote") or "") for c in a.get("claims") or []
    )).lower()
    assert a.get("refused") is False, (a.get("dropped"), a.get("message"))
    assert re.search(r"student", joined)
    assert "21" in joined
    assert "21" in (a.get("summary") or "")
    assert "do not specify" not in joined
    assert "cannot apply" not in joined


def test_fat_chunk_eligibility_includes_age_21(retriever, store):
    a = ask(
        "Who is eligible for the All Builders Welcome Grant?",
        PROFILE_GRANTEE_2026,
        retriever=_FatChunkRetriever(retriever),
        store=store,
        generator=BedrockGenerator(client=_EmptyClaimsNova()),
    )
    joined = ((a.get("summary") or "") + " " + " ".join(c.get("quote") or "" for c in a.get("claims") or [])).lower()
    assert a.get("refused") is False
    assert "21" in joined
    assert "21" in (a.get("summary") or "")
    assert re.search(r"student|career", joined)
    assert re.search(r"previously|employee", joined)
    assert "Limitation of Liability" not in joined


def test_split_benefit_chunks_recover_flight_and_hotel(retriever, store):
    a = ask(
        "What does the ABW Grant cover?",
        PROFILE_GRANTEE_2026,
        retriever=_SplitBenefitsRetriever(retriever),
        store=store,
        generator=BedrockGenerator(client=_PassOnlyCoverageNova()),
    )
    joined = ((a.get("summary") or "") + " " + " ".join(c.get("quote") or "" for c in a.get("claims") or [])).lower()
    assert a.get("refused") is False
    assert "pass" in joined
    assert "flight" in joined or "airfare" in joined
    assert "hotel" in joined


def test_registration_hits_top_up_to_program_benefits(retriever, store):
    wrapped = _NoTermsFirstRetriever(retriever)
    a = ask(
        "What does the grant cover for re:Invent?",
        PROFILE_GRANTEE_2026,
        retriever=wrapped,
        store=store,
        generator=BedrockGenerator(client=_RegistrationSessionNova()),
    )
    joined = ((a.get("summary") or "") + " " + " ".join(c.get("quote") or "" for c in a.get("claims") or [])).lower()
    assert wrapped.calls >= 2
    assert a.get("refused") is False, (a.get("dropped"), a.get("message"))
    assert "pass" in joined
    assert "flight" in joined or "airfare" in joined
    assert "hotel" in joined
    assert "re:play-only" not in joined
    assert "can i still stay" not in joined


def test_access_conflict_quotes_both_dates_from_fat_faq(retriever, store):
    a = ask(
        "When do accessibility accommodation requests need to be submitted?",
        PROFILE_GRANTEE_2026,
        retriever=_FatChunkRetriever(retriever),
        store=store,
        generator=BedrockGenerator(client=_Dec4NoiseNova()),
    )
    lead = a.get("summary") or ""
    blob = " ".join((c.get("quote") or "") for c in a.get("claims") or [])
    assert "13" in lead and "14" in lead
    assert re.search(r"Nov\.?\s*13", blob, re.I)
    assert re.search(r"November 14|14th", blob, re.I)
    assert not is_canned_conflict_lead(lead)
    cited = " ".join(
        f"{(c.get('citation') or {}).get('doc_id') or ''} {(c.get('citation') or {}).get('title') or ''}"
        for c in a.get("claims") or []
    ).lower()
    assert "faq" in cited
    assert "accessibility-services" in cited or "accessibility services" in cited


class _ByWhenAccessNova:
    name = "fake-nova-bywhen"

    def complete(self, system, user, **k):
        if "Verified claims" in (user or ""):
            return json.dumps(
                {
                    "answer": (
                        "Official pages list two different request-by dates: Nov. 13, 2026 and November 14th. "
                        "I cannot tell which deadline governs from these sources."
                    )
                }
            )
        m13 = re.search(r"\[(P\d+\.U\d+)\](.*Nov\.?\s*13[\s\S]{0,80})", user)
        return json.dumps(
            {
                "answer": "Request accessibility services by Nov. 13, 2026.",
                "claims": [
                    {
                        "text": "The deadline for all requests is Nov. 13, 2026.",
                        "source": (m13.group(1) if m13 else "P1.U0"),
                        "quote": "The deadline for all requests is Nov. 13, 2026.",
                    }
                ],
            }
        )


def test_variant_questions_do_not_hardcode_grant_sentence(retriever, store):
    novas = (_EmptyClaimsNova(), _ListQuestionNova(), _PassOnlyCoverageNova(), _MalformedThenEmptyNova())
    questions = (
        "What does the ABW Grant cover?",
        "List what the ABW Grant covers.",
        "Can you summarize ABW grant coverage?",
        "What travel and lodging does the ABW grant cover?",
    )
    canned = "The grant covers a full conference pass, roundtrip airfare, and hotel accommodation."
    for q, nova in zip(questions, novas):
        a = ask(
            q,
            PROFILE_GRANTEE_2026,
            retriever=retriever,
            store=store,
            generator=BedrockGenerator(client=nova),
        )
        summary = (a.get("summary") or "").strip()
        assert summary != canned, q
        if isinstance(nova, _MalformedThenEmptyNova) and a.get("refused"):
            # F19: an LLM that only echoes a quote cannot produce a verified answer; refuse
            # honestly instead of returning claims under an empty summary.
            assert a.get("refusal_reason") == "no_verified_claim", (q, a.get("refusal_reason"))
            continue
        assert a.get("refused") is False, (q, a.get("message"), a.get("dropped"))
        joined = (summary + " " + " ".join(c.get("quote") or "" for c in a.get("claims") or [])).lower()
        if "travel and lodging" in q.lower():
            assert "flight" in joined or "airfare" in joined
            assert "hotel" in joined
        else:
            assert "pass" in joined
            assert "flight" in joined or "airfare" in joined
            assert "hotel" in joined


def test_by_when_and_submitted_access_quote_both_dates(retriever, store):
    for q in (
        "By when must I request accessibility services for re:Invent?",
        "When do accessibility accommodation requests need to be submitted?",
    ):
        a = ask(
            q,
            PROFILE_GRANTEE_2026,
            retriever=_FatChunkRetriever(retriever),
            store=store,
            generator=BedrockGenerator(client=_ByWhenAccessNova()),
        )
        lead = a.get("summary") or ""
        blob = " ".join((c.get("quote") or "") for c in a.get("claims") or [])
        assert "13" in lead and "14" in lead, q
        assert re.search(r"Nov\.?\s*13", blob, re.I), q
        assert re.search(r"November 14|14th", blob, re.I), q
        assert not is_canned_conflict_lead(lead), q


def test_venue_paraphrase_salvage_does_not_invent_minutes(retriever, store):
    wrapped = _NoAgendaFirstRetriever(_FatChunkRetriever(retriever))
    a = ask(
        "When moving between conference venues, what buffer does the guidance recommend?",
        PROFILE_GRANTEE_2026,
        retriever=wrapped,
        store=store,
        generator=BedrockGenerator(client=_VenueEmptyNova()),
    )
    joined = ((a.get("summary") or "") + " " + " ".join(
        (c.get("quote") or "") for c in a.get("claims") or []
    )).lower()
    assert a.get("refused") is False
    assert a.get("outcome_key") != "unresolved_contradiction"
    assert "additional time" in joined or "additional travel" in joined or "travel between" in joined
    assert not re.search(r"\b\d+\s*minutes?\b", joined)
