import re
from pathlib import Path

from app.services.verify import (
    clip_quote_to_support,
    expand_list_span,
    locate,
    omitted_claim_texts,
    relevant_verified_claims,
    summary_covers_question,
    verify,
    verify_summary,
)

ROOT = Path(__file__).resolve().parents[2]
TERMS_PAGE = (ROOT / "kb/official/2026/abw-terms.md").read_text()

PAGE = (
    "To properly coordinate services, all requests must be received by November 14th. "
    "Requests for services received after this date cannot be guaranteed."
)

# Exact live-AWS failure: Nova copied defined-term quotes with single quotes
# while the stored official terms use double quotes.
LIVE_SINGLE_QUOTE_EVIDENCE = (
    "Participants of the Program will receive the following benefits ('Program Benefits'):"
)
STORED_DOUBLE_QUOTE_SPAN = (
    'Participants of the Program will receive the following benefits ("Program Benefits"):'
)


def test_quote_must_be_substring():
    ok, why, span = verify(
        "Requests must be received by November 14th.",
        "all requests must be received by November 14th",
        PAGE,
    )
    assert ok, why
    assert span is not None


def test_claim_number_not_in_quote_is_dropped():
    ok, why, _ = verify(
        "Requests must be received by November 13th.",
        "all requests must be received by November 14th",
        PAGE,
    )
    assert not ok
    assert "13" in why


def test_missing_quote_fails():
    ok, why, _ = verify("Anything", "this quote is not on the page", PAGE)
    assert not ok
    assert "substring" in why or "supported" in why


def test_summary_cannot_invent_counts():
    ok, why = verify_summary("The deadline is November 99.", ["November 14th"])
    assert not ok
    assert "99" in why


def test_summary_ok_when_numbers_in_quotes():
    ok, why = verify_summary("Requests must arrive by November 14th.", ["November 14th"])
    assert ok, why


def test_period_mismatch_is_dropped():
    ok, why, _ = verify(
        "You have 14 years to book a return flight.",
        "All return flights must be scheduled within 14 days following the last day of the Event",
        "All return flights must be scheduled within 14 days following the last day of the Event, with no exceptions allowed.",
    )
    assert not ok
    assert "year" in why


def test_live_aws_single_vs_double_program_benefits_quotes_match():
    """Nova evidence used benefits ('Program Benefits'); stored source uses double quotes."""
    assert STORED_DOUBLE_QUOTE_SPAN in TERMS_PAGE
    assert LIVE_SINGLE_QUOTE_EVIDENCE not in TERMS_PAGE
    ok, why, span = verify(
        "The grant covers Program Benefits including a conference pass, flight, and hotel.",
        LIVE_SINGLE_QUOTE_EVIDENCE,
        TERMS_PAGE,
    )
    assert ok, why
    assert span is not None
    assert locate(LIVE_SINGLE_QUOTE_EVIDENCE, TERMS_PAGE) is not None


def test_curly_quotes_match_stored_straight_double_quotes():
    curly = (
        "Participants of the Program will receive the following benefits (\u201cProgram Benefits\u201d):"
    )
    ok, why, span = verify(
        "Participants receive Program Benefits.",
        curly,
        TERMS_PAGE,
    )
    assert ok, why
    assert span is not None


def test_event_location_single_vs_double_quotes_match():
    ok, why, span = verify(
        "The grant covers a roundtrip flight to the Event Location.",
        "the city of the Event ('Event Location')",
        TERMS_PAGE,
    )
    assert ok, why
    assert span is not None


def test_straight_vs_curly_apostrophe_in_aws_possessive_matches():
    ok, why, span = verify(
        "Some benefits may be determined in AWS's sole discretion.",
        "You may also receive certain benefits from time-to-time as determined in AWS\u2019s sole discretion.",
        TERMS_PAGE,
    )
    assert ok, why
    assert span is not None


def test_altered_program_benefits_wording_still_fails():
    ok, why, _ = verify(
        "The grant covers Program Perks including a conference pass.",
        "Participants of the Program will receive the following benefits ('Program Perks'):",
        TERMS_PAGE,
    )
    assert not ok
    assert "substring" in why or "supported" in why


