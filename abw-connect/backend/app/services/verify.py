"""Claim verification. A matching quote proves the source, not the claim.

1. The quote must correspond to a contiguous span of the stored/retrieved source
   (punctuation, quote style, whitespace, case, and short source-label prefixes
   are ignored; the published quote is snapped back to the source wording).
2. Every count, date fragment, and every period word in the claim must also appear in the quoted span.
A claim failing either check is dropped.
"""
from __future__ import annotations

import re

from .index import STOP as INDEX_STOP
from .textnorm import NUM_WORDS, content_tokens, norm, squash, tokenize

PERIODS = {
    "day": ["day"],
    "week": ["week"],
    "month": ["month"],
    "year": ["year"],
    "hour": ["hour"],
    "minute": ["minute"],
    "night": ["night"],
}

# Leading tokens the model often prepends when copying evidence.
_LABEL_TOKS = {
    "section",
    "part",
    "clause",
    "source",
    "passage",
    "quote",
    "excerpt",
    "unit",
    "according",
    "official",
    "from",
    "per",
    "see",
}


_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_NEG_RE = re.compile(r"\b(?:cannot|can't|can’t|never|not|no)\b", re.I)
MAX_EVIDENCE_CHARS = 480
MAX_LIST_CHARS = 900
_ABBREV_END = re.compile(
    r"(?:Nov|Dec|Oct|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Mr|Ms|Dr|vs|e\.g|i\.e)\.$",
    re.I,
)


def _years(s: str) -> set[str]:
    return set(_YEAR_RE.findall(s or ""))


def _is_year(tok: str) -> bool:
    return bool(re.fullmatch(r"(?:19|20)\d{2}", tok or ""))


def _numbers(s: str) -> set[str]:
    s = squash(s)
    out: set[str] = set()
    for d in re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)", s):
        out.add(d)
    for w, v in NUM_WORDS.items():
        if w in ("single", "once"):
            continue
        if re.search(rf"\b{w}\b", s):
            out.add(str(v))
    return out


def _periods(s: str) -> set[str]:
    s = squash(s)
    found: set[str] = set()
    for p in ("minute", "hour", "day", "night", "week", "month", "year"):
        if re.search(rf"\b{p}s?\b", s):
            found.add(p)
    return found


def _is_label_tok(tok: str) -> bool:
    if tok in _LABEL_TOKS:
        return True
    return bool(re.fullmatch(r"p\d+", tok) or re.fullmatch(r"u\d+", tok))


