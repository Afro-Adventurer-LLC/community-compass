"""Multi-turn chat: rewrite follow-ups into a standalone question, then run ask().

History is used only to understand a follow-up. It is never evidence: every claim is
still verified against the cited source text.
"""
from __future__ import annotations

import time

from ..config import CHAT_HISTORY_TURNS, GENERATOR_MODE, LLM_TIMEOUT_S, use_aws
from . import smalltalk
from .ask import ask
from .rewrite import rewrite
from .store import ConversationForbidden, ConversationNotFound, get_store

REWRITER = None  # tests may install a fake rewriter here


def _uses_llm(mode: str | None) -> bool:
    m = (mode or GENERATOR_MODE).lower()
    return m == "llm" or (m == "auto" and use_aws())


def _profile_key(profile: dict) -> str:
    return f"{profile.get('role', 'grantee')}:{profile.get('event_year')}:{int(bool(profile.get('include_alumni', True)))}"


def chat(
    question: str,
    profile: dict | None = None,
    conversation_id: str | None = None,
    mode: str | None = None,
    *,
    store=None,
    retriever=None,
    generator=None,
):
    t0 = time.time()
    profile = dict(profile or {})
    store = store or get_store()
    key = _profile_key(profile)
    if conversation_id:
        store.check(conversation_id, key)
        cid = conversation_id
    else:
        cid = store.create_conversation(key)

    pre = smalltalk.classify(question)
    if pre == "greeting":
        a = ask(question, profile, mode=mode, retriever=retriever, store=store, generator=generator, conversation_id=cid)
        a.update(
            conversation_id=cid,
            question=question,
            interpreted_as=None,
            turn_type="smalltalk",
            rewrite=dict(method="skipped", error=None, ms=0),
        )
        a["turn"] = store.add_turn(cid, question, question, "smalltalk", a, a["rewrite"])
        return a

    hist = store.history(cid, CHAT_HISTORY_TURNS)
    thread_topic = next((h["topic"] for h in reversed(hist) if h.get("topic")), None)
    if pre == "task_request":
        a = ask(
            question,
            profile,
            mode=mode,
            retriever=retriever,
            store=store,
            generator=generator,
            topic_hint=thread_topic,
            conversation_id=cid,
        )
        a.update(
            conversation_id=cid,
            question=question,
            interpreted_as=None,
            turn_type="task_request",
            rewrite=dict(method="skipped", error=None, ms=0),
            history_turns=0,
            latency_ms=int((time.time() - t0) * 1000),
        )
        a["turn"] = store.add_turn(cid, question, question, "task_request", a, a["rewrite"])
        return a

    use_llm = _uses_llm(mode)
    standalone, turn_type, info = rewrite(question, hist, profile, use_llm, rewriter=REWRITER)
    kw = {}
    if turn_type == "follow_up":
        kw = dict(history=hist)
    if use_llm:
        kw["llm_budget_s"] = max(LLM_TIMEOUT_S - (time.time() - t0), 3.0)
    a = ask(
        standalone,
        profile,
        mode=mode,
        retriever=retriever,
        store=store,
        generator=generator,
        topic_hint=thread_topic,
        conversation_id=cid,
        **kw,
    )
    if a.get("kind") == "task_request":
        turn_type = "task_request"
    elif a.get("kind") != "answer":
        turn_type = "smalltalk"
    a.update(
        conversation_id=cid,
        question=question,
        interpreted_as=standalone,
        turn_type=turn_type,
        rewrite=info,
        history_turns=len(hist) if turn_type == "follow_up" else 0,
        latency_ms=int((time.time() - t0) * 1000),
    )
    a["turn"] = store.add_turn(cid, question, standalone, turn_type, a, info)
    return a