def test_quote_style_match_does_not_save_changed_number():
    ok, why, _ = verify(
        "The grant covers a roundtrip flight within 99 miles of your address.",
        "Roundtrip flight between an airport near (within 50 miles of) the address you list "
        "in your application and the city of the Event ('Event Location')",
        TERMS_PAGE,
    )
    assert not ok
    assert "99" in why


def test_its_contraction_does_not_match_its_without_apostrophe():
    ok, why, _ = verify(
        "Program benefits are personal.",
        "You may not transfer it's benefits.",
        "You may not transfer its benefits.",
    )
    assert not ok
    assert "substring" in why or "supported" in why


def test_trailing_passage_label_is_stripped_without_dropping_content_words():
    quote = (
        'Participants of the Program will receive the following benefits ("Program Benefits"): (P1)'
    )
    ok, why, span = verify(
        "The grant covers Program Benefits including a conference pass, flight, and hotel.",
        quote,
        TERMS_PAGE,
    )
    assert ok, why
    assert span is not None


LIVE_GRANT03_PASS_QUOTE = (
    'Participants of the Program will receive the following benefits ("Program Benefits"): '
    "- A full conference pass to the Event you applied for"
)
LIVE_GRANT03_SPLICED_FLIGHT = (
    'Participants of the Program will receive the following benefits ("Program Benefits"): '
    "- Roundtrip flight between an airport near (within 50 miles of) the address you list "
    'in your application and the city of the Event ("Event Location");'
)


def test_live_grant03_spliced_flight_quote_still_verifies():
    """ad4808 grant_03: intro glued onto the flight bullet, skipping the pass bullet."""
    ok, why, span = verify(
        "The ABW Grant covers roundtrip flight.",
        LIVE_GRANT03_SPLICED_FLIGHT,
        TERMS_PAGE,
    )
    assert ok, why
    snapped = TERMS_PAGE[span[0] : span[1]]
    assert "Roundtrip flight" in snapped
    assert "Program Perks" not in snapped


def test_live_grant03_pass_quote_expands_through_sibling_bullets():
    ok, why, span = verify(
        "The ABW Grant covers a full conference pass.",
        LIVE_GRANT03_PASS_QUOTE,
        TERMS_PAGE,
    )
    assert ok, why
    snapped = TERMS_PAGE[span[0] : span[1]]
    assert "conference pass" in snapped
    assert "Roundtrip flight" in snapped
    assert "Hotel accommodations" in snapped
    assert "Limitation of Liability" not in snapped


def test_flight_claim_with_pass_only_quote_is_not_verified():
    ok, why, _ = verify(
        "The ABW Grant covers roundtrip flight.",
        "A full conference pass to the Event you applied for",
        TERMS_PAGE,
    )
    assert not ok
    assert "supported" in why or "substring" in why


def test_summary_completeness_keeps_all_in_scope_claims():
    claims = [
        {"text": "The grant covers a full conference pass.", "quote": "A full conference pass to the Event you applied for;"},
        {"text": "The grant covers a roundtrip flight.", "quote": "Roundtrip flight between an airport near the event."},
        {"text": "The grant covers hotel accommodations.", "quote": "Hotel accommodations in Event Location during the Event."},
    ]
    ok, why = summary_covers_question(
        "What does the ABW Grant cover?",
        "The grant covers a full conference pass.",
        claims,
    )
    assert not ok
    assert "omits" in why
    ok, why = summary_covers_question(
        "What does the ABW Grant cover?",
        "The grant covers a full conference pass, a roundtrip flight, and hotel accommodations.",
        claims,
    )
    assert ok, why


def test_flight_only_question_does_not_require_hotel_in_summary():
    claims = [
        {"text": "The grant covers a roundtrip flight.", "quote": "Roundtrip flight between an airport near the event."},
        {"text": "The grant covers hotel accommodations.", "quote": "Hotel accommodations in Event Location during the Event."},
    ]
    ok, why = summary_covers_question(
        "Does the All Builders Welcome Grant pay for airfare?",
        "Yes, the grant covers a roundtrip flight to the event location.",
        claims,
    )
    assert ok, why


