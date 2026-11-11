"""End-to-end pipeline tests against the local KB (no AWS)."""
import json
import re

from app.services.ask import ask
from app.services.chat import chat
from app.services.generator import BedrockGenerator
from app.services.present import is_canned_conflict_lead
from app.services.store import MemoryStore
from tests.integration.live_replay import repair_answer

CONFLICT_PROSE = (
    "Official accessibility pages list two different request-by dates: Nov. 13, 2026 and November 14th. "
    "I cannot tell which deadline governs from these sources."
)
CANNED_CONFLICT_LEAD = (
    "The official sources disagree: one says Nov. 13, 2026 and the other says November 14th. "
    "Please confirm with AWS event support before relying on either date."
)


def test_citations_are_verified_against_source(retriever, store):
    a = ask(
        "What does the All Builders Welcome Grant cover?",
        {"event_year": 2026, "include_alumni": True, "role": "grantee"},
        mode="extractive",
        retriever=retriever,
        store=store,
    )
    assert a["claims"]
    for c in a["claims"]:
        assert c["citation"]["source_url"]
        assert c["quote"]
        page = retriever.document_text(c["citation"]["doc_id"])
        from app.services.verify import locate
        from app.services.textnorm import norm

        assert locate(norm(c["quote"]), page)


def test_new_chat_then_history_not_used_as_evidence(retriever, store):
    profile = {"event_year": 2026, "include_alumni": True, "role": "grantee"}
    a1 = chat("When and where is re:Invent 2026?", profile, mode="extractive", store=store, retriever=retriever)
    a2 = chat(
        "thanks!",
        profile,
        conversation_id=a1["conversation_id"],
        mode="extractive",
        store=store,
        retriever=retriever,
    )
    assert a2["kind"] == "greeting"
    hist = store.history(a1["conversation_id"])
    assert all(h["turn_type"] != "smalltalk" for h in hist)


def test_llm_timeout_refuses_instead_of_dumping_excerpts(retriever, store):
    class Boom:
        name = "boom"

        def complete(self, *a, **k):
            raise TimeoutError("simulated timeout")

    from app.services.generator import BedrockGenerator

    gen = BedrockGenerator(client=Boom())
    a = ask(
        "When and where is re:Invent 2026?",
        {"event_year": 2026, "include_alumni": True, "role": "grantee"},
        retriever=retriever,
        store=store,
        generator=gen,
    )
    assert a["refused"] is True
    assert a["generator"] != "extractive"
    assert a["generator_error"]
    summary = a.get("summary") or ""
    assert "Limitation of Liability" not in summary
    assert len(summary) < 400
    blob = " ".join(c.get("text") or "" for c in a.get("claims") or [])
    assert "These AWS All Builders Welcome Grant Program Terms" not in blob


PROFILE_GRANTEE_2026 = {"event_year": 2026, "include_alumni": True, "role": "grantee"}
BENEFITS_Q = "What does the All Builders Welcome Grant cover?"


class _QuoteStyleNova:
    """Replay the live AWS quote-style mismatch: single quotes around defined terms."""

    name = "fake-nova"
    swap_to = "Program Perks"

    def __init__(self, *, corrupt: bool = False):
        self.corrupt = corrupt

    def complete(self, system, user, **k):
        m = re.search(
            r"\[(P\d+\.U\d+)\] (Participants of the Program will receive the following benefits "
            r'\("Program Benefits"\):)',
            user,
        )
        assert m, "expected Program Benefits unit in retrieved passages"
        src, exact = m.group(1), m.group(2)
        quoted = exact.replace('"Program Benefits"', "'Program Benefits'")
        if self.corrupt:
            quoted = quoted.replace("Program Benefits", self.swap_to)
        return json.dumps(
            {
                "answer": "The grant covers a conference pass, roundtrip flight, and hotel.",
                "claims": [
                    {
                        "text": "The grant covers Program Benefits: a conference pass, roundtrip flight, and hotel.",
                        "source": src,
                        "quote": quoted,
                    }
                ],
            }
        )


def test_llm_single_quoted_program_benefits_claims_are_kept(retriever, store):
    a = ask(
        BENEFITS_Q,
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_QuoteStyleNova()),
    )
    assert a["kind"] == "answer"
    assert a["refused"] is False
    assert a["claims"], a.get("dropped")
    assert any("Program Benefits" in (c.get("quote") or "") for c in a["claims"])
    assert not any("substring" in (d.get("reason") or "") for d in a.get("dropped") or [])


def test_llm_altered_program_benefits_wording_is_still_dropped(retriever, store):
    a = ask(
        BENEFITS_Q,
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_QuoteStyleNova(corrupt=True)),
    )
    assert not any(_QuoteStyleNova.swap_to in (c.get("quote") or "") for c in a["claims"])
    dropped = a.get("dropped") or []
    assert dropped
    assert any("substring" in (d.get("reason") or "") for d in dropped)


class _OneSidedDeadlineNova:
    """Replay live AWS: Nova names Nov. 13 as *the* deadline while both dates are in passages."""

    name = "fake-nova-deadline"

    def complete(self, system, user, **k):
        if "Verified claims" in (user or "") or "already source-checked" in (user or ""):
            return json.dumps({"answer": CONFLICT_PROSE})
        m13 = re.search(
            r"\[(P\d+\.U\d+)\](.*Nov\.?\s*13[\s\S]{0,80})",
            user,
        )
        m14 = re.search(
            r"\[(P\d+\.U\d+)\](.*November 14th[\s\S]{0,80})",
            user,
        )
        assert m13 and m14, "expected both Nov. 13 and November 14th units in passages"
        q13 = "The deadline for all requests is Nov. 13, 2026."
        q14 = "all requests must be received by November 14th."
        return json.dumps(
            {
                "answer": "The deadline for all requests is Nov. 13, 2026",
                "claims": [
                    {
                        "text": "The deadline for all requests is Nov. 13, 2026.",
                        "source": m13.group(1),
                        "quote": q13,
                    },
                    {
                        "text": "All requests must be received by November 14th.",
                        "source": m14.group(1),
                        "quote": q14,
                    },
                ],
            }
        )


