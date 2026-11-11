from app.services.ask import _lexical_support


class _Hit:
    def __init__(self, text, score=0.8):
        self.text = text
        self.score = score


TERMS_SNIPPET = (
    'Participants of the Program will receive the following benefits ("Program Benefits"): '
    "A full conference pass to the Event you applied for; "
    "Roundtrip flight between an airport near (within 50 miles of) the address you list "
    'in your application and the city of the Event ("Event Location"); and '
    "Hotel accommodations in Event Location during the Event."
)


def test_natural_grant_paraphrases_are_supported():
    hits = [_Hit(TERMS_SNIPPET)]
    for q in (
        "What's included in the ABW grant?",
        "Does the All Builders Welcome Grant pay for airfare and lodging?",
        "Will ABW cover my flight and hotel?",
        "What will I receive if I'm selected for the ABW grant?",
        "Please tell me: What does the All Builders Welcome Grant cover?",
        "Can you summarize ABW grant coverage?",
        "What does the grant cover for re:Invent?",
        "What is included when someone receives an ABW grant?",
        "List ABW Grant inclusions for re:Invent attendees.",
        "Can you outline the ABW grant package components?",
        "Which costs does the ABW grant pay?",
        "Does ABW cover airfare, lodging, and a conference badge?",
    ):
        assert _lexical_support(q, hits), q


def test_pizza_is_not_supported_by_grant_terms_hits():
    hits = [_Hit(TERMS_SNIPPET)]
    assert not _lexical_support("What's the best pizza topping?", hits)


def test_undergrad_qualify_paraphrase_is_supported(retriever):
    from app.services.ask import _lexical_support, _top_up_hits

    q = "Do undergrads qualify for All Builders Welcome?"
    hits = retriever.retrieve(q, event_year=2026, include_alumni=True, k=8)
    hits = _top_up_hits(retriever, q, hits, 2026, True)
    assert hits
    assert _lexical_support(q, hits)