def test_live_quote_mismatch_p_only_prefix_and_curly_quotes():
    """Live shape: passage-only [P1] label plus curly defined-term quotes."""
    quote = (
        "[P1] Participants of the Program will receive the following benefits "
        "(\u201cProgram Benefits\u201d):"
    )
    ok, why, span = verify(
        "The grant covers Program Benefits including a conference pass, flight, and hotel.",
        quote,
        TERMS_PAGE,
    )
    assert ok, why
    assert span is not None
    snapped = TERMS_PAGE[span[0] : span[1]]
    assert "Program Benefits" in snapped
    assert locate(quote, TERMS_PAGE) is not None


def test_realistic_nova_quote_variants_still_match_terms():
    """Variants seen when Nova copies Terms evidence with reformatting, not new facts."""
    claim = "The grant covers Program Benefits including a conference pass, flight, and hotel."
    variants = [
        'Participants of the Program will receive the following benefits (Program Benefits):',
        '[P1.U5] Participants of the Program will receive the following benefits ("Program Benefits"):',
        'Section 1.4: Participants of the Program will receive the following benefits ("Program Benefits"):',
        "Participants of the Program will receive the following benefits (**Program Benefits**):",
        '- Participants of the Program will receive the following benefits ("Program Benefits"):',
        "Participants of the Program will receive the following benefits ( “Program Benefits” ) :",
    ]
    for quote in variants:
        ok, why, span = verify(claim, quote, TERMS_PAGE)
        assert ok, (quote, why)
        assert span is not None
        snapped = TERMS_PAGE[span[0] : span[1]]
        assert "Program Benefits" in snapped


def test_paraphrase_is_not_treated_as_evidence():
    ok, why, _ = verify(
        "The grant covers a conference pass.",
        "The program pays for a ticket, airfare, and lodging for attendees.",
        TERMS_PAGE,
    )
    assert not ok
    assert "substring" in why or "supported" in why


def test_long_quote_missing_and_before_hotel_still_matches():
    """F2: 350-char multi-bullet quote omitted the connective 'and' before hotel."""
    quote = (
        "Participants of the Program will receive the following benefits ('Program Benefits'): "
        "- A full conference pass to the Event you applied for; "
        "- Roundtrip flight between an airport near (within 50 miles of) the address you list "
        "in your application and the city of the Event ('Event Location'); "
        "- Hotel accommodations in Event Location during the Event."
    )
    assert "; and" in TERMS_PAGE
    assert "; - Hotel" in quote or "; - Hotel" in quote.replace("\n", " ")
    ok, why, span = verify(
        "The grant covers hotel accommodations in Event Location during the Event.",
        quote,
        TERMS_PAGE,
    )
    assert ok, why
    snapped = TERMS_PAGE[span[0] : span[1]]
    assert "and" in snapped
    assert "Hotel accommodations" in snapped


def test_flex_match_does_not_save_changed_benefit_wording():
    quote = (
        "Participants of the Program will receive the following benefits ('Program Perks'): "
        "- A full conference pass to the Event you applied for; "
        "- Roundtrip flight between an airport near (within 50 miles of) the address you list "
        "in your application and the city of the Event ('Event Location'); "
        "- Hotel accommodations in Event Location during the Event."
    )
    ok, why, _ = verify("The grant covers Program Perks.", quote, TERMS_PAGE)
    assert not ok
    assert "substring" in why or "supported" in why


def test_summary_drops_hotel_when_hotel_claim_did_not_survive():
    ok, why = verify_summary(
        "The All Builders Welcome Grant covers a full conference pass, roundtrip flight, and hotel accommodations.",
        [
            "A full conference pass to the Event you applied for;",
            'Roundtrip flight between an airport near (within 50 miles of) the address you list in your application and the city of the Event ("Event Location");',
        ],
        [
            "The grant covers a full conference pass.",
            "The grant covers a roundtrip flight.",
        ],
    )
    assert not ok
    assert "hotel" in why.lower()


