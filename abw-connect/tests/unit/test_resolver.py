from app.services.resolver import resolve, slot_of


FAQ = dict(
    id="faq-a11y",
    doc_id="official/2026/faqs-accessibility",
    title="re:Invent 2026 FAQs — Accessibility services",
    section="Accessibility Services",
    source_type="official",
    event_year=2026,
    text="To properly coordinate services, all requests must be received by November 14th. Requests for services received after this date cannot be guaranteed.",
)
A11Y = dict(
    id="page-a11y",
    doc_id="official/2026/accessibility-services",
    title="Accessibility services at re:Invent 2026",
    section="How to request a service",
    source_type="official",
    event_year=2026,
    text="The following services are only available by advance request. The deadline for all requests is Nov. 13, 2026. Requests received after this date cannot be guaranteed.",
)
ALUMNI = dict(
    id="alumni-age",
    doc_id="alumni/2023-newcomers-guide",
    title="Alumni experience",
    section="Personal experience",
    source_type="alumni_experience",
    event_year=2023,
    text="Be at least 18 years old to apply for the grant. This is personal experience.",
)
TERMS = dict(
    id="terms-age",
    doc_id="official/2026/abw-terms",
    title="ABW Terms",
    section="1.1 Participation",
    source_type="official",
    event_year=2026,
    text="A. you are at least 21 years of age; B. you are within the first 5 years of your technology career.",
)


def test_slot_detects_accessibility_deadline():
    assert slot_of(FAQ["text"]) == "accessibility_request_deadline"
    assert slot_of(A11Y["text"]) == "accessibility_request_deadline"


def test_official_nov_13_vs_14_is_unresolved_contradiction():
    res = resolve([FAQ, A11Y], "accessibility")
    assert res["outcome"] == "unresolved_contradiction"
    assert not res["suppressed"]
    kinds = {p["outcome"] for p in res["pairs"]}
    assert "unresolved_contradiction" in kinds


def test_alumni_never_overrides_official_age():
    res = resolve([TERMS, ALUMNI], "eligibility")
    assert ALUMNI["id"] in res["suppressed"]
    assert TERMS["id"] not in res["suppressed"]
    assert res["outcome"] in ("compatible", "official_over_alumni")
    assert any(p["outcome"] == "official_over_alumni" for p in res["pairs"])


def test_compatible_when_same_date():
    twin = dict(A11Y, id="twin", doc_id="other-official", text=FAQ["text"])
    res = resolve([FAQ, twin], "accessibility")
    assert res["outcome"] == "compatible"


AGENDA = dict(
    id="agenda",
    doc_id="official/2026/agenda",
    title="re:Invent 2026 Agenda",
    section="Agenda",
    source_type="official",
    event_year=2026,
    text=(
        "Monday, November 30. Friday, December 4. "
        "Sessions are held across all venues. Allow additional time for travel between properties."
    ),
)
FAQ_ABOUT = dict(
    id="faq-about",
    doc_id="official/2026/faqs-about",
    title="re:Invent 2026 FAQs — About the event",
    section="About AWS re:Invent",
    source_type="official",
    event_year=2026,
    text="Nov. 30 – Dec. 4 in Las Vegas, NV. The conference takes place across multiple venues.",
)
KNOW = dict(
    id="know",
    doc_id="official/2026/know-before-you-go",
    title="Know before you go",
    section="Plan your schedule",
    source_type="official",
    event_year=2026,
    text="Sessions run across multiple Las Vegas properties, so check where yours are held and allow 30 to 45 minutes between venues.",
)
VENUE_Q = "How much time should I leave between re:Invent venues?"


def test_venue_time_question_does_not_flag_event_week_dates():
    res = resolve([AGENDA, FAQ_ABOUT, KNOW], "travel", question=VENUE_Q)
    assert res["outcome"] != "unresolved_contradiction"
    assert not any(p.get("outcome") == "unresolved_contradiction" for p in res["pairs"])


def test_venue_time_question_variants_skip_date_clash():
    for q in (
        VENUE_Q,
        "how long between properties?",
        "travel time between venues",
        "How much time should I leave between re:Invent venues?",
    ):
        res = resolve([AGENDA, FAQ_ABOUT], "travel", question=q)
        assert res["outcome"] != "unresolved_contradiction", q


def test_unslotted_agenda_dates_are_not_a_contradiction():
    res = resolve([AGENDA, FAQ_ABOUT], "travel")
    assert res["outcome"] != "unresolved_contradiction"


def test_accessibility_deadline_still_conflicts_next_to_agenda_dates():
    res = resolve([FAQ, A11Y, AGENDA], "accessibility", question="When is the deadline to request accessibility accommodations?")
    assert res["outcome"] == "unresolved_contradiction"


SESSIONS = dict(
    id="sessions",
    doc_id="official/2026/faqs-sessions",
    title="re:Invent 2026 FAQs — Sessions",
    section="Reserved seating",
    source_type="official",
    event_year=2026,
    text="If you reserve a seat, arrive within ten minutes of the start time or the seat may be released.",
)


def test_unslotted_session_minutes_do_not_conflict_with_travel_buffer():
    q = "When moving between conference venues, what buffer does the guidance recommend?"
    res = resolve([KNOW, SESSIONS], "travel", question=q)
    assert res["outcome"] != "unresolved_contradiction"
    assert not any(p.get("outcome") == "unresolved_contradiction" for p in res["pairs"])


def test_venue_paraphrases_do_not_inherit_accessibility_deadline_conflict():
    travel = dict(
        KNOW,
        id="travel-app",
        doc_id="official/2026/faqs-at-conference",
        text="On-site, use interactive maps and turn-by-turn wayfinding to get between venues.",
    )
    for q in (
        "When moving between conference venues, what buffer does the guidance recommend?",
        "What do the re:Invent travel instructions say about getting from one venue to another?",
        "How should I plan transportation between re:Invent properties?",
    ):
        res = resolve([FAQ, A11Y, travel], "travel", question=q)
        assert res["outcome"] != "unresolved_contradiction", q
        assert not any(p.get("outcome") == "unresolved_contradiction" for p in res["pairs"]), q


def test_campus_and_transit_paraphrases_are_duration_questions():
    from app.services.resolver import _DURATION_QUESTION, _question_skips_date_clash

    for q in (
        "Transit buffer between re:Invent campuses?",
        "Any guidance on getting across the re:Invent campus?",
        "How many minutes between venues should I plan?",
    ):
        assert _DURATION_QUESTION.search(q), q
        assert _question_skips_date_clash(q)


def test_accessibility_arrive_cutoff_slot():
    from app.services.resolver import slot_of

    for q in (
        "When must accessibility requests arrive?",
        "Last day to request ASL or accessibility services?",
        "Accessibility services cutoff date for re:Invent 2026?",
    ):
        assert slot_of(q) == "accessibility_request_deadline", q
