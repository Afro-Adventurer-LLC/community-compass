"use client";

import { useMemo, useState } from "react";
import { Clock } from "lucide-react";
import type { Session, UserPrefs } from "@/types";
import { durationLabel, rangeLabel } from "@/lib/format";
import {
  suggestForGap,
  type Block,
  type Gap,
  type WalkLookup,
} from "@/lib/schedule";
import Button from "@/components/ui/Button";
import SessionRow from "@/components/SessionRow";

// A free window in the stack, with reachable, ranked suggestions on demand.
export default function GapRow({
  gap,
  sessions,
  blocks,
  prefs,
  lookup,
}: {
  gap: Gap;
  sessions: Session[];
  blocks: Block[];
  prefs: UserPrefs;
  lookup: WalkLookup;
}) {
  const [open, setOpen] = useState(false);

  const suggestions = useMemo(
    () => (open ? suggestForGap(gap, sessions, blocks, prefs, lookup, 3) : []),
    [open, gap, sessions, blocks, prefs, lookup]
  );

  const route =
    gap.before.venue && gap.after.venue
      ? `${gap.before.venue} to ${gap.after.venue}`
      : "";

  return (
    <li className="rounded-xl border border-dashed border-border-strong p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-sm text-muted">
          <Clock size={16} strokeWidth={1.75} aria-hidden />
          <span>
            Free{" "}
            <span className="font-mono text-ink">
              {rangeLabel(gap.start, gap.end)}
            </span>{" "}
            · {durationLabel(gap.minutes)}
            {route && ` · ${route}`}
          </span>
        </p>
        <Button
          variant="secondary"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "Hide suggestions" : "Fill this gap"}
        </Button>
      </div>

      {open &&
        (suggestions.length > 0 ? (
          <ul className="mt-3 space-y-2">
            {suggestions.map((s) => (
              <SessionRow
                key={s.session.id}
                session={s.session}
                fit={s.fit}
                reasons={
                  s.reasons.length > 0 ? s.reasons : ["Fits the time and the walk"]
                }
              />
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-muted">
            Nothing reachable fits this window. Widen your interests on the Plan
            page or turn on events.
          </p>
        ))}
    </li>
  );
}