def test_summary_keeps_hotel_when_verified_quote_has_hotel():
    ok, why = verify_summary(
        "The grant covers a conference pass, roundtrip flight, and hotel accommodations.",
        [
            "A full conference pass to the Event you applied for;",
            'Roundtrip flight between an airport near (within 50 miles of) the address you list in your application and the city of the Event ("Event Location");',
            "Hotel accommodations in Event Location during the Event.",
        ],
        [
            "The grant covers a conference pass.",
            "The grant covers a roundtrip flight.",
            "The grant covers hotel accommodations.",
        ],
    )
    assert ok, why


def test_evidence_page_unions_retrieved_chunks_when_local_doc_missing():
    from app.services.ask import evidence_page

    intro = "These Terms govern participation in the Program."
    benefits = 'Participants of the Program will receive the following benefits ("Program Benefits"):'
    class EmptyDoc:
        def document_text(self, doc_id):
            return ""

    page = evidence_page(
        {"doc_id": "terms", "text": intro},
        [
            {"doc_id": "terms", "text": intro},
            {"doc_id": "terms", "text": benefits},
        ],
        EmptyDoc(),
    )
    ok_first_only, _, _ = verify(
        "The grant covers Program Benefits.",
        "benefits ('Program Benefits')",
        intro,
    )
    assert not ok_first_only
    ok, why, _ = verify(
        "The grant covers Program Benefits.",
        "benefits ('Program Benefits')",
        page,
    )
    assert ok, why


def test_event_year_in_claim_is_allowed_when_page_has_the_year():
    page = "re:Invent 2026\nNov. 30 – Dec. 4 | Las Vegas, NV"
    ok, why, _ = verify(
        "re:Invent 2026 is from Nov. 30 to Dec. 4.",
        "Nov. 30 – Dec. 4 | Las Vegas, NV",
        page,
    )
    assert ok, why


def test_event_year_metadata_satisfies_year_token_when_doc_text_empty():
    from app.services.ask import evidence_page

    class EmptyDoc:
        def document_text(self, doc_id):
            return ""

    page = evidence_page(
        {
            "doc_id": "know",
            "text": "Nov. 30 – Dec. 4 | Las Vegas, NV",
            "title": "Know before you go — re:Invent 2026",
            "event_year": 2026,
        },
        [],
        EmptyDoc(),
    )
    ok, why, _ = verify(
        "re:Invent 2026 is from Nov. 30 to Dec. 4.",
        "Nov. 30 – Dec. 4 | Las Vegas, NV",
        page,
    )
    assert ok, why


def test_year_not_on_the_page_is_still_dropped():
    page = "Nov. 30 – Dec. 4 | Las Vegas, NV"
    ok, why, _ = verify(
        "re:Invent 2099 is from Nov. 30 to Dec. 4.",
        "Nov. 30 – Dec. 4 | Las Vegas, NV",
        page,
    )
    assert not ok
    assert "2099" in why


def test_nov13_claim_with_year_matches_quote_that_omits_year():
    page = (
        "Accessibility services at re:Invent 2026. "
        "The deadline for all requests is Nov. 13, 2026. Requests received after this date cannot be guaranteed."
    )
    ok, why, _ = verify(
        "The deadline for all requests is Nov. 13, 2026.",
        "The deadline for all requests is Nov. 13",
        page,
    )
    assert ok, why


def test_students_are_not_entailed_by_application_period_sentence():
    ok, why, _ = verify(
        "Students can apply for the All Builders Welcome Grant.",
        "Applications for the Program must be received during the Application Period of an Event",
        TERMS_PAGE,
        question="Can students apply for the All Builders Welcome Grant?",
    )
    assert not ok


def test_attendees_question_echo_does_not_drop_benefits_claim():
    """Live 257e811 grant_04/07/13: Nova echoed 'attendees'/'coverage' into a supported benefits claim."""
    quote = (
        'Participants of the Program will receive the following benefits ("Program Benefits"): '
        "- A full conference pass to the Event you applied for"
    )
    ok, why, _ = verify(
        "The grant covers a full conference pass, roundtrip flight, and hotel accommodations for attendees.",
        quote,
        TERMS_PAGE,
        question="What does ABW grant coverage include for attendees?",
    )
    assert ok, why


