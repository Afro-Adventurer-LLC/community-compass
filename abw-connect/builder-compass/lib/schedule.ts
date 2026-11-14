// ---------------------------------------------------------------------------
// Schedule engine: turns the user's plan into normalized blocks and answers
// "does this fit?" — time conflicts, walking feasibility to the block before
// and after, free gaps, and stack stats. Pure functions; no React, no I/O.
//
// Drop-in items (parties, expo, featured experiences) are tracked but never
// create conflicts or act as a walking origin, because you can come and go.
// ---------------------------------------------------------------------------

import type {
  CustomItem,
  Feasibility,
  FeasibilityResult,
  PlanItem,
  PlanStatus,
  Session,
  UserPrefs,
} from "@/types";
import { dateOf, minutesBetween } from "@/lib/format";
import { feasibilityFor, overlaps } from "@/lib/walkGraph";
import { reasonsFor, scoreSession } from "@/lib/ranking";

export type WalkLookup = Map<string, number>;

export interface Block {
  key: string;
  kind: "session" | "custom";
  id: string; // session id or custom item id
  title: string;
  code?: string;
  venue: string;
  room: string;
  start: string;
  end: string;
  dropIn: boolean;
  status?: PlanStatus;
  session?: Session;
}

export function sessionToBlock(s: Session, status?: PlanStatus): Block {
  return {
    key: `s:${s.id}`,
    kind: "session",
    id: s.id,
    title: s.title,
    code: s.code,
    venue: s.venue,
    room: s.room,
    start: s.start,
    end: s.end,
    dropIn: !s.reservable,
    status,
    session: s,
  };
}

function customToBlock(c: CustomItem): Block {
  return {
    key: `c:${c.id}`,
    kind: "custom",
    id: c.id,
    title: c.title,
    venue: c.venue ?? "",
    room: c.room ?? "",
    start: c.start,
    end: c.end,
    dropIn: false,
  };
}

/**
 * Many sessions repeat under different codes (e.g. AIM316-R, AIM316-R1) at
 * different times. A normalized title identifies "the same session".
 */
export function titleKey(title: string): string {
  return title.trim().toLowerCase().replace(/\s+/g, " ");
}

export function plannedTitles(blocks: Block[]): Set<string> {
  return new Set(
    blocks.filter((b) => b.kind === "session").map((b) => titleKey(b.title))
  );
}

function sortBlocks(blocks: Block[]): Block[] {
  return [...blocks].sort(
    (a, b) =>
      new Date(a.start).getTime() - new Date(b.start).getTime() ||
      new Date(a.end).getTime() - new Date(b.end).getTime()
  );
}

export function toBlocks(
  plan: PlanItem[],
  sessions: Session[],
  customItems: CustomItem[]
): Block[] {
  const byId = new Map(sessions.map((s) => [s.id, s]));
  const blocks: Block[] = [];
  for (const p of plan) {
    const s = byId.get(p.sessionId);
    if (s) blocks.push(sessionToBlock(s, p.status));
  }
  for (const c of customItems) blocks.push(customToBlock(c));
  return sortBlocks(blocks);
}

// --- Fit checks --------------------------------------------------------------

export interface FitResult {
  conflicts: Block[];
  from: Block | null; // block you walk from
  to: Block | null; // block you walk to afterwards
  arrival: FeasibilityResult | null; // from -> this
  departure: FeasibilityResult | null; // this -> to
}

const EMPTY_FIT: FitResult = {
  conflicts: [],
  from: null,
  to: null,
  arrival: null,
  departure: null,
};

function walkCheck(
  from: Block,
  toVenue: string,
  toStart: string,
  lookup: WalkLookup
): FeasibilityResult | null {
  // Without a venue on either side there is nothing to measure.
  if (!from.venue || !toVenue) return null;
  return feasibilityFor(
    { venue: from.venue, end: from.end },
    { venue: toVenue, start: toStart },
    lookup
  );
}

