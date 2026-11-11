"use client";

import { useState } from "react";
import type { ChatResponse } from "@/services/api";
import { flagUnanswered, sendFeedback } from "@/services/api";
import CitationChip from "./CitationChip";
import ConflictCallout from "./ConflictCallout";
import {
  composePrimaryAnswer,
  detailNotes,
  hasTraceDetails,
  isRefusalLike,
  safetyNotes,
} from "@/lib/presentAnswer";

type Props = {
  role: "user" | "assistant";
  text?: string;
  answer?: ChatResponse;
  loading?: boolean;
  error?: string;
  onSuggestion?: (q: string) => void;
};

export default function MessageBubble({ role, text, answer, loading, error, onSuggestion }: Props) {
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const [flagged, setFlagged] = useState(false);

  if (role === "user") {
    return (
      <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-sm text-white whitespace-pre-wrap">
        {text}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="max-w-[90%] rounded-2xl rounded-bl-md border border-slate-200 bg-white px-4 py-3 text-sm text-ink-500">
        <span className="inline-flex items-center gap-2">
          <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
          Searching official ABW and re:Invent sources…
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-[90%] rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">
        {error}
      </div>
    );
  }

  if (!answer) return null;

  const suggestions = answer.suggestions || [];
  const narrative = composePrimaryAnswer(answer);
  const safety = safetyNotes(answer.notes);
  const extras = detailNotes(answer.notes);
  const showTrace = hasTraceDetails(answer);
  const claims = answer.claims || [];
  const conflict = answer.outcome_key === "unresolved_contradiction";

  async function onThumb(which: "up" | "down") {
    if (!answer) return;
    setRating(which);
    try {
      await sendFeedback({
        conversation_id: answer.conversation_id,
        turn: answer.turn,
        rating: which,
        question: answer.question,
      });
    } catch {
      setRating(null);
    }
  }

  async function onFlag() {
    if (!answer) return;
    setFlagged(true);
    try {
      await flagUnanswered({
        question: answer.question,
        conversation_id: answer.conversation_id,
        turn: answer.turn,
        reason: "user_flag",
        event_year: 2026,
      });
    } catch {
      setFlagged(false);
    }
  }

  return (
    <div className="max-w-[94%] rounded-2xl rounded-bl-md border border-slate-200 bg-white px-4 py-3 text-sm">
      {narrative ? (
        <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-ink">{narrative}</p>
      ) : isRefusalLike(answer) ? null : (
        <p className="text-ink-500">No short source-backed answer is available. Open View details for retrieved evidence, or try again.</p>
      )}

      {safety.length ? <ConflictCallout notes={safety} /> : null}

      {suggestions.length ? (
        <ul className="mt-3 space-y-1">
          {suggestions.map((q) => (
            <li key={q}>
              <button
                type="button"
                className="text-left text-sm text-accent-600 underline-offset-2 hover:underline"
                onClick={() => onSuggestion?.(q)}
              >
                {q}
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {showTrace ? (
        <details className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
          <summary className="cursor-pointer select-none text-sm font-medium text-ink-700 outline-none marker:text-ink-500 focus-visible:ring-2 focus-visible:ring-accent">
            View details
          </summary>
          <div className="mt-3 space-y-4 text-sm">
            <section>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-500">Trace</h3>
              <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs text-ink-500">
                {answer.outcome ? (
                  <>
                    <dt>Outcome</dt>
                    <dd className={conflict ? "font-medium text-red-800" : ""}>{answer.outcome}</dd>
                  </>
                ) : null}
                {answer.generator ? (
                  <>
                    <dt>Generator</dt>
                    <dd>{answer.generator}</dd>
                  </>
                ) : null}
                {typeof answer.latency_ms === "number" ? (
                  <>
                    <dt>Latency</dt>
                    <dd>{answer.latency_ms} ms</dd>
                  </>
                ) : null}
                {answer.turn_type === "follow_up" && answer.interpreted_as ? (
                  <>
                    <dt>Interpreted as</dt>
                    <dd>{answer.interpreted_as}</dd>
                  </>
                ) : null}
                {answer.topic ? (
                  <>
                    <dt>Topic</dt>
                    <dd>{answer.topic}</dd>
                  </>
                ) : null}
              </dl>
              {answer.generator_error ? (
                <p className="mt-2 rounded-md bg-amber-50 px-2 py-1 text-xs text-amber-900">
                  Generation timed out or failed. No passage dump was used as the answer.
                </p>
              ) : null}
            </section>

            {claims.length ? (
              <section>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-500">Evidence</h3>
                <ul className="mt-2 space-y-3">
                  {claims.map((c, i) => (
                    <li key={i}>
                      <p>{c.text}</p>
                      <div className="mt-1 flex flex-wrap gap-1.5">
                        {(c.citations || [c.citation]).filter(Boolean).map((cit, j) => (
                          <CitationChip key={j} citation={cit} />
                        ))}
                      </div>
                      {c.quote ? <p className="mt-1 text-xs italic text-slate-500">“{c.quote}”</p> : null}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            {extras.length ? <ConflictCallout notes={extras} /> : null}

            {answer.passages?.length ? (
              <section>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-500">Retrieved</h3>
                <ul className="mt-1 space-y-1 text-xs text-ink-500">
                  {answer.passages.map((p, i) => (
                    <li key={p.id || i}>
                      {[p.title, p.section, p.source_type, p.event_year, p.suppressed ? "suppressed" : null]
                        .filter(Boolean)
                        .join(" · ")}
                      {typeof p.score === "number" ? ` · score ${p.score}` : ""}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            {answer.dropped?.length ? (
              <section>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-500">Verifier</h3>
                <ul className="mt-1 space-y-1 text-xs text-ink-500">
                  {answer.dropped.map((d, i) => (
                    <li key={i}>
                      {d.reason || "dropped"}
                      {d.text ? ` — ${d.text.slice(0, 160)}` : ""}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </div>
        </details>
      ) : null}

      {answer.kind === "answer" || answer.refused ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-2 text-xs text-ink-500">
          <button
            type="button"
            className={`rounded-md border px-2 py-1 ${rating === "up" ? "border-emerald-400 bg-emerald-50" : "border-slate-200"}`}
            onClick={() => onThumb("up")}
          >
            Helpful
          </button>
          <button
            type="button"
            className={`rounded-md border px-2 py-1 ${rating === "down" ? "border-red-300 bg-red-50" : "border-slate-200"}`}
            onClick={() => onThumb("down")}
          >
            Not helpful
          </button>
          <button
            type="button"
            className="rounded-md border border-slate-200 px-2 py-1"
            onClick={onFlag}
            disabled={flagged}
          >
            {flagged ? "Flagged for advisors" : "Flag as unanswered"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
