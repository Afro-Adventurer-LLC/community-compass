"use client";

import { useEffect, useState } from "react";
import { listFeedback, listUnanswered, type FeedbackItem, type UnansweredItem } from "@/services/api";

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
    <main className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-semibold">Advisor view</h1>
      <p className="mt-1 text-sm text-ink-500">
        Unanswered questions (system refusals and user flags) and thumbs feedback, for follow-up with grantees.
      </p>

      {error ? (
        <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">{error}</p>
      ) : null}

      <section className="mt-8">
        <h2 className="text-lg font-semibold">Unanswered questions</h2>
        {unanswered === null ? (
          <p className="mt-2 text-sm text-ink-500">Loading…</p>
        ) : unanswered.length === 0 ? (
          <p className="mt-2 rounded-lg border border-dashed border-slate-200 bg-white px-4 py-8 text-center text-sm text-ink-500">
            No unanswered questions yet.
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 bg-white">
            {unanswered.map((item) => (
              <li key={item.id} className="px-4 py-3">
                <p className="font-medium">{item.question}</p>
                <p className="mt-1 text-xs text-ink-500">
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
        <h2 className="text-lg font-semibold">Feedback</h2>
        {feedback === null ? (
          <p className="mt-2 text-sm text-ink-500">Loading…</p>
        ) : feedback.length === 0 ? (
          <p className="mt-2 rounded-lg border border-dashed border-slate-200 bg-white px-4 py-8 text-center text-sm text-ink-500">
            No feedback yet.
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 bg-white">
            {feedback.map((item) => (
              <li key={item.id} className="px-4 py-3">
                <p className="font-medium">
                  {item.rating === "up" ? "Helpful" : "Not helpful"}
                  {item.question ? ` · ${item.question}` : ""}
                </p>
                <p className="mt-1 text-xs text-ink-500">
                  turn {item.turn}
                  {item.created_at ? ` · ${item.created_at}` : ""}
                  {item.comment ? ` · ${item.comment}` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
