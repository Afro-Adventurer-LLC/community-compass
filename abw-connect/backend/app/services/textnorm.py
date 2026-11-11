"""Text normalisation shared by indexing and claim verification, so substring checks are exact."""
from __future__ import annotations

import re
import unicodedata

# Straight/curly and single/double quotes and apostrophes fold to one character so
# evidence matching does not reject "Program Benefits" vs 'Program Benefits'.
_QUOTE_CHARS = (
    "\u2018",  # ‘
    "\u2019",  # ’
    "\u201c",  # “
    "\u201d",  # ”
    "'",
)

_DASH_SPACE = {
    "\u2013": "-",
    "\u2014": "-",
    "\u00a0": " ",
    "\u00ad": "",
}

NUM_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "single": 1,
    "once": 1,
}

TOPICS: dict[str, list[str]] = {
    "eligibility": [
        "eligib",
        "21 years",
        "at least 21",
        "years of age",
        "years old",
        "how old",
        "first 5 years",
        "first five years",
        "university student",
        "undergrad",
        "undergraduate",
        "college student",
        "reapply",
        "reapplication",
        "previously accepted a grant",
        "apply for the",
        "qualify",
    ],
    "benefits": [
        "program benefits",
        "conference pass",
        "roundtrip",
        "hotel accommodations",
        "covers the cost",
    ],
    "travel": [
        "travel agency",
        "return flights",
        "14 days",
        "personal expenses",
        "shuttle",
        "monorail",
        "30 to 45 minutes",
        "between venues",
        "between campuses",
        "across the campus",
        "transit buffer",
        "getting across",
        "allow additional time",
    ],
    "accessibility": [
        "accessib",
        "accommodat",
        "asl",
        "sign language",
        "caption",
        "cart",
        "sighted guide",
        "mobility device",
        "lactation",
        "reflection room",
    ],
    "registration": [
        "register",
        "registration",
        "$2,499",
        "2499",
        "cancellation",
        "refund",
        "builder id",
        "full conference pass",
    ],
    "sessions": [
        "session",
        "keynote",
        "workshop",
        "reserved seating",
        "event catalog",
        "bootcamp",
        "chalk talk",
    ],
    "agenda": [
        "agenda",
        "badge pickup",
        "november 29",
        "november 30",
        "december 4",
        "harry reid",
    ],
    "grant": [
        "all builders welcome",
        "abw grant",
        "abw",
        "grant recipient",
        "alumni advisor",
        "applications are now closed",
        "welcome event",
        "mentorship",
    ],
    "hotels": [
        "hotel",
        "sleeping room",
        "treasure island",
        "discounted rates",
        "campus hotel",
    ],
    "certification": [
        "certification",
        "exam voucher",
        "50% discount",
        "january 31, 2027",
    ],
    "conduct": ["code of conduct", "safety", "event terms"],
    "packing": [
        "travel checklist",
        "broken-in shoes",
        "portable charger",
        "know before you go",
        "what should i pack",
        "what to pack",
        "what to bring",
    ],
}


def fold_quotes(s: str) -> str:
    """Map straight/curly and single/double quotes and apostrophes to one character."""
    for ch in _QUOTE_CHARS:
        s = s.replace(ch, '"')
    return s


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = fold_quotes(s)
    for a, b in _DASH_SPACE.items():
        s = s.replace(a, b)
    s = re.sub(r"[ \t]+", " ", s)
    return s


def squash(s: str) -> str:
    """Whitespace-insensitive, case-insensitive form used for quote matching."""
    return re.sub(r"\s+", " ", norm(s)).strip().lower()


def topic_of(text: str) -> str | None:
    t = squash(text)
    for key, kws in TOPICS.items():
        if any(k in t for k in kws):
            return key
    return None


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]{2,}", squash(text))


_CONTENT_TOKEN = re.compile(r"[A-Za-z0-9]+")


def content_tokens(s: str) -> list[tuple[str, int, int]]:
    """Alphanumeric tokens with offsets in the original string. Punctuation is ignored."""
    return [(m.group(0).lower(), m.start(), m.end()) for m in _CONTENT_TOKEN.finditer(s or "")]
