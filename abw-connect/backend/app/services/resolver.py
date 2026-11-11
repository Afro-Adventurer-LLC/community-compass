"""Resolver: decides how the applicable passages relate, using only stored text.

Outcomes
  compatible                 all passages can be true for this caller
  explicit_exception         a stored sentence grants the more specific document authority
  superseded                 a stored sentence says a later version replaces an earlier one
  unresolved_contradiction   both apply, both cannot be true, and no stored edge orders them

Alumni experience never overrides official guidance. Conflicting alumni numbers/dates are
suppressed; they do not produce an unresolved contradiction against official text.
"""
from __future__ import annotations

import re
from typing import Any

from .textnorm import NUM_WORDS, squash

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

DATE_RE = re.compile(
    r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
    r"(?:[-–]\s*\d{1,2}(?:st|nd|rd|th)?)?(?:,?\s*(20\d{2}))?",
    re.I,
)

AGE_RE = re.compile(
    r"\b(?:at least|must be at least|must be|you are at least)\s+(\d{1,2})\s+years?\s+(?:of age|old)\b",
    re.I,
)
AGE_UNDER_RE = re.compile(r"\bunder\s+(\d{1,2})\b", re.I)

MONEY_RE = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?")

COUNT_RE = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+"
    r"(days?|years?|miles?|hours?|minutes?|venues?|sessions?|hotels?)\b",
    re.I,
)

SUPERSEDE_RE = re.compile(
    r"\b(this (?:page|document|version) (?:replaces|supersedes)|supersedes|replaced by)\b",
    re.I,
)
EXCEPTION_RE = re.compile(
    r"\b(except(?:ion)?|unless otherwise|does not apply if)\b",
    re.I,
)


def _as_int(tok: str) -> int | None:
    tok = tok.lower().replace(",", "")
    if tok.isdigit():
        return int(tok)
    return NUM_WORDS.get(tok)


def slot_of(text: str) -> str | None:
    """Coarse fact slot used to decide whether two numbers/dates are comparable."""
    t = squash(text)
    a11y = any(
        k in t
        for k in (
            "accessib",
            "accommodat",
            "asl",
            "sign language",
            "cart",
            "sighted guide",
            "mobility device",
            "neurodivergent",
            "sensory need",
        )
    )
    deadlineish = any(
        k in t
        for k in (
            "deadline",
            "must be received",
            "requests must",
            "all requests",
            "by november",
            "by nov",
            "cannot be guaranteed",
            "submitted",
            "by when",
            "must arrive",
            "arrive by",
            "cutoff",
            "last day",
            "when must",
        )
    )
    nov_deadline = bool(re.search(r"nov(?:ember|\.)?\s*1[34]", t))
    if (a11y and deadlineish) or (deadlineish and nov_deadline) or (a11y and nov_deadline):
        return "accessibility_request_deadline"
    if "21 years" in t or "at least 21" in t:
        if "grant" in t or "program" in t or "apply" in t or "eligible" in t:
            return "grant_min_age"
        if "hotel" in t or "campus" in t or "gaming" in t:
            return "hotel_min_age"
        return "min_age"
    if "18 years" in t or "at least 18" in t:
        if "badge" in t or "attendee" in t or "conference" in t:
            return "event_min_age"
        return "min_age"
    if "14 days" in t and ("flight" in t or "return" in t):
        return "return_flight_window"
    if "first 5 years" in t or "first five years" in t:
        return "career_years"
    if "2,499" in t or "2499" in t:
        return "full_pass_price"
    if "oct. 16" in t or "oct 16" in t or "october 16" in t:
        return "cancel_full_refund"
    if "nov. 23" in t or "nov 23" in t or "november 23" in t:
        return "cancel_partial_refund"
    if "november 5" in t and "hotel" in t:
        return "hotel_block_close"
    if "50%" in t and "certification" in t:
        return "cert_discount"
    if a11y:
        return "accessibility"
    return None


def date_facts(text: str) -> set[tuple]:
    out = set()
    for m in DATE_RE.finditer(text):
        month = MONTHS[m.group(1).lower().rstrip(".")]
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else None
        out.add(("date", month, day, year))
    return out


def age_facts(text: str) -> set[tuple]:
    out = set()
    for m in AGE_RE.finditer(text):
        out.add(("age", int(m.group(1))))
    return out


def money_facts(text: str) -> set[tuple]:
    out = set()
    for m in MONEY_RE.finditer(text):
        n = int(m.group(1).replace(",", ""))
        out.add(("money", n))
    return out


def count_facts(text: str) -> set[tuple]:
    out = set()
    for m in COUNT_RE.finditer(text):
        n = _as_int(m.group(1))
        if n is None:
            continue
        unit = m.group(2).rstrip("s").lower()
        out.add(("count", unit, n))
    return out


def facts(text: str) -> set[tuple]:
    """Typed facts used to detect clashes between passages."""
    return date_facts(text) | age_facts(text) | money_facts(text) | count_facts(text)


def _comparable(a: tuple, b: tuple) -> bool:
    if a[0] != b[0] or a == b:
        return False
    if a[0] == "date":
        # Same calendar day (year optional) is not a clash; different day/month is.
        return a[1] != b[1] or a[2] != b[2]
    if a[0] == "count":
        return a[1] == b[1] and a[2] != b[2]
    if a[0] in ("age", "money"):
        return a[1] != b[1]
    return False


