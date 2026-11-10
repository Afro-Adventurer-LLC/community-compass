"use client";

import { useMemo } from "react";
import type { Session, SessionLevel } from "@/types";
import { useCompassStore } from "@/lib/store";
import { dayLabel } from "@/lib/format";
import { titleCase, topRoles, topTopics } from "@/lib/ranking";
import Card from "@/components/ui/Card";
import Chip from "@/components/ui/Chip";
import Segmented from "@/components/ui/Segmented";
import { inputClass } from "@/components/ui/Button";

const DEPTHS: { value: string; label: string }[] = [
  { value: "100", label: "L100" },
  { value: "200", label: "L200" },
  { value: "300", label: "L300" },
  { value: "400", label: "L400" },
];

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value)
    ? list.filter((v) => v !== value)
    : [...list, value];
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 text-sm font-medium text-ink">{label}</div>
      {hint && <p className="mb-2 text-xs text-muted">{hint}</p>}
      {children}
    </div>
  );
}

export default function ProfilePanel({
  sessions,
  days,
}: {
  sessions: Session[];
  days: string[];
}) {
  const prefs = useCompassStore((s) => s.prefs);
  const setPrefs = useCompassStore((s) => s.setPrefs);

  const roles = useMemo(() => topRoles(sessions, 12), [sessions]);
  // Keep already-chosen interests visible even if they fall outside the top list.
  const topics = useMemo(() => {
    const top = topTopics(sessions, 30);
    return [...top, ...prefs.interests.filter((i) => !top.includes(i))];
  }, [sessions, prefs.interests]);

  return (
    <Card glass className="overflow-hidden p-0">
      <div className="border-b border-[var(--glass-ring)] px-5 py-4">
        <h2 className="font-semibold text-ink">Your planning profile</h2>
        <p className="mt-1 text-sm text-muted">Preferences are saved locally and shape every recommendation.</p>
      </div>

      <div className="space-y-6 p-5">

      <Field label="Role">
        <select
          value={prefs.role}
          onChange={(e) => setPrefs({ role: e.target.value })}
          className={inputClass}
          aria-label="Role"
        >
          {!roles.includes(prefs.role) && <option value={prefs.role}>{prefs.role}</option>}
          {roles.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </Field>

      <Field
        label="Depth you want"
        hint="100 Foundational, 200 Intermediate, 300 Advanced, 400 Expert."
      >
        <Segmented
          ariaLabel="Preferred session level"
          value={String(prefs.depth)}
          onChange={(v) => setPrefs({ depth: Number(v) as SessionLevel })}
          options={DEPTHS}
        />
      </Field>

      <Field
        label="Interests"
        hint={`${prefs.interests.length} selected. Sessions must match at least one.`}
      >
        <div className="flex flex-wrap gap-2">
          {topics.map((t) => (
            <Chip
              key={t}
              active={prefs.interests.includes(t)}
              onClick={() => setPrefs({ interests: toggle(prefs.interests, t) })}
            >
              {titleCase(t)}
            </Chip>
          ))}
        </div>
      </Field>

      <Field label="Days you will be there" hint="Select none to plan every day.">
        <div className="flex flex-wrap gap-2">
          {days.map((d) => (
            <Chip
              key={d}
              active={prefs.days.includes(d)}
              onClick={() => setPrefs({ days: toggle(prefs.days, d) })}
            >
              {dayLabel(d)}
            </Chip>
          ))}
        </div>
      </Field>

      <Field label="Sessions per day">
        <select
          value={prefs.maxPerDay}
          onChange={(e) => setPrefs({ maxPerDay: Number(e.target.value) })}
          className={inputClass}
          aria-label="Maximum sessions per day"
        >
          {[3, 4, 5, 6].map((n) => (
            <option key={n} value={n}>
              Up to {n}
            </option>
          ))}
        </select>
      </Field>

      <label className="flex cursor-pointer items-start gap-3 text-sm">
        <input
          type="checkbox"
          checked={prefs.includeEvents}
          onChange={(e) => setPrefs({ includeEvents: e.target.checked })}
          className="mt-0.5 h-4 w-4 cursor-pointer accent-brand-purple"
        />
        <span>
          <span className="font-medium text-ink">Include parties and events</span>
          <span className="block text-xs text-muted">
            Adds short featured experiences. All-day expo items are always left out.
          </span>
        </span>
      </label>

      <Field label="What do you want out of the week?" hint="Used in the prompt for your own AI.">
        <textarea
          rows={3}
          value={prefs.goal}
          onChange={(e) => setPrefs({ goal: e.target.value })}
          placeholder="Move our monolith to serverless and learn how teams govern AI agents."
          className={inputClass}
          aria-label="What do you want out of the week?"
        />
      </Field>
      </div>
    </Card>
  );
}
