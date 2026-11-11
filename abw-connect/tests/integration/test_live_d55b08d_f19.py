"""F19: live d55b08d failure traces replayed against captured Bedrock chunks.

Retrieval: `tests/fixtures/live_d55b08d/bedrock_retrieve.json` holds the real Bedrock
Retrieve results (flattened chunk text, no local kb/ — like the deployed Lambda) for
every query the pipeline makes on these questions. Generation: `TraceNova` replays the
live Nova outputs from /workspace/abw-deploy/live-d55b08d (answers, cited quotes, and
the rejected short_answer drafts, verbatim). Where the live run stopped (it never made
a third, coverage-repair call), the fake only states a fact when the prompt actually
shows that verified claim, so the test checks that the pipeline puts the evidence in
front of the model; production code never writes the answer.
"""
from __future__ import annotations

import json
import re

import pytest

from app.services.ask import ask
from app.services.generator import BedrockGenerator, parse_llm_json
from app.services.present import is_canned_conflict_lead
from app.services.verify import verify_unspecified_summary
from tests.integration.live_replay import ReplayRetriever, TraceNova, must_include_block

PROFILE = {"event_year": 2026, "include_alumni": True, "role": "grantee"}

PASS_Q = "A full conference pass to the Event you applied for"

# ---- live strings (verbatim from live-d55b08d raw records) -----------------------------

G13_Q = "Can you summarize ABW grant coverage?"
G13_ANSWER = "The ABW grant covers a full conference pass, roundtrip flight, and hotel accommodations."
G13_SHORT = (
    "The ABW grant covers a full conference pass and a roundtrip flight between an airport near "
    "the applicant's address and the event location."
)
S00_Q = "What are the ABW grant benefits?"
S00_ANSWER = "The ABW grant benefits include a full conference pass, roundtrip flight, and hotel accommodations."

STU1_Q = "Can students apply for the All Builders Welcome Grant?"
STU1_DRAFTS = [
    "Students can apply for the All Builders Welcome Grant if they are preparing for a career in technology. Full eligibility details are in the Terms and Conditions.",
    "Students can apply for the All Builders Welcome Grant if they are preparing for a career in technology. Age requirements are not specified for students.",
]
STU2_Q = "Are university students eligible for the ABW Grant?"
STU2_DRAFTS = [
    "University students preparing for a career in technology are eligible for the ABW Grant, but only a limited number of grants will be awarded to them.",
    "University students preparing for a career in technology are eligible for the ABW Grant, but they must be within the first 5 years of their career or be a student. However, you must be at least 21 years old, not previously accepted a grant, and not be affiliated with AWS. Personal expenses are not reimbursable.",
]
S18_Q = "May college students apply to ABW?"
S18_DRAFTS = [
    "College students may apply if they are preparing for a career in technology. A limited number of grants are available to select university students.",
    "College students may apply if they are preparing for a career in technology. However, you must be at least 21 years of age to apply.",
]
S19_Q = "Do undergrads qualify for All Builders Welcome?"
S19_DRAFTS = [
    "Undergraduates qualify for All Builders Welcome if they are preparing for a career in technology. Age and other conditions apply.",
    "Undergraduates qualify for All Builders Welcome if they are preparing for a career in technology. However, they must also be at least 21 years old.",
]
S20_Q = "What are the ABW eligibility requirements?"
S20_DRAFTS = [
    "You may not have previously accepted a grant to the Event you are applying for, be an employee of AWS or its affiliates, be an employee of an entity engaged in illegal activity, or be an employee of an entity subject to sanctions or owned by a government. You must complete all mandatory fields of the application and attend the full Event. You must also comply with the AWS Code of Conduct and AWS Event Terms and Conditions.",
    "ABW eligibility requires you to not have previously accepted a grant for the event, not be an employee of AWS or sanctioned entities, complete all application fields, attend the full event, comply with AWS Code of Conduct and Event Terms, and be within the first 5 years of your tech career or a university student with unique barriers.",
    "You must be at least 21 years old, not have previously accepted a grant for the event, not be an employee of AWS or its affiliates, not be on any restricted parties list, complete all application fields, attend the full event, comply with the AWS Code of Conduct and Event Terms, and meet one of the eligibility criteria.",
]
S20_CLAIMS = [
    ("You may not have previously accepted a grant to the Event you are applying for.",
     "you have not previously accepted a grant to the Event you are applying for (e.g., from the We Power Tech or All Builders Welcome programs"),
    ("You must complete all mandatory fields of the application.",
     "You are required to complete all mandatory fields of the application; incomplete entries will not be accepted as valid"),
    ("You must attend the full Event.",
     "If you are accepted into the Program, you must (1) attend the full Event"),
]
ROOM_Q = "Can I choose my own hotel room type with the ABW grant?"
ROOM_DRAFTS = [
    "You cannot choose your own hotel room type with the ABW grant.",
    "The grant provides hotel accommodations, but it does not specify if you can choose your own room type.",
]
HOTEL_CLAIM = ("The grant provides hotel accommodations during the event.", "Hotel accommodations in Event Location during the Event")
SUITE_Q = "Can ABW grantees pick a suite instead of a standard room?"

