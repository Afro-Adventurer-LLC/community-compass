"""Pinned, swappable generator interface.

Generators turn passages into *claims*: {text, source (passage/unit id), quote}. They never produce
uncited prose. Every claim is then checked by verify.py; the generator is not trusted.
"""
from __future__ import annotations

import json
import re
import time

from ..config import GENERATOR_MODE, LLM_TIMEOUT_S, use_aws
from .llm import LLMClient, LLMError, get_llm
from .textnorm import squash, tokenize
from .present import llm_answer_is_dump
from .verify import align_quote
from .index import EXPAND, STOP as INDEX_STOP

SYSTEM = """You answer questions from AWS All Builders Welcome (ABW) grant recipients and alumni advisors.
Use ONLY the numbered passages given. Output valid JSON only (no code fences, no commentary):
{"answer": "...", "claims":[{"text": "...", "source": "P1.U3", "quote": "..."}]}
"answer" is the user-visible reply: one or two short sentences (under 400 characters) that
directly answer the question. It may only contain facts stated in your claims: no number, date,
or time period that is not in a claim's quote. Never paste passage text, Terms, disclaimers,
section numbers, or multiple paragraphs into "answer". Evidence belongs only in claims.
Use "answer": "" only with no claims. Write at most 8 claims, most important first, only those
that actually answer this question.
Rules:
1. Each claim is one plain-English sentence addressed to the reader ("You may ...", "The grant covers ...").
2. "quote" is copied EXACTLY, character for character, from the unit named in "source" (a contiguous substring).
   Copy the unit text as-is; do not rephrase, add labels like [P1.U3], or change punctuation.
3. "source" is only a passage id such as "P1.U3". Never put a JSON object, Python dict, or nested claim in "source".
4. Every number and every time period in "text" (day, week, month, year, hour) must appear in its quote.
   Never convert periods: a day is not a week; keep the wording of deadlines.
5. Passages labeled source_type=alumni_experience are personal experience. Never let them override official
   passages. If you cite them, the claim text must say it is personal experience.
6. If official passages disagree on the value the question asks about, write a claim for EACH cited value;
   do not pick a winner. The "answer" field must name each conflicting verified value in your own words
   and make the disagreement or uncertainty clear. Do not invent that one source overrides the other
   unless a passage says so. Never lead with only one of the conflicting values. Do not treat
   unrelated dates in the same retrieved set as a disagreement about this question.
7. Never use outside knowledge. Only if NO passage states a rule relevant to the question, return {"answer": "", "claims": []}.
"""

NUDGE = (
    "Your previous reply was not valid JSON. Reply again with valid JSON only - no code fences - "
    'exactly {"answer": "...", "claims": [...]}, at most 8 claims. '
    '"source" must be a passage id like P1.U3. "answer" is one or two short sentences, not copied passages.'
)

SHAPE_NUDGE = (
    "Your previous JSON was unusable. Reply again with valid JSON only. "
    '"answer" must be one or two short sentences under 400 characters that answer the question; '
    "do not copy Terms, disclaimers, or passage text into answer. "
    'Each claim "source" must be a passage id like "P1.U3" (never an object or document title). '
    "Include a verbatim quote substring from that unit. At most 8 claims, only facts that answer the question."
)

ANSWER_ONLY_SYSTEM = """You write a short user-visible answer from verified claims. Output JSON only:
{"answer": "..."}
The answer is one or two short sentences (under 400 characters) that directly answer the question.
Use only facts in the verified claims (their text and their quotes). Do not invent numbers, dates, or benefits that are not in those claims.
Do not copy quotes or claim text as a document dump. Do not list every source clause.
Include each verified fact that answers this question; do not keep only the first claim.
If the claims conflict on the asked value, mention each verified value and the disagreement or uncertainty
in your own words. Do not pick a winner. Do not say that neither source overrides the other unless the
claims state that. Do not write a form letter.
"""

SOURCE_ID_RE = re.compile(r"P\s*(\d+)(?:\s*[.]\s*U\s*(\d+))?", re.I)


class LLMOutputError(ValueError):
    pass