def test_package_question_echo_does_not_drop_benefits_claim():
    """Live 257e811 grant_09: 'package'/'provide' in the question must not fail entailment."""
    quote = (
        'Participants of the Program will receive the following benefits ("Program Benefits"): '
        "- A full conference pass to the Event you applied for"
    )
    ok, why, _ = verify(
        "The All Builders Welcome Grant package provides a full conference pass, roundtrip flight, and hotel.",
        quote,
        TERMS_PAGE,
        question="What package does the All Builders Welcome Grant provide?",
    )
    assert ok, why


def test_hotel_suite_negative_is_not_entailed_by_hotel_bullet():
    ok, why, _ = verify(
        "You cannot choose your own hotel room type or upgrade to a suite with the grant.",
        "Hotel accommodations in Event Location during the Event",
        TERMS_PAGE,
    )
    assert not ok


def test_summary_question_echo_accommodation_is_not_a_leak():
    """Live 30d420e access_02: question verbs must not empty a Nov. 13 summary."""
    ok, why = verify_summary(
        "Accessibility accommodation requests need to be submitted by Nov. 13, 2026.",
        ["The deadline for all requests is Nov. 13, 2026."],
        ["The deadline for all requests is Nov. 13, 2026."],
        question="When do accessibility accommodation requests need to be submitted?",
    )
    assert ok, why


def test_clip_keeps_november_14_after_accessibility_service_list():
    faq = (ROOT / "kb/official/2026/faqs-accessibility.md").read_text()
    clipped = clip_quote_to_support("all requests must be received by November 14th", faq)
    assert re.search(r"November 14", clipped, re.I)
    assert "####" not in clipped
    assert len(clipped) < 400


def test_summary_does_not_keep_question_term_students_without_quote():
    ok, why = verify_summary(
        "Students can reapply for the All Builders Welcome Grant if not selected for a cohort.",
        ["If you are not selected for a cohort of the Program, you may reapply as long as you are eligible"],
        ["If you are not selected for a cohort of the Program, you may reapply as long as you are eligible"],
        question="Can students apply for the All Builders Welcome Grant?",
    )
    assert not ok
    assert "student" in why.lower()


def test_eligibility_d_quote_expands_to_earlier_list_items():
    from app.services.verify import align_quote

    quote = (
        "D. you have not previously accepted a grant to the Event you are applying for "
        "(e.g., from the We Power Tech or All Builders Welcome programs);"
    )
    snapped, span = align_quote(quote, TERMS_PAGE)
    assert snapped
    assert "21 years of age" in snapped
    assert "university student" in snapped or "first 5 years" in snapped
    assert "Limitation of Liability" not in snapped
    clipped = clip_quote_to_support("You must be at least 21 years of age.", snapped)
    assert "21" in clipped
    assert len(clipped) <= 600


def test_clip_quote_drops_heading_dump_to_supporting_sentence():
    dump = (
        "Contact customer support (awsreinvent-support@amazon.com) to coordinate. "
        "The deadline for all requests is Nov. 13, 2026. Requests received after this date cannot be guaranteed. "
        "#### CART (Communication Access Realtime Translation) CART services are available by request. "
        "#### Accessible transportation Accessible transportation across the re:Invent campus will be available."
    )
    clipped = clip_quote_to_support(
        "The deadline for all requests is Nov. 13, 2026.",
        dump,
    )
    assert "Nov. 13" in clipped
    assert "####" not in clipped
    assert len(clipped) < 400


def test_summary_allows_question_echoed_period_day():
    ok, why = verify_summary(
        "The last day to request ASL services is Nov. 13, 2026.",
        ["The deadline for all requests is Nov. 13, 2026."],
        ["The deadline for all requests is Nov. 13, 2026."],
        question="Last day to request ASL or accessibility services?",
    )
    assert ok, why


def test_summary_allows_question_echoed_period_year_for_reapply():
    quote = (
        "If you are not selected for a cohort of the Program, you may reapply "
        "for subsequent cohorts of the Program as long as you are eligible."
    )
    ok, why = verify_summary(
        "If you were not selected last year, you may reapply for subsequent cohorts as long as you are eligible.",
        [quote],
        [quote],
        question="If I was rejected last year, can I try ABW again?",
    )
    assert ok, why