S16_Q = "Transit buffer between re:Invent campuses?"
S16_CLAIM = (
    "Accessible transportation across the re:Invent campus will be available throughout the week.",
    "Accessible transportation across the re:Invent campus will be available throughout the week, including for re:Play, the official AWS re:Invent party",
)
S17_Q = "Time to leave when walking between properties?"
S17_CLAIM = (
    "You must arrive at the room at least ten minutes prior to the session start time or your seat will be released to walk-up attendees.",
    "You must arrive at the room at least ten minutes prior to the session start time or your seat will be released to walk-up attendees and you will be asked to join the back of the walk-up line",
)
S26_Q = "Any guidance on getting across the re:Invent campus?"
S15_Q = "How many minutes between venues should I plan?"
V01_Q = "How much time should I leave between re:Invent venues?"
ADDL = ("Allow additional time for travel between properties.", "Allow additional time for travel between properties")

_TRAVEL_MIN = re.compile(r"allow (\d+) to (\d+) minutes between venues", re.I)


def _prev_draft(user: str) -> str:
    m = re.search(r"Rejected draft: (.*)\n", user or "")
    return m.group(1) if m else ""


def _travel_writer(fallback: str):
    """Simulated Nova rewrite. States documented minutes only if the prompt shows them, and
    (like Nova on a repair prompt) adds each listed missing fact in its own words."""

    def after(user: str) -> str:
        block = must_include_block(user).lower()
        parts = []
        m = _TRAVEL_MIN.search(user or "")
        if m:
            parts.append(f"Allow {m.group(1)} to {m.group(2)} minutes between venues, since sessions run across multiple properties.")
        if "additional time" in block:
            parts.append("Build in additional time for travel between properties.")
        if "ten minutes" in block:
            parts.append("Also arrive at your session room at least ten minutes early or your reserved seat may be released.")
        if "accessible transportation" in block:
            parts.append("Accessible transportation across the campus is available throughout the week.")
        return " ".join(parts) or fallback

    return after


def _student_repair(user: str) -> str | None:
    """Simulated Nova coverage repair for student/eligibility asks: keeps the rejected
    draft and adds each verified fact the prompt lists (age 21, criterion, restrictions)."""
    block = must_include_block(user).lower()
    if not block:
        return None
    prev = _prev_draft(user).strip().rstrip(".")
    bits = []
    if "university student" in block:
        bits.append("university students preparing for a career in technology can apply, and a limited number of grants go to them")
    if "first 5 years" in block:
        bits.append("early-career applicants within their first 5 years in tech also qualify")
    if "21" in block:
        bits.append("applicants must be at least 21")
    if "previously" in block:
        bits.append("you must not have previously accepted a grant for the event")
    if "employee" in block or "affiliat" in block:
        bits.append("you must not be an AWS employee or affiliate")
    if not bits:
        return None
    return (prev + ". Also, " if prev else "") + "; ".join(bits) + "."


def _elig_repair(user: str) -> str | None:
    """Simulated Nova repair for the requirements ask: one concise list in its own words,
    keeping the rejected draft's criteria and adding the listed ones."""
    block = must_include_block(user).lower()
    if "university student" in block or "first 5 years" in block:
        return (
            "You must be at least 21, be within the first 5 years of your technology career or a "
            "university student preparing for a career in technology (a limited number of grants go to "
            "students), not have previously accepted a grant for the event, not be an AWS employee or "
            "affiliate, complete all mandatory application fields, and attend the full event."
        )
    return None