def _maybe_mapping(value):
    """Parse a nested claim dict, including Python-repr strings from json_repair."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s or s[0] not in "{[":
        return None
    try:
        import ast

        parsed = ast.literal_eval(s)
        return parsed if isinstance(parsed, dict) else None
    except (SyntaxError, ValueError, MemoryError):
        pass
    try:
        parsed = json.loads(s)
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def source_passage_id(raw) -> str | None:
    """Return P{n}.U{m} from a source field, nested dict, or stringified repaired claim.

    Accepts P1.U3, P1, [P1.U0], and passage-only ids (unit defaults to 0).
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        return source_passage_id(raw.get("source") or raw.get("id"))
    nested = _maybe_mapping(raw)
    if nested:
        found = source_passage_id(nested.get("source") or nested.get("id"))
        if found:
            return found
    m = SOURCE_ID_RE.search(str(raw))
    if not m:
        return None
    return f"P{int(m.group(1))}.U{int(m.group(2) or 0)}"


def normalize_generated_claim(cl) -> dict:
    """Recover text/source/quote when repair nests the claim inside `source`."""
    if not isinstance(cl, dict):
        return dict(text="", source="", quote="")
    src_raw = cl.get("source")
    nested = src_raw if isinstance(src_raw, dict) else _maybe_mapping(src_raw)
    text = cl.get("text") or ""
    quote = cl.get("quote") or ""
    extra: dict = {}
    for k, v in cl.items():
        if k not in {"text", "source", "quote"}:
            extra[k] = v
    if nested:
        text = text or nested.get("text") or ""
        quote = quote or nested.get("quote") or ""
        src_raw = nested.get("source") or src_raw
    sid = source_passage_id(src_raw)
    if not quote and text:
        quote = text
    out = dict(text=str(text or ""), source=sid or (str(src_raw).strip() if src_raw is not None else ""), quote=str(quote or ""))
    out.update(extra)
    return out


def assign_source_from_meta(raw, chunks: list) -> str | None:
    """Bind a URL, document title, or doc id to a retrieved passage."""
    key = squash(str(raw or "").strip())
    if not key or len(key) < 8 or not chunks:
        return None
    for pi, chunk in enumerate(chunks):
        title = squash(chunk.get("title") or "")
        if title and key == title:
            return f"P{pi + 1}.U0"
        url = squash(chunk.get("source_url") or "")
        if url and len(key) >= 20 and (key.rstrip("/") == url.rstrip("/") or url in key or key in url):
            return f"P{pi + 1}.U0"
        for field in (chunk.get("doc_id"), chunk.get("id")):
            fv = squash(str(field or ""))
            if fv and key == fv:
                return f"P{pi + 1}.U0"
    return None


def assign_source_from_quote(quote: str, chunks: list) -> str | None:
    """If the model named a title instead of P{n}.U{m}, bind the quote to a passage."""
    if not quote or not chunks:
        return None
    for pi, chunk in enumerate(chunks):
        page = chunk.get("text") or ""
        snapped, _ = align_quote(quote, page)
        if not snapped:
            continue
        for ui, t in unit_texts(chunk):
            hit, _ = align_quote(quote, t)
            if hit:
                return f"P{pi + 1}.U{ui}"
        return f"P{pi + 1}.U0"
    return None


def bind_claim_source(cl, chunks: list | None = None) -> dict:
    """Normalize nested sources and recover P-ids from quotes when the id is a title."""
    out = normalize_generated_claim(cl)
    sid = source_passage_id(out.get("source"))
    if sid:
        out["source"] = sid
        return out
    chunks = chunks or []
    assigned = assign_source_from_quote(out.get("quote") or "", chunks) or assign_source_from_meta(
        out.get("source"), chunks
    )
    if assigned:
        out["source"] = assigned
    return out


