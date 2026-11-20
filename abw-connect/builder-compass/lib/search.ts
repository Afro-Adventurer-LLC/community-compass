// ---------------------------------------------------------------------------
// Search + filtering over the session catalog.
// Fuzzy text search via Fuse.js, plus a rules-based natural-language parser
// that turns a sentence into visible, editable filters. The parser is the
// placeholder for the future AWS-hosted AI endpoint — same output shape.
// ---------------------------------------------------------------------------

import Fuse from "fuse.js";
import type { Session, SessionLevel, SessionType } from "@/types";
import { dateOf, dayLabel, weekdayName } from "@/lib/format";

export interface Filters {
  text: string;
  tracks: string[];
  levels: SessionLevel[];
  types: SessionType[];
  venues: string[];
  roles: string[];
  days: string[]; // YYYY-MM-DD
  reservableOnly: boolean;
}

export const emptyFilters: Filters = {
  text: "",
  tracks: [],
  levels: [],
  types: [],
  venues: [],
  roles: [],
  days: [],
  reservableOnly: false,
};

export function dayOf(session: Session): string {
  return dateOf(session.start);
}

export function buildFuse(sessions: Session[]): Fuse<Session> {
  return new Fuse(sessions, {
    keys: [
      { name: "title", weight: 3 },
      { name: "code", weight: 3 },
      { name: "topics", weight: 2 },
      { name: "track", weight: 1 },
      { name: "speakers", weight: 1 },
      { name: "abstract", weight: 1 },
    ],
    threshold: 0.35,
    ignoreLocation: true,
  });
}

export function countActiveFilters(f: Filters): number {
  return (
    f.tracks.length +
    f.levels.length +
    f.types.length +
    f.venues.length +
    f.roles.length +
    f.days.length +
    (f.reservableOnly ? 1 : 0)
  );
}

/** Filters the catalog. When `text` is set, results stay in relevance order. */
export function applyFilters(
  sessions: Session[],
  filters: Filters,
  fuse: Fuse<Session>
): Session[] {
  const base = filters.text.trim()
    ? fuse.search(filters.text.trim()).map((r) => r.item)
    : sessions;

  return base.filter(
    (s) =>
      (filters.tracks.length === 0 || filters.tracks.includes(s.track)) &&
      (filters.levels.length === 0 || filters.levels.includes(s.level)) &&
      (filters.types.length === 0 || filters.types.includes(s.type)) &&
      (filters.venues.length === 0 || filters.venues.includes(s.venue)) &&
      (filters.roles.length === 0 ||
        s.roles.some((r) => filters.roles.includes(r))) &&
      (filters.days.length === 0 || filters.days.includes(dayOf(s))) &&
      (!filters.reservableOnly || s.reservable)
  );
}

// -----------------------------------------------------------------------------
// Rules-based natural-language parser (placeholder for the AWS AI endpoint).
// Everything it understands becomes a normal filter the user can see and edit.
// -----------------------------------------------------------------------------

export interface NLResult {
  filters: Partial<Filters>;
  explanation: string;
  understood: boolean;
}

interface Scratch {
  v: string; // remaining, unconsumed text (lower-case)
}

