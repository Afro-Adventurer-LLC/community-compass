"use client";

import { ChevronDown, X } from "lucide-react";
import { countActiveFilters, emptyFilters, type Filters } from "@/lib/search";
import { dayLabel, levelLabel } from "@/lib/format";
import type { SessionLevel, SessionType } from "@/types";
import Chip from "@/components/ui/Chip";

const LEVELS: SessionLevel[] = [100, 200, 300, 400, 500, 0];
const TYPES: SessionType[] = [
  "Keynote",
  "Breakout",
  "Chalk Talk",
  "Workshop",
  "Builder Session",
  "Code Talk",
  "Lightning Talk",
  "Lab",
  "Bootcamp",
  "Exam prep",
  "Featured",
  "Expo",
  "Gamified learning",
  "Event service",
];

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value)
    ? list.filter((v) => v !== value)
    : [...list, value];
}

function Group({
  label,
  count,
  defaultOpen = false,
  children,
}: {
  label: string;
  count: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  return (
    <details
      open={defaultOpen}
      className="group border-b border-[var(--glass-ring)] py-3 last:border-b-0"
    >
      <summary className="flex min-h-[32px] cursor-pointer list-none items-center justify-between text-sm font-medium text-ink [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2">
          {label}
          {count > 0 && (
            <span className="rounded-md bg-brand-tint px-1.5 py-0.5 font-mono text-xs text-brand-purple">
              {count}
            </span>
          )}
        </span>
        <ChevronDown
          size={16}
          strokeWidth={1.75}
          className="text-muted transition duration-200 group-open:rotate-180"
          aria-hidden
        />
      </summary>
      <div className="mt-3 flex flex-wrap gap-2">{children}</div>
    </details>
  );
}

interface Props {
  filters: Filters;
  onChange: (next: Filters) => void;
  tracks: string[];
  venues: string[];
  roles: string[];
}

export default function FilterChips({
  filters,
  onChange,
  tracks,
  venues,
  roles,
}: Props) {
  return (
    <div>
      <div className="flex items-center justify-between border-b border-[var(--glass-ring)] py-3">
        <span id="reservable-label" className="text-sm font-medium text-ink">
          Reservable only
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={filters.reservableOnly}
          aria-labelledby="reservable-label"
          onClick={() =>
            onChange({ ...filters, reservableOnly: !filters.reservableOnly })
          }
          className={`relative h-6 w-11 cursor-pointer rounded-full transition duration-200 ${
            filters.reservableOnly ? "bg-brand-purple" : "bg-border-strong"
          }`}
        >
          <span
            className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-canvas shadow-card transition duration-200 ${
              filters.reservableOnly ? "translate-x-5" : ""
            }`}
          />
        </button>
      </div>

      <Group label="Track" count={filters.tracks.length} defaultOpen>
        {tracks.map((t) => (
          <Chip
            glass
            key={t}
            active={filters.tracks.includes(t)}
            onClick={() => onChange({ ...filters, tracks: toggle(filters.tracks, t) })}
          >
            {t}
          </Chip>
        ))}
      </Group>

      <Group label="Role" count={filters.roles.length}>
        {roles.map((r) => (
          <Chip
            glass
            key={r}
            active={filters.roles.includes(r)}
            onClick={() => onChange({ ...filters, roles: toggle(filters.roles, r) })}
          >
            {r}
          </Chip>
        ))}
      </Group>

      <Group label="Level" count={filters.levels.length}>
        {LEVELS.map((l) => (
          <Chip
            glass
            key={l}
            active={filters.levels.includes(l)}
            onClick={() => onChange({ ...filters, levels: toggle(filters.levels, l) })}
          >
            {levelLabel(l)}
          </Chip>
        ))}
      </Group>

      <Group label="Session type" count={filters.types.length}>
        {TYPES.map((t) => (
          <Chip
            glass
            key={t}
            active={filters.types.includes(t)}
            onClick={() => onChange({ ...filters, types: toggle(filters.types, t) })}
          >
            {t}
          </Chip>
        ))}
      </Group>

      <Group label="Venue" count={filters.venues.length}>
        {venues.map((v) => (
          <Chip
            glass
            key={v}
            active={filters.venues.includes(v)}
            onClick={() => onChange({ ...filters, venues: toggle(filters.venues, v) })}
          >
            {v}
          </Chip>
        ))}
      </Group>
    </div>
  );
}

// --- Applied filters, each removable -----------------------------------------

function Applied({
  label,
  onRemove,
}: {
  label: string;
  onRemove: () => void;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-lg border border-brand-purple/20 bg-brand-tint/80 py-1 pl-2.5 pr-1 text-sm font-medium text-brand-purple backdrop-blur-md">
      {label}
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove filter ${label}`}
        className="flex h-6 w-6 cursor-pointer items-center justify-center rounded-md transition duration-200 hover:bg-brand-purple/10"
      >
        <X size={14} strokeWidth={2} aria-hidden />
      </button>
    </span>
  );
}

export function ActiveFilters({
  filters,
  onChange,
}: {
  filters: Filters;
  onChange: (next: Filters) => void;
}) {
  const count = countActiveFilters(filters) + (filters.text.trim() ? 1 : 0);
  if (count === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {filters.text.trim() && (
        <Applied
          label={`“${filters.text.trim()}”`}
          onRemove={() => onChange({ ...filters, text: "" })}
        />
      )}
      {filters.days.map((d) => (
        <Applied
          key={d}
          label={dayLabel(d)}
          onRemove={() => onChange({ ...filters, days: toggle(filters.days, d) })}
        />
      ))}
      {filters.tracks.map((t) => (
        <Applied
          key={t}
          label={t}
          onRemove={() => onChange({ ...filters, tracks: toggle(filters.tracks, t) })}
        />
      ))}
      {filters.roles.map((r) => (
        <Applied
          key={r}
          label={r}
          onRemove={() => onChange({ ...filters, roles: toggle(filters.roles, r) })}
        />
      ))}
      {filters.levels.map((l) => (
        <Applied
          key={l}
          label={levelLabel(l)}
          onRemove={() => onChange({ ...filters, levels: toggle(filters.levels, l) })}
        />
      ))}
      {filters.types.map((t) => (
        <Applied
          key={t}
          label={t}
          onRemove={() => onChange({ ...filters, types: toggle(filters.types, t) })}
        />
      ))}
      {filters.venues.map((v) => (
        <Applied
          key={v}
          label={v}
          onRemove={() => onChange({ ...filters, venues: toggle(filters.venues, v) })}
        />
      ))}
      {filters.reservableOnly && (
        <Applied
          label="Reservable only"
          onRemove={() => onChange({ ...filters, reservableOnly: false })}
        />
      )}
      <button
        type="button"
        onClick={() => onChange(emptyFilters)}
        className="cursor-pointer text-sm font-medium text-muted transition duration-200 hover:text-ink"
      >
        Clear all
      </button>
    </div>
  );
}