def _escape_inner_quotes(body: str) -> str:
    """Escape bare `"` inside JSON string values (quotes copied from Terms such as
    `the Event ("Event Location")`). A quote only closes a string when the next
    non-space character is JSON structure (`,` `:` `}` `]`) or the end of input."""
    out: list[str] = []
    in_str = False
    esc = False
    n = len(body)
    for i, ch in enumerate(body):
        if not in_str:
            out.append(ch)
            if ch == '"':
                in_str = True
            continue
        if esc:
            out.append(ch)
            esc = False
            continue
        if ch == "\\":
            out.append(ch)
            esc = True
            continue
        if ch == '"':
            j = i + 1
            while j < n and body[j] in " \t\r\n":
                j += 1
            if j >= n or body[j] in ",:}]":
                out.append(ch)
                in_str = False
            else:
                out.append('\\"')
            continue
        if ch == "\n":
            out.append("\\n")
            continue
        out.append(ch)
    return "".join(out)


def parse_llm_json(raw: str, truncated: bool = False):
    txt = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw or "", flags=re.S)
    i = txt.find("{")
    if i < 0:
        raise LLMOutputError("no JSON object in reply")
    body = txt[i:]
    j = body.rfind("}")
    how = "json"
    try:
        data = json.loads(body[: j + 1]) if j >= 0 else None
        if not isinstance(data, dict):
            raise ValueError
    except ValueError as e:
        err = e
        data = None
        # F19: unescaped quotes inside a copied Terms quote broke the JSON and json_repair
        # then lost list items (live grant_13 hotel). Escape bare inner quotes first.
        try:
            fixed = _escape_inner_quotes(body[: j + 1] if j >= 0 else body)
            cand = json.loads(fixed)
            if isinstance(cand, dict) and isinstance(cand.get("claims"), list):
                data = cand
        except ValueError:
            data = None
        if data is None:
            try:
                import json_repair

                data = json_repair.loads(body)
            except Exception:
                raise LLMOutputError(f"unrepairable JSON ({type(err).__name__}: {err})") from err
        how = "repaired"
        if not isinstance(data, dict) or not isinstance(data.get("claims"), list):
            raise LLMOutputError(f"unrepairable JSON ({type(err).__name__}: {err})")
        # Keep every claim that still carries text or a quote: a truncated last claim is
        # passed to the verifier (which drops it with a reason if its quote cannot be
        # located) instead of being silently discarded here. Only a claim with neither
        # text nor quote is unusable.
        last = data["claims"][-1] if data["claims"] else None
        incomplete_last = isinstance(last, dict) and not (
            str(last.get("text") or "").strip() or str(last.get("quote") or "").strip()
        )
        if incomplete_last:
            data["claims"] = data["claims"][:-1]
    if not isinstance(data.get("claims"), list):
        raise LLMOutputError("reply has no claims list")
    data["claims"] = [normalize_generated_claim(c) for c in data["claims"] if isinstance(c, dict)]
    return data, how


def unit_texts(chunk: dict) -> list[tuple[int, str]]:
    units = chunk.get("units") or []
    text = chunk.get("text") or ""
    out = []
    if not units:
        units = [(0, len(text))]
    for i, span in enumerate(units):
        s, e = span[0], span[1]
        t = text[s:e].strip()
        if not t or t.startswith("#"):
            continue
        if t.endswith(":") and len(t) < 60:
            continue
        out.append((i, t))
    return out


def _overlap(question: str, text: str) -> int:
    q = {t for t in tokenize(question) if t not in INDEX_STOP}
    for t in list(q):
        q.update(EXPAND.get(t, []))
    if not q:
        return 0
    return len(q & {t for t in tokenize(text) if t not in INDEX_STOP})


class Generator:
    name = "base"

    def claims(self, question, profile, chunks, history=None):
        raise NotImplementedError


class ExtractiveGenerator(Generator):
    """No-LLM mode: every claim is a verbatim paragraph/bullet from the selected passages."""

    name = "extractive"

    def claims(self, question, profile, chunks, history=None):  # history is ignored
        out = []
        for pi, c in enumerate(chunks):
            units = unit_texts(c)
            ranked = sorted(units, key=lambda ut: -_overlap(question, ut[1]))
            with_overlap = [u for u in ranked if _overlap(question, u[1]) > 0]
            cap = 16 if c.get("primary", False) else 8
            units = (with_overlap or ranked)[:cap]
            for ui, t in units[:24]:
                text = re.sub(r"^[•\-]\s*", "", t)
                if c.get("source_type") == "alumni_experience":
                    claim = f"Personal experience from an alumni advisor: {text}"
                else:
                    claim = text
                out.append(dict(text=claim, source=f"P{pi + 1}.U{ui}", quote=t))
        return out


