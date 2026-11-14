"""Ask workflow: retrieval -> support -> resolver -> generate -> verify -> answer.

History is never evidence. Alumni experience never overrides official guidance.
"""
from __future__ import annotations

import re
import time
from typing import Any

from ..config import MIN_SCORE, OFF_TOPIC_SCORE, DEFAULT_EVENT_YEAR
from . import smalltalk
from .generator import (
    _overlap,
    bind_claim_source,
    get_generator,
    normalize_generated_claim,
    source_passage_id,
    unit_texts,
)
from .resolver import _DURATION_QUESTION, facts, resolve, slot_of
from .retrieval import Retriever, get_retriever
from .store import Store, get_store
from .textnorm import tokenize, topic_of
from .index import EXPAND, STOP as INDEX_STOP, canonical_doc_id, scrub_s3_uris

_STOP = {
    "the", "a", "an", "is", "are", "was", "be", "to", "of", "in", "on", "at", "for", "and",
    "or", "my", "me", "i", "we", "you", "do", "does", "what", "when", "where", "who", "how",
    "which", "why", "with", "from", "this", "that", "it", "can", "need",
}
_DOMAIN_STOP = {
    "abw", "grant", "aws", "reinvent", "event", "policy", "official", "question", "please",
    "re", "invent", "all", "builders", "welcome", "conference", "page", "document",
}
# Coverage paraphrases that rarely appear in Terms; do not fail lexical support on them.
_PARAPHRASE_LIGHT = {
    "someone", "somebody", "person", "people", "list", "outline", "tell", "summarize",
    "break", "down", "components", "inclusions", "included", "receives", "receive",
    "attendees", "attendee", "come", "comes", "which", "costs", "package",
}
_COVERAGE_VERBS = {
    "cover", "covers", "coverage", "include", "includes", "included", "inclusions",
    "benefits", "package", "pay", "pays", "expenses", "costs", "components", "outline",
}
_GRANT_ISH = {"grant", "grantee", "abw", "builders", "scholarship", "funding"}
_STUDENT_ISH = {
    "student", "students", "undergrad", "undergrads", "undergraduate", "college",
}
_ELIG_ISH = {"eligible", "eligibility", "qualify", "qualifies", "requirements"}
_ROOM_ISH = {"suite", "suites", "room", "rooms"}
_ROOM_MODIFIERS = _ROOM_ISH | {
    "pick", "choose", "select", "instead", "standard", "upgrade", "upgrades", "type", "types",
    "own", "grantee", "grantees", "get", "book", "single", "double", "private", "share", "sharing",
}
_QUESTION_UNIT = re.compile(
    r"(?i)^\s*(can i|what |when |where |who |why |how |do i|does |are you|is there|will there).{0,120}\?\s*$"
    r"|\?\s*$"
)
_COVERAGE_NOISE = re.compile(
    r"(?i)cancellation polic|re:?play-only|add-on pass|required to attend re:invent|"
    r"required when in the designated|campus hotel\?"
)
from .present import (
    conflict_both_sides_supported,
    conflict_unknown_kind,
    conflict_value_tokens,
    is_canned_conflict_lead,
    llm_answer_is_dump,
    phrase_for_date_fact,
    verify_conflict_summary,
)
from .verify import (
    _focus_tokens,
    _looks_structured_list,
    align_quote,
    clip_quote_to_support,
    expand_list_span,
    expand_to_containing_line,
    locate,
    omitted_claim_texts,
    relevant_verified_claims,
    summary_covers_question,
    travel_minute_values,
    verify,
    verify_summary,
    verify_unspecified_summary,
)

OUTCOME_LABEL = {
    "compatible": "Compatible",
    "explicit_exception": "Explicit exception",
    "superseded": "Superseded",
    "unresolved_contradiction": "Unresolved contradiction",
    "official_over_alumni": "Compatible",
}


def _grant_coverage_intent(question: str) -> bool:
    """True for 'what does the grant cover' paraphrases, including missing ABW acronym."""
    qtoks = set(tokenize(question or ""))
    return bool(qtoks & _COVERAGE_VERBS) and bool(qtoks & _GRANT_ISH)


def _slots_from_found(found: set[str]) -> set[str]:
    slots: set[str] = set()
    if found & {"pass", "ticket", "badge"}:
        slots.add("pass")
    if found & {"flight", "roundtrip", "airfare"}:
        slots.add("flight")
    if found & {"hotel", "lodging"}:
        slots.add("hotel")
    return slots


def _needed_benefit_slots(question: str) -> set[str]:
    """Generic coverage wants P+F+H; travel/lodging or flight+hotel stays scoped."""
    if not _grant_coverage_intent(question):
        return set()
    qtoks = set(tokenize(question or ""))
    named: set[str] = set()
    if qtoks & {"flight", "airfare"} or (qtoks & {"travel"} and "lodging" in qtoks):
        named.add("flight")
    if qtoks & {"hotel", "lodging"}:
        named.add("hotel")
    if qtoks & {"pass", "badge", "ticket"}:
        named.add("pass")
    package = bool(qtoks & {"package", "benefits", "list", "inclusions", "components", "badge", "pass"})
    if named == {"flight", "hotel"} and not package:
        return named
    if named == {"flight"} or named == {"hotel"}:
        return named
    return {"pass", "flight", "hotel"}


def _best_official_slots(hits) -> set[str]:
    """Benefit slots per official document (not pass from registration + hotel from hotels FAQ)."""
    by_doc: dict[str, set[str]] = {}
    for h in hits or []:
        src = h.get("source_type") if isinstance(h, dict) else getattr(h, "source_type", "")
        if src and src != "official":
            continue
        doc = canonical_doc_id(
            (h.get("doc_id") if isinstance(h, dict) else getattr(h, "doc_id", "")) or ""
        )
        by_doc.setdefault(doc, set()).update(_slots_from_found(set(tokenize(_hit_text(h)))))
    best: set[str] = set()
    for slots in by_doc.values():
        if len(slots) > len(best):
            best = slots
    return best


def _is_program_benefit_unit(text: str) -> bool:
    t = (text or "").strip()
    if not t or _QUESTION_UNIT.search(t) or _COVERAGE_NOISE.search(t):
        return False
    return bool(_slots_from_found(set(tokenize(t))))


def _lexical_support(question: str, hits) -> bool:
    """Require distinctive query tokens to appear in the top passages.

    Raw BM25 scores are not comparable across queries, so a numeric floor alone
    would treat off-topic questions as supported.
    """
    qtoks = [t for t in tokenize(question) if t not in _STOP and t not in INDEX_STOP]
    if not qtoks or not hits:
        return False

    blob = " ".join(_hit_text(h) for h in hits[:8])
    found = set(tokenize(blob))

    def present(tok: str) -> bool:
        if tok in found:
            return True
        return any(e in found for e in EXPAND.get(tok, []))

    distinctive = [t for t in qtoks if t not in _DOMAIN_STOP]
    if _grant_coverage_intent(question):
        distinctive = [t for t in distinctive if t not in _PARAPHRASE_LIGHT]
        if not distinctive:
            return bool(_best_official_slots(hits) or found & {"builders", "welcome", "terms", "benefits"})
    # Undergrad/qualify paraphrases: require student/eligibility evidence, not the surface wording.
    qset = set(qtoks)
    if qset & _STUDENT_ISH:
        paraphrase = {"qualify", "qualifies", "undergrad", "undergrads", "undergraduate", "college"}
        distinctive = [t for t in distinctive if t not in paraphrase]
        if not distinctive:
            return bool(found & {"student", "students", "university", "eligible", "21", "career"})
    # Room-type asks ("pick a suite instead of a standard room"): the documents may not
    # name the room type at all, and that is exactly what the LLM must be able to say.
    # Support is the lodging evidence, not the room-type wording (live stress_22 no_support).
    if qset & _ROOM_ISH:
        distinctive = [t for t in distinctive if t not in _ROOM_MODIFIERS]
        if not distinctive:
            return bool(found & {"hotel", "hotels", "accommodations", "lodging"})
    if distinctive:
        hit = sum(1 for t in distinctive if present(t))
        return hit / len(distinctive) >= 0.34
    return sum(1 for t in qtoks if present(t)) / len(qtoks) >= 0.5


def _cite(c: dict, span=None, quote=None) -> dict:
    return dict(
        doc_id=c.get("doc_id"),
        title=c.get("title"),
        section=c.get("section"),
        source_url=c.get("source_url"),
        event_year=c.get("event_year"),
        source_type=c.get("source_type"),
        retrieval_date=c.get("retrieval_date"),
        evidence_span=list(span) if span else None,
        alumni_experience=c.get("source_type") == "alumni_experience",
    )