def _clash(fa: set[tuple], fb: set[tuple]) -> list[tuple]:
    out = []
    for x in fa:
        for y in fb:
            if _comparable(x, y):
                out.append((x, y))
    return out


_DURATION_QUESTION = re.compile(
    r"\b(how much time|how long|minutes|hours|leave between|between venues|"
    r"between properties|travel time|time should i leave|shuttle|"
    r"buffer|moving between|transportation between|getting from one venue|"
    r"between (?:re:?invent )?campus(?:es)?|across (?:the )?(?:re:?invent )?campus|"
    r"transit buffer|getting across|travel between)\b",
    re.I,
)
_DATE_QUESTION = re.compile(r"\b(deadline|when is|what day|what date|which day)\b", re.I)


def _question_skips_date_clash(question: str | None) -> bool:
    """Travel-duration questions must not surface unrelated event-week dates as a conflict."""
    q = question or ""
    return bool(_DURATION_QUESTION.search(q) and not _DATE_QUESTION.search(q))


def _date_only_clash(clash: list[tuple]) -> bool:
    return bool(clash) and all(x[0] == "date" and y[0] == "date" for x, y in clash)


def resolve(chunks: list[dict], topic: str | None, question: str | None = None) -> dict[str, Any]:
    """Return dict(outcome, pairs=[...], suppressed=set()).

    Official vs official clashes on the same slot → unresolved_contradiction.
    Alumni vs official clashes → alumni suppressed (never overrides).
    A later event_year official doc can supersede an earlier one if the text says so.

    Calendar dates only conflict when both passages have a real named slot
    (for example accessibility_request_deadline). Unslotted agenda/FAQ week
    dates are not a contradiction, and duration questions never use date clashes.
    """
    result: dict[str, Any] = dict(outcome="compatible", pairs=[], suppressed=set(), edges_used=[])
    F = [facts(c.get("text") or "") for c in chunks]
    native_slots = [
        slot_of(" ".join(filter(None, [c.get("title"), c.get("section"), c.get("text")])))
        for c in chunks
    ]
    skip_dates = _question_skips_date_clash(question)

    for i, a in enumerate(chunks):
        for j in range(i + 1, len(chunks)):
            b = chunks[j]
            if a.get("doc_id") == b.get("doc_id"):
                continue
            fa, fb = F[i], F[j]
            clash = _clash(fa, fb)
            if skip_dates:
                clash = [
                    (x, y)
                    for x, y in clash
                    if not (x[0] == "date" and y[0] == "date")
                    and not (x[0] == "count" and y[0] == "count" and x[1] in {"minute", "hour"})
                ]
            if not clash:
                continue
            native_a, native_b = native_slots[i], native_slots[j]
            qslot = slot_of(question or "") if question else None
            if _date_only_clash(clash):
                # A question about travel/wayfinding must not be answered by an
                # unrelated deadline clash. No question (unit tests) keeps prior rules.
                if question:
                    if not qslot or (qslot != native_a and qslot != native_b):
                        continue
                same_deadline = bool(
                    native_a
                    and native_b
                    and str(native_a).endswith("_deadline")
                    and str(native_b).endswith("_deadline")
                )
                if not same_deadline and (not native_a or not native_b or native_a != native_b):
                    continue
            else:
                # Unslotted counts (travel minutes vs reserved-seat minutes) must
                # not inherit the question topic and fire a false conflict.
                sa, sb = native_a, native_b
                if not sa or not sb or sa != sb:
                    if not (
                        sa
                        and sb
                        and str(sa).endswith("_deadline")
                        and str(sb).endswith("_deadline")
                    ):
                        continue

            a_off = a.get("source_type") == "official"
            b_off = b.get("source_type") == "official"

            if a_off != b_off:
                alumni, official = (a, b) if b_off else (b, a)
                result["pairs"].append(
                    dict(
                        outcome="official_over_alumni",
                        winner=official["id"],
                        loser=alumni["id"],
                        clash=clash,
                    )
                )
                result["suppressed"].add(alumni["id"])
                continue

            if a_off and b_off:
                ya, yb = a.get("event_year"), b.get("event_year")
                a_super = bool(SUPERSEDE_RE.search(a.get("text") or ""))
                b_super = bool(SUPERSEDE_RE.search(b.get("text") or ""))
                if (ya and yb and ya != yb) and (a_super or b_super):
                    newer, older = (a, b) if (ya or 0) > (yb or 0) else (b, a)
                    result["pairs"].append(
                        dict(outcome="superseded", winner=newer["id"], loser=older["id"], clash=clash)
                    )
                    result["suppressed"].add(older["id"])
                    continue
                if EXCEPTION_RE.search(a.get("text") or "") or EXCEPTION_RE.search(b.get("text") or ""):
                    # A passage that states an exception can govern the more general one.
                    specific = a if EXCEPTION_RE.search(a.get("text") or "") else b
                    general = b if specific is a else a
                    result["pairs"].append(
                        dict(
                            outcome="explicit_exception",
                            winner=specific["id"],
                            loser=general["id"],
                            clash=clash,
                        )
                    )
                    result["suppressed"].add(general["id"])
                    continue
                result["pairs"].append(
                    dict(outcome="unresolved_contradiction", a=a["id"], b=b["id"], clash=clash)
                )

    kinds = {p["outcome"] for p in result["pairs"]}
    for k in ("unresolved_contradiction", "superseded", "explicit_exception"):
        if k in kinds:
            result["outcome"] = k
            break
    return result
