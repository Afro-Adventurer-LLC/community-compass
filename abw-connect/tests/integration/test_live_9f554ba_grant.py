"""Live 9f554ba remaining grant retrieve / selection gaps.

Cold grant_11 retrieved registration+hotels FAQs, not Terms Program Benefits.
grant_14/16 had Terms but incomplete in-scope slots (paraphrased flight quote;
hotel omitted from summary). Stress paraphrases hit no_support on lexical noise.
Mocks vary LLM shape; they do not dictate a canned user-facing sentence.
"""
from __future__ import annotations

import json
import random
import re

from app.services.ask import ask
from app.services.generator import BedrockGenerator
from tests.integration.test_live_68dd830_recovery import (
    PROFILE_GRANTEE_2026,
    _EmptyClaimsNova,
    _FatChunkRetriever,
    _MalformedThenEmptyNova,
    _NoTermsFirstRetriever,
    _PassOnlyCoverageNova,
    _RegistrationSessionNova,
    _SplitBenefitsRetriever,
)


class _HotelOnlyBadFlightQuoteNova:
    """Live grant_14: hotel verified; flight quote paraphrased 'Event Location'."""

    name = "fake-nova-hotel-bad-flight"

    def complete(self, system, user, **k):
        if "Verified claims" in (user or ""):
            blob = user or ""
            bits = []
            if re.search(r"flight|roundtrip|airfare", blob, re.I):
                bits.append("roundtrip flight")
            if re.search(r"hotel|lodging", blob, re.I):
                bits.append("hotel accommodations")
            return json.dumps({"answer": "The grant covers " + " and ".join(bits) + "."})
        return json.dumps(
            {
                "answer": "The ABW grant covers hotel accommodations during the event.",
                "claims": [
                    {
                        "text": "The grant covers hotel accommodations.",
                        "source": "P1.U0",
                        "quote": "Hotel accommodations in Event Location during the Event",
                    },
                    {
                        "text": "The grant covers roundtrip flight.",
                        "source": "P1.U0",
                        "quote": (
                            "Roundtrip flight between an airport near (within 50 miles of) "
                            "the address you list in your application and the city of the Event Location;"
                        ),
                    },
                ],
            }
        )


class _ReplayFaqNova:
    """Live grant_11: model answers from registration/hotel FAQs including re:Play."""

    name = "fake-nova-replay-faq"

    def complete(self, system, user, **k):
        if "Verified claims" in (user or ""):
            return json.dumps(
                {
                    "answer": "The grant covers a full conference pass, roundtrip flight, and hotel accommodations."
                }
            )
        return json.dumps(
            {
                "answer": "The grant covers a full conference pass for re:Invent, and an add-on pass is available for re:Play-only entry.",
                "claims": [
                    {
                        "text": "The grant covers registration for re:Invent 2026.",
                        "source": "P1.U0",
                        "quote": "Yes. You need to be registered for re:Invent in order to attend any event sessions or functions",
                    },
                    {
                        "text": "An add-on pass is available for re:Play-only entry.",
                        "source": "P1.U0",
                        "quote": "An add-on pass is available for re:Play-only entry",
                    },
                ],
            }
        )


class _IncompleteThenCompleteNova:
    """Two short_answer variants; post-verifier should keep the covering one."""

    name = "fake-nova-two-rewrites"

    def __init__(self):
        self.n = 0

    def complete(self, system, user, **k):
        if "Verified claims" in (user or ""):
            self.n += 1
            if self.n == 1:
                return json.dumps({"answer": "The grant covers a full conference pass."})
            return json.dumps(
                {
                    "answer": "The grant covers a full conference pass, roundtrip flight, and hotel accommodations."
                }
            )
        return json.dumps({"answer": "", "claims": []})


def _joined(a: dict) -> str:
    return (
        (a.get("summary") or "")
        + " "
        + " ".join((c.get("quote") or "") for c in a.get("claims") or [])
    ).lower()