def select_chunks(question: str, hits: list[dict]) -> tuple[str | None, list[dict]]:
    """Pick answer passages from the top hits, preferring official docs, and always
    keeping other-document passages so the resolver can see disagreements."""
    if not hits:
        return None, []
    qt = topic_of(question) or hits[0].get("topic")

    def sort_key(h):
        official = 1.0 if h.get("source_type") == "official" else 0.85
        return (h.get("score") or 0) * official

    ranked = sorted(hits, key=sort_key, reverse=True)
    chosen: list[dict] = []
    seen_ids: set[str] = set()
    seen_docs: set[str] = set()
    for h in ranked:
        if h["id"] in seen_ids:
            continue
        if h["doc_id"] in seen_docs and h.get("source_type") != "official":
            continue
        chosen.append(h)
        seen_ids.add(h["id"])
        seen_docs.add(h["doc_id"])
        if len(chosen) >= 6:
            break
    if not chosen:
        chosen = [ranked[0]]
    # Official first-passages are primary for extractive quoting.
    official = [c for c in chosen if c.get("source_type") == "official"]
    primary_ids = {c["id"] for c in (official[:3] or chosen[:2])}
    for h in chosen:
        h["primary"] = h["id"] in primary_ids
    return qt, chosen


def _answerable(retriever: Retriever, event_year: int, include_alumni: bool):
    def ok(q: str) -> bool:
        hits = retriever.retrieve(q, event_year=event_year, include_alumni=include_alumni, k=8)
        if not hits:
            return False
        return (hits[0].score or 0) >= MIN_SCORE
    return ok


def _topics(question, topic_hint=None, hits=()):
    out = [topic_of(question), topic_hint] + [getattr(h, "topic", None) or (h.get("topic") if isinstance(h, dict) else None) for h in list(hits)[:3]]
    return [t for i, t in enumerate(out) if t and t not in out[:i]]


def _friendly_refusal(out, reason, question, retriever, event_year, include_alumni, topic_hint=None, hits=()):
    msg, sugg = smalltalk.refusal_reply(
        reason,
        _topics(question, topic_hint, hits),
        _answerable(retriever, event_year, include_alumni),
        question=question,
    )
    out.update(refusal_reason=reason, message=msg, suggestions=sugg)
    return out


def evidence_page(chunk: dict, active: list[dict] | None, retriever) -> str:
    """Text the verifier may search.

    On AWS, Bedrock Retrieve returns per-chunk text and document_text() is often
    empty (no local copy of the doc). Never verify against only the first chunk
    of a doc_id: union the local doc (if any) with every retrieved sibling chunk.
    """
    doc_id = chunk.get("doc_id")
    parts: list[str] = []
    seen: set[str] = set()

    def add(text: str | None) -> None:
        t = (text or "").strip()
        if t and t not in seen:
            seen.add(t)
            parts.append(t)

    if retriever is not None and doc_id:
        try:
            add(retriever.document_text(doc_id))
        except Exception:
            pass
    add(chunk.get("title"))
    add(chunk.get("section"))
    year = chunk.get("event_year")
    if year:
        add(str(year))
    add(chunk.get("text"))
    for other in active or []:
        if other.get("doc_id") == doc_id:
            add(other.get("text"))
    return "\n\n".join(parts)


def _passage_index(source: str | None, n: int) -> int | None:
    sid = source_passage_id(source)
    if not sid:
        return None
    try:
        pi = int(sid.split(".")[0].lstrip("Pp")) - 1
    except (TypeError, ValueError):
        return None
    if 0 <= pi < n:
        return pi
    return None


def _resolve_chunk(cl: dict, active: list[dict]):
    """Map a claim to a retrieved passage, recovering nested/malformed source ids."""
    if not active:
        return None, None
    pi = _passage_index(cl.get("source"), len(active))
    if pi is not None:
        return pi, active[pi]
    quote = cl.get("quote") or cl.get("text") or ""
    if not quote:
        return None, None
    for i, chunk in enumerate(active):
        page = chunk.get("text") or ""
        snapped, _span = align_quote(quote, page)
        if snapped:
            return i, chunk
    return None, None


def _timeout_error(gen_error: str | None) -> bool:
    s = (gen_error or "").lower()
    return "timeout" in s


_ATOMIC_ITEM = re.compile(
    r"(?m)^[ \t]*((?:[\-•*]|[A-I]\.|\d+\.)[ \t]+\S[^\n]*)"
)
# Inline list items in flattened Bedrock chunks ("...; and - Hotel accommodations in Event
# Location during the Event. You must follow ..."): an item ends at `;`, a newline, or a
# sentence end (". " + capital). Running to the next `;` swallowed the rest of the chunk
# (>400 chars) and dropped the hotel bullet (live d55b08d grant_13 / stress_00).
_ATOMIC_INLINE = re.compile(
    r"(?:[\-•*]|[A-I]\.)\s+\S(?:[^;\n.]|\.(?=\S)|\.(?=\s+[a-z0-9(]))*(?:\.(?=\s|$))?"
)


def _atomic_units(text: str) -> list[str]:
    """Sentence/bullet pieces from a Bedrock-sized chunk (live salvage skipped units >400).

    Union bullets AND sentences. A sessions FAQ with other list items still contains
    the non-bullet buffer line; returning bullets only hid it (live venue_02).
    """
    t = (text or "").strip()
    if not t:
        return []
    items = [m.group(1).strip() for m in _ATOMIC_ITEM.finditer(t)]
    items.extend(m.group(0).strip() for m in _ATOMIC_INLINE.finditer(t))
    items.extend(p.strip() for p in re.split(r"(?<=[.!?])\s+", t))
    out: list[str] = []
    seen: set[str] = set()
    for p in items:
        p = p.strip().rstrip(";")
        if p.startswith("#"):
            # Bedrock flattens markdown: "### Plan your schedule Sessions run ... allow
            # 30 to 45 minutes between venues." is one piece. Keep the sentence (still a
            # verbatim substring) instead of skipping it as a heading (live venue d55b08d).
            if "\n" in p or not re.search(r"[.!?]$", p):
                continue
            p = re.sub(r"^#+\s*", "", p)
        if 20 <= len(p) <= 400 and p not in seen:
            seen.add(p)
            out.append(p)
    if out:
        return out
    if 24 <= len(t) <= 400:
        return [t]
    return []


def _hit_text(h) -> str:
    if isinstance(h, dict):
        return h.get("text") or ""
    return getattr(h, "text", "") or ""


def _hit_id(h) -> str:
    if isinstance(h, dict):
        return str(h.get("id") or "")
    return str(getattr(h, "id", "") or "")


def _intent_need_tokens(question: str, chunks) -> set[str]:
    blob = " ".join(_hit_text(h) for h in chunks or [])
    found = set(tokenize(blob))
    qtoks = set(tokenize(question or ""))
    need: set[str] = set()
    missing = _needed_benefit_slots(question) - _best_official_slots(chunks)
    if missing:
        need.add("roundtrip")
        if "pass" in missing:
            need.update({"pass", "conference"})
        if "flight" in missing:
            need.update({"flight", "roundtrip"})
        if "hotel" in missing:
            need.add("hotel")
    if _DURATION_QUESTION.search(question or "") and "additional" not in found:
        need.update({"additional", "properties"})
    if slot_of(question or "") == "accessibility_request_deadline":
        days = {
            (f[1], f[2])
            for h in chunks or []
            for f in facts(_hit_text(h))
            if f and f[0] == "date"
        }
        if len(days) < 2:
            need.update({"november", "received", "14th"})
    if qtoks & _STUDENT_ISH and not (found & {"student", "students", "university"}):
        need.update({"university", "student", "21"})
    if (qtoks & _ELIG_ISH or qtoks & _STUDENT_ISH) and "21" not in found:
        need.update({"21", "years", "age"})
    # Venue/campus travel-buffer paraphrases often retrieve accessible-transport instead.
    if _DURATION_QUESTION.search(question or "") and not (
        found & {"additional", "30", "45", "minutes", "properties"}
    ):
        need.update({"additional", "properties", "minutes", "venues"})
    return need