def test_llm_onesided_deadline_summary_is_replaced_with_both_dates(retriever, store):
    a = ask(
        "When is the deadline to request accessibility accommodations?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_OneSidedDeadlineNova()),
    )
    assert a["outcome_key"] == "unresolved_contradiction"
    lead = a.get("summary") or ""
    assert "13" in lead and "14" in lead
    assert not lead.lower().lstrip().startswith("the deadline for all requests is")
    assert not is_canned_conflict_lead(lead)
    assert lead.strip() != CANNED_CONFLICT_LEAD
    assert any(n.get("kind") == "unresolved_contradiction" for n in a.get("notes") or [])
    note_blob = " ".join(n.get("text") or "" for n in a.get("notes") or [])
    assert "awsreinvent-support" not in note_blob.lower()
    blob = " ".join(c["text"] + " " + c["quote"] for c in a["claims"])
    assert "13" in blob and "14" in blob
    assert "December 4" not in (a.get("summary") or "")


class _ConflictProseNova:
    name = "fake-nova-conflict-prose"

    def complete(self, system, user, **k):
        if "Verified claims" in (user or "") or "already source-checked" in (user or ""):
            return json.dumps({"answer": CONFLICT_PROSE})
        m13 = re.search(r"\[(P\d+\.U\d+)\](.*Nov\.?\s*13[\s\S]{0,80})", user)
        m14 = re.search(r"\[(P\d+\.U\d+)\](.*November 14th[\s\S]{0,80})", user)
        assert m13 and m14
        return json.dumps(
            {
                "answer": CONFLICT_PROSE,
                "claims": [
                    {
                        "text": "The deadline for all requests is Nov. 13, 2026.",
                        "source": m13.group(1),
                        "quote": "The deadline for all requests is Nov. 13, 2026.",
                    },
                    {
                        "text": "All requests must be received by November 14th.",
                        "source": m14.group(1),
                        "quote": "all requests must be received by November 14th.",
                    },
                ],
            }
        )


def test_llm_conflict_prose_is_kept_and_is_not_a_template(retriever, store):
    a = ask(
        "When is the deadline to request accessibility accommodations?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_ConflictProseNova()),
    )
    lead = a.get("summary") or ""
    assert a["outcome_key"] == "unresolved_contradiction"
    assert lead == CONFLICT_PROSE
    assert not is_canned_conflict_lead(lead)
    assert "13" in lead and "14" in lead
    blob = " ".join(c["text"] + " " + c["quote"] for c in a["claims"])
    assert "13" in blob and "14" in blob


class _EmptyClaimsNova:
    name = "fake-nova-empty"

    def complete(self, system, user, **k):
        # First turns emit no claims (live grant_11/16). The salvage rewrite still
        # asks for a short answer from verified units.
        if "Verified claims" in (user or "") or "already source-checked" in (user or ""):
            if "21" in (user or "") and re.search(r"student|eligib", user or "", re.I):
                bits = [
                    "Eligibility includes being at least 21 years of age",
                    "university students preparing for a career in technology are named among the criteria",
                ]
                # Bounded rewrite prompts list omitted facts; include them when present.
                if re.search(r"employee|affiliates", user or "", re.I):
                    bits.append("applicants may not be an employee of AWS or its affiliates")
                if re.search(r"previously|accepted a grant", user or "", re.I):
                    bits.append("you must not have previously accepted a grant to the same Event")
                return json.dumps({"answer": "; ".join(bits) + "."})
            return json.dumps(
                {"answer": "The grant covers a conference pass, roundtrip flight, and hotel accommodations."}
            )
        return json.dumps({"answer": "", "claims": []})


class _PrefixQuoteNova:
    """Reformatting + source-prefix; quote is not character-identical to the unit."""

    name = "fake-nova-prefix"

    def complete(self, system, user, **k):
        m = re.search(
            r"\[(P\d+\.U\d+)\] (Participants of the Program will receive the following benefits "
            r'\("Program Benefits"\):)',
            user,
        )
        assert m, "expected Program Benefits unit"
        return json.dumps(
            {
                "answer": "The grant covers a conference pass, roundtrip flight, and hotel.",
                "claims": [
                    {
                        "text": "The grant covers Program Benefits: a conference pass, roundtrip flight, and hotel.",
                        "source": m.group(1),
                        "quote": f"[P1.U3] Section 1.4 Participants of the Program will receive the following benefits (Program Benefits):",
                    }
                ],
            }
        )


class _Dec4NoiseNova:
    """Live-style: Nov. 13 claim plus Agenda December 4; FAQ November 14th omitted."""

    name = "fake-nova-dec4"

    def complete(self, system, user, **k):
        if "Verified claims" in (user or "") or "already source-checked" in (user or ""):
            return json.dumps({"answer": CONFLICT_PROSE})
        m13 = re.search(r"\[(P\d+\.U\d+)\](.*Nov\.?\s*13[\s\S]{0,80})", user)
        m_dec = re.search(r"\[(P\d+\.U\d+)\](.*December 4[\s\S]{0,40})", user)
        assert m13, "expected Nov. 13 unit"
        claims = [
            {
                "text": "The deadline for all requests is Nov. 13, 2026.",
                "source": m13.group(1),
                "quote": "The deadline for all requests is Nov. 13, 2026.",
            }
        ]
        if m_dec:
            claims.append(
                {
                    "text": "The event runs through Friday, December 4.",
                    "source": m_dec.group(1),
                    "quote": "Friday, December 4",
                }
            )
        return json.dumps({"answer": "The deadline for all requests is Nov. 13, 2026", "claims": claims})


