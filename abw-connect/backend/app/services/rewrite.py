"""Turn a chat message + the current thread into a standalone question.

Labels follow_up (depends on the thread) or new_topic (complete on its own; history is then ignored).
LLM mode: one short Bedrock call. Any failure → the message is used as typed and treated as a new topic.
Extractive/offline mode: a small heuristic.
"""
from __future__ import annotations

import json
import re
import time

from ..config import REWRITE_TIMEOUT_S
from .llm import LLMClient, LLMError
from .textnorm import topic_of

SYSTEM = """You rewrite the latest chat message about the AWS All Builders Welcome (ABW) grant or re:Invent
into ONE standalone question. Output valid JSON only:
{"standalone_question": "...", "turn_type": "follow_up" | "new_topic"}
- follow_up: the message only makes sense with the conversation (pronouns like "it"/"that", "how many?",
  "and for ...?", "what about ...?", "who books that?"). Rewrite it as a complete question that names the
  topic from the most recent relevant turn, keeping the user's own wording where possible.
- new_topic: the message is already a complete question on its own. Return it unchanged.
- Mixed ("ok, and what about hotels?"): new_topic about the new subject.
- Never add a date, number, or rule the user did not write or the conversation did not mention.
- Do not answer the question.
"""

FOLLOW_LEAD = re.compile(
    r"^\s*(and|also|so|but|then|plus|what about|how about|what if|and if|same for|ok(ay)?,? and|"
    r"how (many|much|long|often)|who|when|where|which|why|is that|does (it|that|this)|can (it|that|i still)|"
    r"what('s| is| are) the (limit|deadline|max(imum)?|minimum|process|benefit))\b",
    re.I,
)
PRONOUN = re.compile(r"\b(it|that|this|those|these|they|them|its|there|one)\b", re.I)


def heuristic(message, hist):
    """No-LLM rewrite. A message is a follow-up when there is an earlier answered turn and the message
    has no topic of its own and is very short, starts like a follow-up, or leans on a pronoun."""
    if not hist:
        return message, "new_topic"
    words = re.findall(r"[a-z0-9/']+", message.lower())
    own_topic = topic_of(message)
    # Complete questions with their own content are new topics even if they start with who/when.
    if len(words) >= 5 and not PRONOUN.search(message) and not re.match(
        r"^\s*(and|also|so|but|then|what about|how about|ok(ay)?,? and)\b", message, re.I
    ):
        return message, "new_topic"
    dependent = len(words) <= 4 or FOLLOW_LEAD.match(message) or PRONOUN.search(message)
    if own_topic is None and dependent:
        prev = hist[-1]["standalone"]
        m = re.search(r"\(about: (.*)\)$", prev)
        prev = m.group(1) if m else prev
        return f"{message.strip()} (about: {prev.strip()})", "follow_up"
    return message, "new_topic"


def _parse(raw: str):
    txt = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw or "", flags=re.S)
    i = txt.find("{")
    if i < 0:
        raise ValueError("no JSON object in rewrite reply")
    try:
        data = json.loads(txt[i : txt.rfind("}") + 1])
    except ValueError:
        import json_repair

        data = json_repair.loads(txt[i:])
    if not isinstance(data, dict):
        raise ValueError("rewrite reply is not an object")
    sq = str(data.get("standalone_question") or "").strip()
    tt = str(data.get("turn_type") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not sq or len(sq) > 600 or tt not in ("follow_up", "new_topic"):
        raise ValueError(f"bad rewrite fields: turn_type={tt!r}, standalone length={len(sq)}")
    return sq, tt


class LLMRewriter:
    def __init__(self, client: LLMClient, timeout_s: float = REWRITE_TIMEOUT_S):
        self.client = client
        self.timeout_s = timeout_s

    def rewrite(self, message, hist, profile):
        convo = "\n".join(
            f"Turn {i + 1} user: {h['standalone']}\nTurn {i + 1} answer: {h['answer']}"
            for i, h in enumerate(hist)
        )
        user = (
            f"Caller role: {profile.get('role', 'grantee')}, event year {profile.get('event_year')}.\n\n"
            f"Conversation so far (most recent last):\n{convo}\n\nLatest message: {message}"
        )
        t0 = time.time()
        last = None
        for attempt in (1, 2):
            left = self.timeout_s - (time.time() - t0)
            if left < 0.5:
                break
            try:
                raw = self.client.complete(SYSTEM, user, timeout_s=left, max_tokens=200)
                return _parse(raw)
            except Exception as e:
                last = e
                stalled = "timeout" in type(e).__name__.lower() or "connection" in type(e).__name__.lower()
                if attempt == 2 or not stalled:
                    raise
        raise last or LLMError("rewrite failed")


def rewrite(message, hist, profile, use_llm, rewriter=None):
    """Returns (standalone_question, turn_type, info) with info = {method, error, ms}."""
    t0 = time.time()
    if not hist:
        return message, "new_topic", dict(method="first_turn", error=None, ms=0)
    if not use_llm:
        sq, tt = heuristic(message, hist)
        return sq, tt, dict(method="heuristic", error=None, ms=int((time.time() - t0) * 1000))
    try:
        sq, tt = (rewriter or LLMRewriter(get_llm_safe())).rewrite(message, hist, profile)
        if tt == "new_topic":
            sq = message
        return sq, tt, dict(method="llm", error=None, ms=int((time.time() - t0) * 1000))
    except Exception as e:
        return message, "new_topic", dict(
            method="as_typed",
            error=f"{type(e).__name__}: {str(e)[:200]}",
            ms=int((time.time() - t0) * 1000),
        )


def get_llm_safe():
    from .llm import get_llm

    return get_llm()
