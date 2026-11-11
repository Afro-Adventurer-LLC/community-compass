from app.services.store import MemoryStore


def test_health_mock_mode(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mock"] is True
    assert body["documents"] >= 1
    assert body["retriever"] == "local"
    assert body.get("knowledge_base") is False
    assert "git_sha" in body


def test_health_reports_git_sha_from_env(client, monkeypatch):
    monkeypatch.setenv("ABW_GIT_SHA", "17b43c7972cfb88a357070e76284a735a5f344d6")
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["git_sha"] == "17b43c7972cfb88a357070e76284a735a5f344d6"


def test_health_ignores_non_hex_git_sha(client, monkeypatch):
    monkeypatch.setenv("ABW_GIT_SHA", "not-a-secret-but-not-hex")
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["git_sha"] is None


def test_chat_answers_eligibility(client):
    r = client.post("/api/chat", json={"question": "Who is eligible for the All Builders Welcome Grant?", "mode": "extractive"})
    assert r.status_code == 200
    a = r.json()
    assert a["kind"] == "answer"
    assert a["refused"] is False
    blob = " ".join(c["text"] for c in a["claims"])
    assert "21" in blob
    assert any(c["citation"]["source_url"] for c in a["claims"])
    assert a["conversation_id"]


def test_chat_surfaces_nov_13_vs_14_conflict(client):
    r = client.post(
        "/api/chat",
        json={
            "question": "When is the deadline to request accessibility accommodations?",
            "mode": "extractive",
        },
    )
    assert r.status_code == 200
    a = r.json()
    assert a["kind"] == "answer"
    assert a["outcome_key"] == "unresolved_contradiction"
    assert any(n["kind"] == "unresolved_contradiction" for n in a["notes"])
    blob = " ".join(c["text"] + " " + c["quote"] for c in a["claims"])
    assert "13" in blob and "14" in blob
    lead = a.get("summary") or ""
    from app.services.present import is_canned_conflict_lead

    assert not is_canned_conflict_lead(lead)
    assert not lead.lower().lstrip().startswith("the deadline for all requests is")
    if lead:
        assert "13" in lead and "14" in lead


def test_refusal_logs_unanswered(client):
    r = client.post(
        "/api/chat",
        json={"question": "What is the ABW policy on bringing a pet lizard to keynotes?", "mode": "extractive"},
    )
    assert r.status_code == 200
    a = r.json()
    assert a.get("refused") or a.get("kind") in {"off_topic", "greeting"}
    listed = client.get("/api/advisor/unanswered").json()["items"]
    if a.get("refused"):
        assert listed, "refusal must be stored for advisor follow-up"
        assert any("lizard" in (item.get("question") or "") for item in listed)


def test_task_request_declines(client):
    r = client.post("/api/chat", json={"question": "can you write an email for me to AWS support"})
    assert r.status_code == 200
    a = r.json()
    assert a["kind"] == "task_request"
    assert a["refused"] is True
    assert "can't" in (a.get("message") or "").lower() or "cannot" in (a.get("message") or "").lower()
    assert a.get("suggestions")


def test_feedback_and_flag(client):
    chat = client.post("/api/chat", json={"question": "When and where is re:Invent 2026?", "mode": "extractive"}).json()
    fb = client.post(
        "/api/feedback",
        json={"conversation_id": chat["conversation_id"], "turn": chat["turn"], "rating": "up"},
    )
    assert fb.status_code == 200
    flag = client.post(
        "/api/unanswered",
        json={"question": "custom leftover question", "conversation_id": chat["conversation_id"], "reason": "user_flag"},
    )
    assert flag.status_code == 200
    items = client.get("/api/advisor/feedback").json()["items"]
    assert items
    uq = client.get("/api/advisor/unanswered").json()["items"]
    assert any(i.get("question") == "custom leftover question" for i in uq)


def test_follow_up_rewrites_standalone(client):
    first = client.post(
        "/api/chat",
        json={"question": "How are ABW grant travel arrangements booked?", "mode": "extractive"},
    ).json()
    cid = first["conversation_id"]
    second = client.post(
        "/api/chat",
        json={"question": "how many days?", "conversation_id": cid, "mode": "extractive"},
    ).json()
    assert second["turn_type"] == "follow_up"
    assert "14" in " ".join(c["text"] + c["quote"] for c in second["claims"]) or "travel" in (second.get("interpreted_as") or "").lower()


def test_alumni_labeled_not_override(client):
    r = client.post(
        "/api/chat",
        json={"question": "How old do I need to be to apply for the ABW grant?", "mode": "extractive"},
    ).json()
    assert r["refused"] is False
    official = [c for c in r["claims"] if not c.get("alumni_experience")]
    assert any("21" in c["text"] or "21" in c["quote"] for c in official)
    # Must not present 18 as the grant minimum from alumni.
    grant_claims = " ".join(c["text"] for c in official)
    assert "18" not in grant_claims or "21" in grant_claims