def test_llm_empty_claims_refuses_instead_of_dumping_terms(retriever, store):
    a = ask(
        BENEFITS_Q,
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_EmptyClaimsNova()),
    )
    summary = a.get("summary") or a.get("message") or ""
    blob = " ".join((c.get("text") or "") + " " + (c.get("quote") or "") for c in a.get("claims") or [])
    assert "Limitation of Liability" not in summary
    assert "Section 1.7" not in summary
    assert "These AWS All Builders Welcome Grant Program Terms" not in summary
    assert "Limitation of Liability" not in blob
    canned = "The grant covers a full conference pass, roundtrip airfare, and hotel accommodation."
    assert (a.get("summary") or "").strip() != canned
    for c in a.get("claims") or []:
        assert len(c.get("quote") or "") < 600
        assert "####" not in (c.get("quote") or "")
    # Live 8d41 grant_11/16: empty LLM claims must not hard-refuse when short
    # official units exist. Timeout still refuses (see timeout test).
    assert a.get("refused") is False
    assert a.get("claims")
    assert a.get("summary")
    joined = ((a.get("summary") or "") + " " + blob).lower()
    assert "pass" in joined
    assert "flight" in joined or "airfare" in joined
    assert "hotel" in joined
    assert "Limitation of Liability" not in (a.get("summary") or "")


def test_llm_source_prefix_and_stripped_quotes_are_kept(retriever, store):
    a = ask(
        BENEFITS_Q,
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_PrefixQuoteNova()),
    )
    assert a["claims"]
    assert any("Program Benefits" in (c.get("quote") or "") for c in a["claims"])


def test_conflict_lead_uses_faq_nov_14_not_agenda_december_4(retriever, store):
    a = ask(
        "When is the deadline to request accessibility accommodations for re:Invent 2026?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_Dec4NoiseNova()),
    )
    assert a["outcome_key"] == "unresolved_contradiction"
    lead = a.get("summary") or ""
    assert "13" in lead and "14" in lead
    assert "December" not in lead
    assert not is_canned_conflict_lead(lead)
    blob = " ".join(c["text"] + " " + c["quote"] for c in a["claims"])
    assert "14" in blob


class _NoLocalDoc:
    """Bedrock-shaped retriever: chunk text only, no full document body."""

    name = "bedrock-sim"

    def __init__(self, inner):
        self.inner = inner

    def retrieve(self, *a, **k):
        return self.inner.retrieve(*a, **k)

    def document_text(self, doc_id):
        return ""


class _RepairedNestedSourceNova:
    """Live F1 / cover_06: json_repair nested the claim into source; quote empty."""

    name = "fake-nova-repaired"

    def complete(self, system, user, **k):
        m = re.search(
            r"\[(P\d+\.U\d+)\] (Participants of the Program will receive the following benefits "
            r'\("Program Benefits"\):)',
            user,
        )
        assert m, "expected Program Benefits unit in retrieved passages"
        sid = m.group(1)

        def wrap(text, quote):
            return {
                "text": text,
                "source": str({"text": quote, "source": sid, "quote": quote}),
                "quote": "",
            }

        return json.dumps(
            {
                "answer": (
                    "The All Builders Welcome Grant covers a full conference pass, "
                    "roundtrip flight, and hotel accommodations."
                ),
                "claims": [
                    wrap(
                        "The grant covers a full conference pass to the event you applied for.",
                        'Participants of the Program will receive the following benefits ("Program Benefits"): - A full conference pass to the Event you applied for;',
                    ),
                    wrap(
                        "The grant covers roundtrip flight between an airport near (within 50 miles of) the address you list in your application and the city of the event.",
                        'Roundtrip flight between an airport near (within 50 miles of) the address you list in your application and the city of the Event ("Event Location");',
                    ),
                    wrap(
                        "The grant covers hotel accommodations in the event location during the event.",
                        "Hotel accommodations in Event Location during the Event.",
                    ),
                ],
            }
        )


def test_repaired_nested_source_claims_are_verified(retriever, store):
    a = ask(
        BENEFITS_Q,
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_RepairedNestedSourceNova()),
    )
    assert a["refused"] is False, a.get("dropped")
    assert a["claims"]
    assert not any((d.get("reason") or "") == "unknown source passage" for d in a.get("dropped") or [])
    blob = " ".join(c["text"] + " " + c["quote"] for c in a["claims"])
    assert re.search(r"conference pass", blob, re.I)
    assert re.search(r"flight", blob, re.I)
    assert re.search(r"hotel", blob, re.I)
    summary = a.get("summary") or ""
    assert re.search(r"conference pass", summary, re.I)
    assert "These AWS All Builders Welcome Grant Program Terms" not in summary


def test_extractive_grant_cover_does_not_use_terms_dump_as_summary(retriever, store):
    """cover_06: missing LLM answer must not become a Terms dump or a canned coverage sentence."""
    a = ask(
        "Please tell me: What does the All Builders Welcome Grant cover?",
        PROFILE_GRANTEE_2026,
        mode="extractive",
        retriever=retriever,
        store=store,
    )
    summary = a.get("summary") or ""
    assert "These AWS All Builders Welcome Grant Program Terms" not in summary
    assert "Limitation of Liability" not in summary
    assert "Section 1.7" not in summary
    assert len(summary) < 700
    canned = "The grant covers a full conference pass, roundtrip airfare, and hotel accommodation."
    assert summary.strip() != canned


def test_grant_coverage_verifies_when_local_document_text_is_empty(retriever, store):
    a = ask(
        BENEFITS_Q,
        PROFILE_GRANTEE_2026,
        retriever=_NoLocalDoc(retriever),
        store=store,
        generator=BedrockGenerator(client=_QuoteStyleNova()),
    )
    assert a["refused"] is False
    assert a["claims"]
    assert any("Program Benefits" in (c.get("quote") or "") for c in a["claims"])
    summary = a.get("summary") or ""
    assert summary
    assert len(summary) < 500
    assert "Limitation of Liability" not in summary