def _history_block(history):
    """Follow-ups: earlier turns as context for what the user means. Not evidence: never quoted or cited."""
    lines = "\n".join(f"- Q: {h['standalone']}\n  A: {h['answer']}" for h in history)
    return (
        "Earlier in this conversation (context only - NOT a source; never quote or cite it, use only the passages):\n"
        f"{lines}\n"
    )


class BedrockGenerator(Generator):
    def __init__(self, client: LLMClient | None = None):
        self.client = client or get_llm()
        self.name = f"llm:{getattr(self.client, 'name', 'bedrock')}"
        self.budget_s = LLM_TIMEOUT_S
        self.summary = None
        self.attempts = []

    def claims(self, question, profile, chunks, history=None):
        blocks = []
        for pi, c in enumerate(chunks):
            head = (
                f"[P{pi + 1}] {c.get('title')} - {c.get('section') or ''} "
                f"(source_type={c.get('source_type')}, event_year={c.get('event_year')})"
            )
            units = "\n".join(f"  [P{pi + 1}.U{ui}] {t}" for ui, t in unit_texts(c))
            blocks.append(head + "\n" + units)
        who = (
            f"Caller: {profile.get('role', 'grantee')} asking about event year {profile.get('event_year')}.\n"
        )
        user = (
            who
            + (_history_block(history) if history else "")
            + f"Question: {question}\n\nPassages:\n"
            + "\n\n".join(blocks)
        )
        msgs_system, user_text = SYSTEM, user
        deadline = time.time() + self.budget_s
        self.summary, self.attempts = None, []
        last_err = None
        last_out = []
        for attempt in (1, 2, 3):
            left = deadline - time.time()
            if attempt > 1 and left < 3:
                break
            try:
                raw = self.client.complete(msgs_system, user_text, timeout_s=max(left, 0.5))
            except Exception as e:
                last_err = e
                self.attempts.append(dict(attempt=attempt, ok=False, error=str(e)))
                raise LLMError(f"{type(e).__name__}: {e}") from e
            try:
                data, how = parse_llm_json(raw)
            except LLMOutputError as e:
                last_err = e
                self.attempts.append(dict(attempt=attempt, ok=False, error=str(e)))
                user_text = user + "\n\n" + NUDGE
                continue
            answer = str(data.get("answer") or "").strip()
            out = []
            recovered_source = False
            for c in data["claims"]:
                if not isinstance(c, dict):
                    continue
                cl = bind_claim_source(c, chunks)
                quote = cl.get("quote") or ""
                src = cl.get("source") or ""
                if source_passage_id(src) and not SOURCE_ID_RE.search(str(c.get("source") or "")):
                    recovered_source = True
                try:
                    pi = int(src.split(".")[0].lstrip("Pp")) - 1
                    page = chunks[pi].get("text") or ""
                    snapped, _ = align_quote(quote, page)
                    if snapped:
                        quote = snapped
                except Exception:
                    pass
                out.append(dict(text=cl.get("text") or "", source=src, quote=quote))
            dump = llm_answer_is_dump(answer)
            self.attempts.append(
                dict(
                    attempt=attempt,
                    ok=bool(out) and not dump,
                    parsed=how,
                    dump=dump,
                    recovered_source=recovered_source,
                )
            )
            if out and answer and not dump:
                self.summary = answer
                return out
            if out:
                last_out = out
                if answer and not dump:
                    self.summary = answer
            last_err = LLMOutputError("answer missing, dumped passages, or source ids unusable")
            user_text = user + "\n\n" + SHAPE_NUDGE
            continue
        if last_out:
            # Claims recovered; a missing/dump answer is filled later from verified quotes.
            return last_out
        raise LLMOutputError(f"no valid JSON after {len(self.attempts)} attempt(s): {last_err}")

    def short_answer(
        self,
        question: str,
        claims,
        timeout_s: float | None = None,
        omitted: list[str] | None = None,
        conflict: bool = False,
        must_include: list[str] | None = None,
        previous: str | None = None,
        unspecified: str | None = None,
        final: bool = False,
    ) -> str | None:
        """One extra LLM turn: write a short answer from verified claims (text + quote).

        `must_include` (F19 coverage repair) lists verified claim texts the previous
        draft left out; those claims are listed first so the row cap never hides them.
        `unspecified` names what the verified claims do not state (room type), so the
        model can say the documents don't specify it instead of inventing a yes/no.
        `final` marks the last bounded coverage repair: the model keeps what the closest
        draft got right, adds every listed fact, and writes any caveat itself.
        """
        rows = []
        must = [m for m in (must_include or []) if m]
        if must:
            def _is_must(c) -> bool:
                t = (c.get("text") or "") if isinstance(c, dict) else str(c)
                return any(m[:60] and m[:60] in t for m in must)

            claims = sorted(list(claims or []), key=lambda c: 0 if _is_must(c) else 1)
        for c in claims or []:
            if isinstance(c, str):
                text, quote = "", c
            else:
                text = (c.get("text") or "").strip()
                quote = (c.get("quote") or "").strip()
            if text or quote:
                rows.append((text, quote))
        if not question or not rows:
            return None
        lines = []
        for i, (text, quote) in enumerate(rows[:10], 1):
            lines.append(f"{i}. claim: {text or '(see quote)'}\n   quote: {quote}")
        user = (
            f"Question: {question}\n\n"
            "Verified claims (already source-checked; do not add facts that are not here):\n"
            + "\n".join(lines)
            + "\n"
        )
        if omitted:
            bits = "; ".join(o for o in omitted if o)
            if bits:
                user += (
                    "\nYour previous answer dropped verified facts the question asked for: "
                    f"{bits}\nInclude those facts. Still no new facts, no dump.\n"
                )
        if must:
            bits = "\n".join(f"- {m}" for m in must)
            user += (
                "\nA previous draft was rejected because it left out these verified facts that "
                f"answer the question:\n{bits}\n"
                + (f"Rejected draft: {previous}\n" if previous else "")
                + "Write a new answer in your own words that states each of those facts briefly. "
                "Two or three short sentences are fine. Still no new facts, no copied passages.\n"
            )
            if final:
                user += (
                    "This is the final attempt. Keep every fact the rejected draft stated correctly "
                    "and add each listed fact. If a listed fact is a condition or limit, say so in your "
                    "own words (a short caveat is fine). Do not drop any listed fact.\n"
                )
        if unspecified:
            user += (
                f"\nThe verified claims do not state {unspecified}. Say plainly that the documents "
                "don't specify it, and give the related verified fact if one answers part of the "
                "question. Do not say it is allowed or not allowed.\n"
            )
        if conflict:
            user += (
                "\nThe verified claims conflict on the value this question asks about. "
                "Write a concise answer in your own words that names each verified conflicting value "
                "and marks the disagreement or uncertainty. Do not pick a winner. "
                "Do not invent an override. Do not paste quotes or write a form letter.\n"
            )
        left = timeout_s if timeout_s is not None else min(8.0, max(self.budget_s, 3.0))
        raw = self.client.complete(ANSWER_ONLY_SYSTEM, user, timeout_s=max(left, 0.5), max_tokens=400)
        txt = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw or "", flags=re.S)
        i = txt.find("{")
        if i < 0:
            return None
        body_json = txt[i:]
        j = body_json.rfind("}")
        data = None
        try:
            data = json.loads(body_json[: j + 1]) if j >= 0 else None
        except (json.JSONDecodeError, TypeError, ValueError):
            try:
                import json_repair

                data = json_repair.loads(body_json)
            except Exception:
                return None
        if not isinstance(data, dict):
            return None
        answer = str(data.get("answer") or "").strip()
        if not answer or llm_answer_is_dump(answer):
            return None
        self.attempts.append(dict(attempt="short_answer", ok=True, parsed="answer_only"))
        return answer


def get_generator(mode: str | None = None, llm: LLMClient | None = None) -> Generator:
    mode = (mode or GENERATOR_MODE).lower()
    if mode == "auto":
        mode = "llm" if (llm or use_aws()) else "extractive"
    if mode == "llm":
        return BedrockGenerator(client=llm or get_llm())
    return ExtractiveGenerator()