def _splice_intent_chunks(question: str, hits: list[dict], chosen: list[dict]) -> list[dict]:
    """Keep lower-ranked retrieved units that carry missing intent facts (live grant_11 / venue_02)."""
    need = _intent_need_tokens(question, chosen)
    if not need:
        return chosen
    have = {h.get("id") for h in chosen}
    extra: list[dict] = []

    def _coverage_rank(h) -> int:
        doc = (h.get("doc_id") or "").lower()
        text = _hit_text(h).lower()
        if "abw-terms" in doc or "roundtrip" in text or "program benefits" in text:
            return 0
        if "abw-grant" in doc:
            return 1
        if "faqs-" in doc:
            return 3
        return 2

    ranked_hits = list(hits or [])
    if _grant_coverage_intent(question):
        ranked_hits.sort(key=_coverage_rank)
    for h in ranked_hits:
        hid = h.get("id")
        if hid in have:
            continue
        if set(tokenize(_hit_text(h))) & need:
            extra.append(h)
            have.add(hid)
        if len(extra) >= 3:
            break
    if not extra:
        return chosen
    keep, spare = [], []
    for h in chosen:
        (keep if set(tokenize(_hit_text(h))) & need else spare).append(h)
    out: list[dict] = []
    seen: set = set()
    for h in keep + extra + spare:
        hid = h.get("id")
        if hid in seen:
            continue
        seen.add(hid)
        out.append(h)
        if len(out) >= 8:
            break
    official = [c for c in out if c.get("source_type") == "official"]
    primary_ids = {c["id"] for c in (official[:3] or out[:2])}
    for h in out:
        h["primary"] = h.get("id") in primary_ids
    return out


def _expand_query(question: str) -> str:
    extra: list[str] = []
    seen = set(tokenize(question or ""))
    for t in tokenize(question or ""):
        for e in EXPAND.get(t, []):
            if e not in seen and e not in _SALVAGE_BRAND:
                seen.add(e)
                extra.append(e)
    if not extra:
        return ""
    return f"{question} {' '.join(extra[:12])}"


def _top_up_hits(retriever, question: str, hits, event_year: int, include_alumni: bool):
    """One extra retrieve when intent facts (benefits, buffer, second deadline) are missing."""
    if retriever is None:
        return hits
    blob = " ".join(_hit_text(h) for h in (hits or [])[:8])
    found = set(tokenize(blob))
    qtoks = set(tokenize(question or ""))
    extra = []
    coverage_missing = _needed_benefit_slots(question) - _best_official_slots(hits)
    if coverage_missing:
        # Provenance query: FAQs match "pass"/"hotel"; Terms match Program Benefits + roundtrip.
        extra.extend(
            ["All", "Builders", "Welcome", "Grant", "Program", "Benefits", "roundtrip"]
        )
        if "pass" in coverage_missing:
            extra.extend(["conference", "pass"])
        if "flight" in coverage_missing:
            extra.extend(["roundtrip", "flight"])
        if "hotel" in coverage_missing:
            extra.extend(["hotel", "accommodations"])
    # Getting-around "properties" is shuttle text, not the agenda buffer sentence (live venue_02).
    # Campus/transit paraphrases similarly drift to accessible-transportation FAQs.
    # F19: trigger on the absence of a *travel-minutes* statement, not on any "minutes"
    # token (the seat-release "ten minutes prior" FAQ satisfied the old check), and do
    # not put expected answer numbers into the query.
    if _DURATION_QUESTION.search(question or "") and not any(
        travel_minute_values(_hit_text(h)) for h in (hits or [])[:8]
    ):
        extra.extend(
            ["allow", "minutes", "between", "venues", "properties", "travel", "time", "sessions", "schedule"]
        )
    date_gap = False
    a11y_deadline = slot_of(question or "") == "accessibility_request_deadline"
    if not a11y_deadline:
        # Timing paraphrases ("arrive", "cutoff", "last day", "ASL") must still pull both dates.
        ql = (question or "").lower()
        if any(k in ql for k in ("accessib", "asl", "accommodat")) and any(
            k in ql for k in ("arrive", "cutoff", "deadline", "last day", "by when", "when must", "request")
        ):
            a11y_deadline = True
    if a11y_deadline:
        days = {
            (f[1], f[2])
            for h in hits or []
            for f in facts(_hit_text(h))
            if f and f[0] == "date"
        }
        date_gap = len(days) < 2
        if date_gap:
            extra.extend(["received", "by", "November", "14th", "Nov.", "13", "deadline"])
    if qtoks & _STUDENT_ISH and not (found & {"student", "students", "university"}):
        extra.extend(["university", "student", "21", "years", "age"])
    if (qtoks & _ELIG_ISH or qtoks & _STUDENT_ISH) and "21" not in found:
        extra.extend(["21", "years", "age", "eligible", "university", "student"])
    if qtoks & {"reapply", "rejected", "previous", "previously", "again"} and "reapply" not in found:
        extra.extend(["reapply", "subsequent", "cohorts", "not selected"])
    extra_toks = set()
    for t in tokenize(question or ""):
        extra_toks.update(EXPAND.get(t, []))
    extra_toks -= _SALVAGE_BRAND | _STOP | INDEX_STOP
    missing_expand = bool(extra_toks) and not (extra_toks & found)
    if not extra and not missing_expand and not date_gap:
        return hits
    q2 = _expand_query(question)
    if extra:
        q2 = (q2 or question) + " " + " ".join(extra)
    if not q2 or q2.strip() == (question or "").strip():
        return hits
    try:
        more = retriever.retrieve(
            q2, event_year=event_year, include_alumni=include_alumni, k=8
        )
    except Exception:
        return hits
    seen = {_hit_id(h) for h in hits or []}
    out = list(hits or [])
    for h in more or []:
        hid = _hit_id(h)
        if hid and hid not in seen:
            seen.add(hid)
            out.append(h)
    return out


def _sibling_list_claims(question: str, claims: list, active: list, retriever) -> list[dict]:
    """Bind other list items in an already-verified span (pass bullet → flight/hotel, B → A)."""
    if not claims or not active:
        return []
    # Same-fact synonyms (airfare/flight), not retrieval EXPAND (pay→hotel).
    focus = _focus_tokens(question or "")
    if not focus:
        for t in tokenize(question or ""):
            if t in _STOP:
                continue
            focus.update(EXPAND.get(t, []))
            if t not in _SALVAGE_BRAND:
                focus.add(t)
        focus -= _SALVAGE_BRAND
    have = {(c.get("quote") or "").strip() for c in claims}
    have.update((c.get("text") or "").strip() for c in claims)
    extra: list[dict] = []
    for cl in claims:
        pi, chunk = None, None
        doc = (cl.get("citation") or {}).get("doc_id")
        if doc:
            for i, c in enumerate(active):
                if c.get("doc_id") == doc:
                    pi, chunk = i, c
                    break
        if chunk is None:
            pi, chunk = _resolve_chunk(
                {"quote": cl.get("quote") or "", "text": cl.get("text") or "", "source": ""},
                active,
            )
        if chunk is None:
            continue
        page = evidence_page(chunk, active, retriever)
        loc = locate(cl.get("quote") or "", page)
        snapped = ""
        if loc:
            s, e = expand_list_span(page, loc, bullets=True)
            snapped = page[s:e]
        if not snapped or not _looks_structured_list(snapped):
            snapped, _span = align_quote(cl.get("quote") or "", page)
        if not snapped or not _looks_structured_list(snapped):
            continue
        src = f"P{pi + 1}.U0" if pi is not None else None
        for line in snapped.splitlines():
            line = line.strip().rstrip(";")
            if len(line) < 24 or len(line) > 400:
                continue
            if line in have or any(h and (h in line or line in h) for h in have):
                continue
            if re.search(r"#{2,}", line) or llm_answer_is_dump(line):
                continue
            if line.endswith(":") and len(line) < 120:
                continue
            utoks = set(tokenize(line))
            if not (focus & utoks):
                continue
            extra.append(dict(text=line, source=src, quote=line, added_by="list_sibling"))
            have.add(line)
            if len(extra) >= 6:
                return extra
    return extra


def _question_want_facts(question: str) -> set[str]:
    focus = _focus_tokens(question or "")
    if not focus:
        for t in tokenize(question or ""):
            if t in _STOP:
                continue
            focus.update(EXPAND.get(t, []))
            if t not in _SALVAGE_BRAND:
                focus.add(t)
        focus -= _SALVAGE_BRAND
    want = focus & _SALVAGE_FACTS
    qtoks = set(tokenize(question or ""))
    if qtoks & _STUDENT_ISH:
        want.add("21")
    if qtoks & _ELIG_ISH or qtoks & _STUDENT_ISH:
        want.update({"21", "student", "university", "previously", "employee"})
    if qtoks & {"reapply", "rejected", "again"}:
        want.update({"reapply", "subsequent"})
    slot_toks = {"pass": "pass", "flight": "flight", "hotel": "hotel"}
    for slot in _needed_benefit_slots(question):
        want.add(slot_toks[slot])
        if slot == "flight":
            want.add("roundtrip")
    return want


