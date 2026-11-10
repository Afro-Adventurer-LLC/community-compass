// ---------------------------------------------------------------------------
// Week planner + "bring your own AI" bridge.
//
// planWeek() is a deterministic, local planner (no network). The AI bridge
// builds a prompt the user pastes into any assistant and parses the reply.
// When the AWS-hosted AI arrives, it replaces the paste step but keeps the same
// prompt-in / list-of-codes-out contract.
// ---------------------------------------------------------------------------

import type { Session, UserPrefs, VenueGraph } from "@/types";
import { dateOf, dayLabel, rangeLabel } from "@/lib/format";
import { reasonsFor, scoreDetail, titleCase } from "@/lib/ranking";
import {
  autoEligible,
  fitCheck,
  isAcceptableFit,
  isComfortableFit,
  plannedTitles,
  sessionToBlock,
  titleKey,
  type Block,
  type FitResult,
  type WalkLookup,
} from "@/lib/schedule";

export interface PlannedPick {
  session: Session;
  score: number;
  reasons: string[];
  fit: FitResult;
}

export interface PlannedDay {
  day: string;
  theme: string;
  picks: PlannedPick[];
  plannedToday: number; // sessions already in the stack that day
  full: boolean; // the daily limit is already used up by the stack
}

export function catalogDays(sessions: Session[]): string[] {
  return Array.from(new Set(sessions.map((s) => dateOf(s.start)))).sort();
}

/** Days the user attends; an empty selection means every day. */
export function activeDays(allDays: string[], prefs: UserPrefs): string[] {
  const chosen = prefs.days.filter((d) => allDays.includes(d));
  return chosen.length > 0 ? chosen : allDays;
}

/**
 * A short theme for the day: the interest the day's picks share most. Themes
 * already used on earlier days are avoided when there is another choice, so
 * the week reads as distinct days rather than one repeated label.
 */
function themeOf(
  picks: PlannedPick[],
  prefs: UserPrefs,
  used: Set<string>
): string {
  if (picks.length === 0) return "";
  const counts = new Map<string, number>();
  for (const p of picks) {
    for (const t of scoreDetail(p.session, prefs).matchedTopics) {
      counts.set(t, (counts.get(t) ?? 0) + 1);
    }
  }
  if (counts.size === 0) {
    for (const p of picks) {
      counts.set(p.session.track, (counts.get(p.session.track) ?? 0) + 1);
    }
  }
  const ranked = Array.from(counts.entries()).sort(
    (a, b) => b[1] - a[1] || a[0].localeCompare(b[0])
  );
  const choice = ranked.find(([t]) => !used.has(t)) ?? ranked[0];
  used.add(choice[0]);
  return titleCase(choice[0]);
}

/**
 * Greedy planner: best-scoring sessions first, skipping anything that overlaps
 * or strands you (not reachable / unknown walk). Plans around the existing
 * stack and never exceeds `maxPerDay` timed sessions per day in total.
 *
 * Two passes: the first only accepts sessions whose walks keep the full
 * 10-minute buffer; the second fills any remaining slots with tight walks.
 */
export function planWeek(
  sessions: Session[],
  existing: Block[],
  prefs: UserPrefs,
  lookup: WalkLookup,
  days: string[]
): PlannedDay[] {
  const planned = new Set(existing.map((b) => b.key));
  const needsInterestMatch = prefs.interests.length > 0;
  // Repeats of one session run on several days; never plan the same one twice.
  const seenTitles = plannedTitles(existing);
  const usedThemes = new Set<string>();

  return days.map((day) => {
    const timedToday = existing.filter(
      (b) => !b.dropIn && b.kind === "session" && dateOf(b.start) === day
    ).length;
    const remaining = Math.max(0, prefs.maxPerDay - timedToday);

    const candidates = sessions
      .filter((s) => dateOf(s.start) === day && autoEligible(s, prefs))
      .filter((s) => !planned.has(`s:${s.id}`))
      .map((s) => ({ s, d: scoreDetail(s, prefs) }))
      .filter(({ d }) => !needsInterestMatch || d.matchedTopics.length > 0)
      .sort(
        (a, b) => b.d.score - a.d.score || a.s.start.localeCompare(b.s.start)
      );

    const working: Block[] = [...existing];
    const chosen: Session[] = [];
    for (const fits of [isComfortableFit, isAcceptableFit]) {
      for (const { s } of candidates) {
        if (chosen.length >= remaining) break;
        if (seenTitles.has(titleKey(s.title))) continue;
        const block = sessionToBlock(s);
        if (!fits(fitCheck(block, working, lookup))) continue;
        working.push(block);
        chosen.push(s);
        seenTitles.add(titleKey(s.title));
      }
    }

    const picks: PlannedPick[] = chosen
      .sort((a, b) => a.start.localeCompare(b.start))
      .map((s) => ({
        session: s,
        score: scoreDetail(s, prefs).score,
        reasons: reasonsFor(s, prefs),
        fit: fitCheck(sessionToBlock(s), working, lookup),
      }));

    return {
      day,
      theme: themeOf(picks, prefs, usedThemes),
      picks,
      plannedToday: timedToday,
      full: remaining === 0,
    };
  });
}