/** How does `candidate` fit among `blocks`? (`blocks` may include candidate.) */
export function fitCheck(
  candidate: Block,
  blocks: Block[],
  lookup: WalkLookup
): FitResult {
  if (candidate.dropIn) return EMPTY_FIT;

  const others = blocks.filter((b) => b.key !== candidate.key && !b.dropIn);
  const day = dateOf(candidate.start);
  const candStart = new Date(candidate.start).getTime();
  const candEnd = new Date(candidate.end).getTime();

  const conflicts = others.filter((b) => overlaps(b, candidate));

  let from: Block | null = null;
  let to: Block | null = null;
  for (const b of others) {
    if (dateOf(b.start) !== day) continue;
    const bStart = new Date(b.start).getTime();
    const bEnd = new Date(b.end).getTime();
    if (bEnd <= candStart) {
      if (!from || bEnd > new Date(from.end).getTime()) from = b;
    } else if (bStart >= candEnd) {
      if (!to || bStart < new Date(to.start).getTime()) to = b;
    }
  }

  return {
    conflicts,
    from,
    to,
    arrival: from ? walkCheck(from, candidate.venue, candidate.start, lookup) : null,
    departure: to ? walkCheck(candidate, to.venue, to.start, lookup) : null,
  };
}

const RANK: Record<Feasibility, number> = {
  comfortable: 0,
  unknown: 1,
  tight: 2,
  "not-happening": 3,
};

export interface WorstWalk {
  result: FeasibilityResult;
  direction: "from" | "to";
  other: Block;
}

/** The least comfortable walk around a block, or null when there is none. */
export function worstWalk(fit: FitResult): WorstWalk | null {
  const options: WorstWalk[] = [];
  if (fit.arrival && fit.from) {
    options.push({ result: fit.arrival, direction: "from", other: fit.from });
  }
  if (fit.departure && fit.to) {
    options.push({ result: fit.departure, direction: "to", other: fit.to });
  }
  if (options.length === 0) return null;
  return options.reduce((worst, o) =>
    RANK[o.result.feasibility] > RANK[worst.result.feasibility] ? o : worst
  );
}

export function analyzeAll(
  blocks: Block[],
  lookup: WalkLookup
): Map<string, FitResult> {
  const map = new Map<string, FitResult>();
  for (const b of blocks) map.set(b.key, fitCheck(b, blocks, lookup));
  return map;
}

// --- Stats & week overview ---------------------------------------------------

export interface StackStats {
  sessions: number;
  custom: number;
  hours: number;
  days: number;
  busiestDay: { day: string; hours: number } | null;
  walkMinutes: number;
  tight: number;
  notReachable: number;
  conflictPairs: number;
}

function blockHours(b: Block): number {
  return minutesBetween(b.start, b.end) / 60;
}

export function stackStats(
  blocks: Block[],
  fits: Map<string, FitResult>
): StackStats {
  const timed = blocks.filter((b) => !b.dropIn);
  const perDay = new Map<string, number>();
  let walk = 0;
  let tight = 0;
  let notReachable = 0;
  let conflictTotal = 0;

  for (const b of timed) {
    perDay.set(dateOf(b.start), (perDay.get(dateOf(b.start)) ?? 0) + blockHours(b));
    const fit = fits.get(b.key);
    if (!fit) continue;
    conflictTotal += fit.conflicts.length;
    if (fit.arrival) {
      if (fit.arrival.walkMinutes) walk += fit.arrival.walkMinutes;
      if (fit.arrival.feasibility === "tight") tight += 1;
      if (fit.arrival.feasibility === "not-happening") notReachable += 1;
    }
  }

  let busiest: StackStats["busiestDay"] = null;
  for (const [day, hours] of Array.from(perDay.entries())) {
    if (!busiest || hours > busiest.hours) busiest = { day, hours };
  }

  return {
    sessions: blocks.filter((b) => b.kind === "session").length,
    custom: blocks.filter((b) => b.kind === "custom").length,
    hours: Math.round(timed.reduce((sum, b) => sum + blockHours(b), 0) * 10) / 10,
    days: perDay.size,
    busiestDay: busiest
      ? { day: busiest.day, hours: Math.round(busiest.hours * 10) / 10 }
      : null,
    walkMinutes: walk,
    tight,
    notReachable,
    // every conflict is counted from both sides
    conflictPairs: Math.round(conflictTotal / 2),
  };
}

export interface DaySummary {
  day: string;
  blocks: number;
  hours: number;
  issues: number; // blocks with a conflict or an unreachable walk
  tight: number; // walks that arrive with less than the 10-minute buffer
}

export function summarizeDays(
  days: string[],
  blocks: Block[],
  fits: Map<string, FitResult>
): DaySummary[] {
  return days.map((day) => {
    const dayBlocks = blocks.filter((b) => dateOf(b.start) === day);
    const timed = dayBlocks.filter((b) => !b.dropIn);
    const issues = timed.filter((b) => {
      const fit = fits.get(b.key);
      return (
        !!fit &&
        (fit.conflicts.length > 0 ||
          fit.arrival?.feasibility === "not-happening")
      );
    }).length;
    const tight = timed.filter(
      (b) => fits.get(b.key)?.arrival?.feasibility === "tight"
    ).length;
    return {
      day,
      tight,
      blocks: dayBlocks.length,
      hours: Math.round(timed.reduce((s, b) => s + blockHours(b), 0) * 10) / 10,
      issues,
    };
  });
}