class _DumpAnswerNova:
    """Live cover_06 shape: model pastes retrieved Terms into answer."""

    name = "fake-nova-dump"

    def complete(self, system, user, **k):
        if "Verified claims" in user:
            return json.dumps(
                {
                    "answer": "Program Benefits include a conference pass, a roundtrip flight, and hotel accommodations."
                }
            )
        m = re.search(
            r"\[(P\d+\.U\d+)\] (Participants of the Program will receive the following benefits "
            r'\("Program Benefits"\):)',
            user,
        )
        assert m, "expected Program Benefits unit"
        return json.dumps(
            {
                "answer": user,
                "claims": [
                    {
                        "text": "The grant covers Program Benefits: a conference pass, roundtrip flight, and hotel.",
                        "source": m.group(1),
                        "quote": m.group(2),
                    }
                ],
            }
        )


def test_llm_passage_dump_is_not_used_as_primary_answer(retriever, store):
    a = ask(
        BENEFITS_Q,
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_DumpAnswerNova()),
    )
    summary = a.get("summary") or ""
    assert "Limitation of Liability" not in summary
    assert "Section 1.7" not in summary
    assert "you are not an employee" not in summary.lower()
    assert len(summary) < 650
    canned = "The grant covers a full conference pass, roundtrip airfare, and hotel accommodation."
    assert summary.strip() != canned


VENUE_Q = "How much time should I leave between re:Invent venues?"


class _VenueTimeNova:
    """LLM writes the venue-transfer answer from retrieved guidance, not event dates."""

    name = "fake-nova-venue"

    def complete(self, system, user, **k):
        m45 = re.search(
            r"\[(P\d+\.U\d+)\]([^\[]{0,120}30 to 45 minutes between venues[^\[]{0,40})",
            user,
            re.I,
        )
        extra = re.search(
            r"\[(P\d+\.U\d+)\]([^\[]{0,80}additional time for travel between properties[^\[]{0,20})",
            user,
            re.I,
        )
        claims = []
        if m45:
            claims.append(
                {
                    "text": "Allow 30 to 45 minutes between venues.",
                    "source": m45.group(1),
                    "quote": "allow 30 to 45 minutes between venues",
                }
            )
        if extra:
            claims.append(
                {
                    "text": "Allow additional time for travel between properties.",
                    "source": extra.group(1),
                    "quote": "Allow additional time for travel between properties.",
                }
            )
        assert claims, "expected venue-travel units in retrieved passages\n" + user[:800]
        return json.dumps(
            {
                "answer": "Allow 30 to 45 minutes between venues, and additional time for travel between properties.",
                "claims": claims,
            }
        )


def test_venue_time_llm_does_not_surface_event_date_conflict(retriever, store):
    a = ask(
        VENUE_Q,
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_VenueTimeNova()),
    )
    assert a["refused"] is False, a.get("dropped")
    assert a.get("outcome_key") != "unresolved_contradiction"
    lead = a.get("summary") or ""
    assert "disagree" not in lead.lower()
    assert not re.search(r"December\s*4|Dec\.?\s*4", lead)
    assert not re.search(r"Nov(?:ember)?\.?\s*30", lead)
    assert re.search(r"30", lead) and re.search(r"45|additional time", lead, re.I)
    assert len(lead) < 400
    assert not any(n.get("kind") == "unresolved_contradiction" for n in a.get("notes") or [])


def test_venue_time_extractive_is_not_a_date_conflict(retriever, store):
    a = ask(
        VENUE_Q,
        PROFILE_GRANTEE_2026,
        mode="extractive",
        retriever=retriever,
        store=store,
    )
    assert a.get("outcome_key") != "unresolved_contradiction"
    summary = a.get("summary") or ""
    assert "disagree" not in summary.lower()
    assert not re.search(r"December\s*4|Dec\.?\s*4", summary)
    blob = " ".join(c.get("text") or "" for c in a.get("claims") or [])
    assert re.search(r"30|45|additional time", blob, re.I)


def test_venue_time_question_variants_are_not_date_conflicts(retriever, store):
    for q in (
        "how long between properties?",
        "travel time between venues",
        "How much time should I leave between re:Invent venues?",
    ):
        a = ask(q, PROFILE_GRANTEE_2026, mode="extractive", retriever=retriever, store=store)
        assert a.get("outcome_key") != "unresolved_contradiction", q
        assert not any(n.get("kind") == "unresolved_contradiction" for n in a.get("notes") or []), q


class _VenueBadSourceEveryRetry:
    """Live venue_04: document title as source on every retry, quote still in the passage."""

    name = "fake-nova-venue-bad-source"
    calls = 0

    def complete(self, system, user, **k):
        self.calls += 1
        if "Verified claims" in user:
            return json.dumps({"answer": "Allow 30 to 45 minutes between venues."})
        m45 = re.search(r"30 to 45 minutes between venues", user, re.I)
        extra = re.search(r"additional time for travel between properties", user, re.I)
        assert m45 or extra, user[:800]
        quote = "allow 30 to 45 minutes between venues" if m45 else "Allow additional time for travel between properties."
        return json.dumps(
            {
                "answer": "Allow 30 to 45 minutes between venues.",
                "claims": [
                    {
                        "text": "Allow 30 to 45 minutes between venues.",
                        "source": "Know before you go",
                        "quote": quote,
                    }
                ],
            }
        )


def test_venue_bad_source_every_retry_still_answers(retriever, store):
    client = _VenueBadSourceEveryRetry()
    a = ask(
        VENUE_Q,
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=client),
    )
    assert a["refused"] is False, (a.get("dropped"), a.get("generator_error"), a.get("llm_attempts"))
    lead = a.get("summary") or ""
    assert re.search(r"30|45|additional time", lead, re.I)
    assert "disagree" not in lead.lower()
    assert client.calls >= 1
    canned = "The grant covers a full conference pass, roundtrip airfare, and hotel accommodation."
    assert lead.strip() != canned