CASES = {
    "grant_13": lambda: (G13_Q, TraceNova(answer=G13_ANSWER, claims=[("The ABW grant covers a full conference pass.", PASS_Q)], shorts=[G13_SHORT])),
    "stress_00": lambda: (S00_Q, TraceNova(answer=S00_ANSWER, claims=[("The ABW grant provides a full conference pass to the event.", PASS_Q)])),
    "student1": lambda: (STU1_Q, TraceNova(answer="Students can apply for the All Builders Welcome Grant in 2026.", claims=[("Students can apply for the All Builders Welcome Grant in 2026.", "Applications for the Program must be received during the Application Period of an Event")], shorts=list(STU1_DRAFTS), after=_student_repair)),
    "student2": lambda: (STU2_Q, TraceNova(answer="The grant terms do not specify if university students are eligible.", claims=[("The grant terms do not specify if university students are eligible.", "By completing and submitting your application, you confirm that you have read, understand, and agree to be bound by these Terms and the decisions of AWS and the selection committee and that you satisfy all eligibility requirements")], shorts=list(STU2_DRAFTS), after=_student_repair)),
    "stress_18": lambda: (S18_Q, TraceNova(answer="The terms do not specify that college students are ineligible to apply.", claims=[("The terms do not specify that college students are ineligible to apply.", "D. you have not previously accepted a grant to the Event you are applying for")], shorts=list(S18_DRAFTS), after=_student_repair)),
    "stress_19": lambda: (S19_Q, TraceNova(answer="The grant terms do not specify that undergrads are ineligible.", claims=[("The grant terms do not specify that undergrads are ineligible.", "D. you have not previously accepted a grant to the Event you are applying for (e.g., from the We Power Tech or All Builders Welcome programs")], shorts=list(S19_DRAFTS), after=_student_repair)),
    "stress_20": lambda: (S20_Q, TraceNova(answer=S20_DRAFTS[0], claims=S20_CLAIMS, shorts=S20_DRAFTS[1:], after=_elig_repair)),
    "hotel_room_01": lambda: (ROOM_Q, TraceNova(answer=ROOM_DRAFTS[0], claims=[HOTEL_CLAIM], shorts=[ROOM_DRAFTS[1]])),
    "stress_22": lambda: (SUITE_Q, TraceNova(answer="The grant provides hotel accommodations, but the documents don't specify whether you can pick a suite instead of a standard room.", claims=[HOTEL_CLAIM])),
    "stress_22_invented": lambda: (SUITE_Q, TraceNova(answer="Yes, you can pick a suite instead of a standard room.", claims=[HOTEL_CLAIM], shorts=["You may upgrade to a suite with the grant."])),
    "stress_16": lambda: (S16_Q, TraceNova(answer=S16_CLAIM[0], claims=[S16_CLAIM], after=_travel_writer(S16_CLAIM[0]))),
    "stress_17": lambda: (S17_Q, TraceNova(answer="You must arrive at the room at least ten minutes prior to the session start time.", claims=[S17_CLAIM], after=_travel_writer("You must arrive at the room at least ten minutes prior to the session start time."))),
    "stress_26": lambda: (S26_Q, TraceNova(answer="Accessible transportation will be available across the re:Invent campus, including for re:Play.", claims=[("Accessible transportation will be available across the re:Invent campus, including for re:Play.", S16_CLAIM[1])], after=_travel_writer("Accessible transportation will be available across the re:Invent campus."))),
    "stress_15": lambda: (S15_Q, TraceNova(answer=ADDL[0], claims=[ADDL], after=_travel_writer(ADDL[0]))),
    "venue_01": lambda: (V01_Q, TraceNova(answer=ADDL[0], claims=[ADDL], after=_travel_writer(ADDL[0]))),
}


def run_case(name: str, retriever, store):
    q, nova = CASES[name]()
    a = ask(q, PROFILE, retriever=retriever, store=store, generator=BedrockGenerator(client=nova))
    return a, nova


@pytest.fixture
def replay(monkeypatch):
    # Deployed Lambda knobs for Bedrock 0-1 scores (docs/AWS_DEPLOY.md), not the mock defaults.
    import app.services.ask as ask_mod

    monkeypatch.setattr(ask_mod, "MIN_SCORE", 0.25)
    monkeypatch.setattr(ask_mod, "OFF_TOPIC_SCORE", 0.15)
    return ReplayRetriever()


def _common(a, replay):
    assert not replay.misses, replay.misses
    s = a.get("summary") or ""
    assert a.get("refused") is False, (a.get("refusal_reason"), a.get("dropped"))
    assert s.strip(), a.get("dropped")
    assert (a.get("generator") or "").startswith("llm:")
    assert not is_canned_conflict_lead(s)
    assert "here's what i can answer" not in s.lower()
    assert len(s) < 450
    return s


# ---- 1. student / eligibility --------------------------------------------------------