def _strip_source_prefix(toks: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    """Drop [P1.U3] / Section 1.4 / 'according to the terms' prefixes, keep the evidence."""
    i = 0
    n = len(toks)
    while i < n - 3:
        t = toks[i][0]
        if _is_label_tok(t):
            i += 1
            continue
        if t.isdigit() and i > 0 and (_is_label_tok(toks[i - 1][0]) or toks[i - 1][0].isdigit()):
            i += 1
            continue
        break
    return toks[i:]


def _strip_source_suffix(toks: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    """Drop trailing source labels such as (P1) that the model sometimes appends."""
    n = len(toks)
    i = n
    while i > 3:
        t = toks[i - 1][0]
        if _is_label_tok(t):
            i -= 1
            continue
        if t.isdigit() and i >= 2 and (_is_label_tok(toks[i - 2][0]) or toks[i - 2][0].isdigit()):
            i -= 1
            continue
        break
    return toks[:i]


# Connectives the model sometimes drops from a long multi-bullet quote. Never skip
# numbers or content words — only these short grammatical tokens.
_OPTIONAL_TOKS = {"and", "or", "the", "a", "an"}

# Function/domain words ignored when checking that a claim's facts appear in its span.
_CLAIM_LIGHT = INDEX_STOP | {
    "must", "will", "may", "grant", "grantee", "abw", "aws", "program", "covers",
    "cover", "including", "include", "includes", "included", "receive", "following",
    "benefits", "benefit", "package", "all", "builders", "welcome", "official",
    "terms", "applicant", "selected",
    "reinvent", "invent", "vegas", "nevada", "las", "re",
    "attendees", "attendee", "coverage", "summarize", "provide", "provides",
    "expenses", "expense", "listed", "list", "lists", "tell",
}

# Same-fact paraphrases (airfare/flight), not retrieval expansions (cover→hotel).
_SYNONYM = {
    "airfare": ["flight", "roundtrip"],
    "flight": ["airfare", "roundtrip", "travel"],
    "roundtrip": ["flight", "airfare"],
    "travel": ["flight", "airfare"],
    "lodging": ["hotel", "accommodations"],
    "hotel": ["lodging", "accommodations"],
    "accommodations": ["hotel", "lodging"],
    "ticket": ["pass", "badge"],
    "pass": ["ticket", "badge"],
    "badge": ["pass", "ticket"],
    "minutes": ["time"],
    "venues": ["properties", "venue"],
    "properties": ["venues", "venue"],
    "venue": ["venues", "properties"],
    "apply": ["applications", "application"],
    "applications": ["apply", "application"],
    "application": ["apply", "applications"],
    "nov": ["november"],
    "november": ["nov"],
    "dec": ["december"],
    "december": ["dec"],
    "student": ["students", "undergrad", "undergraduate", "undergraduates", "college"],
    "students": ["student", "undergrad", "undergraduate", "undergraduates", "college"],
    "university": ["college", "student", "students"],
    "college": ["university", "student", "students"],
    "undergrad": ["student", "students", "undergraduate", "university"],
    "undergraduate": ["student", "students", "undergrad", "university"],
    "undergrads": ["student", "students", "undergrad", "university"],
    "undergraduates": ["student", "students", "undergrad", "university"],
    # Same fact: "not an employee ... of AWS or its affiliates" vs "not affiliated with AWS".
    "affiliates": ["affiliated", "affiliate"],
    "affiliate": ["affiliated", "affiliates"],
    "affiliated": ["affiliates", "affiliate"],
    "tech": ["technology"],
    "technology": ["tech"],
    "qualify": ["eligible", "eligibility"],
    "eligible": ["eligibility", "qualify"],
    "eligibility": ["eligible", "qualify"],
    "reapply": ["reapplication", "subsequent"],
    "subsequent": ["reapply"],
}

# Claim tokens that must appear in the quote even if they were also in the question.
_FACTISH = {
    "hotel", "lodging", "accommodations", "flight", "roundtrip", "airfare",
    "student", "students", "suite", "deadline", "eligible", "eligibility",
    "pass", "conference", "night", "miles", "cannot",
}

# Summary question-echo leak check: inventable benefits / actors, not framing words
# like eligibility that questions use while quotes state the criteria without that noun.
_SUMMARY_FACTISH = {
    "hotel", "lodging", "accommodations", "flight", "roundtrip", "airfare",
    "student", "students", "suite", "deadline",
    "pass", "conference", "night", "miles", "cannot",
}

_BULLET_CONT = re.compile(
    r'\s*["\')]*\s*:?\s*(?:;|,|and)?\s*(?:[\-•*]|\d+\.|[A-I]\.)\s+[^\n]+'
)
_LIST_LINE = re.compile(r"[ \t]*(?:[\-•*]|[A-I]\.|\d+\.)[ \t]+\S[^\n]*")


def _find_seq(needle: list[str], page_toks: list[tuple[str, int, int]]) -> tuple[int, int] | None:
    if not needle:
        return None
    hay = [t[0] for t in page_toks]
    n = len(needle)
    for i in range(0, len(hay) - n + 1):
        if hay[i : i + n] == needle:
            return (page_toks[i][1], page_toks[i + n - 1][2])
    return None


def _find_flex(needle: list[str], page_toks: list[tuple[str, int, int]]) -> tuple[int, int] | None:
    """Match content tokens allowing optional connectives in the source or quote.

    Used when a long quote is otherwise verbatim but omitted 'and' before a bullet.
    Every non-optional quote token must still appear, in order, so altered wording
    and changed numbers still fail.
    """
    need = [t for t in needle if t not in _OPTIONAL_TOKS]
    if len(need) < 4:
        return None
    hay = [t[0] for t in page_toks]
    n = len(need)
    for i, tok in enumerate(hay):
        if tok != need[0]:
            continue
        j = i
        k = 0
        while j < len(hay) and k < n:
            if hay[j] == need[k]:
                k += 1
                j += 1
            elif hay[j] in _OPTIONAL_TOKS:
                j += 1
            else:
                break
        if k == n:
            return (page_toks[i][1], page_toks[j - 1][2])
    return None


def locate(quote: str, page_text: str) -> tuple[int, int] | None:
    """Return (start, end) of quote inside page_text, or None.

    Matching is on alphanumeric token sequence so quote-style, bullets, and
    other punctuation cannot reject otherwise identical evidence. Offsets are
    in the original page string so the span can be copied back verbatim.
    """
    if not quote or not page_text:
        return None
    page_toks = content_tokens(page_text)
    quote_toks = _strip_source_suffix(_strip_source_prefix(content_tokens(quote)))
    if not quote_toks or not page_toks:
        return None
    q = [t[0] for t in quote_toks]
    span = _find_seq(q, page_toks)
    if span:
        return span
    span = _find_flex(q, page_toks)
    if span:
        return span
    # Live grant_03/17: Nova prepended the list intro to a later bullet, skipping
    # items in between. Keep the quote's *suffix* (never drop trailing content
    # words — that accepted Program Perks / it's vs its).
    min_keep = 5
    for drop in range(1, max(1, len(q) - min_keep + 1)):
        rest = q[drop:]
        if len(rest) < min_keep:
            break
        span = _find_seq(rest, page_toks) or _find_flex(rest, page_toks)
        if span:
            return span
    # Whitespace/case path for odd spacing that still shares punctuation-bearing words.
    words = re.findall(r"\S+", norm(quote).strip())
    if not words:
        return None
    pat = r"\s+".join(re.escape(w) for w in words)
    m = re.search(pat, norm(page_text), re.I)
    if not m:
        return None
    # Map the normed match back via tokens of the quote remainder.
    return _find_seq(q, page_toks)


def expand_to_containing_line(page_text: str, span: tuple[int, int]) -> tuple[int, int]:
    """If the match is a short fragment, take the source line it sits on.

    Defined-term snippets such as the city of the Event ("Event Location") are
    not themselves the fact; the bullet that contains them is.
    """
    start, end = span
    if not page_text or end <= start or (end - start) >= 120:
        return span
    nl_b = page_text.rfind("\n", 0, start)
    line_start = 0 if nl_b < 0 else nl_b + 1
    nl_a = page_text.find("\n", end)
    line_end = len(page_text) if nl_a < 0 else nl_a
    line = page_text[line_start:line_end].strip()
    if line.startswith("#") or len(line) < 20 or len(line) > 500:
        return span
    return (line_start, line_end)


def expand_list_span(
    page_text: str, span: tuple[int, int], *, bullets: bool = False
) -> tuple[int, int]:
    """If the match is a list header or item, include sibling list items only.

    Walks backward first (so criterion D still captures A–C), then forward
    through bullets / A. B. C. items. Does not walk into the next legal
    paragraph. Caps length so Terms dumps stay out.

    `bullets=True` also walks `-` siblings. Verify must not use that: a pass
    bullet must not entail a flight claim. Harvest uses it to bind each sibling
    as its own quoted claim.
    """
    start, end = span
    if not page_text:
        return span
    if bullets:
        start, end = expand_to_containing_line(page_text, (start, end))
    head = page_text[start:end]
    first = (head.split("\n") or [""])[0].strip()
    looks_header = (
        head.rstrip().endswith(":")
        or "following" in head.lower()
        or "criteria" in head.lower()
    )
    looks_lettered = bool(re.match(r"[A-I]\.\s+\S", first) or re.search(r"\b[A-I]\.\s+\S", head[:24]))
    looks_bullet = bool(bullets and _LIST_LINE.match(first))
    if not (looks_header or looks_lettered or looks_bullet):
        return span

    def _prev_line(s: int) -> tuple[int, str]:
        j = s
        while j > 0 and page_text[j - 1] in " \t\n":
            j -= 1
        nl = page_text.rfind("\n", 0, j)
        line_start = 0 if nl < 0 else nl + 1
        return line_start, page_text[line_start:j].strip()

    s = start
    while s > 0 and (end - s) < MAX_LIST_CHARS:
        line_start, stripped = _prev_line(s)
        if line_start >= s:
            break
        intro = (
            stripped.endswith(":")
            and len(stripped) < 120
            and ("following" in stripped.lower() or "criteria" in stripped.lower())
        )
        if _LIST_LINE.match(stripped) or intro:
            s = line_start
            if intro:
                break
            continue
        break
    i = min(end, len(page_text))
    while i < len(page_text):
        m = _BULLET_CONT.match(page_text, i)
        if not m:
            break
        if (m.end() - s) > MAX_LIST_CHARS:
            break
        i = m.end()
    end = i if i > end else end
    return (s, end)


def align_quote(quote: str, page_text: str) -> tuple[str | None, tuple[int, int] | None]:
    """If quote matches a source span, return the verbatim source slice and span."""
    span = locate(quote, page_text)
    if span is None:
        return None, None
    span = expand_to_containing_line(page_text, span)
    span = expand_list_span(page_text, span)
    return page_text[span[0] : span[1]], span


def _distinctive_claim_toks(text: str) -> set[str]:
    return {
        t[0]
        for t in content_tokens(text or "")
        if t[0] not in _CLAIM_LIGHT and not _is_label_tok(t[0]) and not t[0].isdigit()
    }


def _expanded_toks(toks: set[str]) -> set[str]:
    out = set(toks)
    for t in toks:
        out.update(_SYNONYM.get(t, []))
    return out


def _has_negation(text: str) -> bool:
    return bool(_NEG_RE.search(text or ""))


def _split_sentences(text: str) -> list[str]:
    """Split on sentence boundaries without cutting month abbreviations (Nov. 13)."""
    parts: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(text or "")
    while i < n:
        buf.append(text[i])
        if text[i] in ".!?" and (i + 1 >= n or text[i + 1].isspace()):
            frag = "".join(buf).strip()
            if frag and not _ABBREV_END.search(frag):
                j = i + 1
                while j < n and text[j].isspace():
                    j += 1
                if j >= n or text[j].isupper() or text[j] in "#-•*":
                    parts.append(frag)
                    buf = []
        i += 1
    rest = "".join(buf).strip()
    if rest:
        parts.append(rest)
    return parts


def _looks_structured_list(quote: str) -> bool:
    if re.search(r"#{2,}", quote or ""):
        return False
    lines = [ln.strip() for ln in (quote or "").splitlines() if ln.strip()]
    if len(lines) >= 2:
        listish = sum(1 for ln in lines if _LIST_LINE.match(ln) or ln.endswith(":"))
        return listish >= 2
    return bool(re.search(r"\b[A-I]\.\s+\S.+\b[B-I]\.\s+\S", quote or "", re.S))


def clip_quote_to_support(claim_text: str, quote: str) -> str:
    """Prefer the supporting sentence or list passage over a whole-chunk dump."""
    if not quote:
        return quote
    dump = bool(re.search(r"#{2,}", quote))
    keep_list = _looks_structured_list(quote)
    need = _expanded_toks(_distinctive_claim_toks(claim_text)) | _numbers(claim_text)
    if not dump and keep_list:
        cap = min(MAX_LIST_CHARS, 600)
        kept = quote if len(quote) <= cap else quote[:cap]
        if len(quote) > cap:
            nl = kept.rfind("\n")
            kept = kept[:nl] if nl > 80 else kept
        have = _expanded_toks({t[0] for t in content_tokens(kept)}) | _numbers(kept)
        if not need or (need & have):
            return kept
        # Prefix clip dropped the supporting date/fact (FAQ November 14th after a service list).
    if not dump and len(quote) <= MAX_EVIDENCE_CHARS and (not need or need & (
        _expanded_toks({t[0] for t in content_tokens(quote)}) | _numbers(quote)
    )):
        return quote
    parts: list[str] = []
    for block in re.split(r"(?:\n+|#{2,4}\s+)", quote):
        parts.extend(_split_sentences(block))
    parts = [p.strip() for p in parts if p and p.strip()]
    best, best_n = quote[:MAX_EVIDENCE_CHARS], -1
    for p in parts:
        if len(p) < 12:
            continue
        piece = p if len(p) <= MAX_EVIDENCE_CHARS else p[:MAX_EVIDENCE_CHARS]
        have = _expanded_toks({t[0] for t in content_tokens(piece)}) | _numbers(piece)
        n = len(need & have)
        if n > best_n:
            best, best_n = piece, n
    return best


def verify(claim_text: str, quote: str, page_text: str, question: str | None = None):
    """Return (ok, reason, span). On success, span is in page_text coordinates.

    Core tokens that are only the user's question wording (attendees, summarize)
    may be absent from the quote. Source facts (hotel, flight, student, suite,
    negation, numbers) still have to appear in the span.
    """
    if not quote or not page_text:
        return False, "missing quote or page", None
    snapped, span = align_quote(quote, page_text)
    if snapped is None or span is None:
        return False, "quote is not a substring of the stored source text", None
    q_nums, c_nums = _numbers(snapped), _numbers(claim_text)
    missing = c_nums - q_nums
    year_miss = {n for n in missing if _is_year(n)}
    other_miss = missing - year_miss
    if year_miss - (_years(snapped) | _years(page_text)):
        other_miss |= year_miss - (_years(snapped) | _years(page_text))
    if other_miss:
        return False, f"claim states count(s) {sorted(other_miss)} not in the quoted span", span
    q_per = _periods(snapped)
    for p in _periods(claim_text):
        allowed = PERIODS.get(p, [p])
        if not any(a in q_per for a in allowed):
            return (
                False,
                f"claim uses period '{p}' but the quoted span says {sorted(q_per) or 'no period'}",
                span,
            )
    if _has_negation(claim_text) and not _has_negation(snapped):
        return False, "claim negation is not in the quoted span", span
    need = _distinctive_claim_toks(claim_text)
    have = _expanded_toks({t[0] for t in content_tokens(snapped)})
    q_echo = _distinctive_claim_toks(question or "")
    if need:
        hit = {t for t in need if t in have or any(e in have for e in _SYNONYM.get(t, []))}
        if not hit:
            return False, "claim wording is not supported by the quoted span", span
        core = {t for t in need if len(t) >= 6}
        missing_core = [
            t
            for t in core
            if t not in hit
            and (t in _FACTISH or t not in q_echo)
        ]
        if missing_core:
            return False, "claim is not entailed by the quoted span", span
    return True, "ok", span


# Coverage nouns a summary must not mention unless a verified claim still has them.
_SUMMARY_MARKERS = (
    ("hotel", ("hotel", "lodging")),
    ("flight", ("flight", "roundtrip", "airfare")),
    ("conference pass", ("conference pass", "conference badge")),
)


def verify_summary(
    summary: str,
    quotes: list[str],
    claim_texts: list[str] | None = None,
    question: str | None = None,
    allow_uncertainty_negation: bool = False,
):
    """The direct-answer summary may only use facts from verified claims."""
    if not summary:
        return False, "empty summary"
    if not quotes and not claim_texts:
        return False, "no verified claims to support the summary"
    q_nums = set().union(*(_numbers(q) for q in quotes)) if quotes else set()
    blob_texts = [*(quotes or []), *(claim_texts or [])]
    if not allow_uncertainty_negation:
        hit = _unspecified_contradiction(summary, blob_texts)
        if hit:
            return False, f"summary says the documents don't specify {hit!r}, but a verified claim states it"
    have_years = set().union(*(_years(t) for t in blob_texts)) if blob_texts else set()
    missing = _numbers(summary) - q_nums
    if allow_uncertainty_negation:
        # Conflict prose may say "two dates" / "one page"; only digit/year facts must be sourced.
        digits = set(re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)", summary or ""))
        missing = {n for n in missing if n in digits or _is_year(n)}
    year_miss = {n for n in missing if _is_year(n)} - have_years - q_nums
    other = {n for n in missing if not _is_year(n)}
    if other or year_miss:
        return False, f"summary states count(s) {sorted(other | year_miss)} not in any verified claim"
    q_per = set().union(*(_periods(q) for q in quotes)) if quotes else set()
    # Claim quotes may state calendar dates without the word "day"/"year"; question-echoed
    # period words are framing ("last day", "last year"), not new temporal facts.
    q_ask_per = _periods(question or "")
    claim_blob_per = set().union(*(_periods(t) for t in (claim_texts or []))) if claim_texts else set()
    allowed_per = q_per | claim_blob_per | q_ask_per
    for p in _periods(summary):
        allowed = PERIODS.get(p, [p])
        if not any(a in allowed_per for a in allowed):
            return False, f"summary uses period '{p}' not in any verified claim ({sorted(q_per) or 'none'})"
    blob = " ".join(blob_texts).lower()
    s = summary.lower()
    for label, needles in _SUMMARY_MARKERS:
        if any(n in s for n in needles) and not any(n in blob for n in needles):
            return False, f"summary mentions {label} not present in any verified claim"
    if (
        not allow_uncertainty_negation
        and _has_negation(summary)
        and not any(_has_negation(t) for t in blob_texts)
    ):
        return False, "summary negation is not in any verified claim"
    if question:
        blob_toks = _expanded_toks(_distinctive_claim_toks(" ".join(blob_texts)))
        leaked = []
        q_echo = _distinctive_claim_toks(question)
        for tok in _distinctive_claim_toks(summary):
            if len(tok) < 6:
                continue
            if tok not in q_echo:
                continue
            if tok not in _SUMMARY_FACTISH:
                continue
            if tok in blob_toks or any(e in blob_toks for e in _SYNONYM.get(tok, [])):
                continue
            leaked.append(tok)
        if leaked:
            return False, f"summary uses question terms {leaked} not in verified claims"
    return True, "ok"


def _focus_tokens(text: str) -> set[str]:
    toks = set(tokenize(text or ""))
    out: set[str] = set()
    for t in toks:
        if t in _CLAIM_LIGHT or len(t) < 4:
            continue
        out.add(t)
        for e in _SYNONYM.get(t, []):
            if e not in _CLAIM_LIGHT:
                out.add(e)
    return out


# Tokens too weak to mark a claim "covered" by themselves (shared career/tech prose).
_COVER_WEAK = {
    "technology", "tech", "career", "preparing", "journey", "beginning", "role",
    "select", "limited", "number", "awarded", "details", "review", "conditions",
    "terms", "full", "please", "named", "among", "criteria", "builders", "welcome",
    "attendance", "person", "cost", "covers", "cover", "inperson",
}

_META_CLAIM = re.compile(
    r"(?i)(for full eligibility details|please review the terms|"
    r"limitation of liability|terms and conditions)"
)

# High-signal facts that, when present in a claim, must be represented to cover it.
_COVER_SIGNAL = _FACTISH | {
    "21", "employee", "affiliates", "previously", "reapply", "subsequent",
    "cohort", "cohorts", "prohibited", "restricted", "illegal", "barriers",
    "disadvantages", "university", "minutes", "additional", "properties",
    "venues", "november", "received", "deadline", "asl", "accessibility",
    "roundtrip", "accommodations",
}


def _claim_blob(c: dict) -> str:
    return f"{c.get('text') or ''} {c.get('quote') or ''}"


def _is_meta_claim(c: dict) -> bool:
    return bool(_META_CLAIM.search(_claim_blob(c)))


def _question_is_studentish(question: str) -> bool:
    q = set(tokenize(question or ""))
    return bool(
        q
        & {
            "student",
            "students",
            "undergrad",
            "undergrads",
            "undergraduate",
            "college",
            "eligible",
            "eligibility",
            "qualify",
            "qualifies",
            "requirements",
        }
    )


def _claim_coverage_need(
    focus: set[str],
    boilerplate: set[str],
    question: str | None = None,
) -> set[str]:
    """Distinctive facts a summary must show to cover one relevant claim."""
    ql = (question or "").lower()
    requirementsish = any(k in ql for k in ("eligib", "requirement", "criteria", "who can", "who is"))
    studentish = _question_is_studentish(question or "")
    # Apply/qualify: any student-bearing claim is covered by student/university in the summary.
    # Do not demand marketing leftovers (limited/awarded/select/role) after boilerplate removal.
    if studentish and not requirementsish:
        student_sig = focus & {"student", "students", "university"}
        if student_sig:
            return student_sig
    signal = (focus & _COVER_SIGNAL) - boilerplate
    if signal:
        return signal
    need = focus - boilerplate - _COVER_WEAK
    return need


_STUDENT_FACT_TOKS = {"student", "students", "university", "undergraduate", "undergraduates", "college"}
_STUDENT_Q_TOKS = _STUDENT_FACT_TOKS | {"undergrad", "undergrads"}
_NOT_CRITERIA = re.compile(
    r"(?i)\b(reimburse\w*|forfeit the grant|leave the Program|further benefits|reappl\w*)\b"
)


# Documented restrictions every student answer must show alongside the student
# criterion and age 21 (when they are among the verified claims): the applicant's own
# AWS employee/affiliation exclusion (Terms E) and the previously-accepted exclusion (D).
_STUDENT_RESTRICTIONS = re.compile(
    r"(?i)\byou are not an employee\b|\bnot (?:be )?(?:an? )?(?:AWS )?(?:employee|affiliated)\b"
    r"|\bpreviously accepted\b"
)


def _question_names_students(question: str) -> bool:
    return bool(set(tokenize(question or "")) & _STUDENT_Q_TOKS)


def relevant_verified_claims(question: str, claims: list[dict]) -> list[dict]:
    """Claims whose facts the question is asking about.

    A broad coverage question keeps every verified claim. A narrowed question
    (airfare only, deadline only) keeps claims that overlap the question so a
    flight-only ask does not require hotel. Meta "see Terms" lines are never
    required in the primary summary. Student/eligibility asks always keep age-21
    criteria claims when present. Apply/qualify paraphrases do not require
    barriers or marketing cost claims unless those claims also carry student facts.
    """
    qf = _focus_tokens(question)
    studentish = _question_is_studentish(question)
    ql = (question or "").lower()
    requirementsish = any(k in ql for k in ("eligib", "requirement", "criteria", "who can", "who is"))
    # F19: a question that names a student group ("college students", "undergrads",
    # "university students ... eligible") asks about student eligibility. Its required
    # facts are the student criterion, the age floor, and the documented restrictions
    # (own AWS employee/affiliation exclusion, previously-accepted exclusion), not every
    # Terms clause that shares a word with the question (reapply, reimbursement, forfeit).
    student_scope = _question_names_students(question)
    scored: list[tuple[dict, bool]] = []
    for c in claims or []:
        if _is_meta_claim(c):
            continue
        blob0 = _claim_blob(c)
        if student_scope:
            ctoks0 = set(tokenize(blob0))
            scored.append((
                c,
                bool(ctoks0 & _STUDENT_FACT_TOKS) or "21" in ctoks0 or bool(_STUDENT_RESTRICTIONS.search(blob0)),
            ))
            continue
        # Post-award conduct clauses are not eligibility criteria even when they say "eligible".
        # ...unless the question itself asks about them ("who is eligible to reapply?").
        if requirementsish and _NOT_CRITERIA.search(blob0) and not _NOT_CRITERIA.search(ql):
            continue
        blob = _claim_blob(c)
        cf = _focus_tokens(blob)
        ctoks = set(tokenize(blob))
        # Apply/qualify: skip barriers / pure cost marketing unless student-bearing.
        if studentish and not requirementsish:
            if re.search(r"(?i)\b(barriers|disadvantages)\b", blob):
                continue
            if re.search(r"(?i)\bcovers the cost\b", blob) and not (
                ctoks & {"student", "students", "university"}
            ):
                continue
        # Eligibility/requirements: skip off-slot salvage (hotel under-21, cert voucher, deferral).
        if requirementsish:
            if re.search(
                r"(?i)\b(exam voucher|deferral|campus hotel|checking in with someone who is 21)\b",
                blob,
            ):
                continue
            if re.search(r"(?i)\bforfeit the grant\b", blob):
                continue
        hit = bool(qf & cf)
        if studentish and "21" in ctoks:
            hit = True
        if studentish and ctoks & {"student", "students", "university"}:
            hit = True
        # Broad eligibility/requirements asks: keep official criteria claims even when
        # they do not lexically overlap "eligibility"/"requirements".
        if requirementsish and (cf & _COVER_SIGNAL or "21" in ctoks):
            hit = True
        scored.append((c, hit))
    named = [c for c, hit in scored if hit]
    if qf and named:
        return named
    if studentish and named:
        return named
    return [c for c, _ in scored]


def omitted_claim_texts(question: str, summary: str, claims: list[dict]) -> list[str]:
    """Return texts of relevant claims whose distinctive signal facts are absent from summary.

    Shared weak tokens (tech/career/preparing) alone do not cover a claim. Signal
    facts (age 21, student, employee exclusion, hotel, reapply, …) must appear when
    present on the claim. Boilerplate shared by every scoped claim is ignored.
    """
    scoped = relevant_verified_claims(question, claims)
    if not scoped:
        return []
    # Focus the claim *text* (not the evidence quote). Fat Bedrock quotes can contain
    # venue lists and other neighbors that must not become mandatory summary facts.
    foci = [_focus_tokens(c.get("text") or "") for c in scoped]
    boilerplate = set.intersection(*foci) if len(foci) > 1 else set()
    s_all = _focus_tokens(summary)
    # Digits like 21 are often stripped by _focus_tokens (len < 4); include raw tokens.
    s_toks = set(tokenize(summary or "")) | s_all
    omitted = []
    for c, focus in zip(scoped, foci):
        need = _claim_coverage_need(focus, boilerplate, question=question)
        # Age digit lives outside _focus_tokens; treat explicitly when present in text/quote.
        if "21" in set(tokenize(_claim_blob(c))):
            need = set(need) | {"21"}
        if not need:
            continue
        hit = {
            t
            for t in need
            if t in s_toks or any(e in s_toks for e in _SYNONYM.get(t, []))
        }
        if hit:
            continue
        omitted.append((c.get("text") or "")[:160])
    return omitted


def summary_covers_question(question: str, summary: str, claims: list[dict]) -> tuple[bool, str]:
    """Each in-scope verified claim must contribute at least one distinctive signal fact."""
    omitted = omitted_claim_texts(question, summary, claims)
    if omitted:
        return False, "summary omits verified facts that answer the question"
    return True, "ok"


# --- F19: "the documents don't specify X" answers -----------------------------------

# The marker clause ends at ".", ";", or a contrast/continuation clause
# (", but you can choose a suite" must stay visible to the permission check).
_UNSPEC_TAIL = r"(?:(?!,?\s+(?:but|however|yet|though|although|so)\b|,\s*and\b)[^.;])*"
_UNSPEC_MARKER = re.compile(
    r"(?i)\b(?:(?:does|do|did)\s*n[o']?t|doesn['’]t|don['’]t)\s+"
    r"(?:specify|say|state|mention|indicate|address|include information on|cover whether)\b" + _UNSPEC_TAIL
    + r"|\bnot\s+(?:specified|stated|mentioned|addressed)\b" + _UNSPEC_TAIL
    + r"|\bno\s+(?:information|details|mention)\s+(?:about|on|of|regarding)\b" + _UNSPEC_TAIL
)
_PERMISSION_CLAIM = re.compile(
    r"(?i)\b(?:you|grantees?|participants?|recipients?|attendees?|students?|everyone)\s+"
    r"(?:can|may|could|will|would|are allowed to|are able to|are free to|get to|are permitted to|are entitled to)\s+"
    r"(?:also\s+)?(?:choose|select|pick|request|upgrade|book|reserve|get|have|receive|stay)\b"
    # "the grant allows / lets / permits / entitles / covers upgrades ..."
    r"|\b(?:grant|program|programme|abw|aws|it|this|policy|terms|hotel|benefit)s?\s+"
    r"(?:also\s+)?(?:allows?|lets|permits?|enables?|entitles?|includes? (?:a|your) choice|offers? (?:a|your) choice|gives? you (?:a|the) choice)\b"
    r"|\b(?:is|are)\s+(?:allowed|permitted|available|eligible)\b"
    r"|\byour (?:choice|pick) of\b|\bup to you\b|\bat your discretion\b"
    r"|\b(?:can|may) be (?:chosen|selected|upgraded|requested|picked)\b"
)


_UNSPEC_FRAMING = {
    "specify", "specified", "specifies", "documents", "document", "state", "states", "stated",
    "mention", "mentioned", "mentions", "information", "details", "detail", "terms", "conditions",
    "whether", "grant", "grants", "program", "event", "provide", "provided", "provides", "apply",
    "applies", "cover", "covers", "covered", "include", "includes", "indicate", "address", "say", "says",
}


def _unspecified_contradiction(summary: str, blob_texts: list[str]) -> str | None:
    """F19: "Age requirements are not specified for students" while a verified claim says
    "you are at least 21 years of age". A clause claiming the documents are silent must not
    name a fact the verified claims state. Returns the shared fact token, or None."""
    claim_toks: set[str] = set()
    for t in blob_texts or []:
        claim_toks |= _focus_tokens(t)
    for sent in re.split(r"(?<=[.!?])\s+", summary or ""):
        for clause in re.split(r"[,;]|\b(?:but|however|although|though)\b", sent, flags=re.I):
            if not _UNSPEC_MARKER.search(clause):
                continue
            shared = (_focus_tokens(clause) - _UNSPEC_FRAMING) & claim_toks
            if shared:
                return sorted(shared)[0]
    return None


def verify_unspecified_summary(
    summary: str,
    claims: list[dict],
    question: str | None = None,
) -> tuple[bool, str]:
    """Accept an LLM answer that says the documents don't specify the asked detail.

    Used only when the caller has established that no verified claim states the
    asked detail (e.g. room type). The answer must (1) carry an explicit
    "documents don't specify" statement, (2) not assert a permission or a
    prohibition outside that statement, and (3) pass `verify_summary` for every
    other fact it states (numbers, benefits, periods, question-echo leaks).
    """
    s = (summary or "").strip()
    if not s:
        return False, "empty summary"
    if not _UNSPEC_MARKER.search(s):
        return False, "unspecified answer lacks a 'documents don't specify' statement"
    rest = _UNSPEC_MARKER.sub(" ", s)
    if _PERMISSION_CLAIM.search(rest):
        return False, "unspecified answer asserts a permission not in any verified claim"
    if _has_negation(rest) and not any(
        _has_negation(f"{c.get('text') or ''} {c.get('quote') or ''}") for c in claims or []
    ):
        return False, "unspecified answer asserts a prohibition not in any verified claim"
    ok, why = verify_summary(
        rest,
        [c.get("quote") or "" for c in claims or []],
        [c.get("text") or "" for c in claims or []],
        question=None,
    )
    if not ok and why != "empty summary":
        return False, why
    return True, "ok"


# --- F19: venue travel-time minutes ----------------------------------------------------

_TRAVEL_MINUTES = re.compile(
    r"(?i)\b(\d+)\s*(?:(?:to|-|–|or)\s*(\d+)\s*)?minutes?\b"
)
_TRAVEL_CONTEXT = re.compile(r"(?i)\b(venues?|propert(?:y|ies)|between|campus|walk\w*|travel\w*)\b")
_SEAT_CONTEXT = re.compile(r"(?i)\b(prior to the session|session start|seat|room at least)\b")


def travel_minute_values(text: str) -> set[str]:
    """Minute values stated for travel between venues (not seat-release or session length)."""
    t = text or ""
    out: set[str] = set()
    for sent in re.split(r"(?<=[.!?;])\s+", t):
        if not _TRAVEL_CONTEXT.search(sent) or _SEAT_CONTEXT.search(sent):
            continue
        for m in _TRAVEL_MINUTES.finditer(sent):
            out.add(m.group(1))
            if m.group(2):
                out.add(m.group(2))
    return out
