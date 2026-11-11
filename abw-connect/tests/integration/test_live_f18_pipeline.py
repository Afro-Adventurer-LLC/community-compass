"""F18 live-008a222 residual failures: rewrite keep, paraphrases, dual dates, venue buffer.

Mocks reproduce the raw-trace shapes from /workspace/abw-deploy/live-008a222 (cold + stress).
They do not hardcode user-facing answer strings in production code paths.
"""
from __future__ import annotations

import json
import re

from app.services.ask import ask
from app.services.generator import BedrockGenerator
from app.services.present import is_canned_conflict_lead
from tests.integration.test_pipeline import PROFILE_GRANTEE_2026
from tests.integration.live_replay import repair_answer


class _StudentOmitsThenIncludesAgeNova:
    """Live student1: first short_answer omits age 21; second includes it but was discarded."""

    name = "fake-nova-student-age-retry"

    def __init__(self):
        self.n = 0

    def complete(self, system, user, **k):
        if "Verified claims" in (user or "") or "already source-checked" in (user or ""):
            fixed = repair_answer(user)  # F19 coverage-repair prompt (compliant Nova)
            if fixed:
                return json.dumps({"answer": fixed})
            self.n += 1
            if self.n == 1:
                return json.dumps(
                    {
                        "answer": (
                            "Students can apply for the All Builders Welcome Grant if they "
                            "are preparing for a career in technology."
                        )
                    }
                )
            return json.dumps(
                {
                    "answer": (
                        "Students can apply for the All Builders Welcome Grant if they are "
                        "preparing for a career in technology. However, applicants must be "
                        "at least 21 years of age."
                    )
                }
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


class _EligFramingNova:
    """Live stress elig: summaries used the word eligibility and were hard-rejected."""

    name = "fake-nova-elig-framing"

    def __init__(self):
        self.n = 0

    def complete(self, system, user, **k):
        if "Verified claims" in (user or "") or "already source-checked" in (user or ""):
            self.n += 1
            # First draft may omit a verified constraint; retry must include omitted facts.
            if self.n == 1 and "employee" not in (user or "").lower():
                return json.dumps(
                    {
                        "answer": (
                            "ABW eligibility requires you to be at least 21 years of age and "
                            "within the first 5 years of your technology career or a university "
                            "student preparing for a career in technology."
                        )
                    }
                )
            return json.dumps(
                {
                    "answer": (
                        "ABW eligibility requires you to be at least 21 years of age, "
                        "within the first 5 years of your technology career or a university "
                        "student preparing for a career in technology, and not an employee "
                        "of AWS or its affiliates."
                    )
                }
            )
        return json.dumps({"answer": "", "claims": []})


class _ReapplyYearEchoNova:
    """Live stress prior: summary used 'year' from the question and was hard-rejected."""

    name = "fake-nova-reapply-year"

    def complete(self, system, user, **k):
        if "Verified claims" in (user or "") or "already source-checked" in (user or ""):
            return json.dumps(
                {
                    "answer": (
                        "If you were not selected for a cohort last year, you may reapply "
                        "for subsequent cohorts as long as you are eligible."
                    )
                }
            )
        return json.dumps(
            {
                "answer": "You may reapply.",
                "claims": [
                    {
                        "text": "If you are not selected, you may reapply for subsequent cohorts as long as you are eligible.",
                        "source": "P1.U0",
                        "quote": (
                            "If you are not selected for a cohort of the Program, you may reapply "
                            "for subsequent cohorts of the Program as long as you are eligible."
                        ),
                    }
                ],
            }
        )


class _AccessArriveOnesidedNova:
    """Live stress access: onesided Nov 13 lead; rewrite must surface both verified dates."""

    name = "fake-nova-access-arrive"

    def __init__(self):
        self.n = 0

    def complete(self, system, user, **k):
        if "Verified claims" in (user or "") or "already source-checked" in (user or ""):
            return json.dumps(
                {
                    "answer": (
                        "Official pages disagree: one says accessibility requests must arrive "
                        "by Nov. 13, 2026, and another says by November 14th."
                    )
                }
            )
        self.n += 1
        return json.dumps(
            {
                "answer": "Accessibility requests must arrive by Nov. 13, 2026.",
                "claims": [
                    {
                        "text": "The deadline for all requests is Nov. 13, 2026.",
                        "source": "P1.U0",
                        "quote": "The deadline for all requests is Nov. 13, 2026.",
                    }
                ],
            }
        )


class _SummarizeCoveragePassFlightNova:
    """Live grant_13: model named hotel in answer but hotel never verified; salvage must bind it."""

    name = "fake-nova-summarize-pass-flight"

    def complete(self, system, user, **k):
        if "Verified claims" in (user or "") or "already source-checked" in (user or ""):
            blob = user or ""
            bits = []
            if re.search(r"pass|conference", blob, re.I):
                bits.append("a full conference pass")
            if re.search(r"flight|roundtrip|airfare", blob, re.I):
                bits.append("a roundtrip flight")
            if re.search(r"hotel|lodging|accommodations", blob, re.I):
                bits.append("hotel accommodations")
            return json.dumps({"answer": "The ABW grant covers " + ", ".join(bits) + "."})
        return json.dumps(
            {
                "answer": "The ABW grant covers a full conference pass, roundtrip flight, and hotel accommodations.",
                "claims": [
                    {
                        "text": "The ABW grant covers a full conference pass.",
                        "source": "P1.U0",
                        "quote": "A full conference pass to the Event you applied for",
                    },
                    {
                        "text": "The grant covers a roundtrip flight.",
                        "source": "P1.U0",
                        "quote": (
                            "Roundtrip flight between an airport near (within 50 miles of) "
                            "the address you list in your application and the city of the Event "
                            '("Event Location")'
                        ),
                    },
                ],
            }
        )


def _joined(a: dict) -> str:
    return (
        (a.get("summary") or "")
        + " "
        + " ".join((c.get("quote") or "") + " " + (c.get("text") or "") for c in a.get("claims") or [])
    ).lower()


def test_student_age_retry_is_kept_not_emptied(retriever, store):
    a = ask(
        "Can students apply for the All Builders Welcome Grant?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_StudentOmitsThenIncludesAgeNova()),
    )
    summary = a.get("summary") or ""
    assert a.get("refused") is False
    assert summary.strip(), a.get("dropped")
    assert "21" in summary
    assert re.search(r"student", summary, re.I)


def test_undergrad_paraphrase_is_not_no_support(retriever, store):
    a = ask(
        "Do undergrads qualify for All Builders Welcome?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_StudentOmitsThenIncludesAgeNova()),
    )
    assert a.get("refusal_reason") != "no_support"
    assert a.get("refused") is False
    joined = _joined(a)
    assert "21" in joined
    assert re.search(r"student|university", joined, re.I)
    summary = a.get("summary") or ""
    if summary:
        assert "21" in summary


def test_eligibility_framing_word_does_not_empty_summary(retriever, store):
    a = ask(
        "What are the ABW eligibility requirements?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_EligFramingNova()),
    )
    summary = a.get("summary") or ""
    assert a.get("refused") is False
    assert summary.strip(), a.get("dropped")
    assert "21" in summary
    assert re.search(r"student|career", summary, re.I)


def test_reapply_question_year_echo_keeps_answer(retriever, store):
    a = ask(
        "If I was rejected last year, can I try ABW again?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_ReapplyYearEchoNova()),
    )
    summary = a.get("summary") or ""
    assert a.get("refused") is False
    assert summary.strip(), a.get("dropped")
    assert re.search(r"reapply", summary, re.I)


def test_access_arrive_paraphrase_keeps_both_dates(retriever, store):
    for q in (
        "When must accessibility requests arrive?",
        "Last day to request ASL or accessibility services?",
        "Accessibility services cutoff date for re:Invent 2026?",
    ):
        a = ask(
            q,
            PROFILE_GRANTEE_2026,
            retriever=retriever,
            store=store,
            generator=BedrockGenerator(client=_AccessArriveOnesidedNova()),
        )
        blob = _joined(a)
        summary = a.get("summary") or ""
        assert "13" in blob and re.search(r"14", blob), (q, a.get("dropped"), blob[:300])
        assert not is_canned_conflict_lead(summary)
        if summary:
            assert "13" in summary and "14" in summary, (q, summary)


def test_campus_transit_paraphrases_bind_travel_buffer(retriever, store):
    for q in (
        "Transit buffer between re:Invent campuses?",
        "Any guidance on getting across the re:Invent campus?",
        "How many minutes between venues should I plan?",
    ):
        a = ask(
            q,
            PROFILE_GRANTEE_2026,
            mode="extractive",
            retriever=retriever,
            store=store,
        )
        joined = _joined(a)
        assert a.get("refusal_reason") != "no_support", q
        # Prefer venue buffer evidence over accessible-transportation-only drift.
        assert (
            "additional" in joined
            or "30" in joined
            or "45" in joined
            or "minutes" in joined
            or "properties" in joined
        ), (q, joined[:400])
        if "accessible transportation" in joined and "additional" not in joined:
            # Transport FAQ alone is not enough for buffer paraphrases.
            assert "30" in joined or "45" in joined or "minutes" in joined, q


def test_summarize_coverage_binds_hotel_into_claims_and_summary(retriever, store):
    a = ask(
        "Can you summarize ABW grant coverage?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_SummarizeCoveragePassFlightNova()),
    )
    joined = _joined(a)
    summary = (a.get("summary") or "").lower()
    assert a.get("refused") is False
    assert "hotel" in joined or "lodging" in joined
    assert "pass" in joined
    assert "flight" in joined or "roundtrip" in joined or "airfare" in joined
    if summary:
        assert "hotel" in summary or "lodging" in summary
        canned = "the grant covers a full conference pass, roundtrip airfare, and hotel accommodation."
        assert summary.strip() != canned


def test_hotel_room_unspecified_still_refuses(retriever, store):
    class _SuiteNova:
        name = "fake-nova-suite-f18"

        def complete(self, system, user, **k):
            return json.dumps(
                {
                    "answer": "You cannot choose a suite.",
                    "claims": [
                        {
                            "text": "You cannot choose a suite.",
                            "source": "P1.U0",
                            "quote": "Hotel accommodations in Event Location during the Event",
                        }
                    ],
                }
            )

    a = ask(
        "Can I upgrade to my own suite with the ABW grant?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_SuiteNova()),
    )
    assert a.get("refused") is True
    msg = (a.get("message") or a.get("refusal") or "").lower()
    assert "do not specify" in msg or "couldn't find" in msg or "unspecified" in (a.get("refusal_reason") or "")


def test_off_topic_france_still_safe(retriever, store):
    a = ask(
        "What is the capital of France?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
    )
    assert a.get("kind") in ("off_topic", "smalltalk", None) or a.get("refused") or a.get("kind") == "off_topic"
    summary = (a.get("summary") or "").lower()
    assert "paris" not in summary


def test_accept_rewrite_hard_rejects_incomplete_eligibility(retriever, store):
    """Coverage miss is not soft-accepted: incomplete eligibility draft must not publish."""
    from app.services.ask import _accept_rewrite

    claims = [
        {
            "text": "you are at least 21 years of age; B.",
            "quote": "you are at least 21 years of age; B.",
        },
        {
            "text": "You may not be an employee of AWS or its affiliates.",
            "quote": "You may not be an employee of AWS or its affiliates.",
        },
        {
            "text": "university student preparing for a career in technology",
            "quote": "university student preparing for a career in technology",
        },
    ]
    dropped = []
    accepted, omitted = _accept_rewrite(
        "Applicants should be preparing for a career in technology.",
        "What are the ABW eligibility requirements?",
        claims,
        dropped,
    )
    assert accepted is None
    assert omitted
    assert any("employee" in o.lower() or "21" in o for o in omitted)


def test_emotional_thanks_then_grant_still_answers(retriever, store):
    from app.services.chat import chat

    # Greeting / thanks first should not poison a later grant question.
    r0 = chat(
        "thanks!",
        PROFILE_GRANTEE_2026,
        store=store,
        retriever=retriever,
        mode="extractive",
    )
    assert r0.get("kind") == "greeting"
    a = chat(
        "What does the All Builders Welcome Grant cover?",
        PROFILE_GRANTEE_2026,
        conversation_id=r0.get("conversation_id"),
        store=store,
        retriever=retriever,
        mode="extractive",
    )
    joined = _joined(a)
    assert a.get("refused") is False
    assert "pass" in joined or "flight" in joined or "hotel" in joined


def test_f17_student_trace_shape_keeps_multifact_age21(retriever, store):
    """Same response shape as live student1_01: bad entailment then age-21 rewrite kept."""
    a = ask(
        "Can students apply for the All Builders Welcome Grant?",
        PROFILE_GRANTEE_2026,
        retriever=retriever,
        store=store,
        generator=BedrockGenerator(client=_StudentOmitsThenIncludesAgeNova()),
    )
    summary = a.get("summary") or ""
    assert summary.strip()
    assert "21" in summary
    assert re.search(r"student", summary, re.I)
    # Must not publish the incomplete first draft alone.
    assert "21" in summary