def test_student2_live_second_draft_with_restrictions_is_accepted(replay, store):
    a, _ = run_case("student2", replay, store)
    s = _common(a, replay)
    assert s == STU2_DRAFTS[1]  # the live LLM draft itself: 21 + previously accepted + AWS affiliation


@pytest.mark.parametrize("name,draft", [("stress_18", S18_DRAFTS[1]), ("stress_19", S19_DRAFTS[1])])
def test_student_draft_without_restrictions_is_rejected_then_repaired(replay, store, name, draft):
    a, nova = run_case(name, replay, store)
    s = _common(a, replay)
    assert s != draft
    assert any(d.get("text") == draft for d in a["dropped"])  # 21 alone is not enough
    low = s.lower()
    assert "21" in s and "previously accepted" in low and ("aws employee" in low or "affiliat" in low)
    assert ("student" in low or "undergrad" in low)
    block = must_include_block(nova.short_users[-1]).lower()
    assert "previously accepted" in block and "employee" in block


def test_no_code_written_partial_note(replay, store):
    for name in CASES:
        a, _ = run_case(name, replay, store)
        assert not any(n.get("kind") == "summary_partial" for n in a.get("notes") or []), name


def test_coverage_never_satisfied_refuses_after_final_llm_attempt(replay, store):
    """A Nova that never states the restrictions: 4 bounded LLM calls (the last is the
    final repair prompt), nothing that fails coverage is published, normal refusal."""
    nova = TraceNova(
        answer=S19_DRAFTS[0],
        claims=[("The grant terms do not specify that undergrads are ineligible.", "D. you have not previously accepted a grant to the Event you are applying for (e.g., from the We Power Tech or All Builders Welcome programs")],
        shorts=list(S19_DRAFTS) + [S19_DRAFTS[1], S19_DRAFTS[1]],
    )
    a = ask(S19_Q, PROFILE, retriever=replay, store=store, generator=BedrockGenerator(client=nova))
    assert a["refused"] is True and a.get("refusal_reason") == "no_verified_claim"
    assert a["summary"] is None
    assert len(nova.short_users) == 4
    assert "This is the final attempt" in nova.short_users[3]
    assert "previously accepted" in must_include_block(nova.short_users[3])


def test_student1_coverage_repair_states_age_21(replay, store):
    a, nova = run_case("student1", replay, store)
    s = _common(a, replay)
    assert "21" in s and "student" in s.lower()
    # Both live drafts were rejected (no age 21); the third call was the coverage repair
    # and it listed the verified age-21 claim for the model.
    assert len(nova.short_users) == 3
    assert "21 years of age" in must_include_block(nova.short_users[2])
    reasons = [d["reason"] for d in a["dropped"] if d.get("source") == "answer"]
    assert any("age 21" in r or "omits verified facts" in r for r in reasons)


def test_eligibility_requirements_repair_after_two_rejections(replay, store):
    a, nova = run_case("stress_20", replay, store)
    s = _common(a, replay)
    assert "21" in s
    assert "student" in s.lower() or "career" in s.lower()
    assert len(nova.short_users) == 3


def test_live_student_drafts_without_21_are_still_rejected(replay, store):
    """Strictness held: the two live student1 drafts never become the answer."""
    a, _ = run_case("student1", replay, store)
    assert a["summary"] not in STU1_DRAFTS
    assert "not specified" not in (a["summary"] or "").lower()


# ---- 2. grant hotel --------------------------------------------------------------------


@pytest.mark.parametrize("name", ["grant_13", "stress_00"])
def test_grant_flattened_benefits_list_binds_hotel(replay, store, name):
    a, _ = run_case(name, replay, store)
    s = _common(a, replay).lower()
    assert "pass" in s and ("flight" in s or "airfare" in s) and "hotel" in s
    hotel = [c for c in a["claims"] if "hotel accommodations in event location" in (c.get("quote") or "").lower()]
    assert hotel, [c["quote"] for c in a["claims"]]
    assert "abw-terms" in hotel[0]["citation"]["doc_id"]
    for c in a["claims"]:
        assert len(c.get("quote") or "") <= 400


def test_repaired_json_with_inner_quotes_keeps_every_claim():
    """Live grant_13 parsed as `repaired`: Terms quote `the Event ("Event Location")`."""
    raw = (
        '{"answer": "' + G13_ANSWER + '", "claims": ['
        '{"text": "The ABW grant covers a full conference pass.", "source": "P5.U0", "quote": "' + PASS_Q + '"}, '
        '{"text": "The grant covers a roundtrip flight.", "source": "P5.U0", "quote": "Roundtrip flight between an airport near (within 50 miles of) the address you list in your application and the city of the Event ("Event Location")"}, '
        '{"text": "The grant covers hotel accommodations.", "source": "P5.U0", "quote": "Hotel accommodations in Event Location during the Event"}]}'
    )
    data, how = parse_llm_json(raw)
    assert how == "repaired"
    assert [c["quote"][:5] for c in data["claims"]] == ["A ful", "Round", "Hotel"]
    assert data["claims"][1]["quote"].endswith('("Event Location")')


