"""Run the eval harness as part of pytest (extractive / mock retriever)."""
from evals.run_evals import PROFILE, check_item, check_turn, HERE
import json

from app.services.ask import ask
from app.services.chat import chat
from app.services.store import MemoryStore


def test_per_item_evals(retriever, store):
    cases = json.loads((HERE / "questions.json").read_text())
    failed = []
    for case in cases:
        a = ask(case["question"], PROFILE, mode="extractive", retriever=retriever, store=store)
        fails = check_item(case, a, retriever)
        if fails:
            failed.append((case["id"], fails, a.get("kind"), a.get("outcome_key"), a.get("refused")))
    assert not failed, failed


def test_multi_turn_evals(retriever):
    chains = json.loads((HERE / "chat_cases.json").read_text())
    failed = []
    for chain in chains:
        store = MemoryStore()
        cid = None
        for i, t in enumerate(chain["turns"]):
            a = chat(
                t["q"],
                PROFILE,
                conversation_id=cid,
                mode="extractive",
                store=store,
                retriever=retriever,
            )
            cid = a["conversation_id"]
            fails = check_turn(t, a)
            if fails:
                failed.append((chain["name"], i, t["q"], fails, a.get("turn_type"), a.get("kind")))
    assert not failed, failed