class _LiveQuoteMismatchNova:
    """Passage-only id P1 plus curly quotes and a source-label prefix — live quote mismatch shape."""

    name = "fake-nova-quote-mismatch"

    def complete(self, system, user, **k):
        m = re.search(
            r"\[P(\d+)\.U\d+\] (Participants of the Program will receive the following benefits "
            r'\("Program Benefits"\):)',
            user,
        )
        assert m, "expected Program Benefits unit"
        pn = m.group(1)
        quote = (
            f"[P{pn}] Participants of the Program will receive the following benefits "
            "(\u201cProgram Benefits\u201d):"
        )
        return json.dumps(
            {
                "answer": "The grant covers Program Benefits including a conference pass, flight, and hotel.",
                "claims": [
                    {
                        "text": "The grant covers Program Benefits including a conference pass, flight, and hotel.",
                        "source": f"P{pn}",
                        "quote": quote,
                    }
                ],
            }
        )


def test_live_quote_mismatch_p_only_and_curly_quotes_still_verifies(retriever, store):
    a = ask(
        BENEFITS_Q,
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_LiveQuoteMismatchNova()),
    )
    assert a["refused"] is False, a.get("dropped")
    assert a["claims"]
    summary = a.get("summary") or ""
    assert summary
    assert re.search(r"pass|flight|hotel|benefits", summary, re.I)
    assert "Limitation of Liability" not in summary


class _EmptyAnswerWithClaimsNova:
    """Live empty_summary: verified claims, blank answer on every main attempt."""

    name = "fake-nova-empty-answer"

    def complete(self, system, user, **k):
        if "Verified claims" in user:
            return json.dumps(
                {"answer": "The program includes a conference pass, roundtrip flight, and hotel accommodations."}
            )
        m = re.search(
            r"\[(P\d+\.U\d+)\] (Participants of the Program will receive the following benefits "
            r'\("Program Benefits"\):)',
            user,
        )
        assert m, "expected Program Benefits unit"
        return json.dumps(
            {
                "answer": "",
                "claims": [
                    {
                        "text": "The grant covers Program Benefits: a conference pass, roundtrip flight, and hotel.",
                        "source": m.group(1),
                        "quote": m.group(2),
                    }
                ],
            }
        )


def test_empty_llm_answer_recovers_short_summary_from_verified_quotes(retriever, store):
    a = ask(
        BENEFITS_Q,
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_EmptyAnswerWithClaimsNova()),
    )
    assert a["refused"] is False, a.get("dropped")
    summary = a.get("summary") or ""
    assert summary
    assert re.search(r"conference pass|flight|hotel", summary, re.I)
    assert len(summary) < 400
    canned = "The grant covers a full conference pass, roundtrip airfare, and hotel accommodation."
    assert summary.strip() != canned


def test_natural_grant_wording_is_not_no_support(retriever, store):
    for q in (
        "What's included in the ABW grant?",
        "Does the All Builders Welcome Grant pay for airfare and lodging?",
        "Will ABW cover my flight and hotel?",
        "Please tell me: What does the All Builders Welcome Grant cover?",
    ):
        a = ask(q, PROFILE_GRANTEE_2026, mode="extractive", retriever=retriever, store=store)
        assert a.get("refusal_reason") != "no_support", (q, a.get("refusal"), a.get("message"))
        assert a.get("refused") is False, (q, a.get("kind"), a.get("refusal"))
        blob = " ".join(c.get("text") or "" for c in a.get("claims") or [])
        assert re.search(r"pass|flight|hotel|benefit", blob, re.I), q


LIVE_GRANT03_PASS_QUOTE = (
    'Participants of the Program will receive the following benefits ("Program Benefits"): '
    "- A full conference pass to the Event you applied for"
)
LIVE_GRANT03_SPLICED_FLIGHT = (
    'Participants of the Program will receive the following benefits ("Program Benefits"): '
    "- Roundtrip flight between an airport near (within 50 miles of) the address you list "
    'in your application and the city of the Event ("Event Location");'
)


class _LiveGrant03PartialNova:
    """Live ad4808 grant_03: spliced flight quote; original LLM answer had all three benefits."""

    name = "fake-nova-live-grant03"

    def complete(self, system, user, **k):
        if "Verified claims" in user:
            return json.dumps(
                {
                    "answer": "The ABW Grant covers a full conference pass, roundtrip flight, and hotel accommodations."
                }
            )
        return json.dumps(
            {
                "answer": "The ABW Grant covers a full conference pass, roundtrip flight, and hotel accommodations.",
                "claims": [
                    {
                        "text": "The ABW Grant covers a full conference pass.",
                        "source": "Know before you go",
                        "quote": LIVE_GRANT03_PASS_QUOTE,
                    },
                    {
                        "text": "The ABW Grant covers roundtrip flight.",
                        "source": "https://aws.amazon.com/events/reinvent/experiences/all-builders-welcome/all-builders-welcome-terms/",
                        "quote": LIVE_GRANT03_SPLICED_FLIGHT,
                    },
                ],
            }
        )


def test_live_grant03_partial_quotes_keep_complete_llm_answer(retriever, store):
    a = ask(
        "What does the ABW Grant cover?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_LiveGrant03PartialNova()),
    )
    assert a["refused"] is False, (a.get("dropped"), a.get("generator_error"))
    summary = a.get("summary") or ""
    assert re.search(r"conference pass", summary, re.I)
    assert re.search(r"flight|roundtrip", summary, re.I)
    assert re.search(r"hotel", summary, re.I)
    assert "Limitation of Liability" not in summary
    canned = "The grant covers a full conference pass, roundtrip airfare, and hotel accommodation."
    assert summary.strip() != canned