def test_truncated_last_claim_is_kept_for_verification():
    raw = (
        '{"answer": "x", "claims": [{"text": "pass", "source": "P1.U0", "quote": "A full conference pass"}, '
        '{"text": "The grant covers hotel accommodations in Event Loc'
    )
    data, _ = parse_llm_json(raw)
    assert len(data["claims"]) == 2
    assert "hotel" in data["claims"][1]["text"]


# ---- 3. hotel room type ------------------------------------------------------------------


def test_room_type_llm_unspecified_answer_is_accepted(replay, store):
    a, _ = run_case("hotel_room_01", replay, store)
    s = _common(a, replay)
    assert s == ROOM_DRAFTS[1]
    assert any(d.get("text") == ROOM_DRAFTS[0] for d in a["dropped"])  # invented prohibition rejected


def test_suite_question_reaches_the_llm_and_answers_unspecified(replay, store):
    a, nova = run_case("stress_22", replay, store)
    assert a.get("refusal_reason") != "no_support"
    assert nova.claim_users, "LLM never ran"
    s = _common(a, replay)
    assert "specify" in s.lower()


def test_suite_invented_permission_is_refused_not_published(replay, store):
    a, _ = run_case("stress_22_invented", replay, store)
    assert not replay.misses, replay.misses
    assert a["refused"] is True and a.get("refusal_reason") == "unspecified"
    assert a["summary"] is None


@pytest.mark.parametrize(
    "text,ok",
    [
        ("The grant allows you to choose a suite; room type is otherwise not specified.", False),
        ("The documents don't specify room type, but the grant lets grantees pick a suite.", False),
        ("Room type is not specified, and suites are available to grantees.", False),
        ("The documents don't specify room type; upgrades can be requested.", False),
        ("Room selection is up to you; the documents don't say more.", False),
        ("The grant provides hotel accommodations, but it does not specify if you can choose your own room type.", True),
        ("The documents don't say whether grantees can pick a suite.", True),
        ("You cannot choose your own hotel room type with the ABW grant.", False),
        ("The documents don't specify it, but you can choose a suite.", False),
        ("Hotel is covered for 5 nights; room type is not specified.", False),
    ],
)
def test_verify_unspecified_summary(text, ok):
    claims = [dict(text=HOTEL_CLAIM[0], quote=HOTEL_CLAIM[1])]
    assert verify_unspecified_summary(text, claims, ROOM_Q)[0] is ok


# ---- 4. venue --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["stress_16", "stress_17", "stress_26", "stress_15", "venue_01"])
def test_venue_paraphrases_state_documented_minutes(replay, store, name):
    a, _ = run_case(name, replay, store)
    s = _common(a, replay)
    assert "30" in s and "45" in s, (s, [c["quote"] for c in a["claims"]])
    mins = [c for c in a["claims"] if re.search(r"30 to 45 minutes", c.get("quote") or "")]
    assert mins and "know-before-you-go" in mins[0]["citation"]["doc_id"]
    # never invent minutes: every number in the answer is in a verified quote
    quotes = " ".join(c.get("quote") or "" for c in a["claims"])
    for n in re.findall(r"\d+", s):
        assert n in quotes


def test_live_venue_summary_without_minutes_is_rejected(replay, store):
    a, _ = run_case("stress_15", replay, store)
    assert any(
        d.get("text") == ADDL[0] and "travel minutes" in d.get("reason", "") for d in a["dropped"]
    ), a["dropped"]


def test_summary_saying_unspecified_for_a_stated_fact_is_rejected():
    from app.services.verify import verify_summary

    quotes = ["you are at least 21 years of age", "you are a university student preparing for a career in technology"]
    ok, why = verify_summary(STU1_DRAFTS[1], quotes, quotes, question=STU1_Q)
    assert not ok and "don't specify" in why
    from app.services.verify import _unspecified_contradiction

    # Room type is genuinely absent from the claims: not a contradiction (that answer goes
    # through verify_unspecified_summary).
    assert _unspecified_contradiction(ROOM_DRAFTS[1], [HOTEL_CLAIM[1], HOTEL_CLAIM[0]]) is None