// --- Bring-your-own-AI bridge ------------------------------------------------

export interface PromptInput {
  sessions: Session[];
  prefs: UserPrefs;
  days: string[];
  graph: VenueGraph;
  limit?: number;
}

/** Top candidates per day, so the prompt stays short and covers the week. */
function aiCandidates(
  sessions: Session[],
  prefs: UserPrefs,
  days: string[],
  limit: number
): Session[] {
  const perDay = Math.max(5, Math.ceil(limit / Math.max(1, days.length)));
  const out: Session[] = [];
  for (const day of days) {
    const ranked = sessions
      .filter((s) => dateOf(s.start) === day && autoEligible(s, prefs))
      .map((s) => ({ s, d: scoreDetail(s, prefs) }))
      .filter(({ d }) => prefs.interests.length === 0 || d.matchedTopics.length > 0)
      .sort((a, b) => b.d.score - a.d.score || a.s.start.localeCompare(b.s.start))
      .slice(0, perDay)
      .map(({ s }) => s);
    out.push(...ranked);
  }
  return out.sort((a, b) => a.start.localeCompare(b.start));
}

export function buildAiPrompt({
  sessions,
  prefs,
  days,
  graph,
  limit = 60,
}: PromptInput): string {
  const candidates = aiCandidates(sessions, prefs, days, limit);
  const walks = graph.edges
    .map((e) => `${e.from} <-> ${e.to}: ${e.minutes} min`)
    .join("\n");
  const rows = candidates.map((s) =>
    [
      s.code,
      `${dayLabel(s.start)} ${rangeLabel(s.start, s.end)}`,
      s.venue,
      s.level ? `L${s.level}` : "No level",
      s.type,
      s.title,
    ].join(" | ")
  );

  return [
    "You are helping me plan my AWS re:Invent 2026 week in Las Vegas. All times are Pacific.",
    "",
    "About me",
    `- Role: ${prefs.role}`,
    `- Preferred depth: Level ${prefs.depth}`,
    `- Interests: ${prefs.interests.length ? prefs.interests.join(", ") : "not specified"}`,
    `- Days I am attending: ${days.map(dayLabel).join(", ")}`,
    `- What I want out of the week: ${prefs.goal.trim() || "not specified"}`,
    "",
    "Rules",
    `- Pick at most ${prefs.maxPerDay} sessions per day.`,
    "- Never pick two sessions that overlap in time.",
    "- Venues are far apart. When two picks are in different venues, leave at least the walking time below plus 10 minutes between them.",
    "- Only use session codes from the candidate list. Do not invent sessions.",
    "",
    "Walking time between venues",
    walks,
    "",
    "Candidate sessions (code | day and time | venue | level | type | title)",
    ...rows,
    "",
    "Reply with JSON only, in exactly this shape:",
    '{"picks":[{"code":"SESSION_CODE","why":"one short sentence"}]}',
  ].join("\n");
}

export interface AiPick {
  session: Session;
  why?: string;
}

export interface AiReply {
  picks: AiPick[];
  unknown: string[]; // codes the reply mentioned that are not in the catalog
}

function extractJson(text: string): unknown {
  const stripped = text.replace(/```(?:json)?/gi, "");
  const candidates: Array<[string, string]> = [
    ["{", "}"],
    ["[", "]"],
  ];
  for (const [open, close] of candidates) {
    const i = stripped.indexOf(open);
    const j = stripped.lastIndexOf(close);
    if (i !== -1 && j > i) {
      try {
        return JSON.parse(stripped.slice(i, j + 1));
      } catch {
        // try the next shape
      }
    }
  }
  return null;
}

export function parseAiReply(text: string, sessions: Session[]): AiReply {
  const byCode = new Map(sessions.map((s) => [s.code.toUpperCase(), s]));
  const picks: AiPick[] = [];
  const unknown: string[] = [];
  const seen = new Set<string>();

  const take = (rawCode: string, why?: string) => {
    const code = rawCode.trim().toUpperCase();
    if (!code || seen.has(code)) return;
    seen.add(code);
    const session = byCode.get(code);
    if (session) picks.push({ session, why });
    else unknown.push(rawCode.trim());
  };

  const json = extractJson(text);
  const list: unknown = Array.isArray(json)
    ? json
    : json && typeof json === "object"
      ? (json as { picks?: unknown }).picks
      : null;

  if (Array.isArray(list)) {
    for (const entry of list) {
      if (typeof entry === "string") take(entry);
      else if (entry && typeof entry === "object") {
        const e = entry as { code?: unknown; why?: unknown };
        if (typeof e.code === "string") {
          take(e.code, typeof e.why === "string" ? e.why : undefined);
        }
      }
    }
  } else {
    // Fallback: scan free text for anything that looks like a session code.
    for (const match of text.match(/[A-Za-z]{2,5}\d{2,4}[A-Za-z0-9-]*/g) ?? []) {
      const code = match.toUpperCase();
      if (byCode.has(code)) take(code);
    }
  }

  return { picks, unknown };
}
