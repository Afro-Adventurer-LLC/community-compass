"""Display-side helpers. Never invent facts; only rearrange verified claims/notes."""
from __future__ import annotations

import re

from .resolver import DATE_RE, MONTHS

MONTH_DATE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+"
    r"\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?\b",
    re.I,
)


def date_mentions(*texts: str) -> list[str]:
    """Distinct calendar-date phrases, first-seen order, not retrieval-score order."""
    found: list[str] = []
    seen: set[str] = set()
    for t in texts:
        for m in MONTH_DATE.finditer(t or ""):
            raw = re.sub(r"\s+", " ", m.group(0)).strip()
            key = raw.lower().rstrip(".")
            if key not in seen:
                seen.add(key)
                found.append(raw)
    return found


def _day_number(phrase: str) -> int | None:
    m = re.search(r"\d{1,2}", phrase)
    return int(m.group(0)) if m else None


_START_CTX = re.compile(
    r"(starting on|starts on|start on|accepted starting|kickoff|badge pickup)",
    re.I,
)
_DEADLINE_CTX = re.compile(
    r"(deadline|must be received|received by|requests must)",
    re.I,
)

_DUMP_MARKERS = re.compile(
    r"(limitation of liability|disclaimer|severability|you are not an employee|"
    r"specially designated nationals|aggregate liability|section 1\.\d|"
    r"these \"terms\"|terms & conditions|#{2,}|1\.\d\s+termination)",
    re.I,
)


def llm_answer_is_dump(text: str | None) -> bool:
    """True when the model pasted retrieved passages instead of a short answer."""
    s = (text or "").strip()
    if not s:
        return False
    if len(s) > 650:
        return True
    if s.count("\n") >= 4:
        return True
    if _DUMP_MARKERS.search(s) and len(s) > 280:
        return True
    return False


def _window_around(text: str, start: int, end: int, pad: int = 90) -> str:
    return (text or "")[max(0, start - pad) : end + pad]


def is_start_not_deadline(text: str, start: int, end: int) -> bool:
    """True for 'starting on Nov. 29' windows that are not a request deadline."""
    win = _window_around(text, start, end)
    return bool(_START_CTX.search(win) and not _DEADLINE_CTX.search(win))


def phrase_for_date_fact(text: str, fact: tuple) -> str | None:
    """Return the source wording of (date, month, day, year) in text, or None.

    Prefer deadline wording. Skip event-start / 'accepted starting' mentions so a
    Nov. 29 kickoff is never presented as the conflicting accessibility deadline.
    """
    if not fact or fact[0] != "date":
        return None
    month, day = fact[1], fact[2]
    fallback = None
    for m in DATE_RE.finditer(text or ""):
        got_month = MONTHS[m.group(1).lower().rstrip(".")]
        got_day = int(m.group(2))
        if got_month != month or got_day != day:
            continue
        phrase = re.sub(r"\s+", " ", m.group(0)).strip()
        if is_start_not_deadline(text or "", m.start(), m.end()):
            continue
        if _DEADLINE_CTX.search(_window_around(text or "", m.start(), m.end())):
            return phrase
        fallback = fallback or phrase
    return fallback


def _claim_doc_id(claim: dict) -> str | None:
    cit = claim.get("citation") or {}
    if cit.get("doc_id"):
        return cit["doc_id"]
    for c in claim.get("citations") or []:
        if c.get("doc_id"):
            return c["doc_id"]
    return None


def _add_phrase(phrases: list[str], seen: set[tuple[int, int]], phrase: str | None) -> None:
    if not phrase:
        return
    m = DATE_RE.search(phrase)
    if not m:
        return
    key = (MONTHS[m.group(1).lower().rstrip(".")], int(m.group(2)))
    if key in seen:
        return
    seen.add(key)
    phrases.append(phrase)


def _phrase_from_source(claims: list[dict], src: dict, fact: tuple) -> str | None:
    """Prefer a verified claim citing this source; else the retrieved source text."""
    doc_id = src.get("doc_id")
    for c in claims:
        if _claim_doc_id(c) != doc_id:
            continue
        blob = f"{c.get('text') or ''} {c.get('quote') or ''}"
        found = phrase_for_date_fact(blob, fact)
        if found:
            return found
    return phrase_for_date_fact(src.get("text") or "", fact)