def _benefit_list_doc(question: str, active: list) -> str | None:
    """Official doc whose retrieved text names the most benefit slots (>= 2) for a coverage ask."""
    if not _grant_coverage_intent(question):
        return None
    by_doc: dict[str, set[str]] = {}
    for c in active or []:
        if c.get("source_type") != "official":
            continue
        doc = canonical_doc_id(c.get("doc_id") or "")
        units = [u for u in _atomic_units(c.get("text") or "") if _is_program_benefit_unit(u)]
        for u in units:
            by_doc.setdefault(doc, set()).update(_slots_from_found(set(tokenize(u))))
    best, best_n = None, 1
    for doc, slots in by_doc.items():
        if len(slots) > best_n:
            best, best_n = doc, len(slots)
    return best


def _fill_missing_fact_claims(question: str, claims: list, active: list, retriever) -> list[dict]:
    """Bind short official units for in-scope facts the LLM/list-walk missed (live grant_02/14)."""
    want = _question_want_facts(question)
    if not want:
        return []
    have = set()
    have_quotes = set()
    for c in claims or []:
        have |= set(tokenize((c.get("text") or "") + " " + (c.get("quote") or "")))
        have_quotes.add((c.get("quote") or "").strip())
    missing = {t for t in want if t not in have}
    # F19: for coverage asks, a benefit slot counts as present only when a claim from the
    # official document that lists the benefits states it. "re:Play pass" or "hotel
    # confirmation email" claims from other FAQs no longer hide a missing list item.
    benefit_doc = _benefit_list_doc(question, active)
    if benefit_doc:
        doc_have: set[str] = set()
        for c in claims or []:
            if canonical_doc_id((c.get("citation") or {}).get("doc_id") or "") == benefit_doc:
                doc_have |= set(tokenize((c.get("text") or "") + " " + (c.get("quote") or "")))
        slot_tokens = {"pass", "flight", "roundtrip", "hotel"} & want
        missing |= {t for t in slot_tokens if t not in doc_have}
    if not missing:
        return []
    extra: list[dict] = []
    for pi, c in enumerate(active or []):
        if c.get("source_type") != "official":
            continue
        if benefit_doc and canonical_doc_id(c.get("doc_id") or "") != benefit_doc and not (missing - {"pass", "flight", "roundtrip", "hotel"}):
            continue
        page = evidence_page(c, active, retriever)
        seen_pieces: set[str] = set()
        for piece in _atomic_units(page) + _atomic_units(c.get("text") or ""):
            if piece in seen_pieces:
                continue
            seen_pieces.add(piece)
            if piece in have_quotes or any(h and (h in piece or piece in h) for h in have_quotes if h):
                continue
            if re.search(r"#{2,}", piece) or llm_answer_is_dump(piece):
                continue
            if _grant_coverage_intent(question) and not _is_program_benefit_unit(piece):
                continue
            utoks = set(tokenize(piece))
            hit = missing & utoks
            if not hit:
                continue
            extra.append(
                dict(text=piece, source=f"P{pi + 1}.U0", quote=piece, added_by="missing_fact")
            )
            have_quotes.add(piece)
            missing -= hit
            if not missing or len(extra) >= 6:
                return extra
    return extra


def _duration_evidence_claims(question: str, claims: list, active: list, retriever) -> list[dict]:
    """Venue travel-time asks: bind official units that state travel minutes between
    venues when no verified claim carries them yet (live stress_16/17/26 bound
    accessible-transport or seat-release text instead). Verification still decides."""
    if not _is_duration_question(question):
        return []
    if _claim_travel_minutes(claims)[0]:
        return []
    have = {(c.get("quote") or "").strip() for c in claims or []}
    extra: list[dict] = []
    for pi, c in enumerate(active or []):
        if c.get("source_type") != "official":
            continue
        for piece in _atomic_units(c.get("text") or ""):
            if piece in have or not travel_minute_values(piece):
                continue
            extra.append(dict(text=piece, source=f"P{pi + 1}.U0", quote=piece, added_by="travel_minutes"))
            have.add(piece)
            if len(extra) >= 2:
                return extra
    return extra


_SALVAGE_BRAND = {
    "grant", "abw", "aws", "all", "builders", "welcome", "program", "reinvent", "event",
}
# Salvage ranking only. "conference" stays FACTISH for entailment (conference pass)
# but must not hide travel-buffer units that never say "conference".
_SALVAGE_FACTS = {
    "hotel", "lodging", "flight", "roundtrip", "airfare", "student", "students",
    "suite", "pass", "deadline", "eligible", "university", "21", "previously",
}


def _short_evidence_claims(question: str, chunks: list[dict]) -> list[dict]:
    """Last resort: short retrieved units that overlap the question.

    Used only when the LLM produced no verified claim. Units stay sentence/bullet
    sized so Terms dumps never become the answer. Score expanded question facts
    (pass/flight/hotel, student, deadline) above brand-name overlap so marketing
    paragraphs do not beat the supporting bullets.
    """
    qtoks = [t for t in tokenize(question) if t not in _STOP]
    focus: set[str] = set()
    for t in qtoks:
        focus.update(EXPAND.get(t, []))
        if t not in _SALVAGE_BRAND:
            focus.add(t)
    focus -= _SALVAGE_BRAND
    scored: list[tuple[float, int, int, str]] = []
    for pi, c in enumerate(chunks or []):
        if c.get("source_type") != "official":
            continue
        pieces: list[tuple[int, str]] = []
        for ui, t in unit_texts(c):
            atoms = _atomic_units(t)
            if atoms:
                pieces.extend((ui, p) for p in atoms)
            elif 24 <= len(t) <= 400:
                pieces.append((ui, t))
        if not pieces:
            pieces = [(0, p) for p in _atomic_units(c.get("text") or "")]
        for ui, t in pieces:
            if len(t) < 24 or len(t) > 400:
                continue
            if re.search(r"#{2,}", t) or llm_answer_is_dump(t):
                continue
            if _grant_coverage_intent(question) and not _is_program_benefit_unit(t):
                continue
            n = _overlap(question, t)
            if n <= 0:
                continue
            utoks = set(tokenize(t))
            n_focus = len(focus & utoks)
            if n_focus <= 0:
                continue
            n_fact = len((focus & _SALVAGE_FACTS) & utoks)
            score = (n_focus * 8 + n_fact * 4 + n) / max(len(t) / 100.0, 1.0)
            scored.append((score, n_fact, pi, ui, t))
    scored.sort(key=lambda row: -row[0])
    qtoks = set(tokenize(question or ""))
    cap = 6 if qtoks & (_ELIG_ISH | _STUDENT_ISH | {"reapply"}) else 4
    out = []
    for _n, _nf, pi, ui, t in scored[:cap]:
        out.append(dict(text=t, source=f"P{pi + 1}.U{ui}", quote=t, added_by="short_unit"))
    return out


def _quoted_date_days(items) -> set[tuple]:
    days: set[tuple] = set()
    for cl in items or []:
        blob = f"{cl.get('quote') or ''} {cl.get('text') or ''}"
        for f in facts(blob):
            if f and f[0] == "date":
                days.add((f[1], f[2]))
    return days