def test_summary_eligibility_framing_word_is_not_a_leak():
    quotes = [
        "you are at least 21 years of age; B.",
        "you are within the first 5 years of your technology career, or you are a university student preparing for a career in technology.",
    ]
    ok, why = verify_summary(
        "ABW eligibility requires you to be at least 21 years of age and a university student preparing for a career in technology or within the first 5 years of your technology career.",
        quotes,
        quotes,
        question="What are the ABW eligibility requirements?",
    )
    assert ok, why


def test_summary_still_rejects_invented_period_not_in_question_or_claims():
    ok, why = verify_summary(
        "Requests must arrive within one week of registration.",
        ["The deadline for all requests is Nov. 13, 2026."],
        ["The deadline for all requests is Nov. 13, 2026."],
        question="When must accessibility requests arrive?",
    )
    assert not ok
    assert "period" in why or "week" in why or "count" in why


def test_eligibility_shared_tech_career_does_not_cover_constraints():
    """Weak tech/career prose must not satisfy age/student/employee eligibility claims."""
    claims = [
        {
            "text": "you are at least 21 years of age; B.",
            "quote": "you are at least 21 years of age; B.",
        },
        {
            "text": "you are a university student preparing for a career in technology.",
            "quote": "you are a university student preparing for a career in technology.",
        },
        {
            "text": "You may not be an employee of AWS or its affiliates.",
            "quote": "You may not be an employee of AWS or its affiliates.",
        },
    ]
    q = "What are the ABW eligibility requirements?"
    ok, why = summary_covers_question(
        q,
        "Applicants should be preparing for a career in technology.",
        claims,
    )
    assert not ok
    omitted = omitted_claim_texts(q, "Applicants should be preparing for a career in technology.", claims)
    assert any("21" in o for o in omitted)
    assert any("employee" in o.lower() for o in omitted)


def test_eligibility_missing_non_age_constraint_is_omitted():
    claims = [
        {
            "text": "you are at least 21 years of age; B.",
            "quote": "you are at least 21 years of age; B.",
        },
        {
            "text": "You may not be an employee of AWS or its affiliates.",
            "quote": "You may not be an employee of AWS or its affiliates.",
        },
    ]
    q = "What are the ABW eligibility requirements?"
    summary = "Applicants must be at least 21 years of age."
    ok, why = summary_covers_question(q, summary, claims)
    assert not ok
    omitted = omitted_claim_texts(q, summary, claims)
    assert any("employee" in o.lower() for o in omitted)


def test_student_apply_does_not_require_barriers_or_meta_terms():
    claims = [
        {
            "text": "university students preparing for a role in tech",
            "quote": "university students preparing for a role in tech",
        },
        {
            "text": "you are at least 21 years of age; B.",
            "quote": "you are at least 21 years of age; B.",
        },
        {
            "text": "you have faced unique barriers or disadvantages while pursuing opportunities",
            "quote": "you have faced unique barriers or disadvantages while pursuing opportunities",
        },
        {
            "text": "For full eligibility details, please review the Terms and Conditions.",
            "quote": "For full eligibility details, please review the Terms and Conditions.",
        },
    ]
    q = "Can students apply for the All Builders Welcome Grant?"
    summary = (
        "Students can apply if they are preparing for a career in technology. "
        "Applicants must be at least 21 years of age."
    )
    scoped = relevant_verified_claims(q, claims)
    blobs = " ".join((c.get("text") or "") for c in scoped).lower()
    assert "barriers" not in blobs
    assert "please review the terms" not in blobs
    ok, why = summary_covers_question(q, summary, claims)
    assert ok, why


def test_scoped_airfare_question_still_ignores_hotel_claim():
    claims = [
        {
            "text": "The grant covers a roundtrip flight.",
            "quote": "Roundtrip flight between an airport near the event.",
        },
        {
            "text": "The grant covers hotel accommodations.",
            "quote": "Hotel accommodations in Event Location during the Event.",
        },
    ]
    ok, why = summary_covers_question(
        "Does the All Builders Welcome Grant pay for airfare?",
        "Yes, the grant covers a roundtrip flight to the event location.",
        claims,
    )
    assert ok, why