def dates_from_conflict_records(
    claims: list[dict],
    conflict_pairs: list[dict] | None = None,
    chunks_by_id: dict | None = None,
) -> list[str]:
    """Date phrases from resolver contradiction records, never unrelated claim dates."""
    phrases: list[str] = []
    seen: set[tuple[int, int]] = set()
    pairs = [p for p in (conflict_pairs or []) if p.get("outcome") == "unresolved_contradiction"]
    by_id = chunks_by_id or {}
    if pairs and by_id:
        for p in pairs:
            a, b = by_id.get(p.get("a")), by_id.get(p.get("b"))
            if not a or not b:
                continue
            clash = p.get("clash") or []
            if clash:
                for fa, fb in clash:
                    if fa and fa[0] == "date":
                        _add_phrase(phrases, seen, _phrase_from_source(claims, a, fa))
                    if fb and fb[0] == "date":
                        _add_phrase(phrases, seen, _phrase_from_source(claims, b, fb))
            else:
                for src in (a, b):
                    related = [c for c in claims if _claim_doc_id(c) == src.get("doc_id")]
                    blob = " ".join(
                        f"{c.get('text') or ''} {c.get('quote') or ''}" for c in related
                    ) or (src.get("text") or "")
                    for phrase in date_mentions(blob):
                        loc = (blob or "").lower().find(phrase.lower()[: min(18, len(phrase))])
                        if loc >= 0 and is_start_not_deadline(blob, loc, loc + len(phrase)):
                            continue
                        _add_phrase(phrases, seen, phrase)
        return _sort_phrases(phrases)

    official = [c for c in claims if not c.get("alumni_experience")] or list(claims)
    mentions = date_mentions(*(f"{c.get('text') or ''} {c.get('quote') or ''}" for c in official))
    for phrase in mentions:
        _add_phrase(phrases, seen, phrase)
    return _sort_phrases(phrases)


def _sort_phrases(phrases: list[str]) -> list[str]:
    def key(p: str):
        m = DATE_RE.search(p)
        if not m:
            return (99, 99)
        return (MONTHS[m.group(1).lower().rstrip(".")], int(m.group(2)))

    return sorted(phrases, key=key)


def conflicting_date_phrases(claims: list[dict]) -> list[str]:
    """One display phrase per distinct calendar day from the given claims."""
    return dates_from_conflict_records(claims)


# Retired primary-answer templates. Code may still *detect* these so they are
# never accepted as the user-facing summary. Do not compose them.
_CANNED_LEAD_INTERPOLATED = re.compile(
    r"^The official sources disagree: one says .+ and the other says .+\.\s*"
    r"Please confirm with AWS event support before relying on either (date|value)\.$",
    re.I | re.S,
)
_CANNED_LEAD_FALLBACK = re.compile(
    r"^The official sources disagree and neither overrides the other\.\s*"
    r"Please confirm with AWS event support before relying on either value\.$",
    re.I,
)
_UNCERTAINTY = re.compile(
    r"disagree|conflict|differ|different|confirm|versus|\bvs\.?\b|unclear|"
    r"mismatch|contradict|cannot tell|can'?t tell|do not agree|don'?t agree|"
    r"not the same|two (different|conflicting)|both (dates|values|figures|amounts)|"
    r"one (page|source|document|lists|says)|another (page|source|lists|says)|\bor\b",
    re.I,
)
_KNOWN_FACT_KINDS = frozenset({"date", "age", "money", "count"})


