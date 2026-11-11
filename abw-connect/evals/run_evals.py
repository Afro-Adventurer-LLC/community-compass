"""Eval harness for ABW Connect.

Per-item and multi-turn cases with expected behaviour: answer, refuse, flag conflict.
Run from repo root (mock mode, no AWS):

    PYTHONPATH=backend python -m evals.run_evals
    PYTHONPATH=backend python -m evals.run_evals --json evals/results.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.ask import ask  # noqa: E402
from app.services.chat import chat  # noqa: E402
from app.services.index import LocalIndex  # noqa: E402
from app.services.retrieval import LocalRetriever  # noqa: E402
from app.services.store import MemoryStore  # noqa: E402
from app.services.verify import locate  # noqa: E402
from app.services.textnorm import norm  # noqa: E402

HERE = Path(__file__).parent
PROFILE = dict(event_year=2026, include_alumni=True, role="grantee")


def _blob(a: dict) -> str:
    return " \n".join(c.get("text", "") + " || " + c.get("quote", "") for c in a.get("claims") or [])


def _is_refuse(a: dict) -> bool:
    return bool(a.get("refused")) or a.get("kind") in {"off_topic", "greeting", "task_request"}


def check_item(case: dict, a: dict, retriever: LocalRetriever) -> list[str]:
    fails = []
    expect = case.get("expect")
    if case.get("expect_kind") and a.get("kind") not in case["expect_kind"]:
        if expect != "refuse" or not _is_refuse(a):
            fails.append(f"kind {a.get('kind')} not in {case['expect_kind']}")
    if expect == "flag_conflict":
        if a.get("outcome_key") != "unresolved_contradiction":
            fails.append(f"outcome {a.get('outcome_key')} != unresolved_contradiction")
        if not any(n.get("kind") == "unresolved_contradiction" for n in a.get("notes") or []):
            fails.append("missing unresolved_contradiction note")
        lead = a.get("summary") or ""
        from app.services.present import is_canned_conflict_lead

        if is_canned_conflict_lead(lead):
            fails.append("conflict summary must not be a canned template")
        if re.match(r"^\s*The deadline for all requests is", lead, re.I):
            fails.append("conflict summary must not lead with a single deadline")
        if lead:
            for rx in case.get("must_match") or []:
                if not re.search(rx, lead, re.I):
                    fails.append(f"conflict summary missing /{rx}/")
    elif expect == "refuse":
        if not _is_refuse(a):
            fails.append(f"expected refusal, got kind={a.get('kind')} refused={a.get('refused')}")
        else:
            if not (a.get("suggestions") or []) and a.get("kind") != "greeting":
                fails.append("refusal missing suggestions")
    elif expect == "answer":
        if a.get("kind") != "answer" or a.get("refused"):
            fails.append(f"expected answer, got kind={a.get('kind')} refused={a.get('refused')}")
    blob = _blob(a)
    for rx in case.get("must_match") or []:
        if not re.search(rx, blob, re.I):
            fails.append(f"missing /{rx}/")
    for rx in case.get("must_not_match_official") or []:
        official = " \n".join(
            c["text"] for c in a.get("claims") or [] if not c.get("alumni_experience")
        )
        if re.search(rx, official, re.I):
            fails.append(f"forbidden official fact /{rx}/")
    if case.get("must_cite_url_contains"):
        urls = [c["citation"].get("source_url") or "" for c in a.get("claims") or []]
        for needle in case["must_cite_url_contains"]:
            if not any(needle in u for u in urls):
                fails.append(f"missing citation url containing {needle}")
    if case.get("must_note") and not any(n.get("kind") == case["must_note"] for n in a.get("notes") or []):
        fails.append(f"missing note {case['must_note']}")
    for c in a.get("claims") or []:
        page = retriever.document_text(c["citation"]["doc_id"])
        if not locate(norm(c["quote"]), page):
            fails.append(f"quote not in source {c['citation']['doc_id']}: {c['quote'][:80]}")
    return fails


def run_items(retriever, store, mode: str) -> list[dict]:
    cases = json.loads((HERE / "questions.json").read_text())
    rows = []
    for case in cases:
        t0 = time.time()
        a = ask(case["question"], PROFILE, mode=mode, retriever=retriever, store=store)
        fails = check_item(case, a, retriever)
        rows.append(
            dict(
                id=case["id"],
                ok=not fails,
                fails=fails,
                kind=a.get("kind"),
                refused=a.get("refused"),
                outcome=a.get("outcome_key"),
                ms=int((time.time() - t0) * 1000),
            )
        )
        mark = "PASS" if not fails else "FAIL"
        print(f"  [{mark}] {case['id']}  {case['question'][:70]}")
        for f in fails:
            print(f"         - {f}")
    return rows


def check_turn(t: dict, a: dict) -> list[str]:
    fails = []
    if t.get("kind") and a.get("kind") != t["kind"]:
        fails.append(f"kind {a.get('kind')} != {t['kind']}")
    if t.get("turn_type") and a.get("turn_type") != t["turn_type"]:
        fails.append(f"turn_type {a.get('turn_type')} != {t['turn_type']} (interpreted_as={a.get('interpreted_as')!r})")
    if t.get("expect") == "flag_conflict" and a.get("outcome_key") != "unresolved_contradiction":
        fails.append(f"outcome {a.get('outcome_key')}")
    if t.get("expect") == "answer" and (a.get("kind") != "answer" or a.get("refused")):
        fails.append(f"expected answer, got {a.get('kind')} refused={a.get('refused')}")
    ia = a.get("interpreted_as") or ""
    if t.get("interp_has") and not re.search(t["interp_has"], ia, re.I):
        fails.append(f"interpreted_as {ia!r} !~ {t['interp_has']}")
    blob = _blob(a)
    for rx in t.get("must_match") or []:
        if not re.search(rx, blob, re.I):
            fails.append(f"missing /{rx}/")
    return fails


def run_chat(retriever, mode: str) -> list[dict]:
    chains = json.loads((HERE / "chat_cases.json").read_text())
    rows = []
    for chain in chains:
        store = MemoryStore()
        cid = None
        print(f"  chain: {chain['name']}")
        for i, t in enumerate(chain["turns"]):
            a = chat(
                t["q"],
                PROFILE,
                conversation_id=cid,
                mode=mode,
                store=store,
                retriever=retriever,
            )
            cid = a["conversation_id"]
            fails = check_turn(t, a)
            rows.append(dict(chain=chain["name"], turn=i, ok=not fails, fails=fails, kind=a.get("kind"), turn_type=a.get("turn_type")))
            mark = "PASS" if not fails else "FAIL"
            print(f"    [{mark}] t{i} {t['q'][:60]}")
            for f in fails:
                print(f"           - {f}")
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", default="extractive", choices=["extractive", "llm", "auto"])
    p.add_argument("--json", dest="json_out")
    args = p.parse_args()
    retriever = LocalRetriever(LocalIndex(ROOT / "kb"))
    store = MemoryStore()
    print("== per-item ==")
    items = run_items(retriever, store, args.mode)
    print("== multi-turn ==")
    chats = run_chat(retriever, args.mode)
    n_fail = sum(1 for r in items + chats if not r["ok"])
    n_ok = sum(1 for r in items + chats if r["ok"])
    print(f"\n{n_ok} passed, {n_fail} failed")
    payload = dict(items=items, chat=chats, passed=n_ok, failed=n_fail)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(payload, indent=2))
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