def test_grant_without_abw_acronym_retrieves_program_benefits(retriever, store):
    for q in (
        "What does the grant cover for re:Invent?",
        "What does this grant cover at re:Invent?",
        "What will the grant pay for at re:Invent?",
    ):
        wrapped = _NoTermsFirstRetriever(retriever)
        a = ask(
            q,
            PROFILE_GRANTEE_2026,
            retriever=wrapped,
            store=store,
            generator=BedrockGenerator(client=_ReplayFaqNova()),
        )
        joined = _joined(a)
        assert wrapped.calls >= 2, q
        assert a.get("refused") is False, (q, a.get("message"), a.get("dropped"))
        assert "pass" in joined
        assert "flight" in joined or "airfare" in joined
        assert "hotel" in joined
        assert "re:play-only" not in joined
        assert "can i still stay" not in joined


def test_paraphrased_flight_quote_still_binds_source_flight(retriever, store):
    a = ask(
        "What travel and lodging does the ABW grant cover?",
        PROFILE_GRANTEE_2026,
        retriever=_SplitBenefitsRetriever(retriever),
        store=store,
        generator=BedrockGenerator(client=_HotelOnlyBadFlightQuoteNova()),
    )
    joined = _joined(a)
    assert a.get("refused") is False
    assert "hotel" in joined
    assert "flight" in joined or "airfare" in joined or "roundtrip" in joined
    summary = (a.get("summary") or "").lower()
    if summary:
        assert "flight" in summary or "airfare" in summary or "roundtrip" in summary
        assert "hotel" in summary or "lodging" in summary


def test_list_coverage_recovers_missing_hotel_slot(retriever, store):
    a = ask(
        "List what the ABW Grant covers.",
        PROFILE_GRANTEE_2026,
        retriever=_FatChunkRetriever(retriever),
        store=store,
        generator=BedrockGenerator(client=_PassOnlyCoverageNova()),
    )
    joined = _joined(a)
    assert a.get("refused") is False
    assert "pass" in joined
    assert "flight" in joined or "airfare" in joined
    assert "hotel" in joined
    summary = (a.get("summary") or "").lower()
    if summary:
        assert "hotel" in summary or "lodging" in summary


def test_stress_paraphrases_are_not_no_support(retriever, store):
    questions = [
        "What is included when someone receives an ABW grant?",
        "List ABW Grant inclusions for re:Invent attendees.",
        "Can you outline the ABW grant package components?",
        "Which costs does the ABW grant pay?",
        "Does ABW cover airfare, lodging, and a conference badge?",
        "Break down ABW grant coverage for me.",
        "What benefits come with the All Builders Welcome Grant?",
        "Summarize program benefits of the All Builders Welcome Grant.",
        "What support package does ABW provide to grantees?",
        "What does AWS All Builders Welcome funding cover?",
    ]
    rng = random.Random(9)
    novas = [
        _EmptyClaimsNova(),
        _PassOnlyCoverageNova(),
        _MalformedThenEmptyNova(),
        _IncompleteThenCompleteNova(),
        _RegistrationSessionNova(),
    ]
    for q in questions:
        nova = rng.choice(novas)
        a = ask(
            q,
            PROFILE_GRANTEE_2026,
            retriever=_FatChunkRetriever(retriever),
            store=store,
            generator=BedrockGenerator(client=nova),
        )
        assert a.get("refusal_reason") != "no_support", (q, type(nova).__name__)
        if isinstance(nova, _MalformedThenEmptyNova) and a.get("refused"):
            # F19: this fake never writes a verifiable answer (it echoes a quote). The
            # honest outcome is a no_verified_claim refusal, not claims under an empty
            # summary (which is what earlier tips returned here).
            assert a.get("refusal_reason") == "no_verified_claim", (q, a.get("refusal_reason"))
            continue
        assert a.get("refused") is False, (q, a.get("message"), a.get("dropped"))
        assert (a.get("summary") or "").strip(), (q, type(nova).__name__, a.get("dropped"))
        joined = _joined(a)
        assert "flight" in joined or "hotel" in joined or "pass" in joined, q
        canned = "The grant covers a full conference pass, roundtrip airfare, and hotel accommodation."
        assert (a.get("summary") or "").strip() != canned


def test_rewrite_prefers_covering_candidate(retriever, store):
    a = ask(
        "What does the ABW Grant cover?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_IncompleteThenCompleteNova()),
    )
    summary = (a.get("summary") or "").lower()
    joined = _joined(a)
    assert a.get("refused") is False
    assert "pass" in joined and ("flight" in joined or "hotel" in joined)
    if summary:
        assert "pass" in summary
        assert "flight" in summary or "hotel" in summary