function esc(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Remove every whole-word match of `pattern`; true if anything matched. */
function consume(scratch: Scratch, pattern: string): boolean {
  const probe = new RegExp(`\\b(?:${pattern})\\b`, "i");
  if (!probe.test(scratch.v)) return false;
  scratch.v = scratch.v.replace(new RegExp(probe.source, "gi"), " ");
  return true;
}

function addUnique<T>(list: T[] | undefined, value: T): T[] {
  const base = list ?? [];
  return base.includes(value) ? base : [...base, value];
}

const LEVEL_PATTERNS: Array<[string, SessionLevel]> = [
  ["beginner|intro(?:ductory)?|foundational|100", 100],
  ["intermediate|200", 200],
  ["advanced|300", 300],
  ["expert|deep[- ]dive|400", 400],
  ["distinguished|500", 500],
];

const TYPE_PATTERNS: Array<[string, SessionType]> = [
  ["chalk talks?", "Chalk Talk"],
  ["code talks?", "Code Talk"],
  ["builder(?:s['’]?|['’]s)? sessions?", "Builder Session"],
  ["lightning talks?|lightning", "Lightning Talk"],
  ["workshops?", "Workshop"],
  ["breakouts?(?: sessions?)?", "Breakout"],
  ["keynotes?", "Keynote"],
  ["labs?", "Lab"],
  ["bootcamps?", "Bootcamp"],
  ["exam prep", "Exam prep"],
];

const ROLE_PATTERNS: Array<[string, string]> = [
  ["data engineers?", "Data Engineer"],
  ["data scientists?", "Data Scientist"],
  ["security (?:specialists?|engineers?)", "Cloud Security Specialist"],
  ["devops", "DevOps Engineer"],
  ["architects?", "Solution / Systems Architect"],
  ["developers?|software engineers?|engineers?", "Developer / Engineer"],
  ["executives?|cto|cio|ceo", "IT Executive"],
  ["managers?", "IT Professional / Technical Manager"],
  ["admins?|administrators?", "IT Administrator"],
  ["researchers?|academics?", "Academic / Researcher"],
];

const TRACK_KEYWORDS: Array<[string, string]> = [
  [
    "ai|artificial intelligence|genai|gen ai|generative ai|ml|machine learning|llms?|agentic|agents?",
    "Artificial Intelligence",
  ],
  ["serverless|lambda", "Serverless"],
  ["security|identity|iam", "Security & Identity"],
  ["analytics|data lakes?", "Analytics"],
  ["containers?|kubernetes|eks|ecs", "Containers"],
  ["developer tools?|developer tooling|ci/cd", "Developer Tools"],
  ["networking|network", "Networking & Content Delivery"],
  ["databases?", "Databases"],
  ["storage", "Storage"],
  ["compute|ec2", "Compute"],
  ["migration|modernization", "Migration & Modernization"],
  ["architecture", "Architecture"],
  ["operations|observability", "Cloud Operations"],
];

const VENUE_ALIASES: Array<[string, string]> = [
  ["venetian", "Venetian"],
  ["caesars forum|forum", "Caesars Forum"],
  ["caesars palace", "Caesars Palace"],
  ["mgm(?: grand)?", "MGM Grand"],
  ["wynn|encore", "Wynn/Encore"],
  ["allegiant(?: stadium)?", "Allegiant Stadium"],
];

const STOPWORDS = new Set([
  "a", "an", "the", "in", "on", "at", "for", "of", "to", "me", "my", "i",
  "show", "find", "give", "want", "need", "some", "sessions", "session",
  "talks", "talk", "about", "with", "and", "or", "near", "around", "from",
  "please", "that", "are", "is", "any", "all", "day", "only", "level",
]);

const MONTHS: Record<string, string> = { nov: "11", dec: "12" };

export function parseNaturalLanguage(
  query: string,
  allSessions: Session[]
): NLResult {
  const scratch: Scratch = { v: ` ${query.toLowerCase()} ` };
  const filters: Partial<Filters> = {};
  const parts: string[] = [];

  const knownTracks = new Set(allSessions.map((s) => s.track));
  const knownVenues = new Set(allSessions.map((s) => s.venue));
  const knownRoles = new Set(allSessions.flatMap((s) => s.roles));
  const knownDays = Array.from(new Set(allSessions.map(dayOf))).sort();

  // Dates like "dec 2" / "december 2".
  const dateRe = /\b(nov(?:ember)?|dec(?:ember)?)\.?\s*0?(\d{1,2})\b/gi;
  for (const m of Array.from(scratch.v.matchAll(dateRe))) {
    const iso = `2026-${MONTHS[m[1].slice(0, 3).toLowerCase()]}-${m[2].padStart(2, "0")}`;
    if (knownDays.includes(iso)) {
      filters.days = addUnique(filters.days, iso);
    }
  }
  scratch.v = scratch.v.replace(dateRe, " ");

  // Weekday names ("wednesday", "wed").
  for (const day of knownDays) {
    const full = weekdayName(day);
    const short = full.slice(0, 3);
    const extra = full === "tuesday" ? "|tues" : full === "thursday" ? "|thur|thurs" : "";
    if (consume(scratch, `${full}|${short}${extra}`)) {
      filters.days = addUnique(filters.days, day);
    }
  }

  for (const [pattern, level] of LEVEL_PATTERNS) {
    if (consume(scratch, pattern)) filters.levels = addUnique(filters.levels, level);
  }
  for (const [pattern, type] of TYPE_PATTERNS) {
    if (consume(scratch, pattern)) filters.types = addUnique(filters.types, type);
  }

  for (const venue of Array.from(knownVenues)) {
    if (venue === "Various Locations") continue;
    if (consume(scratch, esc(venue.toLowerCase()))) {
      filters.venues = addUnique(filters.venues, venue);
    }
  }
  for (const [pattern, venue] of VENUE_ALIASES) {
    if (knownVenues.has(venue) && consume(scratch, pattern)) {
      filters.venues = addUnique(filters.venues, venue);
    }
  }

  for (const [pattern, role] of ROLE_PATTERNS) {
    if (knownRoles.has(role) && consume(scratch, pattern)) {
      filters.roles = addUnique(filters.roles, role);
    }
  }

  if (consume(scratch, "reservable|reservations?|reserve")) {
    filters.reservableOnly = true;
  }

  for (const track of Array.from(knownTracks)) {
    if (track === "General") continue;
    if (consume(scratch, esc(track.toLowerCase()))) {
      filters.tracks = addUnique(filters.tracks, track);
    }
  }
  for (const [pattern, track] of TRACK_KEYWORDS) {
    if (knownTracks.has(track) && consume(scratch, pattern)) {
      filters.tracks = addUnique(filters.tracks, track);
    }
  }

  // Whatever is left becomes the free-text search.
  const leftover = scratch.v
    .replace(/[^a-z0-9+#.\- ]/g, " ")
    .split(/\s+/)
    .filter((w) => w && !STOPWORDS.has(w))
    .join(" ");
  if (leftover) filters.text = leftover;

  if (filters.days?.length) parts.push(filters.days.map(dayLabel).join(" / "));
  if (filters.levels?.length) parts.push(`level ${filters.levels.join(" / ")}`);
  if (filters.types?.length) parts.push(filters.types.join(" / "));
  if (filters.tracks?.length) parts.push(filters.tracks.join(" / "));
  if (filters.venues?.length) parts.push(filters.venues.join(" / "));
  if (filters.roles?.length) parts.push(`for ${filters.roles.join(" / ")}`);
  if (filters.reservableOnly) parts.push("reservable only");
  if (leftover) parts.push(`text "${leftover}"`);

  const understood = parts.length > 0;
  const explanation = understood
    ? `Read as ${parts.join(", ")}. Change or remove any filter below.`
    : "I could not find a day, level, topic, or venue in that. Try something like “advanced AI workshops on Wednesday”.";

  return { filters, explanation, understood };
}