class _FirstClaimOnlyRewriteNova:
    """Empty main answer; first rewrite uses only the first verified claim."""

    name = "fake-nova-first-claim-only"

    def __init__(self):
        self.rewrites = 0

    def complete(self, system, user, **k):
        if "Verified claims" in user:
            self.rewrites += 1
            if self.rewrites == 1:
                return json.dumps({"answer": "The grant covers a full conference pass."})
            assert "conference pass" in user.lower() or "claim:" in user.lower()
            return json.dumps(
                {
                    "answer": "The grant covers a full conference pass, a roundtrip flight, and hotel accommodations."
                }
            )
        m_pass = re.search(r"\[(P\d+\.U\d+)\][^\[]{0,40}full conference pass", user, re.I)
        m_flight = re.search(r"\[(P\d+\.U\d+)\][^\[]{0,40}Roundtrip flight", user, re.I)
        m_hotel = re.search(r"\[(P\d+\.U\d+)\][^\[]{0,40}Hotel accommodations", user, re.I)
        assert m_pass and m_flight and m_hotel, user[:1200]
        return json.dumps(
            {
                "answer": "",
                "claims": [
                    {
                        "text": "The grant covers a full conference pass.",
                        "source": m_pass.group(1),
                        "quote": "A full conference pass to the Event you applied for;",
                    },
                    {
                        "text": "The grant covers a roundtrip flight.",
                        "source": m_flight.group(1),
                        "quote": "Roundtrip flight between an airport near (within 50 miles of) the address you list in your application and the city of the Event",
                    },
                    {
                        "text": "The grant covers hotel accommodations.",
                        "source": m_hotel.group(1),
                        "quote": "Hotel accommodations in Event Location during the Event.",
                    },
                ],
            }
        )


def test_rewrite_recovers_when_first_turn_keeps_only_first_claim(retriever, store):
    client = _FirstClaimOnlyRewriteNova()
    a = ask(
        BENEFITS_Q,
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=client),
    )
    assert a["refused"] is False, a.get("dropped")
    summary = a.get("summary") or ""
    assert re.search(r"conference pass", summary, re.I)
    assert re.search(r"flight|roundtrip", summary, re.I)
    assert re.search(r"hotel", summary, re.I)
    assert client.rewrites >= 2
    assert "Limitation of Liability" not in summary


class _FlightOnlyNova:
    name = "fake-nova-flight-only"

    def complete(self, system, user, **k):
        m_flight = re.search(r"\[(P\d+\.U\d+)\][^\[]{0,40}Roundtrip flight", user, re.I)
        m_hotel = re.search(r"\[(P\d+\.U\d+)\][^\[]{0,40}Hotel accommodations", user, re.I)
        assert m_flight, user[:800]
        claims = [
            {
                "text": "The grant covers a roundtrip flight.",
                "source": m_flight.group(1),
                "quote": "Roundtrip flight between an airport near (within 50 miles of) the address you list in your application and the city of the Event",
            }
        ]
        if m_hotel:
            claims.append(
                {
                    "text": "The grant covers hotel accommodations.",
                    "source": m_hotel.group(1),
                    "quote": "Hotel accommodations in Event Location during the Event.",
                }
            )
        return json.dumps(
            {
                "answer": "Yes, the grant covers a roundtrip flight to the event location.",
                "claims": claims,
            }
        )


def test_flight_only_intent_does_not_force_hotel_into_answer(retriever, store):
    a = ask(
        "Does the All Builders Welcome Grant pay for airfare?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_FlightOnlyNova()),
    )
    assert a["refused"] is False, a.get("dropped")
    summary = a.get("summary") or ""
    assert re.search(r"flight|roundtrip|airfare", summary, re.I)
    assert "Limitation of Liability" not in summary
    assert "disagree" not in summary.lower()


class _UnsupportedFactRewriteNova:
    name = "fake-nova-99-miles"

    def complete(self, system, user, **k):
        if "Verified claims" in user:
            return json.dumps({"answer": "The grant covers a roundtrip flight within 99 miles of your address."})
        m = re.search(r"\[(P\d+\.U\d+)\][^\[]{0,40}Roundtrip flight", user, re.I)
        assert m, user[:800]
        return json.dumps(
            {
                "answer": "",
                "claims": [
                    {
                        "text": "The grant covers a roundtrip flight within 50 miles of your address.",
                        "source": m.group(1),
                        "quote": "Roundtrip flight between an airport near (within 50 miles of) the address you list in your application and the city of the Event",
                    }
                ],
            }
        )


def test_rewrite_does_not_accept_unsupported_invented_facts(retriever, store):
    a = ask(
        "Does the All Builders Welcome Grant pay for airfare?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_UnsupportedFactRewriteNova()),
    )
    summary = a.get("summary") or ""
    assert "99" not in summary
    assert "Limitation of Liability" not in summary
    dropped = " ".join((d.get("reason") or "") + " " + (d.get("text") or "") for d in a.get("dropped") or [])
    assert "99" in dropped


def test_typed_grant_questions_are_supported_without_blank_or_dump(retriever, store):
    questions = (
        "What does the ABW Grant cover?",
        "What benefits does the ABW grant include?",
        "What does the ABW grant package include?",
        "What's included in the ABW grant?",
        "Does the All Builders Welcome Grant pay for airfare and lodging?",
        "Will ABW cover my flight and hotel?",
        "Please tell me: What does the All Builders Welcome Grant cover?",
        "What does the All Builders Welcome Grant cover?",
    )
    for q in questions:
        a = ask(q, PROFILE_GRANTEE_2026, mode="extractive", retriever=retriever, store=store)
        assert a.get("refused") is False, (q, a.get("refusal"), a.get("kind"))
        assert a.get("refusal_reason") != "no_support", q
        blob = " ".join(c.get("text") or "" for c in a.get("claims") or [])
        assert blob, q
        summary = a.get("summary") or ""
        assert "Limitation of Liability" not in summary
        assert "Section 1.7" not in summary


def test_live_ad4808_fixture_quotes_now_verify():
    import json
    from pathlib import Path

    from app.services.verify import verify

    root = Path(__file__).resolve().parents[2]
    terms = (root / "kb/official/2026/abw-terms.md").read_text()
    fixture = json.loads((root / "tests/fixtures/live_ad4808/grant_03_752d.json").read_text())
    dropped = fixture["response"]["dropped"]
    flight = next(d for d in dropped if "roundtrip flight" in (d.get("text") or "").lower())
    ok, why, span = verify(flight["text"], flight["quote"], terms)
    assert ok, why
    assert "Roundtrip flight" in terms[span[0] : span[1]]