def _conflict_date_snippets(res, active, retriever, already) -> list[dict]:
    """Sentence quotes for conflict dates missing from claims (live access duplicate Nov13).

    Search the full evidence page / chunk text, not unit_texts: FAQ November 14th sits
    after a long service list and was never a dropped claim (locate-prefix was not the miss).
    """
    if res.get("outcome") != "unresolved_contradiction":
        return []
    conflict_ids = {
        x
        for p in res.get("pairs") or []
        if p.get("outcome") == "unresolved_contradiction"
        for x in (p.get("a"), p.get("b"))
        if x
    }
    needed_by_id: dict[str, list] = {}
    for p in res.get("pairs") or []:
        if p.get("outcome") != "unresolved_contradiction":
            continue
        for fa, fb in p.get("clash") or []:
            if fa and fa[0] == "date":
                needed_by_id.setdefault(p["a"], []).append(fa)
            if fb and fb[0] == "date":
                needed_by_id.setdefault(p["b"], []).append(fb)
    quoted = _quoted_date_days(already)
    extra: list[dict] = []
    for pi, c in enumerate(active or []):
        if c.get("id") not in conflict_ids:
            continue
        needed = needed_by_id.get(c["id"]) or []
        page = evidence_page(c, active, retriever) or (c.get("text") or "")
        targets = list(needed) or [f for f in facts(page) if f and f[0] == "date"]
        seen_here: set[tuple] = set()
        for fact in targets:
            if not fact or fact[0] != "date":
                continue
            key = (fact[1], fact[2])
            if key in quoted or key in seen_here:
                continue
            hit = phrase_for_date_fact(page, fact) or phrase_for_date_fact(c.get("text") or "", fact)
            if not hit:
                continue
            loc = page.lower().find(hit.lower())
            src_blob = page if loc >= 0 else (c.get("text") or "")
            loc = src_blob.lower().find(hit.lower())
            if loc >= 0:
                span = expand_to_containing_line(src_blob, (loc, loc + len(hit)))
                snippet = (src_blob[span[0] : span[1]] or "").strip()
            else:
                snippet = clip_quote_to_support(hit, src_blob)
            snippet = clip_quote_to_support(hit, snippet or src_blob)
            if str(fact[2]) not in snippet:
                continue
            if len(snippet) > 600:
                snippet = clip_quote_to_support(hit, snippet)
            extra.append(
                dict(
                    text=snippet,
                    source=f"P{pi + 1}.U0",
                    quote=snippet,
                    added_by="conflict_date",
                )
            )
            quoted.add(key)
            seen_here.add(key)
    return extra


def _dedupe_same_date_claims(claims: list) -> list:
    """Keep the longer quote when two claims repeat the same calendar day from one doc."""
    out: list = []
    index: dict[tuple, int] = {}
    for c in claims or []:
        days = [
            (f[1], f[2])
            for f in facts(f"{c.get('quote') or ''} {c.get('text') or ''}")
            if f and f[0] == "date"
        ]
        if not days:
            out.append(c)
            continue
        doc = (c.get("citation") or {}).get("doc_id") or ""
        key = (days[0], doc)
        prev = index.get(key)
        if prev is None:
            index[key] = len(out)
            out.append(c)
            continue
        if len(c.get("quote") or "") > len(out[prev].get("quote") or ""):
            out[prev] = c
    return out


def _room_type_unspecified(question: str, claims: list) -> bool:
    """True when the user asked about room type/suite and no claim actually says so."""
    q = (question or "").lower()
    if not any(k in q for k in ("suite", "room type", "own room", "upgrade")):
        return False
    blob = " ".join((c.get("text") or "") + " " + (c.get("quote") or "") for c in claims or []).lower()
    return not any(k in blob for k in ("suite", "room type", "own room"))


def _collect_verified(raw, active, retriever, question: str | None = None):
    pages: dict[str, str] = {}
    claims, dropped = [], []
    for original in raw:
        cl = normalize_generated_claim(original) if isinstance(original, dict) else {}
        _pi, c = _resolve_chunk(cl, active)
        if c is None:
            dropped.append(dict(original if isinstance(original, dict) else cl, reason="unknown source passage"))
            continue
        key = c["doc_id"]
        if key not in pages:
            pages[key] = evidence_page(c, active, retriever)
        page = pages[key]
        quote = cl.get("quote") or ""
        text = cl.get("text") or ""
        ok, why, span = verify(text, quote, page, question=question)
        if ok:
            aligned = page[span[0] : span[1]] if span else quote
            published = clip_quote_to_support(text, aligned)
            loc = locate(published, page)
            if loc:
                published = page[loc[0] : loc[1]]
                span = loc
            dumpish = bool(re.search(r"#{2,}", text)) or (
                len(text) > 600 and text[:80].strip() == (quote or aligned)[:80].strip()
            )
            citation = _cite(c, span)
            claims.append(
                dict(
                    text=published if dumpish else text,
                    quote=published,
                    citation=citation,
                    citations=[citation],
                    role="answer",
                    alumni_experience=c.get("source_type") == "alumni_experience",
                )
            )
        else:
            dropped.append(dict(cl, reason=why))
    return claims, dropped


def _coverage_slots_missing(question: str, summary: str, claims: list) -> list[str]:
    need = _needed_benefit_slots(question)
    if not need:
        return []
    claim_slots: set[str] = set()
    for c in claims or []:
        claim_slots |= _slots_from_found(
            set(tokenize(f"{c.get('text') or ''} {c.get('quote') or ''}"))
        )
    have = _slots_from_found(set(tokenize(summary or "")))
    return sorted((need & claim_slots) - have)


def _age_21_required_missing(question: str, summary: str, claims: list) -> str | None:
    qtoks = set(tokenize(question or ""))
    studentish = {
        "student", "students", "undergrad", "undergrads", "undergraduate",
        "eligible", "eligibility", "qualify", "qualifies",
    }
    if not (qtoks & studentish):
        return None
    blob = " ".join(f"{c.get('text') or ''} {c.get('quote') or ''}" for c in claims or [])
    if "21" not in set(tokenize(blob)):
        return None
    if "21" in set(tokenize(summary or "")):
        return None
    return "at least 21 years of age"


def _is_duration_question(question: str) -> bool:
    return bool(_DURATION_QUESTION.search(question or ""))


def _claim_travel_minutes(claims: list) -> tuple[set[str], list[str]]:
    vals: set[str] = set()
    texts: list[str] = []
    for c in claims or []:
        v = travel_minute_values(f"{c.get('text') or ''} {c.get('quote') or ''}")
        if v:
            vals |= v
            texts.append((c.get("text") or c.get("quote") or "")[:200])
    return vals, texts


def _travel_minutes_missing(question: str, summary: str, claims: list) -> list[str]:
    """Venue travel-time asks: when a verified claim states the minutes, the answer must
    state them too (live d55b08d venue answers said only "allow additional time").
    Returns the claim texts to include; [] when satisfied or not applicable."""
    if not _is_duration_question(question):
        return []
    vals, texts = _claim_travel_minutes(claims)
    if not vals:
        return []
    have = set(re.findall(r"\d+", summary or ""))
    if vals & have:
        return []
    return texts


def _core_gate_missing(question: str, summary: str, claims: list) -> list[str]:
    """Owner-required facts that no published summary may omit (age 21, in-scope
    benefits, documented travel minutes). Returns notes for the rewrite prompt."""
    out: list[str] = []
    m21 = _age_21_required_missing(question, summary, claims)
    if m21:
        out.extend(_claim_texts_with(claims, "21") or [m21])
    out.extend(_coverage_slots_missing(question, summary, claims))
    out.extend(_travel_minutes_missing(question, summary, claims))
    return out


def _claim_texts_with(claims: list, token: str) -> list[str]:
    out = []
    for c in claims or []:
        if token in set(tokenize(f"{c.get('text') or ''} {c.get('quote') or ''}")):
            out.append((c.get("text") or c.get("quote") or "")[:200])
    return out[:2]


def _accept_rewrite(
    cand: str | None,
    question: str,
    claims: list,
    dropped: list,
    conflict_ctx: dict | None = None,
) -> tuple[str | None, list[str]]:
    """Return (accepted summary, omitted-fact notes). Invention fails drop the candidate."""
    if not cand:
        return None, []
    if llm_answer_is_dump(cand):
        dropped.append(dict(text=cand[:400], source="answer", quote="", reason="answer copied retrieved passages"))
        return None, []
    if conflict_ctx:
        if is_canned_conflict_lead(cand):
            dropped.append(dict(text=cand, source="answer", quote="", reason="conflict summary is a canned template"))
            return None, []
        ok, why = verify_conflict_summary(
            cand,
            claims,
            conflict_ctx.get("pairs"),
            conflict_ctx.get("chunks"),
        )
        if not ok:
            dropped.append(dict(text=cand, source="answer", quote="", reason=why))
            tokens = conflict_value_tokens(claims, conflict_ctx.get("pairs"), conflict_ctx.get("chunks"))
            missing = [t for t in tokens[:2] if t not in (cand or "")]
            return None, missing or [why]
        ok2, why2 = verify_summary(
            cand,
            [cl["quote"] for cl in claims],
            [cl["text"] for cl in claims],
            question=question,
            allow_uncertainty_negation=True,
        )
        if not ok2:
            dropped.append(dict(text=cand, source="answer", quote="", reason=why2))
            return None, []
        return cand, []
    ok, why = verify_summary(
        cand,
        [cl["quote"] for cl in claims],
        [cl["text"] for cl in claims],
        question=question,
    )
    if not ok:
        dropped.append(dict(text=cand, source="answer", quote="", reason=why))
        return None, []
    okc, whyc = summary_covers_question(question, cand, claims)
    if not okc:
        # Hard reject: question-scoped relevant claims must be represented. Omitted
        # texts feed the next bounded rewrite prompt; the candidate is not accepted.
        dropped.append(dict(text=cand, source="answer", quote="", reason=whyc))
        return None, omitted_claim_texts(question, cand, claims)
    miss21 = _age_21_required_missing(question, cand, claims)
    if miss21:
        dropped.append(dict(text=cand, source="answer", quote="", reason="summary omits age 21 from verified criteria"))
        return None, _claim_texts_with(claims, "21") or [miss21]
    miss_slots = _coverage_slots_missing(question, cand, claims)
    if miss_slots:
        dropped.append(
            dict(text=cand, source="answer", quote="", reason=f"summary omits in-scope benefits {miss_slots}")
        )
        return None, miss_slots
    miss_min = _travel_minutes_missing(question, cand, claims)
    if miss_min:
        dropped.append(
            dict(text=cand, source="answer", quote="", reason="summary omits the documented travel minutes")
        )
        return None, miss_min
    return cand, []