// --- Free gaps ---------------------------------------------------------------

export interface Gap {
  key: string;
  day: string;
  start: string; // end of the block before
  end: string; // start of the block after
  minutes: number;
  before: Block;
  after: Block;
}

/** Free windows between timed blocks on the same day. */
export function findGaps(blocks: Block[], minMinutes = 60): Gap[] {
  const gaps: Gap[] = [];
  const timed = sortBlocks(blocks.filter((b) => !b.dropIn));
  const byDay = new Map<string, Block[]>();
  for (const b of timed) {
    const d = dateOf(b.start);
    byDay.set(d, [...(byDay.get(d) ?? []), b]);
  }

  for (const [day, list] of Array.from(byDay.entries())) {
    let frontier = list[0];
    for (const b of list.slice(1)) {
      if (new Date(b.start).getTime() > new Date(frontier.end).getTime()) {
        const minutes = minutesBetween(frontier.end, b.start);
        if (minutes >= minMinutes) {
          gaps.push({
            key: `${day}:${frontier.key}:${b.key}`,
            day,
            start: frontier.end,
            end: b.start,
            minutes,
            before: frontier,
            after: b,
          });
        }
      }
      if (new Date(b.end).getTime() > new Date(frontier.end).getTime()) {
        frontier = b;
      }
    }
  }
  return gaps;
}

// --- Suggestions (gaps + week planner share these rules) ---------------------

const MAX_EVENT_MINUTES = 240; // skips all-day expo / merch-store style items

/** May the planner suggest this session automatically? */
export function autoEligible(session: Session, prefs: UserPrefs): boolean {
  if (session.reservable) return true;
  if (!prefs.includeEvents) return false;
  const length =
    session.lengthMinutes ?? minutesBetween(session.start, session.end);
  return length <= MAX_EVENT_MINUTES;
}

export interface Suggestion {
  session: Session;
  fit: FitResult;
  reasons: string[];
  score: number;
}

/** A candidate is acceptable when it does not collide or strand the user. */
export function isAcceptableFit(fit: FitResult): boolean {
  if (fit.conflicts.length > 0) return false;
  const bad = (r: FeasibilityResult | null) =>
    !!r && (r.feasibility === "not-happening" || r.feasibility === "unknown");
  return !bad(fit.arrival) && !bad(fit.departure);
}

/** Acceptable, and every walk around it has the full 10-minute buffer. */
export function isComfortableFit(fit: FitResult): boolean {
  if (!isAcceptableFit(fit)) return false;
  const ok = (r: FeasibilityResult | null) => !r || r.feasibility === "comfortable";
  return ok(fit.arrival) && ok(fit.departure);
}

export function suggestForGap(
  gap: Gap,
  sessions: Session[],
  blocks: Block[],
  prefs: UserPrefs,
  lookup: WalkLookup,
  limit = 3
): Suggestion[] {
  const gapStart = new Date(gap.start).getTime();
  const gapEnd = new Date(gap.end).getTime();
  const planned = new Set(blocks.map((b) => b.key));
  const haveTitles = plannedTitles(blocks);
  const out: Suggestion[] = [];

  for (const session of sessions) {
    if (dateOf(session.start) !== gap.day) continue;
    if (haveTitles.has(titleKey(session.title))) continue; // a repeat of one you have
    const s = new Date(session.start).getTime();
    const e = new Date(session.end).getTime();
    if (s < gapStart || e > gapEnd) continue;
    if (!autoEligible(session, prefs)) continue;

    const block = sessionToBlock(session);
    if (planned.has(block.key)) continue;

    const fit = fitCheck(block, blocks, lookup);
    if (!isAcceptableFit(fit)) continue;

    out.push({
      session,
      fit,
      reasons: reasonsFor(session, prefs),
      score: scoreSession(session, prefs),
    });
  }

  // Comfortable walks always rank above tight ones, then by match score.
  const comfy = (s: Suggestion) => (isComfortableFit(s.fit) ? 1 : 0);
  return out
    .sort(
      (a, b) =>
        comfy(b) - comfy(a) ||
        b.score - a.score ||
        a.session.start.localeCompare(b.session.start)
    )
    .slice(0, limit);
}
