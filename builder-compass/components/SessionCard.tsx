"use client";

import Link from "next/link";
import { Check, Clock3, MapPin, Plus } from "lucide-react";
import type { Session } from "@/types";
import { useCompassStore } from "@/lib/store";
import { dayLabel, levelLabel, rangeLabel } from "@/lib/format";
import type { FitResult } from "@/lib/schedule";
import Button from "@/components/ui/Button";
import { FitPill } from "@/components/FeasibilityBadge";

export default function SessionCard({
  session,
  fit,
}: {
  session: Session;
  fit?: FitResult | null;
}) {
  const isPlanned = useCompassStore((s) => s.isPlanned(session.id));
  const addToPlan = useCompassStore((s) => s.addToPlan);
  const removeFromPlan = useCompassStore((s) => s.removeFromPlan);

  return (
    <article className="glass glass-interactive flex min-h-[280px] flex-col rounded-2xl p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <span className="rounded-md bg-brand-tint/80 px-2 py-1 font-mono text-xs font-semibold text-brand-purple">
          {session.code}
        </span>
        <span className="shrink-0 text-right font-mono text-xs leading-relaxed text-muted">
          <span className="block font-semibold text-ink">{dayLabel(session.start)}</span>
          {rangeLabel(session.start, session.end)}
        </span>
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <span
          className={`rounded-md px-1.5 py-0.5 font-semibold ${
            session.level === 0
              ? "bg-surface/60 text-muted"
              : "bg-brand-tint text-brand-purple"
          }`}
        >
          {levelLabel(session.level)}
        </span>
        <span className="text-muted">{session.type}</span>
      </div>

      <h3 className="mb-1.5 text-base font-semibold leading-snug">
        <Link
          href={`/session/${encodeURIComponent(session.id)}`}
          className="text-ink transition duration-200 hover:text-brand-purple"
        >
          {session.title}
        </Link>
      </h3>

      <p className="line-clamp-2 mb-4 text-sm leading-relaxed text-muted">
        {session.abstract}
      </p>

      {!isPlanned && fit && (
        <div className="mb-3">
          <FitPill fit={fit} />
        </div>
      )}

      <div className="mt-auto border-t border-[var(--glass-ring)] pt-3">
        <div className="mb-3 flex min-w-0 flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
          <span className="inline-flex items-center gap-1.5"><Clock3 size={13} aria-hidden />{rangeLabel(session.start, session.end)}</span>
          <span className="inline-flex min-w-0 items-center gap-1.5 truncate"><MapPin size={13} className="shrink-0" aria-hidden />{session.venue}</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-muted">{session.reservable ? "Reservable" : "Walk-up"}</span>
          {isPlanned ? (
            <Button variant="secondary" onClick={() => removeFromPlan(session.id)}>
              <Check size={16} strokeWidth={2} aria-hidden />
              In your stack
            </Button>
          ) : (
            <Button onClick={() => addToPlan(session.id)}>
              <Plus size={16} strokeWidth={2} aria-hidden />
              Add to stack
            </Button>
          )}
        </div>
      </div>
    </article>
  );
}