def _summary_slot_count(question: str, summary: str, claims: list) -> int:
    need = _needed_benefit_slots(question)
    if not need:
        return 0
    have = _slots_from_found(set(tokenize(summary or "")))
    return len(need & have)


def _candidate_quality(question: str, summary: str, claims: list) -> tuple[int, int, int, int]:
    """Rank rewrite candidates: age-21, benefit slots + travel minutes, question-scope covers, slot count."""
    if not summary:
        return (0, 0, 0, 0)
    age_ok = 0 if _age_21_required_missing(question, summary, claims) else 1
    miss = _coverage_slots_missing(question, summary, claims) + _travel_minutes_missing(question, summary, claims)
    slots_ok = 0 if miss else 1
    covers_ok = 1 if summary_covers_question(question, summary, claims)[0] else 0
    n = _summary_slot_count(question, summary, claims)
    return (age_ok, slots_ok, covers_ok, n)


def _rewrite_from_verified_claims(
    gen,
    question: str,
    claims: list,
    dropped: list,
    gen_error,
    conflict_ctx: dict | None = None,
) -> str | None:
    """Bounded LLM rewrite from the question plus verified claim text and quotes.

    Attempts 1-2: answer from the verified claims (attempt 2 is told what attempt 1
    omitted). Attempt 3 (F19 coverage repair): when every draft was hard-rejected for
    omitting verified facts, the LLM gets the missing claim texts (listed first, never
    hidden by the row cap) plus its rejected draft. Attempt 4 (final): the closest
    rejected draft (fewest omissions, invention-free) and exactly what it omitted; the
    LLM writes any caveat itself. Every candidate still passes `_accept_rewrite`
    (invention, full question coverage, age 21, in-scope benefits, travel minutes).
    Nothing that fails coverage is returned; the caller refuses instead.
    """
    writer = getattr(gen, "short_answer", None)
    if not callable(writer) or _timeout_error(gen_error):
        return None
    best = None
    best_q = (-1, -1, -1, -1)
    omitted = None
    last_rejected = None
    closest = None  # (n_omitted, draft, omitted) among invention-free coverage rejects

    def _call(**kw):
        try:
            return writer(question, claims, **kw)
        except TypeError:
            kw.pop("must_include", None)
            kw.pop("previous", None)
            kw.pop("final", None)
            try:
                return writer(question, claims, omitted=kw.get("omitted"), conflict=kw.get("conflict", False))
            except TypeError:
                return writer(question, claims, omitted=kw.get("omitted"))

    for attempt in (1, 2, 3, 4):
        if attempt >= 3:
            # Coverage repair only after a hard reject that named missing verified facts.
            if conflict_ctx or not omitted:
                break
            if attempt == 3:
                kw = dict(omitted=None, conflict=False, must_include=list(omitted), previous=last_rejected)
            else:
                if closest is None:
                    break
                kw = dict(
                    omitted=None, conflict=False, must_include=list(closest[2]), previous=closest[1], final=True
                )
        else:
            kw = dict(omitted=omitted, conflict=bool(conflict_ctx))
        try:
            cand = _call(**kw)
        except Exception as e:
            dropped.append(
                dict(text="", source="answer", quote="", reason=f"short_answer: {type(e).__name__}: {str(e)[:160]}")
            )
            break
        accepted, omitted_now = _accept_rewrite(cand, question, claims, dropped, conflict_ctx=conflict_ctx)
        if conflict_ctx:
            if accepted:
                return accepted
            omitted = omitted_now
            continue
        if accepted:
            q = _candidate_quality(question, accepted, claims)
            if q > best_q:
                best, best_q = accepted, q
            if q[0] and q[1] and q[2]:
                return accepted
            continue
        if cand and omitted_now:
            last_rejected = cand
            # Closest draft for the final repair prompt only (never published as-is).
            if verify_summary(
                cand, [cl["quote"] for cl in claims], [cl["text"] for cl in claims], question=question
            )[0] and not llm_answer_is_dump(cand):
                miss = list(dict.fromkeys(
                    [*omitted_claim_texts(question, cand, claims), *_core_gate_missing(question, cand, claims)]
                ))
                if miss and (closest is None or len(miss) < closest[0]):
                    closest = (len(miss), cand, miss)
            # Union keeps facts named by every rejection (age 21 + student criterion).
            omitted = list(dict.fromkeys([*(omitted or []), *omitted_now]))
            continue
        if not omitted_now:
            # Invention/dump reject: the next attempt starts clean.
            continue
    if conflict_ctx:
        return None
    cand = best
    if not cand:
        return None
    if _core_gate_missing(question, cand, claims):
        return None
    if not summary_covers_question(question, cand, claims)[0]:
        return None
    return cand


def _unspecified_llm_answer(gen, question: str, claims: list, dropped: list, gen_error, first: str | None):
    """LLM-written 'documents don't specify' answer, validated by verify_unspecified_summary."""
    cands = []
    if first and not llm_answer_is_dump(first):
        cands.append(first)
    tried = 0
    writer = getattr(gen, "short_answer", None)
    for cand in cands:
        ok, why = verify_unspecified_summary(cand, claims, question)
        if ok:
            return cand
        dropped.append(dict(text=cand, source="answer", quote="", reason=why))
    if not callable(writer) or _timeout_error(gen_error):
        return None
    detail = "the specific room-type detail the question asks about"
    while tried < 2:
        tried += 1
        try:
            try:
                cand = writer(question, claims, unspecified=detail)
            except TypeError:
                cand = writer(question, claims)
        except Exception as e:
            dropped.append(
                dict(text="", source="answer", quote="", reason=f"short_answer: {type(e).__name__}: {str(e)[:160]}")
            )
            return None
        if not cand or llm_answer_is_dump(cand):
            continue
        ok, why = verify_unspecified_summary(cand, claims, question)
        if ok:
            return cand
        dropped.append(dict(text=cand, source="answer", quote="", reason=why))
    return None


def _log_unanswered(store: Store, question: str, reason: str, event_year: int, conversation_id=None):
    try:
        store.add_unanswered(
            dict(
                question=question,
                reason=reason,
                event_year=event_year,
                conversation_id=conversation_id,
                source="system_refusal",
            )
        )
    except Exception:
        pass


