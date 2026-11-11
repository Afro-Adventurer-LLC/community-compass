"""Greeting / off-topic detection, task-request detection, and suggested questions.

Task requests ("write an email for me") get a polite decline plus the relevant info we can
actually answer. Policy/program questions are never routed here.
"""
from __future__ import annotations

import re

GREETING = re.compile(
    r"^\s*(hi+|hey+|hello+|hiya|howdy|yo|sup|wh?at'?s+ up|wassup|good (morning|afternoon|evening|night)|"
    r"how are (you|u)|how'?s it going|thanks?( you)?|thank (you|u)|thx|ok(ay)?|cool|nice|great|bye|"
    r"who are (you|u)|what are (you|u)|what can (you|u) do|help|test(ing)?)\b[\s!?.,:)]*\w{0,12}[\s!?.]*$",
    re.I,
)

DOMAIN = re.compile(
    r"\b(abw|all builders welcome|grant|re:?invent|reinvent|aws|vegas|las vegas|session|keynote|"
    r"workshop|expo|badge|hotel|travel|flight|shuttle|accessib|accommodat|eligib|mentor|"
    r"alumni|advisor|grantee|pass|register|registration|agenda|certification|voucher|"
    r"deadline|code of conduct|welcome reception|lounge|headshot|replay|re:play)\b",
    re.I,
)

_TASK_VERB = (
    r"(write|draft|compose|send|e-?mail|mail|message|text|contact|reach out to|call|phone|fill( it)?( out| in)?|"
    r"complete (the|my|this|a) (form|application)|submit|book|schedule|plan|organi[sz]e|prepare|"
    r"make (me )?(a |an |my )?(schedule|plan|timetable|appointment|email|letter)|sign me up|register me|"
    r"apply (for|to) .* for me|do my)"
)
TASK = re.compile(
    r"^\s*((so|ok(ay)?|and|then|now|also|great|thanks|cool|hey)[,!.]?\s+)*"
    r"(((can|could|would|will) (you|u)|pls|please|plz|help me( to)?|i (want|need) you to|i'?d like you to|"
    r"go ahead and)\s+)+(please\s+)?(help me\s+)?(to\s+)?" + _TASK_VERB + r"\b"
    r"|^\s*(please\s+)?" + _TASK_VERB + r"\s+(a|an|the|my|me|him|her|them|to|this|that|it)\b",
    re.I,
)
TASK_LABELS = [
    (r"e-?mail|mail|letter|message|text|write|draft|compose", "draft emails or letters"),
    (r"form|application|fill|submit|complete", "fill out or submit forms"),
    (r"contact|reach out|call|phone|send", "contact people for you"),
    (r"schedule|timetable|plan|organi[sz]e|book|appointment", "plan schedules or book appointments"),
    (r"sign me up|register me|apply", "register or apply for you"),
]

TOPIC_QUESTIONS = {
    "eligibility": [
        "Who is eligible for the All Builders Welcome Grant?",
        "How old do I need to be to apply for the ABW grant?",
        "Can I reapply if I am not selected?",
    ],
    "benefits": [
        "What does the All Builders Welcome Grant cover?",
        "Does the grant include a conference pass, flight, and hotel?",
        "Can I transfer my grant benefits to someone else?",
    ],
    "travel": [
        "How are ABW grant travel arrangements booked?",
        "How long do I have after the event to take my return flight?",
        "How much time should I leave between re:Invent venues?",
    ],
    "accessibility": [
        "What accessibility services are available at re:Invent?",
        "How do I request ASL interpretation or a sighted guide?",
        "When is the deadline to request accessibility accommodations?",
    ],
    "registration": [
        "How much does a full conference pass cost?",
        "What is the cancellation refund policy for re:Invent?",
        "Do I need AWS Builder ID to register?",
    ],
    "sessions": [
        "When does reserved seating open?",
        "If I reserve a seat, is my spot guaranteed?",
        "What is the difference between favoriting a session and reserving a seat?",
    ],
    "agenda": [
        "When and where is re:Invent 2026?",
        "Where can I pick up my badge?",
        "When is the CEO keynote?",
    ],
    "grant": [
        "Are ABW grant applications still open for re:Invent 2026?",
        "What extra programming do grant recipients get during the week?",
        "What happens if I cannot attend the full event after I am accepted?",
    ],
    "hotels": [
        "How do I book a discounted re:Invent hotel?",
        "Can I stay at a campus hotel if I am under 21?",
        "When do sleeping room blocks close?",
    ],
    "certification": [
        "Will certification exams be offered at re:Invent?",
        "Who gets the 50% AWS Certification exam voucher?",
        "When does the certification exam voucher expire?",
    ],
    "packing": [
        "What should I pack for re:Invent?",
        "How much time should I leave between venues?",
        "Where do I pick up my badge on day one?",
    ],
}

