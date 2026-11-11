from app.services.present import (
    conflict_both_sides_supported,
    conflict_unknown_kind,
    conflict_value_tokens,
    conflicting_date_phrases,
    dates_from_conflict_records,
    is_canned_conflict_lead,
    llm_answer_is_dump,
    verify_conflict_summary,
)


C13 = dict(
    text="The deadline for all requests is Nov. 13, 2026.",
    quote="The deadline for all requests is Nov. 13, 2026.",
    alumni_experience=False,
    citation={"doc_id": "official/2026/accessibility-services"},
)
C14 = dict(
    text="All requests must be received by November 14th.",
    quote="all requests must be received by November 14th.",
    alumni_experience=False,
    citation={"doc_id": "official/2026/faqs-accessibility"},
)
DEC4 = dict(
    text="The event runs through Friday, December 4.",
    quote="Friday, December 4",
    alumni_experience=False,
    citation={"doc_id": "official/2026/agenda"},
)

A11Y_SRC = dict(
    id="page-a11y",
    doc_id="official/2026/accessibility-services",
    title="Accessibility services at re:Invent 2026",
    section="How to request a service",
    text=(
        "The following services are only available by advance request. "
        "The deadline for all requests is Nov. 13, 2026. "
        "Requests received after this date cannot be guaranteed."
    ),
)
FAQ_SRC = dict(
    id="faq-a11y",
    doc_id="official/2026/faqs-accessibility",
    title="re:Invent 2026 FAQs — Accessibility services",
    section="What accessibility services will be available at re:Invent?",
    text=(
        "To properly coordinate services, all requests must be received by November 14th. "
        "Requests for services received after this date cannot be guaranteed."
    ),
)
AGENDA_SRC = dict(
    id="agenda",
    doc_id="official/2026/agenda",
    title="re:Invent 2026 Agenda",
    section="Agenda",
    text="Friday, December 4",
)

PAIRS = [
    dict(
        outcome="unresolved_contradiction",
        a="page-a11y",
        b="faq-a11y",
        clash=[(("date", 11, 13, 2026), ("date", 11, 14, None))],
    )
]
BY_ID = {A11Y_SRC["id"]: A11Y_SRC, FAQ_SRC["id"]: FAQ_SRC, AGENDA_SRC["id"]: AGENDA_SRC}

CANNED = (
    "The official sources disagree: one says Nov. 13, 2026 and the other says November 14th. "
    "Please confirm with AWS event support before relying on either date."
)
CANNED_FALLBACK = (
    "The official sources disagree and neither overrides the other. "
    "Please confirm with AWS event support before relying on either value."
)


def test_canned_conflict_templates_are_detected():
    assert is_canned_conflict_lead(CANNED)
    assert is_canned_conflict_lead(CANNED_FALLBACK)
    assert not is_canned_conflict_lead(
        "Official pages list two different request-by dates: Nov. 13, 2026 and November 14th."
    )


def test_conflict_validator_accepts_paraphrases_with_both_dates():
    paraphrases = [
        "Official pages list two different request-by dates: Nov. 13, 2026 and November 14th. Confirm which applies.",
        "One source says requests are due Nov. 13, 2026; another says November 14th. I cannot tell which governs.",
        "There is a conflict: November 14th versus Nov. 13, 2026.",
    ]
    for s in paraphrases:
        ok, why = verify_conflict_summary(s, [C13, C14], PAIRS, BY_ID)
        assert ok, (s, why)
        assert not is_canned_conflict_lead(s)


def test_conflict_validator_rejects_onesided_canned_and_winner():
    ok, why = verify_conflict_summary("The deadline for all requests is Nov. 13, 2026.", [C13, C14], PAIRS, BY_ID)
    assert not ok
    assert "13" in why or "omits" in why or "uncertainty" in why
    ok, why = verify_conflict_summary(CANNED, [C13, C14], PAIRS, BY_ID)
    assert not ok
    assert "canned" in why
    ok, _ = verify_conflict_summary(CANNED_FALLBACK, [C13, C14], PAIRS, BY_ID)
    assert not ok


def test_conflict_validator_does_not_require_neither_overrides():
    s = "Accessibility docs differ: Nov. 13, 2026 on one page and November 14th on another."
    ok, why = verify_conflict_summary(s, [C13, C14], PAIRS, BY_ID)
    assert ok, why
    assert "neither overrides" not in s.lower()


def test_dates_from_conflict_records_ignore_agenda_december_4():
    phrases = dates_from_conflict_records([C13, DEC4], PAIRS, BY_ID)
    blob = " ".join(phrases)
    assert "13" in blob and "14" in blob
    assert "December" not in blob
    assert conflict_both_sides_supported([C13, C14], PAIRS, BY_ID)
    assert not conflict_both_sides_supported([C13, DEC4], PAIRS, BY_ID)


