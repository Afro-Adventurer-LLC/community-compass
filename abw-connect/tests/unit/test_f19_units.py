"""F19 unit checks on real flattened Bedrock chunks (tests/fixtures/live_d55b08d)."""
from __future__ import annotations

import json

from app.services.ask import _atomic_units
from app.services.verify import relevant_verified_claims, travel_minute_values
from tests.integration.live_replay import FIXTURE

_ROWS = [r for rows in json.loads(FIXTURE.read_text()).values() for r in rows]


def _chunk(doc: str, needle: str) -> str:
    for r in _ROWS:
        if r["doc_id"].endswith(doc) and needle in r["text"]:
            return r["text"]
    raise AssertionError(f"fixture lacks {doc} chunk with {needle!r}")


def test_flattened_program_benefits_list_yields_every_bullet():
    t = _chunk("abw-terms.md", "Hotel accommodations in Event Location during the Event")
    assert "\n" not in t  # Bedrock flattening, as in the deployed Lambda
    units = _atomic_units(t)
    assert all(len(u) <= 400 for u in units)
    assert "- Hotel accommodations in Event Location during the Event." in units
    assert any(u.startswith("- A full conference pass to the Event you applied for") for u in units)
    assert any(u.startswith("- Roundtrip flight between an airport near") for u in units)


def test_flattened_heading_sentence_with_travel_minutes_is_a_unit():
    t = _chunk("know-before-you-go.md", "30 to 45 minutes")
    hits = [u for u in _atomic_units(t) if "30 to 45 minutes" in u]
    assert hits and hits[0] in t and not hits[0].startswith("#")


def test_travel_minutes_are_travel_not_seat_release():
    assert travel_minute_values(
        "Sessions run across multiple Las Vegas properties, so check where yours are held and allow 30 to 45 minutes between venues."
    ) == {"30", "45"}
    assert travel_minute_values(
        "You must arrive at the room at least ten minutes prior to the session start time or your seat will be released."
    ) == set()
    assert travel_minute_values("Reserved seating opens 15 minutes before the session.") == set()


def test_reapply_scoping_only_when_question_is_not_about_reapplying():
    reapply = dict(
        text="If you are not selected for a cohort of the Program, you may reapply for subsequent cohorts.",
        quote="If you are not selected for a cohort of the Program, you may reapply for subsequent cohorts of the Program as long as you are eligible",
    )
    age = dict(text="you are at least 21 years of age", quote="you are at least 21 years of age")
    reqs = relevant_verified_claims("What are the ABW eligibility requirements?", [reapply, age])
    assert age in reqs and reapply not in reqs
    asked = relevant_verified_claims("Who is eligible to reapply for ABW?", [reapply, age])
    assert reapply in asked
