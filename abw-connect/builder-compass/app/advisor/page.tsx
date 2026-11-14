"use client";

import { useEffect, useState } from "react";
import PageHeader from "@/components/ui/PageHeader";
import { listFeedback, listUnanswered, type FeedbackItem, type UnansweredItem } from "@/services/abwApi";

export default function AdvisorPage() {
  const [unanswered, setUnanswered] = useState<UnansweredItem[] | null>(null);
  const [feedback, setFeedback] = useState<FeedbackItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listUnanswered(), listFeedback()])
      .then(([u, f]) => {
        setUnanswered(u.items);
        setFeedback(f.items);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  return (
    <div>
      <PageHeader
        title="Advisor view"
        subtitle="Unanswered questions (system refusals and user flags) and thumbs feedback, for follow-up with grantees."
      />

      {error ? (
        <p className="mt-4 rounded-lg border border-error/30 bg-error/10 px-3 py-2 text-sm text-error-fg">{error}</p>
      ) : null}

      <section className="mt-8">
        <h2 className="text-lg font-semibold text-ink">Unanswered questions</h2>
        {unanswered === null ? (
          <p className="mt-2 text-sm text-muted">Loading…</p>
        ) : unanswered.length === 0 ? (
          <p className="mt-2 rounded-2xl border border-dashed border-border bg-canvas shadow-card px-4 py-8 text-center text-sm text-muted">
            No unanswered questions yet.
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-border overflow-hidden rounded-2xl border border-border bg-canvas shadow-card">
            {unanswered.map((item) => (
              <li key={item.id} className="px-4 py-3">
                <p className="font-medium text-ink">{item.question}</p>
                <p className="mt-1 text-xs text-muted">
                  {[item.reason, item.source !== item.reason ? item.source : null, item.status]
                    .filter(Boolean)
                    .join(" · ")}
                  {item.created_at ? ` · ${item.created_at}` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-lg font-semibold text-ink">Feedback</h2>
        {feedback === null ? (
          <p className="mt-2 text-sm text-muted">Loading…</p>
        ) : feedback.length === 0 ? (
          <p className="mt-2 rounded-2xl border border-dashed border-border bg-canvas shadow-card px-4 py-8 text-center text-sm text-muted">
            No feedback yet.
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-border overflow-hidden rounded-2xl border border-border bg-canvas shadow-card">
            {feedback.map((item) => (
              <li key={item.id} className="px-4 py-3">
                <p className="font-medium text-ink">
                  {item.rating === "up" ? "Helpful" : "Not helpful"}
                  {item.question ? ` · ${item.question}` : ""}
                </p>
                <p className="mt-1 text-xs text-muted">
                  turn {item.turn}
                  {item.created_at ? ` · ${item.created_at}` : ""}
                  {item.comment ? ` · ${item.comment}` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
