import type { ChatResponse, Claim, Note } from "@/services/api";

/** Status notes that stay on the primary card. Conflict evidence lives in View details. */
export const SAFETY_NOTE_KINDS = new Set(["official_over_alumni"]);

const MONTH_DATE =
  /\b(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?\b/gi;

export type HealthInfo = {
  mock: boolean;
  retriever: string;
  documents: number;
  default_generator?: string | null;
  knowledge_base?: boolean;
  git_sha?: string | null;
};

export function isRefusalLike(answer: Pick<ChatResponse, "refused" | "kind">): boolean {
  return (
    Boolean(answer.refused) ||
    answer.kind === "greeting" ||
    answer.kind === "off_topic" ||
    answer.kind === "task_request"
  );
}

export function uniqueClaimTexts(claims: Claim[] | undefined): string[] {
  const out: string[] = [];
  for (const c of claims || []) {
    const t = (c.text || "").trim();
    if (!t) continue;
    if (out.includes(t)) continue;
    out.push(t);
  }
  return out;
}

export function dateMentions(...texts: string[]): string[] {
  const found: string[] = [];
  const seen = new Set<string>();
  for (const t of texts) {
    const re = new RegExp(MONTH_DATE.source, MONTH_DATE.flags);
    let m: RegExpExecArray | null;
    while ((m = re.exec(t || ""))) {
      const raw = m[0].replace(/\s+/g, " ").trim();
      const key = raw.toLowerCase().replace(/\.$/, "");
      if (seen.has(key)) continue;
      seen.add(key);
      found.push(raw);
    }
  }
  return found;
}

function dayNumber(phrase: string): number | null {
  const m = phrase.match(/\d{1,2}/);
  return m ? Number(m[0]) : null;
}

export function conflictDocIds(answer: Pick<ChatResponse, "notes">): Set<string> {
  const ids = new Set<string>();
  for (const n of answer.notes || []) {
    if (n.kind !== "unresolved_contradiction") continue;
    for (const c of n.citations || []) {
      if (c.doc_id) ids.add(c.doc_id);
    }
  }
  return ids;
}

function claimDocId(c: Claim): string | undefined {
  return c.citation?.doc_id || c.citations?.find((x) => x.doc_id)?.doc_id;
}

/** One phrase per distinct day-of-month, sorted by day — never by retrieval score. */
export function conflictingDatePhrases(claims: Claim[] | undefined, docIds?: Set<string>): string[] {
  const list = claims || [];
  const official = list.filter((c) => !c.alumni_experience);
  let pool = official.length ? official : list;
  if (docIds && docIds.size) {
    const scoped = pool.filter((c) => {
      const id = claimDocId(c);
      return id ? docIds.has(id) : false;
    });
    if (scoped.length) pool = scoped;
  }
  const mentions = dateMentions(...pool.map((c) => `${c.text || ""} ${c.quote || ""}`));
  const byDay = new Map<number, string>();
  for (const phrase of mentions) {
    const day = dayNumber(phrase);
    if (day === null || byDay.has(day)) continue;
    byDay.set(day, phrase);
  }
  return [...byDay.keys()].sort((a, b) => a - b).map((d) => byDay.get(d) as string);
}

const CANNED_LEAD_INTERPOLATED =
  /^The official sources disagree: one says .+ and the other says .+\.\s*Please confirm with AWS event support before relying on either (date|value)\.$/i;
const CANNED_LEAD_FALLBACK =
  /^The official sources disagree and neither overrides the other\.\s*Please confirm with AWS event support before relying on either value\.$/i;

export function isCannedConflictLead(text: string | null | undefined): boolean {
  const s = (text || "").trim().replace(/\s+/g, " ");
  return CANNED_LEAD_INTERPOLATED.test(s) || CANNED_LEAD_FALLBACK.test(s);
}

/**
 * Readable primary answer from already-verified fields only.
 * The backend LLM writes conflict answers. This layer never interpolates dates
 * into a fixed warning sentence.
 */
export function composePrimaryAnswer(answer: ChatResponse): string {
  if (isRefusalLike(answer)) {
    return (answer.message || answer.refusal || "").trim();
  }
  const summary = (answer.summary || "").trim();
  if (answer.outcome_key === "unresolved_contradiction") {
    if (!summary || isCannedConflictLead(summary)) return "";
    return summary;
  }
  if (summary) return summary;
  // LLM writes the visible answer. Claims stay in View details — never concatenate
  // retrieved excerpts into a primary reply, and never invent a canned sentence.
  return "";
}

export function safetyNotes(notes: Note[] | undefined): Note[] {
  return (notes || []).filter((n) => SAFETY_NOTE_KINDS.has(n.kind));
}

export function detailNotes(notes: Note[] | undefined): Note[] {
  return (notes || []).filter((n) => !SAFETY_NOTE_KINDS.has(n.kind));
}

export function hasTraceDetails(answer: ChatResponse): boolean {
  return Boolean(
    (answer.claims && answer.claims.length) ||
      (answer.notes && answer.notes.length) ||
      answer.generator ||
      answer.outcome ||
      typeof answer.latency_ms === "number" ||
      (answer.passages && answer.passages.length) ||
      (answer.dropped && answer.dropped.length) ||
      answer.interpreted_as ||
      answer.generator_error,
  );
}

export function shortGenerator(name: string | null | undefined): string {
  if (!name) return "";
  if (name === "extractive") return "extractive";
  const m = name.match(/nova[^\s:]*/i);
  if (m) return m[0];
  const last = name.split(":").filter(Boolean).pop();
  return last || name;
}

/**
 * Status-bar label. In AWS/Bedrock mode the local lexical index is unused, so
 * `documents` is often 0 and must not be shown as "0 docs".
 */
function _shortSha(value: string | null | undefined): string {
  const hex = (value || "").replace(/[^0-9a-f]/gi, "");
  return hex.length >= 7 ? hex.slice(0, 7) : "";
}

export function formatHealthStatus(h: HealthInfo): string {
  const gen = shortGenerator(h.default_generator);
  const kb = h.knowledge_base === true || (!h.mock && h.retriever === "bedrock");
  const sha = _shortSha(h.git_sha);
  if (kb) {
    const base = gen ? `Knowledge base · Bedrock Retrieve · ${gen}` : "Knowledge base · Bedrock Retrieve";
    return sha ? `${base} · ${sha}` : base;
  }
  const docs = `${h.documents} local doc${h.documents === 1 ? "" : "s"}`;
  const mock = h.mock ? "mock" : h.retriever;
  const base = gen ? `${docs} · ${mock} · ${gen}` : `${docs} · ${mock}`;
  return sha ? `${base} · ${sha}` : base;
}