TEMPLATES = [
    ("grant", "Are ABW grant applications still open for re:Invent 2026?"),
    ("eligibility", "Who is eligible for the All Builders Welcome Grant?"),
    ("benefits", "What does the All Builders Welcome Grant cover?"),
    ("accessibility", "When is the deadline to request accessibility accommodations?"),
    ("travel", "How much time should I leave between re:Invent venues?"),
    ("agenda", "When and where is re:Invent 2026?"),
    ("sessions", "If I reserve a seat, is my spot guaranteed?"),
    ("hotels", "How do I book a discounted re:Invent hotel?"),
    ("certification", "Who gets the 50% AWS Certification exam voucher?"),
]


def task_label(question: str) -> str:
    for rx, label in TASK_LABELS:
        if re.search(rx, question, re.I):
            return label
    return "do tasks like that"


def classify(question: str):
    """'task_request', 'greeting', 'maybe_off_topic', or None (in-domain question)."""
    if TASK.search(question):
        return "task_request"
    if DOMAIN.search(question):
        return None
    if GREETING.match(question) or not re.search(r"[a-z]{3}", question, re.I):
        return "greeting"
    return "maybe_off_topic"


def suggestions(n=3) -> list[str]:
    return [q for _, q in TEMPLATES[:n]]


def related(topics, answerable, n=3, exclude=()) -> list[str]:
    out, seen = [], {e.strip().lower() for e in exclude}
    for t in [t for t in topics if t]:
        for q in TOPIC_QUESTIONS.get(t, []):
            if len(out) < n and q.lower() not in seen and answerable(q):
                out.append(q)
                seen.add(q.lower())
    for q in suggestions(n=8):
        if len(out) < n and q.lower() not in seen and answerable(q):
            out.append(q)
            seen.add(q.lower())
    # Last resort: still show domain questions even if retrieval is cold (empty index).
    for q in suggestions(n=8):
        if len(out) < n and q.lower() not in seen:
            out.append(q)
            seen.add(q.lower())
    return out[:n]


def reply(kind: str):
    first = "Hi! " if kind == "greeting" else "That's outside what I can help with. "
    msg = (
        first
        + "I answer questions for All Builders Welcome (ABW) grant recipients and alumni advisors, "
        "using official re:Invent and ABW pages plus labeled alumni experience. Every claim is cited. "
        "Try one of these:"
    )
    return msg, suggestions()


def task_reply(question: str, topics, answerable):
    msg = (
        f"I can't {task_label(question)}, but I can share the relevant official information. "
        "Here are a few things I can answer from the ABW and re:Invent sources I have:"
    )
    return msg, related(topics, answerable)


def refusal_reply(reason: str, topics, answerable, question=""):
    if reason == "unspecified":
        msg = (
            "The documents I have don't specify that, so I won't infer a yes or a prohibition. "
            "An alumni advisor or AWS event support can confirm."
        )
    elif reason == "conflict_incomplete":
        msg = (
            "Official sources conflict on this, but I don't have verified quotes for both values, "
            "so I won't pick one. An alumni advisor or AWS event support can confirm."
        )
    elif reason == "no_verified_claim":
        msg = (
            "I couldn't find a clear, source-backed answer to this in the ABW and re:Invent documents I have, "
            "so I won't guess. An alumni advisor or AWS event support can confirm."
        )
    else:
        msg = (
            "I couldn't find this in the ABW and re:Invent documents I have, so I won't guess. "
            "An alumni advisor or AWS event support can confirm."
        )
    sugg = related(topics, answerable, exclude=(question,))
    if sugg:
        msg += " Related questions I can try:"
    return msg, sugg