class _EventDatesNova:
    name = "fake-nova-dates"

    def complete(self, system, user, **k):
        m = re.search(
            r"\[(P\d+\.U\d+)\][^\[]{0,80}(Nov\.?\s*30[^\n\[]{0,60}Dec\.?\s*4[^\n\[]{0,40})",
            user,
            re.I,
        )
        assert m, user[:800]
        quote = re.sub(r"\s+", " ", m.group(2)).strip(" .;:")
        return json.dumps(
            {
                "answer": "re:Invent 2026 is from Nov. 30 to Dec. 4.",
                "claims": [
                    {
                        "text": "re:Invent 2026 is from Nov. 30 to Dec. 4.",
                        "source": m.group(1),
                        "quote": quote,
                    }
                ],
            }
        )


def test_when_is_reinvent_does_not_refuse_on_year_token(retriever, store):
    a = ask(
        "When is re:Invent 2026?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_EventDatesNova()),
    )
    assert a.get("refused") is False, (a.get("dropped"), a.get("refusal"))
    summary = a.get("summary") or ""
    assert re.search(r"Nov\.?\s*30", summary, re.I)
    assert re.search(r"Dec\.?\s*4", summary, re.I)
    assert a.get("outcome_key") != "unresolved_contradiction"


def test_venue_paraphrases_are_not_accessibility_conflicts(retriever, store):
    for q in (
        "When moving between conference venues, what buffer does the guidance recommend?",
        "What do the re:Invent travel instructions say about getting from one venue to another?",
        "How should I plan transportation between re:Invent properties?",
    ):
        a = ask(q, PROFILE_GRANTEE_2026, mode="extractive", retriever=retriever, store=store)
        assert a.get("outcome_key") != "unresolved_contradiction", q
        lead = a.get("summary") or ""
        assert "November 14" not in lead
        assert not re.search(r"Nov\.?\s*13", lead)
        blob = " ".join((c.get("text") or "") + " " + (c.get("quote") or "") for c in a.get("claims") or [])
        assert "####" not in blob
        for c in a.get("claims") or []:
            assert len(c.get("quote") or "") < 600
            assert "####" not in (c.get("quote") or "")


def test_accessibility_deadline_still_leads_with_both_dates(retriever, store):
    a = ask(
        "When is the deadline to request accessibility accommodations?",
        PROFILE_GRANTEE_2026,
        mode="extractive",
        retriever=retriever,
        store=store,
    )
    assert a.get("outcome_key") == "unresolved_contradiction"
    lead = a.get("summary") or ""
    blob = " ".join((c.get("quote") or "") for c in a.get("claims") or [])
    assert "13" in blob
    assert re.search(r"14", blob)
    assert "November 14" in blob or "14th" in blob
    assert not is_canned_conflict_lead(lead)
    if lead:
        assert "13" in lead and "14" in lead
    assert "####" not in blob
    assert all(len((c.get("quote") or "")) < 600 for c in a.get("claims") or [])
    assert any((c.get("citation") or {}).get("evidence_span") for c in a.get("claims") or [])


class _StudentWrongQuoteNova:
    name = "fake-nova-student"

    def complete(self, system, user, **k):
        if "Verified claims" in (user or "") or "already source-checked" in (user or ""):
            fixed = repair_answer(user)  # F19 coverage-repair prompt (compliant Nova)
            if fixed:
                return json.dumps({"answer": fixed})
            if "21" in (user or "") and re.search(r"student", user or "", re.I):
                return json.dumps(
                    {
                        "answer": "University students may be eligible if they are at least 21 and meet the other criteria."
                    }
                )
            return json.dumps(
                {"answer": "University students preparing for a career in technology are named in the eligibility criteria."}
            )
        return json.dumps(
            {
                "answer": "Students can apply for the All Builders Welcome Grant.",
                "claims": [
                    {
                        "text": "Students can apply for the All Builders Welcome Grant.",
                        "source": "P1.U0",
                        "quote": "Applications for the Program must be received during the Application Period of an Event",
                    }
                ],
            }
        )


def test_student_claim_not_entailed_by_application_period_is_dropped(retriever, store):
    a = ask(
        "Can students apply for the All Builders Welcome Grant?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_StudentWrongQuoteNova()),
    )
    blob = " ".join((c.get("text") or "") + " " + (c.get("quote") or "") for c in a.get("claims") or [])
    summary = a.get("summary") or ""
    # Application-period quote must not carry an unsourced "students can apply".
    for c in a.get("claims") or []:
        quote = c.get("quote") or ""
        if "Application Period of an Event" in quote and "student" not in quote.lower():
            assert "Students can apply for the All Builders Welcome Grant." not in (c.get("text") or "")
    if "Students can apply for the All Builders Welcome Grant." in summary:
        assert re.search(r"student", blob, re.I)
    assert a.get("refused") is False
    joined = (summary + " " + blob).lower()
    assert re.search(r"student", joined, re.I)
    assert "21" in joined
    assert "21" in summary
    assert "do not specify" not in joined
    assert "Limitation of Liability" not in summary


class _HotelSuiteNova:
    name = "fake-nova-suite"

    def complete(self, system, user, **k):
        return json.dumps(
            {
                "answer": "You cannot choose your own hotel room type or upgrade to a suite with the grant.",
                "claims": [
                    {
                        "text": "You cannot choose your own hotel room type or upgrade to a suite with the grant.",
                        "source": "P1.U0",
                        "quote": "Hotel accommodations in Event Location during the Event",
                    }
                ],
            }
        )


def test_hotel_suite_unsupported_negative_is_not_published(retriever, store):
    a = ask(
        "Can I choose my own hotel room type or upgrade to a suite with the grant?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_HotelSuiteNova()),
    )
    summary = a.get("summary") or ""
    msg = a.get("message") or ""
    assert "suite" not in summary.lower()
    assert "cannot choose" not in summary.lower()
    blob = " ".join(c.get("text") or "" for c in a.get("claims") or [])
    assert "suite" not in blob.lower()
    assert a.get("refused") is True
    assert "don't specify" in msg.lower() or "do not specify" in msg.lower()


