from app.services.rewrite import heuristic, rewrite
from app.services.smalltalk import classify, refusal_reply, task_label


def test_greeting():
    assert classify("thanks!") == "greeting"
    assert classify("hello") == "greeting"


def test_task_request_email():
    assert classify("can you write an email for me") == "task_request"
    assert "draft emails" in task_label("can you write an email for me")


def test_in_domain_question_not_smalltalk():
    assert classify("Who is eligible for the ABW grant?") is None


def test_off_topic_without_domain_vocab():
    assert classify("What's the best pizza in town?") == "maybe_off_topic"


def test_heuristic_follow_up():
    hist = [dict(standalone="How are ABW grant travel arrangements booked?", answer="Through the AWS travel agency.")]
    sq, tt = heuristic("how many days?", hist)
    assert tt == "follow_up"
    assert "about:" in sq


def test_heuristic_new_topic():
    hist = [dict(standalone="How are ABW grant travel arrangements booked?", answer="...")]
    sq, tt = heuristic("When is re:Invent 2026?", hist)
    assert tt == "new_topic"
    assert sq == "When is re:Invent 2026?"


def test_rewrite_first_turn_skips():
    sq, tt, info = rewrite("Who is eligible?", [], {"role": "grantee"}, use_llm=False)
    assert tt == "new_topic"
    assert info["method"] == "first_turn"


def test_refusal_does_not_use_empty_here_is_what_i_can_answer():
    msg, sugg = refusal_reply("no_verified_claim", ["eligibility"], lambda q: True, question="Can students apply?")
    assert "Here's what I can answer:" not in msg
    assert "I won't guess" in msg or "won't" in msg
    if sugg:
        assert "Related questions I can try:" in msg
    msg_empty, sugg_empty = refusal_reply("conflict_incomplete", [], lambda q: False, question="x")
    if not sugg_empty:
        assert "Here's what I can answer:" not in msg_empty
        assert "Related questions I can try:" not in msg_empty
    assert "won't pick one" in msg_empty