def test_dates_from_conflict_records_order_is_by_day_not_claim_order():
    a = dates_from_conflict_records([C14, C13], PAIRS, BY_ID)
    b = dates_from_conflict_records([C13, C14], PAIRS, BY_ID)
    assert a == b
    assert a[0].find("13") >= 0 or "13" in a[0]


def test_conflicting_phrases_are_distinct_days():
    phrases = conflicting_date_phrases([C13, C14, dict(C13)])
    assert len(phrases) == 2


def test_conflict_records_ignore_nov_29_start_date():
    a11y = dict(
        A11Y_SRC,
        text=(
            A11Y_SRC["text"]
            + " Requests will be accepted starting on Sunday, Nov. 29. "
            + "The concierge phone number will be available at a later date."
        ),
    )
    nov29 = dict(
        text="Requests will be accepted starting on Sunday, Nov. 29.",
        quote="Requests will be accepted starting on Sunday, Nov. 29.",
        alumni_experience=False,
        citation={"doc_id": "official/2026/accessibility-services"},
    )
    pairs = [
        dict(
            outcome="unresolved_contradiction",
            a="page-a11y",
            b="faq-a11y",
            clash=[
                (("date", 11, 13, 2026), ("date", 11, 14, None)),
                (("date", 11, 13, 2026), ("date", 11, 29, None)),
            ],
        )
    ]
    phrases = dates_from_conflict_records(
        [C13, nov29, DEC4],
        pairs,
        {**BY_ID, "page-a11y": a11y},
    )
    blob = " ".join(phrases)
    assert "13" in blob and "14" in blob
    assert "29" not in blob
    assert "December" not in blob


def test_conflict_validator_money_and_age_are_generic():
    money_claims = [
        dict(text="The fee is $50.", quote="The fee is $50.", citation={"doc_id": "a"}),
        dict(text="The fee is $100.", quote="The fee is $100.", citation={"doc_id": "b"}),
    ]
    money_pairs = [
        dict(
            outcome="unresolved_contradiction",
            a="a",
            b="b",
            clash=[(("money", 50), ("money", 100))],
        )
    ]
    chunks = {
        "a": dict(id="a", doc_id="a", text="The fee is $50."),
        "b": dict(id="b", doc_id="b", text="The fee is $100."),
    }
    ok, why = verify_conflict_summary(
        "Official pages disagree on the fee: $50 versus $100.",
        money_claims,
        money_pairs,
        chunks,
    )
    assert ok, why
    toks = conflict_value_tokens(money_claims, money_pairs, chunks)
    assert "50" in toks and "100" in toks
    ok, _ = verify_conflict_summary("The fee is $50.", money_claims, money_pairs, chunks)
    assert not ok

    age_claims = [
        dict(text="Applicants must be 18.", quote="must be 18", citation={"doc_id": "a"}),
        dict(text="Applicants must be 21.", quote="must be 21", citation={"doc_id": "b"}),
    ]
    age_pairs = [
        dict(
            outcome="unresolved_contradiction",
            a="a",
            b="b",
            clash=[(("age", 18), ("age", 21))],
        )
    ]
    age_chunks = {
        "a": dict(id="a", doc_id="a", text="Applicants must be 18."),
        "b": dict(id="b", doc_id="b", text="Applicants must be 21."),
    }
    ok, why = verify_conflict_summary(
        "One page says 18 and another says 21; I cannot tell which age governs.",
        age_claims,
        age_pairs,
        age_chunks,
    )
    assert ok, why


def test_unknown_conflict_kind_is_flagged():
    pairs = [
        dict(
            outcome="unresolved_contradiction",
            clash=[(("slot", "foo"), ("slot", "bar"))],
        )
    ]
    assert conflict_unknown_kind(pairs)
    assert not conflict_unknown_kind(PAIRS)


def test_short_llm_answer_is_not_a_dump():
    assert not llm_answer_is_dump(
        "The grant covers a full conference pass, roundtrip airfare, and hotel accommodation."
    )
    assert not llm_answer_is_dump(
        "Allow 30 to 45 minutes between venues and extra time for travel between properties."
    )


def test_terms_passage_is_a_dump():
    dump = (
        "D. you have not previously accepted a grant to the Event you are applying for; "
        "E. you are not an employee, intern, independent contractor, officer, director; "
        "Limitation of Liability NEITHER WE NOR ANY OF OUR AFFILIATES WILL BE LIABLE. "
        "Section 1.7 Termination Either you or we may terminate your participation."
    )
    assert llm_answer_is_dump(dump)
    assert llm_answer_is_dump("x" * 700)