def test_who_is_eligible_surfaces_more_than_criterion_d(retriever, store):
    a = ask(
        "Who is eligible for the All Builders Welcome Grant?",
        PROFILE_GRANTEE_2026,
        mode="extractive",
        retriever=retriever,
        store=store,
    )
    blob = " ".join((c.get("text") or "") + " " + (c.get("quote") or "") for c in a.get("claims") or [])
    assert re.search(r"21", blob)
    assert re.search(r"student|career", blob, re.I)
    assert "Limitation of Liability" not in blob
    for c in a.get("claims") or []:
        assert len(c.get("quote") or "") < 600


class _PassOnlyCoverageNova:
    """Live 30d420e grant_16: repaired JSON kept only the pass bullet."""

    name = "fake-nova-pass-only"

    def complete(self, system, user, **k):
        if "Verified claims" in (user or "") or "already source-checked" in (user or ""):
            return json.dumps(
                {
                    "answer": "The ABW Grant covers a full conference pass, roundtrip flight, and hotel accommodations."
                }
            )
        return json.dumps(
            {
                "answer": "The ABW Grant covers a full conference pass, roundtrip flight, and hotel accommodations.",
                "claims": [
                    {
                        "text": "The ABW Grant covers a full conference pass.",
                        "source": "P1.U0",
                        "quote": "A full conference pass to the Event you applied for",
                    }
                ],
            }
        )


class _VenueEmptyNova:
    name = "fake-nova-venue-empty"

    def complete(self, system, user, **k):
        if "Verified claims" in (user or "") or "already source-checked" in (user or ""):
            fixed = repair_answer(user)  # F19 coverage-repair prompt (compliant Nova)
            if fixed:
                return json.dumps({"answer": fixed})
            m = re.search(r"quote: (.+)", user or "")
            ans = (m.group(1) if m else "Allow additional time for travel between properties.").strip()
            return json.dumps({"answer": ans[:400]})
        return json.dumps({"answer": "", "claims": []})


class _RegistrationSessionNova:
    """Live 30d420e grant_11: registration/session claims that are not Program Benefits."""

    name = "fake-nova-registration"

    def complete(self, system, user, **k):
        if "Verified claims" in (user or "") or "already source-checked" in (user or ""):
            return json.dumps(
                {
                    "answer": "The grant covers a full conference pass, roundtrip flight, and hotel accommodations."
                }
            )
        return json.dumps(
            {
                "answer": "The grant covers your re:Invent registration and access to sessions.",
                "claims": [
                    {
                        "text": "The grant covers your re:Invent registration.",
                        "source": "P1.U0",
                        "quote": "Sessions are held across all venues",
                    },
                    {
                        "text": "The grant covers access to sessions.",
                        "source": "P1.U0",
                        "quote": "Sessions are held across all venues",
                    },
                ],
            }
        )


def test_pass_only_claim_recovers_sibling_flight_and_hotel(retriever, store):
    a = ask(
        "List what the ABW Grant covers.",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_PassOnlyCoverageNova()),
    )
    summary = (a.get("summary") or "").lower()
    blob = " ".join((c.get("quote") or "") for c in a.get("claims") or []).lower()
    joined = summary + " " + blob
    assert a.get("refused") is False
    assert "pass" in joined
    assert "flight" in joined or "airfare" in joined
    assert "hotel" in joined


def test_venue_buffer_empty_llm_claims_bind_additional_time(retriever, store):
    a = ask(
        "When moving between conference venues, what buffer does the guidance recommend?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_VenueEmptyNova()),
    )
    joined = ((a.get("summary") or "") + " " + " ".join(
        (c.get("text") or "") + " " + (c.get("quote") or "") for c in a.get("claims") or []
    )).lower()
    assert a.get("refused") is False, (a.get("dropped"), a.get("message"))
    assert a.get("outcome_key") != "unresolved_contradiction"
    assert "additional time" in joined or "travel between" in joined


def test_registration_session_claims_fall_back_to_program_benefits(retriever, store):
    a = ask(
        "What does the grant cover for re:Invent?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_RegistrationSessionNova()),
    )
    joined = ((a.get("summary") or "") + " " + " ".join(
        (c.get("quote") or "") for c in a.get("claims") or []
    )).lower()
    assert a.get("refused") is False, (a.get("dropped"), a.get("message"))
    assert "pass" in joined
    assert "flight" in joined or "hotel" in joined


def test_summarize_coverage_is_not_no_support(retriever, store):
    a = ask(
        "Can you summarize ABW grant coverage?",
        PROFILE_GRANTEE_2026,
        mode="extractive",
        retriever=retriever,
        store=store,
    )
    assert a.get("refusal_reason") != "no_support"
    assert a.get("refused") is False


def test_accessibility_accommodation_submitted_keeps_both_dates(retriever, store):
    a = ask(
        "When do accessibility accommodation requests need to be submitted?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_Dec4NoiseNova()),
    )
    lead = a.get("summary") or ""
    blob = " ".join((c.get("quote") or "") for c in a.get("claims") or [])
    assert "13" in lead and "14" in lead
    assert re.search(r"November 14|14th", blob, re.I)
    assert lead.strip()
    assert not is_canned_conflict_lead(lead)


def test_pizza_question_is_not_answered_from_grant_terms(retriever, store):
    a = ask(
        "What's the best pizza topping?",
        PROFILE_GRANTEE_2026,
        mode="extractive",
        retriever=retriever,
        store=store,
    )
    assert a.get("kind") == "off_topic" or a.get("refused") is True
    blob = (a.get("summary") or "") + " ".join(c.get("text") or "" for c in a.get("claims") or [])
    assert "conference pass" not in blob.lower()
    assert "Limitation of Liability" not in blob