def is_canned_conflict_lead(text: str | None) -> bool:
    """True for the retired interpolated / fallback conflict sentences."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if not s:
        return False
    return bool(_CANNED_LEAD_INTERPOLATED.match(s) or _CANNED_LEAD_FALLBACK.match(s))


def _as_fact(obj) -> tuple | None:
    if obj is None:
        return None
    if isinstance(obj, tuple):
        return obj
    if isinstance(obj, list):
        return tuple(obj)
    return None


def _fact_token(fact: tuple) -> str | None:
    if not fact:
        return None
    kind = fact[0]
    if kind == "date":
        return str(int(fact[2]))
    if kind == "age":
        return str(fact[1])
    if kind == "money":
        return str(fact[1])
    if kind == "count":
        return str(fact[2])
    return None


def conflict_unknown_kind(conflict_pairs: list[dict] | None) -> bool:
    """True when a clash uses a fact type this pipeline cannot present safely."""
    for p in conflict_pairs or []:
        if p.get("outcome") not in (None, "unresolved_contradiction"):
            continue
        for item in p.get("clash") or []:
            if not item:
                continue
            sides = item[:2] if isinstance(item, (list, tuple)) else (item,)
            for raw in sides:
                fact = _as_fact(raw)
                if fact and fact[0] not in _KNOWN_FACT_KINDS:
                    return True
    return False


def _unique_tokens(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for t in items:
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def conflict_value_tokens(
    claims: list[dict],
    conflict_pairs: list[dict] | None = None,
    chunks_by_id: dict | None = None,
) -> list[str]:
    """Short tokens identifying each side of an unresolved clash (not a sentence)."""
    phrases = dates_from_conflict_records(claims, conflict_pairs, chunks_by_id)
    date_toks = []
    for phrase in phrases:
        day = _day_number(phrase)
        if day is not None:
            date_toks.append(str(day))
    date_toks = _unique_tokens(date_toks)
    if len(date_toks) >= 2:
        return date_toks[:2]

    other: list[str] = []
    for p in conflict_pairs or []:
        if p.get("outcome") not in (None, "unresolved_contradiction"):
            continue
        for item in p.get("clash") or []:
            if not item or not isinstance(item, (list, tuple)):
                continue
            for raw in item[:2]:
                fact = _as_fact(raw)
                if not fact or fact[0] == "date":
                    continue
                tok = _fact_token(fact)
                if tok:
                    other.append(tok)
    other = _unique_tokens(other)
    if len(other) >= 2:
        return other[:2]
    return _unique_tokens(date_toks + other)


def fact_has_supporting_claim(token: str, claims: list[dict] | None) -> bool:
    if not token:
        return False
    for c in claims or []:
        blob = f"{c.get('text') or ''} {c.get('quote') or ''}"
        if token in blob:
            return True
    return False


def conflict_both_sides_supported(
    claims: list[dict],
    conflict_pairs: list[dict] | None = None,
    chunks_by_id: dict | None = None,
) -> bool:
    """True when verified claims include a short quote for each conflicting value."""
    tokens = conflict_value_tokens(claims, conflict_pairs, chunks_by_id)
    if len(tokens) < 2:
        return False
    return all(fact_has_supporting_claim(t, claims) for t in tokens[:2])


def verify_conflict_summary(
    summary: str | None,
    claims: list[dict],
    conflict_pairs: list[dict] | None = None,
    chunks_by_id: dict | None = None,
) -> tuple[bool, str]:
    """Semantic check: both sourced values, supporting quotes, no canned lead, no silent winner.

    Does not require any particular sentence. Does not require 'neither overrides'.
    """
    s = (summary or "").strip()
    if not s:
        return False, "empty conflict summary"
    if llm_answer_is_dump(s):
        return False, "conflict summary copied retrieved passages"
    if is_canned_conflict_lead(s):
        return False, "conflict summary is a canned template"
    tokens = conflict_value_tokens(claims, conflict_pairs, chunks_by_id)
    if len(tokens) < 2:
        return False, "missing both conflicting values"
    missing = [t for t in tokens[:2] if t not in s]
    if missing:
        return False, f"conflict summary omits values {missing}"
    for t in tokens[:2]:
        if not fact_has_supporting_claim(t, claims):
            return False, f"no supporting quote for conflicting value {t}"
    if not _UNCERTAINTY.search(s):
        return False, "conflict summary does not mark disagreement or uncertainty"
    return True, ""