def ask(
    question: str,
    profile: dict | None = None,
    mode: str | None = None,
    *,
    retriever: Retriever | None = None,
    store: Store | None = None,
    generator=None,
    history=None,
    llm_budget_s=None,
    topic_hint=None,
    conversation_id=None,
) -> dict[str, Any]:
    t0 = time.time()
    profile = dict(profile or {})
    profile.setdefault("event_year", DEFAULT_EVENT_YEAR)
    profile.setdefault("include_alumni", True)
    profile.setdefault("role", "grantee")
    event_year = int(profile["event_year"])
    include_alumni = bool(profile.get("include_alumni", True))
    retriever = retriever or get_retriever()
    store = store or get_store()

    base = dict(
        question=question,
        profile=profile,
        claims=[],
        dropped=[],
        notes=[],
        summary=None,
        kind="answer",
        retrieval=retriever.name,
    )
    kind = smalltalk.classify(question)
    if kind == "greeting":
        msg, sugg = smalltalk.reply("greeting")
        return scrub_s3_uris(dict(
            base,
            kind="greeting",
            refused=False,
            refusal=None,
            outcome=None,
            generator=None,
            message=msg,
            suggestions=sugg,
            latency_ms=int((time.time() - t0) * 1000),
        ))
    if kind == "task_request":
        msg, sugg = smalltalk.task_reply(
            question,
            _topics(question, topic_hint),
            _answerable(retriever, event_year, include_alumni),
        )
        return scrub_s3_uris(dict(
            base,
            kind="task_request",
            refused=True,
            refusal_reason="task_request",
            refusal="Task request: the assistant answers questions, it does not send email or fill forms.",
            outcome=None,
            generator=None,
            message=msg,
            suggestions=sugg,
            latency_ms=int((time.time() - t0) * 1000),
        ))

    hits_p = retriever.retrieve(question, event_year=event_year, include_alumni=include_alumni, k=16)
    hits_p = _top_up_hits(retriever, question, hits_p, event_year, include_alumni)
    hits = [p.as_dict() if hasattr(p, "as_dict") else dict(p) for p in hits_p]
    best = hits_p[0].score if hits_p else 0.0
    supported = bool(hits_p) and best >= MIN_SCORE and _lexical_support(question, hits_p)

    if kind == "maybe_off_topic" and (not supported or best < OFF_TOPIC_SCORE):
        msg, sugg = smalltalk.reply("off_topic")
        return scrub_s3_uris(dict(
            base,
            kind="off_topic",
            refused=False,
            refusal=None,
            outcome=None,
            generator=None,
            message=msg,
            suggestions=sugg,
            latency_ms=int((time.time() - t0) * 1000),
        ))
    if not supported:
        out = dict(
            base,
            refused=True,
            outcome=None,
            generator=None,
            refusal="I couldn't find this in the documents that apply to you.",
        )
        _friendly_refusal(out, "no_support", question, retriever, event_year, include_alumni, topic_hint, hits_p)
        _log_unanswered(store, question, "no_support", event_year, conversation_id)
        out["latency_ms"] = int((time.time() - t0) * 1000)
        return scrub_s3_uris(out)

    topic, chunks = select_chunks(question, [dict(h) for h in hits])
    if _grant_coverage_intent(question):
        topic = "grant"
    chunks = _splice_intent_chunks(question, [dict(h) for h in hits], chunks)
    # Accessibility deadline paraphrases must keep both Nov 13 and Nov 14 evidence in play
    # before resolve, or the conflict path never starts (live stress access onesided).
    if slot_of(question or "") == "accessibility_request_deadline" or (
        any(k in (question or "").lower() for k in ("accessib", "asl", "accommodat"))
        and any(k in (question or "").lower() for k in ("arrive", "cutoff", "deadline", "last day", "by when", "when must", "request"))
    ):
        days = {
            (f[1], f[2])
            for h in chunks
            for f in facts(_hit_text(h))
            if f and f[0] == "date"
        }
        if len(days) < 2:
            have = {h.get("id") for h in chunks}
            for h in hits:
                if h.get("id") in have:
                    continue
                hdays = {
                    (f[1], f[2])
                    for f in facts(_hit_text(h))
                    if f and f[0] == "date"
                }
                if hdays - days:
                    chunks.append(h)
                    have.add(h.get("id"))
                    days |= hdays
                if len(days) >= 2 or len(chunks) >= 8:
                    break
            official = [c for c in chunks if c.get("source_type") == "official"]
            primary_ids = {c["id"] for c in (official[:3] or chunks[:2])}
            for h in chunks:
                h["primary"] = h.get("id") in primary_ids
    if _is_duration_question(question) and not any(travel_minute_values(_hit_text(h)) for h in chunks):
        have_ids = {h.get("id") for h in chunks}
        for h in hits:
            if h.get("id") not in have_ids and h.get("source_type") == "official" and travel_minute_values(_hit_text(h)):
                chunks.insert(0, h)
                break
    res = resolve(chunks, topic, question=question)
    active = [c for c in chunks if c["id"] not in res["suppressed"]]
    # Official text that was suppressed only because of alumni never stays suppressed that way
    # (resolve already drops alumni). Keep official active always unless superseded.

    gen = generator or get_generator(mode)
    if llm_budget_s is not None and hasattr(gen, "budget_s"):
        gen.budget_s = llm_budget_s
    gen_error = None
    try:
        raw = gen.claims(question, profile, active, history=history) if history else gen.claims(question, profile, active)
    except Exception as e:
        gen_error = f"{type(e).__name__}: {str(e)[:300]}"
        raw = []

    raw = [bind_claim_source(cl, active) for cl in raw if isinstance(cl, dict)]

    raw.extend(_conflict_date_snippets(res, active, retriever, raw))

    claims, dropped = _collect_verified(raw, active, retriever, question=question)
    llm_had_claims = bool(claims)
    if not claims and not _timeout_error(gen_error):
        salvage = _short_evidence_claims(question, active)
        extra, extra_dropped = _collect_verified(salvage, active, retriever, question=question)
        dropped.extend(extra_dropped)
        if extra:
            dropped.append(
                dict(
                    text="",
                    source="salvage",
                    quote="",
                    reason="llm claims empty; bound short retrieved units",
                )
            )
            claims = extra

    siblings = _sibling_list_claims(question, claims, active, retriever)
    if siblings:
        more, more_dropped = _collect_verified(siblings, active, retriever, question=question)
        dropped.extend(more_dropped)
        seen_q = {(c.get("quote") or "").strip() for c in claims}
        for c in more:
            q = (c.get("quote") or "").strip()
            if q and q not in seen_q:
                claims.append(c)
                seen_q.add(q)

    missing_facts = _fill_missing_fact_claims(question, claims, active, retriever)
    if missing_facts:
        more, more_dropped = _collect_verified(missing_facts, active, retriever, question=question)
        dropped.extend(more_dropped)
        seen_q = {(c.get("quote") or "").strip() for c in claims}
        for c in more:
            q = (c.get("quote") or "").strip()
            if q and q not in seen_q:
                claims.append(c)
                seen_q.add(q)

    date_fill = _conflict_date_snippets(res, active, retriever, claims)
    if date_fill:
        more, more_dropped = _collect_verified(date_fill, active, retriever, question=question)
        dropped.extend(more_dropped)
        seen_q = {(c.get("quote") or "").strip() for c in claims}
        for c in more:
            q = (c.get("quote") or "").strip()
            if q and q not in seen_q:
                claims.append(c)
                seen_q.add(q)
    travel = _duration_evidence_claims(question, claims, active, retriever)
    if travel:
        more, more_dropped = _collect_verified(travel, active, retriever, question=question)
        dropped.extend(more_dropped)
        seen_q = {(c.get("quote") or "").strip() for c in claims}
        for c in more:
            q = (c.get("quote") or "").strip()
            if q and q not in seen_q:
                claims.append(c)
                seen_q.add(q)
    claims = _dedupe_same_date_claims(claims)
    # Live grant_13: Bedrock Terms slices often omit the hotel bullet; one more targeted
    # retrieve keeps Program Benefits evidence available for missing-slot fill.
    if _grant_coverage_intent(question):
        need_slots = _needed_benefit_slots(question)
        have_slots: set[str] = set()
        for c in claims:
            have_slots |= _slots_from_found(
                set(tokenize(f"{c.get('text') or ''} {c.get('quote') or ''}"))
            )
        missing_slots = need_slots - have_slots
        if missing_slots and retriever is not None:
            q_bits = ["All Builders Welcome Grant Program Benefits"]
            if "hotel" in missing_slots:
                q_bits.extend(["hotel", "accommodations"])
            if "flight" in missing_slots:
                q_bits.extend(["roundtrip", "flight"])
            if "pass" in missing_slots:
                q_bits.extend(["conference", "pass"])
            try:
                more = retriever.retrieve(
                    " ".join(q_bits),
                    event_year=event_year,
                    include_alumni=include_alumni,
                    k=8,
                )
            except Exception:
                more = []
            more_dicts = [p.as_dict() if hasattr(p, "as_dict") else dict(p) for p in (more or [])]
            if more_dicts:
                active = _splice_intent_chunks(question, more_dicts + [dict(h) for h in active], list(active))
                refill = _fill_missing_fact_claims(question, claims, active, retriever)
                if refill:
                    more_c, more_d = _collect_verified(refill, active, retriever, question=question)
                    dropped.extend(more_d)
                    seen_q = {(c.get("quote") or "").strip() for c in claims}
                    for c in more_c:
                        q = (c.get("quote") or "").strip()
                        if q and q not in seen_q:
                            claims.append(c)
                            seen_q.add(q)
                sib2 = _sibling_list_claims(question, claims, active, retriever)
                if sib2:
                    more_c, more_d = _collect_verified(sib2, active, retriever, question=question)
                    dropped.extend(more_d)
                    seen_q = {(c.get("quote") or "").strip() for c in claims}
                    for c in more_c:
                        q = (c.get("quote") or "").strip()
                        if q and q not in seen_q:
                            claims.append(c)
                            seen_q.add(q)
            claims = _dedupe_same_date_claims(claims)
    if _grant_coverage_intent(question) and claims:
        keep = []
        for c in claims:
            blob = f"{c.get('text') or ''} {c.get('quote') or ''}"
            if _is_program_benefit_unit(blob):
                keep.append(c)
            else:
                dropped.append(dict(c, reason="not a program-benefit unit for this coverage question"))
        if keep:
            claims = keep

    # A sentence whose LLM claims all died must not be kept and re-checked
    # against unrelated salvage quotes (live student false-yes / suite negative).
    summary = getattr(gen, "summary", None) if (gen_error is None and llm_had_claims) else None
    by_id = {c["id"]: c for c in chunks}
    conflict_pairs = [p for p in res["pairs"] if p.get("outcome") == "unresolved_contradiction"]
    conflict_ctx = dict(pairs=conflict_pairs, chunks=by_id) if res["outcome"] == "unresolved_contradiction" else None
    conflict_incomplete = False
    unspecified_answered = False
    if conflict_ctx:
        if conflict_unknown_kind(conflict_pairs):
            if summary:
                dropped.append(
                    dict(text=summary, source="answer", quote="", reason="unsupported conflict kind; not selecting a value")
                )
            summary = None
            conflict_incomplete = True
        else:
            if summary:
                if llm_answer_is_dump(summary) or is_canned_conflict_lead(summary):
                    dropped.append(
                        dict(
                            text=summary[:400],
                            source="answer",
                            quote="",
                            reason="conflict summary dump or canned template",
                        )
                    )
                    summary = None
                else:
                    ok, why = verify_conflict_summary(summary, claims, conflict_pairs, by_id)
                    if ok:
                        ok2, why2 = verify_summary(
                            summary,
                            [cl["quote"] for cl in claims],
                            [cl["text"] for cl in claims],
                            question=question,
                            allow_uncertainty_negation=True,
                        )
                        if not ok2:
                            ok, why = False, why2
                    if not ok:
                        dropped.append(dict(text=summary, source="answer", quote="", reason=why))
                        summary = None
            if not conflict_both_sides_supported(claims, conflict_pairs, by_id):
                if summary:
                    dropped.append(
                        dict(text=summary, source="answer", quote="", reason="conflict missing a verified side")
                    )
                summary = None
                conflict_incomplete = True
            elif not summary and claims:
                summary = _rewrite_from_verified_claims(
                    gen, question, claims, dropped, gen_error, conflict_ctx=conflict_ctx
                )
    elif _room_type_unspecified(question, claims):
        # F19: no verified claim states the asked detail. An LLM answer that says the
        # documents don't specify it (and asserts no permission/prohibition) is the
        # correct answer, not a refusal (live hotel_room_01 draft was discarded).
        summary = _unspecified_llm_answer(gen, question, claims, dropped, gen_error, summary)
        unspecified_answered = bool(summary)
    else:
        if summary:
            if llm_answer_is_dump(summary):
                dropped.append(
                    dict(text=summary[:400], source="answer", quote="", reason="answer copied retrieved passages")
                )
                summary = None
            else:
                ok, why = verify_summary(
                    summary,
                    [cl["quote"] for cl in claims],
                    [cl["text"] for cl in claims],
                    question=question,
                )
                if not ok:
                    dropped.append(dict(text=summary, source="answer", quote="", reason=why))
                    summary = None
                else:
                    okc, whyc = summary_covers_question(question, summary, claims)
                    if not okc:
                        dropped.append(dict(text=summary, source="answer", quote="", reason=whyc))
                        summary = None
                    miss21 = _age_21_required_missing(question, summary or "", claims)
                    if summary and miss21:
                        dropped.append(
                            dict(text=summary, source="answer", quote="", reason="summary omits age 21 from verified criteria")
                        )
                        summary = None
                    miss_min = _travel_minutes_missing(question, summary or "", claims) if summary else []
                    if summary and miss_min:
                        dropped.append(
                            dict(text=summary, source="answer", quote="", reason="summary omits the documented travel minutes")
                        )
                        summary = None
                    miss_slots = _coverage_slots_missing(question, summary or "", claims) if summary else []
                    if summary and miss_slots:
                        dropped.append(
                            dict(
                                text=summary,
                                source="answer",
                                quote="",
                                reason=f"summary omits in-scope benefits {miss_slots}",
                            )
                        )
                        summary = None
        if not summary and claims:
            summary = _rewrite_from_verified_claims(
                gen, question, claims, dropped, gen_error
            )

    notes = []
    for p in res["pairs"]:
        if p["outcome"] == "unresolved_contradiction":
            a, b = by_id[p["a"]], by_id[p["b"]]
            notes.append(
                dict(
                    kind="unresolved_contradiction",
                    text=f"Unresolved contradiction · '{a['title']}' · '{b['title']}'",
                    citations=[_cite(a), _cite(b)],
                )
            )
        elif p["outcome"] in ("explicit_exception", "superseded"):
            w, l = by_id[p["winner"]], by_id[p["loser"]]
            notes.append(
                dict(
                    kind=p["outcome"],
                    text=f"'{w['title']}' governs here over '{l['title']}'.",
                    citations=[_cite(w)],
                )
            )
        elif p["outcome"] == "official_over_alumni":
            w, l = by_id[p["winner"]], by_id[p["loser"]]
            notes.append(
                dict(
                    kind="official_over_alumni",
                    text=(
                        f"Official guidance from '{w['title']}' is shown. "
                        f"'{l['title']}' is personal alumni experience and does not override official guidance."
                    ),
                    citations=[_cite(w), _cite(l)],
                )
            )

    # One callout per conflict pair-set is enough for the UI.
    uniq_notes, seen_notes = [], set()
    for n in notes:
        key = (n["kind"], tuple(sorted((c.get("doc_id") or "") for c in n.get("citations") or [])))
        if key in seen_notes:
            continue
        seen_notes.add(key)
        uniq_notes.append(n)
    notes = uniq_notes

    if any(c.get("source_type") == "alumni_experience" for c in active):
        if not any(n["kind"] == "alumni_experience" for n in notes):
            notes.append(
                dict(
                    kind="alumni_experience",
                    text="Some cited passages are personal alumni experience, not official AWS guidance. They are labeled in the citations.",
                    citations=[
                        _cite(c)
                        for c in active
                        if c.get("source_type") == "alumni_experience"
                    ],
                )
            )

    unspecified = _room_type_unspecified(question, claims) and not unspecified_answered
    if unspecified:
        if summary:
            dropped.append(
                dict(text=summary, source="answer", quote="", reason="docs do not specify room type")
            )
        summary = None
    summary_unverified = False
    if not summary and claims and not unspecified and not conflict_incomplete:
        if callable(getattr(gen, "short_answer", None)) and not _timeout_error(gen_error):
            # An LLM was available and no draft survived verification: refuse honestly
            # rather than publish claims under an empty answer. (Extractive/mock mode and
            # LLM timeouts keep the earlier behavior: claims without an LLM summary.)
            summary_unverified = True
    refused = not claims or unspecified or conflict_incomplete or summary_unverified
    out = dict(
        base,
        claims=claims,
        dropped=dropped,
        notes=notes,
        refused=refused,
        refusal="No claim survived verification, so I won't answer." if refused else None,
        outcome=OUTCOME_LABEL.get(res["outcome"], res["outcome"]),
        outcome_key=res["outcome"],
        topic=topic,
        generator=gen.name,
        generator_error=gen_error,
        summary=summary,
        llm_attempts=getattr(gen, "attempts", None),
        passages=[
            dict(
                id=c["id"],
                title=c["title"],
                section=c["section"],
                source_type=c.get("source_type"),
                event_year=c.get("event_year"),
                suppressed=c["id"] in res["suppressed"],
                score=round(float(c.get("score") or 0), 4),
                primary=bool(c.get("primary")),
            )
            for c in chunks
        ],
        latency_ms=int((time.time() - t0) * 1000),
    )
    if refused:
        if unspecified:
            why = "unspecified"
        elif summary_unverified:
            why = "no_verified_claim"
        elif conflict_incomplete:
            why = "conflict_incomplete"
        else:
            why = "no_verified_claim"
        _friendly_refusal(out, why, question, retriever, event_year, include_alumni, topic_hint, chunks)
        _log_unanswered(store, question, why, event_year, conversation_id)
        out["latency_ms"] = int((time.time() - t0) * 1000)
    return scrub_s3_uris(out)
