"use client";

import Link from "next/link";
import { Check, Plus } from "lucide-react";
import type { Session } from "@/types";
import { useCompassStore } from "@/lib/store";
import { dayLabel, levelLabel, rangeLabel } from "@/lib/format";
import type { FitResult } from "@/lib/schedule";
import Button from "@/components/ui/Button";
import { FitPill } from "@/components/FeasibilityBadge";

// Compact session line used in planner results, gap suggestions, AI replies and
// related sessions. Shares its add/remove behaviour with SessionCard.
export default function SessionRow({
  session,
  fit,
  reasons,
  why,
  showDay = false,
}: {
  session: Session;
  fit?: FitResult | null;
  reasons?: string[];
  why?: string;
  showDay?: boolean;
}) {
  const isPlanned = useCompassStore((s) => s.isPlanned(session.id));
  const addToPlan = useCompassStore((s) => s.addToPlan);
  const removeFromPlan = useCompassStore((s) => s.removeFromPlan);

  const detail = why ?? (reasons && reasons.length > 0 ? reasons.join(" · ") : "");

  return (
    <li className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-border bg-canvas p-3">
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          <span className="font-mono font-medium text-ink">
            {showDay && `${dayLabel(session.start)} · `}
            {rangeLabel(session.start, session.end)}
          </span>
          <span className="font-mono font-semibold text-brand-purple">
            {session.code}
          </span>
          <span className="text-muted">
            {levelLabel(session.level)} · {session.type}
          </span>
        </div>
        <Link
          href={`/session/${encodeURIComponent(session.id)}`}
          className="text-sm font-semibold leading-snug text-ink transition duration-200 hover:text-brand-purple"
        >
          {session.title}
        </Link>
        <div className="mt-0.5 text-xs text-muted">{session.venue}</div>
        {detail && <p className="mt-1 text-xs text-muted">{detail}</p>}
        {fit && !isPlanned && (
          <div className="mt-2">
            <FitPill fit={fit} />
          </div>
        )}
      </div>
      {isPlanned ? (
        <Button variant="secondary" onClick={() => removeFromPlan(session.id)}>
          <Check size={16} strokeWidth={2} aria-hidden />
          In stack
        </Button>
      ) : (
        <Button onClick={() => addToPlan(session.id)}>
          <Plus size={16} strokeWidth={2} aria-hidden />
          Add
        </Button>
      )}
    </li>
  );
}
